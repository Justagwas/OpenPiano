from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path


def _identity(path: Path) -> tuple[int, int, int, int]:
    stat = path.stat()
    return stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns


@dataclass(frozen=True, slots=True)
class SoundFontCapabilities:
    path: Path
    identity: tuple[int, int, int, int]
    digest: str | None

    def matches(self, assets: dict[str, int]) -> bool:
        return self.digest in assets and assets[self.digest] == self.identity[2]

    def validate_unchanged(self) -> None:
        if _identity(self.path) != self.identity:
            raise RuntimeError('SoundFont changed during loading.')


def inspect_soundfont(path: Path, *, stop_event=None) -> SoundFontCapabilities:
    from openpiano.core.piano_key_release import _KEY_RELEASE_ASSETS
    from openpiano.core.piano_room import _ROOM_ASSETS
    from openpiano.core.piano_damping import _RECAPTURE_ASSETS
    from openpiano.core.soundfont_loading import _MIN_PARALLEL_BYTES
    from openpiano.core.soundfont_levels import CALIBRATED_ASSETS

    path = Path(path).resolve()
    before = _identity(path)
    if stop_event is not None and stop_event.is_set():
        raise InterruptedError('SoundFont loading cancelled.')
    known_sizes = (set(_KEY_RELEASE_ASSETS.values()) | set(_ROOM_ASSETS.values())
                   | set(_RECAPTURE_ASSETS.values()) | set(CALIBRATED_ASSETS.values()))
    digest = None
    if before[2] in known_sizes or (path.suffix.lower() == '.sf3' and before[2] > _MIN_PARALLEL_BYTES):
        with path.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
    result = SoundFontCapabilities(path, before, digest)
    result.validate_unchanged()
    if stop_event is not None and stop_event.is_set():
        raise InterruptedError('SoundFont loading cancelled.')
    return result
