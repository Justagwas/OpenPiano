from __future__ import annotations

import ctypes
import time
import weakref
from pathlib import Path

from openpiano.core.native_audio import NativePeakLimiter, native_audio_library
from openpiano.core.piano_key_release import _matches_asset
from openpiano.core.piano_preroll import PianoPreroll, PianoReplayEvent

_RECAPTURE_ASSETS = {
    '904888b533b80b0ac4cdf29a67f4ef4b3750e80c527a3490ec3f683919e70356': 396148602,
    '61e395a1755b9551c64bf78738e70f4e87354017feeb1dbc681a369389cd438a': 396062522,
    'f46a12ccb9eb48b97f85d21d670d1051d546ff91d362e1bff7ab27bba2596ab6': 396062650,
}


def staged_piano_damping(module, synth, sample_rate: int, path: Path, bank: int, preset: int,
                        *, half_pedal: bool = False, contact_blend: bool = False, capabilities=None):
    if (bank, preset) != (0, 0) or not _matches_asset(path, _RECAPTURE_ASSETS, capabilities=capabilities):
        return None
    existing = getattr(synth, '_openpiano_piano_damping', None)
    if existing is not None:
        existing.activate(half_pedal=half_pedal, contact_blend=contact_blend)
        return existing
    return NativePianoDamping(module, synth, sample_rate, half_pedal=half_pedal,
                              contact_blend=contact_blend)


