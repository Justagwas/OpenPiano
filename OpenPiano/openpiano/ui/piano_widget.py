
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QMouseEvent, QPaintEvent, QPainter, QPen
from PySide6.QtWidgets import QWidget

from openpiano.core.config import ANIMATION_PROFILE, UI_SCALE_MAX, UI_SCALE_MIN
from openpiano.core.keymap import binding_to_label, is_black_key
from openpiano.core.theme import ThemePalette, apply_key_color_overrides

if TYPE_CHECKING:
    from openpiano.core.config import AnimationSpeed
    from openpiano.core.keymap import Binding, PianoMode


@dataclass(slots=True)
class _KeyRect:
    note: int
    rect: QRectF


def _lerp_channel(a: int, b: int, t: float) -> int:
    return int(round(a + ((b - a) * t)))


def _lerp_color(start: QColor, end: QColor, t: float) -> QColor:
    return QColor(
        _lerp_channel(start.red(), end.red(), t),
        _lerp_channel(start.green(), end.green(), t),
        _lerp_channel(start.blue(), end.blue(), t),
        _lerp_channel(start.alpha(), end.alpha(), t),
    )


class PianoWidget(QWidget):
    
    notePressed = Signal(int)
    noteReleased = Signal(int)
    dragNoteChanged = Signal(object)
    keybindKeySelected = Signal(int)

    def __init__(self, theme: ThemePalette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._base_theme = theme
        self._theme = theme
        self._mode: PianoMode = "61"
        self._ui_scale = 1.0
        self._animation_speed: AnimationSpeed = "instant"
        self._show_key_labels = True
        self._show_note_labels = True
        self._mapping: dict[int, Binding] = {}
        self._labels: dict[int, str] = {}
        self._notes: list[int] = []
        self._white_note_count = 0
        self._white_rects: list[_KeyRect] = []
        self._black_rects: list[_KeyRect] = []
        self._rect_by_note: dict[int, QRectF] = {}
        self._pressed_notes: set[int] = set()
        self._mouse_pressed = False
        self._last_drag_note: int | None = None
        self._keybind_edit_mode = False
        self._selected_keybind_note: int | None = None
        self._anim_t: dict[int, float] = {}
        self._anim_step: dict[int, float] = {}
        self._anim_timer_id = self.startTimer(16)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent, True)

    def _sp(self, value: int) -> int:
        return max(1, int(round(value * self._ui_scale)))

    def _white_width(self) -> int:
        return self._sp(26)

    def _white_height(self) -> int:
        return self._sp(220)

    def _black_width(self) -> int:
        return self._sp(18)

    def _black_height(self) -> int:
        return self._sp(140)

    def _gap(self) -> int:
        return self._sp(1)

    def _top_margin(self) -> int:
        return self._sp(8)

    def _side_margin(self) -> int:
        return self._sp(12)

    def sizeHint(self) -> QSize:                          
        width, height = self._desired_size()
        return QSize(width, height)

    def minimumSizeHint(self) -> QSize:                          
        width, height = self._desired_size()
        return QSize(width, height)

    def _desired_size(self) -> tuple[int, int]:
        white_count = max(1, self._white_note_count)
        width = (self._side_margin() * 2) + (white_count * self._white_width()) + ((white_count - 1) * self._gap())
        height = (self._top_margin() * 2) + self._white_height()
        return width, height

    def set_theme(self, theme: ThemePalette) -> None:
        self._base_theme = theme
        self._theme = theme
        self.update()

    def set_ui_scale(self, scale: float) -> None:
        clamped = max(UI_SCALE_MIN, min(UI_SCALE_MAX, float(scale)))
        if abs(clamped - self._ui_scale) < 0.001:
            return
        self._ui_scale = clamped
        self._rebuild_geometry()
        self.updateGeometry()
        self.update()

    def set_mode(self, mode: "PianoMode", mapping: dict[int, Binding], labels: dict[int, str]) -> None:
        self._mode = mode
        self._mapping = dict(mapping)
        self._labels = dict(labels)
        self._notes = sorted(self._mapping.keys())
        self._white_note_count = sum(1 for note in self._notes if not is_black_key(note))
        if self._selected_keybind_note not in self._mapping:
            self._selected_keybind_note = None
        self._pressed_notes.clear()
        self._anim_t.clear()
        self._anim_step.clear()
        self._rebuild_geometry()
        self.updateGeometry()
        self.update()

    def set_keybind_edit_mode(self, active: bool, selected_note: int | None = None) -> None:
        self._keybind_edit_mode = bool(active)
        self._mouse_pressed = False
        self._last_drag_note = None
        if self._keybind_edit_mode:
            self._selected_keybind_note = selected_note if selected_note in self._mapping else None
        else:
            self._selected_keybind_note = None
        self.update()

    def set_selected_keybind_note(self, note: int | None) -> None:
        selected = note if isinstance(note, int) and note in self._mapping else None
        if selected == self._selected_keybind_note:
            return
        self._selected_keybind_note = selected
        self.update()

    def set_label_visibility(self, show_key_labels: bool, show_note_labels: bool) -> None:
        self._show_key_labels = bool(show_key_labels)
        self._show_note_labels = bool(show_note_labels)
        self.update()

    def set_animation_speed(self, speed: str) -> None:
        speed_value = speed if speed in ANIMATION_PROFILE else "instant"
        self._animation_speed = speed_value                            

    def set_key_colors(self, white: str, white_pressed: str, black: str, black_pressed: str) -> None:
        self._theme = apply_key_color_overrides(
            self._base_theme,
            white=white,
            white_pressed=white_pressed,
            black=black,
            black_pressed=black_pressed,
        )
        self.update()

    def set_pressed(self, note: int, pressed: bool) -> None:
        if note not in self._rect_by_note:
            return
        target_pressed = bool(pressed)
        was_pressed = note in self._pressed_notes
        if target_pressed == was_pressed:
            return

        if target_pressed:
            self._pressed_notes.add(note)
        else:
            self._pressed_notes.discard(note)

        frames, _, _, _ = ANIMATION_PROFILE[self._animation_speed]
        if frames <= 0:
            self._anim_t[note] = 1.0 if target_pressed else 0.0
            self._anim_step.pop(note, None)
        else:
            start = self._anim_t.get(note, 1.0 if was_pressed else 0.0)
            self._anim_t[note] = start
            self._anim_step[note] = (1.0 / max(1, frames)) * (1.0 if target_pressed else -1.0)

        rect = self._rect_by_note.get(note)
        if rect is not None:
            self.update(rect.toRect().adjusted(-2, -2, 2, 2))

    def note_at(self, pos: QPoint) -> int | None:
        point = QPointF(pos)
        for item in self._black_rects:
            if item.rect.contains(point):
                return item.note
        for item in self._white_rects:
            if item.rect.contains(point):
                return item.note
        return None

    def resizeEvent(self, event) -> None:                          
        super().resizeEvent(event)
        self._rebuild_geometry()

    def timerEvent(self, event) -> None:                          
        if event.timerId() != self._anim_timer_id:
            return super().timerEvent(event)
        if not self._anim_step:
            return
        changed_rects: list[QRect] = []
        for note, step in list(self._anim_step.items()):
            current = self._anim_t.get(note, 0.0)
            next_value = max(0.0, min(1.0, current + step))
            self._anim_t[note] = next_value
            done = (step > 0 and next_value >= 1.0) or (step < 0 and next_value <= 0.0)
            if done:
                self._anim_step.pop(note, None)
            rect = self._rect_by_note.get(note)
            if rect is not None:
                changed_rects.append(rect.toRect().adjusted(-2, -2, 2, 2))
        for rect in changed_rects:
            self.update(rect)

    def _rebuild_geometry(self) -> None:
        self._white_rects.clear()
        self._black_rects.clear()
        self._rect_by_note.clear()
        if not self._notes:
            return

        white_w = float(self._white_width())
        white_h = float(self._white_height())
        black_w = float(self._black_width())
        black_h = float(self._black_height())
        gap = float(self._gap())
        top = float(self._top_margin())
        left = float(self._side_margin())

        white_x_by_note: dict[int, float] = {}
        x = left
        for note in self._notes:
            if is_black_key(note):
                continue
            rect = QRectF(x, top, white_w, white_h)
            self._white_rects.append(_KeyRect(note=note, rect=rect))
            self._rect_by_note[note] = rect
            white_x_by_note[note] = x
            x += white_w + gap

        for note in self._notes:
            if not is_black_key(note):
                continue
            prev_white = note - 1
            while prev_white >= self._notes[0] and is_black_key(prev_white):
                prev_white -= 1
            if prev_white not in white_x_by_note:
                continue
            center = white_x_by_note[prev_white] + white_w
            x1 = center - (black_w / 2.0)
            rect = QRectF(x1, top, black_w, black_h)
            self._black_rects.append(_KeyRect(note=note, rect=rect))
            self._rect_by_note[note] = rect

    def _note_fill_color(self, note: int) -> QColor:
        is_black = is_black_key(note)
        base = QColor(self._theme.black_key if is_black else self._theme.white_key)
        pressed = QColor(self._theme.black_key_pressed if is_black else self._theme.white_key_pressed)
        t = self._anim_t.get(note, 1.0 if note in self._pressed_notes else 0.0)
        return _lerp_color(base, pressed, t)

    def paintEvent(self, event: QPaintEvent) -> None:                          
        clip = event.rect()
        clip_f = QRectF(clip)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        painter.setClipRegion(event.region())
        painter.fillRect(clip, QColor(self._theme.panel_bg))

        if not self._notes:
            painter.end()
            return

        white_outline = QColor(self._theme.border)
        white_top = QColor("#FFFFFF")
        white_bottom = QColor("#C8C8CC")
        white_outline_pen = QPen(white_outline, 1)
        white_top_pen = QPen(white_top, 1)
        white_bottom_pen = QPen(white_bottom, 1)
        draw_labels = self._show_key_labels or self._show_note_labels

                                
        for item in self._white_rects:
            rect = item.rect
            if not rect.intersects(clip_f):
                continue
            fill = self._note_fill_color(item.note)
            painter.fillRect(rect, fill)
            painter.setPen(white_outline_pen)
            painter.drawRect(rect)
            painter.setPen(white_top_pen)
            painter.drawLine(
                int(rect.left()) + 1,
                int(rect.top()) + 1,
                int(rect.right()) - 1,
                int(rect.top()) + 1,
            )
            painter.setPen(white_bottom_pen)
            painter.drawLine(
                int(rect.left()) + 1,
                int(rect.bottom()) - 1,
                int(rect.right()) - 1,
                int(rect.bottom()) - 1,
            )
            if draw_labels:
                self._draw_labels(painter, item.note, rect, black=False)

                                 
        black_top = QColor("#F5F5F5")
        black_side = QColor("#36363A")
        black_outline_pen = QPen(QColor("#000000"), 1)
        black_top_pen = QPen(black_top, 1)
        black_side_pen = QPen(black_side, 1)
        for item in self._black_rects:
            rect = item.rect
            if not rect.intersects(clip_f):
                continue
            fill = self._note_fill_color(item.note)
            painter.fillRect(rect, fill)
            painter.setPen(black_outline_pen)
            painter.drawRect(rect)
            painter.setPen(black_top_pen)
            painter.drawLine(
                int(rect.left()) + 1,
                int(rect.top()) + 1,
                int(rect.right()) - 1,
                int(rect.top()) + 1,
            )
            painter.setPen(black_side_pen)
            painter.drawLine(
                int(rect.left()) + 1,
                int(rect.top()) + 1,
                int(rect.left()) + 1,
                int(rect.bottom()) - 1,
            )
            painter.drawLine(
                int(rect.right()) - 1,
                int(rect.top()) + 1,
                int(rect.right()) - 1,
                int(rect.bottom()) - 1,
            )
            if draw_labels:
                self._draw_labels(painter, item.note, rect, black=True)

                                
        first = self._white_rects[0].rect
        last = self._white_rects[-1].rect
        outer = QRectF(
            first.left(),
            first.top(),
            (last.right() - first.left()) + 1.0,
            first.height(),
        )
        if outer.intersects(clip_f):
            painter.setPen(white_outline_pen)
            painter.drawRect(outer)

        selected = self._selected_keybind_note
        selected_rect = self._rect_by_note.get(selected) if selected is not None else None
        if self._keybind_edit_mode and selected_rect is not None and selected_rect.intersects(clip_f):
            accent = QColor(self._theme.accent)
            accent.setAlpha(55)
            painter.fillRect(selected_rect.adjusted(1.0, 1.0, -1.0, -1.0), accent)
            painter.setPen(QPen(QColor(self._theme.accent), 2))
            painter.drawRect(selected_rect.adjusted(1.0, 1.0, -1.0, -1.0))
        painter.end()

    def _draw_labels(self, painter: QPainter, note: int, rect: QRectF, black: bool) -> None:
        binding = self._mapping.get(note)
        note_text = self._labels.get(note, "")
        hotkey_text = binding_to_label(binding) if binding is not None else ""
        if not self._show_key_labels:
            hotkey_text = ""
        if not self._show_note_labels:
            note_text = ""
        if not hotkey_text and not note_text:
            return

        color = QColor("#F6F6F6" if black else "#111827")
        painter.setPen(color)

        def draw_multiline_bottom(
            bottom: float,
            text: str,
            font_size: int,
            line_height: int,
            line_gap: int,
        ) -> None:
            lines = [line for line in text.split("\n") if line]
            if not lines:
                return
            fitted_size = max(self._sp(6), int(font_size))
            width_limit = max(1, int(rect.width()) - self._sp(2))
            while fitted_size > self._sp(6):
                font = QFont("Segoe UI", fitted_size, QFont.Weight.Bold)
                metrics = QFontMetrics(font)
                if max(metrics.horizontalAdvance(line) for line in lines) <= width_limit:
                    break
                fitted_size -= 1
            draw_font = QFont("Segoe UI", fitted_size, QFont.Weight.Bold)
            metrics = QFontMetrics(draw_font)
            lh = max(self._sp(9), int(line_height), metrics.height())
            gap = max(0, int(line_gap))
            total_height = (lh * len(lines)) - gap
            start_y = bottom - total_height
            painter.setFont(draw_font)
            for idx, line in enumerate(lines):
                y = start_y + (idx * lh)
                painter.drawText(
                    QRectF(rect.left(), y, rect.width(), lh),
                    Qt.AlignHCenter | Qt.AlignVCenter,
                    line,
                )

        if black:
            key_font_size = self._sp(9)
            note_font_size = self._sp(7)
            mode_gap = self._sp(4) if self._mode == "88" else 0
            hotkey_bottom = rect.bottom() - self._sp(21) - mode_gap
            note_bottom = rect.bottom() - self._sp(8)
            if hotkey_text and note_text:
                if "\n" in hotkey_text:
                    draw_multiline_bottom(
                        hotkey_bottom,
                        hotkey_text,
                        key_font_size,
                        self._sp(10),
                        self._sp(3),
                    )
                else:
                    painter.setFont(QFont("Segoe UI", key_font_size, QFont.Weight.Bold))
                    painter.drawText(
                        QRectF(rect.left(), hotkey_bottom - self._sp(18), rect.width(), self._sp(18)),
                        Qt.AlignHCenter | Qt.AlignBottom,
                        hotkey_text,
                    )
                painter.setFont(QFont("Segoe UI", note_font_size, QFont.Weight.Bold))
                painter.drawText(
                    QRectF(rect.left(), note_bottom - self._sp(14), rect.width(), self._sp(14)),
                    Qt.AlignHCenter | Qt.AlignBottom,
                    note_text,
                )
            else:
                text = hotkey_text or note_text
                if "\n" in text:
                    draw_multiline_bottom(
                        rect.bottom() - self._sp(12),
                        text,
                        key_font_size,
                        self._sp(10),
                        self._sp(3),
                    )
                else:
                    text_font_size = key_font_size if hotkey_text else note_font_size
                    text_height = self._sp(18) if hotkey_text else self._sp(14)
                    painter.setFont(QFont("Segoe UI", text_font_size, QFont.Weight.Bold))
                    painter.drawText(
                        QRectF(rect.left(), note_bottom - text_height, rect.width(), text_height),
                        Qt.AlignHCenter | Qt.AlignBottom,
                        text,
                    )
            return

        hotkey_font_size = self._sp(11)
        note_font_size = self._sp(10)
        mode_gap = self._sp(5) if self._mode == "88" else 0
        hotkey_bottom = rect.bottom() - self._sp(31) - mode_gap
        note_bottom = rect.bottom() - self._sp(9)
        if hotkey_text and note_text:
            if "\n" in hotkey_text:
                draw_multiline_bottom(
                    hotkey_bottom,
                    hotkey_text,
                    hotkey_font_size,
                    self._sp(12),
                    self._sp(4),
                )
            else:
                painter.setFont(QFont("Segoe UI", hotkey_font_size, QFont.Weight.Bold))
                painter.drawText(
                    QRectF(rect.left(), hotkey_bottom - self._sp(20), rect.width(), self._sp(20)),
                    Qt.AlignHCenter | Qt.AlignBottom,
                    hotkey_text,
                )
            painter.setFont(QFont("Segoe UI", note_font_size, QFont.Weight.Bold))
            painter.drawText(
                QRectF(rect.left(), note_bottom - self._sp(18), rect.width(), self._sp(18)),
                Qt.AlignHCenter | Qt.AlignBottom,
                note_text,
            )
        else:
            text = hotkey_text or note_text
            if "\n" in text:
                draw_multiline_bottom(
                    rect.bottom() - self._sp(15),
                    text,
                    hotkey_font_size,
                    self._sp(12),
                    self._sp(4),
                )
            else:
                text_font_size = hotkey_font_size if hotkey_text else note_font_size
                painter.setFont(QFont("Segoe UI", text_font_size, QFont.Weight.Bold))
                painter.drawText(
                    QRectF(rect.left(), note_bottom - self._sp(18), rect.width(), self._sp(18)),
                    Qt.AlignHCenter | Qt.AlignBottom,
                    text,
                )

    def mousePressEvent(self, event: QMouseEvent) -> None:                          
        if event.button() != Qt.LeftButton:
            return super().mousePressEvent(event)
        if self._keybind_edit_mode:
            note = self.note_at(event.position().toPoint())
            self._selected_keybind_note = note
            if note is not None:
                self.keybindKeySelected.emit(note)
            self.update()
            event.accept()
            return
        note = self.note_at(event.position().toPoint())
        self._mouse_pressed = True
        self._last_drag_note = note
        if note is not None:
            self.notePressed.emit(note)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:                          
        if self._keybind_edit_mode:
            event.accept()
            return
        note = self.note_at(event.position().toPoint())
        if self._mouse_pressed:
            if note != self._last_drag_note:
                self._last_drag_note = note
                self.dragNoteChanged.emit(note)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:                          
        if event.button() != Qt.LeftButton:
            return super().mouseReleaseEvent(event)
        if self._keybind_edit_mode:
            event.accept()
            return
        note = self._last_drag_note
        self._mouse_pressed = False
        self._last_drag_note = None
        if note is not None:
            self.noteReleased.emit(note)
        self.dragNoteChanged.emit(None)
        event.accept()

    def leaveEvent(self, event) -> None:                          
        if self._keybind_edit_mode:
            super().leaveEvent(event)
            return
        if self._mouse_pressed:
            self._last_drag_note = None
            self.dragNoteChanged.emit(None)
        super().leaveEvent(event)

