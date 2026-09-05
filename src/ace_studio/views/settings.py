from __future__ import annotations

import asyncio

import flet as ft

from ..hardware import recommended_models
from ..models import LMMode, MemoryMode, MemorySettings
from ..runtime import DIT_MODELS, LM_MODELS, SUPPORTED_COMMIT
from ..theme import BORDER, FIELD_STYLE, GREEN, MUTED, PRIMARY_BUTTON_STYLE, RAISED, WARNING


def build(studio) -> ft.AlertDialog:
    report = studio.runtime.hardware
    manifest = studio.runtime.current_manifest()
    recommended_dit, recommended_lm = recommended_models(report)
    selected_dit, selected_lm = studio.runtime.selected_models()
    installed_dit = [name for name in DIT_MODELS if studio.runtime.model_installed(name)]
    installed_lm = [name for name in LM_MODELS if studio.runtime.model_installed(name)]
    dit = ft.Dropdown(
        label="Generation model",
        value=selected_dit,
        options=[ft.DropdownOption(key=name, text=name) for name in (installed_dit or [selected_dit])],
        **FIELD_STYLE,
    )
    lm = ft.Dropdown(
        label="Language model",
        value=selected_lm or "disabled",
        options=[ft.DropdownOption(key="disabled", text="Disabled")] + [ft.DropdownOption(key=name, text=name) for name in installed_lm],
        **FIELD_STYLE,
    )

    memory = studio.runtime.get_memory_settings()
    memory_preset = ft.Dropdown(
        label="Memory preset",
        value=memory.mode.value,
        options=[ft.DropdownOption(key=mode.value, text=mode.value.capitalize()) for mode in MemoryMode],
        **FIELD_STYLE,
    )
    memory_lm = ft.Dropdown(
        label="Language model memory",
        value=memory.lm_mode.value,
        options=[ft.DropdownOption(key=lm.value, text=lm.value.replace("-", " ").title()) for lm in LMMode],
        **FIELD_STYLE,
    )
    memory_versions = ft.Dropdown(
        label="Max versions",
        value=str(memory.max_versions),
        options=[ft.DropdownOption(key=str(x), text=str(x)) for x in range(1, 5)],
        width=100,
        **FIELD_STYLE,
    )
    memory_duration = ft.TextField(
        label="Max duration (s)",
        value=str(memory.max_duration_sec) if memory.max_duration_sec else "",
        hint_text="No limit",
        width=130,
        keyboard_type=ft.KeyboardType.NUMBER,
        **FIELD_STYLE,
    )
    memory_ckpt = ft.Switch(label="Gradient checkpointing (training)", value=memory.training_checkpointing, active_color=GREEN)
    memory_train_batch = ft.Dropdown(
        label="Training batch",
        value=str(memory.training_max_batch),
        options=[ft.DropdownOption(key=str(x), text=str(x)) for x in range(1, 5)],
        width=100,
        **FIELD_STYLE,
    )
    memory_train_rank = ft.Dropdown(
        label="Max rank",
        value=str(memory.training_max_rank),
        options=[ft.DropdownOption(key=str(x), text=str(x)) for x in (16, 32, 64, 128, 256)],
        width=100,
        **FIELD_STYLE,
    )
    memory_train_alpha = ft.Dropdown(
        label="Max alpha",
        value=str(memory.training_max_alpha),
        options=[ft.DropdownOption(key=str(x), text=str(x)) for x in (32, 64, 128, 256, 512)],
        width=100,
        **FIELD_STYLE,
    )
    advanced_memory = ft.ExpansionTile(
        title=ft.Text("Advanced memory overrides", size=14),
        controls=[
            ft.Container(
                ft.Column(
                    [
                        memory_lm,
                        ft.Row([memory_versions, memory_duration], wrap=True),
                        ft.Divider(color=BORDER),
                        memory_ckpt,
                        ft.Row([memory_train_batch, memory_train_rank, memory_train_alpha], wrap=True),
                    ],
                    spacing=12,
                ),
                padding=ft.Padding.only(bottom=12),
            )
        ],
        bgcolor=RAISED,
        collapsed_bgcolor=RAISED,
        shape=ft.RoundedRectangleBorder(radius=8),
        collapsed_shape=ft.RoundedRectangleBorder(radius=8),
    )

    def close(_event: ft.Event) -> None:
        studio.page.pop_dialog()

    def save(_event: ft.Event) -> None:
        selected = [dit.value, None if lm.value == "disabled" else lm.value]
        missing = [name for name in selected if name and not studio.runtime.model_installed(name)]
        if missing:
            studio.notice(f"Download {missing[0]} before selecting it.", True)
            return
        studio.runtime.select_models(*selected)
        studio.runtime.stop()
        studio.generation.reset_client()
        studio.client = None
        studio.page.pop_dialog()
        studio.notice("Model selection saved. It will load on the next request.")

    def save_memory(_event: ft.Event) -> None:
        duration_value = memory_duration.value.strip()
        max_duration = None
        if duration_value:
            try:
                max_duration = max(30, min(600, int(duration_value)))
            except ValueError:
                studio.notice("Duration must be a number.", True)
                return
        settings = MemorySettings(
            mode=MemoryMode(memory_preset.value),
            lm_mode=LMMode(memory_lm.value),
            max_versions=max(1, min(4, int(memory_versions.value))),
            max_duration_sec=max_duration,
            training_checkpointing=memory_ckpt.value,
            training_max_batch=max(1, min(4, int(memory_train_batch.value))),
            training_max_rank=max(1, min(256, int(memory_train_rank.value))),
            training_max_alpha=max(1, min(512, int(memory_train_alpha.value))),
        )
        studio.runtime.save_memory_settings(settings)
        studio.runtime.stop()
        studio.generation.reset_client()
        studio.client = None
        studio.page.pop_dialog()
        studio.notice("Memory settings saved. They will apply on the next generation.")

    async def update(_event: ft.Event) -> None:
        studio.notice("Checking and staging the latest ACE-Step runtime…")
        try:
            await asyncio.to_thread(studio.runtime.install_latest)
            studio.notice("ACE-Step is up to date. Compatibility probe passed.")
        except Exception as exc:
            studio.notice(str(exc), True)

    async def download(name: str, button: ft.Button, detail: ft.Text) -> None:
        button.disabled = True
        button.content = "Downloading…"
        studio.page.update()
        loop = asyncio.get_running_loop()

        def progress(message: str, _value: float | None) -> None:
            loop.call_soon_threadsafe(lambda: (setattr(detail, "value", message[-100:]), studio.page.update()))

        try:
            await asyncio.to_thread(studio.runtime.download_model, name, progress)
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
        studio.page.update()

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
        installed = studio.runtime.model_installed(name)
        detail = ft.Text(descriptions.get(name, "Supported ACE-Step model"), color=MUTED, size=11)
        button = ft.Button(
            "Installed" if installed else "Download", icon=ft.Icons.CHECK if installed else ft.Icons.DOWNLOAD, disabled=installed
        )
        button.on_click = lambda _e, n=name, b=button, d=detail: studio.page.run_task(download, n, b, d)
        model_rows.append(ft.ListTile(title=ft.Text(name), subtitle=detail, trailing=button))

    adapter_rows: list[ft.Control] = []
    for adapter in studio.storage.adapters():
        scale = ft.Dropdown(
            value=str(adapter.scale),
            width=100,
            options=[ft.DropdownOption(key=str(value), text=str(value)) for value in (0.25, 0.5, 0.75, 1.0)],
            **FIELD_STYLE,
        )

        async def activate(_event: ft.Event, adapter_id=adapter.id, selected_scale=scale) -> None:
            try:
                await asyncio.to_thread(studio.training.activate, adapter_id, True, float(selected_scale.value))
                studio.notice("Adapter loaded for generation.")
                studio.page.pop_dialog()
                studio.page.show_dialog(studio.settings_dialog())
            except Exception as exc:
                studio.notice(str(exc), True)

        async def unload(_event: ft.Event) -> None:
            try:
                await asyncio.to_thread(studio.training.deactivate)
                studio.notice("Adapter unloaded.")
                studio.page.pop_dialog()
                studio.page.show_dialog(studio.settings_dialog())
            except Exception as exc:
                studio.notice(str(exc), True)

        async def change_scale(_event: ft.Event, adapter_id=adapter.id, selected_scale=scale, is_active=adapter.active) -> None:
            if not is_active:
                return
            try:
                await asyncio.to_thread(studio.training.activate, adapter_id, True, float(selected_scale.value))
                studio.notice("Adapter scale updated.")
            except Exception as exc:
                studio.notice(str(exc), True)

        def delete_adapter(_event: ft.Event, adapter_id=adapter.id) -> None:
            studio.storage.delete_adapter(adapter_id)
            studio.page.pop_dialog()
            studio.page.show_dialog(studio.settings_dialog())

        def rename_adapter(_event: ft.Event, adapter_id=adapter.id, current_name=adapter.name) -> None:
            new_name = ft.TextField(label="Adapter name", value=current_name, autofocus=True, **FIELD_STYLE)

            def save_name(_save_event: ft.Event) -> None:
                if not new_name.value.strip():
                    studio.notice("Adapter name cannot be empty.", True)
                    return
                studio.storage.update_adapter(adapter_id, name=new_name.value.strip())
                studio.page.pop_dialog()
                studio.page.pop_dialog()
                studio.page.show_dialog(studio.settings_dialog())

            studio.page.show_dialog(
                ft.AlertDialog(
                    modal=True,
                    title=ft.Text("Rename adapter"),
                    content=new_name,
                    actions=[
                        ft.TextButton("Cancel", on_click=lambda _e: studio.page.pop_dialog()),
                        ft.Button("Save", style=PRIMARY_BUTTON_STYLE, on_click=save_name),
                    ],
                )
            )

        scale.on_select = change_scale

        adapter_rows.append(
            ft.ListTile(
                title=ft.Text(adapter.name),
                subtitle=ft.Text(f"{adapter.kind.upper()} · {adapter.path}"),
                leading=ft.Icon(ft.Icons.CHECK_CIRCLE if adapter.active else ft.Icons.TUNE, color=GREEN if adapter.active else MUTED),
                trailing=ft.Row(
                    [
                        scale,
                        ft.Button("Unload" if adapter.active else "Load", on_click=unload if adapter.active else activate),
                        ft.IconButton(ft.Icons.EDIT, tooltip="Rename adapter", on_click=rename_adapter),
                        ft.IconButton(ft.Icons.DELETE_OUTLINE, tooltip="Remove adapter from ACE Studio", on_click=delete_adapter),
                    ],
                    tight=True,
                ),
            )
        )

    recommended_missing = any(name and not studio.runtime.model_installed(name) for name in (recommended_dit, recommended_lm))

    content = ft.ListView(
        [
            studio.heading("Settings", "Models, runtime, and storage."),
            ft.Text("Models & runtime", size=20, weight=ft.FontWeight.W_600),
            ft.ResponsiveRow(
                [
                    ft.Container(
                        studio.card(
                            ft.Icon(ft.Icons.MEMORY, color=GREEN, size=36),
                            ft.Text("Hardware", size=20, weight=ft.FontWeight.W_600),
                            ft.Text(report.summary),
                            ft.Text(report.profile.value, color=MUTED),
                            expand=True,
                        ),
                        col={"sm": 12, "lg": 6},
                    ),
                    ft.Container(
                        studio.card(
                            ft.Icon(ft.Icons.SYSTEM_UPDATE, color=GREEN, size=36),
                            ft.Text("ACE-Step 1.5", size=20, weight=ft.FontWeight.W_600),
                            ft.Text(f"Supported commit {SUPPORTED_COMMIT[:10]}"),
                            ft.Text(f"Installed {(manifest.commit[:10] if manifest else 'not installed')}", color=MUTED),
                            ft.Button("Reinstall supported runtime", on_click=update),
                            expand=True,
                        ),
                        col={"sm": 12, "lg": 6},
                    ),
                ],
                spacing=16,
                run_spacing=16,
            ),
            studio.card(
                ft.Text("Active models", size=20, weight=ft.FontWeight.W_600),
                ft.Text(
                    f"Recommended for this hardware: {recommended_dit} + {recommended_lm or 'no language model'}"
                    + (" · download required" if recommended_missing else ""),
                    color=GREEN,
                    size=12,
                ),
                dit,
                lm,
                ft.Button("Save selection", icon=ft.Icons.SAVE, style=PRIMARY_BUTTON_STYLE, on_click=save),
            ),
            studio.card(
                ft.Text("Memory safety", size=20, weight=ft.FontWeight.W_600),
                ft.Text(
                    "Preset adapts to detected hardware. Use Full only on machines with sufficient RAM."
                    + (" Current mode may freeze low-memory machines." if memory.mode == MemoryMode.FULL else ""),
                    color=MUTED if memory.mode != MemoryMode.FULL else WARNING,
                    size=12,
                ),
                ft.Row(
                    [
                        ft.Icon(
                            ft.Icons.SHIELD,
                            color=GREEN if memory.mode == MemoryMode.SAFE else (WARNING if memory.mode == MemoryMode.FULL else MUTED),
                        ),
                        memory_preset,
                        ft.Container(expand=True),
                        ft.Button("Save memory settings", icon=ft.Icons.SAVE, style=PRIMARY_BUTTON_STYLE, on_click=save_memory),
                    ],
                    spacing=12,
                ),
                advanced_memory,
            ),
            studio.card(ft.Text("Available models", size=20, weight=ft.FontWeight.W_600), *model_rows),
            studio.card(
                ft.Text("Adapters", size=20, weight=ft.FontWeight.W_600),
                *(adapter_rows or [ft.Text("Train and export an adapter to use it here.", color=MUTED)]),
            ),
            studio.card(
                ft.Text("Storage", size=20, weight=ft.FontWeight.W_600),
                ft.ListTile(
                    leading=ft.Icon(ft.Icons.FOLDER),
                    title=ft.Text(str(studio.storage.root)),
                    subtitle=ft.Text("Runtime, models, library, training data, and logs"),
                ),
            ),
            studio.card(
                ft.Text("About", size=20, weight=ft.FontWeight.W_600),
                ft.Text("ACE Studio 0.1.14"),
                ft.Text("ACE-Step is installed from its official upstream repository and keeps its own license files.", color=MUTED),
            ),
        ],
        spacing=18,
        width=780,
        height=560,
    )
    return ft.AlertDialog(modal=True, content=content, actions=[ft.TextButton("Close", on_click=close)])