class NativePianoDamping:

    def __init__(self, module, synth, sample_rate: int, *, half_pedal: bool = False,
                 contact_blend: bool = False) -> None:
        if contact_blend and not half_pedal:
            raise ValueError('Contact blending requires experimental half-pedal.')
        dll = native_audio_library()
        library = getattr(module, '_fl', None)
        if (dll is None or library is None or not hasattr(dll, 'op_piano_abi_version')
                or not hasattr(dll, 'op_audio_phase')):
            raise RuntimeError('Native piano damping is unavailable.')
        dll.op_piano_abi_version.restype = ctypes.c_int
        self._abi = dll.op_piano_abi_version()
        if self._abi not in (2, 3) or (half_pedal and self._abi < 3):
            raise RuntimeError('Incompatible native piano damping.')
        buffer_size = module.cfunc('fluid_synth_get_internal_bufsize', ctypes.c_int,
            ('synth', ctypes.c_void_p, 1))
        if (synth.get_setting('synth.threadsafe-api') != 1
                or buffer_size(synth.synth) != 64
                or synth.get_setting('synth.sample-rate') != sample_rate
                or synth.get_setting('synth.polyphony') > 1024):
            raise RuntimeError('Unsupported FluidSynth configuration for piano recapture.')
        dll.op_piano_create.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
        dll.op_piano_create.restype = ctypes.c_void_p
        dll.op_piano_command.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
        dll.op_piano_command.restype = ctypes.c_int
        dll.op_piano_destroy.argtypes = [ctypes.c_void_p]
        dll.op_piano_destroy.restype = None
        self.dll = dll
        self._module = module
        self._outputs = weakref.WeakSet()
        self._current_output = None
        self._sample_rate = sample_rate
        self._released_notes: set[int] = set()
        self._pedal_value = 0
        self._physical_notes: set[int] = set()
        self._owned_notes: set[int] = set()
        self._history = PianoPreroll()
        self.pointer = dll.op_piano_create(synth.synth, library._handle, sample_rate)
        if not self.pointer:
            raise RuntimeError('Could not create native piano damping.')
        self._command(0, 6)
        self.half_pedal = bool(half_pedal)
        self.contact_blend = bool(contact_blend)
        if self._abi >= 3:
            self._command(int(self.half_pedal), 9)
        self.enabled = True
        owners = getattr(synth, '_openpiano_piano_owners', None)
        if owners is None:
            owners = synth._openpiano_piano_owners = []
        owners.append(self)
        synth._openpiano_piano_damping = self
        output = getattr(synth, '_openpiano_output', None)
        if output is not None:
            self.attach(output)

    def _command(self, key: int, operation: int) -> int:
        result = self.dll.op_piano_command(self.pointer, int(key), operation)
        if result < 0:
            raise RuntimeError('Native piano command failed.')
        return result

    def attach(self, output) -> None:
        if not isinstance(output.limiter, NativePeakLimiter):
            raise RuntimeError('Piano recapture requires the native renderer.')
        output.limiter.attach_piano(self)
        self._outputs.add(output.limiter)
        self._current_output = weakref.ref(output.limiter)

    def press(self, note: int, velocity: int = 100, *, at_seconds: float | None = None,
              key_held: bool = True, strike_age_seconds: float = 0.0) -> None:
        self._command(note, 1)
        self._released_notes.discard(note)
        self._owned_notes.add(note)
        if key_held:
            self._physical_notes.add(note)
        else:
            self._physical_notes.discard(note)
        self._remember('note_on', note, velocity, at_seconds, key_held, strike_age_seconds)

    def _remember(self, kind, note=0, velocity=0, at_seconds=None,
                   key_held=True, strike_age_seconds=0.0) -> None:
        point = time.monotonic() if at_seconds is None else float(at_seconds)
        output = self._current_output() if self._current_output is not None else None
        phase = output.render_phase() if output is not None else 0
        self._history.remember(PianoReplayEvent(point, kind, note, velocity, key_held, strike_age_seconds),
                               phase_seconds=phase / self._sample_rate)

    def key_release(self, note: int, *, at_seconds: float | None = None) -> None:
        if note in self._physical_notes:
            self._physical_notes.discard(note)
            self._remember('key_release', note, at_seconds=at_seconds)

    def recording_preroll(self, now: float):
        if not any(self.damping_loss(note) is not None for note in self._released_notes):
            return None
        return self._history.snapshot(now)

    def damp(self, note: int, *, at_seconds: float | None = None) -> bool:
        captured = bool(self._command(note, 2))
        if captured:
            self._released_notes.add(note)
        if note in self._owned_notes:
            self._owned_notes.discard(note)
            self._remember('note_off', note, at_seconds=at_seconds)
        return captured

    def damping_loss(self, note: int) -> float | None:
        value = self._command(note, 8)
        return (value - 1) / 10.0 if value else None

    @property
    def contact_strength(self) -> float:
        if not self.contact_blend:
            return 1.0
        position = min(self._pedal_value, 64) / 64.0
        return (1.0 - position) ** 2 * (1.0 + 2.0 * position)

    def pedal(self, value: int, *, at_seconds: float | None = None) -> list[tuple[int, float]]:
        value = max(0, min(127, int(value)))
        previous = self._pedal_value
        self._command(value, 3)
        self._pedal_value = value
        self._remember('pedal', velocity=value, at_seconds=at_seconds)
        contacts = []
        if previous >= 64 > value:
            for note in sorted(self._released_notes):
                loss = self.damping_loss(note)
                if loss is None:
                    self._released_notes.discard(note)
                else:
                    contacts.append((note, loss))
        return contacts

    def clear(self) -> None:
        self._command(0, 4)
        self._released_notes.clear()
        self._pedal_value = 0
        self._physical_notes.clear()
        self._owned_notes.clear()
        self._history.clear()

    def disable(self) -> None:
        self._command(0, 7)
        self._released_notes.clear()
        self._pedal_value = 0
        self._physical_notes.clear()
        self._owned_notes.clear()
        self._history.clear()
        self.enabled = False
        for limiter in self._outputs:
            limiter.attach_piano(None)

    def activate(self, *, half_pedal: bool | None = None,
                 contact_blend: bool | None = None) -> None:
        mode = self.half_pedal if half_pedal is None else bool(half_pedal)
        blend = self.contact_blend if contact_blend is None else bool(contact_blend)
        if blend and not mode:
            raise ValueError('Contact blending requires experimental half-pedal.')
        if mode and self._abi < 3:
            raise RuntimeError('Native half-pedal damping is unavailable.')
        self._command(0, 6)
        if self._abi >= 3:
            self._command(int(mode), 9)
        self.half_pedal = mode
        self.contact_blend = blend
        self._released_notes.clear()
        self._pedal_value = 0
        self._physical_notes.clear()
        self._owned_notes.clear()
        self._history.clear()
        self.enabled = True
        for limiter in self._outputs:
            limiter.attach_piano(self)

    def close(self) -> None:
        pointer = getattr(self, 'pointer', None)
        if pointer:
            self.dll.op_piano_destroy(pointer)
            self.pointer = None

    def __del__(self) -> None:
        self.close()
