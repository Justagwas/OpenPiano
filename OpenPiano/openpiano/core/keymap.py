
from __future__ import annotations

import sys
from functools import lru_cache
from typing import Literal, TypeAlias

BindingSource: TypeAlias = Literal["keyboard", "mouse"]
Binding: TypeAlias = tuple[BindingSource, str, bool, bool, bool]
BindingSpec: TypeAlias = str | tuple[str, str]
PianoMode: TypeAlias = Literal["61", "88"]
KEYBIND_SCHEMA_VERSION = 2

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

_TOKEN_TO_QWERTY_SCANCODE = {token: scan for scan, token in _QWERTY_SCANCODE_TO_TOKEN.items()}


def _normalize_keyboard_token(value: str) -> str | None:
    token = str(value or "").strip().lower()
    if not token:
        return None
    if token.startswith("scan:"):
        try:
            scan = normalize_scan_code(int(token[5:], 16))
        except ValueError:
            return None
        return physical_key_token(scan) if scan in _PHYSICAL_KEY_NAMES else None
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


def serialize_custom_keybind_payload(bindings: dict[int, Binding | None]) -> dict[str, str | None]:
    payload: dict[str, str | None] = {}
    for note in sorted(bindings.keys()):
        binding = bindings[note]
        if note < MIDI_START_88 or note > MIDI_END_88:
            continue
        payload[str(note)] = binding_to_id(binding) if binding is not None else None
    return payload


def deserialize_custom_keybind_payload(payload: object) -> dict[int, Binding | None]:
    if not isinstance(payload, dict):
        return {}
    parsed: dict[int, Binding | None] = {}
    for note_raw, binding_raw in payload.items():
        try:
            note = int(str(note_raw).strip())
        except Exception:
            continue
        if note < MIDI_START_88 or note > MIDI_END_88:
            continue
        if binding_raw is None:
            parsed[note] = None
            continue
        if not isinstance(binding_raw, str):
            continue
        binding = binding_from_id(binding_raw)
        if binding is None:
            continue
        parsed[note] = binding
    return parsed


def apply_custom_keybinds(base_mapping: dict[int, Binding | None], overrides: dict[int, Binding | None]) -> dict[int, Binding | None]:
    merged = dict(base_mapping)
    for note, binding in overrides.items():
        if note in merged:
            merged[note] = binding
    return merged


def extract_custom_keybind_overrides(base_mapping: dict[int, Binding | None], mapping: dict[int, Binding | None]) -> dict[int, Binding | None]:
    overrides: dict[int, Binding | None] = {}
    for note, default_binding in base_mapping.items():
        current_binding = mapping.get(note)
        if note not in mapping:
            continue
        if current_binding != default_binding:
            overrides[note] = current_binding
    return overrides


def build_binding_to_notes(mapping: dict[int, Binding | None]) -> dict[Binding, tuple[int, ...]]:
    grouped: dict[Binding, list[int]] = {}
    for note, binding in mapping.items():
        if binding is not None:
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
    return {note: _default_physical_binding(_MIDI_TO_BINDING_SPEC_88[note]) for note in range(midi_start, midi_end + 1)}

def get_note_labels(mode: PianoMode) -> dict[int, str]:
    midi_start, midi_end = MODE_RANGES[mode]
    return {note: f"{NOTE_NAMES[note % 12]}{(note // 12) - 1}" for note in range(midi_start, midi_end + 1)}


def is_black_key(midi_note: int) -> bool:
    return midi_note % 12 in BLACK_NOTES


def binding_to_label(binding: Binding) -> str:
    source, token, ctrl, shift, alt = binding
    if source == "keyboard" and token.startswith("scan:"):
        return _physical_binding_label(binding, compact=True)
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
    if source == "keyboard" and token.startswith("scan:"):
        return _physical_binding_label(binding, compact=False)
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


def _normalize_layout_token_for_remap(value: str) -> str | None:
    text = str(value or "").strip()
    if len(text) != 1:
        return None
    token = text.lower()
    if token.isalnum():
        return token
    return None


def _localized_label_for_scancode(scan_code: int, *, fallback: str) -> str:
    label = _windows_key_label(normalize_scan_code(scan_code), False, keyboard_layout_id())
    return label.lower() if label and label.isalpha() else (label or fallback)


