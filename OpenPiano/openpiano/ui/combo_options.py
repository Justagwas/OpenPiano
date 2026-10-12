from __future__ import annotations

from typing import TYPE_CHECKING
from collections import Counter

from openpiano.core.preset_families import DEFAULT_FAMILIES, FamilyPreset

if TYPE_CHECKING:
    from openpiano.core.instrument_registry import InstrumentInfo


def instrument_options(instruments: list[InstrumentInfo]) -> list[tuple[str, str]]:
    source_labels = {"builtin": "OpenPiano Built-in", "localappdata": "OpenPiano External"}
    return [(f"{item.name} [{source_labels[item.source]}]", item.id) for item in instruments]


def bank_options(banks: list[int], names: dict[int, str] | None = None) -> list[tuple[str, int]]:
    labels = names or {}
    return [(labels.get(int(bank), str(int(bank))), int(bank)) for bank in banks]


def named_piano_bank(instrument_id: str) -> str | None:
    stem = str(instrument_id).split(":", 1)[-1].rsplit(".", 1)[0]
    normalized = "".join(char for char in stem.lower() if char.isalnum())
    if normalized == "grandpiano":
        return "Pianos"
    if normalized in ("steinwayd274hifi", "steinwayd274releasepreview", "steinwayd274concert"):
        return "Steinway"
    return None


def preset_options(
    presets: list[int], preset_names: dict[int, str] | None = None, *, include_numbers: bool = True,
) -> list[tuple[str, int]]:
    labels = preset_names or {}
    options: list[tuple[str, int]] = []
    for preset in presets:
        preset_value = int(preset)
        preset_name = str(labels.get(preset_value, "")).strip()
        if preset_name:
            label = f"{preset_value} - {preset_name}" if include_numbers else preset_name
        else:
            label = str(preset_value)
        options.append((label, preset_value))
    return options


def family_options(entries: list[FamilyPreset]) -> list[tuple[str, int]]:
    counts = Counter(entry.family for entry in entries)
    return [(f"All sounds ({len(entries)})", -1)] + [
        (f"{name} ({counts[family]})", family)
        for family, name in enumerate(DEFAULT_FAMILIES) if counts[family]
    ]


def family_preset_options(entries: list[FamilyPreset], family: int) -> list[tuple[str, tuple[int, int]]]:
    selected = [entry for entry in entries if family == -1 or entry.family == family]
    duplicates = Counter(entry.name.casefold() for entry in selected)
    options = []
    for entry in selected:
        label = entry.name
        if duplicates[entry.name.casefold()] > 1:
            label += f" (Bank {entry.bank}, preset {entry.preset})"
        if family == -1:
            label = f"{DEFAULT_FAMILIES[entry.family]}: {label}"
        options.append((label, entry.address))
    return options


def midi_input_options(items: list[str]) -> list[tuple[str, str]]:
    options: list[tuple[str, str]] = [("None", "")]
    for name in items:
        label = str(name).strip()
        if label:
            options.append((label, label))
    return options

