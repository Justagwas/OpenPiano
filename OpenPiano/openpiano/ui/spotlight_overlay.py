from __future__ import annotations

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QPaintEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget


class SpotlightOverlay(QWidget):
    def __init__(self, theme, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._theme = theme
        self._target_rects: list[QRect] = []
        self.setObjectName("spotlightOverlay")
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.setAutoFillBackground(False)
        self.hide()

    def set_theme(self, theme) -> None:
        self._theme = theme
        self.update()

    def set_target_rects(self, rects: list[QRect] | None) -> None:
        self._target_rects = [QRect(rect) for rect in (rects or []) if isinstance(rect, QRect) and rect.isValid()]
        self.update()

    def sync_to_parent(self) -> None:
        parent = self.parentWidget()
        if parent is None:
            return
        self.setGeometry(parent.rect())
        self.update()

    def paintEvent(self, event: QPaintEvent) -> None:
        del event
        if not self._target_rects:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        full = QRectF(self.rect())
        overlay_color = QColor(0, 0, 0, 178)
        path = QPainterPath()
        path.addRect(full)
        spotlights: list[QRectF] = []
        for target in self._target_rects:
            spotlight = QRectF(target).adjusted(-6.0, -6.0, 6.0, 6.0)
            if not spotlight.isValid():
                continue
            spotlights.append(spotlight)
            path.addRoundedRect(spotlight, 8.0, 8.0)
        path.setFillRule(Qt.OddEvenFill)
        painter.fillPath(path, overlay_color)

        pen = QPen(QColor(self._theme.accent_hover), 2)
        painter.setPen(pen)
        for spotlight in spotlights:
            painter.drawRoundedRect(spotlight, 8.0, 8.0)
        painter.end()