_PHYSICAL_KEY_NAMES: dict[int, str] = {
    **_QWERTY_SCANCODE_TO_TOKEN,
    0x01: "Esc", 0x0C: "-", 0x0D: "=", 0x0E: "Backspace", 0x0F: "Tab",
    0x1A: "[", 0x1B: "]", 0x1C: "Enter", 0x27: ";", 0x28: "'",
    0x29: "`", 0x2B: "\\", 0x33: ",", 0x34: ".", 0x35: "/", 0x39: "Space",
    **{scan: f"F{scan - 0x3A}" for scan in range(0x3B, 0x45)},
    0x57: "F11", 0x58: "F12",
    **{scan: f"F{scan - 0x57}" for scan in range(0x64, 0x70)},
    0x37: "Num *", 0x47: "Num 7", 0x48: "Num 8", 0x49: "Num 9", 0x4A: "Num -",
    0x4B: "Num 4", 0x4C: "Num 5", 0x4D: "Num 6", 0x4E: "Num +",
    0x4F: "Num 1", 0x50: "Num 2", 0x51: "Num 3", 0x52: "Num 0", 0x53: "Num .",
    0x56: "\\", 0x73: "\\", 0x7D: "?",
    0xE01C: "Num Enter", 0xE035: "Num /",
    0xE047: "Home", 0xE048: "Up", 0xE049: "Page Up", 0xE04B: "Left",
    0xE04D: "Right", 0xE04F: "End", 0xE050: "Down", 0xE051: "Page Down",
    0xE052: "Insert", 0xE053: "Delete", 0xE05B: "Windows", 0xE05C: "Windows",
    0xE05D: "Menu",
}
_MODIFIER_SCANS = {0x1D, 0x2A, 0x36, 0x38, 0xE01D, 0xE038}
_KEY_NAME_TO_SCAN = {name.lower(): scan for scan, name in _PHYSICAL_KEY_NAMES.items()}
_KEY_NAME_TO_SCAN.update(_TOKEN_TO_QWERTY_SCANCODE)
_KEY_NAME_TO_SCAN.update({"\\": 0x2B})
_KEY_NAME_TO_SCAN.update({"return": 0x1C, "escape": 0x01, "backtab": 0x0F,
                          "pageup": 0xE049, "pagedown": 0xE051, "del": 0xE053})
_SHIFTED_PUNCTUATION = dict(zip("-=[];'`,./\\", '_+{}:"~<>?|'))
_LABEL_CACHE: dict[tuple[int, bool], str] = {}
_VIRTUAL_KEY_CACHE: dict[int, int] = {}
_LABEL_LAYOUT: int | None = None


def normalize_scan_code(value: int) -> int:
    scan = int(value)
    if 0x100 <= scan <= 0x1FF:
        return 0xE000 | (scan & 0xFF)
    if 0x200 <= scan <= 0x2FF:
        return 0xE100 | (scan & 0xFF)
    return scan if 0 < scan <= 0xFFFF else 0


# Linux evdev key codes whose PC set-1 scan code differs. Codes 1-88 are identical in both.
_EVDEV_TO_SCAN_CODE: dict[int, int] = {
    89: 0x73, 96: 0xE01C, 97: 0xE01D, 98: 0xE035, 100: 0xE038,
    102: 0xE047, 103: 0xE048, 104: 0xE049, 105: 0xE04B, 106: 0xE04D,
    107: 0xE04F, 108: 0xE050, 109: 0xE051, 110: 0xE052, 111: 0xE053,
    124: 0x7D, 125: 0xE05B, 126: 0xE05C, 127: 0xE05D,
    **{183 + offset: 0x64 + offset for offset in range(12)},
}


def native_key_scan_code(native_scan_code: int) -> int:
    """Convert QKeyEvent.nativeScanCode() to the PC set-1 scan code used by key bindings."""
    value = int(native_scan_code)
    if sys.platform.startswith("linux"):
        # Qt on X11 and Wayland reports XKB key codes, which are evdev key codes + 8.
        evdev = value - 8
        if 1 <= evdev <= 88:
            return evdev
        return _EVDEV_TO_SCAN_CODE.get(evdev, 0)
    return value


