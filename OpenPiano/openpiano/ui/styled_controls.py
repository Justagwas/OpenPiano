from __future__ import annotations

from PySide6.QtCore import QPointF, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPalette, QPen
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QListView,
    QProxyStyle,
    QStyle,
    QStyleOptionButton,
    QStyleOptionComboBox,
    QStyleOptionSlider,
    QStyleOptionViewItem,
    QStyledItemDelegate,
    QWidget,
)


class RoundHandleSliderStyle(QProxyStyle):
    def __init__(
        self,
        *,
        handle_color: str,
        border_color: str,
        groove_color: str,
        fill_color: str,
        handle_size: int = 18,
        groove_height: int = 6,
    ) -> None:
        super().__init__()
        self._handle_color = QColor(handle_color)
        self._border_color = QColor(border_color)
        self._groove_color = QColor(groove_color)
        self._fill_color = QColor(fill_color)
        self._handle_size = max(12, int(handle_size))
        self._groove_height = max(4, int(groove_height))

    def set_colors(self, *, handle_color: str, border_color: str, groove_color: str, fill_color: str) -> None:
        self._handle_color = QColor(handle_color)
        self._border_color = QColor(border_color)
        self._groove_color = QColor(groove_color)
        self._fill_color = QColor(fill_color)

    def set_metrics(self, *, handle_size: int, groove_height: int) -> None:
        self._handle_size = max(12, int(handle_size))
        self._groove_height = max(4, int(groove_height))

    def pixelMetric(self, metric, option=None, widget=None):
        if metric == QStyle.PixelMetric.PM_SliderLength:
            return self._handle_size
        if metric == QStyle.PixelMetric.PM_SliderThickness:
            return max(self._handle_size + 6, self._groove_height + 10)
        return super().pixelMetric(metric, option, widget)

    def _handle_diameter(self) -> int:
        return self._handle_size

    def _groove_rect(self, option: QStyleOptionSlider, widget: QWidget | None) -> QRect:
        _ = widget
        diameter = self._handle_diameter()
        groove_h = self._groove_height
        inset = max(1, diameter // 2)
        width = max(2, int(option.rect.width()) - (inset * 2))
        x = int(option.rect.left()) + inset
        y = int(option.rect.center().y() - (groove_h // 2))
        return QRect(x, y, width, groove_h)

    def _handle_rect(self, option: QStyleOptionSlider, widget: QWidget | None) -> QRect:
        groove = self._groove_rect(option, widget)
        diameter = self._handle_diameter()
        available = max(0, groove.width() - diameter)
        pos = QStyle.sliderPositionFromValue(
            int(option.minimum),
            int(option.maximum),
            int(option.sliderPosition),
            int(available),
            bool(option.upsideDown),
        )
        x = int(groove.left()) + int(pos)
        y = int(groove.center().y() - (diameter // 2))
        return QRect(x, y, diameter, diameter)

    def subControlRect(self, control, option, sub_control, widget=None):
        if control == QStyle.ComplexControl.CC_Slider and isinstance(option, QStyleOptionSlider):
            if option.orientation == Qt.Horizontal:
                if sub_control == QStyle.SubControl.SC_SliderGroove:
                    return self._groove_rect(option, widget)
                if sub_control == QStyle.SubControl.SC_SliderHandle:
                    return self._handle_rect(option, widget)
        return super().subControlRect(control, option, sub_control, widget)

    def drawComplexControl(self, control, option, painter, widget=None):
        if control != QStyle.ComplexControl.CC_Slider or not isinstance(option, QStyleOptionSlider):
            super().drawComplexControl(control, option, painter, widget)
            return
        if option.orientation != Qt.Horizontal:
            super().drawComplexControl(control, option, painter, widget)
            return

        groove = self._groove_rect(option, widget)
        handle = self._handle_rect(option, widget)
        radius = max(2.0, groove.height() / 2.0)

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)

        painter.setPen(Qt.NoPen)
        painter.setBrush(self._groove_color)
        painter.drawRoundedRect(QRectF(groove), radius, radius)

        if handle.isValid():
            if option.upsideDown:
                fill_left = float(handle.center().x())
                fill_width = float(groove.right() - handle.center().x())
            else:
                fill_left = float(groove.left())
                fill_width = float(handle.center().x() - groove.left())
            if fill_width > 0:
                fill_rect = QRectF(fill_left, float(groove.top()), fill_width, float(groove.height()))
                painter.setBrush(self._fill_color)
                painter.drawRoundedRect(fill_rect, radius, radius)

        if handle.isValid():
            circle_rect = QRectF(handle)
            painter.setBrush(self._handle_color)
            painter.setPen(QPen(self._border_color, max(1, int(round(self._handle_size / 16)))))
            painter.drawEllipse(circle_rect)

        painter.restore()


class SquareCheckBoxStyle(QProxyStyle):
    def __init__(
        self,
        *,
        border_color: str,
        fill_color: str,
        check_color: str,
        size: int = 16,
        radius: int = 4,
    ) -> None:
        super().__init__()
        self._border_color = QColor(border_color)
        self._fill_color = QColor(fill_color)
        self._check_color = QColor(check_color)
        self._size = max(12, int(size))
        self._radius = max(2, int(radius))

    def set_colors(self, *, border_color: str, fill_color: str, check_color: str) -> None:
        self._border_color = QColor(border_color)
        self._fill_color = QColor(fill_color)
        self._check_color = QColor(check_color)

    def set_metrics(self, *, size: int, radius: int) -> None:
        self._size = max(12, int(size))
        self._radius = max(2, int(radius))

    def pixelMetric(self, metric, option=None, widget=None):
        if metric in {QStyle.PixelMetric.PM_IndicatorWidth, QStyle.PixelMetric.PM_IndicatorHeight}:
            return self._size
        return super().pixelMetric(metric, option, widget)

    def _indicator_rect(self, option) -> QRect:
        left = int(option.rect.left()) + 2
        top = int(option.rect.center().y() - (self._size // 2))
        return QRect(left, top, self._size, self._size)

    def subElementRect(self, element, option, widget=None):
        if isinstance(option, QStyleOptionButton):
            if element == QStyle.SubElement.SE_CheckBoxIndicator:
                return self._indicator_rect(option)
            if element == QStyle.SubElement.SE_CheckBoxContents:
                indicator = self._indicator_rect(option)
                gap = 6
                left = int(indicator.right() + 1 + gap)
                width = max(0, int(option.rect.right()) - left + 1)
                return QRect(left, int(option.rect.top()), width, int(option.rect.height()))
        return super().subElementRect(element, option, widget)

    def drawPrimitive(self, element, option, painter, widget=None):
        if element != QStyle.PrimitiveElement.PE_IndicatorCheckBox:
            super().drawPrimitive(element, option, painter, widget)
            return

        rect = option.rect.adjusted(1, 1, -2, -2)
        checked = bool(option.state & QStyle.StateFlag.State_On)
        enabled = bool(option.state & QStyle.StateFlag.State_Enabled)
        border = QColor(self._border_color)
        fill = QColor(self._fill_color if checked else "transparent")
        check = QColor(self._check_color)

        if not enabled:
            border.setAlpha(130)
            fill.setAlpha(110 if checked else 0)
            check.setAlpha(170)

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(QPen(border, 1))
        painter.setBrush(fill)
        painter.drawRoundedRect(QRectF(rect), float(self._radius), float(self._radius))

        if checked:
            pen_w = max(2, int(round(self._size / 9)))
            pen = QPen(check, pen_w, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen)
            x = float(rect.x())
            y = float(rect.y())
            w = float(rect.width())
            h = float(rect.height())
            p1 = QPointF(x + w * 0.24, y + h * 0.56)
            p2 = QPointF(x + w * 0.44, y + h * 0.74)
            p3 = QPointF(x + w * 0.78, y + h * 0.34)
            painter.drawLine(p1, p2)
            painter.drawLine(p2, p3)
        painter.restore()


class ComboPopupDelegate(QStyledItemDelegate):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        palette = parent.palette() if isinstance(parent, QWidget) else QApplication.palette()
        self._accent = QColor("#D20F39")
        self._text_color = QColor(palette.color(QPalette.Text))
        self._panel_bg = QColor(palette.color(QPalette.Base))
        hover_candidate = QColor(palette.color(QPalette.AlternateBase))
        self._hover_bg = hover_candidate if hover_candidate.isValid() else QColor(self._panel_bg).darker(108)
        self._selected_bg = QColor(self._accent)
        self._selected_bg.setAlpha(42)

    def set_colors(self, *, accent: str, text: str, panel: str, hover: str) -> None:
        self._accent = QColor(accent)
        self._text_color = QColor(text)
        self._panel_bg = QColor(panel)
        self._hover_bg = QColor(hover)
        self._selected_bg = QColor(accent)
        self._selected_bg.setAlpha(42)

    def paint(self, painter, option, index) -> None:
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        rect = opt.rect
        if not rect.isValid():
            return

        state = opt.state
        is_selected = bool(state & QStyle.StateFlag.State_Selected)
        is_hovered = bool(state & QStyle.StateFlag.State_MouseOver)
        is_enabled = bool(state & QStyle.StateFlag.State_Enabled)

        painter.save()
        painter.setRenderHint(QPainter.Antialiasing, True)
        painter.setPen(Qt.NoPen)
        if is_selected:
            painter.setBrush(self._selected_bg)
        elif is_hovered:
            painter.setBrush(self._hover_bg)
        else:
            painter.setBrush(self._panel_bg)
        painter.drawRect(rect)

        left_pad = 8
        if is_selected:
            marker_width = max(3, int(round(rect.height() * 0.10)))
            marker_rect = QRect(
                int(rect.left() + 2),
                int(rect.top() + 4),
                marker_width,
                max(2, int(rect.height() - 8)),
            )
            painter.setBrush(self._accent)
            painter.drawRoundedRect(QRectF(marker_rect), marker_width / 2.0, marker_width / 2.0)
            left_pad += marker_width + 5

        text_rect = rect.adjusted(left_pad, 0, -6, 0)
        text_color = QColor(self._text_color)
        if not is_enabled:
            text_color.setAlpha(145)
        painter.setPen(text_color)
        font = opt.font
        font.setBold(True)
        painter.setFont(font)
        text = opt.fontMetrics.elidedText(str(opt.text or ""), Qt.TextElideMode.ElideRight, max(1, text_rect.width()))
        painter.drawText(text_rect, int(Qt.AlignVCenter | Qt.AlignLeft), text)
        painter.restore()

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        hint.setHeight(max(24, hint.height()))
        return hint


class ChevronComboBox(QComboBox):
    popupAboutToShow = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._arrow_idle = QColor("#B7B7BC")
        self._arrow_active = QColor("#F4F4F5")
        self._popup_delegate = ComboPopupDelegate(self)
        popup_view = QListView(self)
        popup_view.setUniformItemSizes(True)
        popup_view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        popup_view.setMouseTracking(True)
        if popup_view.viewport() is not None:
            popup_view.viewport().setAutoFillBackground(True)
            popup_view.viewport().setMouseTracking(True)
        popup_view.setItemDelegate(self._popup_delegate)
        self.setView(popup_view)

    def set_arrow_colors(self, idle: str, active: str) -> None:
        self._arrow_idle = QColor(idle)
        self._arrow_active = QColor(active)
        self.update()

    def set_popup_colors(self, *, accent: str, text: str, panel: str, hover: str) -> None:
        self._popup_delegate.set_colors(accent=accent, text=text, panel=panel, hover=hover)
        view = self.view()
        if view is None:
            return
        palette = view.palette()
        palette.setColor(QPalette.Base, QColor(panel))
        palette.setColor(QPalette.Text, QColor(text))
        palette.setColor(QPalette.Highlight, QColor(accent))
        palette.setColor(QPalette.HighlightedText, QColor(text))
        view.setPalette(palette)
        if view.viewport() is not None:
            view.viewport().setPalette(palette)
            view.viewport().update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, True)

        is_open = False
        try:
            view = self.view()
            is_open = bool(view.isVisible()) if view is not None else False
        except Exception:
            is_open = False

        color = self._arrow_active if (self.hasFocus() or is_open) else self._arrow_idle
        pen_width = max(1, int(round(self.height() / 12)))
        pen = QPen(color, pen_width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
        painter.setPen(pen)

        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        arrow_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox,
            option,
            QStyle.SubControl.SC_ComboBoxArrow,
            self,
        )
        if not arrow_rect.isValid():
            return

        cx = arrow_rect.center().x()
        cy = arrow_rect.center().y()
        span = max(3, int(round(min(arrow_rect.width(), arrow_rect.height()) * 0.22)))

        if is_open:
            painter.drawLine(cx - span, cy + (span // 2), cx, cy - (span // 2))
            painter.drawLine(cx, cy - (span // 2), cx + span, cy + (span // 2))
        else:
            painter.drawLine(cx - span, cy - (span // 2), cx, cy + (span // 2))
            painter.drawLine(cx, cy + (span // 2), cx + span, cy - (span // 2))

    def showPopup(self) -> None:
        self.popupAboutToShow.emit()
        super().showPopup()
