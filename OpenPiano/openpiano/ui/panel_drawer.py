from __future__ import annotations

from typing import Literal


ActivePanel = Literal["none", "settings", "controls", "both"]


class PanelDrawerState:
    def __init__(self, active: ActivePanel = "none") -> None:
        normalized = self._normalize(active)
        self._settings_visible = normalized in {"settings", "both"}
        self._controls_visible = normalized in {"controls", "both"}

    @staticmethod
    def _normalize(value: str) -> ActivePanel:
        if value == "settings":
            return "settings"
        if value == "controls":
            return "controls"
        if value == "both":
            return "both"
        return "none"

    @property
    def active(self) -> ActivePanel:
        if self._settings_visible and self._controls_visible:
            return "both"
        if self._settings_visible:
            return "settings"
        if self._controls_visible:
            return "controls"
        return "none"

    @property
    def settings_visible(self) -> bool:
        return self._settings_visible

    @property
    def controls_visible(self) -> bool:
        return self._controls_visible

    def set_active(self, active: ActivePanel) -> bool:
        target = self._normalize(active)
        previous = self.active
        self._settings_visible = target in {"settings", "both"}
        self._controls_visible = target in {"controls", "both"}
        if target == previous:
            return False
        return True

    def set_settings_visible(self, visible: bool) -> bool:
        target = bool(visible)
        if target == self._settings_visible:
            return False
        self._settings_visible = target
        return True

    def set_controls_visible(self, visible: bool) -> bool:
        target = bool(visible)
        if target == self._controls_visible:
            return False
        self._controls_visible = target
        return True
