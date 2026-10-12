from __future__ import annotations

import hashlib
from pathlib import Path
from openpiano.core.native_result import check_native_result

from openpiano.core.piano_release_resonance import PianoReleaseResonance, RESONANCE_ASSETS

KEY_RELEASE_BANK = 16383
KEY_RELEASE_CHANNEL = 1
KEY_RELEASE_POLYPHONY = 1024

_KEY_RELEASE_ASSETS: dict[str, int] = {
    '4ee21ac1d95c7091a70a5a5437d1f6dd8c8c16d6013e9e5a4cc0ef9dfd46489e': 391264506,
    '2201c2486758715cbb0049df9aafd26030efbe9928861fee0b5b186893510af2': 391264510,
    '25d3f493d81786629c2b3174677196384f89e9129fbaf8bd6cedd1c61b391cd6': 391265676,
    **RESONANCE_ASSETS,
}


def has_piano_key_release(path: Path, *, capabilities=None) -> bool:
    return _matches_asset(path, _KEY_RELEASE_ASSETS, capabilities=capabilities)


def has_piano_release_resonance(path: Path, *, capabilities=None) -> bool:
    return _matches_asset(path, RESONANCE_ASSETS, capabilities=capabilities)


def _matches_asset(path: Path, assets: dict[str, int], *, capabilities=None) -> bool:
    if capabilities is not None:
        return capabilities.matches(assets)
    if path.stat().st_size not in assets.values():
        return False
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest() in assets


class PianoKeyRelease:

    def __init__(self, synth, sfid: int, polyphony: int, *, resonance: bool = False) -> None:
        self.synth = synth
        self.sfid = sfid
        self._physical_notes: set[int] = set()
        self.resonance = PianoReleaseResonance(synth, sfid, KEY_RELEASE_BANK) if resonance else None
        self.select_program()
        synth.setting('synth.polyphony', max(int(polyphony), KEY_RELEASE_POLYPHONY))

    def select_program(self) -> None:
        result = self.synth.program_select(KEY_RELEASE_CHANNEL, self.sfid, KEY_RELEASE_BANK, 0)
        if result is not None and int(result) < 0:
            raise RuntimeError('Could not select the piano key-release recordings.')
        if self.resonance is not None:
            self.resonance.select_program()

    def press(self, note: int, velocity: int = 100, *, key_held: bool = True,
              at_seconds: float | None = None, strike_age_seconds: float = 0.0) -> None:
        if self.resonance is not None:
            self.resonance.press(note, velocity, at_seconds=at_seconds, strike_age_seconds=strike_age_seconds)
        if key_held:
            self._physical_notes.add(note)
        else:
            self._physical_notes.discard(note)

    def release(self, note: int) -> None:
        if note not in self._physical_notes:
            return
        self._physical_notes.discard(note)
        if 21 <= note <= 108:
            check_native_result(self.synth.noteon(KEY_RELEASE_CHANNEL, note, 100), 'play the key release')

    def stop(self) -> None:
        self._physical_notes.clear()
        check_native_result(self.synth.cc(KEY_RELEASE_CHANNEL, 120, 0), 'silence key releases')
        if self.resonance is not None:
            self.resonance.stop()

    def damp(self, note: int, *, at_seconds: float | None = None, enabled: bool = True,
             retain: bool = False, damping_loss_db: float = 0.0,
             contact_strength: float = 1.0) -> None:
        if self.resonance is not None:
            self.resonance.damp(note, at_seconds=at_seconds, enabled=enabled,
                                retain=retain, damping_loss_db=damping_loss_db,
                                contact_strength=contact_strength)

    def forget(self, note: int) -> None:
        self._physical_notes.discard(note)
