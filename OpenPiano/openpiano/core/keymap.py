
from __future__ import annotations

from typing import Literal, TypeAlias

BindingSource: TypeAlias = Literal["keyboard", "mouse"]
Binding: TypeAlias = tuple[BindingSource, str, bool, bool, bool]
LegacyBinding: TypeAlias = str | tuple[str, str]
PianoMode: TypeAlias = Literal["61", "88"]

MIDI_START_61 = 36
MIDI_END_61 = 96
MIDI_START_88 = 21
MIDI_END_88 = 108

_MIDI_TO_LEGACY_BINDING_88: dict[int, LegacyBinding] = {
    21: ("ctrl", "1"),
    22: ("ctrl", "2"),
    23: ("ctrl", "3"),
    24: ("ctrl", "4"),
    25: ("ctrl", "5"),
    26: ("ctrl", "6"),
    27: ("ctrl", "7"),
    28: ("ctrl", "8"),
    29: ("ctrl", "9"),
    30: ("ctrl", "0"),
    31: ("ctrl", "q"),
    32: ("ctrl", "w"),
    33: ("ctrl", "e"),
    34: ("ctrl", "r"),
    35: ("ctrl", "t"),
    36: "1",
    37: ("shift", "1"),
    38: "2",
    39: ("shift", "2"),
    40: "3",
    41: "4",
    42: ("shift", "4"),
    43: "5",
    44: ("shift", "5"),
    45: "6",
    46: ("shift", "6"),
    47: "7",
    48: "8",
    49: ("shift", "8"),
    50: "9",
    51: ("shift", "9"),
    52: "0",
    53: "q",
    54: ("shift", "q"),
    55: "w",
    56: ("shift", "w"),
    57: "e",
    58: ("shift", "e"),
    59: "r",
    60: "t",
    61: ("shift", "t"),
    62: "y",
    63: ("shift", "y"),
    64: "u",
    65: "i",
    66: ("shift", "i"),
    67: "o",
    68: ("shift", "o"),
    69: "p",
    70: ("shift", "p"),
    71: "a",
    72: "s",
    73: ("shift", "s"),
    74: "d",
    75: ("shift", "d"),
    76: "f",
    77: "g",
    78: ("shift", "g"),
    79: "h",
    80: ("shift", "h"),
    81: "j",
    82: ("shift", "j"),
    83: "k",
    84: "l",
    85: ("shift", "l"),
    86: "z",
    87: ("shift", "z"),
    88: "x",
    89: "c",
    90: ("shift", "c"),
    91: "v",
    92: ("shift", "v"),
    93: "b",
    94: ("shift", "b"),
    95: "n",
    96: "m",
    97: ("ctrl", "y"),
    98: ("ctrl", "u"),
    99: ("ctrl", "i"),
    100: ("ctrl", "o"),
    101: ("ctrl", "p"),
    102: ("ctrl", "a"),
    103: ("ctrl", "s"),
    104: ("ctrl", "d"),
    105: ("ctrl", "f"),
    106: ("ctrl", "g"),
    107: ("ctrl", "h"),
    108: ("ctrl", "j"),
}

MODE_RANGES: dict[PianoMode, tuple[int, int]] = {
    "61": (MIDI_START_61, MIDI_END_61),
    "88": (MIDI_START_88, MIDI_END_88),
}

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
BLACK_NOTES = {1, 3, 6, 8, 10}

SHIFTED_DIGIT_SYMBOLS = {
    "!": "1",
    "@": "2",
    "#": "3",
    "$": "4",
    "%": "5",
    "^": "6",
    "&": "7",
    "*": "8",
    "(": "9",
    ")": "0",
}
BASE_DIGIT_TO_SHIFTED_SYMBOL = {value: key for key, value in SHIFTED_DIGIT_SYMBOLS.items()}

KEYNAME_TO_CHAR = {
    "exclam": "!",
    "at": "@",
    "numbersign": "#",
    "dollar": "$",
    "percent": "%",
    "asciicircum": "^",
    "ampersand": "&",
    "asterisk": "*",
    "parenleft": "(",
    "parenright": ")",
}

MOUSE_BUTTONS = {
    "right",
    "middle",
    "x1",
    "x2",
}

MODIFIER_KEYNAMES = {
    "shift",
    "shift_l",
    "shift_r",
    "control",
    "control_l",
    "control_r",
    "ctrl",
    "alt",
    "alt_l",
    "alt_r",
    "meta",
    "super_l",
    "super_r",
}

_DISPLAY_KEY_NAMES = {
    "right": "RMB",
    "middle": "MMB",
    "x1": "X1",
    "x2": "X2",
}

_DISPLAY_KEY_NAMES_VERBOSE = {
    "right": "Right mouse button",
    "middle": "Middle mouse button",
    "x1": "Back mouse button (X1)",
    "x2": "Forward mouse button (X2)",
}


