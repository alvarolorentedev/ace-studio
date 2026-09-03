import tempfile
import unittest
from pathlib import Path

from ace_studio.models import GenerationRequest
from ace_studio.storage import Storage


class StorageTest(unittest.TestCase):
    def test_generation_fields_and_library_round_trip(self):
        request = GenerationRequest("ambient jazz", bpm=92, instrumental=True, seed=7, advanced={"audio_format": "unexpected"})
        self.assertEqual(request.fields()["bpm"], "92")
        self.assertEqual(request.fields()["audio_format"], "wav")
        self.assertEqual(request.fields()["use_random_seed"], "false")
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            storage.save_generation("one", "Night Bus", "text2music", "/tmp/a.wav", request.prompt, "", {"bpm": 92})
            self.assertEqual(storage.generations()[0]["metadata"]["bpm"], 92)
            storage.update_title("one", "Midnight Platform")
            self.assertEqual(storage.generations()[0]["title"], "Midnight Platform")
            self.assertTrue(storage.toggle_favorite("one"))

    def test_deleting_a_generation_removes_its_managed_audio_file(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            audio = storage.audio_dir / "song.wav"
            audio.write_bytes(b"audio")
            storage.save_generation("one", "Night Bus", "text2music", str(audio), "", "", {})
            self.assertTrue(storage.delete_generation("one"))
            self.assertFalse(audio.exists())
            self.assertEqual(storage.generations(), [])


if __name__ == "__main__":
    unittest.main()
