
from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6.QtCore import QPoint, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QMouseEvent, QPaintEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from openpiano.core.config import (
    ANIMATION_PROFILE,
    DEFAULT_PIANO_STYLE,
    UI_SCALE_MAX,
    UI_SCALE_MIN,
    normalize_piano_style,
)
from openpiano.core.keymap import binding_to_label, is_black_key
from openpiano.core.theme import ThemePalette, apply_key_color_overrides

if TYPE_CHECKING:
    from openpiano.core.config import AnimationSpeed
    from openpiano.core.keymap import Binding, PianoMode


@dataclass(slots=True)
class _KeyRect:
    note: int
    rect: QRectF


@dataclass(slots=True)
class _EffectStream:
    note: int
    x: float
    key_top: float
    width: float
    height: float
    started_at: float
    released_at: float | None = None
    release_distance: float = 0.0
    release_duration: float = 1.2
    release_height: float = 0.0


@dataclass(slots=True)
class _EffectSpark:
    x: float
    y: float
    dx: float
    dy: float
    size: float
    started_at: float
    duration: float


def _lerp_channel(a: int, b: int, t: float) -> int:
    return int(round(a + ((b - a) * t)))


def _lerp_color(start: QColor, end: QColor, t: float) -> QColor:
    return QColor(
        _lerp_channel(start.red(), end.red(), t),
        _lerp_channel(start.green(), end.green(), t),
        _lerp_channel(start.blue(), end.blue(), t),
        _lerp_channel(start.alpha(), end.alpha(), t),
    )


def _with_alpha(color: QColor, alpha: int) -> QColor:
    copy = QColor(color)
    copy.setAlpha(max(0, min(255, int(alpha))))
    return copy


def _readable_text_color(background: QColor) -> QColor:
    luminance = (
        (0.2126 * background.redF())
        + (0.7152 * background.greenF())
        + (0.0722 * background.blueF())
    )
    return QColor("#111827" if luminance > 0.54 else "#F6F6F6")


