from __future__ import annotations

import flet as ft

ACCENT = GREEN = "#1ED760"
INK = "#0A0D0C"
PANEL = "#121716"
RAISED = "#19201E"
BORDER = "#303735"
TEXT = "#F5F7F5"
MUTED = "#A9B0AD"
DANGER = "#8C2431"
SUCCESS = "#225A35"
INPUT = "#0E1312"
TRACK = "#34403B"
SHELL = "#0E1211"
PLAYER = "#101413"
SELECTED = "#232A28"
SUCCESS_SURFACE = "#14251B"
SUCCESS_BORDER = "#2D6A43"
ERROR_SURFACE = "#2A1518"
ERROR_BORDER = "#74313A"
WARNING = "#E5B95C"
DANGER_TEXT = "#E57373"
ARTWORK_GRADIENT = ["#523BC6", "#E05480", "#F2A75F"]

SPACE_1, SPACE_2, SPACE_3, SPACE_4, SPACE_5, SPACE_6 = 4, 8, 12, 16, 24, 32
CONTROL_RADIUS = 8
CARD_RADIUS = 12

FIELD_STYLE = {
    "border_radius": CONTROL_RADIUS,
    "border_color": BORDER,
    "focused_border_color": ACCENT,
    "focused_border_width": 2,
    "color": TEXT,
    "fill_color": INPUT,
    "filled": True,
    "hover_color": INPUT,
    "content_padding": ft.Padding.symmetric(horizontal=12, vertical=12),
}

PRIMARY_BUTTON_STYLE = ft.ButtonStyle(
    color=INK,
    bgcolor=ACCENT,
    padding=ft.Padding.symmetric(horizontal=16, vertical=12),
    shape=ft.RoundedRectangleBorder(radius=CONTROL_RADIUS),
)
SECONDARY_BUTTON_STYLE = ft.ButtonStyle(
    color=TEXT,
    bgcolor=RAISED,
    side=ft.BorderSide(1, BORDER),
    padding=ft.Padding.symmetric(horizontal=16, vertical=12),
    shape=ft.RoundedRectangleBorder(radius=CONTROL_RADIUS),
)
DANGER_BUTTON_STYLE = ft.ButtonStyle(
    color=TEXT,
    bgcolor=DANGER,
    padding=ft.Padding.symmetric(horizontal=16, vertical=12),
    shape=ft.RoundedRectangleBorder(radius=CONTROL_RADIUS),
)


def app_theme() -> ft.Theme:
    return ft.Theme(
        color_scheme_seed=ACCENT,
        font_family="Inter",
        scaffold_bgcolor=INK,
        card_bgcolor=PANEL,
        divider_color=BORDER,
        hint_color=MUTED,
        focus_color="#1ED76033",
        hover_color=INPUT,
        highlight_color=INPUT,
        splash_color=ft.Colors.TRANSPARENT,
        disabled_color="#69716D",
        button_theme=ft.ButtonTheme(style=SECONDARY_BUTTON_STYLE),
        text_button_theme=ft.TextButtonTheme(style=ft.ButtonStyle(color=ACCENT)),
        icon_button_theme=ft.IconButtonTheme(
            style=ft.ButtonStyle(icon_color=MUTED, shape=ft.RoundedRectangleBorder(radius=CONTROL_RADIUS))
        ),
        checkbox_theme=ft.CheckboxTheme(fill_color=ACCENT, check_color=INK, border_side=ft.BorderSide(1, BORDER)),
        slider_theme=ft.SliderTheme(active_track_color=ACCENT, inactive_track_color=TRACK, thumb_color=ACCENT, track_height=4),
        progress_indicator_theme=ft.ProgressIndicatorTheme(color=ACCENT, linear_track_color=TRACK, linear_min_height=4),
        divider_theme=ft.DividerTheme(color=BORDER, thickness=1),
        dialog_theme=ft.DialogTheme(
            bgcolor=PANEL,
            barrier_color="#00000099",
            shape=ft.RoundedRectangleBorder(radius=CARD_RADIUS),
            actions_padding=ft.Padding.all(SPACE_4),
        ),
    )
