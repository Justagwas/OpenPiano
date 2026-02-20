
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from openpiano.core.config import (
    APP_NAME,
    DEFAULT_MASTER_VOLUME,
    DEFAULT_NOTE_VELOCITY,
    DEFAULT_THEME_MODE,
    INSTRUMENT_BANK_MAX,
    INSTRUMENT_BANK_MIN,
    INSTRUMENT_PRESET_MAX,
    INSTRUMENT_PRESET_MIN,
    NOTE_VELOCITY_MAX,
    NOTE_VELOCITY_MIN,
    SUSTAIN_PERCENT_MAX,
    SUSTAIN_PERCENT_MIN,
    TRANSPOSE_MAX,
    TRANSPOSE_MIN,
    UI_SCALE_MAX,
    UI_SCALE_MIN,
    UI_SCALE_STEP,
)
from openpiano.core.keymap import MIDI_END_88, MIDI_START_88, PianoMode, binding_from_id, binding_to_id
from openpiano.core.normalize import clamp_float, clamp_int, quantize_step

SETTINGS_FILE_NAME = "OpenPiano_config.json"
ThemeMode = Literal["dark", "light"]
AnimationSpeed = Literal["instant", "fast", "normal", "slow", "very_slow"]
KeyboardInputMode = Literal["layout", "qwerty"]


@dataclass(frozen=True, slots=True)
class AppSettings:
    mode: PianoMode = "61"
    instrument_id: str = ""
    volume: float = DEFAULT_MASTER_VOLUME
    velocity: int = DEFAULT_NOTE_VELOCITY
    show_stats: bool = True
    controls_open: bool = False
    transpose: int = 0
    sustain_percent: int = 100
    sustain_fade: int = 0
    hold_space_for_sustain: bool = False
    show_key_labels: bool = True
    show_note_labels: bool = False
    instrument_bank: int = 0
    instrument_preset: int = 0
    theme_mode: ThemeMode = DEFAULT_THEME_MODE
    ui_scale: float = 1.0
    animation_speed: AnimationSpeed = "instant"
    auto_check_updates: bool = True
    midi_input_device: str = ""
    white_key_color: str = ""
    white_key_pressed_color: str = ""
    black_key_color: str = ""
    black_key_pressed_color: str = ""
    hq_soundfont_prompt_seen: bool = False
    keyboard_input_mode: KeyboardInputMode = "layout"
    keyboard_layout_choice_seen: bool = False
    custom_keybinds: dict[str, str] = field(default_factory=dict)


def _appdata_settings_dir() -> Path | None:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_NAME
    return Path(__file__).resolve().parents[2]


def _ensure_settings_dir(path: Path) -> None:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception:
        return

    probe = path / ".openpiano_settings_probe.tmp"
    try:
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
    except Exception:
        try:
            if probe.exists():
                probe.unlink()
        except Exception:
            pass
        return


_SETTINGS_DIR_CACHE: Path | None = None


def _settings_dir() -> Path:
    global _SETTINGS_DIR_CACHE
    if _SETTINGS_DIR_CACHE is not None:
        return _SETTINGS_DIR_CACHE

    appdata = _appdata_settings_dir()
    if appdata is None:
        appdata = Path(__file__).resolve().parents[2]
    _ensure_settings_dir(appdata)
    _SETTINGS_DIR_CACHE = appdata
    return appdata


def _settings_path(path: Path | None = None) -> Path:
    if path is not None:
        return path
    return _settings_dir() / SETTINGS_FILE_NAME


def _clamp_mode(value: Any) -> PianoMode:
    return value if value in {"61", "88"} else "61"


def _clamp_volume(value: Any) -> float:
    return clamp_float(value, 0.0, 1.0, default=DEFAULT_MASTER_VOLUME)