def physical_key_token(native_scan_code: int) -> str:
    return f"scan:{normalize_scan_code(native_scan_code):04x}"


def is_keypad_scan_code(native_scan_code: int) -> bool:
    return _PHYSICAL_KEY_NAMES.get(normalize_scan_code(native_scan_code), "").startswith("Num ")


def _default_physical_binding(spec: BindingSpec) -> Binding:
    source, token, ctrl, shift, alt = _binding_spec_to_binding(spec)
    return (source, physical_key_token(_TOKEN_TO_QWERTY_SCANCODE[token]), ctrl, shift, alt)


def normalize_key_event_physical(
    native_scan_code: int, *, shift: bool, ctrl: bool, alt: bool = False,
    key_name: str = "", keypad: bool = False,
) -> Binding | None:
    scan = normalize_scan_code(native_scan_code)
    if scan in _MODIFIER_SCANS:
        return None
    if scan == 0:
        name = str(key_name or "").strip().lower()
        if keypad:
            name = {"end": "1", "down": "2", "pagedown": "3", "page down": "3",
                    "left": "4", "clear": "5", "right": "6", "home": "7", "up": "8",
                    "pageup": "9", "page up": "9", "insert": "0", "delete": ".",
                    "return": "enter"}.get(name, name)
            name = "num " + name
        scan = _KEY_NAME_TO_SCAN.get(name, 0)
    if scan not in _PHYSICAL_KEY_NAMES:
        return None
    return ("keyboard", physical_key_token(scan), bool(ctrl), bool(shift), bool(alt))


def binding_reserved_reason(binding: Binding) -> str | None:
    source, token, ctrl, _shift, alt = binding
    if source != "keyboard" or not token.startswith("scan:"):
        return None
    scan = int(token[5:], 16)
    if scan in {0xE05B, 0xE05C}:
        return "The Windows key is reserved for system shortcuts."
    if scan == 0xE053:
        return "Delete clears the selected note's binding in the keybinding editor."
    if scan == 0x39:
        return "Space is reserved for sustain."
    if scan in {0xE048, 0xE050, 0xE04B, 0xE04D}:
        return "Arrow keys are reserved for volume and transposition."
    if scan == 0x0F:
        return "Tab is reserved for moving between controls."
    if scan == 0x01:
        return "Escape is reserved for closing or leaving controls."
    if ctrl and not alt:
        if not _LABEL_CACHE:
            refresh_keyboard_labels()
        if (_VIRTUAL_KEY_CACHE.get(scan) == 0x5A
                or _LABEL_CACHE.get((scan, False), _PHYSICAL_KEY_NAMES.get(scan, "")).casefold() == "z"):
            return "Ctrl+Z is reserved for undo in the keybinding editor."
    if alt and scan in {0x3E, 0x0F, 0x01, 0x39}:
        return "This combination is reserved for a Windows shortcut."
    if ctrl and alt and scan == 0xE053:
        return "This combination is reserved for Windows security."
    return None


@lru_cache(maxsize=1)
def _keyboard_api():
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        user32 = ctypes.windll.user32
        signatures = {
            "GetKeyboardLayout": ([ctypes.c_uint], ctypes.c_void_p),
            "MapVirtualKeyExW": ([ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p], ctypes.c_uint),
            "ToUnicodeEx": ([ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(ctypes.c_ubyte),
                             ctypes.c_wchar_p, ctypes.c_int, ctypes.c_uint, ctypes.c_void_p], ctypes.c_int),
            "VkKeyScanExW": ([ctypes.c_wchar, ctypes.c_void_p], ctypes.c_short),
        }
        for name, (args, result) in signatures.items():
            fn = getattr(user32, name)
            fn.argtypes, fn.restype = args, result
        return user32
    except (AttributeError, OSError):
        return None


def keyboard_layout_id() -> int:
    api = _keyboard_api()
    return int(api.GetKeyboardLayout(0) or 0) if api is not None else 0


