from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QPushButton,
    QSlider,
    QWidget,
)

from openpiano.core.theme import ThemePalette


def message_box_stylesheet(theme: ThemePalette) -> str:
    return f"""
            QDialog, QMessageBox {{
                background: {theme.panel_bg};
                color: {theme.text_primary};
            }}
            QLabel {{
                color: {theme.text_primary};
                background: transparent;
            }}
            QPushButton {{
                background: {theme.panel_bg};
                color: {theme.text_primary};
                border: 1px solid {theme.border};
                border-radius: 6px;
                padding: 5px 10px;
                font: 600 9.5pt "Segoe UI";
                min-height: 24px;
            }}
            QPushButton:hover {{
                background: {theme.accent};
                color: {theme.text_primary};
            }}
            QPushButton:disabled {{
                background: {theme.panel_bg};
                color: {theme.text_secondary};
                border-color: {theme.border};
            }}
        """


def apply_dialog_button_cursors(dialog: QWidget) -> None:
    interactive_types = (QPushButton, QComboBox, QSlider, QCheckBox, QAbstractItemView)
    for widget in dialog.findChildren(QWidget):
        if isinstance(widget, interactive_types):
            if widget.isEnabled():
                widget.setCursor(Qt.PointingHandCursor)
            else:
                widget.unsetCursor()


def clear_override_cursors() -> None:
    while QApplication.overrideCursor() is not None:
        QApplication.restoreOverrideCursor()
