
from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal, QTimer
from PySide6.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPalette, QPen, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFrame,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListView,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSlider,
    QSizePolicy,
    QScrollBar,
    QStyle,
    QStyleOptionButton,
    QStyleOptionComboBox,
    QStyleOptionViewItem,
    QStyleOptionSlider,
    QStyledItemDelegate,
    QProxyStyle,
    QVBoxLayout,
    QWidget,
)

from openpiano.core.config import (
    APP_NAME,
    APP_VERSION,
    UI_SCALE_MAX,
    UI_SCALE_MIN,
    UI_SCALE_STEP,
)
from openpiano.core.theme import ThemePalette
from openpiano.ui.piano_widget import PianoWidget
from openpiano.ui.stats_bar import StatsBar
from openpiano.ui.tutorial_overlay import TutorialOverlay

if TYPE_CHECKING:

    from openpiano.core.instrument_registry import InstrumentInfo
    from openpiano.core.keymap import PianoMode


ANIMATION_SPEED_LABELS = {
    "instant": "Instant",
    "fast": "Fast",
    "normal": "Normal",
    "slow": "Slow",
    "very_slow": "Very Slow",
}


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
        parent: QWidget | None = None,
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
        parent: QWidget | None = None,
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

class MainWindow(QMainWindow):
    
    modeChanged = Signal(str)
    instrumentChanged = Signal(str)
    bankChanged = Signal(int)
    presetChanged = Signal(int)
    volumeChanged = Signal(float)
    velocityChanged = Signal(int)
    transposeChanged = Signal(int)
    sustainPercentChanged = Signal(int)
    holdSpaceSustainChanged = Signal(bool)
    showKeyLabelsChanged = Signal(bool)
    showNoteLabelsChanged = Signal(bool)
    themeModeChanged = Signal(str)
    uiScaleChanged = Signal(float)
    animationSpeedChanged = Signal(str)
    keyColorChanged = Signal(str, str)
    autoCheckUpdatesChanged = Signal(bool)
    checkUpdatesNowRequested = Signal()
    settingsToggled = Signal(bool)
    controlsToggled = Signal(bool)
    statsToggled = Signal(bool)
    midiInputDeviceChanged = Signal(str)
    midiInputDropdownOpened = Signal()
    recordingToggled = Signal(bool)
    saveRecordingRequested = Signal()
    allNotesOffRequested = Signal()
    tutorialRequested = Signal()
    tutorialNextRequested = Signal()
    tutorialBackRequested = Signal()
    tutorialSkipRequested = Signal()
    tutorialFinishRequested = Signal()
    websiteRequested = Signal()
    resetDefaultsRequested = Signal()

    def __init__(self, theme: ThemePalette, icon_path: Path | None = None) -> None:
        super().__init__()
        self.theme = theme
        self._ui_scale = 1.0
        self._applied_ui_scale = 1.0
        self._settings_visible = False
        self._controls_visible = False
        self._stats_visible = True
        self._theme_mode = "dark"
        self._tutorial_mode = False
        self._recording_active = False
        self._ui_scale_steps = int(round((UI_SCALE_MAX - UI_SCALE_MIN) / UI_SCALE_STEP))
        self._ui_scale_commit_timer = QTimer(self)
        self._ui_scale_commit_timer.setSingleShot(True)
        self._ui_scale_commit_timer.setInterval(120)
        self._ui_scale_commit_timer.timeout.connect(self._commit_ui_scale_if_changed)
        self._slider_styles: list[RoundHandleSliderStyle] = []
        self._checkbox_styles: list[SquareCheckBoxStyle] = []
        self._key_color_values: dict[str, str] = {
            "white_key": "",
            "white_key_pressed": "",
            "black_key": "",
            "black_key_pressed": "",
        }
        self.setWindowTitle(APP_NAME)
        self.setWindowFlag(Qt.WindowMaximizeButtonHint, False)
        self._icon_path = icon_path
        if hasattr(Qt, "MSWindowsFixedSizeDialogHint"):
            self.setWindowFlag(Qt.MSWindowsFixedSizeDialogHint, True)
        if icon_path is not None and icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))

        self._build_ui()
        self._set_interaction_cursors()
        self._install_wheel_guards()
        self._apply_style()
        self.refresh_fixed_size()

    def _sp(self, value: int) -> int:
        return max(1, int(round(value * self._ui_scale)))

    def _build_ui(self) -> None:
        root = QWidget(self)
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(14, 14, 14, 10)
        outer.setSpacing(10)

        self.piano_widget = PianoWidget(self.theme, root)
        outer.addWidget(self.piano_widget, 0, Qt.AlignHCenter)

        self.stats_bar = StatsBar(self.theme, root)
        outer.addWidget(self.stats_bar)

        self.controls_scroll = QScrollArea(root)
        self.controls_scroll.setObjectName("controlsScroll")
        self.controls_scroll.setWidgetResizable(True)
        self.controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.controls_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.controls_scroll.setFrameShape(QFrame.NoFrame)
        self.controls_scroll.setVisible(False)
        self.controls_scroll.setFixedHeight(90)
        outer.addWidget(self.controls_scroll)

        self._build_controls_panel()

        self.panel_divider = QFrame(root)
        self.panel_divider.setObjectName("panelDivider")
        self.panel_divider.setFixedHeight(1)
        self.panel_divider.setVisible(False)
        outer.addWidget(self.panel_divider)

        self.settings_scroll = QScrollArea(root)
        self.settings_scroll.setObjectName("settingsScroll")
        self.settings_scroll.setWidgetResizable(True)
        self.settings_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.settings_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.settings_scroll.setFrameShape(QFrame.NoFrame)
        self.settings_scroll.setVisible(False)
        self.settings_scroll.setFixedHeight(236)
        outer.addWidget(self.settings_scroll)

        self._build_settings_panel()
        self._build_footer(outer)
        self._build_tutorial_overlay(root)

        self.recording_indicator = QFrame(root)
        self.recording_indicator.setObjectName("recordingIndicator")
        self.recording_indicator.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self.recording_indicator.hide()
        self._recording_indicator_effect = QGraphicsDropShadowEffect(self.recording_indicator)
        self._recording_indicator_effect.setOffset(0, 0)
        self.recording_indicator.setGraphicsEffect(self._recording_indicator_effect)
        self._position_recording_indicator()

    def _build_settings_panel(self) -> None:
        self.settings_body = QWidget(self.settings_scroll)
        self.settings_body.setObjectName("settingsBody")
        self.settings_scroll.setWidget(self.settings_body)

        layout = QVBoxLayout(self.settings_body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        self.sound_card, sound_layout = self._create_section_card("Sound", self.settings_body)
        layout.addWidget(self.sound_card)

        sound_volume_row = QHBoxLayout()
        self._configure_settings_row(sound_volume_row)
        sound_volume_label = QLabel("Volume", self.sound_card)
        sound_volume_label.setObjectName("settingLabel")
        self.volume_slider = QSlider(Qt.Horizontal, self.sound_card)
        self.volume_slider.setObjectName("volumeSlider")
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(60)
        self.volume_slider.valueChanged.connect(self._on_volume_value_changed)
        self.volume_value = QLabel("60%", self.sound_card)
        self.volume_value.setObjectName("settingValue")
        sound_volume_row.addWidget(sound_volume_label)
        sound_volume_row.addWidget(self.volume_slider, 1)
        sound_volume_row.addWidget(self.volume_value)
        sound_layout.addLayout(sound_volume_row)

        velocity_row = QHBoxLayout()
        self._configure_settings_row(velocity_row)
        velocity_label = QLabel("Velocity", self.sound_card)
        velocity_label.setObjectName("settingLabel")
        self.velocity_slider = QSlider(Qt.Horizontal, self.sound_card)
        self.velocity_slider.setObjectName("velocitySlider")
        self.velocity_slider.setRange(1, 127)
        self.velocity_slider.setValue(100)
        self.velocity_slider.valueChanged.connect(self._on_velocity_value_changed)
        self.velocity_value = QLabel("100", self.sound_card)
        self.velocity_value.setObjectName("settingValue")
        velocity_row.addWidget(velocity_label)
        velocity_row.addWidget(self.velocity_slider, 1)
        velocity_row.addWidget(self.velocity_value)
        sound_layout.addLayout(velocity_row)

        transpose_row = QHBoxLayout()
        self._configure_settings_row(transpose_row)
        transpose_label = QLabel("Transpose", self.sound_card)
        transpose_label.setObjectName("settingLabel")
        self.transpose_slider = QSlider(Qt.Horizontal, self.sound_card)
        self.transpose_slider.setObjectName("transposeSlider")
        self.transpose_slider.setRange(-21, 21)
        self.transpose_slider.setValue(0)
        self.transpose_slider.valueChanged.connect(self._on_transpose_value_changed)
        self.transpose_value = QLabel("+0", self.sound_card)
        self.transpose_value.setObjectName("settingValue")
        transpose_row.addWidget(transpose_label)
        transpose_row.addWidget(self.transpose_slider, 1)
        transpose_row.addWidget(self.transpose_value)
        sound_layout.addLayout(transpose_row)

        sustain_row = QHBoxLayout()
        self._configure_settings_row(sustain_row)
        sustain_label = QLabel("Sustain %", self.sound_card)
        sustain_label.setObjectName("settingLabel")
        self.sustain_slider = QSlider(Qt.Horizontal, self.sound_card)
        self.sustain_slider.setObjectName("sustainSlider")
        self.sustain_slider.setRange(0, 100)
        self.sustain_slider.setValue(100)
        self.sustain_slider.valueChanged.connect(self._on_sustain_percent_changed)
        self.sustain_value = QLabel("100%", self.sound_card)
        self.sustain_value.setObjectName("settingValue")
        sustain_row.addWidget(sustain_label)
        sustain_row.addWidget(self.sustain_slider, 1)
        sustain_row.addWidget(self.sustain_value)
        sound_layout.addLayout(sustain_row)

        self.keyboard_card, keyboard_layout = self._create_section_card("Keyboard", self.settings_body)
        layout.addWidget(self.keyboard_card)

        mode_row = QHBoxLayout()
        self._configure_settings_row(mode_row)
        mode_label = QLabel("Mode", self.keyboard_card)
        mode_label.setObjectName("settingLabel")
        mode_holder = QFrame(self.keyboard_card)
        mode_holder.setObjectName("modeHolder")
        mode_holder_layout = QHBoxLayout(mode_holder)
        mode_holder_layout.setContentsMargins(2, 2, 2, 2)
        mode_holder_layout.setSpacing(2)
        self.mode_group = QButtonGroup(self.keyboard_card)
        self.mode_group.setExclusive(True)
        self.mode_61_btn = QPushButton("61 Keys", mode_holder)
        self.mode_88_btn = QPushButton("88 Keys", mode_holder)
        for button, mode in ((self.mode_61_btn, "61"), (self.mode_88_btn, "88")):
            button.setObjectName("modeButton")
            button.setCheckable(True)
            mode_holder_layout.addWidget(button)
            self.mode_group.addButton(button)
            button.clicked.connect(lambda checked, m=mode: self._on_mode_clicked(checked, m))
        mode_row.addWidget(mode_label)
        mode_row.addWidget(mode_holder, 1)
        keyboard_layout.addLayout(mode_row)
        keyboard_layout.addSpacing(self._sp(2))

        sustain_mode_row = QHBoxLayout()
        self._configure_settings_row(sustain_mode_row)
        sustain_mode_row.setContentsMargins(6, self._sp(1), 6, self._sp(1))
        self.hold_space_sustain_checkbox = QCheckBox("Hold Space for sustain", self.keyboard_card)
        self.hold_space_sustain_checkbox.setObjectName("settingCheckbox")
        self.hold_space_sustain_checkbox.setChecked(False)
        self.hold_space_sustain_checkbox.toggled.connect(self.holdSpaceSustainChanged.emit)
        sustain_mode_row.addWidget(self.hold_space_sustain_checkbox)
        sustain_mode_row.addStretch(1)
        keyboard_layout.addLayout(sustain_mode_row)

        key_label_row = QHBoxLayout()
        self._configure_settings_row(key_label_row)
        key_label_row.setContentsMargins(6, self._sp(1), 6, self._sp(1))
        self.show_key_labels_checkbox = QCheckBox("Keyboard key labels", self.keyboard_card)
        self.show_key_labels_checkbox.setObjectName("settingCheckbox")
        self.show_key_labels_checkbox.setChecked(True)
        self.show_key_labels_checkbox.toggled.connect(self.showKeyLabelsChanged.emit)
        key_label_row.addWidget(self.show_key_labels_checkbox)
        key_label_row.addStretch(1)
        keyboard_layout.addLayout(key_label_row)

        note_label_row = QHBoxLayout()
        self._configure_settings_row(note_label_row)
        note_label_row.setContentsMargins(6, self._sp(1), 6, self._sp(1))
        self.show_note_labels_checkbox = QCheckBox("Note labels", self.keyboard_card)
        self.show_note_labels_checkbox.setObjectName("settingCheckbox")
        self.show_note_labels_checkbox.setChecked(False)
        self.show_note_labels_checkbox.toggled.connect(self.showNoteLabelsChanged.emit)
        note_label_row.addWidget(self.show_note_labels_checkbox)
        note_label_row.addStretch(1)
        keyboard_layout.addLayout(note_label_row)

        self.interface_card, interface_layout = self._create_section_card("Interface", self.settings_body)
        layout.addWidget(self.interface_card)

        ui_size_row = QHBoxLayout()
        self._configure_settings_row(ui_size_row)
        ui_size_label = QLabel("UI Size", self.interface_card)
        ui_size_label.setObjectName("settingLabel")
        self.ui_scale_slider = QSlider(Qt.Horizontal, self.interface_card)
        self.ui_scale_slider.setObjectName("uiScaleSlider")
        self.ui_scale_slider.setRange(0, self._ui_scale_steps)
        self.ui_scale_slider.setSingleStep(1)
        self.ui_scale_slider.setPageStep(1)
        self.ui_scale_slider.setTracking(True)
        self.ui_scale_slider.setValue(int(round((1.0 - UI_SCALE_MIN) / UI_SCALE_STEP)))
        self.ui_scale_slider.valueChanged.connect(self._on_ui_scale_value_changed)
        self.ui_scale_slider.sliderPressed.connect(self._on_ui_scale_slider_pressed)
        self.ui_scale_slider.sliderReleased.connect(self._on_ui_scale_slider_released)
        self.ui_scale_value = QLabel("100%", self.interface_card)
        self.ui_scale_value.setObjectName("settingValue")
        ui_size_row.addWidget(ui_size_label)
        ui_size_row.addWidget(self.ui_scale_slider, 1)
        ui_size_row.addWidget(self.ui_scale_value)
        interface_layout.addLayout(ui_size_row)

        anim_row = QHBoxLayout()
        self._configure_settings_row(anim_row)
        anim_label = QLabel("Anim Speed", self.interface_card)
        anim_label.setObjectName("settingLabel")
        self.anim_speed_combo = ChevronComboBox(self.interface_card)
        self.anim_speed_combo.setObjectName("animCombo")
        for speed, label in ANIMATION_SPEED_LABELS.items():
            self.anim_speed_combo.addItem(label, userData=speed)
        self.anim_speed_combo.currentIndexChanged.connect(self._on_anim_index_changed)
        anim_row.addWidget(anim_label)
        anim_row.addWidget(self.anim_speed_combo, 1)
        interface_layout.addLayout(anim_row)

        colors_row = QHBoxLayout()
        self._configure_settings_row(colors_row)
        colors_label = QLabel("Key Colors", self.interface_card)
        colors_label.setObjectName("settingLabel")
        colors_row.addWidget(colors_label)
        self.white_key_color_button = QPushButton("White", self.interface_card)
        self.white_key_color_button.setObjectName("colorButton")
        self.white_key_color_button.clicked.connect(lambda: self._on_key_color_clicked("white_key"))
        colors_row.addWidget(self.white_key_color_button)
        self.white_key_pressed_color_button = QPushButton("White Pressed", self.interface_card)
        self.white_key_pressed_color_button.setObjectName("colorButton")
        self.white_key_pressed_color_button.clicked.connect(lambda: self._on_key_color_clicked("white_key_pressed"))
        colors_row.addWidget(self.white_key_pressed_color_button)
        self.black_key_color_button = QPushButton("Black", self.interface_card)
        self.black_key_color_button.setObjectName("colorButton")
        self.black_key_color_button.clicked.connect(lambda: self._on_key_color_clicked("black_key"))
        colors_row.addWidget(self.black_key_color_button)
        self.black_key_pressed_color_button = QPushButton("Black Pressed", self.interface_card)
        self.black_key_pressed_color_button.setObjectName("colorButton")
        self.black_key_pressed_color_button.clicked.connect(lambda: self._on_key_color_clicked("black_key_pressed"))
        colors_row.addWidget(self.black_key_pressed_color_button)
        colors_row.addStretch(1)
        interface_layout.addLayout(colors_row)

        updates_row = QHBoxLayout()
        self._configure_settings_row(updates_row)
        self.auto_updates_checkbox = QCheckBox("Automatic Update", self.interface_card)
        self.auto_updates_checkbox.setObjectName("settingCheckbox")
        self.auto_updates_checkbox.setChecked(True)
        self.auto_updates_checkbox.toggled.connect(self.autoCheckUpdatesChanged.emit)
        updates_row.addWidget(self.auto_updates_checkbox)
        self.check_updates_button = QPushButton("Check for Updates now", self.interface_card)
        self.check_updates_button.setObjectName("actionButton")
        self.check_updates_button.clicked.connect(self.checkUpdatesNowRequested.emit)
        updates_row.addWidget(self.check_updates_button)
        updates_row.addStretch(1)
        interface_layout.addLayout(updates_row)

        self.reset_defaults_button = QPushButton("Reset to Defaults", self.settings_body)
        self.reset_defaults_button.setObjectName("resetButton")
        self.reset_defaults_button.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.reset_defaults_button.clicked.connect(self._on_reset_defaults_clicked)
        layout.addWidget(self.reset_defaults_button)
        layout.addStretch(1)
        self._install_slider_styles()
        self._install_checkbox_styles()

    def _build_controls_panel(self) -> None:
        self.controls_body = QWidget(self.controls_scroll)
        self.controls_body.setObjectName("controlsBody")
        self.controls_scroll.setWidget(self.controls_body)

        layout = QVBoxLayout(self.controls_body)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.controls_card = QFrame(self.controls_body)
        self.controls_card.setObjectName("settingsCard")
        controls_layout = QVBoxLayout(self.controls_card)
        controls_layout.setContentsMargins(self._sp(8), self._sp(6), self._sp(8), self._sp(6))
        controls_layout.setSpacing(self._sp(4))
        layout.addWidget(self.controls_card)

        grid = QGridLayout()
        grid.setContentsMargins(self._sp(6), self._sp(2), self._sp(6), self._sp(2))
        grid.setHorizontalSpacing(self._sp(8))
        grid.setVerticalSpacing(self._sp(8))
        grid.setColumnStretch(1, 3)
        grid.setColumnStretch(3, 1)
        grid.setColumnStretch(5, 2)
        self.controls_grid = grid

        instrument_label = QLabel("Instrument", self.controls_card)
        instrument_label.setObjectName("settingLabel")
        self.instrument_combo = ChevronComboBox(self.controls_card)
        self.instrument_combo.setObjectName("instrumentCombo")
        self.instrument_combo.currentIndexChanged.connect(self._on_instrument_index_changed)

        bank_label = QLabel("Bank", self.controls_card)
        bank_label.setObjectName("settingLabel")
        self.bank_combo = ChevronComboBox(self.controls_card)
        self.bank_combo.setObjectName("bankCombo")
        self.bank_combo.currentIndexChanged.connect(self._on_bank_index_changed)

        preset_label = QLabel("Preset", self.controls_card)
        preset_label.setObjectName("settingLabel")
        self.preset_combo = ChevronComboBox(self.controls_card)
        self.preset_combo.setObjectName("presetCombo")
        self.preset_combo.currentIndexChanged.connect(self._on_preset_index_changed)

        midi_label = QLabel("MIDI In", self.controls_card)
        midi_label.setObjectName("settingLabel")
        self.midi_input_combo = ChevronComboBox(self.controls_card)
        self.midi_input_combo.setObjectName("midiInputCombo")
        self.midi_input_combo.currentIndexChanged.connect(self._on_midi_input_index_changed)
        self.midi_input_combo.popupAboutToShow.connect(self.midiInputDropdownOpened.emit)
        self.recording_toggle_button = QPushButton("Start Recording", self.controls_card)
        self.recording_toggle_button.setObjectName("actionButton")
        self.recording_toggle_button.setCheckable(True)
        self.recording_toggle_button.setMinimumWidth(self._sp(110))
        self.recording_toggle_button.toggled.connect(self.recordingToggled.emit)

        self.recording_timer_label = QLabel("00:00", self.controls_card)
        self.recording_timer_label.setObjectName("recordingTimer")
        self.recording_timer_label.setAlignment(Qt.AlignCenter)

        self.save_recording_button = QPushButton("Save recording", self.controls_card)
        self.save_recording_button.setObjectName("actionButton")
        self.save_recording_button.setMinimumWidth(self._sp(124))
        self.save_recording_button.setEnabled(False)
        self.save_recording_button.clicked.connect(self.saveRecordingRequested.emit)

        self.all_notes_off_button = QPushButton("All Notes OFF", self.controls_card)
        self.all_notes_off_button.setObjectName("actionButton")
        self.all_notes_off_button.clicked.connect(self.allNotesOffRequested.emit)

        self.controls_actions = QWidget(self.controls_card)
        actions_layout = QHBoxLayout(self.controls_actions)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(self._sp(6))
        actions_layout.addWidget(self.all_notes_off_button, 1)
        actions_layout.addWidget(self.recording_toggle_button)
        actions_layout.addWidget(self.recording_timer_label)
        actions_layout.addWidget(self.save_recording_button)

        grid.addWidget(instrument_label, 0, 0)
        grid.addWidget(self.instrument_combo, 0, 1)
        grid.addWidget(bank_label, 0, 2)
        grid.addWidget(self.bank_combo, 0, 3)
        grid.addWidget(preset_label, 0, 4)
        grid.addWidget(self.preset_combo, 0, 5)
        grid.addWidget(midi_label, 1, 0)
        grid.addWidget(self.midi_input_combo, 1, 1)
        grid.addWidget(self.controls_actions, 1, 2, 1, 4)

        controls_layout.addLayout(grid)

        self._controls_labels = [instrument_label, bank_label, preset_label, midi_label]

    def _configure_settings_row(self, row: QHBoxLayout) -> None:
                                                               
        row.setContentsMargins(6, self._sp(4), 6, self._sp(4))
        row.setSpacing(self._sp(8))

    def _configure_controls_row(self, row: QHBoxLayout) -> None:
        row.setContentsMargins(4, self._sp(2), 4, self._sp(2))
        row.setSpacing(self._sp(6))

    def _refresh_scaled_layout_metrics(self) -> None:
        controls_outer = self.controls_body.layout()
        if isinstance(controls_outer, QVBoxLayout):
            controls_outer.setSpacing(self._sp(8))

        settings_outer = self.settings_body.layout()
        if isinstance(settings_outer, QVBoxLayout):
            settings_outer.setSpacing(self._sp(8))

        for card, use_controls_row in (
            (self.sound_card, False),
            (self.keyboard_card, False),
            (self.interface_card, False),
            (self.controls_card, True),
        ):
            card_layout = card.layout()
            if not isinstance(card_layout, QVBoxLayout):
                continue
            if use_controls_row:
                card_layout.setContentsMargins(self._sp(6), self._sp(4), self._sp(6), self._sp(4))
                card_layout.setSpacing(self._sp(4))
            else:
                card_layout.setContentsMargins(self._sp(8), self._sp(7), self._sp(8), self._sp(7))
                if card is self.keyboard_card:
                    card_layout.setSpacing(self._sp(4))
                else:
                    card_layout.setSpacing(self._sp(8))
            for idx in range(card_layout.count()):
                item = card_layout.itemAt(idx)
                row = item.layout()
                if not isinstance(row, QHBoxLayout):
                    continue
                if use_controls_row:
                    self._configure_controls_row(row)
                else:
                    self._configure_settings_row(row)

        if hasattr(self, "controls_grid"):
            self.controls_grid.setContentsMargins(self._sp(4), self._sp(1), self._sp(4), self._sp(1))
            self.controls_grid.setHorizontalSpacing(self._sp(6))
            self.controls_grid.setVerticalSpacing(self._sp(6))

        label_width = self._sp(84)
        for label in getattr(self, "_controls_labels", []):
            label.setMinimumWidth(label_width)
            label.setMaximumWidth(label_width)

        self.instrument_combo.setMinimumWidth(self._sp(200))
        self.midi_input_combo.setMinimumWidth(self._sp(200))
        self.bank_combo.setMinimumWidth(self._sp(80))
        self.preset_combo.setMinimumWidth(self._sp(80))
        all_notes_target_width = label_width + self.controls_grid.horizontalSpacing() + self.bank_combo.minimumWidth()
        self.all_notes_off_button.setMinimumWidth(all_notes_target_width)
        self.all_notes_off_button.setMaximumWidth(all_notes_target_width)
        self.recording_toggle_button.setMinimumWidth(self._sp(108))
        self.recording_timer_label.setMinimumWidth(self._sp(50))
        self.recording_timer_label.setMaximumWidth(self._sp(58))
        self.save_recording_button.setMinimumWidth(self._sp(108))
        controls_row_height = self._sp(32)
        self.all_notes_off_button.setMinimumHeight(controls_row_height)
        self.all_notes_off_button.setMaximumHeight(controls_row_height)
        self.recording_toggle_button.setMinimumHeight(controls_row_height)
        self.recording_toggle_button.setMaximumHeight(controls_row_height)
        self.recording_timer_label.setMinimumHeight(controls_row_height)
        self.recording_timer_label.setMaximumHeight(controls_row_height)
        self.save_recording_button.setMinimumHeight(controls_row_height)
        self.save_recording_button.setMaximumHeight(controls_row_height)
        QTimer.singleShot(0, self._sync_all_notes_off_width)

    def _create_section_card(self, title: str, parent: QWidget) -> tuple[QFrame, QVBoxLayout]:
        card = QFrame(parent)
        card.setObjectName("settingsCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(10, 9, 10, 9)
        card_layout.setSpacing(8)
        header = QLabel(title, card)
        header.setObjectName("settingsCardTitle")
        card_layout.addWidget(header)
        return card, card_layout

    def _install_slider_styles(self) -> None:
        self._slider_styles.clear()
        handle_size = max(12, min(36, self._sp(18)))
        groove_height = max(4, min(14, self._sp(6)))
        for slider in (
            self.volume_slider,
            self.velocity_slider,
            self.transpose_slider,
            self.sustain_slider,
            self.ui_scale_slider,
        ):
            style = RoundHandleSliderStyle(
                handle_color=self.theme.text_primary,
                border_color=self.theme.border,
                groove_color=self.theme.border,
                fill_color=self.theme.accent,
                handle_size=handle_size,
                groove_height=groove_height,
                parent=slider,
            )
            slider.setStyle(style)
            self._slider_styles.append(style)

    def _refresh_slider_style_colors(self) -> None:
        handle_size = max(12, min(36, self._sp(18)))
        groove_height = max(4, min(14, self._sp(6)))
        for style in self._slider_styles:
            style.set_colors(
                handle_color=self.theme.text_primary,
                border_color=self.theme.border,
                groove_color=self.theme.border,
                fill_color=self.theme.accent,
            )
            style.set_metrics(handle_size=handle_size, groove_height=groove_height)
        for slider in (
            self.volume_slider,
            self.velocity_slider,
            self.transpose_slider,
            self.sustain_slider,
            self.ui_scale_slider,
        ):
            slider.update()

    def _install_checkbox_styles(self) -> None:
        self._checkbox_styles.clear()
        size = max(18, min(40, self._sp(24)))
        radius = max(3, int(round(size / 5)))
        for checkbox in self.findChildren(QCheckBox):
            style = SquareCheckBoxStyle(
                border_color=self.theme.border,
                fill_color=self.theme.accent,
                check_color=self.theme.text_primary,
                size=size,
                radius=radius,
                parent=checkbox,
            )
            checkbox.setStyle(style)
            self._checkbox_styles.append(style)

    def _refresh_checkbox_style_colors(self) -> None:
        size = max(18, min(40, self._sp(24)))
        radius = max(3, int(round(size / 5)))
        for style in self._checkbox_styles:
            style.set_colors(
                border_color=self.theme.border,
                fill_color=self.theme.accent,
                check_color=self.theme.text_primary,
            )
            style.set_metrics(size=size, radius=radius)
        for checkbox in self.findChildren(QCheckBox):
            checkbox.update()

    def _build_footer(self, outer: QVBoxLayout) -> None:
        self.footer_bar = QFrame(self.centralWidget())
        self.footer_bar.setObjectName("footerBar")
        footer_layout = QVBoxLayout(self.footer_bar)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.setSpacing(self._sp(4))

        divider = QFrame(self.footer_bar)
        divider.setObjectName("footerDivider")
        divider.setFixedHeight(1)
        footer_layout.addWidget(divider)

        row = QHBoxLayout()
        row.setContentsMargins(self._sp(2), 0, self._sp(2), 0)
        row.setSpacing(self._sp(10))

        self.theme_toggle_button = QPushButton("", self.footer_bar)
        self.theme_toggle_button.setObjectName("footerIcon")
        self.theme_toggle_button.setFlat(True)
        self.theme_toggle_button.setIconSize(QSize(self._sp(18), self._sp(18)))
        self.theme_toggle_button.clicked.connect(self._on_theme_toggle_clicked)

        self.settings_toggle_button = QPushButton("Show Settings", self.footer_bar)
        self.settings_toggle_button.setObjectName("footerLink")
        self.settings_toggle_button.clicked.connect(self._on_settings_toggle_clicked)

        self.stats_toggle_button = QPushButton("Hide Stats", self.footer_bar)
        self.stats_toggle_button.setObjectName("footerLink")
        self.stats_toggle_button.clicked.connect(self._on_stats_toggle_clicked)

        self.controls_toggle_button = QPushButton("Show Controls", self.footer_bar)
        self.controls_toggle_button.setObjectName("footerLink")
        self.controls_toggle_button.clicked.connect(self._on_controls_toggle_clicked)

        self.tutorial_button = QPushButton("Tutorial", self.footer_bar)
        self.tutorial_button.setObjectName("footerLink")
        self.tutorial_button.clicked.connect(self.tutorialRequested.emit)

        self.website_button = QPushButton("Official Website", self.footer_bar)
        self.website_button.setObjectName("footerLink")
        self.website_button.clicked.connect(self.websiteRequested.emit)

        for button in (
            self.settings_toggle_button,
            self.stats_toggle_button,
            self.controls_toggle_button,
            self.tutorial_button,
            self.website_button,
        ):
            button.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            button.setFlat(True)

        version_label = QLabel(f"v{APP_VERSION}", self.footer_bar)
        version_label.setObjectName("footerVersion")
        version_label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        row.addWidget(self.theme_toggle_button)
        row.addWidget(self.settings_toggle_button)
        row.addWidget(self.stats_toggle_button)
        row.addStretch(1)
        row.addWidget(self.controls_toggle_button)
        row.addStretch(1)
        row.addWidget(self.tutorial_button)
        row.addWidget(self.website_button)
        row.addWidget(version_label)

        footer_layout.addLayout(row)
        outer.addWidget(self.footer_bar)

    def _build_theme_icon(self, mode: str) -> QIcon:
        if not hasattr(self, "theme_toggle_button"):
            return QIcon()
        size = max(16, self.theme_toggle_button.iconSize().width())
        screen = QGuiApplication.primaryScreen()
        dpr = float(screen.devicePixelRatio()) if screen is not None else 1.0
        px = int(round(size * dpr))
        icon = QPixmap(px, px)
        icon.setDevicePixelRatio(dpr)
        icon.fill(Qt.transparent)

        icon_color = QColor(self.theme.text_primary)

        painter = QPainter(icon)
        painter.setRenderHint(QPainter.Antialiasing, True)

        if mode == "sun":
            painter.setPen(QPen(icon_color, 1.8))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(5, 5, 8, 8)
            rays = (
                (9, 1, 9, 4),
                (9, 14, 9, 17),
                (1, 9, 4, 9),
                (14, 9, 17, 9),
                (3, 3, 5, 5),
                (13, 13, 15, 15),
                (13, 5, 15, 3),
                (3, 15, 5, 13),
            )
            for x1, y1, x2, y2 in rays:
                painter.drawLine(x1, y1, x2, y2)
        else:
            painter.setPen(QPen(icon_color, 1.8))
            painter.setBrush(icon_color)
            painter.drawEllipse(3, 3, 12, 12)
            painter.setCompositionMode(QPainter.CompositionMode_Clear)
            painter.setPen(Qt.NoPen)
            painter.setBrush(Qt.transparent)
            painter.drawEllipse(8, 2, 9, 9)
            painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        painter.end()
        return QIcon(icon)

    def _on_theme_toggle_clicked(self) -> None:
        next_mode = "light" if self._theme_mode == "dark" else "dark"
        self.themeModeChanged.emit(next_mode)

    def _build_tutorial_overlay(self, parent: QWidget) -> None:
        self._tutorial_overlay = TutorialOverlay(self.theme, parent)
        self._tutorial_overlay.nextRequested.connect(self.tutorialNextRequested.emit)
        self._tutorial_overlay.backRequested.connect(self.tutorialBackRequested.emit)
        self._tutorial_overlay.skipRequested.connect(self.tutorialSkipRequested.emit)
        self._tutorial_overlay.finishRequested.connect(self.tutorialFinishRequested.emit)
        self._tutorial_overlay.setGeometry(parent.rect())
        self._tutorial_overlay.hide()

    def _set_interaction_cursors(self) -> None:
        self.piano_widget.setFocusPolicy(Qt.StrongFocus)
        for button in self.findChildren(QPushButton):
            self._set_widget_cursor(button)
            button.setFocusPolicy(Qt.NoFocus)
        for combo in self.findChildren(QComboBox):
            self._set_widget_cursor(combo)
            combo.setFocusPolicy(Qt.NoFocus)
            view = combo.view()
            if view is not None:
                self._set_widget_cursor(view)
                viewport = view.viewport()
                if viewport is not None:
                    self._set_widget_cursor(viewport)
        for checkbox in self.findChildren(QCheckBox):
            self._set_widget_cursor(checkbox)
            checkbox.setFocusPolicy(Qt.NoFocus)
        for slider in self.findChildren(QSlider):
            self._set_widget_cursor(slider)
            slider.setFocusPolicy(Qt.NoFocus)

    @staticmethod
    def _set_widget_cursor(widget: QWidget) -> None:
        if widget.isEnabled() and widget.isVisible():
            widget.setCursor(Qt.PointingHandCursor)
        else:
            widget.unsetCursor()

    def _install_wheel_guards(self) -> None:
        self.installEventFilter(self)
        for widget in self.findChildren(QWidget):
            widget.installEventFilter(self)
        for combo in self.findChildren(QComboBox):
            view = combo.view()
            if view is not None:
                view.installEventFilter(self)
                viewport = view.viewport()
                if viewport is not None:
                    viewport.installEventFilter(self)

    @staticmethod
    def _is_descendant_of(child: object, ancestor: object) -> bool:
        current = child
        while current is not None:
            if current is ancestor:
                return True
            if not hasattr(current, "parent"):
                return False
            current = current.parent()                          
        return False

    def _wheel_allowed(self, watched: object) -> bool:
        for combo in self.findChildren(QComboBox):
            view = combo.view()
            if view is None:
                continue
            if self._is_descendant_of(watched, view):
                return True
        return False

    def _is_settings_descendant(self, watched: object) -> bool:
        return self._is_descendant_of(watched, self.settings_scroll)

    def _is_tutorial_descendant(self, watched: object) -> bool:
        overlay = getattr(self, "_tutorial_overlay", None)
        if overlay is None:
            return False
        return self._is_descendant_of(watched, overlay)

    @staticmethod
    def _is_interactive_control(watched: object) -> bool:
        return isinstance(watched, (QPushButton, QComboBox, QSlider, QCheckBox))

    @staticmethod
    def _scroll_area_by_wheel(scroll_area: QScrollArea, delta_y: int) -> None:
        if delta_y == 0:
            return
        bar: QScrollBar = scroll_area.verticalScrollBar()
        if bar.maximum() <= bar.minimum():
            return
        notches = int(delta_y / 120)
        if notches == 0:
            notches = 1 if delta_y > 0 else -1
        amount = notches * bar.singleStep() * 3
        bar.setValue(bar.value() - amount)

    def eventFilter(self, watched, event):                          
        if event.type() in {
            QEvent.EnabledChange,
            QEvent.Show,
            QEvent.Hide,
            QEvent.Enter,
            QEvent.HoverEnter,
            QEvent.HoverMove,
            QEvent.StyleChange,
            QEvent.Polish,
        }:
            if isinstance(watched, QWidget) and self._is_interactive_control(watched):
                self._set_widget_cursor(watched)

        if self._tutorial_mode and not self._is_tutorial_descendant(watched):
            if event.type() in {
                QEvent.MouseButtonPress,
                QEvent.MouseButtonRelease,
                QEvent.MouseButtonDblClick,
                QEvent.MouseMove,
                QEvent.Wheel,
                QEvent.KeyPress,
                QEvent.KeyRelease,
                QEvent.Shortcut,
                QEvent.ShortcutOverride,
                QEvent.ContextMenu,
            }:
                event.accept()
                return True

        if event.type() == QEvent.Wheel:
            if self._wheel_allowed(watched):
                return super().eventFilter(watched, event)
            if self._is_settings_descendant(watched):
                self._scroll_area_by_wheel(self.settings_scroll, event.angleDelta().y())
                event.accept()
                return True
            if self._is_interactive_control(watched):
                event.accept()
                return True
        return super().eventFilter(watched, event)

    def _position_recording_indicator(self) -> None:
        if not hasattr(self, "recording_indicator"):
            return
        dot = self.recording_indicator
        root = self.centralWidget()
        if root is None:
            return
        margin = self._sp(10)
        x = max(margin, root.width() - dot.width() - margin)
        y = margin
        dot.move(x, y)
        if self._recording_active:
            dot.raise_()


    def _sync_all_notes_off_width(self) -> None:
        if not hasattr(self, "controls_actions"):
            return
        if self.bank_combo.width() <= 0:
            return
        action_left = self.controls_actions.x()
        bank_right = self.bank_combo.x() + self.bank_combo.width()
        target_width = bank_right - action_left
        if target_width < self._sp(96):
            return
        self.all_notes_off_button.setMinimumWidth(target_width)
        self.all_notes_off_button.setMaximumWidth(target_width)

    def _apply_style(self) -> None:
        label_font = self._sp(11)
        value_font = self._sp(11)
        stats_value_font = self._sp(12)
        card_title_font = self._sp(12)
        button_font = self._sp(10)
        footer_font = self._sp(10)
        combo_height = self._sp(24)
        slider_min_h = max(16, self._sp(24))
        self.settings_scroll.setFixedHeight(self._sp(236))
        self.controls_scroll.setFixedHeight(self._sp(90))
        self.panel_divider.setFixedHeight(max(1, self._sp(1)))
        dot_size = max(12, self._sp(14))
        dot_radius = dot_size // 2
        self.recording_indicator.setFixedSize(dot_size, dot_size)
        self._recording_indicator_effect.setBlurRadius(max(16, self._sp(22)))
        glow_color = QColor(self.theme.accent_hover)
        glow_color.setAlpha(210)
        self._recording_indicator_effect.setColor(glow_color)
        self._refresh_scaled_layout_metrics()
        self.setStyleSheet(
            f"""
            QMainWindow {{
                background-color: {self.theme.app_bg};
            }}
            #statsBar {{
                background: {self.theme.panel_bg};
                border: 1px solid {self.theme.border};
                border-radius: 8px;
            }}
            #statsSlot {{
                background: transparent;
                border: none;
                min-width: {self._sp(112)}px;
            }}
            #statsTitle {{
                color: {self.theme.text_secondary};
                font: 600 {self._sp(8)}pt "Segoe UI";
            }}
            #statsValue {{
                color: {self.theme.text_primary};
                font: 700 {stats_value_font}pt "Consolas";
            }}
            #settingsScroll {{
                background: {self.theme.app_bg};
                border: none;
            }}
            #controlsScroll {{
                background: {self.theme.app_bg};
                border: none;
            }}
            QScrollArea#settingsScroll QWidget#qt_scrollarea_viewport {{
                background: {self.theme.app_bg};
                border: none;
            }}
            QScrollArea#controlsScroll QWidget#qt_scrollarea_viewport {{
                background: {self.theme.app_bg};
                border: none;
            }}
            #settingsBody {{
                background: {self.theme.app_bg};
            }}
            #controlsBody {{
                background: {self.theme.app_bg};
            }}
            #settingsCard {{
                background: {self.theme.panel_bg};
                border: 1px solid {self.theme.border};
                border-radius: 8px;
            }}
            #settingsCardTitle {{
                color: {self.theme.text_primary};
                font: 700 {card_title_font}pt "Segoe UI";
            }}
            #settingLabel {{
                color: {self.theme.text_secondary};
                font: 600 {label_font}pt "Segoe UI";
                min-width: {self._sp(80)}px;
            }}
            #settingValue {{
                color: {self.theme.text_primary};
                font: 600 {value_font}pt "Segoe UI";
                min-width: {self._sp(54)}px;
            }}
            #settingCheckbox {{
                color: {self.theme.text_primary};
                font: 600 {self._sp(10)}pt "Segoe UI";
                spacing: 6px;
                padding: {self._sp(2)}px 0 {self._sp(2)}px 0;
                margin: 0;
            }}
            #modeHolder {{
                background: {self.theme.app_bg};
                border: 1px solid {self.theme.border};
                border-radius: 8px;
            }}
            #modeButton {{
                background: transparent;
                color: {self.theme.text_secondary};
                border: none;
                border-radius: 6px;
                padding: {self._sp(4)}px {self._sp(11)}px;
                font: 600 {self._sp(11)}pt "Segoe UI";
            }}
            #modeButton:hover {{
                color: {self.theme.text_primary};
                background: {self.theme.panel_bg};
            }}
            #modeButton:checked {{
                color: {self.theme.text_primary};
                background: {self.theme.accent};
            }}
            #instrumentCombo, #bankCombo, #presetCombo, #animCombo, #midiInputCombo {{
                background: {self.theme.app_bg};
                color: {self.theme.text_primary};
                border: 1px solid {self.theme.border};
                border-radius: 6px;
                padding: {self._sp(2)}px {self._sp(7)}px;
                padding-right: {self._sp(32)}px;
                font: 600 {label_font}pt "Segoe UI";
                min-height: {combo_height}px;
            }}
            #instrumentCombo::drop-down,
            #bankCombo::drop-down,
            #presetCombo::drop-down,
            #animCombo::drop-down,
            #midiInputCombo::drop-down {{
                subcontrol-origin: padding;
                subcontrol-position: top right;
                width: {self._sp(30)}px;
                border: none;
                border-left: 1px solid {self.theme.border};
                border-top-right-radius: 6px;
                border-bottom-right-radius: 6px;
                background: {self.theme.panel_bg};
            }}
            #instrumentCombo::down-arrow,
            #bankCombo::down-arrow,
            #presetCombo::down-arrow,
            #animCombo::down-arrow,
            #midiInputCombo::down-arrow {{
                image: none;
                width: 0px;
                height: 0px;
                border: none;
                margin: 0;
                padding: 0;
                background: transparent;
            }}
            #instrumentCombo QAbstractItemView,
            #bankCombo QAbstractItemView,
            #presetCombo QAbstractItemView,
            #animCombo QAbstractItemView,
            #midiInputCombo QAbstractItemView {{
                background: {self.theme.panel_bg};
                color: {self.theme.text_primary};
                border: 1px solid {self.theme.border};
                selection-background-color: {self.theme.accent};
                font: 600 {label_font}pt "Segoe UI";
            }}
            #volumeSlider,
            #velocitySlider,
            #transposeSlider,
            #sustainSlider,
            #uiScaleSlider {{
                min-height: {slider_min_h}px;
                background: transparent;
            }}
            #colorButton, #actionButton, #resetButton {{
                background: {self.theme.panel_bg};
                color: {self.theme.text_primary};
                border: 1px solid {self.theme.border};
                border-radius: 6px;
                padding: {self._sp(4)}px {self._sp(8)}px;
                font: 600 {button_font}pt "Segoe UI";
            }}
            #colorButton {{
                min-height: {self._sp(26)}px;
                padding: {self._sp(3)}px {self._sp(8)}px;
                font: 600 {self._sp(10)}pt "Segoe UI";
            }}
            #resetButton {{
                min-height: {self._sp(32)}px;
                padding: {self._sp(5)}px {self._sp(10)}px;
                font: 700 {self._sp(11)}pt "Segoe UI";
            }}
            #recordingTimer {{
                background: {self.theme.app_bg};
                color: {self.theme.text_primary};
                border: 1px solid {self.theme.border};
                border-radius: 6px;
                padding: {self._sp(4)}px {self._sp(7)}px;
                font: 700 {self._sp(10)}pt "Consolas";
            }}
            #colorButton:hover, #actionButton:hover, #resetButton:hover {{
                background: {self.theme.accent};
                color: {self.theme.text_primary};
            }}
            #actionButton:disabled {{
                color: {self.theme.text_secondary};
                border-color: {self.theme.border};
                background: {self.theme.app_bg};
            }}
            #footerBar {{
                background: transparent;
                border: none;
            }}
            #footerDivider {{
                background: {self.theme.border};
                border: none;
            }}
            #panelDivider {{
                background: {self.theme.border};
                border: none;
            }}
            #footerLink {{
                background: transparent;
                color: {self.theme.accent};
                border: none;
                padding: 2px 2px;
                font: 700 {footer_font}pt "Segoe UI";
                text-align: left;
            }}
            #footerLink:hover {{
                color: {self.theme.text_primary};
            }}
            #footerVersion {{
                color: {self.theme.text_secondary};
                font: 700 {footer_font}pt "Segoe UI";
            }}
            #footerIcon {{
                background: transparent;
                border: none;
                margin-right: {self._sp(6)}px;
            }}
            #recordingIndicator {{
                background: {self.theme.accent};
                border: 1px solid {self.theme.accent_hover};
                border-radius: {dot_radius}px;
            }}
            """
        )
        self._refresh_key_color_buttons()
        self._refresh_slider_style_colors()
        self._refresh_checkbox_style_colors()
        hover = QColor(self.theme.border)
        hover = hover.lighter(128) if self._theme_mode == "dark" else hover.darker(108)
        for combo in self.findChildren(ChevronComboBox):
            combo.set_arrow_colors(self.theme.text_secondary, self.theme.text_primary)
            combo.set_popup_colors(
                accent=self.theme.accent,
                text=self.theme.text_primary,
                panel=self.theme.panel_bg,
                hover=hover.name(),
            )
        self.set_theme_mode(self._theme_mode)
        self._position_recording_indicator()
        overlay = getattr(self, "_tutorial_overlay", None)
        if overlay is not None:
            overlay.set_theme(self.theme)

    def refresh_fixed_size(self) -> None:
        self.centralWidget().layout().activate()
        self.adjustSize()
        self.setFixedSize(self.sizeHint())
        self._position_recording_indicator()
        QTimer.singleShot(0, self._sync_all_notes_off_width)
        self._sync_tutorial_overlay()

    def resizeEvent(self, event) -> None:                          
        super().resizeEvent(event)
        self._position_recording_indicator()
        QTimer.singleShot(0, self._sync_all_notes_off_width)
        self._sync_tutorial_overlay()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._apply_windows_title_bar_theme()

    def _on_mode_clicked(self, checked: bool, mode: str) -> None:
        if checked:
            self.modeChanged.emit(mode)

    def _on_instrument_index_changed(self, index: int) -> None:
        if index < 0:
            return
        instrument_id = self.instrument_combo.itemData(index, role=Qt.UserRole)
        if isinstance(instrument_id, str):
            self.instrumentChanged.emit(instrument_id)

    def _on_bank_index_changed(self, index: int) -> None:
        if index < 0:
            return
        bank = self.bank_combo.itemData(index, role=Qt.UserRole)
        if isinstance(bank, int):
            self.bankChanged.emit(bank)

    def _on_preset_index_changed(self, index: int) -> None:
        if index < 0:
            return
        preset = self.preset_combo.itemData(index, role=Qt.UserRole)
        if isinstance(preset, int):
            self.presetChanged.emit(preset)

    def _on_midi_input_index_changed(self, index: int) -> None:
        if index < 0:
            return
        device = self.midi_input_combo.itemData(index, role=Qt.UserRole)
        if isinstance(device, str):
            self.midiInputDeviceChanged.emit(device)

    def _on_volume_value_changed(self, value: int) -> None:
        self.volume_value.setText(f"{value}%")
        self.volumeChanged.emit(max(0.0, min(1.0, value / 100.0)))

    def _on_velocity_value_changed(self, value: int) -> None:
        velocity = max(1, min(127, int(value)))
        self.velocity_value.setText(str(velocity))
        self.velocityChanged.emit(velocity)

    def _on_transpose_value_changed(self, value: int) -> None:
        self.transpose_value.setText(f"{value:+d}")
        self.transposeChanged.emit(int(value))

    def _on_sustain_percent_changed(self, value: int) -> None:
        self.sustain_value.setText(f"{int(value)}%")
        self.sustainPercentChanged.emit(int(value))

    def _on_ui_scale_value_changed(self, value: int) -> None:
        scale = UI_SCALE_MIN + (int(value) * UI_SCALE_STEP)
        scale = max(UI_SCALE_MIN, min(UI_SCALE_MAX, round(scale, 2)))
        self.ui_scale_value.setText(f"{int(round(scale * 100.0))}%")
        if not self.ui_scale_slider.isSliderDown():
            self._ui_scale_commit_timer.start()

    def _on_ui_scale_slider_pressed(self) -> None:
        self._ui_scale_commit_timer.stop()

    def _on_ui_scale_slider_released(self) -> None:
        self._ui_scale_commit_timer.stop()
        self._commit_ui_scale_if_changed()

    def _commit_ui_scale_if_changed(self) -> None:
        steps = int(self.ui_scale_slider.value())
        scale = UI_SCALE_MIN + (steps * UI_SCALE_STEP)
        scale = max(UI_SCALE_MIN, min(UI_SCALE_MAX, round(scale, 2)))
        if abs(scale - self._applied_ui_scale) < 0.0001:
            return
        self._applied_ui_scale = scale
        self.uiScaleChanged.emit(scale)

    def _on_anim_index_changed(self, index: int) -> None:
        if index < 0:
            return
        speed = self.anim_speed_combo.itemData(index, role=Qt.UserRole)
        if isinstance(speed, str):
            self.animationSpeedChanged.emit(speed)

    def _on_key_color_clicked(self, target: str) -> None:
        fallback = {
            "white_key": self.theme.white_key,
            "white_key_pressed": self.theme.white_key_pressed,
            "black_key": self.theme.black_key,
            "black_key_pressed": self.theme.black_key_pressed,
        }
        current = (self._key_color_values.get(target) or fallback.get(target) or self.theme.accent)
        color = QColorDialog.getColor(
            QColor(current),
            self,
            "Choose key color",
        )
        self._restore_cursor_state_after_modal()
        if not color.isValid():
            return
        hex_color = color.name(QColor.HexRgb)
        self.set_key_color(target, hex_color)
        self.keyColorChanged.emit(target, hex_color)

    def _on_settings_toggle_clicked(self) -> None:
        self.settingsToggled.emit(not self._settings_visible)

    def _on_controls_toggle_clicked(self) -> None:
        self.controlsToggled.emit(not self._controls_visible)

    def _on_stats_toggle_clicked(self) -> None:
        self.statsToggled.emit(not self._stats_visible)

    def _on_reset_defaults_clicked(self) -> None:
        if self.ask_yes_no(
            "Reset to Defaults",
            "Reset all settings to their default values?",
            default_yes=False,
        ):
            self.resetDefaultsRequested.emit()

    def _message_box_stylesheet(self) -> str:
        button_font = self._sp(10)
        return f"""
            QMessageBox {{
                background: {self.theme.panel_bg};
            }}
            QMessageBox QLabel {{
                color: {self.theme.text_primary};
                font: 600 {button_font}pt "Segoe UI";
            }}
            QMessageBox QPushButton {{
                background: {self.theme.app_bg};
                color: {self.theme.text_primary};
                border: 1px solid {self.theme.border};
                border-radius: 6px;
                min-width: {self._sp(78)}px;
                padding: {self._sp(4)}px {self._sp(10)}px;
                font: 600 {button_font}pt "Segoe UI";
            }}
            QMessageBox QPushButton:hover {{
                background: {self.theme.accent};
                color: {self.theme.text_primary};
            }}
        """

    def _show_themed_message(
        self,
        *,
        icon: QMessageBox.Icon,
        title: str,
        text: str,
        buttons: QMessageBox.StandardButtons = QMessageBox.Ok,
        default_button: QMessageBox.StandardButton | None = None,
    ) -> QMessageBox.StandardButton:
        dialog = QMessageBox(self)
        dialog.setIcon(icon)
        dialog.setWindowTitle(title)
        dialog.setText(str(text))
        dialog.setTextFormat(Qt.PlainText)
        dialog.setStandardButtons(buttons)
        if default_button is not None:
            dialog.setDefaultButton(default_button)
        dialog.setStyleSheet(self._message_box_stylesheet())
        self._apply_dialog_button_cursors(dialog)
        self._apply_windows_title_bar_theme(dialog)
        result = QMessageBox.StandardButton(dialog.exec())
        self._restore_cursor_state_after_modal()
        return result

    @staticmethod
    def _apply_dialog_button_cursors(dialog: QMessageBox) -> None:
        for button in dialog.buttons():
            button.setCursor(Qt.PointingHandCursor)

    def _restore_cursor_state_after_modal_deferred(self) -> None:
        while QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()
        self.setCursor(Qt.ArrowCursor)
        self.unsetCursor()
        self._set_interaction_cursors()

    def _restore_cursor_state_after_modal(self) -> None:
        while QApplication.overrideCursor() is not None:
            QApplication.restoreOverrideCursor()
        self.setCursor(Qt.ArrowCursor)
        self.unsetCursor()
        self._set_interaction_cursors()
        QTimer.singleShot(0, self._restore_cursor_state_after_modal_deferred)

    def show_info(self, title: str, text: str) -> None:
        self._show_themed_message(
            icon=QMessageBox.Information,
            title=title,
            text=text,
        )

    def show_warning(self, title: str, text: str) -> None:
        self._show_themed_message(
            icon=QMessageBox.Warning,
            title=title,
            text=text,
        )

    def ask_yes_no(self, title: str, text: str, *, default_yes: bool = False) -> bool:
        default_button = QMessageBox.Yes if default_yes else QMessageBox.No
        response = self._show_themed_message(
            icon=QMessageBox.Question,
            title=title,
            text=text,
            buttons=QMessageBox.Yes | QMessageBox.No,
            default_button=default_button,
        )
        return response == QMessageBox.Yes

    def _apply_windows_title_bar_theme(self, target: QWidget | None = None) -> None:
        if sys.platform != "win32":
            return
        widget = target or self
        hwnd = int(widget.winId())
        if hwnd <= 0:
            return
        use_dark_title_bar = 1 if self._theme_mode == "dark" else 0
        try:
            import ctypes

            value = ctypes.c_int(use_dark_title_bar)
            for attribute in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (newer, older)
                result = ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    ctypes.c_void_p(hwnd),
                    ctypes.c_uint(attribute),
                    ctypes.byref(value),
                    ctypes.sizeof(value),
                )
                if result == 0:
                    break
        except Exception:
            return

    def set_theme(self, theme: ThemePalette) -> None:
        self.theme = theme
        self.stats_bar.set_theme(theme)
        self.piano_widget.set_theme(theme)
        self._apply_style()

    def set_mode(self, mode: PianoMode) -> None:
        target = self.mode_88_btn if mode == "88" else self.mode_61_btn
        target.setChecked(True)

    def set_instruments(self, instruments: list[InstrumentInfo], selected_id: str) -> None:
        self.instrument_combo.blockSignals(True)
        self.instrument_combo.clear()
        for item in instruments:
            label = f"{item.name} [{item.source}]"
            self.instrument_combo.addItem(label, userData=item.id)

        target_index = -1
        if selected_id:
            for idx in range(self.instrument_combo.count()):
                if self.instrument_combo.itemData(idx, role=Qt.UserRole) == selected_id:
                    target_index = idx
                    break
        if target_index < 0 and self.instrument_combo.count() > 0:
            target_index = 0
        if target_index >= 0:
            self.instrument_combo.setCurrentIndex(target_index)

        self.instrument_combo.blockSignals(False)
        self.instrument_combo.setEnabled(self.instrument_combo.count() > 0)

    def set_bank_preset_options(
        self,
        banks: list[int],
        presets: list[int],
        selected_bank: int,
        selected_preset: int,
    ) -> None:
        self.bank_combo.blockSignals(True)
        self.bank_combo.clear()
        for bank in banks:
            self.bank_combo.addItem(str(bank), userData=int(bank))
        bank_index = -1
        for idx in range(self.bank_combo.count()):
            if self.bank_combo.itemData(idx, role=Qt.UserRole) == selected_bank:
                bank_index = idx
                break
        if bank_index < 0 and self.bank_combo.count() > 0:
            bank_index = 0
        if bank_index >= 0:
            self.bank_combo.setCurrentIndex(bank_index)
        self.bank_combo.blockSignals(False)
        self.bank_combo.setEnabled(self.bank_combo.count() > 0)

        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        for preset in presets:
            self.preset_combo.addItem(str(preset), userData=int(preset))
        preset_index = -1
        for idx in range(self.preset_combo.count()):
            if self.preset_combo.itemData(idx, role=Qt.UserRole) == selected_preset:
                preset_index = idx
                break
        if preset_index < 0 and self.preset_combo.count() > 0:
            preset_index = 0
        if preset_index >= 0:
            self.preset_combo.setCurrentIndex(preset_index)
        self.preset_combo.blockSignals(False)
        self.preset_combo.setEnabled(self.preset_combo.count() > 0)

    def set_midi_input_devices(self, items: list[str], selected: str) -> None:
        self.midi_input_combo.blockSignals(True)
        self.midi_input_combo.clear()
        self.midi_input_combo.addItem("None", userData="")
        for name in items:
            label = str(name).strip()
            if not label:
                continue
            self.midi_input_combo.addItem(label, userData=label)

        target = str(selected).strip()
        target_index = 0
        for idx in range(self.midi_input_combo.count()):
            if self.midi_input_combo.itemData(idx, role=Qt.UserRole) == target:
                target_index = idx
                break
        self.midi_input_combo.setCurrentIndex(target_index)
        self.midi_input_combo.blockSignals(False)
        self.midi_input_combo.setEnabled(True)

    def set_recording_state(self, active: bool, has_take: bool) -> None:
        is_active = bool(active)
        self._recording_active = is_active
        self.recording_toggle_button.blockSignals(True)
        self.recording_toggle_button.setChecked(is_active)
        self.recording_toggle_button.setText("Stop Recording" if is_active else "Start Recording")
        self.recording_toggle_button.blockSignals(False)
        self.save_recording_button.setEnabled(bool(has_take) and not is_active)
        self.recording_indicator.setVisible(is_active)
        self._position_recording_indicator()

    def set_recording_elapsed(self, seconds: int) -> None:
        total = max(0, int(seconds))
        minutes, secs = divmod(total, 60)
        self.recording_timer_label.setText(f"{minutes:02d}:{secs:02d}")

    def set_volume(self, volume: float) -> None:
        value = int(round(max(0.0, min(1.0, volume)) * 100))
        self.volume_slider.blockSignals(True)
        self.volume_slider.setValue(value)
        self.volume_slider.blockSignals(False)
        self.volume_value.setText(f"{value}%")

    def set_velocity(self, value: int) -> None:
        clamped = max(1, min(127, int(value)))
        self.velocity_slider.blockSignals(True)
        self.velocity_slider.setValue(clamped)
        self.velocity_slider.blockSignals(False)
        self.velocity_value.setText(str(clamped))

    def set_transpose(self, value: int) -> None:
        clamped = max(-21, min(21, int(value)))
        self.transpose_slider.blockSignals(True)
        self.transpose_slider.setValue(clamped)
        self.transpose_slider.blockSignals(False)
        self.transpose_value.setText(f"{clamped:+d}")

    def set_sustain_percent(self, value: int) -> None:
        clamped = max(0, min(100, int(value)))
        self.sustain_slider.blockSignals(True)
        self.sustain_slider.setValue(clamped)
        self.sustain_slider.blockSignals(False)
        self.sustain_value.setText(f"{clamped}%")

    def set_hold_space_sustain_mode(self, enabled: bool) -> None:
        self.hold_space_sustain_checkbox.blockSignals(True)
        self.hold_space_sustain_checkbox.setChecked(bool(enabled))
        self.hold_space_sustain_checkbox.blockSignals(False)

    def set_label_visibility(self, show_key_labels: bool, show_note_labels: bool) -> None:
        self.show_key_labels_checkbox.blockSignals(True)
        self.show_note_labels_checkbox.blockSignals(True)
        self.show_key_labels_checkbox.setChecked(bool(show_key_labels))
        self.show_note_labels_checkbox.setChecked(bool(show_note_labels))
        self.show_key_labels_checkbox.blockSignals(False)
        self.show_note_labels_checkbox.blockSignals(False)

    def set_theme_mode(self, mode: str) -> None:
        self._theme_mode = "light" if mode == "light" else "dark"
        if not hasattr(self, "theme_toggle_button"):
            self._apply_windows_title_bar_theme()
            return
        icon_px = max(16, self._sp(18))
        self.theme_toggle_button.setIconSize(QSize(icon_px, icon_px))
        if self._theme_mode == "dark":
            self.theme_toggle_button.setText("")
            self.theme_toggle_button.setIcon(self._build_theme_icon("moon"))
            self.theme_toggle_button.setToolTip("Switch to light mode")
        else:
            self.theme_toggle_button.setText("")
            self.theme_toggle_button.setIcon(self._build_theme_icon("sun"))
            self.theme_toggle_button.setToolTip("Switch to dark mode")
        self._apply_windows_title_bar_theme()

    def set_ui_scale(self, scale: float) -> None:
        clamped = max(0.50, min(2.00, float(scale)))
        self._ui_scale = clamped
        self._applied_ui_scale = clamped
        slider_value = int(round((clamped - UI_SCALE_MIN) / UI_SCALE_STEP))
        self.ui_scale_slider.blockSignals(True)
        self.ui_scale_slider.setValue(slider_value)
        self.ui_scale_slider.blockSignals(False)
        self.ui_scale_value.setText(f"{int(round(clamped * 100.0))}%")
        self._apply_style()
        self.refresh_fixed_size()

    def set_animation_speed(self, speed: str) -> None:
        target = speed if speed in ANIMATION_SPEED_LABELS else "instant"
        self.anim_speed_combo.blockSignals(True)
        for idx in range(self.anim_speed_combo.count()):
            if self.anim_speed_combo.itemData(idx, role=Qt.UserRole) == target:
                self.anim_speed_combo.setCurrentIndex(idx)
                break
        self.anim_speed_combo.blockSignals(False)

    def set_auto_check_updates(self, enabled: bool) -> None:
        self.auto_updates_checkbox.blockSignals(True)
        self.auto_updates_checkbox.setChecked(bool(enabled))
        self.auto_updates_checkbox.blockSignals(False)
    def _build_key_color_button_style(self, background: str, text_color: str) -> str:
        return (
            f"background: {background}; color: {text_color}; border: 1px solid {self.theme.border}; "
            f"border-radius: 6px; padding: {self._sp(4)}px {self._sp(10)}px; "
            f"font: 600 {self._sp(10)}pt 'Segoe UI'; min-height: {self._sp(26)}px;"
        )
    def _refresh_key_color_buttons(self) -> None:
        mapping = {
            "white_key": self.white_key_color_button,
            "white_key_pressed": self.white_key_pressed_color_button,
            "black_key": self.black_key_color_button,
            "black_key_pressed": self.black_key_pressed_color_button,
        }
        labels = {
            "white_key": "White",
            "white_key_pressed": "White Pressed",
            "black_key": "Black",
            "black_key_pressed": "Black Pressed",
        }
        fallback = {
            "white_key": self.theme.white_key,
            "white_key_pressed": self.theme.white_key_pressed,
            "black_key": self.theme.black_key,
            "black_key_pressed": self.theme.black_key_pressed,
        }
        for key, button in mapping.items():
            color = (self._key_color_values.get(key) or fallback[key]).upper()
            text_color = "#111111" if key.startswith("white") else "#F5F5F5"
            label = labels.get(key, "Color")
            button.setText(f"{label} {color}")
            button.setToolTip(f"Current color: {color}")
            button.setStyleSheet(self._build_key_color_button_style(color, text_color))

    def set_key_color(self, target: str, color: str) -> None:
        if target not in self._key_color_values:
            return
        self._key_color_values[target] = color
        self._refresh_key_color_buttons()

    def _update_panel_divider_visibility(self) -> None:
        self.panel_divider.setVisible(self._settings_visible and self._controls_visible)

    def set_settings_visible(self, visible: bool) -> None:
        self._settings_visible = bool(visible)
        self.settings_scroll.setVisible(self._settings_visible)
        self.settings_toggle_button.setText("Hide Settings" if self._settings_visible else "Show Settings")
        self._update_panel_divider_visibility()
        self.refresh_fixed_size()

    def set_controls_visible(self, visible: bool) -> None:
        self._controls_visible = bool(visible)
        self.controls_scroll.setVisible(self._controls_visible)
        self.controls_toggle_button.setText("Hide Controls" if self._controls_visible else "Show Controls")
        self._update_panel_divider_visibility()
        self.refresh_fixed_size()

    def set_stats_visible(self, visible: bool) -> None:
        self._stats_visible = bool(visible)
        self.stats_bar.setVisible(self._stats_visible)
        self.stats_toggle_button.setText("Hide Stats" if self._stats_visible else "Show Stats")
        self.refresh_fixed_size()

    def set_stats_values(self, values: dict[str, str], sustain_active: bool) -> None:
        self.stats_bar.set_values(values, sustain_active=sustain_active)

    def set_window_key_count(self, count: int) -> None:
        self.setWindowTitle(f"{APP_NAME} - {count} Keys")

    def tutorialTargets(self) -> dict[str, QWidget]:
        return {
            "piano": self.piano_widget,
            "stats": self.stats_bar,
            "footer": self.footer_bar,
            "settings_toggle": self.settings_toggle_button,
            "controls_toggle": self.controls_toggle_button,
            "controls_instrument": self.instrument_combo,
            "controls_midi": self.midi_input_combo,
            "controls_recording": self.recording_toggle_button,
            "controls_all_notes_off": self.all_notes_off_button,
            "sound_section": self.sound_card,
            "sound_velocity": self.velocity_slider,
            "keyboard_section": self.keyboard_card,
            "interface_section": self.interface_card,
            "controls_section": self.controls_card,
            "reset_defaults": self.reset_defaults_button,
        }

    def ensure_settings_target_visible(self, target: QWidget) -> None:
        if not self._is_descendant_of(target, self.settings_scroll):
            return
        self.settings_scroll.ensureWidgetVisible(target, 0, self._sp(18))
        self._sync_tutorial_overlay()

    def ensure_controls_target_visible(self, target: QWidget) -> None:
        if not self._is_descendant_of(target, self.controls_scroll):
            return
        self._sync_tutorial_overlay()

    def set_tutorial_mode(self, active: bool) -> None:
        self._tutorial_mode = bool(active)
        overlay = getattr(self, "_tutorial_overlay", None)
        if overlay is None:
            return
        if self._tutorial_mode:
            self._sync_tutorial_overlay()
            overlay.show()
            overlay.raise_()
            overlay.setFocus(Qt.ActiveWindowFocusReason)
        else:
            overlay.hide()

    def update_tutorial_step(
        self,
        *,
        title: str,
        body: str,
        index: int,
        total: int,
        target_widget: QWidget | None,
    ) -> None:
        overlay = getattr(self, "_tutorial_overlay", None)
        if overlay is None:
            return
        target_rect: QRect | None = None
        if target_widget is not None and target_widget.isVisible():
            top_left = target_widget.mapTo(self.centralWidget(), QPoint(0, 0))
            target_rect = QRect(top_left, target_widget.size())
        overlay.set_step(
            title=title,
            body=body,
            index=index,
            total=total,
            is_first=index <= 0,
            is_last=index >= (total - 1),
        )
        overlay.set_target_rect(target_rect)
        overlay.raise_()
        overlay.setFocus(Qt.ActiveWindowFocusReason)

    def _sync_tutorial_overlay(self) -> None:
        overlay = getattr(self, "_tutorial_overlay", None)
        if overlay is None:
            return
        overlay.sync_to_parent()
