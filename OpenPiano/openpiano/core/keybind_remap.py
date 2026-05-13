from __future__ import annotations

from openpiano.core.keymap import (
    Binding,
    apply_custom_keybinds,
    extract_custom_keybind_overrides,
    get_mode_mapping,
    remap_bindings_for_keyboard_mode,
)


def build_default_keybind_map_full(keyboard_input_mode: str) -> dict[int, Binding]:
    base = get_mode_mapping("88")
    if str(keyboard_input_mode or "").strip().lower() == "layout":
        return remap_bindings_for_keyboard_mode(base, "layout")
    return base


def build_keyboard_token_map(
    source_mapping: dict[int, Binding],
    target_mapping: dict[int, Binding],
) -> dict[str, str]:
    token_map: dict[str, str] = {}
    for note, source_binding in source_mapping.items():
        target_binding = target_mapping.get(note)
        if target_binding is None:
            continue
        source_kind, source_token, source_ctrl, source_shift, source_alt = source_binding
        target_kind, target_token, target_ctrl, target_shift, target_alt = target_binding
        if source_kind != "keyboard" or target_kind != "keyboard":
            continue
        if (source_ctrl, source_shift, source_alt) != (target_ctrl, target_shift, target_alt):
            continue
        token_map.setdefault(source_token, target_token)
    return token_map


def translate_keyboard_binding(
    binding: Binding,
    source_to_qwerty: dict[str, str],
    qwerty_to_target: dict[str, str],
) -> Binding:
    source_kind, token, ctrl, shift, alt = binding
    if source_kind != "keyboard":
        return binding
    qwerty_token = source_to_qwerty.get(token, token)
    target_token = qwerty_to_target.get(qwerty_token, qwerty_token)
    return ("keyboard", target_token, bool(ctrl), bool(shift), bool(alt))


def translate_keybind_map(
    *,
    previous_mode: str,
    target_mode: str,
    current_map: dict[int, Binding],
    previous_default_map: dict[int, Binding],
    target_default_map: dict[int, Binding],
) -> tuple[dict[int, Binding], dict[int, Binding]]:
    qwerty_defaults = get_mode_mapping("88")
    source_to_qwerty = (
        build_keyboard_token_map(previous_default_map, qwerty_defaults)
        if str(previous_mode or "").strip().lower() == "layout"
        else {}
    )
    qwerty_to_target = (
        build_keyboard_token_map(qwerty_defaults, target_default_map)
        if str(target_mode or "").strip().lower() == "layout"
        else {}
    )
    translated = {
        note: translate_keyboard_binding(binding, source_to_qwerty, qwerty_to_target)
        for note, binding in current_map.items()
    }
    overrides = extract_custom_keybind_overrides(target_default_map, translated)
    return translated, overrides


def apply_overrides(default_map: dict[int, Binding], overrides: dict[int, Binding]) -> dict[int, Binding]:
    return apply_custom_keybinds(default_map, overrides)

