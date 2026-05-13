from __future__ import annotations

from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget


ScaleFunc = Callable[[int], int]


def configure_settings_row(row: QHBoxLayout, scale: ScaleFunc) -> None:
    row.setContentsMargins(6, scale(4), 6, scale(4))
    row.setSpacing(scale(8))


def configure_controls_row(row: QHBoxLayout, scale: ScaleFunc) -> None:
    row.setContentsMargins(4, scale(2), 4, scale(2))
    row.setSpacing(scale(6))


def create_section_card(title: str, parent: QWidget) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame(parent)
    card.setObjectName("settingsCard")
    card_layout = QVBoxLayout(card)
    card_layout.setContentsMargins(10, 9, 10, 9)
    card_layout.setSpacing(8)
    header = QLabel(title, card)
    header.setObjectName("settingsCardTitle")
    card_layout.addWidget(header)
    return card, card_layout


def add_labeled_slider_row(
    parent: QWidget,
    section_layout: QVBoxLayout,
    *,
    label_text: str,
    slider_object_name: str,
    slider_range: tuple[int, int],
    slider_value: int,
    value_text: str,
    on_value_changed: Callable[[int], None],
    scale: ScaleFunc,
) -> tuple[QSlider, QLabel]:
    row = QHBoxLayout()
    configure_settings_row(row, scale)
    label = QLabel(label_text, parent)
    label.setObjectName("settingLabel")
    slider = QSlider(Qt.Horizontal, parent)
    slider.setObjectName(slider_object_name)
    slider.setRange(int(slider_range[0]), int(slider_range[1]))
    slider.setValue(int(slider_value))
    slider.valueChanged.connect(on_value_changed)
    value_label = QLabel(value_text, parent)
    value_label.setObjectName("settingValue")
    row.addWidget(label)
    row.addWidget(slider, 1)
    row.addWidget(value_label)
    section_layout.addLayout(row)
    return slider, value_label

