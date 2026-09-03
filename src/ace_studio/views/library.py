from __future__ import annotations

import flet as ft

from ..theme import GREEN, MUTED, PANEL


def build(studio) -> ft.Control:
    search = ft.TextField(hint_text="Search your tracks", prefix_icon=ft.Icons.SEARCH, height=48)
    rows = ft.Column(spacing=8)

    def play(path: str, title: str) -> None:
        studio.play_track(path, title)

    def delete(generation_id: str, title: str) -> None:
        def cancel(_event: ft.Event) -> None:
            studio.page.pop_dialog()

        def confirm(_event: ft.Event) -> None:
            studio.storage.delete_generation(generation_id)
            studio.views.pop(0, None)
            studio.page.pop_dialog()
            load()
            studio.notice(f"Deleted {title}")

        studio.page.show_dialog(
            ft.AlertDialog(
                modal=True,
                title=ft.Text(f"Delete {title}?"),
                content=ft.Text("This permanently removes the track and its audio file."),
                actions=[
                    ft.TextButton("Cancel", on_click=cancel),
                    ft.Button("Delete", icon=ft.Icons.DELETE_OUTLINE, bgcolor="#8C2431", color="white", on_click=confirm),
                ],
            )
        )

    def load(_event: ft.Event | None = None) -> None:
        rows.controls.clear()
        for item in studio.storage.generations(search=search.value):
            rows.controls.append(
                ft.Container(
                    bgcolor=PANEL,
                    border_radius=10,
                    padding=12,
                    content=ft.Row(
                        [
                            ft.IconButton(
                                ft.Icons.PLAY_ARROW,
                                tooltip=f"Play {item['title']}",
                                on_click=lambda _e, p=item["audio_path"], t=item["title"]: studio.play_track(p, t),
                            ),
                            ft.Column(
                                [
                                    ft.Text(item["title"], weight=ft.FontWeight.W_600),
                                    ft.Text(item["prompt"][:100] or item["task_type"], color=MUTED, size=12),
                                ],
                                expand=True,
                            ),
                            ft.Text(item["created_at"][:16], color=MUTED),
                            ft.IconButton(
                                ft.Icons.EDIT, tooltip="Rename track", on_click=lambda _e, track=item: studio._rename_track(track, 1)
                            ),
                            ft.IconButton(
                                ft.Icons.FAVORITE if item["favorite"] else ft.Icons.FAVORITE_BORDER,
                                tooltip="Favorite",
                                on_click=lambda _e, i=item["id"]: (studio.storage.toggle_favorite(i), load()),
                            ),
                            ft.IconButton(
                                ft.Icons.DELETE_OUTLINE,
                                tooltip="Delete track",
                                icon_color="#E57373",
                                on_click=lambda _e, i=item["id"], t=item["title"]: delete(i, t),
                            ),
                        ]
                    ),
                )
            )
        if not rows.controls:
            rows.controls.append(
                studio.card(
                    ft.Icon(ft.Icons.MUSIC_NOTE, color=GREEN, size=44),
                    ft.Text("Your finished tracks will appear here."),
                    ft.Text("Create your first song to begin your library.", color=MUTED),
                )
            )
        studio.page.update()

    search.on_change = load
    view = ft.Column(
        [studio.heading("Your library", "Generated tracks, versions, and favorites."), search, rows],
        spacing=20,
        expand=True,
        scroll=ft.ScrollMode.AUTO,
    )
    load()
    return view
