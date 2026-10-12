from __future__ import annotations

import bisect
import math
import time
from openpiano.core.native_result import check_native_result

from openpiano.core.piano_resonance_profile import (
    AGE_TIMES, BODY_ATTENUATION_DB, LAYER_BOUNDARIES, PROFILE, SOURCE_DURATIONS, VELOCITIES,
)


RESONANCE_CHANNELS = (2, 3, 4)
RESONANCE_GAIN_RANGE_DB = 48.0
RESONANCE_ASSETS = {
    'eb43e83208d3a7ba630f5c10dda9f8dee9579c45307aef852e0b09421bebe765': 396148078,
    '904888b533b80b0ac4cdf29a67f4ef4b3750e80c527a3490ec3f683919e70356': 396148602,
    '61e395a1755b9551c64bf78738e70f4e87354017feeb1dbc681a369389cd438a': 396062522,
    'f46a12ccb9eb48b97f85d21d670d1051d546ff91d362e1bff7ab27bba2596ab6': 396062650,
}
_INTENSITY_ANCHORS = (32, 80, 112)


def _interpolate(points, values, position: float) -> float:
    right = bisect.bisect_right(points, position)
    if right == 0:
        return values[0]
    if right == len(points):
        return values[-1]
    left = right - 1
    fraction = (position - points[left]) / (points[right] - points[left])
    return values[left] + fraction * (values[right] - values[left])


def resonance_voices(note: int, velocity: int, age_seconds: float, *,
                     damping_loss_db: float = 0.0,
                     contact_strength: float = 1.0) -> list[tuple[int, int]]:
    if (not 21 <= note < 89 or not math.isfinite(age_seconds)
            or not math.isfinite(damping_loss_db)
            or not math.isfinite(contact_strength) or not 0.0 < contact_strength <= 1.0):
        return []
    root = 21 + 3 * ((note - 20) // 3)
    root = max(21, min(87, root))
    levels, *decays = PROFILE[root]
    velocity = max(1, min(127, int(velocity)))
    age = max(0.0, age_seconds) * 2 ** ((note - root) / 12)
    main_layer = bisect.bisect_right(LAYER_BOUNDARIES, velocity) - 1
    if age >= SOURCE_DURATIONS[root][main_layer]:
        return []
    age_levels = tuple(_interpolate((0.0, *AGE_TIMES), (0.0, *curve), age) for curve in decays)
    attenuation = _interpolate(VELOCITIES, levels, velocity) - levels[-1]
    attenuation += _interpolate(_INTENSITY_ANCHORS, age_levels, velocity)
    attenuation -= max(0.0, damping_loss_db)
    attenuation += 10.0 * math.log10(contact_strength)
    layer = bisect.bisect_left((56, 96), velocity)
    gain_db = attenuation - BODY_ATTENUATION_DB[note][layer]
    if gain_db <= -RESONANCE_GAIN_RANGE_DB:
        return []
    level = max(1, min(127, round(127 * (1 + gain_db / RESONANCE_GAIN_RANGE_DB))))
    return [(RESONANCE_CHANNELS[layer], level)]


class PianoReleaseResonance:

    def __init__(self, synth, sfid: int, bank: int) -> None:
        self.synth = synth
        self.sfid = sfid
        self.bank = bank
        self._strikes: dict[int, tuple[int, float]] = {}
        self.select_program()

    def select_program(self) -> None:
        for program, channel in enumerate(RESONANCE_CHANNELS, start=1):
            result = self.synth.program_select(channel, self.sfid, self.bank, program)
            if result is not None and int(result) < 0:
                raise RuntimeError('Could not select the piano release-resonance recordings.')

    def press(self, note: int, velocity: int, *, at_seconds: float | None = None,
              strike_age_seconds: float = 0.0) -> None:
        point = time.monotonic() if at_seconds is None else float(at_seconds)
        age = float(strike_age_seconds)
        age = max(0.0, age) if math.isfinite(age) else 0.0
        self._strikes[note] = (max(1, min(127, int(velocity))), point - age)

    def damp(self, note: int, *, at_seconds: float | None = None, enabled: bool = True,
             retain: bool = False, damping_loss_db: float = 0.0,
             contact_strength: float = 1.0) -> None:
        strike = (self._strikes.get(note) if retain and enabled else self._strikes.pop(note, None))
        if strike is None or not enabled:
            return
        point = time.monotonic() if at_seconds is None else float(at_seconds)
        velocity, started_at = strike
        for channel, level in resonance_voices(note, velocity, point - started_at,
                                              damping_loss_db=damping_loss_db,
                                              contact_strength=contact_strength):
            check_native_result(self.synth.noteon(channel, note, level), 'play release resonance')

    def stop(self) -> None:
        self._strikes.clear()
        for channel in RESONANCE_CHANNELS:
            check_native_result(self.synth.cc(channel, 120, 0), 'silence release resonance')
