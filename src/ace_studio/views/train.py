from __future__ import annotations

import asyncio
from pathlib import Path

import flet as ft
import flet.canvas as cv

from ..models import TrainingRequest
from ..theme import BORDER, GREEN, MUTED, RAISED


def build(studio) -> ft.Control:
    picker = ft.FilePicker()
    studio.page.services.append(picker)
    folder = ft.TextField(label="Audio dataset folder", read_only=True, expand=True)
    name = ft.TextField(label="Dataset name", value="my-adapter", expand=True)
    tag = ft.TextField(label="Activation tag (optional)", expand=True)
    instrumental = ft.Checkbox(label="All tracks are instrumental", value=True)
    samples = ft.Column(height=150, scroll=ft.ScrollMode.AUTO, visible=False)
    dataset_path: Path | None = None
    tensor_dir: Path | None = None
    status = ft.Text("Choose a folder containing training audio.")
    progress = ft.ProgressBar(value=0, color=GREEN, bgcolor="#34403B")
    kind = ft.Dropdown(
        label="Adapter",
        value="lora",
        options=[ft.DropdownOption(key="lora", text="LoRA"), ft.DropdownOption(key="lokr", text="LoKr")],
        expand=True,
    )
    epochs = ft.TextField(label="Epochs", value="10", width=140)
    learning_rate = ft.TextField(label="Learning rate", value="0.0001", width=180)
    rank = ft.TextField(label="Rank / dimension", value="64", width=160)
    alpha = ft.TextField(label="Alpha", value="128", width=120)
    dropout = ft.TextField(label="Dropout", value="0.1", width=120)
    lokr_factor = ft.TextField(label="LoKr factor (-1 = auto)", value="-1", width=180, visible=False)
    batch_size = ft.TextField(label="Batch size", value="1", width=120)
    accumulation = ft.TextField(label="Gradient accumulation", value="4", width=190)
    save_every = ft.TextField(label="Save every (epochs)", value="5", width=180)
    shift = ft.TextField(label="Training shift", value="3", width=150)
    seed = ft.TextField(label="Seed", value="42", width=120)
    checkpointing = ft.Checkbox(label="Gradient checkpointing", value=False)
    training_log = ft.Text("No training log yet.", selectable=True, max_lines=5, color=MUTED)
    start_button = ft.Button("Start training", icon=ft.Icons.SCIENCE, disabled=True, bgcolor=GREEN, color="#07140B")
    stop_button = ft.Button("Stop", icon=ft.Icons.STOP, visible=False)
    export_button = ft.Button("Export adapter", icon=ft.Icons.SAVE, visible=False)
    output_dir = ""
    _dit, selected_lm = studio.runtime.selected_models()
    auto_label_button = ft.Button(
        "Auto-label unlabeled",
        disabled=selected_lm is None,
        tooltip="Install and select a language model in Settings to auto-label tracks." if selected_lm is None else None,
    )
    loss_points: list[tuple[int, float]] = []
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
            value = max_loss * (1 - index / 4)
            shapes.extend([cv.Line(left, y, left + plot_width, y, grid), cv.Text(0, y - 6, f"{value:.2f}", style=muted)])
        total = max(int(epochs.value or 1), loss_points[-1][0] if loss_points else 1)
        shapes.extend(
            [
                cv.Text(left, height - 16, "0", style=muted),
                cv.Text(left + plot_width - 18, height - 16, str(total), style=muted),
            ]
        )
        if loss_points:
            coordinates = [
                (left + plot_width * epoch / total, top + plot_height * (1 - loss / max_loss)) for epoch, loss in loss_points
            ]
            line = ft.Paint(color=GREEN, stroke_width=2.5)
            dot = ft.Paint(color=GREEN)
            for (x1, y1), (x2, y2) in zip(coordinates, coordinates[1:], strict=False):
                shapes.append(cv.Line(x1, y1, x2, y2, line))
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

    def render_samples(found) -> None:
        samples.controls.clear()
        samples.visible = bool(found)
        for sample in found:

            async def edit(_event: ft.Event, item=sample) -> None:
                caption = ft.TextField(label="Caption", value=item.caption, multiline=True)
                genre = ft.TextField(label="Genre", value=item.genre)
                lyrics = ft.TextField(label="Lyrics", value=item.lyrics, multiline=True)
                bpm = ft.TextField(label="BPM", value=str(item.bpm or ""))
                key = ft.TextField(label="Key", value=item.keyscale)
                signature = ft.TextField(label="Time signature", value=item.timesignature)
                language = ft.TextField(label="Language", value=item.language)
                is_instrumental = ft.Checkbox(label="Instrumental", value=item.is_instrumental)

                async def save_sample(_save_event: ft.Event) -> None:
                    try:
                        item.caption = caption.value.strip()
                        item.genre = genre.value.strip()
                        item.lyrics = lyrics.value
                        item.bpm = int(bpm.value) if bpm.value.strip() else None
                        item.keyscale = key.value.strip()
                        item.timesignature = signature.value.strip()
                        item.language = language.value.strip() or "unknown"
                        item.is_instrumental = is_instrumental.value
                        updated = await asyncio.to_thread(studio.training.update_sample, item)
                        item.labeled = updated.labeled
                        studio.page.pop_dialog()
                        render_samples(found)
                        studio.page.update()
                    except (TypeError, ValueError) as exc:
                        studio.notice(str(exc), True)

                studio.page.show_dialog(
                    ft.AlertDialog(
                        modal=True,
                        title=ft.Text(item.filename),
                        content=ft.Column(
                            [caption, genre, lyrics, ft.Row([bpm, key, signature]), language, is_instrumental],
                            tight=True,
                            scroll=ft.ScrollMode.AUTO,
                        ),
                        actions=[
                            ft.TextButton("Cancel", on_click=lambda _e: studio.page.pop_dialog()),
                            ft.Button("Save", on_click=save_sample),
                        ],
                    )
                )

            samples.controls.append(
                ft.ListTile(
                    title=ft.Text(sample.filename),
                    subtitle=ft.Text(f"{sample.duration:.1f}s · {'ready' if sample.labeled else 'needs metadata'}"),
                    trailing=ft.IconButton(ft.Icons.EDIT, tooltip="Edit track metadata", on_click=edit),
                )
            )

    async def choose(_event: ft.Event) -> None:
        selected = await picker.get_directory_path(dialog_title="Choose training audio folder")
        if selected:
            folder.value = selected
            studio.page.update()

    async def scan(_event: ft.Event) -> None:
        nonlocal dataset_path
        if not folder.value or not name.value.strip():
            studio.notice("Choose a folder and enter a dataset name.", True)
            return
        status.value = "Scanning audio…"
        progress.value = None
        studio.page.update()
        try:
            found = await asyncio.to_thread(studio.training.scan, folder.value, name.value.strip(), tag.value.strip(), instrumental.value)
            render_samples(found)
            dataset_path = await asyncio.to_thread(studio.training.save, name.value.strip(), tag.value.strip(), instrumental.value)
            status.value = f"Found {len(found)} tracks. Dataset saved to {dataset_path}."
            progress.value = 1
        except Exception as exc:
            status.value = str(exc)
            progress.value = 0
            studio.notice(str(exc), True)
        studio.page.update()

    async def poll_task(task_kind: str, task_id: str) -> dict:
        while True:
            value = await asyncio.to_thread(studio.training.task_status, task_kind, task_id)
            current, total = value.get("current", 0), value.get("total", 0)
            progress.value = current / total if total else None
            status.value = str(value.get("progress") or value.get("status"))
            studio.page.update()
            if value.get("status") in {"completed", "failed"}:
                return value
            await asyncio.sleep(1)

    async def auto_label(_event: ft.Event) -> None:
        if not dataset_path:
            studio.notice("Scan and save a dataset first.", True)
            return
        try:
            task_id = await asyncio.to_thread(studio.training.auto_label, dataset_path)
            result = await poll_task("label", task_id)
            if result.get("status") == "failed":
                raise RuntimeError(result.get("error") or "Auto-labeling failed")
            status.value = "Auto-labeling complete. Review metadata in the saved dataset JSON."
        except Exception as exc:
            studio.notice(str(exc), True)
        studio.page.update()

    async def preprocess(_event: ft.Event) -> None:
        nonlocal tensor_dir
        if not dataset_path:
            studio.notice("Scan and save a dataset first.", True)
            return
        try:
            task_id, tensor_dir = await asyncio.to_thread(studio.training.preprocess, name.value.strip())
            result = await poll_task("preprocess", task_id)
            if result.get("status") == "failed":
                raise RuntimeError(result.get("error") or "Preprocessing failed")
            status.value = f"Tensors ready in {tensor_dir}."
            start_button.disabled = False
        except Exception as exc:
            studio.notice(str(exc), True)
        studio.page.update()

    def sync_kind(_event: ft.Event | None = None) -> None:
        epochs.value = "10" if kind.value == "lora" else "500"
        learning_rate.value = "0.0001" if kind.value == "lora" else "0.03"
        dropout.visible = kind.value == "lora"
        lokr_factor.visible = kind.value == "lokr"
        studio.page.update()

    async def train(_event: ft.Event) -> None:
        nonlocal output_dir
        if not tensor_dir:
            return
        output_dir = str(studio.storage.training_dir / "runs" / name.value.strip())
        try:
            loss_points.clear()
            current_loss.value = "—"
            best_loss.value = "—"
            epoch_value.value = f"0 / {epochs.value}"
            draw_loss_chart()
            request = TrainingRequest(
                kind.value,
                str(tensor_dir),
                output_dir,
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
            await asyncio.to_thread(studio.training.start, request)
            start_button.disabled = True
            stop_button.visible = True
            while True:
                value = await asyncio.to_thread(studio.training.status)
                status.value = str(value.get("status", "Training"))
                total = value.get("config", {}).get("epochs") or value.get("config", {}).get("train_epochs") or int(epochs.value)
                epoch = int(value.get("current_epoch", 0))
                progress.value = min(1, epoch / total)
                epoch_value.value = f"{epoch} / {total}"
                loss = value.get("loss")
                if loss is None:
                    loss = value.get("current_loss")
                if loss is not None:
                    loss = float(loss)
                    if loss_points and loss_points[-1][0] == epoch:
                        loss_points[-1] = (epoch, loss)
                    else:
                        loss_points.append((epoch, loss))
                    current_loss.value = f"{loss:.4f}"
                    best_loss.value = f"{min(point[1] for point in loss_points):.4f}"
                    draw_loss_chart()
                logs = value.get("logs") or value.get("log") or []
                if isinstance(logs, list):
                    logs = "\n".join(str(line) for line in logs[-8:])
                training_log.value = str(logs) or "Training in progress…"
                studio.page.update()
                if not value.get("is_training"):
                    if value.get("error"):
                        raise RuntimeError(value["error"])
                    break
                await asyncio.sleep(1)
            export_button.visible = True
            status.value = "Training complete. Export the adapter to register it."
        except Exception as exc:
            studio.notice(str(exc), True)
        finally:
            start_button.disabled = False
            stop_button.visible = False
            studio.page.update()

    async def stop(_event: ft.Event) -> None:
        await asyncio.to_thread(studio.training.stop)
        status.value = "Stopping training…"
        studio.page.update()

    async def export(_event: ft.Event) -> None:
        try:
            path = await asyncio.to_thread(studio.training.export, name.value.strip(), kind.value, output_dir)
            export_button.visible = False
            status.value = f"Adapter registered at {path}."
            studio.notice("Adapter exported. Load it from Settings.")
        except Exception as exc:
            studio.notice(str(exc), True)
        studio.page.update()

    kind.on_select = sync_kind
    start_button.on_click = train
    stop_button.on_click = stop
    export_button.on_click = export
    auto_label_button.on_click = auto_label
    def metric(label: str, value: ft.Text) -> ft.Container:
        return ft.Container(
            ft.Column([ft.Text(label, size=12, color=MUTED), value], spacing=4),
            bgcolor=RAISED,
            border=ft.Border.all(1, BORDER),
            border_radius=10,
            padding=14,
            expand=True,
        )
    return ft.Column(
        [
            studio.heading("Train an adapter", "Prepare a raw-audio dataset and train LoRA or LoKr locally."),
            ft.Row(
                [
                    ft.Column(
                        [
                            studio.card(
                                ft.Row(
                                    [
                                        ft.Icon(ft.Icons.FOLDER_OPEN, color=GREEN),
                                        ft.Text("1 · Dataset", size=18, weight=ft.FontWeight.W_600),
                                    ]
                                ),
                                ft.Row([folder, ft.Button("Choose folder", on_click=choose)]),
                                ft.Row([name, tag]),
                                instrumental,
                                ft.Row([ft.Button("Scan & save", on_click=scan), auto_label_button]),
                                samples,
                                padding=18,
                            ),
                            studio.card(
                                ft.Row(
                                    [
                                        ft.Icon(ft.Icons.TUNE, color=GREEN),
                                        ft.Text("2 · Preprocess & train", size=18, weight=ft.FontWeight.W_600),
                                    ]
                                ),
                                ft.Row([kind, ft.Button("Preprocess tensors", on_click=preprocess)]),
                                ft.Row([epochs, learning_rate]),
                                ft.ExpansionTile(
                                    title=ft.Text("Advanced training controls", size=14),
                                    controls=[
                                        ft.Container(
                                            ft.Column(
                                                [
                                                    ft.Row([rank, alpha, dropout, lokr_factor], wrap=True),
                                                    ft.Row([batch_size, accumulation, save_every], wrap=True),
                                                    ft.Row([shift, seed, checkpointing], wrap=True),
                                                ],
                                                spacing=12,
                                            ),
                                            padding=ft.Padding.only(bottom=12),
                                        )
                                    ],
                                ),
                            ),
                        ],
                        spacing=16,
                        expand=True,
                    ),
                    studio.card(
                        ft.Row(
                            [
                                ft.Icon(ft.Icons.QUERY_STATS, color=GREEN),
                                ft.Text("Training status", size=18, weight=ft.FontWeight.W_600),
                            ]
                        ),
                        ft.Row([status, ft.Container(expand=True), ft.Text("Progress", color=MUTED)]),
                        progress,
                        ft.Row(
                            [metric("Current loss", current_loss), metric("Best loss", best_loss), metric("Epoch", epoch_value)],
                            spacing=10,
                        ),
                        ft.Container(
                            ft.Column([ft.Text("Training loss", weight=ft.FontWeight.W_600), loss_canvas], spacing=8),
                            bgcolor="#0E1312",
                            border=ft.Border.all(1, BORDER),
                            border_radius=10,
                            padding=14,
                        ),
                        ft.ExpansionTile(title=ft.Text("Training log", size=14), controls=[ft.Container(training_log, padding=12)]),
                        ft.Row([export_button, ft.Container(expand=True), stop_button, start_button]),
                        padding=18,
                        expand=True,
                    ),
                ],
                spacing=16,
                vertical_alignment=ft.CrossAxisAlignment.START,
                expand=True,
            ),
        ],
        spacing=18,
        scroll=ft.ScrollMode.AUTO,
        expand=True,
    )