class PianoWidget(QWidget):
    
    notePressed = Signal(int)
    noteReleased = Signal(int)
    dragNoteChanged = Signal(object)
    keybindKeySelected = Signal(int)
    _MAX_EFFECT_SPARKS = 96
    _MAX_RELEASED_STREAMS = 72
    _EFFECT_SPEED_PER_SECOND = 260

    def __init__(self, theme: ThemePalette, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._base_theme = theme
        self._theme = theme
        self._mode: PianoMode = "61"
        self._ui_scale = 1.0
        self._animation_speed: AnimationSpeed = "instant"
        self._piano_style = DEFAULT_PIANO_STYLE
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
        self._active_effect_streams: dict[int, _EffectStream] = {}
        self._released_effect_streams: list[_EffectStream] = []
        self._effect_sparks: list[_EffectSpark] = []
        self._last_effect_tick = 0.0
        self._anim_timer_id = 0
        self.setMouseTracking(True)

    def _ensure_animation_timer(self) -> None:
        if self._anim_timer_id == 0:
            self._anim_timer_id = self.startTimer(16)

    def _animation_timer_needed(self) -> bool:
        if self._anim_step or self._released_effect_streams or self._effect_sparks:
            return True
        if self._piano_style != "effects" or not self._active_effect_streams:
            return False
        max_height = max(self._sp(42), self._top_margin() - self._sp(10))
        return any(stream.height < max_height for stream in self._active_effect_streams.values())

    def _stop_animation_timer_if_idle(self) -> None:
        if self._anim_timer_id != 0 and not self._animation_timer_needed():
            timer_id = self._anim_timer_id
            self._anim_timer_id = 0
            self.killTimer(timer_id)

    def _sp(self, value: int) -> int:
        return max(1, int(round(value * self._ui_scale)))

    def _white_width(self) -> int:
        return self._sp(26)

    def _white_height(self) -> int:
        return self._sp(220)

    def _black_width(self) -> int:
        return self._sp(16)

    def _black_height(self) -> int:
        return self._sp(140)

    def _gap(self) -> int:
        return self._sp(1)

    def _top_margin(self) -> int:
        if self._piano_style == "effects":
            dynamic = int(self.height()) - self._white_height() - self._side_margin()
            return max(0, dynamic)
        return self._sp(6)

    def _side_margin(self) -> int:
        if self._piano_style == "effects":
            return self._sp(24)
        return self._sp(8)

    def sizeHint(self) -> QSize:                          
        width, height = self._desired_size()
        return QSize(width, height)

    def minimumSizeHint(self) -> QSize:                          
        width, height = self._desired_size()
        if self._piano_style == "effects":
            width = 0
            height = self._white_height() + self._side_margin()
        return QSize(width, height)

    def _desired_size(self) -> tuple[int, int]:
        white_count = max(1, self._white_note_count)
        width = (self._side_margin() * 2) + (white_count * self._white_width()) + ((white_count - 1) * self._gap())
        if self._piano_style == "effects":
            height = self._sp(640)
            return width, height
        height = self._top_margin() + self._white_height() + self._side_margin()
        return width, height

    def key_top_y(self) -> int:
        return self._top_margin()

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
        self.clear_effects()
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

    def set_piano_style(self, style: str) -> None:
        target = normalize_piano_style(style)
        if target == self._piano_style:
            return
        self._piano_style = target
        if target != "effects":
            self.clear_effects()
        self._rebuild_geometry()
        self.updateGeometry()
        self.update()

    def set_key_colors(self, white: str, white_pressed: str, black: str, black_pressed: str) -> None:
        self._theme = apply_key_color_overrides(
            self._base_theme,
            white=white,
            white_pressed=white_pressed,
            black=black,
            black_pressed=black_pressed,
        )
        self.update()

    def clear_effects(self) -> None:
        self._active_effect_streams.clear()
        self._released_effect_streams.clear()
        self._effect_sparks.clear()
        self._last_effect_tick = 0.0
        self._update_effect_stage()
        self._stop_animation_timer_if_idle()

    def _effect_stage_update_rect(self) -> QRect:
        key_top = self._top_margin()
        return self.rect().adjusted(0, 0, 0, -(self.height() - key_top - self._sp(3)))

    def _update_effect_stage(self) -> None:
        rect = self._effect_stage_update_rect()
        if rect.isValid() and not rect.isEmpty():
            self.update(rect)

    def _trim_released_streams(self) -> None:
        overflow = len(self._released_effect_streams) - self._MAX_RELEASED_STREAMS
        if overflow <= 0:
            return
        self._released_effect_streams.sort(key=lambda stream: stream.released_at or 0.0)
        del self._released_effect_streams[:overflow]

    def _effect_speed(self) -> float:
        return float(self._sp(self._EFFECT_SPEED_PER_SECOND))

    def _start_note_effect(self, note: int, rect: QRectF) -> None:
        if self._piano_style != "effects":
            return
        now = time.monotonic()
        width_inset = min(self._sp(5 if not is_black_key(note) else 3), rect.width() * 0.22)
        stream = _EffectStream(
            note=note,
            x=rect.center().x(),
            key_top=rect.top(),
            width=max(self._sp(5), rect.width() - width_inset),
            height=float(self._sp(14)),
            started_at=now,
        )
        self._active_effect_streams[note] = stream

        active_pressure = min(
            1.0,
            (
                len(self._active_effect_streams)
                + len(self._released_effect_streams)
                + len(self._effect_sparks) / 18.0
            )
            / 42.0,
        )
        spark_count = 4 if active_pressure > 0.72 else (6 if is_black_key(note) else 9)
        for _ in range(spark_count):
            self._effect_sparks.append(
                _EffectSpark(
                    x=rect.center().x() + random.uniform(-rect.width() * 0.36, rect.width() * 0.36),
                    y=rect.top() + random.uniform(-self._sp(3), self._sp(5)),
                    dx=random.uniform(-self._sp(26), self._sp(26)),
                    dy=random.uniform(-self._sp(72), -self._sp(18)),
                    size=random.uniform(self._sp(1), self._sp(3)),
                    started_at=now,
                    duration=random.uniform(0.34, 0.78),
                )
            )
        if len(self._effect_sparks) > self._MAX_EFFECT_SPARKS:
            del self._effect_sparks[: len(self._effect_sparks) - self._MAX_EFFECT_SPARKS]
        self._trim_released_streams()
        self._ensure_animation_timer()
        self._update_effect_stage()

    def _release_note_effect(self, note: int) -> None:
        stream = self._active_effect_streams.pop(note, None)
        if stream is None:
            return
        stream.released_at = time.monotonic()
        stream.release_height = max(stream.height, self._sp(14))
        stream.release_distance = max(self._sp(140), stream.key_top + stream.release_height + self._sp(54))
        stream.release_duration = max(0.78, stream.release_distance / max(1.0, self._effect_speed()))
        self._released_effect_streams.append(stream)
        self._trim_released_streams()
        self._ensure_animation_timer()
        self._update_effect_stage()

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
            self._ensure_animation_timer()

        rect = self._rect_by_note.get(note)
        if rect is not None:
            if target_pressed:
                self._start_note_effect(note, rect)
            else:
                self._release_note_effect(note)
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
        needs_effect_update = self._advance_effects()
        if not self._anim_step:
            if needs_effect_update:
                self._update_effect_stage()
            self._stop_animation_timer_if_idle()
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
        if needs_effect_update:
            self._update_effect_stage()
        self._stop_animation_timer_if_idle()

    def _advance_effects(self) -> bool:
        if self._piano_style != "effects":
            if self._active_effect_streams or self._released_effect_streams or self._effect_sparks:
                self.clear_effects()
            return False
        if (
            not self._active_effect_streams
            and not self._released_effect_streams
            and not self._effect_sparks
        ):
            return False
        now = time.monotonic()
        if self._last_effect_tick > 0 and (now - self._last_effect_tick) < 0.012:
            return False
        self._last_effect_tick = now
        max_height = max(self._sp(42), self._top_margin() - self._sp(10))
        changed = False
        speed = self._effect_speed()
        for stream in self._active_effect_streams.values():
            held = max(0.0, now - stream.started_at)
            stream.key_top = float(self._top_margin())
            next_height = min(float(max_height), self._sp(18) + (held * speed))
            if abs(next_height - stream.height) > 0.01:
                stream.height = next_height
                changed = True

        kept_released: list[_EffectStream] = []
        for stream in self._released_effect_streams:
            release_t = (now - (stream.released_at or now)) / max(0.001, stream.release_duration)
            if release_t >= 1.0:
                changed = True
            else:
                kept_released.append(stream)
                changed = True
        if len(kept_released) != len(self._released_effect_streams):
            self._released_effect_streams = kept_released
        before_sparks = len(self._effect_sparks)
        if before_sparks:
            self._effect_sparks = [
                spark for spark in self._effect_sparks
                if (now - spark.started_at) < spark.duration
            ]
            changed = changed or len(self._effect_sparks) != before_sparks
        return changed

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

        if self._piano_style == "effects":
            available_width = max(1.0, float(self.width()) - (left * 2.0))
            total_gaps = gap * max(0, self._white_note_count - 1)
            white_w = max(1.0, (available_width - total_gaps) / max(1, self._white_note_count))
            black_w = max(1.0, white_w * (self._black_width() / max(1, self._white_width())))

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

        for note, stream in self._active_effect_streams.items():
            rect = self._rect_by_note.get(note)
            if rect is None:
                continue
            width_inset = min(self._sp(5 if not is_black_key(note) else 3), rect.width() * 0.22)
            stream.x = rect.center().x()
            stream.key_top = rect.top()
            stream.width = max(self._sp(5), rect.width() - width_inset)

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
        painter.setRenderHint(QPainter.Antialiasing, self._piano_style in {"premium", "effects"})
        painter.setClipRegion(event.region())

        if not self._notes:
            painter.end()
            return

        if self._piano_style == "effects":
            self._paint_effects_layer(painter, clip_f)
            self._paint_premium(painter, clip_f)
        elif self._piano_style == "premium":
            self._paint_premium(painter, clip_f)
        else:
            self._paint_classic(painter, clip_f)
        painter.end()

    def _effect_color(self) -> QColor:
        color = QColor(self._theme.white_key_pressed)
        if not color.isValid():
            color = QColor(self._theme.accent)
        return color

    def _is_light_theme(self) -> bool:
        background = QColor(self._theme.app_bg)
        return background.isValid() and background.lightnessF() > 0.6

    def _paint_effects_layer(self, painter: QPainter, clip_f: QRectF) -> None:
        now = time.monotonic()
        base = self._effect_color()
        light_theme = self._is_light_theme()
        painter.save()
        painter.setPen(Qt.NoPen)
        key_top = float(self._top_margin())
        stage_rect = QRectF(0.0, 0.0, float(self.width()), key_top + self._sp(2))
        if light_theme:
            painter.fillRect(QRectF(self.rect()), QColor("#D9B4BA"))
        if stage_rect.intersects(clip_f):
            stage = QLinearGradient(stage_rect.topLeft(), stage_rect.bottomLeft())
            if light_theme:
                stage.setColorAt(0.00, QColor("#E5E7EB"))
                stage.setColorAt(0.36, QColor("#F5F1EE"))
                stage.setColorAt(0.74, QColor("#EADDDD"))
                stage.setColorAt(1.00, QColor("#D9B4BA"))
            else:
                stage.setColorAt(0.00, QColor(5, 7, 10, 32))
                stage.setColorAt(0.52, QColor(32, 12, 18, 18))
                stage.setColorAt(0.84, QColor(92, 14, 24, 32))
                stage.setColorAt(1.00, QColor(148, 22, 34, 56))
            painter.fillRect(stage_rect, stage)

            white_index = 0
            for item in self._white_rects:
                if light_theme:
                    alpha = 22 if white_index % 7 == 0 else 10
                else:
                    alpha = 16 if white_index % 7 == 0 else 7
                y_fade = QLinearGradient(QPointF(0.0, 0.0), QPointF(0.0, key_top))
                guide_color = QColor("#6E3542") if light_theme else QColor("#FFFFFF")
                y_fade.setColorAt(0.00, _with_alpha(guide_color, 0))
                y_fade.setColorAt(0.36, _with_alpha(guide_color, max(1, alpha // 3)))
                y_fade.setColorAt(1.00, _with_alpha(guide_color, alpha))
                painter.setPen(QPen(y_fade, 1))
                x = item.rect.left()
                painter.drawLine(QPointF(x, 0.0), QPointF(x, key_top))
                white_index += 1
            painter.setPen(Qt.NoPen)

            vignette_w = max(self._sp(120), int(self.width() * 0.09))
            edge_color = QColor("#9CA1AA") if light_theme else QColor(self._theme.app_bg)
            edge_alpha = 118 if light_theme else 230
            edge_mid_alpha = 20 if light_theme else 32
            left_vignette = QLinearGradient(QPointF(0.0, 0.0), QPointF(float(vignette_w), 0.0))
            left_vignette.setColorAt(0.00, _with_alpha(edge_color, edge_alpha))
            left_vignette.setColorAt(0.72, _with_alpha(edge_color, edge_mid_alpha))
            left_vignette.setColorAt(1.00, _with_alpha(edge_color, 0))
            painter.fillRect(QRectF(0.0, 0.0, float(vignette_w), key_top), left_vignette)
            right_vignette = QLinearGradient(QPointF(float(self.width() - vignette_w), 0.0), QPointF(float(self.width()), 0.0))
            right_vignette.setColorAt(0.00, _with_alpha(edge_color, 0))
            right_vignette.setColorAt(0.28, _with_alpha(edge_color, edge_mid_alpha))
            right_vignette.setColorAt(1.00, _with_alpha(edge_color, edge_alpha))
            painter.fillRect(QRectF(float(self.width() - vignette_w), 0.0, float(vignette_w), key_top), right_vignette)

            top_vignette = QLinearGradient(QPointF(0.0, 0.0), QPointF(0.0, key_top))
            top_vignette.setColorAt(0.00, _with_alpha(edge_color, 78 if light_theme else 210))
            top_vignette.setColorAt(0.18, _with_alpha(edge_color, 18 if light_theme else 42))
            top_vignette.setColorAt(1.00, _with_alpha(edge_color, 0))
            painter.fillRect(stage_rect, top_vignette)

            glow_rect = QRectF(
                self._side_margin(),
                key_top - self._sp(86),
                max(1.0, self.width() - (self._side_margin() * 2)),
                self._sp(92),
            )
            glow = QLinearGradient(glow_rect.topLeft(), glow_rect.bottomLeft())
            glow.setColorAt(0.00, _with_alpha(base, 0))
            glow.setColorAt(0.72, _with_alpha(base, 24 if light_theme else 34))
            glow.setColorAt(1.00, _with_alpha(base.lighter(128), 62 if light_theme else 78))
            painter.fillRect(glow_rect, glow)
            fade_width = max(self._sp(44), int(self.width() * 0.035))
            left_fade = QLinearGradient(QPointF(0.0, 0.0), QPointF(float(fade_width), 0.0))
            left_fade.setColorAt(0.0, _with_alpha(edge_color, 138 if light_theme else 245))
            left_fade.setColorAt(1.0, _with_alpha(edge_color, 0))
            painter.fillRect(QRectF(0.0, 0.0, float(fade_width), key_top + self._sp(3)), left_fade)
            right_fade = QLinearGradient(QPointF(float(self.width() - fade_width), 0.0), QPointF(float(self.width()), 0.0))
            right_fade.setColorAt(0.0, _with_alpha(edge_color, 0))
            right_fade.setColorAt(1.0, _with_alpha(edge_color, 138 if light_theme else 245))
            painter.fillRect(QRectF(float(self.width() - fade_width), 0.0, float(fade_width), key_top + self._sp(3)), right_fade)

            line_rect = QRectF(
                float(self._side_margin()),
                key_top - max(1, self._sp(1)),
                max(1.0, self.width() - (self._side_margin() * 2)),
                max(1.0, self._sp(2)),
            )
            line_gradient = QLinearGradient(line_rect.topLeft(), line_rect.topRight())
            line_gradient.setColorAt(0.00, _with_alpha(base.lighter(135), 0))
            line_gradient.setColorAt(0.05, _with_alpha(base.lighter(135), 52))
            line_gradient.setColorAt(0.18, _with_alpha(base.lighter(135), 116))
            line_gradient.setColorAt(0.82, _with_alpha(base.lighter(135), 116))
            line_gradient.setColorAt(0.95, _with_alpha(base.lighter(135), 52))
            line_gradient.setColorAt(1.00, _with_alpha(base.lighter(135), 0))
            painter.fillRect(line_rect, line_gradient)
            painter.setPen(Qt.NoPen)

        for stream in [*self._released_effect_streams, *self._active_effect_streams.values()]:
            release_t = 0.0
            if stream.released_at is not None:
                release_t = max(0.0, min(1.0, (now - stream.released_at) / max(0.001, stream.release_duration)))
            alpha_scale = 1.0 if release_t < 0.82 else max(0.0, 1.0 - ((release_t - 0.82) / 0.18))
            lift = stream.release_distance * release_t
            height = stream.release_height if stream.released_at is not None else stream.height
            rect = QRectF(
                stream.x - (stream.width / 2.0),
                stream.key_top - height - lift,
                stream.width,
                height,
            )
            if not rect.intersects(clip_f):
                continue
            shadow_rect = rect.adjusted(-self._sp(5), -self._sp(5), self._sp(5), self._sp(5))
            shadow = QLinearGradient(shadow_rect.topLeft(), shadow_rect.bottomLeft())
            shadow.setColorAt(0.00, _with_alpha(base, int(22 * alpha_scale)))
            shadow.setColorAt(0.50, _with_alpha(base, int(78 * alpha_scale)))
            shadow.setColorAt(1.00, _with_alpha(base, int(24 * alpha_scale)))
            painter.fillPath(self._rounded_path(shadow_rect, float(self._sp(7))), shadow)

            gradient = QLinearGradient(rect.bottomLeft(), rect.topLeft())
            gradient.setColorAt(0.00, _with_alpha(base.darker(145), int(122 * alpha_scale)))
            gradient.setColorAt(0.17, _with_alpha(base.darker(108), int(214 * alpha_scale)))
            gradient.setColorAt(0.50, _with_alpha(base.lighter(132), int(246 * alpha_scale)))
            gradient.setColorAt(0.82, _with_alpha(base, int(214 * alpha_scale)))
            gradient.setColorAt(1.00, _with_alpha(base.darker(142), int(128 * alpha_scale)))
            painter.fillPath(self._rounded_path(rect, float(self._sp(4))), gradient)
            painter.setPen(QPen(_with_alpha(base.lighter(160), int(96 * alpha_scale)), max(1, self._sp(1))))
            painter.drawRoundedRect(rect.adjusted(0.5, 0.5, -0.5, -0.5), self._sp(4), self._sp(4))
            painter.setPen(Qt.NoPen)

        for spark in self._effect_sparks:
            t = max(0.0, min(1.0, (now - spark.started_at) / max(0.001, spark.duration)))
            ease = 1.0 - ((1.0 - t) * (1.0 - t))
            alpha = int(190 * (1.0 - t))
            if alpha <= 0:
                continue
            x = spark.x + (spark.dx * ease)
            y = spark.y + (spark.dy * ease)
            size = max(1.0, spark.size * (1.0 - (t * 0.55)))
            rect = QRectF(x - (size / 2.0), y - (size / 2.0), size, size)
            if not rect.intersects(clip_f):
                continue
            painter.setBrush(_with_alpha(base.lighter(150), alpha))
            painter.drawEllipse(rect)

        painter.restore()

    def _paint_classic(self, painter: QPainter, clip_f: QRectF) -> None:
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

    def _rounded_path(self, rect: QRectF, radius: float) -> QPainterPath:
        path = QPainterPath()
        path.addRoundedRect(rect, radius, radius)
        return path

    def _pressed_amount(self, note: int) -> float:
        return self._anim_t.get(note, 1.0 if note in self._pressed_notes else 0.0)

    def _premium_key_gradient(self, rect: QRectF, note: int, *, black: bool) -> QLinearGradient:
        base = QColor(self._theme.black_key if black else self._theme.white_key)
        pressed = QColor(self._theme.black_key_pressed if black else self._theme.white_key_pressed)
        t = self._pressed_amount(note)
        mixed = _lerp_color(base, pressed, t)
        gradient = QLinearGradient(rect.topLeft(), rect.bottomLeft())
        if black:
            gradient.setColorAt(0.00, mixed.lighter(145))
            gradient.setColorAt(0.12, mixed.lighter(112))
            gradient.setColorAt(0.58, mixed)
            gradient.setColorAt(1.00, mixed.darker(155))
        else:
            warm_top = _lerp_color(base, QColor("#FAF7EF"), 0.58)
            warm_upper = _lerp_color(base, QColor("#F0EDE5"), 0.42)
            warm_lower = _lerp_color(base, QColor("#DEDAD1"), 0.22)
            warm_bottom = _lerp_color(base, QColor("#C8C4B9"), 0.32)
            pressed_top = pressed.lighter(138)
            pressed_upper = pressed.lighter(108)
            pressed_lower = pressed
            pressed_bottom = pressed.darker(142)
            gradient.setColorAt(0.00, _lerp_color(warm_top, pressed_top, t))
            gradient.setColorAt(0.18, _lerp_color(warm_upper, pressed_upper, t))
            gradient.setColorAt(0.66, _lerp_color(warm_lower, pressed_lower, t))
            gradient.setColorAt(1.00, _lerp_color(warm_bottom, pressed_bottom, t))
        return gradient

    def _draw_premium_backlight(self, painter: QPainter, rect: QRectF, note: int, *, black: bool) -> None:
        t = self._pressed_amount(note)
        if t <= 0.001:
            return
        accent = QColor(self._theme.black_key_pressed if black else self._theme.white_key_pressed)
        glow_rect = rect.adjusted(self._sp(2), rect.height() * (0.44 if black else 0.52), -self._sp(2), -self._sp(3))
        glow = QLinearGradient(glow_rect.topLeft(), glow_rect.bottomLeft())
        top_alpha = 18 if black else 32
        mid_alpha = 72 if black else 108
        bottom_alpha = 126 if black else 168
        glow.setColorAt(0.00, _with_alpha(accent.lighter(135), int(top_alpha * t)))
        glow.setColorAt(0.48, _with_alpha(accent.lighter(116), int(mid_alpha * t)))
        glow.setColorAt(1.00, _with_alpha(accent, int(bottom_alpha * t)))
        radius = float(self._sp(4 if black else 5))
        painter.fillPath(self._rounded_path(glow_rect, radius), glow)

        halo = QColor(self._theme.accent_hover)
        halo.setAlpha(int((64 if black else 42) * t))
        painter.setPen(QPen(halo, max(1, self._sp(1))))
        painter.drawRoundedRect(rect.adjusted(1.0, 1.0, -1.0, -1.0), radius, radius)

    def _paint_premium(self, painter: QPainter, clip_f: QRectF) -> None:
        draw_labels = self._show_key_labels or self._show_note_labels
        border = QColor(self._theme.border)
        white_highlight = QColor(255, 255, 255, 170)
        white_edge = _with_alpha(QColor("#9A9286"), 86)
        white_left_glint = QColor(255, 252, 244, 132)
        white_right_separator = _with_alpha(QColor("#8B8377"), 34)
        white_bottom_tone = QColor("#948C7D")

        for item in self._white_rects:
            rect = item.rect
            if not rect.intersects(clip_f):
                continue
            radius = float(self._sp(4))
            body = rect.adjusted(0.5, 0.5, -0.5, -0.5)
            path = self._rounded_path(body, radius)
            painter.fillPath(path, self._premium_key_gradient(body, item.note, black=False))
            self._draw_premium_backlight(painter, body, item.note, black=False)
            pressed_amount = self._pressed_amount(item.note)
            lower_tone_rect = body.adjusted(1.0, body.height() * 0.54, -1.0, -1.0)
            lower_tone = QLinearGradient(lower_tone_rect.topLeft(), lower_tone_rect.bottomLeft())
            lower_alpha = int(24 * (1.0 - min(0.68, pressed_amount * 0.55)))
            lower_tone.setColorAt(0.00, _with_alpha(white_bottom_tone, 0))
            lower_tone.setColorAt(0.46, _with_alpha(white_bottom_tone, int(lower_alpha * 0.34)))
            lower_tone.setColorAt(1.00, _with_alpha(white_bottom_tone, lower_alpha))
            painter.fillPath(self._rounded_path(lower_tone_rect, max(1.0, radius - 1.0)), lower_tone)
            painter.setPen(QPen(white_edge, 1))
            painter.drawPath(path)
            painter.setPen(QPen(white_highlight, 1))
            painter.drawLine(
                QPointF(body.left() + self._sp(2), body.top() + self._sp(2)),
                QPointF(body.right() - self._sp(2), body.top() + self._sp(2)),
            )
            painter.setPen(QPen(white_left_glint, 1))
            painter.drawLine(
                QPointF(body.left() + 1.0, body.top() + self._sp(4)),
                QPointF(body.left() + 1.0, body.bottom() - self._sp(6)),
            )
            painter.setPen(QPen(white_right_separator, 1))
            painter.drawLine(
                QPointF(body.right() - 1.0, body.top() + self._sp(5)),
                QPointF(body.right() - 1.0, body.bottom() - self._sp(5)),
            )
            if draw_labels:
                self._draw_labels(painter, item.note, rect, black=False)

        shadow = QColor(0, 0, 0, 88)
        top_highlight = QColor(255, 255, 255, 82)
        side_highlight = QColor(255, 255, 255, 28)
        black_outline = QColor("#050506")
        for item in self._black_rects:
            rect = item.rect
            if not rect.adjusted(-2.0, -2.0, 2.0, self._sp(5)).intersects(clip_f):
                continue
            radius = float(self._sp(3))
            shadow_rect = rect.adjusted(self._sp(1), self._sp(2), self._sp(1), self._sp(4))
            painter.fillPath(self._rounded_path(shadow_rect, radius), _with_alpha(shadow, 58))
            body = rect.adjusted(0.5, 0.5, -0.5, -0.5)
            path = self._rounded_path(body, radius)
            painter.fillPath(path, self._premium_key_gradient(body, item.note, black=True))
            self._draw_premium_backlight(painter, body, item.note, black=True)
            painter.setPen(QPen(black_outline, 1))
            painter.drawPath(path)
            painter.setPen(QPen(top_highlight, 1))
            painter.drawLine(
                QPointF(body.left() + self._sp(2), body.top() + self._sp(2)),
                QPointF(body.right() - self._sp(2), body.top() + self._sp(2)),
            )
            painter.setPen(QPen(side_highlight, 1))
            painter.drawLine(
                QPointF(body.left() + 1.0, body.top() + self._sp(4)),
                QPointF(body.left() + 1.0, body.bottom() - self._sp(5)),
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
            painter.setPen(QPen(QColor(self._theme.border).darker(118), 1))
            painter.drawRoundedRect(outer.adjusted(0.5, 0.5, -0.5, -0.5), self._sp(4), self._sp(4))

        selected = self._selected_keybind_note
        selected_rect = self._rect_by_note.get(selected) if selected is not None else None
        if self._keybind_edit_mode and selected_rect is not None and selected_rect.intersects(clip_f):
            accent = QColor(self._theme.accent)
            accent.setAlpha(72)
            painter.fillPath(self._rounded_path(selected_rect.adjusted(1.0, 1.0, -1.0, -1.0), self._sp(4)), accent)
            painter.setPen(QPen(QColor(self._theme.accent_hover), 2))
            painter.drawRoundedRect(selected_rect.adjusted(1.0, 1.0, -1.0, -1.0), self._sp(4), self._sp(4))

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

        painter.setPen(_readable_text_color(self._note_fill_color(note)))

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
            line_step = max(self._sp(7), lh - gap)
            total_height = lh + (line_step * (len(lines) - 1))
            start_y = bottom - total_height
            painter.setFont(draw_font)
            for idx, line in enumerate(lines):
                y = start_y + (idx * line_step)
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
                draw_multiline_bottom(
                    hotkey_bottom,
                    hotkey_text,
                    key_font_size,
                    self._sp(10),
                    self._sp(3),
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
        hotkey_bottom = rect.bottom() - self._sp(28) - mode_gap
        note_bottom = rect.bottom() - self._sp(9)
        if hotkey_text and note_text:
            draw_multiline_bottom(
                hotkey_bottom,
                hotkey_text,
                hotkey_font_size,
                self._sp(12),
                self._sp(4),
            )
            painter.setFont(QFont("Segoe UI", note_font_size, QFont.Weight.Bold))
            painter.drawText(
                QRectF(rect.left(), note_bottom - self._sp(18), rect.width(), self._sp(18)),
                Qt.AlignHCenter | Qt.AlignBottom,
                note_text,
            )
        else:
            text = hotkey_text or note_text
            if hotkey_text:
                draw_multiline_bottom(
                    rect.bottom() - self._sp(12),
                    hotkey_text,
                    hotkey_font_size,
                    self._sp(12),
                    self._sp(4),
                )
            else:
                painter.setFont(QFont("Segoe UI", note_font_size, QFont.Weight.Bold))
                painter.drawText(
                    QRectF(rect.left(), note_bottom - self._sp(18), rect.width(), self._sp(18)),
                    Qt.AlignHCenter | Qt.AlignBottom,
                    note_text,
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
            self._mouse_pressed = False
            self._last_drag_note = None
            self.dragNoteChanged.emit(None)
        super().leaveEvent(event)
