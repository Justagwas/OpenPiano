
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from openpiano.core.config import STAT_TITLES, STATS_ORDER
from openpiano.core.theme import ThemePalette


class StatsBar(QFrame):
    
    def __init__(self, theme: ThemePalette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._value_labels: dict[str, QLabel] = {}
        self._last_values: dict[str, str] = {}
        self._sustain_active = False
        self.setObjectName("statsBar")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        for key in STATS_ORDER:
            slot = QFrame(self)
            slot.setObjectName("statsSlot")
            slot_layout = QVBoxLayout(slot)
            slot_layout.setContentsMargins(8, 2, 8, 2)
            slot_layout.setSpacing(1)

            title = QLabel(STAT_TITLES[key], slot)
            title.setObjectName("statsTitle")
            title.setAlignment(Qt.AlignCenter)
            slot_layout.addWidget(title)

            value = QLabel("", slot)
            value.setObjectName("statsValue")
            value.setAlignment(Qt.AlignCenter)
            slot_layout.addWidget(value)
            self._value_labels[key] = value

            layout.addWidget(slot)

    def _apply_sustain_style(self) -> None:
        sustain_label = self._value_labels.get("sustain")
        if sustain_label is None:
            return
        if self._sustain_active:
            sustain_label.setStyleSheet(f"color: {self._theme.accent_hover};")
        else:
            sustain_label.setStyleSheet("")

    def set_theme(self, theme: ThemePalette) -> None:
        self._theme = theme
        self._apply_sustain_style()

    def set_values(self, values: dict[str, str], sustain_active: bool) -> None:
        for key in STATS_ORDER:
            label = self._value_labels.get(key)
            if label is None:
                continue
            value_text = str(values.get(key, ""))
            if self._last_values.get(key) != value_text:
                label.setText(value_text)
                self._last_values[key] = value_text
        sustain_state = bool(sustain_active)
        if sustain_state != self._sustain_active:
            self._sustain_active = sustain_state
            self._apply_sustain_style()
