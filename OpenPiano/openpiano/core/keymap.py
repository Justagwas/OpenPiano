
from __future__ import annotations

from typing import Literal, TypeAlias

Binding: TypeAlias = str | tuple[str, str]
PianoMode: TypeAlias = Literal["61", "88"]

MIDI_START_61 = 36
MIDI_END_61 = 96
MIDI_START_88 = 21
MIDI_END_88 = 108

MIDI_TO_BINDING_88: dict[int, Binding] = {
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


def get_mode_mapping(mode: PianoMode) -> dict[int, Binding]:
    midi_start, midi_end = MODE_RANGES[mode]
    return {note: MIDI_TO_BINDING_88[note] for note in range(midi_start, midi_end + 1)}


def get_binding_to_midi(mode: PianoMode) -> dict[Binding, int]:
    mode_map = get_mode_mapping(mode)
    return {binding: note for note, binding in mode_map.items()}


def get_note_labels(mode: PianoMode) -> dict[int, str]:
    midi_start, midi_end = MODE_RANGES[mode]
    return {note: f"{NOTE_NAMES[note % 12]}{(note // 12) - 1}" for note in range(midi_start, midi_end + 1)}


def is_black_key(midi_note: int) -> bool:
    return midi_note % 12 in BLACK_NOTES


def binding_to_label(binding: Binding, black_key: bool = False) -> str:
    if isinstance(binding, tuple):
        modifier, base = binding
        if modifier == "ctrl":
            shown = base.upper() if base.isalpha() else base
            return f"C\n+\n{shown}"
        if base in BASE_DIGIT_TO_SHIFTED_SYMBOL:
            return BASE_DIGIT_TO_SHIFTED_SYMBOL[base]
        return base.upper() if black_key else base.lower()

    if binding.isalpha():
        return binding.upper() if black_key else binding.lower()
    return binding


def normalize_key_event(text: str, key_name: str, shift: bool, ctrl: bool) -> Binding | None:
    normalized_text = (text or "").strip()
    normalized_key = (key_name or "").strip()
    key_lower = normalized_key.lower()

    if key_lower in MODIFIER_KEYNAMES:
        return None

    if ctrl:
        if len(key_lower) == 1 and key_lower.isalnum():
            return ("ctrl", key_lower)
        if len(normalized_text) == 1 and normalized_text.lower().isalnum():
            return ("ctrl", normalized_text.lower())

    if normalized_text:
        if normalized_text in SHIFTED_DIGIT_SYMBOLS:
            return ("shift", SHIFTED_DIGIT_SYMBOLS[normalized_text])
        if len(normalized_text) == 1 and normalized_text.isalpha():
            base = normalized_text.lower()
            return ("shift", base) if normalized_text.isupper() else base
        if len(normalized_text) == 1 and normalized_text.isdigit():
            return normalized_text

    if key_lower in KEYNAME_TO_CHAR:
        mapped = KEYNAME_TO_CHAR[key_lower]
        return ("shift", SHIFTED_DIGIT_SYMBOLS[mapped])

    if len(normalized_key) == 1:
        if normalized_key.isalpha():
            base = normalized_key.lower()
            return ("shift", base) if shift else base
        if normalized_key.isdigit():
            return ("shift", normalized_key) if shift else normalized_key

    return None


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

