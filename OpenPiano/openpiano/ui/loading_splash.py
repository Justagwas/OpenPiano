from __future__ import annotations


def create_loading_splash(app_name: str):
    from PySide6.QtCore import QRect, Qt
    from PySide6.QtGui import QColor, QFont, QGuiApplication, QPainter, QPixmap
    from PySide6.QtWidgets import QSplashScreen, QWidget

    class LoadingSplash(QSplashScreen):
        def set_status(self, message: str) -> None:
            self._status_message = str(message)
            QWidget.repaint(self)

        def mousePressEvent(self, event) -> None:
            event.ignore()

        def drawContents(self, painter) -> None:
            painter.setPen(QColor('#B7B7BC'))
            painter.setFont(self.font())
            margin = max(14, round(24 * dpi_scale))
            status_top = round(103 * dpi_scale)
            painter.drawText(
                QRect(margin, status_top, self.width() - 2 * margin,
                      self.height() - status_top - round(16 * dpi_scale)),
                Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
                self._status_message,
            )

    screen = QGuiApplication.primaryScreen()
    dpi_scale = 1.0
    dpr = 1.0
    if screen is not None:
        try:
            logical_dpi = float(screen.logicalDotsPerInch())
            if logical_dpi > 0:
                dpi_scale = max(1.0, min(3.0, logical_dpi / 96.0))
        except Exception:
            dpi_scale = 1.0
        try:
            dpr = max(1.0, float(screen.devicePixelRatio()))
        except Exception:
            dpr = 1.0

    width = int(round(460 * dpi_scale))
    height = int(round(180 * dpi_scale))
    px_width = max(1, int(round(width * dpr)))
    px_height = max(1, int(round(height * dpr)))

    pixmap = QPixmap(px_width, px_height)
    pixmap.setDevicePixelRatio(dpr)
    pixmap.fill(QColor('#0A0A0B'))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing, False)
    painter.setPen(Qt.NoPen)
    painter.setBrush(QColor('#141416'))
    border_px = max(1, int(round(1 * dpi_scale)))
    painter.drawRect(0, 0, width, height)
    painter.setPen(QColor('#D20F39'))
    painter.setBrush(Qt.NoBrush)
    painter.drawRect(border_px, border_px, width - (2 * border_px), height - (2 * border_px))
    title_font = QFont('Segoe UI')
    title_font.setBold(True)
    title_font.setPointSizeF(max(11.0, 16.0 * dpi_scale))
    painter.setFont(title_font)
    painter.setPen(QColor('#F4F4F5'))
    x_margin = max(14, int(round(24 * dpi_scale)))
    title_y = max(40, int(round(78 * dpi_scale)))
    painter.drawText(x_margin, title_y, f'{app_name} is loading')
    painter.end()
    splash = LoadingSplash(pixmap, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint)
    message_font = QFont('Segoe UI')
    message_font.setWeight(QFont.DemiBold)
    message_font.setPointSizeF(max(7.0, 9.0 * dpi_scale))
    splash.setFont(message_font)
    splash._status_message = 'Loading application components...'
    splash.setAccessibleName(f'{app_name} startup')
    return splash

