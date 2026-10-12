from __future__ import annotations

from dataclasses import dataclass


DEFAULT_FAMILIES = (
    "Pianos", "Mallets & Bells", "Organs", "Guitars", "Basses", "Strings",
    "Ensembles & Voices", "Brass", "Reeds", "Flutes & Pipes", "Synth Leads",
    "Synth Pads", "Synth Effects", "World Instruments", "Percussion",
    "Sound Effects", "Drum Kits",
)

REMOVED_DEFAULT_PRESETS = frozenset({
    (0, 124), (1, 124),
    (2, 124), (3, 124),
    (1, 125), (2, 125), (3, 125), (4, 125),
    (1, 126), (2, 126),
    (0, 127), (1, 127), (3, 127),
})
DEFAULT_DRUM_PROGRAMS = frozenset({0, 1, 2, 8, 16, 24, 25, 26, 32, 40, 48, 56, 127})


def default_program_selection(bank: int, preset: int) -> tuple[int, int]:
    if (bank, preset) in REMOVED_DEFAULT_PRESETS:
        return 0, 0
    if bank == 128 and preset in DEFAULT_DRUM_PROGRAMS:
        return 120, preset
    return bank, preset


def default_preset_family(bank: int, preset: int) -> int:
    if bank in (120, 128):
        return 16
    if preset == 47:
        return 14
    if preset in (112, 114):
        return 1
    if (bank, preset) == (11, 96):
        return 11
    return preset // 8


@dataclass(frozen=True, slots=True)
class FamilyPreset:
    bank: int
    preset: int
    name: str
    family: int

    @property
    def address(self) -> tuple[int, int]:
        return self.bank, self.preset


def default_family_catalog(
    programs: dict[int, list[int]], names: dict[int, dict[int, str]],
) -> list[FamilyPreset]:
    entries = [
        FamilyPreset(bank, preset, str(names.get(bank, {}).get(preset, "")).strip() or f"Preset {preset}",
                     default_preset_family(bank, preset))
        for bank, presets in programs.items()
        for preset in set(presets)
        if 0 <= preset <= 127
        if (bank, preset) not in REMOVED_DEFAULT_PRESETS
        if not (bank == 128 and preset in programs.get(120, []))
    ]
    return sorted(entries, key=lambda entry: (entry.family, entry.preset, entry.bank))
