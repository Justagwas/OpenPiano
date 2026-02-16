from __future__ import annotations

import sys

WINDOWS_OUTPUT_DRIVERS: tuple[str, ...] = ("dsound", "winmme", "wasapi")


def list_output_drivers() -> list[str]:
    if sys.platform == "win32":
        return list(WINDOWS_OUTPUT_DRIVERS)
    return []


def default_output_driver() -> str:
    if sys.platform == "win32":
        return WINDOWS_OUTPUT_DRIVERS[0]
    return ""
