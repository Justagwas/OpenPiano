
from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6.QtCore import QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QKeyEvent, QPaintEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

if TYPE_CHECKING:
    from openpiano.core.theme import ThemePalette


class TutorialOverlay(QWidget):
    
    nextRequested = Signal()
    backRequested = Signal()
    skipRequested = Signal()
    finishRequested = Signal()

    def __init__(self, theme: ThemePalette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._target_rect: QRect | None = None
        self._panel_margin = 16

        self.setObjectName("tutorialOverlay")
        self.setFocusPolicy(Qt.StrongFocus)
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAutoFillBackground(False)
        self.hide()

        self._panel = QFrame(self)
        self._panel.setObjectName("tutorialPanel")
        panel_layout = QVBoxLayout(self._panel)
        panel_layout.setContentsMargins(12, 10, 12, 10)
        panel_layout.setSpacing(8)

        self._title_label = QLabel("Tutorial", self._panel)
        self._title_label.setObjectName("tutorialTitle")
        panel_layout.addWidget(self._title_label)

        self._body_label = QLabel("", self._panel)
        self._body_label.setObjectName("tutorialBody")
        self._body_label.setWordWrap(True)
        panel_layout.addWidget(self._body_label)

        self._progress_label = QLabel("", self._panel)
        self._progress_label.setObjectName("tutorialProgress")
        panel_layout.addWidget(self._progress_label)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(6)

        self._back_button = QPushButton("Back", self._panel)
        self._back_button.setObjectName("tutorialButton")
        self._back_button.clicked.connect(self.backRequested.emit)
        actions.addWidget(self._back_button)

        self._next_button = QPushButton("Next", self._panel)
        self._next_button.setObjectName("tutorialButton")
        self._next_button.clicked.connect(self.nextRequested.emit)
        actions.addWidget(self._next_button)

        self._finish_button = QPushButton("Finish", self._panel)
        self._finish_button.setObjectName("tutorialButton")
        self._finish_button.clicked.connect(self.finishRequested.emit)
        actions.addWidget(self._finish_button)

        actions.addStretch(1)

        self._skip_button = QPushButton("Skip", self._panel)
        self._skip_button.setObjectName("tutorialButton")
        self._skip_button.clicked.connect(self.skipRequested.emit)
        actions.addWidget(self._skip_button)
        panel_layout.addLayout(actions)

        self.set_theme(theme)

    def set_theme(self, theme: ThemePalette) -> None:
        self._theme = theme
        self._panel.setStyleSheet(
            f"""
            QFrame#tutorialPanel {{
                background: {theme.panel_bg};
                border: 1px solid {theme.border};
                border-radius: 10px;
            }}
            QLabel#tutorialTitle {{
                color: {theme.text_primary};
                font: 700 11pt "Segoe UI";
            }}
            QLabel#tutorialBody {{
                color: {theme.text_secondary};
                font: 600 9pt "Segoe UI";
            }}
            QLabel#tutorialProgress {{
                color: {theme.text_secondary};
                font: 700 8pt "Consolas";
            }}
            QPushButton#tutorialButton {{
                background: {theme.app_bg};
                color: {theme.text_primary};
                border: 1px solid {theme.border};
                border-radius: 6px;
                padding: 5px 10px;
                font: 600 9pt "Segoe UI";
            }}
            QPushButton#tutorialButton:hover {{
                background: {theme.accent};
                color: {theme.text_primary};
            }}
            QPushButton#tutorialButton:disabled {{
                color: {theme.text_secondary};
                background: {theme.panel_bg};
            }}
            """
        )
        self.update()

    def set_step(
        self,
        *,
        title: str,
        body: str,
        index: int,
        total: int,
        is_first: bool,
        is_last: bool,
    ) -> None:
        self._title_label.setText(title)
        self._body_label.setText(body)
        self._progress_label.setText(f"Step {index + 1} of {total}")
        self._back_button.setEnabled(not is_first)
        self._next_button.setVisible(not is_last)
        self._finish_button.setVisible(is_last)
        self._position_panel()

    def set_target_rect(self, rect: QRect | None) -> None:
        self._target_rect = QRect(rect) if rect is not None else None
        self._position_panel()
        self.update()

    def sync_to_parent(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.setGeometry(parent.rect())
        self._position_panel()

    def resizeEvent(self, event) -> None:                          
        super().resizeEvent(event)
        self._position_panel()

    def keyPressEvent(self, event: QKeyEvent) -> None:                          
        if int(event.key()) == int(Qt.Key.Key_Escape):
            self.skipRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event) -> None:                          
        event.accept()

    def mouseMoveEvent(self, event) -> None:                          
        event.accept()

    def mouseReleaseEvent(self, event) -> None:                          
        event.accept()

    def paintEvent(self, event: QPaintEvent) -> None:                          
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        full = QRectF(self.rect())
        overlay_color = QColor(0, 0, 0, 178)
        target_rect = QRectF(self._target_rect) if self._target_rect is not None else None

        if target_rect is not None and target_rect.isValid():
            spotlight = target_rect.adjusted(-6.0, -6.0, 6.0, 6.0)
            path = QPainterPath()
            path.addRect(full)
            path.addRoundedRect(spotlight, 8.0, 8.0)
            path.setFillRule(Qt.OddEvenFill)
            painter.fillPath(path, overlay_color)

            pen = QPen(QColor(self._theme.accent_hover), 2)
            painter.setPen(pen)
            painter.drawRoundedRect(spotlight, 8.0, 8.0)
        else:
            painter.fillRect(self.rect(), overlay_color)

        painter.end()

    def _position_panel(self) -> None:
        bounds = self.rect().adjusted(
            self._panel_margin,
            self._panel_margin,
            -self._panel_margin,
            -self._panel_margin,
        )
        if not bounds.isValid():
            return

        desired_w = min(420, max(300, self.width() - (self._panel_margin * 2)))
        panel_w = max(220, min(desired_w, bounds.width()))
        self._panel.setFixedWidth(panel_w)

        panel_h = self._panel.sizeHint().height()
        panel_h = max(120, min(panel_h, bounds.height()))

        max_x = bounds.left() + max(0, bounds.width() - panel_w)
        max_y = bounds.top() + max(0, bounds.height() - panel_h)
        x = bounds.left() + max(0, (bounds.width() - panel_w) // 2)
        y = bounds.top() + max(0, (bounds.height() - panel_h) // 2)

        target = self._target_rect
        if target is not None and target.isValid():
            target_center_x = target.left() + (target.width() // 2)
            x = max(bounds.left(), min(target_center_x - (panel_w // 2), max_x))

            below_y = target.bottom() + 14
            above_y = target.top() - panel_h - 14
            if below_y <= max_y:
                y = below_y
            elif above_y >= bounds.top():
                y = above_y
            else:
                y = max(bounds.top(), min(target.bottom() - (panel_h // 2), max_y))

        x = max(bounds.left(), min(x, max_x))
        y = max(bounds.top(), min(y, max_y))
        self._panel.setGeometry(x, y, panel_w, panel_h)
        self._panel.raise_()
