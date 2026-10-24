from __future__ import annotations

import ctypes
import re

from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtWidgets import QCheckBox, QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QScrollArea, QSizePolicy, QVBoxLayout, QWidget

from .modal_utils import RestoreCursorOnHide

from ..core.config import APP_VERSION
from ..update_handoff import PRODUCT, acknowledge_completion, pending_completion
from .styled_controls import SquareCheckBoxStyle

_DARK = dict(bg="#141416", track="#0A0A0B", border="#2A2A2D", text="#F4F4F5", muted="#B7B7BC", accent="#D20F39", success="#22C55E", disabled="#202024", disabled_text="#8C8C93")
_LIGHT = dict(bg="#FAFAFB", track="#ECEDEF", border="#D1D3D8", text="#1B1F2A", muted="#4B5161", accent="#C51E3A", success="#1E9A4B", disabled="#E6E8ED", disabled_text="#7A8090")


class UpdateDialog(RestoreCursorOnHide, QDialog):
    canceled = Signal()

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.state = "available"
        self.choice = ""
        self._cancel_enabled = True
        self._gate = None
        self._gate_timer = QTimer(self)
        self._gate_timer.setInterval(250)
        self._gate_timer.timeout.connect(self._refresh_gate)
        self.setWindowTitle("Updates")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        self.setWindowIcon(parent.windowIcon())
        self.layout_box = QVBoxLayout(self)
        self.header = QWidget(self)
        self.header_layout = QVBoxLayout(self.header)
        self.header_layout.setContentsMargins(0, 0, 0, 0)
        self.header_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.header.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.title = QLabel(self)
        self.title.setObjectName("title")
        self.title.setWordWrap(True)
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.detail = QLabel(self)
        self.detail.setWordWrap(True)
        self.detail.setTextFormat(Qt.TextFormat.PlainText)
        self.detail.setObjectName("detail")
        self.header_layout.addWidget(self.title)
        self.header_layout.addWidget(self.detail)
        self.layout_box.addWidget(self.header)
        self.body = QWidget(self)
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(0, 0, 0, 0)
        self.body_layout.setSpacing(0)
        self.layout_box.addWidget(self.body, 1)
        self.available_notes = QLabel(self)
        self.available_notes.setWordWrap(True)
        self.available_notes.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.available_notes.setTextFormat(Qt.TextFormat.PlainText)
        self.available_notes.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.body_layout.addWidget(self.available_notes)
        self.notes = QLabel(self)
        self.notes.setWordWrap(True)
        self.notes.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.notes.setTextFormat(Qt.TextFormat.PlainText)
        self.notes.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.notes_area = QScrollArea(self)
        self.notes_area.setWidgetResizable(True)
        self.notes_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.notes_area.setFrameShape(QScrollArea.Shape.NoFrame)
        self.notes_area.setWidget(self.notes)
        self.body_layout.addWidget(self.notes_area)
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 100)
        self.progress.setFormat("%p%")
        self.body_layout.addWidget(self.progress, 0, Qt.AlignmentFlag.AlignVCenter)
        self.restart_checkbox = QCheckBox(f"Reopen {PRODUCT} when finished", self)
        self.restart_checkbox.setChecked(True)
        self.body_layout.addWidget(self.restart_checkbox, 0, Qt.AlignmentFlag.AlignVCenter)
        self.buttons = QHBoxLayout()
        self.manual_button = QPushButton("Download installer manually", self)
        self.manual_button.setObjectName("manualDownloadLink")
        self.manual_button.setFlat(True)
        self.manual_button.setAutoDefault(False)
        self.cancel_button = QPushButton("Not now", self)
        self.cancel_button.setAutoDefault(False)
        self.primary_button = QPushButton("Update now", self)
        self.manual_button.clicked.connect(lambda: self._choose("manual"))
        self.cancel_button.clicked.connect(self.reject)
        self.primary_button.clicked.connect(self._primary)
        self.buttons.addWidget(self.cancel_button)
        self.buttons.addStretch(1)
        self.buttons.addWidget(self.manual_button)
        self.buttons.addWidget(self.primary_button)
        self.layout_box.addLayout(self.buttons)
        for label in (self.title, self.detail, self.notes):
            label.setTextFormat(Qt.TextFormat.PlainText)
        for button in (self.manual_button, self.cancel_button, self.primary_button):
            button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setTabOrder(self.cancel_button, self.manual_button)
        self.setTabOrder(self.manual_button, self.primary_button)
        self.apply_appearance()

    def apply_appearance(self):
        parent = self.parentWidget()
        mode = getattr(parent, "theme_mode", getattr(parent, "_theme_mode", "dark"))
        getter = getattr(parent, "current_theme_mode", None)
        if callable(getter):
            mode = getter()
        palette = _LIGHT if mode == "light" else _DARK
        percent = getattr(parent, "ui_scale_percent", getattr(parent, "_ui_scale_percent", 100))
        scale = max(.75, min(2., float(getattr(parent, "_ui_scale", float(percent) / 100))))
        self._scale = scale
        self.layout_box.setContentsMargins(round(14 * scale), round(12 * scale), round(14 * scale), round(12 * scale))
        self.layout_box.setSpacing(round(8 * scale))
        self.header_layout.setSpacing(round(4 * scale))
        self.header.setMinimumHeight(round(36 * scale))
        self.buttons.setSpacing(round(8 * scale))
        self.setMinimumWidth(round(420 * scale))
        self.available_notes.setMinimumHeight(round(80 * scale))
        self.notes_area.setMinimumHeight(round(32 * scale))
        self.notes_area.setMaximumHeight(round(64 * scale))
        self.setStyleSheet(f"""
QDialog, QScrollArea, QScrollArea QWidget {{ background: {palette['bg']}; color: {palette['text']}; }}
QLabel {{ background: transparent; color: {palette['text']}; font: 600 {8 * scale:.1f}pt 'Segoe UI'; }}
QLabel#title {{ font: 700 {9 * scale:.1f}pt 'Segoe UI'; }}
QLabel#detail {{ color: {palette['muted']}; }}
QCheckBox {{ background: transparent; color: {palette['text']}; font: 600 {9 * scale:.1f}pt 'Segoe UI'; }}
QPushButton {{ background: {palette['bg']}; color: {palette['text']}; border: 1px solid {palette['border']}; border-radius: {round(6 * scale)}px; padding: {round(5 * scale)}px {round(10 * scale)}px; font: 600 {9.5 * scale:.1f}pt 'Segoe UI'; min-height: {round(24 * scale)}px; }}
QPushButton:focus {{ border-color: {palette['accent']}; }}
QPushButton:hover {{ background: {palette['accent']}; color: {palette['text']}; }}
QPushButton:disabled {{ background: {palette['disabled']}; color: {palette['disabled_text']}; }}
QPushButton#manualDownloadLink {{ background: transparent; color: {palette['text']}; border: 1px solid transparent; border-radius: 0; padding: {round(2 * scale)}px; font: 600 {8 * scale:.1f}pt 'Segoe UI'; text-decoration: underline; }}
QPushButton#manualDownloadLink:hover, QPushButton#manualDownloadLink:focus {{ color: {palette['accent']}; border-color: {palette['accent']}; }}
QProgressBar {{ background: {palette['track']}; color: {palette['text']}; border: 1px solid {palette['border']}; border-radius: {round(6 * scale)}px; min-height: {round(18 * scale)}px; text-align: center; }}
QProgressBar::chunk {{ background: {palette['success']}; border-radius: {round(5 * scale)}px; }}
""")
        style = getattr(self, "_checkbox_style", None)
        if style is None:
            style = SquareCheckBoxStyle(border_color=palette['border'], fill_color=palette['accent'], check_color=palette['text'])
            style.setParent(self.restart_checkbox)
            self._checkbox_style = style
            self.restart_checkbox.setStyle(style)
        style.set_colors(border_color=palette['border'], fill_color=palette['accent'], check_color=palette['text'])
        style.set_metrics(size=max(14, round(20 * scale)), radius=max(2, round(4 * scale)))
        self.restart_checkbox.setCursor(Qt.CursorShape.PointingHandCursor)
        try:
            value = ctypes.c_int(mode != "light")
            setter = ctypes.windll.dwmapi.DwmSetWindowAttribute
            setter.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_void_p, ctypes.c_uint]
            setter(int(self.winId()), 20, ctypes.byref(value), ctypes.sizeof(value))
        except (AttributeError, OSError):
            pass

    def _fit_content(self):
        self.layout_box.activate()
        minimum = self.minimumSizeHint()
        width = max(self.minimumWidth(), minimum.width())
        height = max(round(160 * self._scale), minimum.height())
        if self.state == "available":
            height = max(height, self.layout_box.totalHeightForWidth(width))
        self.resize(width, height)

    def _choose(self, choice):
        self.choice = choice
        self._gate_timer.stop()
        self.accept()

    def _primary(self):
        if self.state == "ready" and not self._refresh_gate():
            return
        confirm = getattr(self.parentWidget(), "_update_install_confirm", None)
        if self.state == "ready" and callable(confirm) and not confirm():
            return
        self._choose("install" if self.state == "ready" else "retry" if self.state == "failed" else "download" if self.state == "available" else "continue")

    def reject(self):
        if not self._cancel_enabled:
            return
        self._gate_timer.stop()
        self.choice = "cancel"
        if self.state == "downloading":
            self.canceled.emit()
        super().reject()

    def _configure(self, state, title, detail):
        self._gate_timer.stop()
        self.state, self.choice = state, ""
        self._cancel_enabled = True
        self.title.setText(title)
        self.detail.setText(detail)
        self.detail.setVisible(bool(detail))
        self.available_notes.hide()
        self.notes_area.hide()
        self.progress.hide()
        self.restart_checkbox.hide()
        self.manual_button.hide()
        self.buttons.removeWidget(self.manual_button)
        self.layout_box.removeWidget(self.manual_button)
        if state == "available":
            self.layout_box.insertWidget(self.layout_box.count() - 1, self.manual_button,
                                         0, Qt.AlignmentFlag.AlignLeft)
            self.setTabOrder(self.manual_button, self.cancel_button)
            self.setTabOrder(self.cancel_button, self.primary_button)
        else:
            self.buttons.insertWidget(2, self.manual_button)
            self.setTabOrder(self.cancel_button, self.manual_button)
            self.setTabOrder(self.manual_button, self.primary_button)
        self.primary_button.show()
        self.primary_button.setEnabled(True)
        self.cancel_button.show()
        self.cancel_button.setEnabled(True)
        self.primary_button.setDefault(True)
        self.apply_appearance()

    def available(self, version, details, supported):
        self._configure("available", "Update available", f"Installed: v{APP_VERSION}   |   Available: v{version}")
        self.available_notes.setText(details.strip())
        self.available_notes.setVisible(bool(details.strip()))
        self.manual_button.show()
        self.primary_button.setText("Update now")
        self.cancel_button.setText("Not now")
        self._supported = supported
        self._fit_content()

    def set_progress(self, value, message):
        if self.choice == "cancel" or self.state == "closing" or (self.state == "failed" and not self.choice):
            return
        if self.state not in {"downloading", "closing"}:
            self._configure("downloading", "Downloading update...", "")
            self.primary_button.hide()
            self.cancel_button.setText("Cancel")
        lower = str(message).lower()
        if any(word in lower for word in ("handing off", "closing", "installer handoff")):
            self.closing()
            return
        checking = any(word in lower for word in ("verif", "checking the download", "ready", "download complete"))
        self.title.setText("Checking the download..." if checking else "Downloading update...")
        self.detail.setText("" if checking else re.sub(r"\s*\d+(?:\.\d+)?\s*%", "", str(message)).strip() if "retry" in lower else "")
        self.detail.setVisible(bool(self.detail.text()))
        self.progress.show()
        self.progress.setRange(0, 0 if checking or "preparing" in lower else 100)
        if not checking:
            self.progress.setValue(max(0, min(100, round(float(value)))))
        self._fit_content()

    def _refresh_gate(self):
        reason = str(self._gate() or "") if self._gate is not None else ""
        self.primary_button.setEnabled(not reason)
        detail = f"{PRODUCT} will close while the update is installed."
        if getattr(self, "_requires_elevation", False):
            detail += " Windows may ask for permission to install the update."
        self.detail.setText(reason or detail)
        return not reason

    def ready(self, version, restart=True, elevation=False):
        self._configure("ready", "Ready to install", f"{PRODUCT} v{version} has been downloaded and checked.")
        self.restart_checkbox.setChecked(restart)
        self.restart_checkbox.show()
        self.primary_button.setText("Install update")
        self.cancel_button.setText("Cancel")
        self._requires_elevation = elevation
        self._gate = getattr(self.parentWidget(), "_update_install_gate", None)
        self._refresh_gate()
        self._gate_timer.start()
        self._fit_content()

    def closing(self):
        self._configure("closing", f"{PRODUCT} is updating...", "The installer will show installation progress when the application has closed.")
        self._cancel_enabled = False
        self.cancel_button.hide()
        self.primary_button.hide()
        self._fit_content()
        self.show()

    def set_cancel_enabled(self, enabled):
        self._cancel_enabled = bool(enabled)
        self.cancel_button.setEnabled(bool(enabled))

    def failure(self, message, retry=False):
        self._configure("failed", "Update did not finish", str(message))
        self.primary_button.setVisible(retry)
        self.primary_button.setText("Retry")
        self.cancel_button.setText("Close")
        self.manual_button.show()
        self._fit_content()


