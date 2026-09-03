from __future__ import annotations

import time
import uuid
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Any

from ..api import AceClient
from ..models import DatasetSample, TrainingRequest
from ..storage import Storage
from .generation import GenerationService


class TrainingService:
    def __init__(self, generation: GenerationService, storage: Storage) -> None:
        self.generation = generation
        self.storage = storage

    def _client(self) -> AceClient:
        return self.generation.client_ready()

    def scan(self, audio_dir: str, name: str, tag: str = "", instrumental: bool = True) -> list[DatasetSample]:
        result = self._client().scan_dataset(audio_dir, name, tag, instrumental)
        return [DatasetSample.from_dict(value) for value in result.get("samples", [])]

    def update_sample(self, sample: DatasetSample) -> DatasetSample:
        result = self._client().update_dataset_sample(sample.index, sample.payload())
        return DatasetSample.from_dict(result["sample"])

    def save(self, name: str, tag: str = "", instrumental: bool = True) -> Path:
        directory = self.storage.training_dir / "datasets" / self._safe_name(name)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "dataset.json"
        self._client().save_dataset(str(path), name, tag, instrumental)
        return path

    def auto_label(self, dataset_path: Path) -> str:
        return str(self._client().auto_label_dataset(str(dataset_path))["task_id"])

    def preprocess(self, name: str) -> tuple[str, Path]:
        output = self.storage.training_dir / "datasets" / self._safe_name(name) / "tensors"
        output.mkdir(parents=True, exist_ok=True)
        task = self._client().preprocess_dataset(str(output))
        return str(task["task_id"]), output

    def task_status(self, kind: str, task_id: str) -> dict[str, Any]:
        client = self._client()
        return client.auto_label_status(task_id) if kind == "label" else client.preprocess_status(task_id)

    def run_pipeline(
        self,
        audio_dir: str,
        name: str,
        tag: str,
        instrumental: bool,
        request: TrainingRequest,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        cancel_event: Event | None = None,
    ) -> Path:
        def report(stage: str, **value: Any) -> None:
            if progress_callback:
                progress_callback({"stage": stage, **value})

        def cancelled() -> None:
            if cancel_event and cancel_event.is_set():
                raise InterruptedError("Training cancelled")

        def wait_for_task(kind: str, task_id: str, stage: str) -> None:
            while True:
                cancelled()
                value = self.task_status(kind, task_id)
                report(stage, **value)
                if value.get("status") == "completed":
                    return
                if value.get("status") == "failed":
                    raise RuntimeError(value.get("error") or f"{stage} failed")
                time.sleep(1)

        cancelled()
        report("Scanning dataset", progress=0)
        samples = self.scan(audio_dir, name, tag, instrumental)
        dataset_path = self.save(name, tag, instrumental)
        report("Dataset saved", progress=1, samples=len(samples), samples_data=samples)

        if any(not sample.labeled for sample in samples) and self.generation.runtime.selected_models()[1]:
            report("Auto-labeling")
            wait_for_task("label", self.auto_label(dataset_path), "Auto-labeling")

        cancelled()
        report("Preprocessing")
        task_id, tensor_dir = self.preprocess(name)
        wait_for_task("preprocess", task_id, "Preprocessing")
        request.tensor_dir = str(tensor_dir)

        cancelled()
        report("Training", progress=0)
        self.start(request)
        while True:
            if cancel_event and cancel_event.is_set():
                self.stop()
                raise InterruptedError("Training cancelled")
            value = self.status()
            report("Training", **value)
            if not value.get("is_training"):
                if value.get("error"):
                    raise RuntimeError(value["error"])
                break
            time.sleep(1)

        cancelled()
        report("Registering adapter", progress=1)
        return self.export(name, request.kind, request.output_dir)

    def start(self, request: TrainingRequest) -> dict[str, Any]:
        client = self._client()
        if any(adapter.active for adapter in self.storage.adapters()):
            client.unload_adapter()
            for adapter in self.storage.adapters():
                if adapter.active:
                    self.storage.update_adapter(adapter.id, active=False)
        return client.start_training(request.kind, request.payload())

    def status(self) -> dict[str, Any]:
        return self._client().training_status()

    def stop(self) -> dict[str, Any]:
        return self._client().stop_training()

    def export(self, name: str, kind: str, output_dir: str) -> Path:
        adapter_id = uuid.uuid4().hex
        destination = self.storage.training_dir / "adapters" / f"{self._safe_name(name)}-{adapter_id[:8]}"
        self._client().export_adapter(output_dir, str(destination))
        self.storage.add_adapter(adapter_id, name, str(destination), kind, {})
        return destination

    def activate(self, adapter_id: str, enabled: bool = True, scale: float = 1) -> None:
        adapter = next((item for item in self.storage.adapters() if item.id == adapter_id), None)
        if not adapter or not Path(adapter.path).exists():
            if adapter:
                self.storage.update_adapter(adapter.id, active=False)
            raise ValueError("The adapter files are missing.")
        client = self._client()
        client.load_adapter(adapter.path, adapter.name)
        client.set_adapter_scale(scale, adapter.name)
        client.toggle_adapter(enabled)
        self.storage.update_adapter(adapter.id, active=enabled, scale=scale)

    def deactivate(self) -> None:
        self._client().unload_adapter()
        for adapter in self.storage.adapters():
            if adapter.active:
                self.storage.update_adapter(adapter.id, active=False)

    @staticmethod
    def _safe_name(name: str) -> str:
        import re

        return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "dataset"
