import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import flet as ft
import flet.canvas as cv

from ace_studio.app import AceStudio
from ace_studio.models import DatasetSample, HardwareReport, RuntimeProfile
from ace_studio.storage import Storage
from ace_studio.views import create, edit, library, settings, setup, train


class Page:
    def __init__(self):
        self.services = []
        self.window = SimpleNamespace()
        self.controls = []

    def update(self):
        pass

    def clean(self):
        self.controls.clear()

    def add(self, *controls):
        self.controls.extend(controls)

    def show_dialog(self, dialog):
        self.dialog = dialog

    def pop_dialog(self):
        self.dialog = None

    def run_task(self, function, *args):
        self.task = (function, args)


class Runtime:
    hardware = HardwareReport("Linux", "x86_64", "cpu", 8, "CPU", RuntimeProfile.LINUX_CPU, True)

    def current_manifest(self):
        return None

    def selected_models(self):
        return "acestep-v15-turbo", None

    def model_installed(self, _name):
        return False

    def stop(self):
        pass

    def install_recommended(self, progress):
        progress("Installed", 1)

    def install_latest(self, *_args):
        return None

    def download_model(self, _name, progress):
        progress("Downloaded", 1)

    def select_models(self, *_models):
        pass


def controls(root):
    found = []
    seen = set()

    def visit(value):
        if isinstance(value, ft.Control) and id(value) not in seen:
            seen.add(id(value))
            found.append(value)
            for child in vars(value).values():
                visit(child)
        elif isinstance(value, (list, tuple)):
            for child in value:
                visit(child)
        elif isinstance(value, dict):
            for child in value.values():
                visit(child)

    visit(root)
    return found


def find(root, **attributes):
    return next(control for control in controls(root) if all(getattr(control, key, None) == value for key, value in attributes.items()))


class Client:
    def improve_inputs(self, *_args, **_kwargs):
        return {"caption": "Improved music", "lyrics": "Improved lyrics"}

    def create_sample(self, *_args):
        return {"caption": "Developed", "lyrics": "Lyrics"}

    def random_sample(self):
        return {"caption": "Random", "lyrics": "Random lyrics"}


class Training:
    last_request = None
    active_args = None
    deactivated = False
    storage = None

    def scan(self, audio_dir, *_args):
        return [DatasetSample(0, "song.wav", str(Path(audio_dir) / "song.wav"), duration=12)]

    def update_sample(self, sample):
        sample.labeled = True
        return sample

    def save(self, name, *_args):
        return Path("/tmp") / name / "dataset.json"

    def auto_label(self, _path):
        return "label"

    def preprocess(self, name):
        return "preprocess", Path("/tmp") / name / "tensors"

    def task_status(self, kind, task_id):
        return {"status": "completed", "current": 1, "total": 1, "progress": f"{kind}:{task_id}"}

    def start(self, request):
        self.last_request = request
        return {"message": "started"}

    def status(self):
        return {
            "status": "Complete",
            "is_training": False,
            "current_epoch": 1,
            "current_loss": 0.2,
            "logs": ["finished"],
            "config": {"epochs": 1},
        }

    def stop(self):
        return {"message": "stopped"}

    def export(self, name, _kind, _output):
        return Path("/tmp") / name

    def activate(self, *args):
        self.active_args = args
        if self.storage:
            self.storage.update_adapter(args[0], active=True, scale=args[2])

    def deactivate(self):
        self.deactivated = True
        if self.storage:
            for adapter in self.storage.adapters():
                self.storage.update_adapter(adapter.id, active=False)


