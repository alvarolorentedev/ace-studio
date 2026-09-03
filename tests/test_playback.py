import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from flet_audio import AudioState

from ace_studio.app import AceStudio


class PlaybackTest(unittest.TestCase):
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
            audio = Path(directory) / "song.wav"
            audio.write_bytes(b"RIFFaudio")
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

    def test_play_pause_control_toggles_audio_and_icon(self):
        class Audio:
            def __init__(self):
                self.calls = []

            async def pause(self):
                self.calls.append("pause")

            async def resume(self):
                self.calls.append("resume")

        studio = AceStudio.__new__(AceStudio)
        studio.audio = Audio()
        studio.audio_state = AudioState.PLAYING
        studio.page = SimpleNamespace(update=lambda: None)
        studio.now_meta = SimpleNamespace(value="")
        studio.play_pause_button = SimpleNamespace(icon=None, tooltip=None)

        asyncio.run(studio._toggle_audio())
        studio._audio_state_changed(SimpleNamespace(state=AudioState.PAUSED))
        asyncio.run(studio._toggle_audio())

        self.assertEqual(studio.audio.calls, ["pause", "resume"])
        self.assertEqual(studio.play_pause_button.tooltip, "Play")

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
        self.assertEqual(played, [("/tmp/one.wav", "One")])

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


if __name__ == "__main__":
    unittest.main()
