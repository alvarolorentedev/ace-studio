import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ace_studio.models import HardwareReport, RuntimeProfile
from ace_studio.runtime import SUPPORTED_COMMIT, RuntimeManager, recommended_models
from ace_studio.storage import Storage


class RuntimeTest(unittest.TestCase):
    def test_run_streams_output_and_reports_failure(self):
        class Process:
            stdout = ["one\n", "\n"]
            returncode = 0

            def wait(self):
                return self.returncode

        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeManager(Storage(Path(directory)))
            messages = []
            with patch("ace_studio.runtime.subprocess.Popen", return_value=Process()):
                runtime._run(["command"], Path(directory), lambda message, _value: messages.append(message))
            self.assertEqual(messages, ["one"])
            Process.returncode = 2
            with patch("ace_studio.runtime.subprocess.Popen", return_value=Process()), self.assertRaisesRegex(RuntimeError, "2"):
                runtime._run(["command"], Path(directory), lambda *_args: None)

    def test_install_reuses_a_compatible_staged_version(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeManager(Storage(Path(directory)))
            destination = runtime.storage.runtime_dir / "versions" / SUPPORTED_COMMIT
            destination.mkdir(parents=True)
            with patch.object(runtime, "_probe", return_value=True):
                manifest = runtime.install_latest()
            self.assertEqual(manifest.commit, SUPPORTED_COMMIT)

    def test_stop_kills_process_after_timeout_and_ignores_stopped_process(self):
        process = SimpleNamespace(
            poll=lambda: None,
            terminate=lambda: None,
            wait=lambda **_kwargs: (_ for _ in ()).throw(subprocess.TimeoutExpired("runtime", 1)),
            kill=lambda: None,
        )
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeManager(Storage(Path(directory)))
            runtime.process = process
            runtime.stop()
            self.assertIsNone(runtime.process)
            runtime.stop()

    def test_runtime_manifest_and_pin_are_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeManager(Storage(Path(directory)))
            self.assertEqual(runtime.latest_commit(), SUPPORTED_COMMIT)
            runtime.current_file.write_text("not json")
            self.assertIsNone(runtime.current_manifest())
            source = runtime.storage.runtime_dir / "versions" / SUPPORTED_COMMIT
            source.mkdir(parents=True)
            manifest = runtime._activate(SUPPORTED_COMMIT, source)
            self.assertEqual(runtime.current_manifest().commit, manifest.commit)
            self.assertIn("installed_at", runtime.current_file.read_text())

    def test_model_download_validates_runtime_and_builds_command(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeManager(Storage(Path(directory)))
            with self.assertRaises(ValueError):
                runtime.download_model("unknown")
            with self.assertRaises(RuntimeError):
                runtime.download_model("acestep-v15-base")
            source = runtime.storage.runtime_dir / "versions" / SUPPORTED_COMMIT
            source.mkdir(parents=True)
            runtime._activate(SUPPORTED_COMMIT, source)
            with patch.object(runtime, "_run") as run:
                runtime.download_model("acestep-v15-base")
            self.assertIn("acestep-v15-base", run.call_args.args[0])

    def test_specialized_installs_choose_profile_requirements(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source"
            source.mkdir()
            runtime = RuntimeManager(Storage(Path(directory) / "data"))
            with patch.object(runtime, "_uv", return_value="uv"), patch.object(runtime, "_run") as run:
                runtime._specialized_install(source, RuntimeProfile.LINUX_ROCM, lambda *_args: None)
                commands = [call.args[0] for call in run.call_args_list]
                self.assertTrue(any("rocm6.3" in argument for command in commands for argument in command))
                self.assertTrue(any("requirements-rocm-linux.txt" in command for command in commands))
                run.reset_mock()
                runtime._specialized_install(source, RuntimeProfile.LINUX_XPU, lambda *_args: None)
                self.assertTrue(any("xpu" in command for call in run.call_args_list for command in call.args[0]))

    def test_probe_handles_missing_success_and_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            runtime = RuntimeManager(Storage(source / "data"))
            self.assertFalse(runtime._probe(source))
            executable = Path(runtime._python(source))
            executable.parent.mkdir(parents=True)
            executable.touch()
            with patch("ace_studio.runtime.subprocess.run", return_value=SimpleNamespace(returncode=0)):
                self.assertTrue(runtime._probe(source))
            with patch("ace_studio.runtime.subprocess.run", side_effect=subprocess.TimeoutExpired("probe", 1)):
                self.assertFalse(runtime._probe(source))

    def test_start_and_stop_manage_process_state(self):
        class Process:
            def __init__(self, *_args, **_kwargs):
                self.returncode = None
                self.terminated = False

            def poll(self):
                return None if not self.terminated else 0

            def terminate(self):
                self.terminated = True

            def wait(self, timeout=None):
                return 0

        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeManager(Storage(Path(directory)))
            source = runtime.storage.runtime_dir / "versions" / SUPPORTED_COMMIT
            source.mkdir(parents=True)
            runtime._activate(SUPPORTED_COMMIT, source)
            bridge = source / ".ace_studio_bridge.py"
            bridge.touch()
            with patch("ace_studio.runtime.subprocess.Popen", Process):
                port, token = runtime.start()
                self.assertGreater(port, 0)
                self.assertTrue(token)
                self.assertEqual(runtime.start(), (port, token))
                runtime.stop()
            self.assertIsNone(runtime.process)

    def test_small_memory_uses_small_model(self):
        report = HardwareReport("Linux", "x86_64", "cpu", 6, "CPU", RuntimeProfile.LINUX_CPU, True)
        self.assertEqual(recommended_models(report), ("acestep-v15-turbo", None))

    def test_16gb_mac_uses_small_language_model(self):
        report = HardwareReport("Darwin", "arm64", "arm", 16, "Apple Silicon", RuntimeProfile.MACOS_MLX, True)
        self.assertEqual(recommended_models(report), ("acestep-v15-turbo", "acestep-5Hz-lm-0.6B"))

    def test_install_downloads_and_selects_recommended_models(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeManager(Storage(Path(directory)))
            runtime.hardware = HardwareReport("Darwin", "arm64", "arm", 16, "Apple Silicon", RuntimeProfile.MACOS_MLX, True)
            with patch.object(runtime, "install_latest"), patch.object(runtime, "download_model") as download:
                runtime.install_recommended()
            self.assertEqual(
                [call.args[0] for call in download.call_args_list],
                ["acestep-v15-turbo", "acestep-5Hz-lm-0.6B"],
            )
            self.assertEqual(json.loads(runtime.model_settings_file.read_text())["lm"], "acestep-5Hz-lm-0.6B")

    def test_model_selection_is_validated_and_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeManager(Storage(Path(directory)))
            for model in ("acestep-v15-sft", "acestep-5Hz-lm-4B"):
                model_dir = runtime.storage.models_dir / model
                model_dir.mkdir()
                (model_dir / "config.json").write_text("{}")
            runtime.select_models("acestep-v15-sft", "acestep-5Hz-lm-4B")
            self.assertEqual(runtime.selected_models(), ("acestep-v15-sft", "acestep-5Hz-lm-4B"))
            with self.assertRaises(ValueError):
                runtime.select_models("not-a-model", None)

    def test_missing_recommendation_falls_back_to_an_installed_model(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeManager(Storage(Path(directory)))
            for model in ("acestep-v15-turbo", "acestep-5Hz-lm-1.7B"):
                model_dir = runtime.storage.models_dir / model
                model_dir.mkdir()
                (model_dir / "config.json").write_text("{}")
            with patch("ace_studio.runtime.recommended_models", return_value=("acestep-v15-turbo", "acestep-5Hz-lm-0.6B")):
                self.assertEqual(runtime.selected_models(), ("acestep-v15-turbo", "acestep-5Hz-lm-1.7B"))

    def test_bundled_runtime_helper_is_resolvable(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertTrue(Path(RuntimeManager(Storage(Path(directory)))._uv()).is_file())

    def test_compiled_packaged_runtime_bridge_is_staged_as_pyc(self):
        with tempfile.TemporaryDirectory() as directory:
            assets = Path(directory) / "assets"
            bridge = assets / "bin" / "ace_studio_bridge.pyc"
            bridge.parent.mkdir(parents=True)
            bridge.write_bytes(b"compiled bridge")
            with patch.dict("os.environ", {"FLET_ASSETS_DIR": str(assets)}):
                runtime = RuntimeManager(Storage(Path(directory) / "data"))
                source = Path(directory) / "runtime"
                source.mkdir()
                staged = runtime._stage_bridge(source)
                self.assertEqual(staged.name, ".ace_studio_bridge.pyc")
                self.assertEqual(staged.read_bytes(), bridge.read_bytes())

    def test_stage_bridge_refreshes_an_existing_staged_bridge(self):
        with tempfile.TemporaryDirectory() as directory:
            runtime = RuntimeManager(Storage(Path(directory) / "data"))
            source = Path(directory) / "runtime"
            source.mkdir()
            bridge = Path(directory) / "ace_studio_bridge.py"
            bridge.write_text("new bridge")
            (source / ".ace_studio_bridge.py").write_text("stale bridge")
            with patch.object(runtime, "_bridge", return_value=bridge):
                self.assertEqual(runtime._stage_bridge(source).read_text(), "new bridge")


if __name__ == "__main__":
    unittest.main()
