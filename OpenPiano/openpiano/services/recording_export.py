from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openpiano.core.instrument_registry import InstrumentInfo


def destination_with_selected_suffix(path_text: str, selected_filter: str) -> Path:
    destination = Path(str(path_text or ""))
    if destination.suffix:
        return destination
    filter_text = str(selected_filter or "").lower()
    return destination.with_suffix(".wav" if "wav" in filter_text else ".mid")


def is_wav_destination(destination: Path) -> bool:
    return Path(destination).suffix.lower() == ".wav"


def wav_export_args(
    *,
    instrument: InstrumentInfo | None,
    bank: int,
    preset: int,
    master_volume: float,
) -> dict[str, object]:
    if instrument is None or not instrument.path.exists():
        raise RuntimeError("WAV export requires a valid loaded SoundFont.")
    return {
        "soundfont_path": Path(instrument.path),
        "bank": int(bank),
        "preset": int(preset),
        "master_volume": float(master_volume),
    }

