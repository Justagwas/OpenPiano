from __future__ import annotations

from typing import Any


def clamp_int(value: Any, minimum: int, maximum: int, *, default: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        parsed = int(default)
    return max(int(minimum), min(int(maximum), parsed))


def clamp_float(value: Any, minimum: float, maximum: float, *, default: float) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = float(default)
    return max(float(minimum), min(float(maximum), parsed))


def quantize_step(value: float, minimum: float, maximum: float, step: float, *, digits: int = 2) -> float:
    clamped = max(float(minimum), min(float(maximum), float(value)))
    steps = round((clamped - float(minimum)) / float(step))
    quantized = float(minimum) + (steps * float(step))
    return round(max(float(minimum), min(float(maximum), quantized)), int(digits))
