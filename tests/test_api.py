import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from threading import Event
from unittest.mock import patch

from ace_studio.api import AceApiError, AceClient, GenerationCancelled


class ApiTest(unittest.TestCase):
    def test_named_api_wrappers_keep_endpoint_paths_out_of_views(self):
        calls = []

        class Client(AceClient):
            def call(self, method, path, payload=None):
                calls.append((method, path, payload))
                if path.endswith("/scan"):
                    return {"samples": []}
                return {"task_id": "task", "status": "idle"}

        client = Client(1, "token")
        client.scan_dataset("/audio", "set")
        client.dataset_samples()
        client.update_dataset_sample(2, {"caption": "x"})
        client.save_dataset("/set.json", "set")
        client.auto_label_dataset("/set.json")
        client.auto_label_status("one")
        client.preprocess_dataset("/tensors")
        client.preprocess_status("two")
        client.start_training("lora", {"tensor_dir": "/tensors"})
        client.start_training("lokr", {"tensor_dir": "/tensors"})
        client.training_status()
        client.stop_training()
        client.export_adapter("/run", "/adapter")
        client.load_adapter("/adapter", "voice")
        client.unload_adapter()
        client.toggle_adapter(True)
        client.set_adapter_scale(0.5, "voice")
        client.adapter_status()
        self.assertEqual(calls[0][1], "/v1/dataset/scan")
        self.assertIn(("GET", "/v1/lora/status", None), calls)

    def test_simple_api_methods_delegate_to_transport(self):
        class Client(AceClient):
            def _request(self, method, path, data=None, content_type="application/json"):
                return method, path, data, content_type

        client = Client(1, "token")
        self.assertEqual(client.health()[:2], ("GET", "/health"))
        self.assertEqual(client.models()[:2], ("GET", "/v1/models"))
        self.assertEqual(client.stats()[:2], ("GET", "/v1/stats"))
        self.assertEqual(client.initialize("dit", "lm")[:2], ("POST", "/v1/init"))
        self.assertEqual(client.random_sample()[:2], ("POST", "/create_random_sample"))
        self.assertEqual(client.waveform("song.wav")[:2], ("GET", "/studio/v1/waveform?path=song.wav&bins=600"))

    def test_multipart_includes_files_and_skips_missing_optional_files(self):
        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "clip.wav"
            audio.write_bytes(b"audio")
            body, content_type = AceClient._multipart({"prompt": "x"}, {"src_audio": str(audio), "reference": None})
            self.assertIn(b'filename="clip.wav"', body)
            self.assertIn(b"audio", body)
            self.assertTrue(content_type.startswith("multipart/form-data; boundary="))

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
                return [
                    {
                        "status": 0,
                        "progress_text": "Denoising",
                        "result": '[{"progress": 0.42, "stage": "generating"}]',
                    }
                ]

        status = Client(1, "token").task_status("job")
        self.assertEqual(status["progress"], 0.42)
        self.assertEqual(status["stage"], "generating")

    def test_generation_wait_stops_when_cancelled(self):
        cancel_event = Event()
        cancel_event.set()
        with self.assertRaises(GenerationCancelled):
            AceClient(1, "token").wait("job", cancel_event=cancel_event)

    def test_generation_success_without_audio_is_an_error(self):
        class Client(AceClient):
            def task_status(self, _task_id):
                return {"status": 1, "result": [{"file": ""}], "error": None}

        with self.assertRaisesRegex(AceApiError, "did not produce an audio file"):
            Client(1, "token").wait("job")

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
            with self.assertRaises(AceApiError):
                AceClient(8000, "secret").download_audio("https://example.com/song.wav", target)


if __name__ == "__main__":
    unittest.main()
