from __future__ import annotations


def nearest_value(candidates: list[int], requested: int) -> int:
    if not candidates:
        return requested
    return min(candidates, key=lambda value: abs(value - requested))


def normalize_program_selection(
    programs: dict[int, list[int]],
    requested_bank: int,
    requested_preset: int,
) -> tuple[int, int]:
    if not programs:
        return max(0, int(requested_bank)), max(0, min(127, int(requested_preset)))
    banks = sorted(programs.keys())
    selected_bank = int(requested_bank) if int(requested_bank) in programs else nearest_value(banks, int(requested_bank))
    presets = sorted(set(programs.get(selected_bank, [])))
    if not presets:
        return selected_bank, max(0, min(127, int(requested_preset)))
    selected_preset = (
        int(requested_preset) if int(requested_preset) in presets else nearest_value(presets, int(requested_preset))
    )
    return selected_bank, selected_preset


def normalize_available_programs(programs: dict[int, list[int]] | None) -> dict[int, list[int]]:
    return {int(bank): sorted(set(int(preset) for preset in presets)) for bank, presets in (programs or {}).items()}
