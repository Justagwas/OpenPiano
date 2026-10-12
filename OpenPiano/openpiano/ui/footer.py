from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPainterPath, QPen, QPixmap


def build_footer_icon(name: str, color: str, size: int, *, checked_color: str | None = None) -> QIcon:
    screen = QGuiApplication.primaryScreen()
    dpr = float(screen.devicePixelRatio()) if screen is not None else 1.0
    icon = QIcon()
    for state, ink in ((QIcon.Off, color), (QIcon.On, checked_color or color)):
        pixmap = QPixmap(round(size * dpr), round(size * dpr))
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.transparent)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.scale(size / 24.0, size / 24.0)
        painter.setPen(QPen(QColor(ink), 2.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        painter.setBrush(Qt.NoBrush)
        path = QPainterPath()

        if name == "settings":
            points = []
            for i in range(64):
                angle = (i * math.tau / 64) - math.pi / 2
                radius = 10.0 if i % 8 in (1, 2, 3, 4) else 7.8
                points.append(QPointF(12 + radius * math.cos(angle), 12 + radius * math.sin(angle)))
            path.moveTo((points[-1] + points[0]) / 2)
            for i, point in enumerate(points):
                path.quadTo(point, (point + points[(i + 1) % len(points)]) / 2)
            path.closeSubpath()
            path.addEllipse(QPointF(12, 12), 3.5, 3.5)
            path.setFillRule(Qt.OddEvenFill)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(ink))
            painter.drawPath(path)
        elif name == "folder":
            path.moveTo(4, 11)
            path.lineTo(4, 6)
            path.quadTo(4, 5, 5, 5)
            path.lineTo(9, 5)
            path.lineTo(12, 8)
            path.lineTo(18, 8)
            path.quadTo(19, 8, 19, 9)
            path.lineTo(19, 11)
            painter.drawPath(path)
            path = QPainterPath()
            path.moveTo(3, 11)
            path.lineTo(21, 11)
            path.quadTo(22, 11, 21.6, 12)
            path.lineTo(19.4, 18.5)
            path.quadTo(19.1, 19.5, 18, 19.5)
            path.lineTo(3, 19.5)
            path.quadTo(2, 19.5, 2.1, 18.5)
            path.lineTo(2.4, 12)
            path.quadTo(2.4, 11, 3, 11)
            path.closeSubpath()
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(ink))
            painter.drawPath(path)
        elif name == "website":
            painter.drawEllipse(QRectF(3, 3, 18, 18))
            painter.drawEllipse(QRectF(8, 3, 8, 18))
            painter.drawLine(QPointF(3, 12), QPointF(21, 12))
        elif name == "controls":
            for y, knob_x in ((5, 8), (12, 16), (19, 10)):
                painter.drawLine(QPointF(3, y), QPointF(21, y))
                painter.setBrush(QColor(ink))
                painter.drawEllipse(QPointF(knob_x, y), 2.3, 2.3)
        elif name == "stats":
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(ink))
            for x, top in ((3, 13), (10, 8), (17, 3)):
                painter.drawRoundedRect(QRectF(x, top, 4, 21 - top), 1, 1)
        elif name == "heart":
            path.moveTo(12, 20.5)
            path.lineTo(5, 13.2)
            path.cubicTo(3.7, 11.9, 3, 10.3, 3, 8.5)
            path.cubicTo(3, 5.7, 5.2, 3.5, 8, 3.5)
            path.cubicTo(9.7, 3.5, 11.1, 4.3, 12, 5.8)
            path.cubicTo(12.9, 4.3, 14.3, 3.5, 16, 3.5)
            path.cubicTo(18.8, 3.5, 21, 5.7, 21, 8.5)
            path.cubicTo(21, 10.3, 20.3, 11.9, 19, 13.2)
            path.lineTo(12, 20.5)
            path.closeSubpath()
            painter.drawPath(path)
        else:
            painter.end()
            raise ValueError(f"Unknown footer icon: {name}")
        painter.end()
        for mode in (QIcon.Normal, QIcon.Active, QIcon.Selected):
            icon.addPixmap(pixmap, mode, state)
    return icon


