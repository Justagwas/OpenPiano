from __future__ import annotations

from typing import Callable


class MidiRoutingService:
    def __init__(self, midi_manager) -> None:
        self._midi_manager = midi_manager
        self._backend_issue_shown = False

    def maybe_warn_backend_issue(self, show_warning: Callable[[str, str], None]) -> None:
        if self._backend_issue_shown:
            return
        getter = getattr(self._midi_manager, "backend_error", None)
        if not callable(getter):
            return
        detail = str(getter() or "").strip()
        if not detail:
            return
        self._backend_issue_shown = True
        show_warning(
            "MIDI Input",
            "MIDI input backend is unavailable.\n\n"
            f"{detail}\n\n"
            "Install MIDI dependencies and restart OpenPiano.",
        )

    def refresh_inputs(
        self,
        *,
        preferred_device: str,
        set_devices: Callable[[list[str], str], None],
        show_warning: Callable[[str, str], None],
    ) -> None:
        self.maybe_warn_backend_issue(show_warning)
        devices = self._midi_manager.list_input_devices()
        selected = preferred_device if preferred_device in devices else ""
        set_devices(devices, selected)

    def _current_device_if_available(self, devices: list[str]) -> str:
        current_getter = getattr(self._midi_manager, "current_device", None)
        current = str(current_getter() if callable(current_getter) else "").strip()
        return current if current in devices else ""

    def apply_device(
        self,
        *,
        device: str,
        set_devices: Callable[[list[str], str], None],
    ) -> str:
        chosen = str(device).strip()
        available = self._midi_manager.list_input_devices()
        if chosen and chosen not in available:
            raise RuntimeError(f"MIDI input device is not currently available: {chosen}")
        if chosen:
            self._midi_manager.open_device(chosen)
        else:
            self._midi_manager.close()
        set_devices(available, chosen)
        return chosen

    def restore_device(
        self,
        *,
        preferred_device: str,
        set_devices: Callable[[list[str], str], None],
        show_warning: Callable[[str, str], None],
        warning_enabled: bool,
    ) -> str:
        requested = str(preferred_device).strip()
        try:
            return self.apply_device(device=requested, set_devices=set_devices)
        except Exception as exc:
            devices = self._midi_manager.list_input_devices()
            selected = self._current_device_if_available(devices)
            set_devices(devices, selected)
            if warning_enabled:
                show_warning(
                    "MIDI Input",
                    f"Could not open MIDI input device:\n{exc}",
                )
            return selected
