import tempfile
import unittest
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import patch

from ace_studio.models import EditRequest, GenerationResult, TrainingRequest
from ace_studio.services import GenerationService, TrainingService
from ace_studio.storage import Storage


class FakeClient:
    def __init__(self):
        self.calls = []

    def generate(self, request):
        self.request = request
        return "job"

    def wait(self, _task_id, **_kwargs):
        return GenerationResult("job", "Edited", [self.source], "", "", {})

    def start_training(self, kind, payload):
        self.calls.append((kind, payload))
        return {"message": "started"}

    def scan_dataset(self, *_args):
        return {"samples": [{"index": 0, "filename": "one.wav", "audio_path": "/one.wav"}]}

    def update_dataset_sample(self, index, payload):
        return {"sample": {"index": index, "filename": "one.wav", "audio_path": "/one.wav", **payload, "labeled": True}}

    def save_dataset(self, *_args):
        return {"message": "saved"}

    def auto_label_dataset(self, *_args):
        return {"task_id": "label"}

    def preprocess_dataset(self, *_args):
        return {"task_id": "preprocess"}

    def auto_label_status(self, task_id):
        return {"task_id": task_id}

    def preprocess_status(self, task_id):
        return {"task_id": task_id}

    def training_status(self):
        return {"status": "Idle"}

    def stop_training(self):
        return {"message": "stopped"}

    def unload_adapter(self):
        self.calls.append(("unload",))

    def export_adapter(self, output, target):
        Path(target).mkdir(parents=True)
        self.calls.append((output, target))

    def load_adapter(self, path, name):
        self.calls.append(("load", path, name))

    def set_adapter_scale(self, scale, name):
        self.calls.append(("scale", scale, name))

    def toggle_adapter(self, enabled):
        self.calls.append(("toggle", enabled))


