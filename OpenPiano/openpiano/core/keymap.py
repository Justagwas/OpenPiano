
from __future__ import annotations

import sys
from typing import Literal, TypeAlias

BindingSource: TypeAlias = Literal["keyboard", "mouse"]
Binding: TypeAlias = tuple[BindingSource, str, bool, bool, bool]
BindingSpec: TypeAlias = str | tuple[str, str]
PianoMode: TypeAlias = Literal["61", "88"]
KeyboardInputMode: TypeAlias = Literal["layout", "qwerty"]

MIDI_START_61 = 36
MIDI_END_61 = 96
MIDI_START_88 = 21
MIDI_END_88 = 108

_MIDI_TO_BINDING_SPEC_88: dict[int, BindingSpec] = {
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

_QWERTY_SCANCODE_TO_TOKEN = {
    0x02: "1",
    0x03: "2",
    0x04: "3",
    0x05: "4",
    0x06: "5",
    0x07: "6",
    0x08: "7",
    0x09: "8",
    0x0A: "9",
    0x0B: "0",
    0x10: "q",
    0x11: "w",
    0x12: "e",
    0x13: "r",
    0x14: "t",
    0x15: "y",
    0x16: "u",
    0x17: "i",
    0x18: "o",
    0x19: "p",
    0x1E: "a",
    0x1F: "s",
    0x20: "d",
    0x21: "f",
    0x22: "g",
    0x23: "h",
    0x24: "j",
    0x25: "k",
    0x26: "l",
    0x2C: "z",
    0x2D: "x",
    0x2E: "c",
    0x2F: "v",
    0x30: "b",
    0x31: "n",
    0x32: "m",
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

KEYBOARD_DEMO_ROWS: tuple[tuple[str, ...], ...] = (
    ("1", "2", "3", "4", "5", "6", "7", "8", "9", "0"),
    ("q", "w", "e", "r", "t", "y", "u", "i", "o", "p"),
    ("a", "s", "d", "f", "g", "h", "j", "k", "l"),
    ("z", "x", "c", "v", "b", "n", "m"),
)

_TOKEN_TO_QWERTY_SCANCODE = {token: scan for scan, token in _QWERTY_SCANCODE_TO_TOKEN.items()}


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


def _display_upper_letter(token: str) -> str:
    value = str(token or "")
    upper = value.upper()
    if len(upper) == 1 and upper.isalpha():
        return upper
    return value


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


def _binding_spec_to_binding(binding: BindingSpec) -> Binding:
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
    return {note: _binding_spec_to_binding(_MIDI_TO_BINDING_SPEC_88[note]) for note in range(midi_start, midi_end + 1)}

def get_note_labels(mode: PianoMode) -> dict[int, str]:
    midi_start, midi_end = MODE_RANGES[mode]
    return {note: f"{NOTE_NAMES[note % 12]}{(note // 12) - 1}" for note in range(midi_start, midi_end + 1)}


def is_black_key(midi_note: int) -> bool:
    return midi_note % 12 in BLACK_NOTES


def binding_to_label(binding: Binding) -> str:
    source, token, ctrl, shift, alt = binding
    if source == "keyboard" and shift and not ctrl and not alt:
        if token in BASE_DIGIT_TO_SHIFTED_SYMBOL:
            return BASE_DIGIT_TO_SHIFTED_SYMBOL[token]
        if token.isalpha():
            return _display_upper_letter(token)

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
        base = token.lower() if token.isascii() else token
    else:
        base = token.upper()

    if not parts:
        return base
    if source == "keyboard":
        combo_base = base
        if shift and token.isalpha():
            combo_base = _display_upper_letter(token)
        return f"{'/'.join(parts)}\n+\n{combo_base}"
    return "+".join(parts + [base])


def binding_to_inline_label(binding: Binding) -> str:
    source, token, ctrl, shift, alt = binding
    if source == "keyboard":
        if token in BASE_DIGIT_TO_SHIFTED_SYMBOL and shift and not ctrl and not alt:
            return BASE_DIGIT_TO_SHIFTED_SYMBOL[token]
        if token.isalpha():
            if not ctrl and not shift and not alt:
                return token.lower() if token.isascii() else token
            base = _display_upper_letter(token) if shift else (token.upper() if token.isascii() else token)
        else:
            base = token.upper()
    else:
        base = _DISPLAY_KEY_NAMES_VERBOSE.get(token, token.upper())

    if source == "keyboard" and shift and not ctrl and not alt and token.isalpha():
        return _display_upper_letter(token)

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


def normalize_key_event_qwerty_scancode(
    native_scan_code: int,
    *,
    shift: bool,
    ctrl: bool,
    alt: bool = False,
) -> Binding | None:
    if sys.platform != "win32":
        return None
    scan = int(native_scan_code) & 0xFF
    token = _QWERTY_SCANCODE_TO_TOKEN.get(scan)
    if token is None:
        return None
    return _build_binding(
        "keyboard",
        token,
        ctrl=bool(ctrl),
        shift=bool(shift),
        alt=bool(alt),
    )


def normalize_key_event_layout_scancode(
    native_scan_code: int,
    *,
    shift: bool,
    ctrl: bool,
    alt: bool = False,
) -> Binding | None:
    if sys.platform != "win32":
        return None
    scan = int(native_scan_code) & 0xFF
    qwerty_token = _QWERTY_SCANCODE_TO_TOKEN.get(scan)
    if qwerty_token is None:
        return None
    localized = _localized_label_for_scancode(scan, fallback=qwerty_token)
    layout_token = _normalize_layout_token_for_remap(localized) or qwerty_token
    return _build_binding(
        "keyboard",
        layout_token,
        ctrl=bool(ctrl),
        shift=bool(shift),
        alt=bool(alt),
    )


def remap_bindings_for_keyboard_mode(
    bindings: dict[int, Binding],
    target_mode: KeyboardInputMode,
) -> dict[int, Binding]:
    target = "qwerty" if str(target_mode or "").strip().lower() == "qwerty" else "layout"
    qwerty_to_layout, layout_to_qwerty = _keyboard_mode_token_maps()
    remapped: dict[int, Binding] = {}
    for note, binding in bindings.items():
        source, token, ctrl, shift, alt = binding
        if source != "keyboard":
            remapped[note] = binding
            continue
        if target == "layout":
            mapped_token = qwerty_to_layout.get(token, token)
        else:
            mapped_token = layout_to_qwerty.get(token, token)
        normalized_token = _normalize_keyboard_token(mapped_token) or token
        normalized_binding = _build_binding(
            "keyboard",
            normalized_token,
            ctrl=bool(ctrl),
            shift=bool(shift),
            alt=bool(alt),
        )
        remapped[note] = normalized_binding if normalized_binding is not None else binding
    return remapped


def qwerty_demo_rows() -> tuple[tuple[str, ...], ...]:
    return KEYBOARD_DEMO_ROWS


def current_layout_demo_rows() -> tuple[tuple[str, ...], ...]:
    rows: list[tuple[str, ...]] = []
    for row in KEYBOARD_DEMO_ROWS:
        localized: list[str] = []
        for token in row:
            scan = _TOKEN_TO_QWERTY_SCANCODE.get(token)
            if scan is None:
                localized.append(token)
                continue
            localized.append(_localized_label_for_scancode(scan, fallback=token))
        rows.append(tuple(localized))
    return tuple(rows)


def _keyboard_mode_token_maps() -> tuple[dict[str, str], dict[str, str]]:
    qwerty_to_layout: dict[str, str] = {}
    layout_to_qwerty: dict[str, str] = {}
    for scan, qwerty_token in _QWERTY_SCANCODE_TO_TOKEN.items():
        localized = _localized_label_for_scancode(scan, fallback=qwerty_token)
        layout_token = _normalize_layout_token_for_remap(localized) or qwerty_token
        qwerty_to_layout[qwerty_token] = layout_token
        if layout_token not in layout_to_qwerty:
            layout_to_qwerty[layout_token] = qwerty_token
    return qwerty_to_layout, layout_to_qwerty


def _normalize_layout_token_for_remap(value: str) -> str | None:
    text = str(value or "").strip()
    if len(text) != 1:
        return None
    token = text.lower()
    if token.isalnum():
        return token
    return None


def _localized_label_for_scancode(scan_code: int, *, fallback: str) -> str:
    scan = int(scan_code) & 0xFF
    fallback_text = str(fallback or "").strip() or "?"
    if scan <= 0:
        return fallback_text
    if not (sys.platform == "win32"):
        return fallback_text
    try:
        import ctypes

        user32 = ctypes.windll.user32
        map_vk = user32.MapVirtualKeyExW
        map_vk.argtypes = [ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p]
        map_vk.restype = ctypes.c_uint
        to_unicode = user32.ToUnicodeEx
        to_unicode.argtypes = [
            ctypes.c_uint,
            ctypes.c_uint,
            ctypes.POINTER(ctypes.c_ubyte),
            ctypes.c_wchar_p,
            ctypes.c_int,
            ctypes.c_uint,
            ctypes.c_void_p,
        ]
        to_unicode.restype = ctypes.c_int
        get_layout = user32.GetKeyboardLayout
        get_layout.argtypes = [ctypes.c_uint]
        get_layout.restype = ctypes.c_void_p

        hkl = get_layout(0)
        # MAPVK_VSC_TO_VK_EX = 3
        vk = int(map_vk(scan, 3, hkl))
        if vk <= 0:
            return fallback_text

        state = (ctypes.c_ubyte * 256)()
        buf = ctypes.create_unicode_buffer(8)
        written = int(to_unicode(vk, scan, state, buf, len(buf), 0, hkl))
        if written <= 0:
            return fallback_text
        text = str(buf.value[:written]).strip()
        if not text:
            return fallback_text
        if len(text) > 1:
            text = text[0]
        if text.isalpha():
            return text.lower()
        return text
    except Exception:
        return fallback_text

