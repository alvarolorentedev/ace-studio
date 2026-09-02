import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from ace_studio.api import AceApiError, AceClient
from ace_studio.models import GenerationRequest, HardwareReport, RuntimeProfile
from ace_studio.runtime import RuntimeManager, recommended_models
from ace_studio.storage import Storage


class CoreTest(unittest.TestCase):
    def test_generation_fields_and_library_round_trip(self):
        request = GenerationRequest("ambient jazz", bpm=92, instrumental=True, seed=7)
        self.assertEqual(request.fields()["bpm"], "92")
        self.assertEqual(request.fields()["use_random_seed"], "false")
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            storage.save_generation("one", "Night Bus", "text2music", "/tmp/a.wav", request.prompt, "", {"bpm": 92})
            self.assertEqual(storage.generations()[0]["metadata"]["bpm"], 92)
            storage.update_audio_path("one", "/tmp/saved.wav")
            self.assertEqual(storage.generations()[0]["audio_path"], "/tmp/saved.wav")
            self.assertTrue(storage.toggle_favorite("one"))

    def test_small_memory_uses_small_model(self):
        report = HardwareReport("Linux", "x86_64", "cpu", 6, "CPU", RuntimeProfile.LINUX_CPU, True)
        self.assertEqual(recommended_models(report), ("acestep-v15-turbo", None))

    def test_16gb_mac_uses_small_language_model(self):
        report = HardwareReport("Darwin", "arm64", "arm", 16, "Apple Silicon", RuntimeProfile.MACOS_MLX, True)
        self.assertEqual(recommended_models(report), ("acestep-v15-turbo", "acestep-5Hz-lm-0.6B"))

    def test_bundled_runtime_helper_is_resolvable(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertTrue(Path(RuntimeManager(Storage(Path(directory)))._uv()).is_file())

    def test_ai_improvement_uses_upstream_format_endpoint(self):
        calls = []

        class Client(AceClient):
            def call(self, method, path, payload=None):
                calls.append((method, path, payload))
                return {"caption": "Improved"}

        result = Client(1, "token").improve_inputs("draft", "lyrics", bpm=120)
        self.assertEqual(result["caption"], "Improved")
        self.assertEqual(calls[0][1], "/format_input")
        self.assertEqual(calls[0][2]["param_obj"]["bpm"], 120)

    def test_generation_progress_is_parsed_from_upstream_status(self):
        class Client(AceClient):
            def _request(self, *_args, **_kwargs):
                return [{
                    "status": 0,
                    "progress_text": "Denoising",
                    "result": '[{"progress": 0.42, "stage": "generating"}]',
                }]

        status = Client(1, "token").task_status("job")
        self.assertEqual(status["progress"], 0.42)
        self.assertEqual(status["stage"], "generating")

    def test_generated_audio_is_downloaded_to_the_persistent_library(self):
        class Response(BytesIO):
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                self.close()

        with tempfile.TemporaryDirectory() as directory, patch("urllib.request.urlopen", return_value=Response(b"RIFFaudio")):
            target = Path(directory) / "song.wav"
            AceClient(8000, "secret").download_audio("/v1/audio?path=song.wav", target)
            self.assertEqual(target.read_bytes(), b"RIFFaudio")
            self.assertEqual(AceClient.audio_suffix("/v1/audio?path=%2Ftmp%2Fsong.mp3"), ".mp3")
            with self.assertRaises(AceApiError):
                AceClient(8000, "secret").download_audio("https://example.com/song.wav", target)


if __name__ == "__main__":
    unittest.main()
