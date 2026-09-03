from __future__ import annotations

import asyncio
from threading import Event

import flet as ft

from ..models import TRACK_NAMES, EditRequest
from ..theme import BORDER, GREEN, MUTED, RAISED


def build(studio) -> ft.Control:
    source = ft.TextField(label="Source WAV", read_only=True, expand=True)
    picker = ft.FilePicker()
    studio.page.services.append(picker)
    tracks = studio.storage.generations()
    library = ft.Dropdown(
        label="Or choose from library",
        options=[ft.DropdownOption(key=item["id"], text=item["title"]) for item in tracks],
        expand=True,
    )
    by_id = {item["id"]: item for item in tracks}
    mode_specs = (
        ("cover", "Cover / style transfer", "Apply a new style while preserving the composition.", ft.Icons.AUTO_FIX_HIGH),
        ("repaint", "Repaint section", "Redraw a selected time range from your description.", ft.Icons.BRUSH),
        ("lego", "Lego: add one track", "Add a new instrument or vocal layer.", ft.Icons.LIBRARY_ADD),
        ("extract", "Extract one track", "Separate one instrument or vocal stem.", ft.Icons.CALL_SPLIT),
        ("complete", "Complete / extend", "Continue selected tracks beyond the source.", ft.Icons.GRAPHIC_EQ),
    )
    mode_cards: dict[str, ft.Container] = {}
    mode = ft.RadioGroup(
        value="repaint",
        content=ft.Column(spacing=8),
    )
    prompt = ft.TextField(label="Edit description", multiline=True, min_lines=4, expand=True)
    lyrics = ft.TextField(label="Lyrics (optional)", multiline=True, min_lines=3, expand=True)
    start = ft.TextField(label="Start (seconds)", value="0", width=160)
    end = ft.TextField(label="End (seconds)", value="30", width=160)
    repaint_range = ft.Row([start, end])
    strength = ft.Slider(min=0, max=1, value=0.8, divisions=20)
    strength_row = ft.Column([ft.Text("Source preservation"), strength])
    track = ft.Dropdown(
        label="Instrument track",
        options=[ft.DropdownOption(key=name, text=name.replace("_", " ").title()) for name in TRACK_NAMES],
        expand=True,
    )
    track_checks = [ft.Checkbox(label=name.replace("_", " ").title()) for name in TRACK_NAMES]
    complete_tracks = ft.Column([ft.Text("Tracks to complete"), ft.Row(track_checks, wrap=True)])
    warning = ft.Text(color="#E5B95C")
    status = ft.Text("Ready")
    result_status = ft.Text("No edit run yet.", color=MUTED)
    progress = ft.ProgressBar(value=0, color=GREEN, bgcolor="#34403B")
    run = ft.Button("Run edit", icon=ft.Icons.AUTO_FIX_HIGH, bgcolor=GREEN, color="#07140B")
    stop = ft.Button("Stop", icon=ft.Icons.STOP, visible=False)
    cancel_event: Event | None = None

    def choose_mode(selected: str) -> None:
        mode.value = selected
        sync_mode()

    for key, label, description, icon in mode_specs:
        card = ft.Container(
            ft.Row(
                [
                    ft.Icon(icon, color=MUTED),
                    ft.Column(
                        [ft.Text(label, weight=ft.FontWeight.W_600), ft.Text(description, size=11, color=MUTED)],
                        spacing=2,
                        expand=True,
                    ),
                    ft.Radio(value=key, active_color=GREEN),
                ]
            ),
            bgcolor=RAISED,
            border=ft.Border.all(1, BORDER),
            border_radius=8,
            padding=10,
            on_click=lambda _event, selected=key: choose_mode(selected),
        )
        mode_cards[key] = card
        mode.content.controls.append(card)

    def select_library(event: ft.Event) -> None:
        if item := by_id.get(event.control.value):
            source.value = item["audio_path"]
            studio.page.update()

    async def choose(_event: ft.Event) -> None:
        files = await picker.pick_files(dialog_title="Choose source WAV", allowed_extensions=["wav"])
        if files:
            source.value = files[0].path
            library.value = None
            studio.page.update()

    def sync_mode(_event: ft.Event | None = None) -> None:
        repaint_range.visible = mode.value == "repaint"
        strength_row.visible = mode.value == "cover"
        track.visible = mode.value in {"lego", "extract"}
        complete_tracks.visible = mode.value == "complete"
        selected_model = studio.runtime.selected_models()[0]
        warning.value = (
            "This mode requires a Base model selected in Settings."
            if mode.value in {"lego", "extract", "complete"} and "base" not in selected_model
            else ""
        )
        for key, card in mode_cards.items():
            selected = key == mode.value
            card.border = ft.Border.all(1, GREEN if selected else BORDER)
            card.bgcolor = "#17211A" if selected else RAISED
        studio.page.update()

    async def submit(_event: ft.Event) -> None:
        nonlocal cancel_event
        try:
            request = EditRequest(
                source_audio=source.value,
                task_type=mode.value,
                prompt=prompt.value,
                lyrics=lyrics.value,
                repaint_start=float(start.value),
                repaint_end=float(end.value),
                cover_strength=float(strength.value),
                track_name=track.value,
                track_classes=[box.label.lower().replace(" ", "_") for box in track_checks if box.value],
                parent_id=library.value,
            )
            request.validate()
        except (TypeError, ValueError) as exc:
            studio.notice(str(exc), True)
            return
        cancel_event = Event()
        run.disabled = True
        stop.visible = True
        progress.value = None
        status.value = "Submitting edit…"
        studio.page.update()
        loop = asyncio.get_running_loop()

        def update(value: dict) -> None:
            loop.call_soon_threadsafe(lambda: _paint_progress(value))

        def _paint_progress(value: dict) -> None:
            progress.value = value.get("progress")
            status.value = str(value.get("stage") or "Editing")
            studio.page.update()

        try:
            result = await asyncio.to_thread(studio.generation.edit, request, update, cancel_event)
            progress.value = 1
            status.value = f"Saved {len(result.audio_paths)} edited track(s)."
            result_status.value = f"{result.title} · saved to Library"
            studio.views.pop(1, None)
            studio.play_track(result.audio_paths[0], result.title)
        except Exception as exc:
            status.value = "Cancelled" if cancel_event.is_set() else str(exc)
            studio.notice(status.value, not cancel_event.is_set())
        finally:
            run.disabled = False
            stop.visible = False
            studio.page.update()

    async def cancel(_event: ft.Event) -> None:
        if cancel_event:
            cancel_event.set()
            await asyncio.to_thread(studio.runtime.stop)
            studio.generation.reset_client()

    library.on_select = select_library
    mode.on_change = sync_mode
    run.on_click = submit
    stop.on_click = cancel
    sync_mode()
    source_panel = studio.card(
        ft.Text("Source", size=17, weight=ft.FontWeight.W_600),
        ft.Container(
            ft.Row([ft.Icon(ft.Icons.AUDIO_FILE, color=MUTED, size=30), source, ft.Button("Choose WAV", on_click=choose)]),
            bgcolor="#0E1312",
            border=ft.Border.all(1, BORDER),
            border_radius=8,
            padding=12,
        ),
        ft.Row(
            [
                ft.Divider(color=BORDER, expand=True),
                ft.Text("Or choose from library", color=GREEN, size=12),
                ft.Divider(color=BORDER, expand=True),
            ]
        ),
        ft.Row([library]),
        ft.Text("Edit mode", size=15, weight=ft.FontWeight.W_600),
        mode,
        warning,
        padding=18,
        expand=True,
    )
    source_panel.expand = 5
    settings_panel = studio.card(
        ft.Text("Edit description", size=15, weight=ft.FontWeight.W_600),
        ft.Row([prompt]),
        ft.Text("Optional lyrics", size=15, weight=ft.FontWeight.W_600),
        ft.Row([lyrics]),
        ft.Divider(color=BORDER),
        ft.Text("Edit parameters", size=15, weight=ft.FontWeight.W_600),
        repaint_range,
        strength_row,
        ft.Row([track]),
        complete_tracks,
        ft.Divider(color=BORDER),
        ft.Row([ft.Text("Status", weight=ft.FontWeight.W_600), ft.Container(expand=True), status]),
        progress,
        ft.Row([ft.Container(expand=True), stop, run]),
        ft.Divider(color=BORDER),
        ft.Row(
            [
                ft.Column([ft.Text("Result", weight=ft.FontWeight.W_600), result_status], spacing=3),
                ft.Container(expand=True),
                ft.Button("Saved automatically", icon=ft.Icons.SAVE_ALT, disabled=True),
            ]
        ),
        padding=18,
        expand=True,
    )
    settings_panel.expand = 7
    return ft.Column(
        [
            studio.heading("Edit a track", "Transform, rearrange, or extend an existing WAV with ACE-Step."),
            ft.Row(
                [source_panel, settings_panel],
                spacing=18,
                vertical_alignment=ft.CrossAxisAlignment.START,
            ),
        ],
        spacing=18,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
