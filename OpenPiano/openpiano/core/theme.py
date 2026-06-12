
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

ThemeMode = Literal["dark", "light"]


@dataclass(frozen=True, slots=True)
class ThemePalette:
    app_bg: str
    panel_bg: str
    border: str
    text_primary: str
    text_secondary: str
    accent: str
    accent_hover: str
    white_key: str
    white_key_pressed: str
    black_key: str
    black_key_pressed: str


THEMES: dict[ThemeMode, ThemePalette] = {
    "dark": ThemePalette(
        app_bg="#0A0A0B",
        panel_bg="#141416",
        border="#2A2A2D",
        text_primary="#F4F4F5",
        text_secondary="#B7B7BC",
        accent="#D20F39",
        accent_hover="#F03A5F",
        white_key="#E8E3D7",
        white_key_pressed="#B9394E",
        black_key="#15161A",
        black_key_pressed="#7C0B23",
    ),
    "light": ThemePalette(
        app_bg="#ECEDEF",
        panel_bg="#FAFAFB",
        border="#D1D3D8",
        text_primary="#1B1F2A",
        text_secondary="#4B5161",
        accent="#C51E3A",
        accent_hover="#D94A63",
        white_key="#EEEAE0",
        white_key_pressed="#B9394E",
        black_key="#181A1F",
        black_key_pressed="#7C0B23",
    ),
}


def _valid_color(value: str) -> bool:
    if not isinstance(value, str):
        return False
    text = value.strip()
    if len(text) != 7 or not text.startswith("#"):
        return False
    for ch in text[1:]:
        if ch not in "0123456789abcdefABCDEF":
            return False
    return True


def apply_key_color_overrides(
    theme: ThemePalette,
    white: str = "",
    white_pressed: str = "",
    black: str = "",
    black_pressed: str = "",
) -> ThemePalette:
    kwargs: dict[str, str] = {}
    if _valid_color(white):
        kwargs["white_key"] = white
    if _valid_color(white_pressed):
        kwargs["white_key_pressed"] = white_pressed
    if _valid_color(black):
        kwargs["black_key"] = black
    if _valid_color(black_pressed):
        kwargs["black_key_pressed"] = black_pressed
    if not kwargs:
        return theme
    return replace(theme, **kwargs)


def get_theme(mode: ThemeMode = "dark") -> ThemePalette:
    return THEMES.get(mode, THEMES["dark"])
