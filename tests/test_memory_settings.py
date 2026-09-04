import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ace_studio.models import (
    HardwareReport,
    LMMode,
    MemoryMode,
    MemorySettings,
    RuntimeProfile,
)
from ace_studio.runtime import RuntimeManager
from ace_studio.services.generation import GenerationService
from ace_studio.services.training import TrainingService
from ace_studio.storage import Storage


class MemorySettingsModelTest(unittest.TestCase):
    def test_defaults_are_safe(self):
        settings = MemorySettings()
        self.assertEqual(settings.mode, MemoryMode.SAFE)
        self.assertEqual(settings.lm_mode, LMMode.DISABLED)
        self.assertEqual(settings.max_versions, 1)
        self.assertIsNone(settings.max_duration_sec)
        self.assertTrue(settings.training_checkpointing)
        self.assertEqual(settings.training_max_batch, 1)

    def test_detect_default_for_low_memory_cpu(self):
        report = HardwareReport("Linux", "x86_64", "cpu", 4, "CPU", RuntimeProfile.LINUX_CPU, True)
        settings = MemorySettings.detect_default(report)
        self.assertEqual(settings.mode, MemoryMode.SAFE)
        self.assertEqual(settings.lm_mode, LMMode.DISABLED)
        self.assertEqual(settings.max_versions, 1)
        self.assertEqual(settings.max_duration_sec, 180)

    def test_detect_default_for_mac_16gb(self):
        report = HardwareReport("Darwin", "arm64", "arm", 16, "Apple Silicon", RuntimeProfile.MACOS_MLX, True)
        settings = MemorySettings.detect_default(report)
        self.assertEqual(settings.mode, MemoryMode.SAFE)
        self.assertEqual(settings.lm_mode, LMMode.MINIMAL)

    def test_detect_default_for_20gb_cuda(self):
        report = HardwareReport("Linux", "x86_64", "cpu", 20, "NVIDIA RTX", RuntimeProfile.LINUX_CUDA, True)
        settings = MemorySettings.detect_default(report)
        self.assertEqual(settings.mode, MemoryMode.BALANCED)
        self.assertEqual(settings.lm_mode, LMMode.AS_SELECTED)

    def test_detect_default_for_32gb_cuda(self):
        report = HardwareReport("Linux", "x86_64", "cpu", 32, "NVIDIA RTX", RuntimeProfile.LINUX_CUDA, True)
        settings = MemorySettings.detect_default(report)
        self.assertEqual(settings.mode, MemoryMode.BALANCED)
        self.assertEqual(settings.lm_mode, LMMode.AS_SELECTED)
        self.assertEqual(settings.max_versions, 2)

    def test_to_dict_roundtrip(self):
        original = MemorySettings(
            mode=MemoryMode.BALANCED,
            lm_mode=LMMode.AS_SELECTED,
            max_versions=2,
            max_duration_sec=300,
            training_checkpointing=True,
            training_max_batch=2,
            training_max_rank=64,
            training_max_alpha=128,
        )
        restored = MemorySettings.from_dict(original.to_dict())
        self.assertEqual(restored.mode, original.mode)
        self.assertEqual(restored.lm_mode, original.lm_mode)
        self.assertEqual(restored.max_versions, original.max_versions)
        self.assertEqual(restored.max_duration_sec, original.max_duration_sec)
        self.assertEqual(restored.training_checkpointing, original.training_checkpointing)
        self.assertEqual(restored.training_max_batch, original.training_max_batch)
        self.assertEqual(restored.training_max_rank, original.training_max_rank)
        self.assertEqual(restored.training_max_alpha, original.training_max_alpha)

    def test_from_dict_corrupt_returns_defaults(self):
        settings = MemorySettings.from_dict({"invalid": "data"})
        self.assertEqual(settings.mode, MemoryMode.SAFE)
        self.assertEqual(settings.lm_mode, LMMode.DISABLED)

    def test_from_dict_clamps_values(self):
        settings = MemorySettings.from_dict({
            "mode": "safe",
            "lm_mode": "disabled",
            "max_versions": 10,
            "max_duration_sec": None,
            "training_checkpointing": True,
            "training_max_batch": 99,
            "training_max_rank": 999,
            "training_max_alpha": 999,
        })
        self.assertEqual(settings.max_versions, 4)
        self.assertEqual(settings.training_max_batch, 4)
        self.assertEqual(settings.training_max_rank, 256)
        self.assertEqual(settings.training_max_alpha, 512)


