import tempfile
import unittest
from pathlib import Path

from ace_studio.models import GenerationRequest, HardwareReport, RuntimeProfile
from ace_studio.runtime import recommended_models
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
            self.assertTrue(storage.toggle_favorite("one"))

    def test_small_memory_uses_small_model(self):
        report = HardwareReport("Linux", "x86_64", "cpu", 6, "CPU", RuntimeProfile.LINUX_CPU, True)
        self.assertEqual(recommended_models(report), ("acestep-v15-turbo", None))

    def test_16gb_mac_uses_small_language_model(self):
        report = HardwareReport("Darwin", "arm64", "arm", 16, "Apple Silicon", RuntimeProfile.MACOS_MLX, True)
        self.assertEqual(recommended_models(report), ("acestep-v15-turbo", "acestep-5Hz-lm-0.6B"))


if __name__ == "__main__":
    unittest.main()
