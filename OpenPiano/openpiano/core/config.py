
from __future__ import annotations

from typing import Literal

APP_NAME = "OpenPiano"
APP_VERSION = "1.0.1"
OFFICIAL_WEBSITE_URL = "https://www.justagwas.com/projects/openpiano"

UPDATE_CHECK_MANIFEST_URL = "https://www.justagwas.com/projects/openpiano/latest.json"
UPDATE_GITHUB_LATEST_URL = "https://github.com/Justagwas/OpenPiano/releases/latest"
UPDATE_GITHUB_DOWNLOAD_URL = "https://www.justagwas.com/projects/a2m/download"
UPDATE_SOURCEFORGE_RSS_URL = "https://sourceforge.net/projects/openpiano/rss?path=/"

DEFAULT_THEME_MODE: Literal["dark", "light"] = "dark"
DEFAULT_MASTER_VOLUME = 0.60
DEFAULT_NOTE_VELOCITY = 100

TRANSPOSE_MIN = -21
TRANSPOSE_MAX = 21
SUSTAIN_PERCENT_MIN = 0
SUSTAIN_PERCENT_MAX = 100
NOTE_VELOCITY_MIN = 1
NOTE_VELOCITY_MAX = 127

INSTRUMENT_BANK_MIN = 0
INSTRUMENT_BANK_MAX = 16383
INSTRUMENT_PRESET_MIN = 0
INSTRUMENT_PRESET_MAX = 127

UI_SCALE_MIN = 0.50
UI_SCALE_MAX = 2.00
UI_SCALE_STEP = 0.05

STATS_TICK_MS = 200
SUSTAIN_TICK_MS = 40
KPS_WINDOW_SECONDS = 1.0

AnimationSpeed = Literal["instant", "fast", "normal", "slow", "very_slow"]
ANIMATION_PROFILE: dict[AnimationSpeed, tuple[int, int, int, int]] = {
    "instant": (0, 0, 0, 0),
    "fast": (2, 6, 2, 10),
    "normal": (3, 10, 3, 16),
    "slow": (4, 12, 4, 18),
    "very_slow": (5, 15, 5, 22),
}

STATS_ORDER = ("volume", "sustain", "kps", "held", "polyphony", "transpose")
STAT_TITLES: dict[str, str] = {
    "volume": "Volume",
    "sustain": "Sustain (Space)",
    "kps": "KPS",
    "held": "Held Keys",
    "polyphony": "Polyphony",
    "transpose": "Transpose",
}
