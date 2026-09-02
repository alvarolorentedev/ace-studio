from __future__ import annotations

import asyncio
import re
import shutil
import time
from pathlib import Path
from threading import Event

import flet as ft
from flet_audio import Audio, AudioState

from .api import AceClient, GenerationCancelled
from .models import GenerationRequest
from .runtime import DIT_MODELS, LM_MODELS, RuntimeManager, recommended_models
from .storage import Storage


GREEN = "#1ED760"
INK = "#0A0D0C"
PANEL = "#121716"
RAISED = "#19201E"
BORDER = "#303735"
MUTED = "#A9B0AD"


class AceStudio:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.storage = Storage()
        self.runtime = RuntimeManager(self.storage)
        self.client: AceClient | None = None
        self.views: dict[int, ft.Control] = {}
        self.content = ft.Container(expand=True)
        self.status = ft.Text("Ready", color=MUTED, size=12)
        self.now_title = ft.Text("Nothing playing", weight=ft.FontWeight.W_600)
        self.now_meta = ft.Text("Choose a track from your library", size=11, color=MUTED)
        self.elapsed = ft.Text("0:00", size=11, color=MUTED)
        self.total = ft.Text("—:—", size=11, color=MUTED)
        self.progress = ft.Slider(min=0, max=1, value=0, active_color=GREEN, inactive_color="#46504C", expand=True)
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
        self.page.theme = ft.Theme(color_scheme_seed=GREEN, font_family="Inter")
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
            border=ft.Border.all(1, "#242925"),
            border_radius=16,
            padding=padding,
            expand=expand,
        )

    def notice(self, message: str, error: bool = False) -> None:
        self.page.show_dialog(ft.SnackBar(ft.Text(message), bgcolor="#8C2431" if error else "#225A35"))

    def show_setup(self) -> None:
        report = self.runtime.hardware
        model, lm = recommended_models(report)
        progress = ft.ProgressBar(value=0, color=GREEN, bgcolor="#29302B")
        log = ft.Text("Ready to install", color=MUTED, selectable=True)
        button = ft.Button("Install ACE-Step", icon=ft.Icons.DOWNLOAD, bgcolor=GREEN, color="#07140B")

        async def install(_event: ft.Event) -> None:
            button.disabled = True
            progress.value = None
            log.value = "Preparing ACE-Step…"
            self.page.update()
            loop = asyncio.get_running_loop()

            def update(message: str, value: float | None) -> None:
                def paint() -> None:
                    log.value = message[-180:]
                    progress.value = value
                    self.page.update()

                loop.call_soon_threadsafe(paint)

            try:
                await asyncio.to_thread(self.runtime.install_recommended, update)
                self.views.clear()
                self.show_shell(0)
            except Exception as exc:
                button.disabled = False
                progress.value = 0
                log.value = str(exc)
                self.page.update()

        button.on_click = install
        self.page.clean()
        self.page.add(
            ft.ListView(
                expand=True,
                padding=40,
                controls=[
                    ft.Row(
                        [
                            ft.Container(
                                width=720,
                                content=ft.Column(
                                    [
                                        ft.Row([ft.Image(src="icon.png", width=44, height=44), ft.Text("ACE Studio", size=30, weight=ft.FontWeight.BOLD)]),
                                        ft.Text("Your music studio", size=42, weight=ft.FontWeight.BOLD),
                                        ft.Text("Install ACE-Step, choose a hardware profile, and start creating.", color=MUTED, size=16),
                                        self.card(
                                            ft.Text("Hardware profile", size=20, weight=ft.FontWeight.W_600),
                                            ft.ListTile(leading=ft.Icon(ft.Icons.MEMORY, color=GREEN), title=ft.Text(report.summary), subtitle=ft.Text(report.profile.value)),
                                            ft.ListTile(leading=ft.Icon(ft.Icons.MODEL_TRAINING, color=GREEN), title=ft.Text(model), subtitle=ft.Text(f"Language model: {lm or 'disabled for this profile'}")),
                                            ft.Text("The first launch downloads ACE-Step, Python packages, and the recommended model. This can take several minutes and multiple gigabytes.", color=MUTED),
                                            progress,
                                            log,
                                            button,
                                        ),
                                    ],
                                    spacing=24,
                                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                                ),
                            )
                        ],
                        alignment=ft.MainAxisAlignment.CENTER,
                    )
                ],
            )
        )

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
                    content=ft.Row([
                        ft.Icon(icon, size=21, color=GREEN if selected else MUTED),
                        ft.Text(label, visible=not self.sidebar_collapsed, color="#F5F7F5" if selected else MUTED, weight=ft.FontWeight.W_600 if selected else ft.FontWeight.W_400),
                    ], spacing=16),
                    bgcolor="#232A28" if selected else None,
                    border=ft.Border(left=ft.BorderSide(3, GREEN if selected else "transparent")),
                    border_radius=8,
                    padding=ft.Padding.symmetric(horizontal=18, vertical=14),
                    on_click=lambda _event, destination=position: self.show_shell(destination),
                )
            )
        bottom_item = lambda label, icon, click: ft.Container(
            content=ft.Row([ft.Icon(icon, size=19, color=MUTED), ft.Text(label, visible=not self.sidebar_collapsed, color=MUTED)], spacing=16),
            border_radius=8,
            padding=ft.Padding.symmetric(horizontal=18, vertical=12),
            tooltip=label,
            on_click=click,
        )
        rail = ft.Container(
            width=72 if self.sidebar_collapsed else 205,
            bgcolor="#0E1211",
            border=ft.Border(right=ft.BorderSide(1, BORDER)),
            padding=ft.Padding.only(left=12, right=12, top=26),
            content=ft.Column(
                [
                    ft.Container(content=ft.Image(src="icon.png", width=36, height=36), tooltip="Expand sidebar", on_click=self._toggle_sidebar)
                    if self.sidebar_collapsed else
                    ft.Row([
                        ft.Image(src="icon.png", width=36, height=36),
                        ft.Text("ACE\nSTUDIO", size=15, weight=ft.FontWeight.BOLD, expand=True),
                        ft.IconButton(ft.Icons.CHEVRON_LEFT, tooltip="Collapse sidebar", on_click=self._toggle_sidebar),
                    ]),
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
        repeat_one_badge = ft.Badge(label="1", alignment=ft.Alignment(0.35, 0.35), bgcolor=GREEN, text_color=INK, small_size=10, large_size=14, text_style=ft.TextStyle(size=8))

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
            bgcolor="#101413",
            border=ft.Border(top=ft.BorderSide(1, BORDER)),
            padding=ft.Padding.symmetric(horizontal=18),
            content=ft.Row(
                [
                    ft.Container(width=56, height=56, border_radius=8, gradient=ft.LinearGradient(colors=["#523BC6", "#E05480", "#F2A75F"]), content=ft.Icon(ft.Icons.MUSIC_NOTE, color="white", size=24), alignment=ft.Alignment.CENTER),
                    ft.Column([self.now_title, self.now_meta], spacing=4, alignment=ft.MainAxisAlignment.CENTER, width=245),
                    ft.Column(
                        [
                            ft.Row([
                                ft.IconButton(ft.Icons.SKIP_PREVIOUS, tooltip="Previous", on_click=lambda _e: self.page.run_task(self._skip_track, -1)),
                                self.play_pause_button,
                                ft.IconButton(ft.Icons.SKIP_NEXT, tooltip="Next", on_click=lambda _e: self.page.run_task(self._skip_track, 1)),
                                repeat,
                            ], alignment=ft.MainAxisAlignment.CENTER, spacing=8),
                            ft.Row([self.elapsed, self.progress, self.total], spacing=12),
                        ],
                        spacing=2,
                        alignment=ft.MainAxisAlignment.CENTER,
                        expand=True,
                    ),
                    ft.IconButton(ft.Icons.DOWNLOAD, tooltip="Save a copy", icon_color=GREEN, on_click=lambda _event: self.page.run_task(self._download_current_track)),
                    self.status,
                ],
                vertical_alignment=ft.CrossAxisAlignment.CENTER,
            ),
        )
        self.page.clean()
        self.page.add(ft.Column([ft.Row([rail, self.content], spacing=0, expand=True), player], spacing=0, expand=True))
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
        field_style = {
            "filled": True,
            "fill_color": "#111514",
            "border_color": BORDER,
            "focused_border_color": GREEN,
            "border_radius": 8,
        }
        prompt = ft.TextField(
            value="",
            hint_text="A nostalgic synthwave track with driving drums, warm pads, and a hopeful mood.",
            multiline=True,
            min_lines=2,
            max_length=1000,
            **field_style,
        )
        lyrics = ft.TextField(
            value="",
            hint_text="[Verse]\nCity lights fade into the night…\n\n[Chorus]\nWe rise above the afterglow…",
            multiline=True,
            min_lines=6,
            max_length=4000,
            **field_style,
        )
        duration_value = ft.Text("2:00", weight=ft.FontWeight.W_600)
        duration = ft.Slider(min=30, max=600, value=120, divisions=57, active_color=GREEN, inactive_color="#37413D")
        bpm_value = ft.Text("120", weight=ft.FontWeight.W_600)
        bpm = ft.Slider(min=40, max=200, value=120, divisions=160, active_color=GREEN, inactive_color="#37413D")
        key = ft.Dropdown(
            value="A minor",
            options=[ft.DropdownOption(key=x, text=x) for x in ["Auto", "C major", "A minor", "D major", "E minor", "F major", "G minor"]],
            dense=True,
            **field_style,
        )
        signature = ft.Dropdown(
            value="4/4",
            options=[ft.DropdownOption(key=x, text=x) for x in ["Auto", "4/4", "3/4", "6/8"]],
            dense=True,
            **field_style,
        )
        instrumental = ft.Switch(value=False, active_color=GREEN)
        thinking = ft.Switch(label="Use language model reasoning", value=True, active_color=GREEN)
        batch = ft.Dropdown(label="Versions", value="1", options=[ft.DropdownOption(key=str(x), text=str(x)) for x in range(1, 5)], width=130, **field_style)
        seed = ft.TextField(label="Seed", hint_text="Random", width=150, keyboard_type=ft.KeyboardType.NUMBER, **field_style)
        guidance = ft.TextField(label="Guidance", value="15", width=130, keyboard_type=ft.KeyboardType.NUMBER, **field_style)
        generate = ft.Button("Generate", icon=ft.Icons.GRAPHIC_EQ, bgcolor=GREEN, color="#07140B")
        improve_music = ft.Button("Improve music", icon=ft.Icons.AUTO_FIX_HIGH, color=GREEN)
        improve_lyrics = ft.Button("Improve lyrics", icon=ft.Icons.AUTO_FIX_HIGH, color=GREEN)
        develop = ft.Button("Develop idea", icon=ft.Icons.PSYCHOLOGY, color=GREEN)
        randomize = ft.Button("Randomize", icon=ft.Icons.SHUFFLE, color=MUTED)
        generation_progress = ft.ProgressBar(value=0, color=GREEN, bgcolor="#34403B")
        generation_stage = ft.Text("Preparing ACE-Step", size=16, weight=ft.FontWeight.W_600)
        generation_percent = ft.Text("0%", color=GREEN, weight=ft.FontWeight.BOLD)
        generation_detail = ft.Text("Loading models…", color=MUTED, size=12)
        generation_eta = ft.Text("Estimating finish time…", color=MUTED, size=12)
        generation_actions = ft.Row(visible=False, wrap=True)
        generation_feedback = ft.Container(
            visible=False,
            bgcolor="#14251B",
            border=ft.Border.all(1, "#2D6A43"),
            border_radius=10,
            padding=16,
            content=ft.Column([
                ft.Row([ft.Icon(ft.Icons.GRAPHIC_EQ, color=GREEN), generation_stage, ft.Container(expand=True), generation_percent]),
                generation_progress,
                ft.Row([generation_detail, ft.Container(expand=True), generation_eta]),
                generation_actions,
            ], spacing=9),
        )

        def format_duration(seconds: float) -> str:
            total = int(seconds)
            return f"{total // 60}:{total % 60:02d}"

        def sync_duration(event: ft.Event) -> None:
            duration_value.value = format_duration(event.control.value)
            self.page.update()

        def sync_bpm(event: ft.Event) -> None:
            bpm_value.value = str(int(event.control.value))
            self.page.update()

        duration.on_change = sync_duration
        bpm.on_change = sync_bpm

        async def improve(kind: str, button: ft.Button) -> None:
            if kind == "music" and not prompt.value.strip():
                self.notice("Describe the music you want to improve first.", True)
                return
            if kind == "lyrics" and not lyrics.value.strip():
                self.notice("Add a lyric idea or draft first.", True)
                return
            original = button.content
            button.disabled = True
            button.content = "ACE is writing…"
            self.status.value = "5Hz LM is improving your idea"
            self.page.update()
            try:
                client = await asyncio.to_thread(self._ensure_client)
                result = await asyncio.to_thread(
                    client.improve_inputs,
                    prompt.value.strip(),
                    lyrics.value.strip(),
                    duration=duration.value,
                    bpm=int(bpm.value),
                    key_scale="" if key.value == "Auto" else key.value,
                    time_signature="" if signature.value == "Auto" else signature.value,
                )
                if kind == "music":
                    prompt.value = result.get("caption") or prompt.value
                else:
                    lyrics.value = result.get("lyrics") or lyrics.value
                self.notice(f"{kind.title()} improved with ACE-Step's language model.")
            except Exception as exc:
                self.notice(str(exc), True)
            finally:
                button.disabled = False
                button.content = original
                self.status.value = "Ready"
                self.page.update()

        async def develop_idea(_event: ft.Event) -> None:
            if not prompt.value.strip():
                self.notice("Give ACE a short idea to develop.", True)
                return
            original = develop.content
            develop.disabled = True
            develop.content = "Developing…"
            self.page.update()
            try:
                client = await asyncio.to_thread(self._ensure_client)
                result = await asyncio.to_thread(client.create_sample, prompt.value.strip(), instrumental.value)
                prompt.value = result.get("caption") or prompt.value
                lyrics.value = result.get("lyrics") or lyrics.value
                self.notice("ACE developed your idea into a complete song brief.")
            except Exception as exc:
                self.notice(str(exc), True)
            finally:
                develop.disabled = False
                develop.content = original
                self.page.update()

        async def random_idea(_event: ft.Event) -> None:
            try:
                client = await asyncio.to_thread(self._ensure_client)
                result = await asyncio.to_thread(client.random_sample)
                prompt.value = result.get("caption") or result.get("prompt") or ""
                lyrics.value = result.get("lyrics") or ""
                self.page.update()
            except Exception as exc:
                self.notice(str(exc), True)

        async def improve_music_click(_event: ft.Event) -> None:
            await improve("music", improve_music)

        async def improve_lyrics_click(_event: ft.Event) -> None:
            await improve("lyrics", improve_lyrics)

        improve_music.on_click = improve_music_click
        improve_lyrics.on_click = improve_lyrics_click
        develop.on_click = develop_idea
        randomize.on_click = random_idea

        async def submit(_event: ft.Event) -> None:
            if not prompt.value.strip() and not lyrics.value.strip():
                self.notice("Add a description or lyrics first.", True)
                return
            try:
                request = GenerationRequest(
                    prompt=prompt.value.strip(), lyrics=lyrics.value.strip(), duration=float(duration.value),
                    bpm=int(bpm.value), key_scale="" if key.value == "Auto" else key.value,
                    time_signature="" if signature.value == "Auto" else signature.value, instrumental=instrumental.value,
                    thinking=thinking.value, batch_size=int(batch.value), seed=int(seed.value) if seed.value.strip() else None,
                    advanced={"guidance_scale": guidance.value},
                )
                request.model = self.runtime.selected_models()[0]
            except ValueError:
                self.notice("BPM, seed, and guidance must be valid numbers.", True)
                return
            generate.disabled = True
            generate.content = "Generating…"
            self.status.value = "ACE-Step is creating"
            generation_feedback.visible = True
            generation_feedback.bgcolor = "#14251B"
            generation_feedback.border = ft.Border.all(1, "#2D6A43")
            generation_progress.value = None
            generation_stage.value = "Starting ACE-Step"
            generation_percent.value = "—"
            generation_detail.value = "Loading the model and submitting your song…"
            generation_eta.value = "First load can take several minutes"
            cancel_event = Event()

            async def stop_generation(_event: ft.Event) -> None:
                cancel_event.set()
                stop.disabled = True
                stop.content = "Stopping…"
                generation_stage.value = "Stopping generation"
                generation_detail.value = "Stopping the local ACE-Step process…"
                self.page.update()
                await asyncio.to_thread(self.runtime.stop)
                self.client = None

            stop = ft.Button("Stop", icon=ft.Icons.STOP, color="#FFFFFF", bgcolor="#8C2431", on_click=stop_generation)
            generation_actions.controls = [stop]
            generation_actions.visible = True
            self.page.update()
            loop = asyncio.get_running_loop()

            def update_progress(update: dict) -> None:
                def paint() -> None:
                    value = max(0.0, min(1.0, float(update.get("progress", 0))))
                    stage = str(update.get("stage") or "Generating").replace("_", " ").strip()
                    generation_progress.value = value
                    generation_percent.value = f"{round(value * 100)}%"
                    generation_stage.value = stage[:1].upper() + stage[1:]
                    generation_detail.value = (update.get("progress_text") or "ACE-Step is synthesizing your track")[-140:]
                    eta = update.get("eta_seconds")
                    generation_eta.value = f"About {self._format_eta(eta)} remaining" if eta is not None else "Estimating finish time…"
                    self.page.update()

                loop.call_soon_threadsafe(paint)
            try:
                result = await asyncio.to_thread(self._generate, request, update_progress, cancel_event)
                generation_progress.value = 1
                generation_percent.value = "100%"
                generation_stage.value = "Your tracks are ready"
                generation_detail.value = f"Created {len(result.audio_paths)} version(s) and saved them to your library."
                generation_eta.value = "Finished"
                generation_actions.controls = [
                    ft.Button(
                        f"Play version {number}",
                        icon=ft.Icons.PLAY_ARROW,
                        bgcolor=GREEN,
                        color="#07140B",
                        on_click=lambda _event, p=path, n=number: self.play_track(p, f"{result.title} · Version {n}"),
                    )
                    for number, path in enumerate(result.audio_paths, 1)
                ]
                generation_actions.visible = True
                self.views.pop(1, None)
                self.notice(f"Created {len(result.audio_paths)} track(s)")
            except Exception as exc:
                if cancel_event.is_set():
                    generation_progress.value = 0
                    generation_percent.value = "Stopped"
                    generation_stage.value = "Generation cancelled"
                    generation_detail.value = "No track was saved."
                    generation_eta.value = "Ready when you are"
                    generation_actions.controls.clear()
                    generation_actions.visible = False
                    self.notice("Generation cancelled")
                    return
                generation_progress.value = 0
                generation_percent.value = "Failed"
                generation_stage.value = "Generation stopped"
                generation_detail.value = str(exc)
                generation_eta.value = "Try again"
                generation_feedback.bgcolor = "#2A1518"
                generation_feedback.border = ft.Border.all(1, "#74313A")
                self.notice(str(exc), True)
            finally:
                generate.disabled = False
                generate.content = "Generate"
                self.status.value = "Ready"
                self.page.update()

        generate.on_click = submit
        advanced = ft.ExpansionTile(
            title=ft.Text("Advanced controls", size=14),
            controls=[ft.Container(ft.Column([thinking, ft.Row([batch, seed, guidance], wrap=True)], spacing=12), padding=ft.Padding.only(bottom=12))],
            bgcolor=RAISED,
            collapsed_bgcolor=RAISED,
            shape=ft.RoundedRectangleBorder(radius=8),
            collapsed_shape=ft.RoundedRectangleBorder(radius=8),
        )

        editor = ft.Column(
            [
                ft.Row([
                    self.heading("Create", "Turn your ideas into music with ACE-Step 1.5."),
                    ft.Container(expand=True),
                ]),
                generation_feedback,
                ft.Container(
                    border=ft.Border.all(1, BORDER), border_radius=10, padding=14,
                    content=ft.Column([
                        ft.Row([ft.Text("Describe your song", weight=ft.FontWeight.W_600), ft.Container(expand=True), improve_music, develop]),
                        prompt,
                        ft.Row([ft.Text("Lyrics", weight=ft.FontWeight.W_600), ft.Container(expand=True), improve_lyrics]),
                        lyrics,
                        ft.Row([
                            ft.Button("Clear", icon=ft.Icons.DELETE_OUTLINE, color=MUTED, on_click=lambda _event: self._clear_fields(prompt, lyrics)),
                            randomize,
                            ft.Container(expand=True),
                            generate,
                        ]),
                    ], spacing=10, horizontal_alignment=ft.CrossAxisAlignment.STRETCH),
                ),
            ],
            spacing=14,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        )

        inspector = ft.Container(
            width=326,
            bgcolor="#0F1413",
            border=ft.Border(left=ft.BorderSide(1, BORDER)),
            padding=22,
            content=ft.Column([
                ft.Row([ft.Icon(ft.Icons.TUNE, color=GREEN), ft.Text("Generation inspector", size=17, weight=ft.FontWeight.W_600)]),
                ft.Divider(color=BORDER),
                ft.Row([ft.Icon(ft.Icons.SCHEDULE, color=MUTED), ft.Text("Duration", expand=True), duration_value]),
                duration,
                ft.Row([ft.Text("0:30", size=11, color=MUTED), ft.Container(expand=True), ft.Text("10:00", size=11, color=MUTED)]),
                ft.Container(height=6),
                ft.Row([ft.Icon(ft.Icons.SPEED, color=MUTED), ft.Text("BPM", expand=True), bpm_value]),
                bpm,
                ft.Row([ft.Text("40", size=11, color=MUTED), ft.Container(expand=True), ft.Text("200", size=11, color=MUTED)]),
                ft.Container(height=8),
                ft.Row([ft.Icon(ft.Icons.MUSIC_NOTE, color=MUTED), ft.Text("Key", expand=True), ft.Container(key, width=150)]),
                ft.Row([ft.Icon(ft.Icons.MORE_TIME, color=MUTED), ft.Text("Time signature", expand=True), ft.Container(signature, width=150)]),
                ft.Row([ft.Icon(ft.Icons.MIC_OFF, color=MUTED), ft.Text("Instrumental", expand=True), instrumental]),
                ft.Container(height=6),
                advanced,
                ft.Container(expand=True),
            ], spacing=12),
        )
        return ft.Row(
            [ft.Container(editor, expand=True, padding=ft.Padding.only(left=30, right=24, top=22, bottom=18)), inspector],
            spacing=0,
            expand=True,
        )

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
                ft.PopupMenuItem(content="Play", icon=ft.Icons.PLAY_ARROW, on_click=lambda _e: self.play_track(item["audio_path"], item["title"])),
                ft.PopupMenuItem(content="Download", icon=ft.Icons.DOWNLOAD, on_click=lambda _e: self.page.run_task(self._download_track, item["audio_path"], item["title"])),
                ft.PopupMenuItem(content="Rename", icon=ft.Icons.EDIT, on_click=lambda _e: self._rename_track(item, view_index)),
                ft.PopupMenuItem(content="Favorite", icon=ft.Icons.FAVORITE_BORDER, on_click=lambda _e: (self.storage.toggle_favorite(item["id"]), self.views.pop(0, None), self.show_shell(0))),
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

        rename = ft.Button("Rename", icon=ft.Icons.EDIT, bgcolor=GREEN, color="#07140B", on_click=save)
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
        if self.client:
            return self.client
        port, token = self.runtime.start()
        client = AceClient(port, token, timeout=900)
        last_error: Exception | None = None
        for _attempt in range(60):
            try:
                client.health()
                self.client = client
                return client
            except Exception as exc:
                last_error = exc
                time.sleep(0.5)
        raise RuntimeError(f"ACE-Step did not become ready: {last_error}")

    def _generate(self, request: GenerationRequest, progress_callback=None, cancel_event: Event | None = None):
        if cancel_event and cancel_event.is_set():
            raise GenerationCancelled("Generation cancelled")
        client = self._ensure_client()
        if progress_callback:
            progress_callback({"progress": 0, "stage": "Submitting", "progress_text": "Adding your song to the generation queue"})
        task_id = client.generate(request)
        self.storage.record_job(task_id, "running", request.fields())
        started = time.monotonic()

        def progress(update: dict) -> None:
            value = float(update.get("progress", 0))
            elapsed = time.monotonic() - started
            if value >= 0.03:
                update["eta_seconds"] = max(0, elapsed * (1 - value) / value)
            if progress_callback:
                progress_callback(update)

        try:
            result = client.wait(task_id, progress_callback=progress, cancel_event=cancel_event)
        except Exception as exc:
            if cancel_event and cancel_event.is_set():
                self.storage.record_job(task_id, "cancelled", request.fields())
                raise GenerationCancelled("Generation cancelled") from exc
            raise
        if result.title == "Untitled generation":
            result.title = self._prompt_title(request.prompt)
        saved_paths = []
        for number, source in enumerate(result.audio_paths, 1):
            path = Path(source)
            target = self.storage.audio_dir / f"{task_id}-{number}.wav"
            if path.exists():
                shutil.copy2(path, target)
            else:
                client.download_audio(source, target)
            self.storage.save_generation(f"{task_id}-{number}", result.title, request.task_type, str(target), request.prompt, request.lyrics, result.metadata)
            saved_paths.append(str(target))
        result.audio_paths = saved_paths
        self.storage.record_job(task_id, "complete", request.fields())
        return result

    def play_track(self, path: str, title: str) -> None:
        self.page.run_task(self._play_track, path, title)

    async def _resume_audio(self) -> None:
        if not self.audio:
            return
        if self.audio_state == AudioState.COMPLETED:
            await self.audio.play()
        else:
            await self.audio.resume()

    async def _toggle_audio(self, _event: ft.Event | None = None) -> None:
        if self.audio_state == AudioState.PLAYING and self.audio:
            await self.audio.pause()
        else:
            await self._resume_audio()

    def _audio_state_changed(self, event) -> None:
        self.audio_state = event.state
        button = getattr(self, "play_pause_button", None)
        if button:
            button.icon = ft.Icons.PAUSE if event.state == AudioState.PLAYING else ft.Icons.PLAY_ARROW
            button.tooltip = "Pause" if event.state == AudioState.PLAYING else "Play"
        self.now_meta.value = {
            AudioState.PLAYING: "Playing · ACE-Step 1.5",
            AudioState.PAUSED: "Paused",
            AudioState.COMPLETED: "Finished · Press play to replay",
        }.get(event.state, self.now_meta.value)
        self.page.update()
        if event.state == AudioState.COMPLETED:
            if self.repeat_mode == "one":
                self.page.run_task(self._resume_audio)
            elif self.repeat_mode == "all":
                self.page.run_task(self._skip_track, 1)

    def _audio_loaded(self, _event) -> None:
        self.audio_loaded.set()

    def _audio_duration_changed(self, event) -> None:
        seconds = event.duration.in_seconds
        self.progress.max = max(1, seconds)
        self.total.value = self._format_time(seconds)
        self.page.update()

    def _audio_position_changed(self, event) -> None:
        if not self.seeking:
            seconds = event.position / 1000
            self.progress.value = seconds
            self.elapsed.value = self._format_time(seconds)
            self.page.update()

    async def _skip_track(self, offset: int) -> None:
        tracks = self.storage.generations()
        if not tracks:
            self.notice("Generate a song first.", True)
            return
        current = self.current_audio_path
        index = next((i for i, track in enumerate(tracks) if str(Path(track["audio_path"]).resolve()) == current), -1 if offset > 0 else 0)
        track = tracks[(index + offset) % len(tracks)]
        await self._play_track(track["audio_path"], track["title"])

    async def _play_track(self, path: str, title: str) -> None:
        try:
            source = Path(path)
            if not source.is_file():
                raise FileNotFoundError("The saved audio file is missing")
            source_path = str(source.resolve())
            source_changed = self.audio is None or self.audio.src != source_path
            if self.audio is None:
                self.audio_loaded.clear()
                self.audio = Audio(
                    src=source_path,
                    volume=0.85,
                    on_loaded=self._audio_loaded,
                    on_state_change=self._audio_state_changed,
                    on_duration_change=self._audio_duration_changed,
                    on_position_change=self._audio_position_changed,
                )
                self.page.services.append(self.audio)
            elif source_changed:
                self.audio_loaded.clear()
                self.audio.src = source_path
            self.now_title.value = title
            self.now_meta.value = "Loading saved audio…"
            self.current_audio_path = source_path
            self.current_audio_title = title
            self.progress.value = 0
            self.elapsed.value = "0:00"
            self.total.value = "—:—"
            self.page.update()
            if source_changed:
                await asyncio.wait_for(self.audio_loaded.wait(), timeout=15)
            await self.audio.play()
        except Exception as exc:
            self.now_meta.value = "Playback failed"
            self.page.update()
            self.notice(f"Could not play this track: {exc}", True)

    def library_view(self) -> ft.Control:
        search = ft.TextField(hint_text="Search your tracks", prefix_icon=ft.Icons.SEARCH, height=48)
        rows = ft.Column(spacing=8)

        def play(path: str, title: str) -> None:
            self.play_track(path, title)

        def delete(generation_id: str, title: str) -> None:
            def cancel(_event: ft.Event) -> None:
                self.page.pop_dialog()

            def confirm(_event: ft.Event) -> None:
                self.storage.delete_generation(generation_id)
                self.views.pop(0, None)
                self.page.pop_dialog()
                load()
                self.notice(f"Deleted {title}")

            self.page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text(f"Delete {title}?"),
                    content=ft.Text("This permanently removes the track and its audio file."),
                    actions=[ft.TextButton("Cancel", on_click=cancel), ft.Button("Delete", icon=ft.Icons.DELETE_OUTLINE, bgcolor="#8C2431", color="white", on_click=confirm)],
                )
            )

        def load(_event: ft.Event | None = None) -> None:
            rows.controls.clear()
            for item in self.storage.generations(search=search.value):
                rows.controls.append(
                    ft.Container(
                        bgcolor=PANEL, border_radius=10, padding=12,
                        content=ft.Row([
                            ft.IconButton(ft.Icons.PLAY_ARROW, tooltip=f"Play {item['title']}", on_click=lambda _e, p=item["audio_path"], t=item["title"]: self.play_track(p, t)),
                            ft.Column([ft.Text(item["title"], weight=ft.FontWeight.W_600), ft.Text(item["prompt"][:100] or item["task_type"], color=MUTED, size=12)], expand=True),
                            ft.Text(item["created_at"][:16], color=MUTED),
                            ft.IconButton(ft.Icons.EDIT, tooltip="Rename track", on_click=lambda _e, track=item: self._rename_track(track, 1)),
                            ft.IconButton(ft.Icons.FAVORITE if item["favorite"] else ft.Icons.FAVORITE_BORDER, tooltip="Favorite", on_click=lambda _e, i=item["id"]: (self.storage.toggle_favorite(i), load())),
                            ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Delete track", icon_color="#E57373", on_click=lambda _e, i=item["id"], t=item["title"]: delete(i, t)),
                        ]),
                    )
                )
            if not rows.controls:
                rows.controls.append(self.card(ft.Icon(ft.Icons.MUSIC_NOTE, color=GREEN, size=44), ft.Text("Your finished tracks will appear here."), ft.Text("Create your first song to begin your library.", color=MUTED)))
            self.page.update()

        search.on_change = load
        view = ft.Column([self.heading("Your library", "Generated tracks, versions, and favorites."), search, rows], spacing=20, expand=True, scroll=ft.ScrollMode.AUTO)
        load()
        return view

    def edit_view(self) -> ft.Control:
        source = ft.TextField(label="Source audio", read_only=True, expand=True)
        picker = ft.FilePicker()
        self.page.services.append(picker)

        async def choose(_event: ft.Event) -> None:
            files = await picker.pick_files(dialog_title="Choose audio", allowed_extensions=["wav"])
            if files:
                source.value = files[0].path
                self.page.update()

        return ft.Column([
            self.heading("Edit audio", "Repaint, extend, cover, extract, or complete an existing track."),
            self.card(
                ft.Row([source, ft.Button("Choose audio", icon=ft.Icons.UPLOAD_FILE, on_click=choose)]),
                ft.Container(height=150, border_radius=12, gradient=ft.LinearGradient(colors=["#183524", "#25613B", "#183524"]), content=ft.Row([ft.Icon(ft.Icons.GRAPHIC_EQ, color=GREEN, size=80)], alignment=ft.MainAxisAlignment.CENTER)),
                ft.Dropdown(label="Edit type", value="repaint", options=[ft.DropdownOption(key=x, text=x.title()) for x in ["repaint", "extend", "cover", "extract", "lego", "complete"]]),
                ft.TextField(label="Edit instruction", hint_text="Replace the bridge with a sparse piano breakdown", multiline=True, min_lines=3),
                ft.Row([ft.TextField(label="Start (seconds)", value="30"), ft.TextField(label="End (seconds)", value="60"), ft.Button("Run edit", icon=ft.Icons.AUTO_FIX_HIGH, bgcolor=GREEN, color="#07140B")]),
            ),
        ], spacing=22, scroll=ft.ScrollMode.AUTO)

    def train_view(self) -> ft.Control:
        return ft.Column([
            self.heading("Train an adapter", "Fine-tune LoRA or LoKr with ACE-Step's training pipeline."),
            ft.Row([
                self.card(ft.Text("1 · Dataset", size=20, weight=ft.FontWeight.W_600), ft.Text("Add audio, captions, and optional lyrics. ACE-Step will preprocess the dataset.", color=MUTED), ft.Button("Choose dataset folder", icon=ft.Icons.FOLDER_OPEN), ft.Text("No dataset selected", color=MUTED), expand=True),
                self.card(ft.Text("2 · Training", size=20, weight=ft.FontWeight.W_600), ft.Dropdown(label="Adapter", value="lora", options=[ft.DropdownOption(key="lora", text="LoRA"), ft.DropdownOption(key="lokr", text="LoKr")]), ft.TextField(label="Steps", value="1000"), ft.TextField(label="Learning rate", value="0.0001"), ft.Button("Start training", icon=ft.Icons.SCIENCE, bgcolor=GREEN, color="#07140B"), expand=True),
            ], expand=True, vertical_alignment=ft.CrossAxisAlignment.START),
            self.card(ft.Text("Training log", weight=ft.FontWeight.W_600), ft.Text("Training jobs and checkpoints will appear here.", color=MUTED)),
        ], spacing=22, scroll=ft.ScrollMode.AUTO)

    def settings_dialog(self) -> ft.AlertDialog:
        report = self.runtime.hardware
        manifest = self.runtime.current_manifest()
        recommended_dit, recommended_lm = recommended_models(report)
        selected_dit, selected_lm = self.runtime.selected_models()
        installed_dit = [name for name in DIT_MODELS if self.runtime.model_installed(name)]
        installed_lm = [name for name in LM_MODELS if self.runtime.model_installed(name)]
        dit = ft.Dropdown(
            label="Generation model",
            value=selected_dit,
            options=[ft.DropdownOption(key=name, text=name) for name in (installed_dit or [selected_dit])],
        )
        lm = ft.Dropdown(
            label="Language model",
            value=selected_lm or "disabled",
            options=[ft.DropdownOption(key="disabled", text="Disabled")]
            + [ft.DropdownOption(key=name, text=name) for name in installed_lm],
        )

        def close(_event: ft.Event) -> None:
            self.page.pop_dialog()

        def save(_event: ft.Event) -> None:
            selected = [dit.value, None if lm.value == "disabled" else lm.value]
            missing = [name for name in selected if name and not self.runtime.model_installed(name)]
            if missing:
                self.notice(f"Download {missing[0]} before selecting it.", True)
                return
            self.runtime.select_models(*selected)
            self.runtime.stop()
            self.client = None
            self.page.pop_dialog()
            self.notice("Model selection saved. It will load on the next request.")

        async def update(_event: ft.Event) -> None:
            self.notice("Checking and staging the latest ACE-Step runtime…")
            try:
                await asyncio.to_thread(self.runtime.install_latest)
                self.notice("ACE-Step is up to date. Compatibility probe passed.")
            except Exception as exc:
                self.notice(str(exc), True)

        async def download(name: str, button: ft.Button, detail: ft.Text) -> None:
            button.disabled = True
            button.content = "Downloading…"
            self.page.update()
            loop = asyncio.get_running_loop()

            def progress(message: str, _value: float | None) -> None:
                loop.call_soon_threadsafe(lambda: (setattr(detail, "value", message[-100:]), self.page.update()))

            try:
                await asyncio.to_thread(self.runtime.download_model, name, progress)
                button.content = "Installed"
                button.icon = ft.Icons.CHECK
                detail.value = "Installed"
                dropdown = dit if name in DIT_MODELS else lm
                if name not in [option.key for option in dropdown.options]:
                    dropdown.options.append(ft.DropdownOption(key=name, text=name))
            except Exception as exc:
                button.disabled = False
                button.content = "Retry"
                detail.value = str(exc)[-100:]
            self.page.update()

        model_rows = []
        descriptions = {
            "acestep-v15-base": "50 steps · special tasks and fine-tuning",
            "acestep-v15-sft": "50 steps · higher detail",
            "acestep-v15-xl-base": "4B · special tasks · high memory",
            "acestep-v15-xl-sft": "4B · highest detail · high memory",
            "acestep-v15-xl-turbo": "4B · fast · 20 GB+ recommended",
            "acestep-5Hz-lm-4B": "Richest planner · high memory",
        }
        for name in (*DIT_MODELS, *LM_MODELS):
            installed = self.runtime.model_installed(name)
            detail = ft.Text(descriptions.get(name, "Supported ACE-Step model"), color=MUTED, size=11)
            button = ft.Button("Installed" if installed else "Download", icon=ft.Icons.CHECK if installed else ft.Icons.DOWNLOAD, disabled=installed)
            button.on_click = lambda _e, n=name, b=button, d=detail: self.page.run_task(download, n, b, d)
            model_rows.append(ft.ListTile(title=ft.Text(name), subtitle=detail, trailing=button))

        recommended_missing = any(
            name and not self.runtime.model_installed(name) for name in (recommended_dit, recommended_lm)
        )

        content = ft.ListView([
            self.heading("Settings", "Models, runtime, and storage."),
            ft.Text("Models & runtime", size=20, weight=ft.FontWeight.W_600),
            ft.Row([
                self.card(ft.Icon(ft.Icons.MEMORY, color=GREEN, size=36), ft.Text("Hardware", size=20, weight=ft.FontWeight.W_600), ft.Text(report.summary), ft.Text(report.profile.value, color=MUTED), expand=True),
                self.card(ft.Icon(ft.Icons.SYSTEM_UPDATE, color=GREEN, size=36), ft.Text("ACE-Step 1.5", size=20, weight=ft.FontWeight.W_600), ft.Text(f"Commit {(manifest.commit[:10] if manifest else 'not installed')}"), ft.Button("Check for update", on_click=update), expand=True),
            ]),
            self.card(
                ft.Text("Active models", size=20, weight=ft.FontWeight.W_600),
                ft.Text(
                    f"Recommended for this hardware: {recommended_dit} + {recommended_lm or 'no language model'}"
                    + (" · download required" if recommended_missing else ""),
                    color=GREEN,
                    size=12,
                ),
                dit,
                lm,
                ft.Button("Save selection", icon=ft.Icons.SAVE, bgcolor=GREEN, color="#07140B", on_click=save),
            ),
            self.card(ft.Text("Available models", size=20, weight=ft.FontWeight.W_600), *model_rows),
            self.card(ft.Text("Storage", size=20, weight=ft.FontWeight.W_600), ft.ListTile(leading=ft.Icon(ft.Icons.FOLDER), title=ft.Text(str(self.storage.root)), subtitle=ft.Text("Runtime, models, library, training data, and logs"))),
            self.card(ft.Text("About", size=20, weight=ft.FontWeight.W_600), ft.Text("ACE Studio 0.1.7"), ft.Text("ACE-Step is installed from its official upstream repository and keeps its own license files.", color=MUTED)),
        ], spacing=18, width=780, height=610)
        return ft.AlertDialog(modal=True, content=content, actions=[ft.TextButton("Close", on_click=close)])


async def main(page: ft.Page) -> None:
    AceStudio(page)


def run() -> None:
    ft.run(main)
