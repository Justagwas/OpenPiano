from __future__ import annotations

import math
from pathlib import Path

from openpiano.core.config import DEFAULT_MASTER_VOLUME, MASTER_VOLUME_MAX
from openpiano.core.normalize import clamp_float
from openpiano.core.soundfont_levels import preset_gain
from openpiano.core.soundfont_capabilities import SoundFontCapabilities


def normalize_volume(value: object) -> float:
    try:
        if not math.isfinite(float(value)):
            return DEFAULT_MASTER_VOLUME
    except (TypeError, ValueError, OverflowError):
        return DEFAULT_MASTER_VOLUME
    return clamp_float(value, 0.0, MASTER_VOLUME_MAX, default=DEFAULT_MASTER_VOLUME)


def playback_gain(
    volume: object, soundfont_path: str | Path | None, bank: int, preset: int,
    *, capabilities: SoundFontCapabilities | None = None,
) -> float:
    return normalize_volume(volume) * preset_gain(capabilities, bank, preset)