def _clamp_bool(value: Any, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _clamp_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    return clamp_int(value, minimum, maximum, default=default)


def _clamp_transpose(value: Any) -> int:
    return _clamp_int(value, 0, TRANSPOSE_MIN, TRANSPOSE_MAX)


def _clamp_sustain_percent(value: Any) -> int:
    return _clamp_int(value, 100, SUSTAIN_PERCENT_MIN, SUSTAIN_PERCENT_MAX)


def _clamp_sustain_fade(value: Any) -> int:
    return _clamp_int(value, 0, 0, 100)


def _clamp_velocity(value: Any) -> int:
    return _clamp_int(value, DEFAULT_NOTE_VELOCITY, NOTE_VELOCITY_MIN, NOTE_VELOCITY_MAX)


def _quantize_scale(value: float) -> float:
    return quantize_step(value, UI_SCALE_MIN, UI_SCALE_MAX, UI_SCALE_STEP, digits=2)


def _clamp_ui_scale(value: Any) -> float:
    parsed = clamp_float(value, UI_SCALE_MIN, UI_SCALE_MAX, default=1.0)
    return _quantize_scale(parsed)


def _clamp_theme_mode(value: Any) -> ThemeMode:
    return value if value in {"dark", "light"} else DEFAULT_THEME_MODE


def _clamp_animation_speed(value: Any) -> AnimationSpeed:
    if value in {"instant", "fast", "normal", "slow", "very_slow"}:
        return value
    return "instant"


def _clamp_keyboard_input_mode(value: Any) -> KeyboardInputMode:
    if value in {"layout", "qwerty"}:
        return value
    return "layout"




def _clamp_midi_device_name(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _clamp_color(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip()
    if not text:
        return ""
    if _HEX_COLOR_RE.match(text):
        return text.lower()
    return ""


def _clamp_custom_keybinds(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    parsed: dict[str, str] = {}
    for note_raw, binding_raw in value.items():
        if not isinstance(binding_raw, str):
            continue
        try:
            note = int(str(note_raw).strip())
        except Exception:
            continue
        if note < MIDI_START_88 or note > MIDI_END_88:
            continue
        normalized = binding_from_id(binding_raw)
        if normalized is None:
            continue
        parsed[str(note)] = binding_to_id(normalized)
    return parsed


def load_settings(path: Path | None = None) -> AppSettings:
    file_path = _settings_path(path)
    if not file_path.exists():
        return AppSettings()
    try:
        payload = json.loads(file_path.read_text(encoding="utf-8"))
    except Exception:
        return AppSettings()
    if not isinstance(payload, dict):
        return AppSettings()

    mode = _clamp_mode(payload.get("mode"))
    instrument_id_raw = payload.get("instrument_id", "")
    instrument_id = str(instrument_id_raw).strip() if isinstance(instrument_id_raw, str) else ""
    volume = _clamp_volume(payload.get("volume"))
    velocity = _clamp_velocity(payload.get("velocity"))
    show_stats = _clamp_bool(payload.get("show_stats"), True)
    controls_open = _clamp_bool(payload.get("controls_open"), False)
    transpose = _clamp_transpose(payload.get("transpose"))
    sustain_percent = _clamp_sustain_percent(payload.get("sustain_percent"))
    sustain_fade = _clamp_sustain_fade(payload.get("sustain_fade"))
    hold_space_for_sustain = _clamp_bool(payload.get("hold_space_for_sustain"), False)
    show_key_labels = _clamp_bool(payload.get("show_key_labels"), True)
    show_note_labels = _clamp_bool(payload.get("show_note_labels"), False)
    instrument_bank = _clamp_int(payload.get("instrument_bank"), 0, INSTRUMENT_BANK_MIN, INSTRUMENT_BANK_MAX)
    instrument_preset = _clamp_int(
        payload.get("instrument_preset"),
        0,
        INSTRUMENT_PRESET_MIN,
        INSTRUMENT_PRESET_MAX,
    )
    theme_mode = _clamp_theme_mode(payload.get("theme_mode"))
    ui_scale = _clamp_ui_scale(payload.get("ui_scale"))
    animation_speed = _clamp_animation_speed(payload.get("animation_speed"))
    auto_check_updates = _clamp_bool(payload.get("auto_check_updates"), True)
    midi_input_device = _clamp_midi_device_name(payload.get("midi_input_device"))
    white_key_color = _clamp_color(payload.get("white_key_color"))
    white_key_pressed_color = _clamp_color(payload.get("white_key_pressed_color"))
    black_key_color = _clamp_color(payload.get("black_key_color"))
    black_key_pressed_color = _clamp_color(payload.get("black_key_pressed_color"))
    hq_soundfont_prompt_seen = _clamp_bool(payload.get("hq_soundfont_prompt_seen"), False)
    keyboard_input_mode = _clamp_keyboard_input_mode(payload.get("keyboard_input_mode"))
    keyboard_layout_choice_seen = _clamp_bool(payload.get("keyboard_layout_choice_seen"), False)
    custom_keybinds = _clamp_custom_keybinds(payload.get("custom_keybinds"))
    return AppSettings(
        mode=mode,
        instrument_id=instrument_id,
        volume=volume,
        velocity=velocity,
        show_stats=show_stats,
        controls_open=controls_open,
        transpose=transpose,
        sustain_percent=sustain_percent,
        sustain_fade=sustain_fade,
        hold_space_for_sustain=hold_space_for_sustain,
        show_key_labels=show_key_labels,
        show_note_labels=show_note_labels,
        instrument_bank=instrument_bank,
        instrument_preset=instrument_preset,
        theme_mode=theme_mode,
        ui_scale=ui_scale,
        animation_speed=animation_speed,
        auto_check_updates=auto_check_updates,
        midi_input_device=midi_input_device,
        white_key_color=white_key_color,
        white_key_pressed_color=white_key_pressed_color,
        black_key_color=black_key_color,
        black_key_pressed_color=black_key_pressed_color,
        hq_soundfont_prompt_seen=hq_soundfont_prompt_seen,
        keyboard_input_mode=keyboard_input_mode,
        keyboard_layout_choice_seen=keyboard_layout_choice_seen,
        custom_keybinds=custom_keybinds,
    )


def save_settings(settings: AppSettings, path: Path | None = None) -> None:
    payload = {
        "mode": _clamp_mode(settings.mode),
        "instrument_id": str(settings.instrument_id).strip(),
        "volume": _clamp_volume(settings.volume),
        "velocity": _clamp_velocity(settings.velocity),
        "show_stats": _clamp_bool(settings.show_stats, True),
        "controls_open": _clamp_bool(settings.controls_open, False),
        "transpose": _clamp_transpose(settings.transpose),
        "sustain_percent": _clamp_sustain_percent(settings.sustain_percent),
        "sustain_fade": _clamp_sustain_fade(settings.sustain_fade),
        "hold_space_for_sustain": _clamp_bool(settings.hold_space_for_sustain, False),
        "show_key_labels": _clamp_bool(settings.show_key_labels, True),
        "show_note_labels": _clamp_bool(settings.show_note_labels, False),
        "instrument_bank": _clamp_int(settings.instrument_bank, 0, INSTRUMENT_BANK_MIN, INSTRUMENT_BANK_MAX),
        "instrument_preset": _clamp_int(
            settings.instrument_preset,
            0,
            INSTRUMENT_PRESET_MIN,
            INSTRUMENT_PRESET_MAX,
        ),
        "theme_mode": _clamp_theme_mode(settings.theme_mode),
        "ui_scale": _clamp_ui_scale(settings.ui_scale),
        "animation_speed": _clamp_animation_speed(settings.animation_speed),
        "auto_check_updates": _clamp_bool(settings.auto_check_updates, True),
        "midi_input_device": _clamp_midi_device_name(settings.midi_input_device),
        "white_key_color": _clamp_color(settings.white_key_color),
        "white_key_pressed_color": _clamp_color(settings.white_key_pressed_color),
        "black_key_color": _clamp_color(settings.black_key_color),
        "black_key_pressed_color": _clamp_color(settings.black_key_pressed_color),
        "hq_soundfont_prompt_seen": _clamp_bool(settings.hq_soundfont_prompt_seen, False),
        "keyboard_input_mode": _clamp_keyboard_input_mode(settings.keyboard_input_mode),
        "keyboard_layout_choice_seen": _clamp_bool(settings.keyboard_layout_choice_seen, False),
        "custom_keybinds": _clamp_custom_keybinds(settings.custom_keybinds),
    }
    raw = json.dumps(payload, indent=2)

    file_path = _settings_path(path)
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(raw, encoding="utf-8")
    except Exception:
                                                                                            
        return

