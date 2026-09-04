from __future__ import annotations

import shutil
import time
from collections.abc import Callable
from pathlib import Path
from threading import Event
from typing import Any

from ..api import AceClient, GenerationCancelled
from ..models import EditRequest, GenerationRequest, GenerationResult
from ..runtime import RuntimeManager
from ..storage import Storage

Progress = Callable[[dict[str, Any]], None]


class GenerationService:
    def __init__(self, runtime: RuntimeManager, storage: Storage) -> None:
        self.runtime = runtime
        self.storage = storage
        self.client: AceClient | None = None
        self.initialized = False

    def client_ready(self) -> AceClient:
        if self.client:
            return self.client
        port, token = self.runtime.start()
        client = AceClient(port, token, timeout=900)
        last_error: Exception | None = None
        for _attempt in range(60):
            try:
                client.health()
                break
            except Exception as exc:
                last_error = exc
                time.sleep(0.5)
        else:
            raise RuntimeError(f"ACE-Step did not become ready: {last_error}")
        model, lm = self.runtime.selected_models()
        client.initialize(model, lm)
        self.client = client
        self.initialized = True
        active = next((adapter for adapter in self.storage.adapters() if adapter.active), None)
        if active and Path(active.path).exists():
            try:
                client.load_adapter(active.path, active.name)
                client.set_adapter_scale(active.scale, active.name)
                client.toggle_adapter(True)
            except Exception:
                self.storage.update_adapter(active.id, active=False)
        elif active:
            self.storage.update_adapter(active.id, active=False)
        return client

    def reset_client(self) -> None:
        self.client = None
        self.initialized = False

    def generate(
        self,
        request: GenerationRequest,
        progress_callback: Progress | None = None,
        cancel_event: Event | None = None,
        parent_id: str | None = None,
    ) -> GenerationResult:
        if cancel_event and cancel_event.is_set():
            raise GenerationCancelled("Generation cancelled")
        caps = self.runtime.generation_caps()
        max_versions = caps["max_versions"] or 4
        if request.batch_size > max_versions:
            raise ValueError(
                f"Batch size {request.batch_size} exceeds memory cap of {max_versions}. "
                f"Lower the number of versions or switch to a higher memory mode in Settings."
            )
        max_duration = caps["max_duration_sec"]
        if max_duration and request.duration > max_duration:
            raise ValueError(
                f"Duration {request.duration:.0f}s exceeds memory cap of {max_duration}s. "
                f"Shorten the track or switch to a higher memory mode in Settings."
            )
        client = self.client_ready()
        if progress_callback:
            progress_callback({"progress": 0, "stage": "Submitting", "progress_text": "Adding your song to the generation queue"})
        task_id = client.generate(request)
        self.storage.record_job(task_id, "running", request.fields())
        started = time.monotonic()

        def progress(update: dict[str, Any]) -> None:
            value = float(update.get("progress", 0))
            if value >= 0.03:
                update["eta_seconds"] = max(0, (time.monotonic() - started) * (1 - value) / value)
            if progress_callback:
                progress_callback(update)

        try:
            result = client.wait(task_id, progress_callback=progress, cancel_event=cancel_event)
        except Exception as exc:
            state = "cancelled" if cancel_event and cancel_event.is_set() else "failed"
            self.storage.record_job(task_id, state, request.fields(), str(exc))
            if state == "cancelled":
                raise GenerationCancelled("Generation cancelled") from exc
            raise
        if result.title == "Untitled generation":
            result.title = self.prompt_title(request.prompt)
        saved_paths: list[str] = []
        for number, source in enumerate(result.audio_paths, 1):
            target = self.storage.audio_dir / f"{task_id}-{number}.wav"
            if Path(source).is_file():
                shutil.copy2(source, target)
            else:
                client.download_audio(source, target)
            self.storage.save_generation(
                f"{task_id}-{number}",
                result.title,
                request.task_type,
                str(target),
                request.prompt,
                request.lyrics,
                result.metadata,
                parent_id,
            )
            saved_paths.append(str(target))
        result.audio_paths = saved_paths
        self.storage.record_job(task_id, "complete", request.fields())
        return result

    def edit(self, request: EditRequest, progress_callback: Progress | None = None, cancel_event: Event | None = None) -> GenerationResult:
        model = self.runtime.selected_models()[0]
        if request.task_type in {"lego", "extract", "complete"} and "base" not in model:
            raise ValueError("Lego, Extract, and Complete require an installed Base model selected in Settings.")
        return self.generate(request.generation_request(model), progress_callback, cancel_event, request.parent_id)

    @staticmethod
    def prompt_title(prompt: str) -> str:
        import re

        words = re.findall(r"[\w'-]+", prompt, flags=re.UNICODE)[:7]
        return " ".join(words).title() or "Untitled generation"
