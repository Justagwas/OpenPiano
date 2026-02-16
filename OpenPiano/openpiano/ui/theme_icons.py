from __future__ import annotations

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPen, QPixmap


def build_theme_icon(*, mode: str, size: int, color: str) -> QIcon:
    icon_size = max(14, int(size))
    screen = QGuiApplication.primaryScreen()
    dpr = float(screen.devicePixelRatio()) if screen is not None else 1.0
    px = int(round(icon_size * dpr))
    icon = QPixmap(px, px)
    icon.setDevicePixelRatio(dpr)
    icon.fill(Qt.transparent)

    icon_color = QColor(color)
    painter = QPainter(icon)
    painter.setRenderHint(QPainter.Antialiasing, True)
    painter.setPen(QPen(icon_color, max(1.1, icon_size * 0.10), Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
    painter.setBrush(Qt.NoBrush)
    center = QPointF(icon_size * 0.5, icon_size * 0.5)

    if mode == "sun":
        _draw_sun_icon(painter, center, icon_size)
    else:
        _draw_moon_icon(painter, center, icon_size, icon_color)

    painter.end()
    return QIcon(icon)


def _draw_sun_icon(painter: QPainter, center: QPointF, icon_size: int) -> None:
    orbit_radius = icon_size * 0.22
    inner_ray = icon_size * 0.34
    outer_ray = icon_size * 0.46
    painter.drawEllipse(
        QPointF(center.x(), center.y()),
        orbit_radius,
        orbit_radius,
    )
    for direction in (
        QPointF(1.0, 0.0),
        QPointF(-1.0, 0.0),
        QPointF(0.0, 1.0),
        QPointF(0.0, -1.0),
        QPointF(0.707, 0.707),
        QPointF(-0.707, -0.707),
        QPointF(0.707, -0.707),
        QPointF(-0.707, 0.707),
    ):
        start = QPointF(center.x() + (direction.x() * inner_ray), center.y() + (direction.y() * inner_ray))
        end = QPointF(center.x() + (direction.x() * outer_ray), center.y() + (direction.y() * outer_ray))
        painter.drawLine(start, end)


def _draw_moon_icon(painter: QPainter, center: QPointF, icon_size: int, icon_color: QColor) -> None:
    moon_radius = icon_size * 0.38
    painter.setBrush(icon_color)
    painter.drawEllipse(center, moon_radius, moon_radius)
    painter.setCompositionMode(QPainter.CompositionMode_Clear)
    painter.setPen(Qt.NoPen)
    painter.setBrush(Qt.transparent)
    painter.drawEllipse(
        QPointF(center.x() + (icon_size * 0.17), center.y() - (icon_size * 0.10)),
        icon_size * 0.34,
        icon_size * 0.34,
    )
    painter.setCompositionMode(QPainter.CompositionMode_SourceOver)
