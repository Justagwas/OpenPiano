from __future__ import annotations

from openpiano.core.keymap import (
    Binding,
    apply_custom_keybinds,
    get_mode_mapping,
    legacy_binding_to_physical,
    legacy_layout_scans,
)


def build_default_keybind_map_full() -> dict[int, Binding]:
    return get_mode_mapping("88")


def migrate_legacy_keybinds(
    overrides: dict[int, Binding | None], keyboard_input_mode: str,
) -> dict[int, Binding | None]:
    needs_layout_lookup = str(keyboard_input_mode).lower() == "layout" and any(
        binding is not None and binding[0] == "keyboard" and not binding[1].startswith("scan:")
        for binding in overrides.values()
    )
    layout_scans = legacy_layout_scans() if needs_layout_lookup else None
    return {
        note: legacy_binding_to_physical(binding, keyboard_input_mode, layout_scans=layout_scans)
        if binding is not None else None
        for note, binding in overrides.items()
    }


def apply_overrides(default_map: dict[int, Binding | None], overrides: dict[int, Binding | None]) -> dict[int, Binding | None]:
    return apply_custom_keybinds(default_map, overrides)

