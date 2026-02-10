
from __future__ import annotations

import time
from collections import deque
from typing import Mapping, Sequence


def trim_kps_events(events: deque[float], window_seconds: float, now: float | None = None) -> None:
    instant = time.monotonic() if now is None else float(now)
    cutoff = instant - float(window_seconds)
    while events and events[0] < cutoff:
        events.popleft()


def collect_stats_values(
    *,
    volume: float,
    sustain_percent: int,
    sustain_temporarily_off: bool,
    transpose: int,
    note_sources: Mapping[int, set[str]],
    sustained_notes: Mapping[int, float | None],
    kps_events: deque[float],
    kps_window_seconds: float,
    stats_order: Sequence[str],
) -> dict[str, str]:
    now = time.monotonic()
    trim_kps_events(kps_events, kps_window_seconds, now=now)

    held = len(note_sources)
    polyphony = len(set(note_sources.keys()) | set(sustained_notes.keys()))
    kps_value = len(kps_events) / float(kps_window_seconds)

    if sustain_temporarily_off or sustain_percent <= 0:
        sustain_text = "OFF  0%"
    elif sustain_percent >= 100:
        sustain_text = "ON 100%"
    else:
        sustain_text = f"ON {sustain_percent:>3d}%"

    values = {
        "volume": f"{int(round(float(volume) * 100)):03d}%",
        "sustain": sustain_text,
        "kps": f"{kps_value:04.1f}",
        "held": f"{held:03d}",
        "polyphony": f"{polyphony:03d}",
        "transpose": f"{int(transpose):+03d}",
    }
    return {key: values.get(key, "") for key in stats_order}
