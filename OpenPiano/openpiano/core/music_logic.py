
from __future__ import annotations


def clamp_transposed_note(base_note: int, transpose: int, min_note: int, max_note: int) -> int:
    return max(min_note, min(max_note, base_note + transpose))


def sustain_hold_ms(percent: int) -> int | None:
    clamped = max(0, min(100, int(percent)))
    if clamped <= 0:
        return 0
    if clamped >= 100:
        return None
    return int(80 + (clamped / 99.0) * 2320)