class ServiceTest(unittest.TestCase):
    def test_client_start_initializes_models_and_restores_active_adapter(self):
        class Client(FakeClient):
            def __init__(self, *_args, **_kwargs):
                super().__init__()

            def health(self):
                return {"ok": True}

            def initialize(self, model, lm):
                self.calls.append(("initialize", model, lm))

        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            adapter_path = Path(directory) / "adapter"
            adapter_path.mkdir()
            storage.add_adapter("one", "Voice", str(adapter_path), "lora", {})
            storage.update_adapter("one", active=True, scale=0.5)
            runtime = SimpleNamespace(start=lambda: (8000, "token"), selected_models=lambda: ("base", "lm"))
            service = GenerationService(runtime, storage)
            with patch("ace_studio.services.generation.AceClient", Client):
                client = service.client_ready()
            self.assertIn(("initialize", "base", "lm"), client.calls)
            self.assertIs(service.client_ready(), client)
            service.reset_client()
            self.assertIsNone(service.client)

    def test_edit_uses_shared_generation_and_parent_link(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            runtime = SimpleNamespace(selected_models=lambda: ("acestep-v15-base", None))
            service = GenerationService(runtime, storage)
            client = FakeClient()
            source = Path(directory) / "source.wav"
            source.write_bytes(b"RIFFsource")
            storage.save_generation("original", "Source", "text2music", str(source), "", "", {})
            result_audio = Path(directory) / "result.wav"
            result_audio.write_bytes(b"RIFFresult")
            client.source = str(result_audio)
            service.client = client
            result = service.edit(EditRequest(str(source), "complete", track_classes=["drums"], parent_id="original"))
            saved = storage.generation("job-1")
            self.assertEqual(result.audio_paths, [str(storage.audio_dir / "job-1.wav")])
            self.assertEqual(saved["parent_id"], "original")

    def test_track_aware_edit_requires_base_model(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.wav"
            source.touch()
            service = GenerationService(
                SimpleNamespace(selected_models=lambda: ("acestep-v15-turbo", None)), Storage(Path(directory) / "data")
            )
            with self.assertRaisesRegex(ValueError, "Base"):
                service.edit(EditRequest(str(source), "extract", track_name="vocals"))

    def test_training_export_registers_and_activates_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            generation = SimpleNamespace(client_ready=lambda: client, runtime=SimpleNamespace())
            client = FakeClient()
            training = TrainingService(generation, storage)
            tensor_dir = Path(directory) / "tensors"
            tensor_dir.mkdir()
            training.start(TrainingRequest("lora", str(tensor_dir), str(Path(directory) / "run")))
            exported = training.export("My Voice", "lora", str(Path(directory) / "run"))
            adapter = storage.adapters()[0]
            self.assertEqual(Path(adapter.path), exported)
            training.activate(adapter.id, scale=0.5)
            self.assertTrue(storage.adapters()[0].active)
            training.deactivate()
            self.assertFalse(storage.adapters()[0].active)

    def test_training_dataset_workflow_delegates_and_uses_managed_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            client = FakeClient()
            training = TrainingService(SimpleNamespace(client_ready=lambda: client, runtime=SimpleNamespace()), storage)
            samples = training.scan("/audio", "My Set")
            samples[0].caption = "ambient"
            self.assertTrue(training.update_sample(samples[0]).labeled)
            dataset = training.save("My Set")
            self.assertEqual(dataset.name, "dataset.json")
            self.assertEqual(training.auto_label(dataset), "label")
            task, tensors = training.preprocess("My Set")
            self.assertEqual((task, tensors.name), ("preprocess", "tensors"))
            self.assertEqual(training.task_status("label", "one")["task_id"], "one")
            self.assertEqual(training.task_status("preprocess", "two")["task_id"], "two")
            self.assertEqual(training.status()["status"], "Idle")
            self.assertEqual(training.stop()["message"], "stopped")

    def test_one_click_training_pipeline_registers_without_activation(self):
        class PipelineClient(FakeClient):
            def auto_label_status(self, task_id):
                return {"task_id": task_id, "status": "completed"}

            def preprocess_status(self, task_id):
                return {"task_id": task_id, "status": "completed"}

            def training_status(self):
                return {"status": "Complete", "is_training": False, "current_epoch": 10, "config": {"epochs": 10}}

        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            client = PipelineClient()
            generation = SimpleNamespace(client_ready=lambda: client, runtime=SimpleNamespace(selected_models=lambda: ("turbo", "lm")))
            training = TrainingService(generation, storage)
            updates = []
            exported = training.run_pipeline(
                "/audio",
                "My Voice",
                "",
                True,
                TrainingRequest("lora", "", str(Path(directory) / "run")),
                updates.append,
            )
            self.assertTrue(exported.exists())
            self.assertEqual([adapter.name for adapter in storage.adapters()], ["My Voice"])
            self.assertFalse(storage.adapters()[0].active)
            self.assertEqual(
                [update["stage"] for update in updates],
                [
                    "Scanning dataset",
                    "Dataset saved",
                    "Auto-labeling",
                    "Auto-labeling",
                    "Preprocessing",
                    "Preprocessing",
                    "Training",
                    "Training",
                    "Registering adapter",
                ],
            )

    def test_one_click_training_cancellation_does_not_start_or_export(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            client = FakeClient()
            training = TrainingService(
                SimpleNamespace(client_ready=lambda: client, runtime=SimpleNamespace(selected_models=lambda: ("turbo", None))), storage
            )
            cancelled = Event()
            cancelled.set()
            with self.assertRaises(InterruptedError):
                training.run_pipeline(
                    "/audio", "My Voice", "", True, TrainingRequest("lora", "", str(Path(directory) / "run")), cancel_event=cancelled
                )
            self.assertEqual(client.calls, [])
            self.assertEqual(storage.adapters(), [])

    def test_missing_adapter_is_rejected_and_deactivated(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            storage.add_adapter("gone", "Gone", "/missing", "lora", {})
            storage.update_adapter("gone", active=True)
            training = TrainingService(SimpleNamespace(client_ready=lambda: FakeClient(), runtime=SimpleNamespace()), storage)
            with self.assertRaisesRegex(ValueError, "missing"):
                training.activate("gone")
            self.assertFalse(storage.adapters()[0].active)


if __name__ == "__main__":
    unittest.main()
