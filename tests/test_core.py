import asyncio
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from flet_audio import AudioState

from ace_studio.api import AceApiError, AceClient
from ace_studio.app import AceStudio
from ace_studio.models import GenerationRequest, HardwareReport, RuntimeProfile
from ace_studio.runtime import RuntimeManager, recommended_models
from ace_studio.storage import Storage


class CoreTest(unittest.TestCase):
    def test_saved_audio_is_loaded_by_file_path_before_playing(self):
        class Value:
            value = ""
            max = 1

        class Page:
            services = []

            def update(self):
                pass

        class Audio:
            def __init__(self, src, on_loaded, on_state_change, **_kwargs):
                self.src = src
                self.on_state_change = on_state_change
                on_loaded(None)

            async def play(self):
                self.on_state_change(SimpleNamespace(state=AudioState.PLAYING))

        async def check(path):
            studio = AceStudio.__new__(AceStudio)
            studio.page = Page()
            studio.audio = None
            studio.audio_state = AudioState.STOPPED
            studio.audio_loaded = asyncio.Event()
            studio.now_title = Value()
            studio.now_meta = Value()
            studio.elapsed = Value()
            studio.total = Value()
            studio.progress = Value()
            studio.current_audio_path = None
            studio.current_audio_title = ""
            studio.notice = lambda *_args: None
            with patch("ace_studio.app.Audio", Audio):
                await studio._play_track(str(path), "Saved song")
            self.assertEqual(studio.audio.src, str(path.resolve()))
            self.assertEqual(studio.audio_state, AudioState.PLAYING)

        with tempfile.TemporaryDirectory() as directory:
            audio = Path(directory) / "song.mp3"
            audio.write_bytes(b"ID3")
            asyncio.run(check(audio))

    def test_completed_audio_replays_instead_of_resuming_released_source(self):
        class Audio:
            def __init__(self):
                self.calls = []

            async def play(self):
                self.calls.append("play")

            async def resume(self):
                self.calls.append("resume")

        studio = AceStudio.__new__(AceStudio)
        studio.audio = Audio()
        studio.audio_state = AudioState.COMPLETED
        asyncio.run(studio._resume_audio())
        self.assertEqual(studio.audio.calls, ["play"])

    def test_repeat_modes_dispatch_on_completion(self):
        class Page:
            def __init__(self):
                self.tasks = []

            def update(self):
                pass

            def run_task(self, function, *args):
                self.tasks.append((function, args))

        studio = AceStudio.__new__(AceStudio)
        studio.page = Page()
        studio.audio_state = AudioState.PLAYING
        studio.now_meta = SimpleNamespace(value="")
        studio.repeat_mode = "one"
        studio._audio_state_changed(SimpleNamespace(state=AudioState.COMPLETED))
        self.assertEqual(studio.page.tasks, [(studio._resume_audio, ())])
        studio.page.tasks.clear()
        studio.repeat_mode = "all"
        studio._audio_state_changed(SimpleNamespace(state=AudioState.COMPLETED))
        self.assertEqual(studio.page.tasks, [(studio._skip_track, (1,))])

    def test_playlist_navigation_wraps_over_all_generated_songs(self):
        tracks = [
            {"id": "one", "title": "One", "audio_path": "/tmp/one.wav"},
            {"id": "two", "title": "Two", "audio_path": "/tmp/two.wav"},
        ]
        studio = AceStudio.__new__(AceStudio)
        studio.storage = SimpleNamespace(generations=lambda: tracks)
        studio.current_audio_path = str(Path("/tmp/two.wav").resolve())
        played = []

        async def play(*args):
            played.append(args)

        studio._play_track = play
        asyncio.run(studio._skip_track(1))
        self.assertEqual(played, [("/tmp/one.wav", "One", "one")])

    def test_prompt_becomes_a_short_generation_title(self):
        self.assertEqual(
            AceStudio._prompt_title("a nostalgic synthwave track with driving drums and warm pads"),
            "A Nostalgic Synthwave Track With Driving Drums",
        )

    def test_audio_events_update_elapsed_and_total_time(self):
        class Page:
            def update(self):
                pass

        studio = AceStudio.__new__(AceStudio)
        studio.page = Page()
        studio.seeking = False
        studio.progress = SimpleNamespace(value=0, max=1)
        studio.elapsed = SimpleNamespace(value="0:00")
        studio.total = SimpleNamespace(value="—:—")
        studio._audio_duration_changed(SimpleNamespace(duration=SimpleNamespace(in_seconds=185)))
        studio._audio_position_changed(SimpleNamespace(position=62_000))
        self.assertEqual((studio.elapsed.value, studio.total.value, studio.progress.max), ("1:02", "3:05", 185))

    def test_download_saves_the_current_audio_with_its_title(self):
        class Picker:
            async def save_file(self, **kwargs):
                self.saved = kwargs

        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "track.wav"
            source.write_bytes(b"RIFFaudio")
            studio = AceStudio.__new__(AceStudio)
            studio.save_picker = Picker()
            studio.notice = lambda *_args: None
            asyncio.run(studio._download_track(str(source), "Night / Drive"))
            self.assertEqual(studio.save_picker.saved, {"file_name": "Night Drive.wav", "src_bytes": b"RIFFaudio"})

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

    def test_small_memory_uses_small_model(self):
        report = HardwareReport("Linux", "x86_64", "cpu", 6, "CPU", RuntimeProfile.LINUX_CPU, True)
        self.assertEqual(recommended_models(report), ("acestep-v15-turbo", None))

    def test_16gb_mac_uses_small_language_model(self):
        report = HardwareReport("Darwin", "arm64", "arm", 16, "Apple Silicon", RuntimeProfile.MACOS_MLX, True)
        self.assertEqual(recommended_models(report), ("acestep-v15-turbo", "acestep-5Hz-lm-0.6B"))

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
