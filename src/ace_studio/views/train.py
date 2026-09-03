from __future__ import annotations

import asyncio
from pathlib import Path
from threading import Event

import flet as ft
import flet.canvas as cv

from ..models import TrainingRequest
from ..theme import BORDER, DANGER_BUTTON_STYLE, FIELD_STYLE, GREEN, INPUT, MUTED, PRIMARY_BUTTON_STYLE, RAISED


def build(studio) -> ft.Control:
    picker = ft.FilePicker()
    studio.page.services.append(picker)
    folder = ft.TextField(label="Audio dataset folder", read_only=True, expand=True, **FIELD_STYLE)
    name = ft.TextField(label="Adapter name", value="my-adapter", expand=True, **FIELD_STYLE)
    instrumental = ft.Checkbox(label="All tracks are instrumental", value=True)
    tag = ft.TextField(label="Activation tag (optional)", expand=True, **FIELD_STYLE)
    kind = ft.Dropdown(
        label="Adapter type",
        value="lora",
        options=[ft.DropdownOption(key="lora", text="LoRA"), ft.DropdownOption(key="lokr", text="LoKr")],
        expand=True,
        **FIELD_STYLE,
    )
    epochs = ft.TextField(label="Epochs", value="10", width=140, **FIELD_STYLE)
    learning_rate = ft.TextField(label="Learning rate", value="0.0001", width=180, **FIELD_STYLE)
    rank = ft.TextField(label="Rank / dimension", value="64", width=160, **FIELD_STYLE)
    alpha = ft.TextField(label="Alpha", value="128", width=120, **FIELD_STYLE)
    dropout = ft.TextField(label="Dropout", value="0.1", width=120, **FIELD_STYLE)
    lokr_factor = ft.TextField(label="LoKr factor (-1 = auto)", value="-1", width=180, visible=False, **FIELD_STYLE)
    batch_size = ft.TextField(label="Batch size", value="1", width=120, **FIELD_STYLE)
    accumulation = ft.TextField(label="Gradient accumulation", value="4", width=190, **FIELD_STYLE)
    save_every = ft.TextField(label="Save every (epochs)", value="5", width=180, **FIELD_STYLE)
    shift = ft.TextField(label="Training shift", value="3", width=150, **FIELD_STYLE)
    seed = ft.TextField(label="Seed", value="42", width=120, **FIELD_STYLE)
    checkpointing = ft.Checkbox(label="Gradient checkpointing", value=False)
    status = ft.Text("Choose a folder to prepare and train an adapter.")
    progress = ft.ProgressBar(value=0)
    start_button = ft.Button("Train adapter", icon=ft.Icons.SCIENCE, disabled=True, style=PRIMARY_BUTTON_STYLE)
    stop_button = ft.Button("Stop training", icon=ft.Icons.STOP, visible=False, style=DANGER_BUTTON_STYLE)
    review = ft.Column(visible=False, spacing=4)
    training_log = ft.Text("No training log yet.", selectable=True, max_lines=5, color=MUTED)
    loss_points: list[tuple[int, float]] = []
    cancel_event: Event | None = None
    current_loss = ft.Text("—", size=22, weight=ft.FontWeight.W_600)
    best_loss = ft.Text("—", size=22, weight=ft.FontWeight.W_600)
    epoch_value = ft.Text("0 / 0", size=22, weight=ft.FontWeight.W_600)
    loss_canvas = cv.Canvas(height=150, expand=True)

    def draw_loss_chart(width: float = 560, height: float = 150) -> None:
        left, right, top, bottom = 42, 12, 10, 26
        plot_width = max(1, width - left - right)
        plot_height = max(1, height - top - bottom)
        grid = ft.Paint(color=BORDER, stroke_width=1)
        muted = ft.TextStyle(size=10, color=MUTED)
        shapes: list[cv.Shape] = []
        max_loss = max((loss for _, loss in loss_points), default=1.0)
        max_loss = max(0.1, max_loss * 1.1)
        for index in range(5):
            y = top + plot_height * index / 4
            shapes.extend(
                [cv.Line(left, y, left + plot_width, y, grid), cv.Text(0, y - 6, f"{max_loss * (1 - index / 4):.2f}", style=muted)]
            )
        total = max(int(epochs.value or 1), loss_points[-1][0] if loss_points else 1)
        shapes.extend([cv.Text(left, height - 16, "0", style=muted), cv.Text(left + plot_width - 18, height - 16, str(total), style=muted)])
        if loss_points:
            coordinates = [(left + plot_width * epoch / total, top + plot_height * (1 - loss / max_loss)) for epoch, loss in loss_points]
            line, dot = ft.Paint(color=GREEN, stroke_width=2.5), ft.Paint(color=GREEN)
            shapes.extend(cv.Line(x1, y1, x2, y2, line) for (x1, y1), (x2, y2) in zip(coordinates, coordinates[1:], strict=False))
            shapes.extend(cv.Circle(x, y, 3, dot) for x, y in coordinates)
        else:
            shapes.append(
                cv.Text(left + 12, top + plot_height / 2, "Loss will appear when training starts", style=ft.TextStyle(color=MUTED))
            )
        loss_canvas.shapes = shapes

    def resize_loss_chart(event: cv.CanvasResizeEvent) -> None:
        draw_loss_chart(event.width, event.height)
        studio.page.update()

    loss_canvas.on_resize = resize_loss_chart
    draw_loss_chart()

    def render_review(samples) -> None:
        review.controls.clear()
        review.visible = bool(samples)
        for sample in samples:

            async def edit(_event: ft.Event, item=sample) -> None:
                caption = ft.TextField(label="Caption", value=item.caption, multiline=True, **FIELD_STYLE)
                genre = ft.TextField(label="Genre", value=item.genre, **FIELD_STYLE)
                lyrics = ft.TextField(label="Lyrics", value=item.lyrics, multiline=True, **FIELD_STYLE)
                instrumental_sample = ft.Checkbox(label="Instrumental", value=item.is_instrumental)

                async def save(_save_event: ft.Event) -> None:
                    item.caption = caption.value.strip()
                    item.genre = genre.value.strip()
                    item.lyrics = lyrics.value
                    item.is_instrumental = instrumental_sample.value
                    try:
                        updated = await asyncio.to_thread(studio.training.update_sample, item)
                    except Exception as exc:
                        studio.notice(str(exc), True)
                        return
                    item.labeled = updated.labeled
                    studio.page.pop_dialog()
                    render_review(samples)
                    studio.page.update()

                studio.page.show_dialog(
                    ft.AlertDialog(
                        modal=True,
                        title=ft.Text(item.filename),
                        content=ft.Column([caption, genre, lyrics, instrumental_sample], tight=True, scroll=ft.ScrollMode.AUTO),
                        actions=[
                            ft.TextButton("Cancel", on_click=lambda _e: studio.page.pop_dialog()),
                            ft.Button("Save", icon=ft.Icons.SAVE, style=PRIMARY_BUTTON_STYLE, on_click=save),
                        ],
                    )
                )

            review.controls.append(
                ft.ListTile(
                    title=ft.Text(sample.filename),
                    subtitle=ft.Text(f"{sample.duration:.1f}s · {'ready' if sample.labeled else 'metadata may need review'}"),
                    trailing=ft.IconButton(ft.Icons.EDIT, tooltip="Edit track metadata", on_click=edit),
                )
            )

    def sync_kind(_event: ft.Event | None = None) -> None:
        epochs.value = "10" if kind.value == "lora" else "500"
        learning_rate.value = "0.0001" if kind.value == "lora" else "0.03"
        dropout.visible = kind.value == "lora"
        lokr_factor.visible = kind.value == "lokr"
        studio.page.update()

    async def choose(_event: ft.Event) -> None:
        selected = await picker.get_directory_path(dialog_title="Choose training audio folder")
        if selected:
            folder.value = selected
            name.value = Path(selected).name or name.value
            start_button.disabled = False
            studio.page.update()

    def paint(update: dict) -> None:
        stage = str(update.get("stage") or "Training")
        status.value = str(update.get("error") or update.get("status") or update.get("progress_text") or stage)
        stop_button.visible = stage == "Training"
        if stage == "Dataset saved" and update.get("samples_data"):
            render_review(update["samples_data"])
        if stage == "Training":
            total = int(update.get("config", {}).get("epochs") or update.get("config", {}).get("train_epochs") or epochs.value)
            epoch = int(update.get("current_epoch", 0))
            epoch_value.value = f"{epoch} / {total}"
            progress.value = min(1, epoch / total) if total else None
            loss = update.get("loss", update.get("current_loss"))
            if loss is not None:
                point = (epoch, float(loss))
                if loss_points and loss_points[-1][0] == epoch:
                    loss_points[-1] = point
                else:
                    loss_points.append(point)
                current_loss.value = f"{point[1]:.4f}"
                best_loss.value = f"{min(value for _, value in loss_points):.4f}"
                draw_loss_chart()
            logs = update.get("logs") or update.get("log") or []
            training_log.value = (
                "\n".join(str(line) for line in logs[-8:]) if isinstance(logs, list) else str(logs or "Training in progress…")
            )
        elif isinstance(update.get("progress"), (int, float)):
            progress.value = float(update["progress"])
        studio.page.update()

    async def train(_event: ft.Event) -> None:
        nonlocal cancel_event
        if not folder.value or not name.value.strip():
            studio.notice("Choose a folder and enter an adapter name.", True)
            return
        try:
            request = TrainingRequest(
                kind.value,
                "",
                str(studio.storage.training_dir / "runs" / name.value.strip()),
                float(learning_rate.value),
                int(epochs.value),
                rank=int(rank.value),
                alpha=int(alpha.value),
                dropout=float(dropout.value),
                batch_size=int(batch_size.value),
                gradient_accumulation=int(accumulation.value),
                save_every=int(save_every.value),
                training_shift=float(shift.value),
                seed=int(seed.value),
                gradient_checkpointing=checkpointing.value,
                lokr_factor=int(lokr_factor.value),
            )
        except (TypeError, ValueError) as exc:
            studio.notice(str(exc), True)
            return
        cancel_event = Event()
        loss_points.clear()
        current_loss.value = best_loss.value = "—"
        epoch_value.value = f"0 / {epochs.value}"
        draw_loss_chart()
        start_button.disabled = True
        stop_button.visible = False
        progress.value = None
        status.value = "Preparing dataset…"
        studio.page.update()
        loop = asyncio.get_running_loop()
        try:
            destination = await asyncio.to_thread(
                studio.training.run_pipeline,
                folder.value,
                name.value.strip(),
                tag.value.strip(),
                instrumental.value,
                request,
                lambda update: loop.call_soon_threadsafe(paint, update),
                cancel_event,
            )
            progress.value = 1
            status.value = f"Adapter registered at {destination}. Load it from Settings when you are ready."
            start_button.content = "Train another adapter"
        except InterruptedError:
            status.value = "Training cancelled. No adapter was registered."
            start_button.content = "Retry training"
        except Exception as exc:
            status.value = str(exc)
            start_button.content = "Retry training"
            studio.notice(str(exc), True)
        finally:
            start_button.disabled = False
            stop_button.visible = False
            studio.page.update()

    async def stop(_event: ft.Event) -> None:
        if cancel_event:
            cancel_event.set()
            status.value = "Stopping training…"
            studio.page.update()

    kind.on_select = sync_kind
    start_button.on_click = train
    stop_button.on_click = stop

    def metric(label: str, value: ft.Text) -> ft.Container:
        return ft.Container(
            ft.Column([ft.Text(label, size=12, color=MUTED), value], spacing=4),
            bgcolor=RAISED,
            border=ft.Border.all(1, BORDER),
            border_radius=8,
            padding=12,
            expand=True,
        )

    return ft.Column(
        [
            studio.heading("Train an adapter", "Choose a folder and ACE Studio will prepare, train, and register a LoRA adapter."),
            ft.ResponsiveRow(
                [
                    ft.Container(
                        content=ft.Column(
                            [
                                studio.card(
                                    ft.Text("Dataset", size=17, weight=ft.FontWeight.W_600),
                                    ft.Row([folder, ft.Button("Choose folder", icon=ft.Icons.FOLDER_OPEN, on_click=choose)]),
                                    name,
                                    instrumental,
                                    ft.ExpansionTile(
                                        title=ft.Text("Advanced settings", size=14),
                                        controls=[
                                            ft.Container(
                                                ft.Column(
                                                    [
                                                        tag,
                                                        kind,
                                                        ft.Row([epochs, learning_rate], wrap=True),
                                                        ft.Row([rank, alpha, dropout, lokr_factor], wrap=True),
                                                        ft.Row([batch_size, accumulation, save_every], wrap=True),
                                                        ft.Row([shift, seed, checkpointing], wrap=True),
                                                        ft.ExpansionTile(
                                                            title=ft.Text("Review detected tracks", size=14), controls=[review]
                                                        ),
                                                    ],
                                                    spacing=12,
                                                ),
                                                padding=ft.Padding.only(bottom=12),
                                            )
                                        ],
                                    ),
                                    ft.Row([start_button, stop_button]),
                                    padding=18,
                                ),
                            ],
                            spacing=16,
                        ),
                        col={"sm": 12, "lg": 6},
                    ),
                    ft.Container(
                        content=studio.card(
                            ft.Text("Training status", size=17, weight=ft.FontWeight.W_600),
                            ft.Row([status, ft.Container(expand=True), ft.Text("Progress", color=MUTED)]),
                            progress,
                            ft.Row(
                                [metric("Current loss", current_loss), metric("Best loss", best_loss), metric("Epoch", epoch_value)],
                                spacing=10,
                            ),
                            ft.Container(
                                ft.Column([ft.Text("Training loss", weight=ft.FontWeight.W_600), loss_canvas], spacing=8),
                                bgcolor=INPUT,
                                border=ft.Border.all(1, BORDER),
                                border_radius=8,
                                padding=12,
                            ),
                            ft.ExpansionTile(title=ft.Text("Training log", size=14), controls=[ft.Container(training_log, padding=12)]),
                            padding=18,
                        ),
                        col={"sm": 12, "lg": 6},
                    ),
                ],
                spacing=16,
                run_spacing=16,
            ),
        ],
        spacing=18,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
