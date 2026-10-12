from __future__ import annotations

import ctypes
import sys
import threading

from openpiano.core.fluidsynth_loader import candidate_dll_dirs

_dll = None
_checked = False
_initialization_lock = threading.Lock()


def native_audio_library():
    with _initialization_lock:
        return _native_audio_library()


def _native_audio_library():
    global _dll, _checked
    if _checked:
        return _dll
    _checked = True
    if sys.platform != 'win32':
        return None
    for folder in candidate_dll_dirs():
        path = folder / 'openpiano_audio.dll'
        if not path.is_file():
            continue
        try:
            dll = ctypes.CDLL(str(path))
            dll.op_audio_abi_version.restype = ctypes.c_int
            if dll.op_audio_abi_version() != 1:
                continue
            dll.op_audio_create.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
            dll.op_audio_create.restype = ctypes.c_void_p
            dll.op_audio_destroy.argtypes = [ctypes.c_void_p]
            dll.op_audio_destroy.restype = None
            dll.op_audio_protect.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
            dll.op_audio_protect.restype = ctypes.c_int
            dll.op_audio_envelope.argtypes = [ctypes.c_void_p]
            dll.op_audio_envelope.restype = ctypes.c_double
            dll.op_audio_diagnostics.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_int]
            dll.op_audio_diagnostics.restype = None
            dll.op_audio_stats.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int64)]
            dll.op_audio_stats.restype = None
            if hasattr(dll, 'op_audio_render'):
                dll.op_audio_render.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
                dll.op_audio_render.restype = ctypes.c_int
                dll.op_audio_piano.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
                dll.op_audio_piano.restype = None
            if hasattr(dll, 'op_audio_copy_phase'):
                dll.op_audio_copy_phase.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
                dll.op_audio_copy_phase.restype = None
            if hasattr(dll, 'op_audio_phase'):
                dll.op_audio_phase.argtypes = [ctypes.c_void_p]
                dll.op_audio_phase.restype = ctypes.c_int
            configure_pcm16(dll)
            configure_wasapi(dll)
            _dll = dll
            return dll
        except (OSError, AttributeError):
            continue
    return None


def configure_pcm16(dll) -> bool:
    if not hasattr(dll, 'op_audio_pcm16'):
        return False
    dll.op_audio_pcm16.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
    dll.op_audio_pcm16.restype = ctypes.c_int
    return True


def configure_wasapi(dll) -> bool:
    if not all(hasattr(dll, name) for name in
               ('op_wasapi_open', 'op_wasapi_stop', 'op_wasapi_destroy', 'op_wasapi_stats')):
        return False
    dll.op_wasapi_open.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint,
                                  ctypes.c_wchar_p, ctypes.c_uint, ctypes.POINTER(ctypes.c_int32)]
    dll.op_wasapi_open.restype = ctypes.c_void_p
    for name in ('op_wasapi_stop', 'op_wasapi_destroy'):
        getattr(dll, name).argtypes = [ctypes.c_void_p]
        getattr(dll, name).restype = None
    dll.op_wasapi_stats.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_int64)]
    dll.op_wasapi_stats.restype = None
    return True


class NativeWasapiDriver:

    def __init__(self, limiter, sample_rate: int, periods: int = 3, device_id=None) -> None:
        self.pointer = None
        self.limiter = limiter
        self.dll = limiter.dll
        if not configure_wasapi(self.dll):
            raise RuntimeError('Event-driven WASAPI is unavailable in this audio helper.')
        error = ctypes.c_int32()
        self.pointer = self.dll.op_wasapi_open(limiter.pointer, sample_rate, periods, device_id,
                                               int(getattr(limiter, '_diagnostic', False)), ctypes.byref(error))
        if not self.pointer:
            raise RuntimeError(f'Could not start event-driven WASAPI (0x{error.value & 0xffffffff:08X}).')

    def statistics(self) -> dict[str, int | float]:
        values = (ctypes.c_int64 * 16)()
        if self.pointer:
            self.dll.op_wasapi_stats(self.pointer, values)
        frequency = max(1, values[15])
        return dict(buffer_frames=values[0], period_frames=values[1], empty_refills=values[2],
                    event_timeouts=values[3], submitted_frames=values[4], refills=values[5],
                    max_interval_ms=1000.0 * values[6] / frequency, mmcss=values[7],
                    clock_position=values[8], clock_frequency=values[9],
                    max_render_ms=1000.0 * values[10] / frequency,
                    missed_padding_deadlines=values[11], mix_rate=values[12],
                    error=values[13], running=values[14])

    def stop(self) -> None:
        if self.pointer:
            self.dll.op_wasapi_stop(self.pointer)

    def close(self) -> None:
        if self.pointer:
            self.dll.op_wasapi_destroy(self.pointer)
            self.pointer = None

    def __del__(self) -> None:
        self.close()


class NativePeakLimiter:

    ceiling = 0.95

    def __init__(self, dll, synth_pointer, write_float, sample_rate: int) -> None:
        self.dll = dll
        self._diagnostic = False
        self.pointer = dll.op_audio_create(synth_pointer, ctypes.cast(write_float, ctypes.c_void_p), sample_rate)
        if not self.pointer:
            raise RuntimeError('Could not allocate native audio protection.')

    @property
    def _envelope(self) -> float:
        return self.dll.op_audio_envelope(self.pointer)

    def process(self, left, right, frames: int) -> None:
        if self.dll.op_audio_protect(self.pointer, left, right, frames) != 0:
            raise RuntimeError('Invalid floating-point audio.')

    def render(self, left, right, frames: int) -> bool:
        if not hasattr(self.dll, 'op_audio_render'):
            return False
        if self.dll.op_audio_render(self.pointer, left, right, frames) != 0:
            raise RuntimeError('Native audio rendering failed.')
        return True

    def attach_piano(self, piano) -> None:
        if not hasattr(self.dll, 'op_audio_piano'):
            raise RuntimeError('Native piano rendering is unavailable.')
        self._piano_owner = piano
        self.dll.op_audio_piano(self.pointer, piano.pointer if piano is not None else None)

    def inherit_phase(self, previous) -> None:
        if isinstance(previous, NativePeakLimiter) and hasattr(self.dll, 'op_audio_copy_phase'):
            self.dll.op_audio_copy_phase(self.pointer, previous.pointer)

    def render_phase(self) -> int:
        return self.dll.op_audio_phase(self.pointer)

    def diagnostics(self, *, muted: bool = False) -> None:
        self.dll.op_audio_diagnostics(self.pointer, 1, int(muted))
        self._diagnostic = True

    def statistics(self) -> dict[str, int | float]:
        values = (ctypes.c_int64 * 7)()
        self.dll.op_audio_stats(self.pointer, values)
        frequency = max(1, values[6])
        return dict(blocks=values[0], frames=values[1], max_block_frames=values[2],
                    max_render_ms=1000.0 * values[3] / frequency,
                    max_callback_interval_ms=1000.0 * values[4] / frequency, failures=values[5])

    def close(self) -> None:
        pointer = getattr(self, 'pointer', None)
        if pointer:
            self.dll.op_audio_destroy(pointer)
            self.pointer = None
        owner = getattr(self, '_piano_owner', None)
        if owner is not None:
            owner._outputs.discard(self)
            if owner._current_output is not None and owner._current_output() is self:
                owner._current_output = None
            self._piano_owner = None

    def __del__(self) -> None:
        self.close()
