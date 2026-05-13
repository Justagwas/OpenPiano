from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from openpiano.core.instrument_registry import InstrumentInfo


def instrument_options(instruments: list[InstrumentInfo]) -> list[tuple[str, str]]:
    return [(f"{item.name} [{item.source}]", item.id) for item in instruments]


def bank_options(banks: list[int]) -> list[tuple[str, int]]:
    return [(str(int(bank)), int(bank)) for bank in banks]


def preset_options(presets: list[int], preset_names: dict[int, str] | None = None) -> list[tuple[str, int]]:
    labels = preset_names or {}
    options: list[tuple[str, int]] = []
    for preset in presets:
        preset_value = int(preset)
        preset_name = str(labels.get(preset_value, "")).strip()
        label = f"{preset_value} - {preset_name}" if preset_name else str(preset_value)
        options.append((label, preset_value))
    return options


def midi_input_options(items: list[str]) -> list[tuple[str, str]]:
    options: list[tuple[str, str]] = [("None", "")]
    for name in items:
        label = str(name).strip()
        if label:
            options.append((label, label))
    return options

