from __future__ import annotations

import asyncio

import flet as ft

from ..hardware import recommended_models
from ..theme import GREEN, MUTED


def show(studio) -> None:
    report = studio.runtime.hardware
    model, lm = recommended_models(report)
    progress = ft.ProgressBar(value=0, color=GREEN, bgcolor="#29302B")
    log = ft.Text("Ready to install", color=MUTED, selectable=True)
    button = ft.Button("Install ACE-Step", icon=ft.Icons.DOWNLOAD, bgcolor=GREEN, color="#07140B")

    async def install(_event: ft.Event) -> None:
        button.disabled = True
        progress.value = None
        log.value = "Preparing ACE-Step…"
        studio.page.update()
        loop = asyncio.get_running_loop()

        def update(message: str, value: float | None) -> None:
            def paint() -> None:
                log.value = message[-180:]
                progress.value = value
                studio.page.update()

            loop.call_soon_threadsafe(paint)

        try:
            await asyncio.to_thread(studio.runtime.install_recommended, update)
            studio.views.clear()
            studio.show_shell(0)
        except Exception as exc:
            button.disabled = False
            progress.value = 0
            log.value = str(exc)
            studio.page.update()

    button.on_click = install
    studio.page.clean()
    studio.page.add(
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
                                    ft.Row(
                                        [
                                            ft.Image(src="icon.png", width=44, height=44),
                                            ft.Text("ACE Studio", size=30, weight=ft.FontWeight.BOLD),
                                        ]
                                    ),
                                    ft.Text("Your music studio", size=42, weight=ft.FontWeight.BOLD),
                                    ft.Text("Install ACE-Step, choose a hardware profile, and start creating.", color=MUTED, size=16),
                                    studio.card(
                                        ft.Text("Hardware profile", size=20, weight=ft.FontWeight.W_600),
                                        ft.ListTile(
                                            leading=ft.Icon(ft.Icons.MEMORY, color=GREEN),
                                            title=ft.Text(report.summary),
                                            subtitle=ft.Text(report.profile.value),
                                        ),
                                        ft.ListTile(
                                            leading=ft.Icon(ft.Icons.MODEL_TRAINING, color=GREEN),
                                            title=ft.Text(model),
                                            subtitle=ft.Text(f"Language model: {lm or 'disabled for this profile'}"),
                                        ),
                                        ft.Text(
                                            "The first launch downloads ACE-Step, Python packages, and the recommended model. "
                                            "This can take several minutes and multiple gigabytes.",
                                            color=MUTED,
                                        ),
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
