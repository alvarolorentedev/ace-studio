from __future__ import annotations

import asyncio
from threading import Event

import flet as ft

from ..models import GenerationRequest, MemoryMode
from ..theme import (
    BORDER,
    DANGER_BUTTON_STYLE,
    ERROR_BORDER,
    ERROR_SURFACE,
    FIELD_STYLE,
    GREEN,
    MUTED,
    PRIMARY_BUTTON_STYLE,
    RAISED,
    SUCCESS_BORDER,
    SUCCESS_SURFACE,
    WARNING,
)


def build(studio) -> ft.Control:
    prompt = ft.TextField(
        value="",
        hint_text="A nostalgic synthwave track with driving drums, warm pads, and a hopeful mood.",
        multiline=True,
        min_lines=2,
        max_length=1000,
        **FIELD_STYLE,
    )
    lyrics = ft.TextField(
        value="",
        hint_text="[Verse]\nCity lights fade into the night…\n\n[Chorus]\nWe rise above the afterglow…",
        multiline=True,
        min_lines=6,
        max_length=4000,
        **FIELD_STYLE,
    )
    duration_value = ft.Text("2:00", weight=ft.FontWeight.W_600)
    duration = ft.Slider(min=30, max=600, value=120, divisions=57)
    bpm_value = ft.Text("120", weight=ft.FontWeight.W_600)
    bpm = ft.Slider(min=40, max=200, value=120, divisions=160)
    key = ft.Dropdown(
        label="Key",
        value="A minor",
        options=[ft.DropdownOption(key=x, text=x) for x in ["Auto", "C major", "A minor", "D major", "E minor", "F major", "G minor"]],
        dense=True,
        expand=True,
        **FIELD_STYLE,
    )
    signature = ft.Dropdown(
        label="Time signature",
        value="4/4",
        options=[ft.DropdownOption(key=x, text=x) for x in ["Auto", "4/4", "3/4", "6/8"]],
        dense=True,
        expand=True,
        **FIELD_STYLE,
    )
    language = ft.Dropdown(
        label="Lyrics language",
        value="en",
        options=[
            ft.DropdownOption(key=code, text=name)
            for code, name in [
                ("en", "English"),
                ("es", "Spanish"),
                ("fr", "French"),
                ("de", "German"),
                ("it", "Italian"),
                ("pt", "Portuguese"),
                ("zh", "Chinese"),
                ("ja", "Japanese"),
                ("ko", "Korean"),
            ]
        ],
        dense=True,
        expand=True,
        **FIELD_STYLE,
    )
    instrumental = ft.Switch(value=False, active_color=GREEN)
    thinking = ft.Switch(label="Use language model reasoning", value=True, active_color=GREEN)
    batch = ft.Dropdown(
        label="Versions", value="1", options=[ft.DropdownOption(key=str(x), text=str(x)) for x in range(1, 5)], width=130, **FIELD_STYLE
    )
    seed = ft.TextField(label="Seed", hint_text="Random", width=150, keyboard_type=ft.KeyboardType.NUMBER, **FIELD_STYLE)
    guidance = ft.TextField(label="Guidance", value="15", width=130, keyboard_type=ft.KeyboardType.NUMBER, **FIELD_STYLE)
    generate = ft.Button("Generate", icon=ft.Icons.GRAPHIC_EQ, style=PRIMARY_BUTTON_STYLE)
    improve_music = ft.Button("Improve music", icon=ft.Icons.AUTO_FIX_HIGH, color=GREEN)
    improve_lyrics = ft.Button("Improve lyrics", icon=ft.Icons.AUTO_FIX_HIGH, color=GREEN)
    develop = ft.Button("Develop idea", icon=ft.Icons.PSYCHOLOGY, color=GREEN)
    randomize = ft.Button("Randomize", icon=ft.Icons.SHUFFLE, color=MUTED)
    memory = studio.runtime.get_memory_settings()
    memory_badge_color = GREEN if memory.mode == MemoryMode.SAFE else (WARNING if memory.mode == MemoryMode.FULL else MUTED)
    memory_badge_icon = (
        ft.Icons.SHIELD if memory.mode == MemoryMode.SAFE
        else (ft.Icons.WARNING if memory.mode == MemoryMode.FULL else ft.Icons.BALANCE)
    )
    memory_badge = ft.Row(
        [
            ft.Icon(memory_badge_icon, size=12, color=memory_badge_color),
            ft.Text(f"Memory: {memory.mode.value.capitalize()}", size=11, color=memory_badge_color),
        ],
        spacing=4,
        tooltip="Current memory safety mode. Change in Settings.",
    )
    generation_progress = ft.ProgressBar(value=0)
    generation_stage = ft.Text("Preparing ACE-Step", size=16, weight=ft.FontWeight.W_600)
    generation_percent = ft.Text("0%", color=GREEN, weight=ft.FontWeight.BOLD)
    generation_detail = ft.Text("Loading models…", color=MUTED, size=12)
    generation_eta = ft.Text("Estimating finish time…", color=MUTED, size=12)
    generation_actions = ft.Row(visible=False, wrap=True)
    generation_feedback = ft.Container(
        visible=False,
        bgcolor=SUCCESS_SURFACE,
        border=ft.Border.all(1, SUCCESS_BORDER),
        border_radius=10,
        padding=16,
        content=ft.Column(
            [
                ft.Row([ft.Icon(ft.Icons.GRAPHIC_EQ, color=GREEN), generation_stage, ft.Container(expand=True), generation_percent]),
                generation_progress,
                ft.Row([generation_detail, ft.Container(expand=True), generation_eta]),
                generation_actions,
            ],
            spacing=9,
        ),
    )

    def format_duration(seconds: float) -> str:
        total = int(seconds)
        return f"{total // 60}:{total % 60:02d}"

    def sync_duration(event: ft.Event) -> None:
        duration_value.value = format_duration(event.control.value)
        studio.page.update()

    def sync_bpm(event: ft.Event) -> None:
        bpm_value.value = str(int(event.control.value))
        studio.page.update()

    duration.on_change = sync_duration
    bpm.on_change = sync_bpm

    async def improve(kind: str, button: ft.Button) -> None:
        if kind == "music" and not prompt.value.strip():
            studio.notice("Describe the music you want to improve first.", True)
            return
        if kind == "lyrics" and not lyrics.value.strip():
            studio.notice("Add a lyric idea or draft first.", True)
            return
        original = button.content
        button.disabled = True
        button.content = "ACE is writing…"
        studio.status.value = "5Hz LM is improving your idea"
        studio.page.update()
        try:
            client = await asyncio.to_thread(studio._ensure_client)
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
            studio.notice(f"{kind.title()} improved with ACE-Step's language model.")
        except Exception as exc:
            studio.notice(str(exc), True)
        finally:
            button.disabled = False
            button.content = original
            studio.status.value = "Ready"
            studio.page.update()

    async def develop_idea(_event: ft.Event) -> None:
        if not prompt.value.strip():
            studio.notice("Give ACE a short idea to develop.", True)
            return
        original = develop.content
        develop.disabled = True
        develop.content = "Developing…"
        studio.page.update()

        query = prompt.value.strip()
        details = []
        if instrumental.value:
            details.append("Instrumental track")
        else:
            language_name = next((opt.text for opt in language.options if opt.key == language.value), language.value)
            details.append(f"Vocals in {language_name}")
        details.append(f"{int(bpm.value)} BPM")
        if key.value != "Auto":
            details.append(f"Key: {key.value}")
        if signature.value != "Auto":
            details.append(f"Time signature: {signature.value}")
        if details:
            query = f"{query}. {', '.join(details)}."

        try:
            client = await asyncio.to_thread(studio._ensure_client)
            result = await asyncio.to_thread(
                client.create_sample,
                query,
                instrumental.value,
                language.value,
                duration=float(duration.value),
                bpm=int(bpm.value),
                key_scale="" if key.value == "Auto" else key.value,
                time_signature="" if signature.value == "Auto" else signature.value,
            )
            prompt.value = result.get("caption") or prompt.value
            lyrics.value = result.get("lyrics") or lyrics.value
            studio.notice("ACE developed your idea into a complete song brief.")
        except Exception as exc:
            studio.notice(str(exc), True)
        finally:
            develop.disabled = False
            develop.content = original
            studio.page.update()

    async def random_idea(_event: ft.Event) -> None:
        try:
            client = await asyncio.to_thread(studio._ensure_client)
            result = await asyncio.to_thread(client.random_sample)
            prompt.value = result.get("caption") or result.get("prompt") or ""
            lyrics.value = result.get("lyrics") or ""
            studio.page.update()
        except Exception as exc:
            studio.notice(str(exc), True)

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
            studio.notice("Add a description or lyrics first.", True)
            return
        try:
            request = GenerationRequest(
                prompt=prompt.value.strip(),
                lyrics=lyrics.value.strip(),
                duration=float(duration.value),
                bpm=int(bpm.value),
                key_scale="" if key.value == "Auto" else key.value,
                time_signature="" if signature.value == "Auto" else signature.value,
                instrumental=instrumental.value,
                vocal_language=language.value,
                thinking=thinking.value,
                batch_size=int(batch.value),
                seed=int(seed.value) if seed.value.strip() else None,
                advanced={"guidance_scale": guidance.value},
            )
            request.model = studio.runtime.selected_models()[0]
        except ValueError:
            studio.notice("BPM, seed, and guidance must be valid numbers.", True)
            return
        generate.disabled = True
        generate.content = "Generating…"
        studio.status.value = "ACE-Step is creating"
        generation_feedback.visible = True
        generation_feedback.bgcolor = SUCCESS_SURFACE
        generation_feedback.border = ft.Border.all(1, SUCCESS_BORDER)
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
            studio.page.update()
            await asyncio.to_thread(studio.runtime.stop)
            studio.generation.reset_client()
            studio.client = None

        stop = ft.Button("Stop", icon=ft.Icons.STOP, style=DANGER_BUTTON_STYLE, on_click=stop_generation)
        generation_actions.controls = [stop]
        generation_actions.visible = True
        studio.page.update()
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
                generation_eta.value = f"About {studio._format_eta(eta)} remaining" if eta is not None else "Estimating finish time…"
                studio.page.update()

            loop.call_soon_threadsafe(paint)

        try:
            result = await asyncio.to_thread(studio._generate, request, update_progress, cancel_event)
            generation_progress.value = 1
            generation_percent.value = "100%"
            generation_stage.value = "Your tracks are ready"
            generation_detail.value = f"Created {len(result.audio_paths)} version(s) and saved them to your library."
            generation_eta.value = "Finished"
            generation_actions.controls = [
                ft.Button(
                    f"Play version {number}",
                    icon=ft.Icons.PLAY_ARROW,
                    style=PRIMARY_BUTTON_STYLE,
                    on_click=lambda _event, p=path, n=number: studio.play_track(p, f"{result.title} · Version {n}"),
                )
                for number, path in enumerate(result.audio_paths, 1)
            ]
            generation_actions.visible = True
            studio.views.pop(1, None)
            studio.notice(f"Created {len(result.audio_paths)} track(s)")
        except Exception as exc:
            if cancel_event.is_set():
                generation_progress.value = 0
                generation_percent.value = "Stopped"
                generation_stage.value = "Generation cancelled"
                generation_detail.value = "No track was saved."
                generation_eta.value = "Ready when you are"
                generation_actions.controls.clear()
                generation_actions.visible = False
                studio.notice("Generation cancelled")
                return
            generation_progress.value = 0
            generation_percent.value = "Failed"
            generation_stage.value = "Generation stopped"
            generation_detail.value = str(exc)
            generation_eta.value = "Try again"
            generation_feedback.bgcolor = ERROR_SURFACE
            generation_feedback.border = ft.Border.all(1, ERROR_BORDER)
            studio.notice(str(exc), True)
        finally:
            generate.disabled = False
            generate.content = "Generate"
            studio.status.value = "Ready"
            studio.page.update()

    generate.on_click = submit
    advanced = ft.ExpansionTile(
        title=ft.Text("Advanced controls", size=14),
        controls=[
            ft.Container(ft.Column([thinking, ft.Row([batch, seed, guidance], wrap=True)], spacing=12), padding=ft.Padding.only(bottom=12))
        ],
        bgcolor=RAISED,
        collapsed_bgcolor=RAISED,
        shape=ft.RoundedRectangleBorder(radius=8),
        collapsed_shape=ft.RoundedRectangleBorder(radius=8),
    )
    adapters = studio.storage.adapters()
    active_adapter = next((adapter for adapter in adapters if adapter.active), None)
    adapter = ft.Dropdown(
        label="LoRA adapter",
        value=active_adapter.id if active_adapter else "none",
        width=170,
        options=[ft.DropdownOption(key="none", text="None")] + [ft.DropdownOption(key=item.id, text=item.name) for item in adapters],
        disabled=not adapters,
        **FIELD_STYLE,
    )
    adapter_scale = ft.Dropdown(
        label="Strength",
        value=str(active_adapter.scale if active_adapter else 1.0),
        width=90,
        options=[ft.DropdownOption(key=str(value), text=str(value)) for value in (0.25, 0.5, 0.75, 1.0)],
        disabled=not adapters,
        **FIELD_STYLE,
    )

    async def apply_adapter(_event: ft.Event) -> None:
        try:
            if adapter.value == "none":
                await asyncio.to_thread(studio.training.deactivate)
            else:
                await asyncio.to_thread(studio.training.activate, adapter.value, True, float(adapter_scale.value))
            studio.notice("Generation adapter updated.")
        except Exception as exc:
            studio.notice(str(exc), True)

    adapter.on_select = apply_adapter
    adapter_scale.on_select = apply_adapter

    editor = ft.Column(
        [
            ft.Row(
                [
                    studio.heading("Create", "Turn your ideas into music with ACE-Step 1.5."),
                    ft.Container(expand=True),
                ]
            ),
            generation_feedback,
            ft.Container(
                border=ft.Border.all(1, BORDER),
                border_radius=10,
                padding=14,
                content=ft.Column(
                    [
                        ft.Row(
                            [ft.Text("Describe your song", weight=ft.FontWeight.W_600), ft.Container(expand=True), improve_music, develop]
                        ),
                        prompt,
                        ft.Row([ft.Text("Lyrics", weight=ft.FontWeight.W_600), ft.Container(expand=True), improve_lyrics]),
                        lyrics,
                        ft.Row(
                            [
                                ft.Button(
                                    "Clear",
                                    icon=ft.Icons.DELETE_OUTLINE,
                                    color=MUTED,
                                    on_click=lambda _event: studio._clear_fields(prompt, lyrics),
                                ),
                                randomize,
                                ft.Container(expand=True),
                                ft.Column(
                                    [
                                        generate,
                                        memory_badge,
                                    ],
                                    horizontal_alignment=ft.CrossAxisAlignment.END,
                                    spacing=4,
                                ),
                            ]
                        ),
                    ],
                    spacing=10,
                    horizontal_alignment=ft.CrossAxisAlignment.STRETCH,
                ),
            ),
        ],
        spacing=14,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )

    inspector = ft.Container(
        width=326,
        bgcolor=RAISED,
        border=ft.Border(left=ft.BorderSide(1, BORDER)),
        padding=22,
        content=ft.Column(
            [
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
                ft.Row([key], spacing=0),
                ft.Row([signature], spacing=0),
                ft.Row([language], spacing=0),
                ft.Row([ft.Icon(ft.Icons.MIC_OFF, color=MUTED), ft.Text("Instrumental", expand=True), instrumental]),
                ft.Row([adapter, adapter_scale], spacing=10),
                ft.Container(height=6),
                advanced,
                ft.Container(expand=True),
            ],
            spacing=12,
            scroll=ft.ScrollMode.AUTO,
            expand=True,
        ),
    )
    return ft.Row(
        [ft.Container(editor, expand=True, padding=ft.Padding.only(left=30, right=24, top=22, bottom=18)), inspector],
        spacing=0,
        expand=True,
    )