def _normalize_keyboard_token(value: str) -> str | None:
    token = str(value or "").strip().lower()
    if not token:
        return None
    if len(token) == 1 and token.isalnum():
        return token
    if len(token) == 1 and token in SHIFTED_DIGIT_SYMBOLS:
        return SHIFTED_DIGIT_SYMBOLS[token]
    if token in KEYNAME_TO_CHAR:
        mapped = KEYNAME_TO_CHAR[token]
        if mapped in SHIFTED_DIGIT_SYMBOLS:
            return SHIFTED_DIGIT_SYMBOLS[mapped]
    return None


def _normalize_mouse_token(value: str) -> str | None:
    token = str(value or "").strip().lower()
    if token.endswith("button"):
        token = token[:-6]
    if token == "extrabutton1":
        token = "x1"
    if token == "extrabutton2":
        token = "x2"
    if token in {"back", "xbutton1"}:
        token = "x1"
    if token in {"forward", "xbutton2"}:
        token = "x2"
    return token if token in MOUSE_BUTTONS else None


def _build_binding(
    source: str,
    token: str,
    *,
    ctrl: bool = False,
    shift: bool = False,
    alt: bool = False,
) -> Binding | None:
    source_value = str(source or "").strip().lower()
    if source_value == "keyboard":
        normalized_token = _normalize_keyboard_token(token)
    elif source_value == "mouse":
        normalized_token = _normalize_mouse_token(token)
    else:
        return None
    if normalized_token is None:
        return None
    return (
        source_value,
        normalized_token,
        bool(ctrl),
        bool(shift),
        bool(alt),
    )


def binding_to_id(binding: Binding) -> str:
    source, token, ctrl, shift, alt = binding
    return f"{source}|{1 if ctrl else 0}|{1 if shift else 0}|{1 if alt else 0}|{token}"


def binding_from_id(value: str) -> Binding | None:
    text = str(value or "").strip()
    if not text:
        return None
    parts = text.split("|", 4)
    if len(parts) != 5:
        return None
    source, ctrl_raw, shift_raw, alt_raw, token = parts
    if ctrl_raw not in {"0", "1"} or shift_raw not in {"0", "1"} or alt_raw not in {"0", "1"}:
        return None
    return _build_binding(
        source,
        token,
        ctrl=(ctrl_raw == "1"),
        shift=(shift_raw == "1"),
        alt=(alt_raw == "1"),
    )


def serialize_custom_keybind_payload(bindings: dict[int, Binding]) -> dict[str, str]:
    payload: dict[str, str] = {}
    for note in sorted(bindings.keys()):
        binding = bindings[note]
        if note < MIDI_START_88 or note > MIDI_END_88:
            continue
        payload[str(note)] = binding_to_id(binding)
    return payload


def deserialize_custom_keybind_payload(payload: object) -> dict[int, Binding]:
    if not isinstance(payload, dict):
        return {}
    parsed: dict[int, Binding] = {}
    for note_raw, binding_raw in payload.items():
        try:
            note = int(str(note_raw).strip())
        except Exception:
            continue
        if note < MIDI_START_88 or note > MIDI_END_88:
            continue
        if not isinstance(binding_raw, str):
            continue
        binding = binding_from_id(binding_raw)
        if binding is None:
            continue
        parsed[note] = binding
    return parsed


def apply_custom_keybinds(base_mapping: dict[int, Binding], overrides: dict[int, Binding]) -> dict[int, Binding]:
    merged = dict(base_mapping)
    for note, binding in overrides.items():
        if note in merged:
            merged[note] = binding
    return merged


def extract_custom_keybind_overrides(base_mapping: dict[int, Binding], mapping: dict[int, Binding]) -> dict[int, Binding]:
    overrides: dict[int, Binding] = {}
    for note, default_binding in base_mapping.items():
        current_binding = mapping.get(note)
        if current_binding is None:
            continue
        if current_binding != default_binding:
            overrides[note] = current_binding
    return overrides


def build_binding_to_notes(mapping: dict[int, Binding]) -> dict[Binding, tuple[int, ...]]:
    grouped: dict[Binding, list[int]] = {}
    for note, binding in mapping.items():
        grouped.setdefault(binding, []).append(note)
    return {binding: tuple(notes) for binding, notes in grouped.items()}


def _legacy_to_binding(binding: LegacyBinding) -> Binding:
    if isinstance(binding, tuple):
        modifier, base = binding
        modifier_value = str(modifier or "").strip().lower()
        base_value = str(base or "").strip().lower()
        if modifier_value == "ctrl":
            normalized = _build_binding("keyboard", base_value, ctrl=True)
            if normalized is not None:
                return normalized
        if modifier_value == "shift":
            normalized = _build_binding("keyboard", base_value, shift=True)
            if normalized is not None:
                return normalized
        if modifier_value == "alt":
            normalized = _build_binding("keyboard", base_value, alt=True)
            if normalized is not None:
                return normalized
    normalized = _build_binding("keyboard", str(binding).strip().lower())
    if normalized is not None:
        return normalized
    return ("keyboard", "q", False, False, False)


def get_mode_mapping(mode: PianoMode) -> dict[int, Binding]:
    midi_start, midi_end = MODE_RANGES[mode]
    return {note: _legacy_to_binding(_MIDI_TO_LEGACY_BINDING_88[note]) for note in range(midi_start, midi_end + 1)}