def get_update_dialog(parent) -> UpdateDialog:
    dialog = getattr(parent, "_unified_update_dialog", None)
    if dialog is None:
        dialog = UpdateDialog(parent)
        parent._unified_update_dialog = dialog
    return dialog


def ask_update_install_preference(parent, *, latest_version, details_text="", install_supported=True):
    dialog = get_update_dialog(parent)
    if dialog.isVisible() and dialog.state == "complete":
        return False, False
    dialog.available(latest_version, details_text, install_supported)
    dialog.exec()
    return dialog.choice in {"download", "manual"}, dialog.choice == "download" and bool(install_supported)


def ask_update_handoff(parent, *, version, default_restart=True, requires_elevation=False):
    dialog = get_update_dialog(parent)
    dialog.ready(version, default_restart, requires_elevation)
    dialog.exec()
    accepted = dialog.choice == "install"
    if accepted:
        dialog.closing()
    return accepted, dialog.restart_checkbox.isChecked()


def show_update_failure(parent, message, *, retry=False):
    dialog = get_update_dialog(parent)
    dialog.failure(message, retry)
    dialog.exec()
    return dialog.choice


def show_update_completion(parent):
    pending = pending_completion(APP_VERSION)
    if pending is None:
        return
    path, data = pending
    dialog = get_update_dialog(parent)
    dialog._configure("complete", "Updated to v" + APP_VERSION, PRODUCT + " is up to date.")
    notes = [str(note).strip() for note in data.get("notes", []) if str(note).strip()]
    dialog.notes.setText("What's new\n" + "\n".join("- " + note for note in notes))
    dialog.notes_area.setVisible(bool(notes))
    dialog.primary_button.setText("Continue")
    dialog.cancel_button.hide()
    dialog._fit_content()
    dialog.exec()
    try:
        acknowledge_completion(path)
    except (OSError, RuntimeError, ValueError):
        pass


def show_update_notice(parent, title, detail):
    dialog = get_update_dialog(parent)
    dialog._configure("notice", title, detail)
    dialog.cancel_button.hide()
    dialog.primary_button.setText("Close")
    dialog._fit_content()
    dialog.exec()