def _windows_key_label(scan: int, shift: bool, layout: int) -> str | None:
    api = _keyboard_api()
    if api is None or not layout:
        return None
    try:
        import ctypes
        vk = api.MapVirtualKeyExW(scan, 3, layout)
        if not vk:
            return None
        state = (ctypes.c_ubyte * 256)()
        if shift:
            state[0x10] = 0x80
        buf = ctypes.create_unicode_buffer(8)
        written = int(api.ToUnicodeEx(vk, scan, state, buf, len(buf), 4, layout))
        text = buf[:abs(written)]
        if len(text) != 1 or not text.isprintable() or text.isspace():
            return None
        return text
    except (AttributeError, OSError, ValueError):
        return None


def refresh_keyboard_labels(*, force: bool = False) -> bool:
    global _LABEL_LAYOUT
    layout = keyboard_layout_id()
    if not force and _LABEL_LAYOUT == layout:
        return False
    labels: dict[tuple[int, bool], str] = {}
    virtual_keys: dict[int, int] = {}
    api = _keyboard_api()
    for scan, fallback in _PHYSICAL_KEY_NAMES.items():
        if api is not None and layout:
            virtual_keys[scan] = int(api.MapVirtualKeyExW(scan, 3, layout))
        for shift in (False, True):
            if fallback.startswith("Num ") or len(fallback) != 1:
                label = fallback
            else:
                label = _windows_key_label(scan, shift, layout)
                if label is None:
                    label = (_SHIFTED_PUNCTUATION.get(fallback, fallback.upper()) if shift else fallback)
                    if shift and fallback in BASE_DIGIT_TO_SHIFTED_SYMBOL:
                        label = BASE_DIGIT_TO_SHIFTED_SYMBOL[fallback]
            labels[(scan, shift)] = label
    _LABEL_CACHE.clear()
    _LABEL_CACHE.update(labels)
    _VIRTUAL_KEY_CACHE.clear()
    _VIRTUAL_KEY_CACHE.update(virtual_keys)
    _LABEL_LAYOUT = layout
    return True


def _physical_binding_label(binding: Binding, *, compact: bool) -> str:
    _, token, ctrl, shift, alt = binding
    scan = int(token[5:], 16)
    if not _LABEL_CACHE:
        refresh_keyboard_labels()
    base = _LABEL_CACHE.get((scan, shift), _PHYSICAL_KEY_NAMES.get(scan, token))
    plain = _LABEL_CACHE.get((scan, False), base)
    if shift and not ctrl and not alt and base != plain and len(base) == 1:
        return base
    modifiers = []
    if ctrl:
        modifiers.append("C" if compact else "Ctrl")
    if shift:
        modifiers.append("S" if compact else "Shift")
    if alt:
        modifiers.append("A" if compact else "Alt")
    if not modifiers:
        return base
    return f"{'/'.join(modifiers)}\n+\n{base}" if compact else " + ".join(modifiers + [base])


def legacy_layout_scans() -> dict[str, int]:
    scans: dict[str, int] = {}
    for scan, fallback in _QWERTY_SCANCODE_TO_TOKEN.items():
        localized = _localized_label_for_scancode(scan, fallback=fallback)
        scans.setdefault(_normalize_layout_token_for_remap(localized) or fallback, scan)
    return scans


def legacy_binding_to_physical(
    binding: Binding, keyboard_input_mode: str, *, layout_scans: dict[str, int] | None = None,
) -> Binding:
    source, token, ctrl, shift, alt = binding
    if source != "keyboard" or token.startswith("scan:"):
        return binding
    scan = None
    if str(keyboard_input_mode).lower() == "layout":
        scan = (layout_scans if layout_scans is not None else legacy_layout_scans()).get(token)
    if scan is None:
        scan = _TOKEN_TO_QWERTY_SCANCODE.get(token)
    if scan is None and len(token) == 1:
        api = _keyboard_api()
        if api is not None:
            code = int(api.VkKeyScanExW(token, keyboard_layout_id()))
            if code != -1:
                scan = normalize_scan_code(api.MapVirtualKeyExW(code & 0xFF, 4, keyboard_layout_id()))
    if scan not in _PHYSICAL_KEY_NAMES:
        return binding
    return (source, physical_key_token(scan), ctrl, shift, alt)
