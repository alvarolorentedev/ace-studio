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

    def test_cleanup_only_removes_managed_nonfavorites_and_ignores_symlinks(self):
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as external_directory:
            storage = Storage(Path(directory))
            favorite = storage.audio_dir / "favorite.wav"
            removable = storage.audio_dir / "remove.wav"
            external = Path(external_directory) / "external.wav"
            favorite.write_bytes(b"favorite")
            removable.write_bytes(b"remove")
            external.write_bytes(b"external")
            storage.save_generation("favorite", "Favorite", "text2music", str(favorite), "", "", {})
            storage.toggle_favorite("favorite")
            storage.save_generation("remove", "Remove", "text2music", str(removable), "", "", {})
            storage.save_generation("external", "External", "text2music", str(external), "", "", {})
            linked = Path(external_directory) / "linked.wav"
            linked.write_bytes(b"linked")
            (storage.runtime_dir / "tmp").mkdir()
            (storage.runtime_dir / "tmp" / "external-link").symlink_to(linked)

            self.assertEqual(storage.clear_temporary_files(), 0)
            count, reclaimed = storage.delete_nonfavorite_generations()

            self.assertEqual((count, reclaimed), (1, len(b"remove")))
            self.assertTrue(favorite.exists())
            self.assertTrue(external.exists())
            self.assertTrue(linked.exists())
            self.assertIsNotNone(storage.generation("favorite"))
            self.assertIsNotNone(storage.generation("external"))
            self.assertIsNone(storage.generation("remove"))

    def test_training_cleanup_is_confined_to_runs(self):
        with tempfile.TemporaryDirectory() as directory:
            storage = Storage(Path(directory))
            run = storage.training_dir / "runs" / "voice"
            dataset = storage.training_dir / "datasets" / "voice"
            run.mkdir(parents=True)
            dataset.mkdir(parents=True)
            (run / "checkpoint.bin").write_bytes(b"checkpoint")
            (dataset / "dataset.json").write_text("{}")

            self.assertEqual(storage.delete_training_run(run), len(b"checkpoint"))
            self.assertTrue(dataset.exists())
            with self.assertRaises(ValueError):
                storage.delete_training_run(dataset)


if __name__ == "__main__":
    unittest.main()
