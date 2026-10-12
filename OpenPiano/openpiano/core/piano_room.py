from __future__ import annotations

import ctypes
from pathlib import Path
from openpiano.core.native_result import check_native_result

from openpiano.core.piano_key_release import _matches_asset


_ROOM_ASSETS = {
    'eb43e83208d3a7ba630f5c10dda9f8dee9579c45307aef852e0b09421bebe765': 396148078,
    '904888b533b80b0ac4cdf29a67f4ef4b3750e80c527a3490ec3f683919e70356': 396148602,
    '61e395a1755b9551c64bf78738e70f4e87354017feeb1dbc681a369389cd438a': 396062522,
    'f46a12ccb9eb48b97f85d21d670d1051d546ff91d362e1bff7ab27bba2596ab6': 396062650,
}
ROOM_PARAMETERS = {'roomsize': .25, 'damp': .65, 'width': .35, 'level': .13}
ROOM_SEND = 60
_CHANNELS = range(5)
_CONTROLLERS = (1, 7, 10, 11, 64, 66, 67, 91, 93)


def has_piano_room(path: Path, *, capabilities=None) -> bool:
    return _matches_asset(path, _ROOM_ASSETS, capabilities=capabilities)


class PianoRoom:

    def __init__(self, synth, setters, reverb_on) -> None:
        self.synth = synth
        self._setters = setters
        self._reverb_on = reverb_on
        self._baseline = {name: float(getattr(synth, 'get_reverb_' + name)())
                          for name in ROOM_PARAMETERS}
        self._baseline_active = int(bool(synth.get_setting('synth.reverb.active')))
        self._baseline_sends = [synth.get_cc(channel, 91) for channel in _CHANNELS]
        self.active = False
        self._muted = False

    @classmethod
    def create(cls, synth, module) -> PianoRoom | None:
        binder = getattr(module, 'cfunc', None)
        if not callable(binder) or not all(callable(getattr(synth, 'get_reverb_' + name, None))
                                          for name in ROOM_PARAMETERS):
            return None
        try:
            setters = {name: binder('fluid_synth_set_reverb_group_' + name, ctypes.c_int,
                                   ('synth', ctypes.c_void_p, 1), ('group', ctypes.c_int, 1),
                                   ('value', ctypes.c_double, 1)) for name in ROOM_PARAMETERS}
            reverb_on = binder('fluid_synth_reverb_on', ctypes.c_int,
                               ('synth', ctypes.c_void_p, 1), ('group', ctypes.c_int, 1),
                               ('on', ctypes.c_int, 1))
            if not all(setters.values()) or reverb_on is None:
                return None
            return cls(synth, setters, reverb_on)
        except (AttributeError, TypeError, ValueError):
            return None

    def _reset(self) -> None:
        programs = [self.synth.program_info(channel) for channel in _CHANNELS]
        controls = [{cc: self.synth.get_cc(channel, cc) for cc in _CONTROLLERS}
                    for channel in _CHANNELS]
        if self.synth.system_reset() < 0:
            raise RuntimeError('Could not clear the piano room.')
        for channel, (sfid, bank, program) in enumerate(programs):
            if sfid >= 0 and self.synth.program_select(channel, sfid, bank, program) < 0:
                raise RuntimeError('Could not restore the piano program after room reset.')
        for channel, values in enumerate(controls):
            for cc, value in values.items():
                if self.synth.get_cc(channel, cc) != value:
                    check_native_result(self.synth.cc(channel, cc, value), 'restore a piano controller')
        self._stop_voices()

    def _stop_voices(self) -> None:
        for channel in _CHANNELS:
            check_native_result(self.synth.cc(channel, 120, 0), 'silence room voices')

    def _parameters(self, values: dict[str, float], active: int) -> None:
        for name, value in values.items():
            if self._setters[name](self.synth.synth, -1, value) < 0:
                raise RuntimeError('Could not configure the piano room.')
        if self._reverb_on(self.synth.synth, -1, active) < 0:
            raise RuntimeError('Could not enable the piano room.')

    def activate(self) -> None:
        self._reset()
        self.active = True
        self._parameters(ROOM_PARAMETERS, 1)
        for channel in _CHANNELS:
            check_native_result(self.synth.cc(channel, 91, ROOM_SEND if channel == 0 else 0), 'set the room send')
        self._stop_voices()
        self._muted = False

    def clear(self) -> None:
        if self.active:
            self._reset()
            if self._reverb_on(self.synth.synth, -1, 0) < 0:
                raise RuntimeError('Could not silence the piano room.')
            self._muted = True

    def resume(self) -> None:
        if self.active and self._muted:
            self._reset()
            if self._reverb_on(self.synth.synth, -1, 1) < 0:
                raise RuntimeError('Could not resume the piano room.')
            self._muted = False

    def close(self) -> None:
        if not self.active:
            return
        self._reset()
        self._parameters(self._baseline, self._baseline_active)
        for channel, send in enumerate(self._baseline_sends):
            check_native_result(self.synth.cc(channel, 91, send), 'restore the room send')
        self._stop_voices()
        self.active = False
        self._muted = False