from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QSizePolicy, QStyle, QStyleOptionButton, QStylePainter,
)


class FooterButton(QPushButton):

    def __init__(self, text, parent):
        super().__init__(text, parent)
        self.setFlat(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setProperty('keyboardFocus', False)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

    def _set_keyboard_focus(self, visible):
        if self.property('keyboardFocus') != visible:
            self.setProperty('keyboardFocus', visible)
            self.style().unpolish(self)
            self.style().polish(self)
            self.update()

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self._set_keyboard_focus(event.reason() in (
            Qt.TabFocusReason, Qt.BacktabFocusReason, Qt.ShortcutFocusReason,
        ))

    def focusOutEvent(self, event):
        self._set_keyboard_focus(False)
        super().focusOutEvent(event)

    def mousePressEvent(self, event):
        self._set_keyboard_focus(False)
        super().mousePressEvent(event)

    def paintEvent(self, event):
        option = QStyleOptionButton()
        self.initStyleOption(option)
        if not self.property('keyboardFocus'):
            option.state &= ~QStyle.State_HasFocus
        painter = QStylePainter(self)
        painter.drawControl(QStyle.CE_PushButton, option)


def describe_footer_button(button, name, description):
    button.setAccessibleName(name)
    button.setAccessibleDescription(description)
    button.setToolTip(description)
    button.setCursor(Qt.PointingHandCursor)


def add_version_to_header(card, layout, version):
    header = layout.itemAt(0).widget()
    layout.removeWidget(header)
    row = QHBoxLayout()
    row.addWidget(header)
    row.addStretch(1)
    label = QLabel(f'v{version}', card)
    label.setObjectName('settingsCardTitle')
    label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
    row.addWidget(label)
    layout.insertLayout(0, row)
    return label


def build_footer_stylesheet(theme, scale, mode, *, frame_name='appFooter'):
    px = lambda value: max(1, round(value * scale))
    box = max(22, px(30))
    font = max(7.4, round(9.4 * scale, 1))
    accent = theme.accent_hover if mode == 'dark' else theme.accent
    pressed = getattr(theme, 'disabled_bg', theme.panel_bg)
    disabled = getattr(theme, 'disabled_fg', theme.text_secondary)
    scope = f'QFrame#{frame_name} QPushButton'
    return f"""
QFrame#{frame_name} {{ background: {theme.app_bg}; border: none; }}
{scope}#footerIcon {{
    background: transparent; color: {theme.text_primary};
    border: 1px solid transparent; border-radius: {px(6)}px;
    min-width: {box}px; max-width: {box}px;
    min-height: {box}px; max-height: {box}px; padding: 0; margin: 0;
}}
{scope}#footerLink {{
    background: transparent; color: {theme.text_primary};
    border: 1px solid transparent; border-radius: {px(6)}px;
    min-height: {box}px; padding: 0 {max(6, px(8))}px;
    font: 600 {font:.1f}pt "Segoe UI";
}}
{scope}#footerDonate {{
    background: transparent; color: {accent};
    border: 1px solid transparent; border-radius: {px(6)}px;
    min-height: {box}px; padding: 0 {max(7, px(10))}px;
    font: 650 {font:.1f}pt "Segoe UI";
}}
{scope}#footerIcon:hover, {scope}#footerLink:hover, {scope}#footerDonate:hover {{
    background: {theme.panel_bg}; border-color: transparent;
}}
{scope}#footerIcon[keyboardFocus="true"]:focus,
{scope}#footerLink[keyboardFocus="true"]:focus,
{scope}#footerDonate[keyboardFocus="true"]:focus {{ border-color: {theme.text_secondary}; }}
{scope}#footerIcon:pressed, {scope}#footerLink:pressed, {scope}#footerDonate:pressed {{
    background: {pressed};
}}
{scope}#footerIcon:disabled, {scope}#footerLink:disabled, {scope}#footerDonate:disabled {{
    color: {disabled}; border-color: transparent; background: transparent;
}}
"""
