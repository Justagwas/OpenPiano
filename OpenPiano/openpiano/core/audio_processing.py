from __future__ import annotations

import ctypes
import math
from array import array

from openpiano.core.native_audio import NativePeakLimiter, NativeWasapiDriver, native_audio_library

_FLOAT_POINTER = ctypes.POINTER(ctypes.c_float)
_FLOAT_BUFFERS = ctypes.POINTER(_FLOAT_POINTER)
_AUDIO_CALLBACK = ctypes.CFUNCTYPE(
    ctypes.c_int, ctypes.c_void_p, ctypes.c_int, ctypes.c_int,
    _FLOAT_BUFFERS, ctypes.c_int, _FLOAT_BUFFERS,
)


class PeakLimiter:

    def __init__(self, sample_rate: int, ceiling: float = 0.95) -> None:
        self.ceiling = ceiling
        self._release = math.exp(-1.0 / (0.080 * sample_rate))
        self._envelope = 0.0

    def process(self, left, right, frames: int) -> None:
        peak = 0.0
        for i in range(frames):
            l, r = abs(left[i]), abs(right[i])
            if not math.isfinite(l) or not math.isfinite(r):
                raise RuntimeError('Invalid floating-point audio.')
            peak = max(peak, l, r)
        if peak <= self.ceiling and self._envelope <= self.ceiling:
            self._envelope = 0.0
            return
        envelope, release, ceiling = self._envelope, self._release, self.ceiling
        for i in range(frames):
            envelope = max(abs(left[i]), abs(right[i]), envelope * release)
            if envelope > ceiling:
                gain = ceiling / envelope
                left[i] *= gain
                right[i] *= gain
        self._envelope = envelope


class SynthOutput:

    def __init__(self, module, synth, sample_rate: int) -> None:
        self._failures = 0
        self.device_output = None
        self._synth_pointer = synth.synth
        self.limiter = PeakLimiter(sample_rate)
        self._write_float = module.cfunc(
            "fluid_synth_write_float", ctypes.c_int,
            ("synth", ctypes.c_void_p, 1), ("frames", ctypes.c_int, 1),
            ("left", ctypes.c_void_p, 1), ("left_offset", ctypes.c_int, 1),
            ("left_stride", ctypes.c_int, 1), ("right", ctypes.c_void_p, 1),
            ("right_offset", ctypes.c_int, 1), ("right_stride", ctypes.c_int, 1),
        )
        dll = native_audio_library()
        self._pcm16 = getattr(dll, 'op_audio_pcm16', None)
        self.callback_data = None
        if dll is not None and isinstance(self._write_float, ctypes._CFuncPtr):
            self.limiter = NativePeakLimiter(dll, self._synth_pointer, self._write_float, sample_rate)
            previous = getattr(synth, '_openpiano_output', None)
            self.limiter.inherit_phase(getattr(previous, 'limiter', None))
            self.callback = ctypes.cast(dll.op_audio_callback, _AUDIO_CALLBACK)
            self.callback_data = self.limiter.pointer
        else:
            self.callback = _AUDIO_CALLBACK(self._audio_callback)
        piano = getattr(synth, '_openpiano_piano_damping', None)
        if piano is not None and piano.enabled:
            piano.attach(self)

    def render(self, left, right, frames: int) -> None:
        native_rendered = isinstance(self.limiter, NativePeakLimiter) and self.limiter.render(left, right, frames)
        result = 0 if native_rendered else self._write_float(self._synth_pointer, frames, left, 0, 1, right, 0, 1)
        if result != 0:
            raise RuntimeError("FluidSynth could not render floating-point audio.")
        self.limiter.process(left, right, frames)

    def _audio_callback(self, _data, frames, _nfx, _fx, nout, out) -> int:
        try:
            if nout < 2:
                return -1
            self.render(out[0], out[1], frames)
            return 0
        except Exception:
            self._failures += 1
            for channel in range(nout):
                ctypes.memset(out[channel], 0, frames * ctypes.sizeof(ctypes.c_float))
            return -1

    def failure_count(self) -> int:
        if self.device_output is not None:
            health = self.device_output.statistics()
            error = health['error']
            if error:
                raise RuntimeError(f'Windows audio output failed (0x{error & 0xffffffff:08X}).')
            if health.get('event_timeouts', 0):
                raise RuntimeError('Windows audio output stopped receiving timely audio-ready events.')
        if isinstance(self.limiter, NativePeakLimiter):
            return int(self.limiter.statistics()['failures'])
        return self._failures

    def close(self) -> None:
        if self.device_output is not None:
            self.device_output.close()
            self.device_output = None
        if isinstance(self.limiter, NativePeakLimiter):
            self.limiter.close()
        self.callback_data = None

    def pcm16(self, frames: int) -> bytes:
        left = (ctypes.c_float * frames)()
        right = (ctypes.c_float * frames)()
        self.render(left, right, frames)
        if self._pcm16 is not None:
            pcm = (ctypes.c_uint8 * (frames * 4))()
            if self._pcm16(left, right, frames, pcm) != 0:
                raise RuntimeError('Invalid floating-point audio during PCM conversion.')
            return bytes(pcm)
        pcm = array("h")
        for i in range(frames):
            pcm.append(max(-32768, min(32767, round(left[i] * 32767.0))))
            pcm.append(max(-32768, min(32767, round(right[i] * 32767.0))))
        return pcm.tobytes()


def start_protected_audio_driver(module, synth, sample_rate: int, *, wasapi_periods=None) -> None:
    previous = getattr(synth, '_openpiano_output', None)
    output = SynthOutput(module, synth, sample_rate)
    if (wasapi_periods is not None and isinstance(output.limiter, NativePeakLimiter)
            and hasattr(output.limiter.dll, 'op_wasapi_open')):
        try:
            output.device_output = NativeWasapiDriver(output.limiter, sample_rate, wasapi_periods)
        except Exception:
            output.close()
            raise
        synth.audio_driver = None
        synth._openpiano_output = output
        if previous is not None:
            previous.close()
        return
    try:
        create_driver = module.cfunc(
            "new_fluid_audio_driver2", ctypes.c_void_p,
            ("settings", ctypes.c_void_p, 1), ("callback", _AUDIO_CALLBACK, 1),
            ("data", ctypes.c_void_p, 1),
        )
        synth._openpiano_output = output
        synth.audio_driver = create_driver(synth.settings, output.callback, output.callback_data)
        if not synth.audio_driver:
            raise RuntimeError("Could not start the protected FluidSynth audio driver.")
    except Exception:
        synth._openpiano_output = previous
        output.close()
        raise
    if previous is not None:
        previous.close()
