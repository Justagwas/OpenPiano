from __future__ import annotations


class AudioOutputError(RuntimeError):
    def __init__(self, message: str, code: int) -> None:
        self.code = code & 0xffffffff
        super().__init__(f'{message} (0x{self.code:08X}).')

    @property
    def allows_fallback(self) -> bool:
        return self.code in {0x88890008, 0x88890016, 0x88890019, 0x88890020}


class AudioOutputUnavailable(AudioOutputError):
    def __init__(self) -> None:
        super().__init__('No audio output device is available. Connect or enable an output device and retry', 0x80070490)
