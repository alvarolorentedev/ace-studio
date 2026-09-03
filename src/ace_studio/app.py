from __future__ import annotations

import asyncio
import re
from pathlib import Path
from threading import Event

import flet as ft
from flet_audio import Audio, AudioState

from .api import AceClient
from .models import GenerationRequest
from .runtime import RuntimeManager
from .services import GenerationService, TrainingService
from .storage import Storage
from .theme import (
    ARTWORK_GRADIENT,
    BORDER,
    CARD_RADIUS,
    DANGER,
    GREEN,
    INK,
    MUTED,
    PANEL,
    PLAYER,
    PRIMARY_BUTTON_STYLE,
    SELECTED,
    SHELL,
    SUCCESS,
    TEXT,
    app_theme,
)


class AceStudio:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.storage = Storage()
        self.runtime = RuntimeManager(self.storage)
        self.generation = GenerationService(self.runtime, self.storage)
        self.training = TrainingService(self.generation, self.storage)
        self.client: AceClient | None = None
        self.views: dict[int, ft.Control] = {}
        self.content = ft.Container(expand=True)
        self.status = ft.Text("Ready", color=MUTED, size=12)
        self.now_title = ft.Text("Nothing playing", weight=ft.FontWeight.W_600)
        self.now_meta = ft.Text("Choose a track from your library", size=11, color=MUTED)
        self.elapsed = ft.Text("0:00", size=11, color=MUTED)
        self.total = ft.Text("—:—", size=11, color=MUTED)
        self.progress = ft.Slider(min=0, max=1, value=0, expand=True)
        self.audio: Audio | None = None
        self.audio_state = AudioState.STOPPED
        self.audio_loaded = asyncio.Event()
        self.current_audio_path: str | None = None
        self.current_audio_title = ""
        self.repeat_mode = "off"
        self.seeking = False
        self.sidebar_collapsed = False
        self.current_view = 0
        self.save_picker = ft.FilePicker()
        self.page.services.append(self.save_picker)
        self._configure()

    def _configure(self) -> None:
        self.page.title = "ACE Studio"
        self.page.bgcolor = INK
        self.page.padding = 0
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.theme = app_theme()
        self.page.dark_theme = app_theme()
        # A setup card needs more vertical room than Flet's compact default.
        self.page.window.width = 1120
        self.page.window.height = 820
        self.page.window.min_width = 900
        self.page.window.min_height = 700
        self.show_setup() if not self.runtime.current_manifest() else self.show_shell(0)

    def card(self, *controls: ft.Control, padding: int = 22, expand: bool = False) -> ft.Container:
        return ft.Container(
            content=ft.Column(list(controls), spacing=14),
            bgcolor=PANEL,
            border=ft.Border.all(1, BORDER),
            border_radius=CARD_RADIUS,
            padding=padding,
            expand=expand,
        )

    def notice(self, message: str, error: bool = False) -> None:
        self.page.show_dialog(ft.SnackBar(ft.Text(message), bgcolor=DANGER if error else SUCCESS))

    def show_setup(self) -> None:
        from .views.setup import show

        show(self)

    def show_shell(self, index: int) -> None:
        self.current_view = index
        destinations = [
            ("Create", ft.Icons.GRAPHIC_EQ),
            ("Library", ft.Icons.LIBRARY_MUSIC),
            ("Edit", ft.Icons.EDIT_NOTE),
            ("Train", ft.Icons.SCIENCE),
        ]

        nav = []
        for position, (label, icon) in enumerate(destinations):
            selected = position == index
            nav.append(
                ft.Container(
                    content=ft.Row(
                        [
                            ft.Icon(icon, size=21, color=GREEN if selected else MUTED),
                            ft.Text(
                                label,
                                visible=not self.sidebar_collapsed,
                                color=TEXT if selected else MUTED,
                                weight=ft.FontWeight.W_600 if selected else ft.FontWeight.W_400,
                            ),
                        ],
                        spacing=16,
                    ),
                    bgcolor=SELECTED if selected else None,
                    border=ft.Border(left=ft.BorderSide(3, GREEN if selected else "transparent")),
                    border_radius=8,
                    padding=ft.Padding.symmetric(horizontal=18, vertical=14),
                    on_click=lambda _event, destination=position: self.show_shell(destination),
                )
            )

        def bottom_item(label, icon, click):
            return ft.Container(
                content=ft.Row(
                    [ft.Icon(icon, size=19, color=MUTED), ft.Text(label, visible=not self.sidebar_collapsed, color=MUTED)],
                    spacing=16,
                ),
                border_radius=8,
                padding=ft.Padding.symmetric(horizontal=18, vertical=12),
                tooltip=label,
                on_click=click,
            )

        rail = ft.Container(
            width=72 if self.sidebar_collapsed else 205,
            bgcolor=SHELL,
            border=ft.Border(right=ft.BorderSide(1, BORDER)),
            padding=ft.Padding.only(left=12, right=12, top=26),
            content=ft.Column(
                [
                    ft.Container(
                        content=ft.Image(src="icon.png", width=36, height=36), tooltip="Expand sidebar", on_click=self._toggle_sidebar
                    )
                    if self.sidebar_collapsed
                    else ft.Row(
                        [
                            ft.Image(src="icon.png", width=36, height=36),
                            ft.Text("ACE\nSTUDIO", size=15, weight=ft.FontWeight.BOLD, expand=True),
                            ft.IconButton(ft.Icons.CHEVRON_LEFT, tooltip="Collapse sidebar", on_click=self._toggle_sidebar),
                        ]
                    ),
                    ft.Container(height=18),
                    *nav,
                    ft.Container(expand=True),
                    bottom_item("Settings", ft.Icons.SETTINGS, lambda _e: self.page.show_dialog(self.settings_dialog())),
                    ft.Container(height=16),
                ],
                spacing=5,
            ),
        )

        repeat_icons = {"off": ft.Icons.REPEAT, "all": ft.Icons.REPEAT_ON, "one": ft.Icons.REPEAT_ON}
        repeat_labels = {"off": "Looping off", "one": "Repeating this song", "all": "Repeating all generated songs"}
        repeat_one_badge = ft.Badge(
            label="1",
            alignment=ft.Alignment(0.35, 0.35),
            bgcolor=GREEN,
            text_color=INK,
            small_size=10,
            large_size=14,
            text_style=ft.TextStyle(size=8),
        )

        def cycle_repeat(_event: ft.Event) -> None:
            modes = ("off", "all", "one")
            self.repeat_mode = modes[(modes.index(self.repeat_mode) + 1) % len(modes)]
            repeat.icon = repeat_icons[self.repeat_mode]
            repeat.badge = repeat_one_badge if self.repeat_mode == "one" else None
            repeat.tooltip = repeat_labels[self.repeat_mode]
            self.notice(repeat_labels[self.repeat_mode])
            self.page.update()

        def preview_seek(event: ft.Event) -> None:
            self.seeking = True
            self.elapsed.value = self._format_time(float(event.control.value))
            self.page.update()

        async def seek(event: ft.Event) -> None:
            if self.audio:
                await self.audio.seek(ft.Duration(seconds=float(event.control.value)))
            self.seeking = False

        self.progress.on_change = preview_seek
        self.progress.on_change_end = seek
        repeat = ft.IconButton(
            repeat_icons[self.repeat_mode],
            badge=repeat_one_badge if self.repeat_mode == "one" else None,
            tooltip=repeat_labels[self.repeat_mode],
            on_click=cycle_repeat,
        )
        self.play_pause_button = ft.IconButton(
            ft.Icons.PAUSE if self.audio_state == AudioState.PLAYING else ft.Icons.PLAY_ARROW,
            icon_color=INK,
            bgcolor=GREEN,
            icon_size=24,
            tooltip="Pause" if self.audio_state == AudioState.PLAYING else "Play",
            on_click=self._toggle_audio,
        )

        player = ft.Container(
            height=88,
            bgcolor=PLAYER,
            border=ft.Border(top=ft.BorderSide(1, BORDER)),
            padding=ft.Padding.symmetric(horizontal=18),
            content=ft.Row(
                [
                    ft.Container(
                        width=56,
                        height=56,
                        border_radius=8,
                        gradient=ft.LinearGradient(colors=ARTWORK_GRADIENT),
                        content=ft.Icon(ft.Icons.MUSIC_NOTE, color="white", size=24),
                        alignment=ft.Alignment.CENTER,
                    ),
                    ft.Column([self.now_title, self.now_meta], spacing=4, alignment=ft.MainAxisAlignment.CENTER, width=245),
                    ft.Column(
                        [
                            ft.Row(
                                [
                                    ft.IconButton(
                                        ft.Icons.SKIP_PREVIOUS,
                                        tooltip="Previous",
                                        on_click=lambda _e: self.page.run_task(self._skip_track, -1),
                                    ),
                                    self.play_pause_button,
                                    ft.IconButton(
                                        ft.Icons.SKIP_NEXT, tooltip="Next", on_click=lambda _e: self.page.run_task(self._skip_track, 1)
                                    ),
                                    repeat,
                                ],
                                alignment=ft.MainAxisAlignment.CENTER,
                                spacing=8,
                            ),
                            ft.Row([self.elapsed, self.progress, self.total], spacing=12),
                        ],
                        spacing=2,
                        alignment=ft.MainAxisAlignment.CENTER,
                        expand=True,
                    ),
                    ft.IconButton(
                        ft.Icons.DOWNLOAD,
                        tooltip="Save a copy",
                        icon_color=GREEN,
                        on_click=lambda _event: self.page.run_task(self._download_current_track),
                    ),
                    self.status,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        self.page.clean()
        self.page.add(
            ft.Column(
                [ft.Container(content=ft.Row([rail, self.content], spacing=0, expand=True), expand=True), player],
                spacing=0,
                expand=True,
            )
        )
        self.render(index)

    def render(self, index: int) -> None:
        builders = [self.create_view, self.library_view, self.edit_view, self.train_view]
        if index not in self.views:
            self.views[index] = builders[index]()
        self.content.content = self.views[index]
        self.content.padding = 0 if index == 0 else 28
        self.content.bgcolor = INK
        self.page.update()

    def _toggle_sidebar(self, _event: ft.Event) -> None:
        self.sidebar_collapsed = not self.sidebar_collapsed
        self.show_shell(self.current_view)

    def heading(self, title: str, subtitle: str) -> ft.Column:
        return ft.Column([ft.Text(title, size=32, weight=ft.FontWeight.BOLD), ft.Text(subtitle, color=MUTED)], spacing=4)

    def create_view(self) -> ft.Control:
        from .views.create import build

        return build(self)

    def _clear_fields(self, prompt: ft.TextField, lyrics: ft.TextField) -> None:
        prompt.value = ""
        lyrics.value = ""
        self.page.update()

    @staticmethod
    def _format_eta(seconds: float) -> str:
        remaining = max(0, round(seconds))
        if remaining < 60:
            return f"{remaining} sec"
        minutes, seconds = divmod(remaining, 60)
        return f"{minutes} min {seconds:02d} sec"

    @staticmethod
    def _format_time(seconds: float) -> str:
        minutes, seconds = divmod(max(0, round(seconds)), 60)
        return f"{minutes}:{seconds:02d}"

    @staticmethod
    def _prompt_title(prompt: str) -> str:
        words = re.findall(r"[\w'-]+", prompt, flags=re.UNICODE)[:7]
        return " ".join(words).title() or "Untitled generation"

    def _track_menu(self, item: dict, view_index: int) -> ft.PopupMenuButton:
        return ft.PopupMenuButton(
            icon=ft.Icons.MORE_HORIZ,
            tooltip="Track actions",
            items=[
                ft.PopupMenuItem(
                    content="Play", icon=ft.Icons.PLAY_ARROW, on_click=lambda _e: self.play_track(item["audio_path"], item["title"])
                ),
                ft.PopupMenuItem(
                    content="Download",
                    icon=ft.Icons.DOWNLOAD,
                    on_click=lambda _e: self.page.run_task(self._download_track, item["audio_path"], item["title"]),
                ),
                ft.PopupMenuItem(content="Rename", icon=ft.Icons.EDIT, on_click=lambda _e: self._rename_track(item, view_index)),
                ft.PopupMenuItem(
                    content="Favorite",
                    icon=ft.Icons.FAVORITE_BORDER,
                    on_click=lambda _e: (self.storage.toggle_favorite(item["id"]), self.views.pop(0, None), self.show_shell(0)),
                ),
            ],
        )

    def _rename_track(self, item: dict, view_index: int) -> None:
        name = ft.TextField(label="Song name", value=item["title"], autofocus=True, max_length=100)

        def cancel(_event: ft.Event) -> None:
            self.page.pop_dialog()

        def save(_event: ft.Event) -> None:
            title = name.value.strip()
            if not title:
                return
            self.storage.update_title(item["id"], title)
            if self.current_audio_title == item["title"]:
                self.current_audio_title = title
                self.now_title.value = title
            self.views.pop(0, None)
            self.views.pop(1, None)
            self.page.pop_dialog()
            self.show_shell(view_index)
            self.notice(f"Renamed to {title}")

        def validate(event: ft.Event) -> None:
            rename.disabled = not event.control.value.strip()
            self.page.update()

        rename = ft.Button("Rename", icon=ft.Icons.EDIT, style=PRIMARY_BUTTON_STYLE, on_click=save)
        name.on_change = validate
        name.on_submit = save
        self.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text("Rename song"),
                content=name,
                actions=[ft.TextButton("Cancel", on_click=cancel), rename],
            )
        )

    async def _download_current_track(self) -> None:
        if not self.current_audio_path:
            self.notice("Play a track before downloading it.", True)
            return
        await self._download_track(self.current_audio_path, self.current_audio_title)

    async def _download_track(self, path: str, title: str) -> None:
        source = Path(path)
        if not source.is_file():
            self.notice("The saved audio file is missing.", True)
            return
        filename = " ".join(re.sub(r"[^\w .-]", "", title, flags=re.UNICODE).split()) or "ACE Studio track"
        await self.save_picker.save_file(file_name=f"{filename}{source.suffix}", src_bytes=source.read_bytes())

    def _ensure_client(self) -> AceClient:
        client = self.generation.client_ready()
        self.client = client
        return client

    def _generate(self, request: GenerationRequest, progress_callback=None, cancel_event: Event | None = None):
        return self.generation.generate(request, progress_callback, cancel_event)

    def play_track(self, path: str, title: str) -> None:
        self.page.run_task(self._play_track, path, title)

    async def _resume_audio(self) -> None:
        from . import playback

        return await playback.resume(self)

    async def _toggle_audio(self, _event: ft.Event | None = None) -> None:
        from . import playback

        return await playback.toggle(self, _event)

    def _audio_state_changed(self, event) -> None:
        from . import playback

        return playback.state_changed(self, event)

    def _audio_loaded(self, _event) -> None:
        from . import playback

        return playback.loaded(self, _event)

    def _audio_duration_changed(self, event) -> None:
        from . import playback

        return playback.duration_changed(self, event)

    def _audio_position_changed(self, event) -> None:
        from . import playback

        return playback.position_changed(self, event)

    async def _skip_track(self, offset: int) -> None:
        from . import playback

        return await playback.skip(self, offset)

    async def _play_track(self, path: str, title: str) -> None:
        from . import playback

        return await playback.play(self, path, title, Audio)

    def library_view(self) -> ft.Control:
        from .views.library import build

        return build(self)

    def edit_view(self) -> ft.Control:
        from .views.edit import build

        return build(self)

    def train_view(self) -> ft.Control:
        from .views.train import build

        return build(self)

    def settings_dialog(self) -> ft.AlertDialog:
        from .views.settings import build

        return build(self)


async def main(page: ft.Page) -> None:
    AceStudio(page)


def run() -> None:
    ft.run(main)