class ViewSmokeTest(unittest.TestCase):
    def studio(self, directory):
        studio = AceStudio.__new__(AceStudio)
        studio.page = Page()
        studio.storage = Storage(Path(directory))
        studio.runtime = Runtime()
        studio.views = {}
        studio.heading = AceStudio.heading.__get__(studio)
        studio.card = AceStudio.card.__get__(studio)
        studio.notice = lambda *_args: None
        studio.play_track = lambda *_args: None
        studio._clear_fields = lambda *_args: None
        studio._ensure_client = lambda: Client()
        studio.generation = SimpleNamespace(
            edit=lambda *_args: SimpleNamespace(audio_paths=["/tmp/result.wav"], title="Edited"), reset_client=lambda: None
        )
        studio.training = Training()
        studio.training.storage = studio.storage
        studio.status = ft.Text("Ready")
        return studio

    def test_each_view_builds_without_starting_runtime(self):
        with tempfile.TemporaryDirectory() as directory:
            studio = self.studio(directory)
            self.assertIsInstance(create.build(studio), ft.Control)
            self.assertIsInstance(library.build(studio), ft.Control)
            self.assertIsInstance(edit.build(studio), ft.Control)
            self.assertIsInstance(train.build(studio), ft.Control)
            self.assertIsInstance(settings.build(studio), ft.AlertDialog)
            setup.show(studio)
            self.assertTrue(studio.page.controls)

    def test_application_constructs_setup_and_shell(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict("os.environ", {"ACE_STUDIO_DATA_DIR": directory}):
            page = Page()
            studio = AceStudio(page)
            self.assertTrue(page.controls)
            studio.show_shell(0)
            repeat = find(page.controls[0], tooltip="Looping off")
            repeat.on_click(None)
            studio.progress.value = 10
            studio.progress.on_change(SimpleNamespace(control=studio.progress))
            asyncio.run(studio.progress.on_change_end(SimpleNamespace(control=studio.progress)))
            studio.render(1)
            studio._toggle_sidebar(None)
            self.assertTrue(studio.sidebar_collapsed)

    def test_track_menu_and_rename_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            studio = self.studio(directory)
            studio.current_audio_title = "Song"
            studio.now_title = ft.Text("Song")
            studio.views = {0: ft.Text(), 1: ft.Text()}
            studio.show_shell = lambda *_args: None
            item = {"id": "one", "title": "Song", "audio_path": str(Path(directory) / "song.wav")}
            studio.storage.save_generation("one", "Song", "text2music", item["audio_path"], "", "", {})
            menu = studio._track_menu(item, 1)
            find(menu, content="Favorite").on_click(None)
            studio._rename_track(item, 1)
            name = find(studio.page.dialog, label="Song name")
            name.value = "Renamed"
            name.on_change(SimpleNamespace(control=name))
            find(studio.page.dialog, content="Rename").on_click(None)
            self.assertEqual(studio.storage.generation("one")["title"], "Renamed")

    def test_create_view_validation_and_helpers(self):
        with tempfile.TemporaryDirectory() as directory:
            studio = self.studio(directory)
            studio._generate = lambda *_args: SimpleNamespace(audio_paths=["/tmp/one.wav"], title="One")
            adapter_path = Path(directory) / "adapter"
            adapter_path.mkdir()
            studio.storage.add_adapter("adapter", "Adapter", str(adapter_path), "lora", {})
            root = create.build(studio)
            adapter = find(root, label="LoRA adapter")
            adapter.value = "adapter"
            asyncio.run(adapter.on_select(SimpleNamespace(control=adapter)))
            self.assertEqual(studio.training.active_args[0], "adapter")
            adapter.value = "none"
            asyncio.run(adapter.on_select(SimpleNamespace(control=adapter)))
            self.assertTrue(studio.training.deactivated)
            duration = next(item for item in controls(root) if isinstance(item, ft.Slider) and item.max == 600)
            duration.value = 90
            duration.on_change(SimpleNamespace(control=duration))
            bpm = next(item for item in controls(root) if isinstance(item, ft.Slider) and item.max == 200)
            bpm.value = 100
            bpm.on_change(SimpleNamespace(control=bpm))
            asyncio.run(find(root, content="Improve music").on_click(None))
            prompt = next(item for item in controls(root) if isinstance(item, ft.TextField) and item.max_length == 1000)
            prompt.value = "idea"
            asyncio.run(find(root, content="Improve music").on_click(None))
            asyncio.run(find(root, content="Develop idea").on_click(None))
            asyncio.run(find(root, content="Randomize").on_click(None))
            prompt.value = "generate this"
            asyncio.run(find(root, content="Generate").on_click(None))

    def test_edit_and_train_primary_success_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            studio = self.studio(directory)
            source_path = Path(directory) / "source.wav"
            source_path.touch()
            edit_root = edit.build(studio)
            edit_mode = next(control for control in controls(edit_root) if isinstance(control, ft.RadioGroup))
            edit_mode.value = "cover"
            edit_mode.on_change(SimpleNamespace(control=edit_mode))
            self.assertTrue(next(control for control in controls(edit_root) if isinstance(control, ft.Slider)).visible)
            find(edit_root, label="Source WAV").value = str(source_path)
            find(edit_root, label="Edit description").value = "new bridge"
            asyncio.run(find(edit_root, content="Run edit").on_click(None))

            train_root = train.build(studio)
            find(train_root, label="Audio dataset folder").value = directory
            asyncio.run(find(train_root, content="Scan & save").on_click(None))
            asyncio.run(find(train_root, tooltip="Edit track metadata").on_click(None))
            asyncio.run(find(studio.page.dialog, content="Save").on_click(None))
            asyncio.run(find(train_root, content="Auto-label unlabeled").on_click(None))
            asyncio.run(find(train_root, content="Preprocess tensors").on_click(None))
            adapter_kind = find(train_root, label="Adapter")
            adapter_kind.value = "lokr"
            adapter_kind.on_select(SimpleNamespace(control=adapter_kind))
            self.assertTrue(find(train_root, label="LoKr factor (-1 = auto)").visible)
            asyncio.run(find(train_root, content="Start training").on_click(None))
            self.assertEqual(studio.training.last_request.kind, "lokr")
            self.assertEqual(find(train_root, value="0.2000").value, "0.2000")
            self.assertTrue(any(isinstance(control, cv.Canvas) for control in controls(train_root)))
            asyncio.run(find(train_root, content="Export adapter").on_click(None))
            asyncio.run(find(train_root, content="Stop").on_click(None))

    def test_setup_library_and_settings_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            studio = self.studio(directory)
            studio.show_shell = lambda *_args: None
            setup.show(studio)
            setup_root = studio.page.controls[0]
            asyncio.run(find(setup_root, content="Install ACE-Step").on_click(None))

            audio = Path(directory) / "song.wav"
            audio.touch()
            studio.storage.save_generation("song", "Song", "text2music", str(audio), "literal % prompt", "", {})
            library_root = library.build(studio)
            find(library_root, hint_text="Search your tracks").value = "%"
            find(library_root, hint_text="Search your tracks").on_change(None)
            favorite = find(library_root, tooltip="Favorite")
            favorite.on_click(None)
            delete = find(library_root, tooltip="Delete track")
            delete.on_click(None)
            find(studio.page.dialog, content="Delete").on_click(None)

            adapter_path = Path(directory) / "adapter"
            adapter_path.mkdir()
            studio.storage.add_adapter("adapter", "Adapter", str(adapter_path), "lora", {})
            settings_root = settings.build(studio)
            find(settings_root, content="Save selection").on_click(None)
            asyncio.run(find(settings_root, content="Reinstall supported runtime").on_click(None))
            find(settings_root, content="Download").on_click(None)
            task, args = studio.page.task
            asyncio.run(task(*args))
            asyncio.run(find(settings_root, content="Load").on_click(None))
            settings_root = studio.page.dialog
            scale = next(item for item in controls(settings_root) if isinstance(item, ft.Dropdown) and item.width == 100)
            scale.value = "0.5"
            asyncio.run(scale.on_select(SimpleNamespace(control=scale)))
            find(settings_root, tooltip="Rename adapter").on_click(None)
            find(studio.page.dialog, label="Adapter name").value = "Renamed"
            find(studio.page.dialog, content="Save").on_click(None)
            self.assertEqual(studio.storage.adapters()[0].name, "Renamed")
            find(studio.page.dialog, tooltip="Remove adapter from ACE Studio").on_click(None)


if __name__ == "__main__":
    unittest.main()
