
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from openpiano.core.config import (
    APP_NAME,
    INSTRUMENT_BANK_MAX,
    INSTRUMENT_BANK_MIN,
    INSTRUMENT_PRESET_MAX,
    INSTRUMENT_PRESET_MIN,
)
from openpiano.core.normalize import clamp_int
from openpiano.core.runtime_paths import app_local_data_dir, project_root, resource_root

InstrumentSource = Literal["builtin", "localappdata"]

SOUNDFONTS_DIR_NAME = "soundfonts"
SOUNDFONT_EXTENSIONS = (".sf2", ".sf3")
SOURCE_ORDER: dict[InstrumentSource, int] = {
    "builtin": 0,
    "localappdata": 1,
}


@dataclass(frozen=True, slots=True)
class InstrumentInfo:
    
    id: str
    name: str
    path: Path
    source: InstrumentSource
    default_bank: int = 0
    default_preset: int = 0


def builtin_fonts_dir() -> Path:
    return resource_root() / SOUNDFONTS_DIR_NAME


def localappdata_fonts_dir() -> Path:
    local_data_dir = app_local_data_dir(APP_NAME)
    if local_data_dir is not None:
        return local_data_dir / "soundfonts"
    return project_root() / "user_soundfonts"


def ensure_user_fonts_dir() -> Path:
    target = localappdata_fonts_dir()
    try:
        target.mkdir(parents=True, exist_ok=True)
    except Exception:
        return target
    return target


def _clamp_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    return clamp_int(value, minimum, maximum, default=default)


def _safe_label(text: str) -> str:
    if not text:
        return "Unnamed"
    return " ".join(text.split()).strip()


def _read_sidecar(soundfont_path: Path) -> tuple[str | None, int, int]:
    sidecar = soundfont_path.with_suffix(f"{soundfont_path.suffix}.json")
    if not sidecar.exists():
        return None, 0, 0

    try:
        raw = json.loads(sidecar.read_text(encoding="utf-8"))
    except Exception:
        return None, 0, 0
    if not isinstance(raw, dict):
        return None, 0, 0

    name = raw.get("name")
    display_name = _safe_label(str(name)) if isinstance(name, str) else None
    bank = _clamp_int(raw.get("bank"), INSTRUMENT_BANK_MIN, INSTRUMENT_BANK_MAX, 0)
    preset = _clamp_int(raw.get("preset"), INSTRUMENT_PRESET_MIN, INSTRUMENT_PRESET_MAX, 0)
    return display_name, bank, preset


def _iter_soundfonts(root: Path) -> list[Path]:
    if not root.exists() or not root.is_dir():
        return []
    files = [path for path in root.iterdir() if path.is_file() and path.suffix.lower() in SOUNDFONT_EXTENSIONS]
    files.sort(key=lambda path: path.name.lower())
    return files


def _build_id(source: InstrumentSource, root: Path, soundfont_path: Path) -> str:
    try:
        rel = soundfont_path.resolve().relative_to(root.resolve())
        rel_text = rel.as_posix().lower()
    except Exception:
        rel_text = soundfont_path.name.lower()
    return f"{source}:{rel_text}"


def _source_roots() -> list[tuple[InstrumentSource, Path]]:
    return [
        ("builtin", builtin_fonts_dir()),
        ("localappdata", localappdata_fonts_dir()),
    ]


def _is_default_builtin(item: InstrumentInfo) -> bool:
    if item.source != "builtin":
        return False
    stem = item.path.stem.lower()
    return stem == "default"


def _normalize_builtin_name(value: str) -> str:
    return "".join(ch for ch in value.lower() if ch.isalnum())


def _is_grand_piano(item: InstrumentInfo) -> bool:
    normalized = _normalize_builtin_name(item.path.stem)
    return normalized == "grandpiano"


def _is_grand_piano_builtin(item: InstrumentInfo) -> bool:
    if item.source != "builtin":
        return False
    return _is_grand_piano(item)


def _pinned_soundfont_priority(item: InstrumentInfo) -> int:
    suffix = item.path.suffix.lower()
    if _is_default_builtin(item):
        if suffix == ".sf3":
            return 0
        if suffix == ".sf2":
            return 2
        return 4
    if _is_grand_piano(item):
        if suffix == ".sf3":
            return 1
        if suffix == ".sf2":
            return 3
        return 5
    return 6


def discover_instruments() -> list[InstrumentInfo]:
    ensure_user_fonts_dir()
    seen_paths: set[str] = set()
    instruments: list[InstrumentInfo] = []

    for source, root in _source_roots():
        for soundfont_path in _iter_soundfonts(root):
            resolved_key = os.path.normcase(str(soundfont_path.resolve()))
            if resolved_key in seen_paths:
                continue
            seen_paths.add(resolved_key)

            sidecar_name, sidecar_bank, sidecar_preset = _read_sidecar(soundfont_path)
            name = sidecar_name or soundfont_path.stem
            instruments.append(
                InstrumentInfo(
                    id=_build_id(source, root, soundfont_path),
                    name=name,
                    path=soundfont_path.resolve(),
                    source=source,
                    default_bank=sidecar_bank,
                    default_preset=sidecar_preset,
                )
            )

    instruments.sort(
        key=lambda item: (
            _pinned_soundfont_priority(item),
            SOURCE_ORDER[item.source],
            item.name.lower(),
            item.path.name.lower(),
        )
    )
    return instruments


def select_fallback_instrument(instruments: list[InstrumentInfo]) -> InstrumentInfo | None:
    for instrument in instruments:
        if _is_default_builtin(instrument):
            return instrument
    for instrument in instruments:
        if _is_grand_piano_builtin(instrument):
            return instrument
    for instrument in instruments:
        if instrument.source == "builtin":
            return instrument
    return instruments[0] if instruments else None