class RuntimeMemorySettingsTest(unittest.TestCase):
    def test_get_memory_settings_returns_defaults_when_no_file(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeManager(Storage(Path(directory)))
            settings = runtime.get_memory_settings()
            self.assertEqual(settings.mode, MemoryMode.SAFE)

    def test_save_and_load_memory_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeManager(Storage(Path(directory)))
            settings = MemorySettings(mode=MemoryMode.FULL, lm_mode=LMMode.AS_SELECTED, max_versions=3)
            runtime.save_memory_settings(settings)
            loaded = runtime.get_memory_settings()
            self.assertEqual(loaded.mode, MemoryMode.FULL)
            self.assertEqual(loaded.lm_mode, LMMode.AS_SELECTED)
            self.assertEqual(loaded.max_versions, 3)

    def test_corrupt_memory_file_falls_back_to_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeManager(Storage(Path(directory)))
            runtime.memory_settings_file.write_text("not json")
            settings = runtime.get_memory_settings()
            self.assertEqual(settings.mode, MemoryMode.SAFE)

    def test_memory_env_safe_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeManager(Storage(Path(directory)))
            runtime.save_memory_settings(MemorySettings(mode=MemoryMode.SAFE, lm_mode=LMMode.DISABLED))
            env = runtime.memory_env()
            self.assertEqual(env["ACESTEP_SAVE_MEMORY"], "1")
            self.assertEqual(env["ACESTEP_INIT_LLM"], "false")

    def test_memory_env_balanced_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeManager(Storage(Path(directory)))
            runtime.save_memory_settings(MemorySettings(mode=MemoryMode.BALANCED, lm_mode=LMMode.AS_SELECTED))
            env = runtime.memory_env()
            self.assertNotIn("ACESTEP_SAVE_MEMORY", env)
            self.assertNotIn("ACESTEP_INIT_LLM", env)

    def test_memory_env_minimal_lm(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeManager(Storage(Path(directory)))
            runtime.save_memory_settings(MemorySettings(mode=MemoryMode.SAFE, lm_mode=LMMode.MINIMAL))
            env = runtime.memory_env()
            self.assertEqual(env["ACESTEP_SAVE_MEMORY"], "1")
            self.assertEqual(env["ACESTEP_INIT_LLM"], "true")

    def test_generation_caps_returns_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeManager(Storage(Path(directory)))
            runtime.save_memory_settings(MemorySettings(max_versions=2, max_duration_sec=200))
            caps = runtime.generation_caps()
            self.assertEqual(caps["max_versions"], 2)
            self.assertEqual(caps["max_duration_sec"], 200)

    def test_training_caps_returns_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeManager(Storage(Path(directory)))
            runtime.save_memory_settings(MemorySettings(
                training_checkpointing=True,
                training_max_batch=2,
                training_max_rank=64,
                training_max_alpha=128,
            ))
            caps = runtime.training_caps()
            self.assertTrue(caps["gradient_checkpointing"])
            self.assertEqual(caps["max_batch"], 2)
            self.assertEqual(caps["max_rank"], 64)
            self.assertEqual(caps["max_alpha"], 128)


class GenerationCapEnforcementTest(unittest.TestCase):
    def _make_request(self, **overrides):
        defaults = dict(
            batch_size=1,
            duration=60,
            task_type="text2music",
            prompt="test",
            lyrics="",
            model="turbo",
            bpm=None,
            key_scale="",
            time_signature="",
            instrumental=False,
            vocal_language="en",
            thinking=True,
            seed=None,
            source_audio=None,
            reference_audio=None,
            repaint_start=0,
            repaint_end=None,
            cover_strength=1,
            instruction="",
            track_name=None,
            track_classes=[],
            advanced={"guidance_scale": "15"},
        )
        defaults.update(overrides)

        def fields():
            return {k: str(v) for k, v in defaults.items() if k in ("prompt", "batch_size")}

        return SimpleNamespace(**defaults, fields=fields)

    def test_batch_size_exceeding_cap_raises_value_error(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            runtime = RuntimeManager(storage)
            runtime.save_memory_settings(MemorySettings(max_versions=1, mode=MemoryMode.SAFE))
            service = GenerationService(runtime, storage)
            request = self._make_request(batch_size=4)
            with self.assertRaisesRegex(ValueError, "Batch size 4 exceeds memory cap"):
                service.generate(request)

    def test_duration_exceeding_cap_raises_value_error(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            runtime = RuntimeManager(storage)
            runtime.save_memory_settings(MemorySettings(max_versions=4, max_duration_sec=180, mode=MemoryMode.SAFE))
            service = GenerationService(runtime, storage)
            request = self._make_request(duration=300)
            with self.assertRaisesRegex(ValueError, "Duration 300s exceeds memory cap"):
                service.generate(request)

    def test_within_caps_does_not_raise(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            runtime = RuntimeManager(storage)
            runtime.save_memory_settings(MemorySettings(max_versions=2, max_duration_sec=300, mode=MemoryMode.BALANCED))
            service = GenerationService(runtime, storage)
            client = SimpleNamespace(
                generate=lambda req: "job",
                wait=lambda tid, **kw: SimpleNamespace(
                    title="Test", audio_paths=["/test.wav"],
                    prompt="", lyrics="", metadata={}, seed="",
                ),
                health=lambda: {"ok": True},
                initialize=lambda m, lm: None,
                download_audio=lambda s, t: t,
            )
            service.client = client
            request = self._make_request(batch_size=2, duration=180)
            with (
                patch.object(service.storage, "save_generation"),
                patch.object(service.storage, "record_job"),
                patch("shutil.copy2"),
            ):
                service.generate(request)


class TrainingCapEnforcementTest(unittest.TestCase):
    def test_start_clamps_values(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            runtime = RuntimeManager(storage)
            runtime.save_memory_settings(MemorySettings(
                training_checkpointing=True,
                training_max_batch=1,
                training_max_rank=32,
                training_max_alpha=64,
            ))
            calls = []
            client = SimpleNamespace(
                start_training=lambda kind, payload: calls.append(payload),
                unload_adapter=lambda: None,
            )
            generation = SimpleNamespace(client_ready=lambda: client, runtime=runtime)
            service = TrainingService(generation, storage)
            request = SimpleNamespace(
                kind="lora",
                tensor_dir="/tmp/tensors",
                output_dir="/tmp/output",
                batch_size=4,
                rank=128,
                alpha=256,
                gradient_checkpointing=False,
                learning_rate=0.0001,
                epochs=10,
                dropout=0.1,
                gradient_accumulation=4,
                save_every=5,
                training_shift=3,
                seed=42,
                lokr_factor=-1,
                payload=lambda: {"batch_size": request.batch_size, "rank": request.rank, "alpha": request.alpha},
            )
            service.start(request)
            self.assertTrue(request.gradient_checkpointing)
            self.assertEqual(request.batch_size, 1)
            self.assertEqual(request.rank, 32)
            self.assertEqual(request.alpha, 64)


if __name__ == "__main__":
    unittest.main()