def get_binding_to_midi(mode: PianoMode) -> dict[Binding, int]:
    mode_map = get_mode_mapping(mode)
    reverse: dict[Binding, int] = {}
    for note, binding in mode_map.items():
        reverse.setdefault(binding, note)
    return reverse


def get_note_labels(mode: PianoMode) -> dict[int, str]:
    midi_start, midi_end = MODE_RANGES[mode]
    return {note: f"{NOTE_NAMES[note % 12]}{(note // 12) - 1}" for note in range(midi_start, midi_end + 1)}


def is_black_key(midi_note: int) -> bool:
    return midi_note % 12 in BLACK_NOTES


def binding_to_label(binding: Binding, black_key: bool = False) -> str:
    source, token, ctrl, shift, alt = binding
    if source == "keyboard" and shift and not ctrl and not alt:
        if token in BASE_DIGIT_TO_SHIFTED_SYMBOL:
            return BASE_DIGIT_TO_SHIFTED_SYMBOL[token]
        if token.isalpha():
            return token.upper()

    parts: list[str] = []
    if ctrl:
        parts.append("C")
    shift_symbol_short = source == "keyboard" and token in BASE_DIGIT_TO_SHIFTED_SYMBOL and shift and not ctrl and not alt
    if shift and not shift_symbol_short:
        parts.append("S")
    if alt:
        parts.append("A")

    if source == "mouse":
        base = _DISPLAY_KEY_NAMES.get(token, token.upper())
    elif shift_symbol_short:
        base = BASE_DIGIT_TO_SHIFTED_SYMBOL[token]
    elif token.isalpha():
        base = token.upper() if black_key else token.lower()
    else:
        base = token.upper()

    if not parts:
        return base
    if source == "keyboard":
        # Keep combo labels compact on keys by stacking modifiers over the base key.
        combo_base = base.upper() if token.isalpha() else base
        return f"{'/'.join(parts)}\n+\n{combo_base}"
    return "+".join(parts + [base])


def binding_to_inline_label(binding: Binding) -> str:
    source, token, ctrl, shift, alt = binding
    if source == "keyboard":
        if token in BASE_DIGIT_TO_SHIFTED_SYMBOL and shift and not ctrl and not alt:
            return BASE_DIGIT_TO_SHIFTED_SYMBOL[token]
        base = token.upper()
    else:
        base = _DISPLAY_KEY_NAMES_VERBOSE.get(token, token.upper())

    if source == "keyboard" and shift and not ctrl and not alt and token.isalpha():
        return base

    modifiers: list[str] = []
    if ctrl:
        modifiers.append("Ctrl")
    if shift:
        modifiers.append("Shift")
    if alt:
        modifiers.append("Alt")
    if not modifiers:
        return base
    return " + ".join(modifiers + [base])


def normalize_mouse_binding(button: str, shift: bool, ctrl: bool, alt: bool) -> Binding | None:
    return _build_binding(
        "mouse",
        button,
        ctrl=ctrl,
        shift=shift,
        alt=alt,
    )


def normalize_key_event(text: str, key_name: str, shift: bool, ctrl: bool, alt: bool = False) -> Binding | None:
    normalized_text = (text or "").strip()
    normalized_key = (key_name or "").strip()
    key_lower = normalized_key.lower()

    if key_lower in MODIFIER_KEYNAMES:
        return None

    effective_shift = bool(shift)
    token: str | None = None

    if normalized_text in SHIFTED_DIGIT_SYMBOLS:
        token = SHIFTED_DIGIT_SYMBOLS[normalized_text]
        effective_shift = True
    elif len(normalized_text) == 1 and normalized_text.isalpha():
        token = normalized_text.lower()
        effective_shift = normalized_text.isupper() or effective_shift
    elif len(normalized_text) == 1 and normalized_text.isdigit():
        token = normalized_text
    elif key_lower in KEYNAME_TO_CHAR:
        mapped = KEYNAME_TO_CHAR[key_lower]
        if mapped in SHIFTED_DIGIT_SYMBOLS:
            token = SHIFTED_DIGIT_SYMBOLS[mapped]
            effective_shift = True
    elif len(normalized_key) == 1 and normalized_key.isalnum():
        token = normalized_key.lower()

    if token is None:
        return None

    return _build_binding(
        "keyboard",
        token,
        ctrl=bool(ctrl),
        shift=bool(effective_shift),
        alt=bool(alt),
    )


def validate_mapping(mode: PianoMode) -> None:
    midi_start, midi_end = MODE_RANGES[mode]
    mode_map = get_mode_mapping(mode)
    expected_notes = set(range(midi_start, midi_end + 1))
    mapped_notes = set(mode_map.keys())

    if expected_notes != mapped_notes:
        missing = sorted(expected_notes - mapped_notes)
        extra = sorted(mapped_notes - expected_notes)
        raise ValueError(f"Invalid note coverage for mode {mode}. Missing={missing}, extra={extra}")

    reverse = get_binding_to_midi(mode)
    if len(reverse) != len(mode_map):
        raise ValueError(f"Duplicate key bindings detected for mode {mode}")

