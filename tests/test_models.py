import json
import tempfile
import unittest
from pathlib import Path

from ace_studio.models import TRACK_NAMES, EditRequest, TrainingRequest


class ModelTest(unittest.TestCase):
    def test_all_edit_modes_validate_and_serialize(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.wav"
            source.write_bytes(b"RIFFaudio")
            requests = [
                EditRequest(str(source), "cover", prompt="jazz", cover_strength=0.5),
                EditRequest(str(source), "repaint", prompt="solo", repaint_end=10),
                EditRequest(str(source), "lego", track_name="guitar"),
                EditRequest(str(source), "extract", track_name="vocals"),
                EditRequest(str(source), "complete", track_classes=["bass", "drums"]),
            ]
            for request in requests:
                request.validate(duration=30)
            fields = requests[-1].generation_request("acestep-v15-base").fields()
            self.assertEqual(json.loads(fields["param_obj"])["track_classes"], ["bass", "drums"])

    def test_edit_validation_rejects_invalid_boundaries(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.wav"
            source.touch()
            with self.assertRaisesRegex(ValueError, "after"):
                EditRequest(str(source), "repaint", prompt="x", repaint_start=10, repaint_end=5).validate()

    def test_training_defaults_match_adapter_kind(self):
        with tempfile.TemporaryDirectory() as directory:
            lora = TrainingRequest("lora", directory, f"{directory}/lora").payload()
            lokr = TrainingRequest("lokr", directory, f"{directory}/lokr").payload()
            self.assertEqual((lora["lora_rank"], lora["train_epochs"]), (64, 10))
            self.assertEqual((lokr["lokr_linear_dim"], lokr["train_epochs"]), (64, 500))
            self.assertEqual(len(TRACK_NAMES), 12)

    def test_training_request_rejects_invalid_boundary_values(self):
        with tempfile.TemporaryDirectory() as directory:
            invalid = [
                TrainingRequest("other", directory, directory),
                TrainingRequest("lora", f"{directory}/missing", directory),
                TrainingRequest("lora", directory, directory, learning_rate=0),
                TrainingRequest("lora", directory, directory, epochs=0),
                TrainingRequest("lora", directory, directory, rank=0),
                TrainingRequest("lora", directory, directory, dropout=2),
            ]
            for request in invalid:
                with self.subTest(request=request), self.assertRaises(ValueError):
                    request.payload()


if __name__ == "__main__":
    unittest.main()
