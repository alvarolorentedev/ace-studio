from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import flet as ft
from flet_audio import Audio

from .api import AceClient
from .models import GenerationRequest
from .runtime import RuntimeManager, recommended_models
from .storage import Storage


GREEN = "#1ED760"
INK = "#0B0D0C"
PANEL = "#151816"
MUTED = "#A7ADA9"


class AceStudio:
    def __init__(self, page: ft.Page) -> None:
        self.page = page
        self.storage = Storage()
        self.runtime = RuntimeManager(self.storage)
        self.client: AceClient | None = None
        self.content = ft.Container(expand=True)
        self.status = ft.Text("Local · private", color=MUTED, size=12)
        self.now_title = ft.Text("Nothing playing", weight=ft.FontWeight.W_600)
        self.audio = Audio(volume=0.85)
        self.page.services.append(self.audio)
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
            log.value = "Preparing the private local runtime…"
            self.page.update()
            loop = asyncio.get_running_loop()

            def update(message: str, value: float | None) -> None:
                def paint() -> None:
                    log.value = message[-180:]
                    progress.value = value
                    self.page.update()

                loop.call_soon_threadsafe(paint)

            try:
                await asyncio.to_thread(self.runtime.install_latest, update)
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
                                        ft.Row([ft.Icon(ft.Icons.GRAPHIC_EQ, color=GREEN, size=36), ft.Text("ACE Studio", size=30, weight=ft.FontWeight.BOLD)]),
                                        ft.Text("Your local music studio", size=42, weight=ft.FontWeight.BOLD),
                                        ft.Text("ACE-Step runs on this computer. Your prompts, lyrics, references, and finished tracks stay here.", color=MUTED, size=16),
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
        destinations = [
            ("Create", ft.Icons.AUTO_AWESOME),
            ("Library", ft.Icons.LIBRARY_MUSIC),
            ("Edit", ft.Icons.EDIT_AUDIO),
            ("Train", ft.Icons.SCIENCE),
            ("Models", ft.Icons.MODEL_TRAINING),
            ("Settings", ft.Icons.SETTINGS),
        ]

        def navigate(event: ft.Event[ft.NavigationRail]) -> None:
            self.render(event.control.selected_index or 0)

        rail = ft.NavigationRail(
            selected_index=index,
            destinations=[ft.NavigationRailDestination(icon=icon, selected_icon=icon, label=label) for label, icon in destinations],
            leading=ft.Container(ft.Row([ft.Icon(ft.Icons.GRAPHIC_EQ, color=GREEN), ft.Text("ACE Studio", weight=ft.FontWeight.BOLD)]), padding=18),
            bgcolor="#101310",
            indicator_color="#24442D",
            extended=True,
            min_extended_width=210,
            on_change=navigate,
        )
        player = ft.Container(
            height=76,
            bgcolor="#111411",
            border=ft.Border(top=ft.BorderSide(1, "#252A26")),
            padding=ft.Padding.symmetric(horizontal=24),
            content=ft.Row(
                [
                    ft.Icon(ft.Icons.ALBUM, color=GREEN, size=34),
                    ft.Column([self.now_title, ft.Text("ACE Studio library", size=11, color=MUTED)], spacing=2, alignment=ft.MainAxisAlignment.CENTER, width=220),
                    ft.IconButton(ft.Icons.PLAY_ARROW, tooltip="Play", on_click=lambda _e: self.audio.resume()),
                    ft.IconButton(ft.Icons.PAUSE, tooltip="Pause", on_click=lambda _e: self.audio.pause()),
                    ft.Container(expand=True),
                    self.status,
                ]
            ),
        )
        self.page.clean()
        self.page.add(ft.Column([ft.Row([rail, self.content], spacing=0, expand=True), player], spacing=0, expand=True))
        self.render(index)

    def render(self, index: int) -> None:
        builders = [self.create_view, self.library_view, self.edit_view, self.train_view, self.models_view, self.settings_view]
        self.content.content = builders[index]()
        self.content.padding = 28
        self.page.update()

    def heading(self, title: str, subtitle: str) -> ft.Column:
        return ft.Column([ft.Text(title, size=32, weight=ft.FontWeight.BOLD), ft.Text(subtitle, color=MUTED)], spacing=4)

    def create_view(self) -> ft.Control:
        prompt = ft.TextField(label="Describe the music", hint_text="Dreamy synth-pop, warm bass, intimate vocals…", multiline=True, min_lines=3)
        lyrics = ft.TextField(label="Lyrics", hint_text="[Verse]\nWrite lyrics or leave blank for instrumental music", multiline=True, min_lines=8)
        duration = ft.Slider(min=10, max=600, value=120, divisions=59, label="{value}s", active_color=GREEN)
        bpm = ft.TextField(label="BPM", value="", width=130, keyboard_type=ft.KeyboardType.NUMBER)
        key = ft.Dropdown(label="Key", value="", options=[ft.DropdownOption(key="", text="Auto")] + [ft.DropdownOption(key=x, text=x) for x in ["C major", "A minor", "D major", "E minor", "F major", "G minor"]], width=160)
        signature = ft.Dropdown(label="Time", value="", options=[ft.DropdownOption(key="", text="Auto"), ft.DropdownOption(key="4/4", text="4/4"), ft.DropdownOption(key="3/4", text="3/4"), ft.DropdownOption(key="6/8", text="6/8")], width=130)
        instrumental = ft.Switch(label="Instrumental", value=False, active_color=GREEN)
        thinking = ft.Switch(label="Use language model / thinking", value=True, active_color=GREEN)
        batch = ft.Dropdown(label="Versions", value="2", options=[ft.DropdownOption(key=str(x), text=str(x)) for x in range(1, 5)], width=130)
        seed = ft.TextField(label="Seed (blank = random)", width=190, keyboard_type=ft.KeyboardType.NUMBER)
        guidance = ft.TextField(label="Guidance scale", value="15", width=160, keyboard_type=ft.KeyboardType.NUMBER)
        generate = ft.Button("Generate", icon=ft.Icons.AUTO_AWESOME, bgcolor=GREEN, color="#07140B")

        async def submit(_event: ft.Event) -> None:
            if not prompt.value.strip() and not lyrics.value.strip():
                self.notice("Add a description or lyrics first.", True)
                return
            try:
                request = GenerationRequest(
                    prompt=prompt.value.strip(), lyrics=lyrics.value.strip(), duration=float(duration.value),
                    bpm=int(bpm.value) if bpm.value.strip() else None, key_scale=key.value or "",
                    time_signature=signature.value or "", instrumental=instrumental.value,
                    thinking=thinking.value, batch_size=int(batch.value), seed=int(seed.value) if seed.value.strip() else None,
                    advanced={"guidance_scale": guidance.value},
                )
            except ValueError:
                self.notice("BPM, seed, and guidance must be valid numbers.", True)
                return
            generate.disabled = True
            generate.content = "Generating…"
            self.status.value = "ACE-Step is creating"
            self.page.update()
            try:
                result = await asyncio.to_thread(self._generate, request)
                self.notice(f"Created {len(result.audio_paths)} track(s)")
                self.render(1)
            except Exception as exc:
                self.notice(str(exc), True)
            finally:
                generate.disabled = False
                generate.content = "Generate"
                self.status.value = "Local · private"
                self.page.update()

        generate.on_click = submit
        advanced = ft.ExpansionTile(
            title=ft.Text("Advanced generation"),
            subtitle=ft.Text("Seed, model thinking, batch, and guidance", color=MUTED),
            controls=[ft.Container(ft.Row([thinking, batch, seed, guidance], wrap=True), padding=ft.Padding.only(bottom=12))],
        )
        return ft.Column(
            [
                self.heading("Create", "Turn a musical idea into a full track with ACE-Step 1.5."),
                ft.Row(
                    [self.card(prompt, lyrics, expand=True), self.card(ft.Text("Shape", size=20, weight=ft.FontWeight.W_600), ft.Text("Duration", color=MUTED), duration, ft.Row([bpm, key, signature], wrap=True), instrumental, advanced, generate, expand=True)],
                    expand=True,
                    vertical_alignment=ft.CrossAxisAlignment.START,
                ),
            ], spacing=22, expand=True, scroll=ft.ScrollMode.AUTO,
        )

    def _generate(self, request: GenerationRequest):
        if not self.client:
            port, token = self.runtime.start()
            self.client = AceClient(port, token, timeout=120)
        task_id = self.client.generate(request)
        self.storage.record_job(task_id, "running", request.fields())
        result = self.client.wait(task_id)
        for number, source in enumerate(result.audio_paths, 1):
            path = Path(source)
            target = self.storage.audio_dir / f"{task_id}-{number}{path.suffix or '.wav'}"
            if path.exists():
                shutil.copy2(path, target)
            else:
                target = path
            self.storage.save_generation(f"{task_id}-{number}", result.title, request.task_type, str(target), request.prompt, request.lyrics, result.metadata)
        self.storage.record_job(task_id, "complete", request.fields())
        return result

    def library_view(self) -> ft.Control:
        search = ft.TextField(hint_text="Search your tracks", prefix_icon=ft.Icons.SEARCH, height=48)
        rows = ft.Column(spacing=8)

        def play(path: str, title: str) -> None:
            self.audio.src = path
            self.now_title.value = title
            self.audio.play()
            self.page.update()

        def load(_event: ft.Event | None = None) -> None:
            rows.controls.clear()
            for item in self.storage.generations(search=search.value):
                rows.controls.append(
                    ft.Container(
                        bgcolor=PANEL, border_radius=10, padding=12,
                        content=ft.Row([
                            ft.IconButton(ft.Icons.PLAY_ARROW, tooltip=f"Play {item['title']}", on_click=lambda _e, p=item["audio_path"], t=item["title"]: play(p, t)),
                            ft.Column([ft.Text(item["title"], weight=ft.FontWeight.W_600), ft.Text(item["prompt"][:100] or item["task_type"], color=MUTED, size=12)], expand=True),
                            ft.Text(item["created_at"][:16], color=MUTED),
                            ft.IconButton(ft.Icons.FAVORITE if item["favorite"] else ft.Icons.FAVORITE_BORDER, tooltip="Favorite", on_click=lambda _e, i=item["id"]: (self.storage.toggle_favorite(i), load())),
                        ]),
                    )
                )
            if not rows.controls:
                rows.controls.append(self.card(ft.Icon(ft.Icons.MUSIC_NOTE, color=GREEN, size=44), ft.Text("Your finished tracks will appear here."), ft.Text("Create your first song to begin a local library.", color=MUTED)))
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
            files = await picker.pick_files(dialog_title="Choose audio", allowed_extensions=["wav", "mp3", "flac", "m4a"])
            if files:
                source.value = files[0].path
                self.page.update()

        return ft.Column([
            self.heading("Edit audio", "Repaint, extend, cover, extract, or complete an existing track."),
            self.card(
                ft.Row([source, ft.Button("Choose audio", icon=ft.Icons.UPLOAD_FILE, on_click=choose)]),
                ft.Container(height=150, border_radius=12, gradient=ft.LinearGradient(colors=["#183524", "#25613B", "#183524"]), content=ft.Row([ft.Icon(ft.Icons.GRAPHIC_EQ, color=GREEN, size=80)], alignment=ft.MainAxisAlignment.CENTER)),
                ft.SegmentedButton(selected={"repaint"}, segments=[ft.Segment(value=x, label=ft.Text(x.title())) for x in ["repaint", "extend", "cover", "extract", "lego", "complete"]]),
                ft.TextField(label="Edit instruction", hint_text="Replace the bridge with a sparse piano breakdown", multiline=True, min_lines=3),
                ft.Row([ft.TextField(label="Start (seconds)", value="30"), ft.TextField(label="End (seconds)", value="60"), ft.Button("Run edit", icon=ft.Icons.AUTO_FIX_HIGH, bgcolor=GREEN, color="#07140B")]),
            ),
        ], spacing=22, scroll=ft.ScrollMode.AUTO)

    def train_view(self) -> ft.Control:
        return ft.Column([
            self.heading("Train an adapter", "Fine-tune LoRA or LoKr locally with ACE-Step's training pipeline."),
            ft.Row([
                self.card(ft.Text("1 · Dataset", size=20, weight=ft.FontWeight.W_600), ft.Text("Add audio, captions, and optional lyrics. ACE-Step will preprocess the dataset.", color=MUTED), ft.Button("Choose dataset folder", icon=ft.Icons.FOLDER_OPEN), ft.Text("No dataset selected", color=MUTED), expand=True),
                self.card(ft.Text("2 · Training", size=20, weight=ft.FontWeight.W_600), ft.Dropdown(label="Adapter", value="lora", options=[ft.DropdownOption(key="lora", text="LoRA"), ft.DropdownOption(key="lokr", text="LoKr")]), ft.TextField(label="Steps", value="1000"), ft.TextField(label="Learning rate", value="0.0001"), ft.Button("Start training", icon=ft.Icons.SCIENCE, bgcolor=GREEN, color="#07140B"), expand=True),
            ], expand=True, vertical_alignment=ft.CrossAxisAlignment.START),
            self.card(ft.Text("Training log", weight=ft.FontWeight.W_600), ft.Text("Training jobs and checkpoints will appear here.", color=MUTED)),
        ], spacing=22, scroll=ft.ScrollMode.AUTO)

    def models_view(self) -> ft.Control:
        report = self.runtime.hardware
        manifest = self.runtime.current_manifest()
        model, lm = recommended_models(report)

        async def update(_event: ft.Event) -> None:
            self.notice("Checking and staging the latest ACE-Step runtime…")
            try:
                await asyncio.to_thread(self.runtime.install_latest)
                self.notice("ACE-Step is up to date. Compatibility probe passed.")
                self.render(4)
            except Exception as exc:
                self.notice(str(exc), True)

        return ft.Column([
            self.heading("Models & runtime", "Hardware-aware local inference and upstream updates."),
            ft.Row([
                self.card(ft.Icon(ft.Icons.MEMORY, color=GREEN, size=36), ft.Text("Hardware", size=20, weight=ft.FontWeight.W_600), ft.Text(report.summary), ft.Text(report.profile.value, color=MUTED), expand=True),
                self.card(ft.Icon(ft.Icons.SYSTEM_UPDATE, color=GREEN, size=36), ft.Text("ACE-Step 1.5", size=20, weight=ft.FontWeight.W_600), ft.Text(f"Commit {(manifest.commit[:10] if manifest else 'not installed')}"), ft.Button("Check for update", on_click=update), expand=True),
            ]),
            self.card(ft.Text("Recommended model set", size=20, weight=ft.FontWeight.W_600), ft.ListTile(leading=ft.Icon(ft.Icons.CHECK_CIRCLE, color=GREEN), title=ft.Text(model), subtitle=ft.Text("Diffusion model")), ft.ListTile(leading=ft.Icon(ft.Icons.CHECK_CIRCLE, color=GREEN), title=ft.Text(lm or "Language model disabled"), subtitle=ft.Text("Selected for available memory"))),
        ], spacing=22, scroll=ft.ScrollMode.AUTO)

    def settings_view(self) -> ft.Control:
        return ft.Column([
            self.heading("Settings", "Local storage and privacy controls."),
            self.card(ft.Text("Storage", size=20, weight=ft.FontWeight.W_600), ft.ListTile(leading=ft.Icon(ft.Icons.FOLDER), title=ft.Text(str(self.storage.root)), subtitle=ft.Text("Runtime, models, library, training data, and logs"))),
            self.card(ft.Text("Privacy", size=20, weight=ft.FontWeight.W_600), ft.Switch(label="Allow anonymous analytics", value=False, disabled=True), ft.Text("ACE Studio has no analytics and binds ACE-Step only to 127.0.0.1 with a per-launch token.", color=MUTED)),
            self.card(ft.Text("About", size=20, weight=ft.FontWeight.W_600), ft.Text("ACE Studio 0.1.0"), ft.Text("ACE-Step is installed from its official upstream repository and keeps its own license files.", color=MUTED)),
        ], spacing=22, scroll=ft.ScrollMode.AUTO)


async def main(page: ft.Page) -> None:
    AceStudio(page)


def run() -> None:
    ft.run(main)
