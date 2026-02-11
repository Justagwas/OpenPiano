from __future__ import annotations

import json
import re
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from collections import deque
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEvent, QObject, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeyEvent
from PySide6.QtWidgets import QApplication, QFileDialog

from openpiano.core.audio_engine import AudioEngineProtocol, FluidSynthAudioEngine, SilentAudioEngine
from openpiano.core.config import (
    ANIMATION_PROFILE,
    APP_NAME,
    APP_VERSION,
    NOTE_VELOCITY_MAX,
    NOTE_VELOCITY_MIN,
    KPS_WINDOW_SECONDS,
    OFFICIAL_WEBSITE_URL,
    STATS_ORDER,
    STATS_TICK_MS,
    SUSTAIN_TICK_MS,
    TRANSPOSE_MAX,
    TRANSPOSE_MIN,
    UI_SCALE_MAX,
    UI_SCALE_MIN,
    UI_SCALE_STEP,
    UPDATE_CHECK_MANIFEST_URL,
    UPDATE_GITHUB_DOWNLOAD_URL,
    UPDATE_GITHUB_LATEST_URL,
    UPDATE_SOURCEFORGE_RSS_URL,
)
from openpiano.core.instrument_registry import (
    InstrumentInfo,
    discover_instruments,
    ensure_portable_fonts_dir,
    select_fallback_instrument,
)
from openpiano.core.keymap import (
    Binding,
    MODE_RANGES,
    PianoMode,
    get_binding_to_midi,
    get_mode_mapping,
    get_note_labels,
    normalize_key_event,
)
from openpiano.core.music_logic import clamp_transposed_note, sustain_hold_ms
from openpiano.core.midi_input import MidiInputManager
from openpiano.core.midi_recording import MidiRecorder
from openpiano.core.settings_store import AppSettings, load_settings, save_settings
from openpiano.core.stats_logic import collect_stats_values, trim_kps_events
from openpiano.core.theme import apply_key_color_overrides, get_theme
from openpiano.ui.main_window import MainWindow


AudioFactory = Callable[[], AudioEngineProtocol]
InstrumentProvider = Callable[[], list[InstrumentInfo]]
MidiManagerFactory = Callable[[Callable[[int, int], None], Callable[[int], None]], MidiInputManager]
RecorderFactory = Callable[[], MidiRecorder]
TutorialStep = dict[str, str | bool]
HQ_SOUNDFONT_URL = "https://downloads.justagwas.com/openpiano/GRAND%20PIANO.sf2"
HQ_SOUNDFONT_FILENAME = "GRAND PIANO.sf2"


def _parse_semver(value: str) -> tuple[int, int, int] | None:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", value or "")
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _round_scale(value: float) -> float:
    clamped = max(UI_SCALE_MIN, min(UI_SCALE_MAX, float(value)))
    steps = round((clamped - UI_SCALE_MIN) / UI_SCALE_STEP)
    rounded = UI_SCALE_MIN + (steps * UI_SCALE_STEP)
    return round(max(UI_SCALE_MIN, min(UI_SCALE_MAX, rounded)), 2)


class PianoAppController(QObject):
    _updateResultReady = Signal(bool, object)
    _midiNoteOnReady = Signal(int, int)
    _midiNoteOffReady = Signal(int)

    def __init__(
        self,
        app: QApplication,
        audio_factory: AudioFactory | None = None,
        instrument_provider: InstrumentProvider | None = None,
        midi_manager_factory: MidiManagerFactory | None = None,
        recorder_factory: RecorderFactory | None = None,
        settings_path: Path | None = None,
        icon_path: Path | None = None,
    ) -> None:
        super().__init__()
        self._app = app
        self._audio_factory = audio_factory or FluidSynthAudioEngine
        self._instrument_provider = instrument_provider or discover_instruments
        self._midi_manager_factory = midi_manager_factory or MidiInputManager
        self._recorder_factory = recorder_factory or MidiRecorder
        self._settings_path = settings_path
        self._is_shutdown = False

        settings = load_settings(self._settings_path)
        self._mode: PianoMode = settings.mode
        self._volume = float(settings.volume)
        self._velocity = max(NOTE_VELOCITY_MIN, min(NOTE_VELOCITY_MAX, int(settings.velocity)))
        self._instrument_id = settings.instrument_id
        self._instrument_bank = int(settings.instrument_bank)
        self._instrument_preset = int(settings.instrument_preset)
        self._show_stats = bool(settings.show_stats)
        self._controls_open = bool(settings.controls_open)
        self._settings_open = False
        self._transpose = int(settings.transpose)
        self._sustain_percent = int(settings.sustain_percent)
        self._hold_space_for_sustain = bool(settings.hold_space_for_sustain)
        self._show_key_labels = bool(settings.show_key_labels)
        self._show_note_labels = bool(settings.show_note_labels)
        self._theme_mode = settings.theme_mode
        self._ui_scale = _round_scale(settings.ui_scale)
        self._animation_speed = (
            settings.animation_speed if settings.animation_speed in ANIMATION_PROFILE else "instant"
        )
        self._auto_check_updates = bool(settings.auto_check_updates)
        self._midi_input_device = str(settings.midi_input_device).strip()
        self._white_key_color = settings.white_key_color
        self._white_key_pressed_color = settings.white_key_pressed_color
        self._black_key_color = settings.black_key_color
        self._black_key_pressed_color = settings.black_key_pressed_color
        self._hq_soundfont_prompt_seen = bool(settings.hq_soundfont_prompt_seen)
        self._space_override_off = False

        self._mapping: dict[int, Binding] = {}
        self._binding_to_midi: dict[Binding, int] = {}
        self._note_labels: dict[int, str] = {}
        self._keys: list[int] = []
        self._mode_min = 36
        self._mode_max = 96

        self._active_bindings: set[Binding] = set()
        self._keycode_to_binding: dict[int, Binding] = {}
        self._binding_to_keycodes: dict[Binding, set[int]] = {}
        self._note_sources: dict[int, set[str]] = {}
        self._source_to_sounding_note: dict[str, int] = {}
        self._sustained_notes: dict[int, float | None] = {}
        self._current_mouse_base_note: int | None = None
        self._kps_events: deque[float] = deque()
        self._stats_dirty = False

        self._instruments: list[InstrumentInfo] = []
        self._instrument_by_id: dict[str, InstrumentInfo] = {}
        self._available_programs: dict[int, list[int]] = {}
        self._tutorial_active = False
        self._tutorial_steps: list[TutorialStep] = []
        self._tutorial_index = 0
        self._tutorial_prev_settings_open = False
        self._tutorial_prev_controls_open = False
        self._tutorial_prev_mode: PianoMode = self._mode

        self.audio_engine: AudioEngineProtocol = SilentAudioEngine()
        self.audio_available = False

        self._update_lock = threading.Lock()
        self._update_check_active = False
        self._updateResultReady.connect(self._finish_update_check)
        self._midiNoteOnReady.connect(self._on_midi_note_on)
        self._midiNoteOffReady.connect(self._on_midi_note_off)

        self._midi_manager = self._midi_manager_factory(self._queue_midi_note_on, self._queue_midi_note_off)
        self._midi_backend_issue_shown = False
        self._recorder = self._recorder_factory()
        self._recording_started_at = 0.0
        self._recording_elapsed_seconds = 0

        base_theme = get_theme(self._theme_mode)
        effective_theme = apply_key_color_overrides(
            base_theme,
            white=self._white_key_color,
            white_pressed=self._white_key_pressed_color,
            black=self._black_key_color,
            black_pressed=self._black_key_pressed_color,
        )
        resolved_icon = icon_path if icon_path is not None else self._default_icon_path()
        self.window = MainWindow(theme=effective_theme, icon_path=resolved_icon)

        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(250)
        self._save_timer.timeout.connect(self._persist_settings_now)

        self._stats_timer = QTimer(self)
        self._stats_timer.setInterval(STATS_TICK_MS)
        self._stats_timer.timeout.connect(self._on_stats_tick)
        self._stats_refresh_timer = QTimer(self)
        self._stats_refresh_timer.setSingleShot(True)
        self._stats_refresh_timer.setInterval(16)
        self._stats_refresh_timer.timeout.connect(self._flush_pending_stats)

        self._sustain_timer = QTimer(self)
        self._sustain_timer.setInterval(SUSTAIN_TICK_MS)
        self._sustain_timer.timeout.connect(self._on_sustain_tick)

        self._connect_signals()
        self._apply_mode(self._mode, persist=False)
        self.window.set_volume(self._volume)
        self.window.set_velocity(self._velocity)
        self.window.set_transpose(self._transpose)
        self.window.set_sustain_percent(self._sustain_percent)
        self.window.set_hold_space_sustain_mode(self._hold_space_for_sustain)
        self.window.set_label_visibility(self._show_key_labels, self._show_note_labels)
        self.window.set_theme_mode(self._theme_mode)
        self.window.set_ui_scale(self._ui_scale)
        self.window.set_animation_speed(self._animation_speed)
        self.window.set_auto_check_updates(self._auto_check_updates)
        self.window.set_stats_visible(self._show_stats)
        self.window.set_settings_visible(False)
        self.window.set_controls_visible(self._controls_open)
        self.window.set_recording_state(active=False, has_take=False)
        self._set_recording_elapsed_display(0)
        self.window.set_key_color("white_key", self._white_key_color)
        self.window.set_key_color("white_key_pressed", self._white_key_pressed_color)
        self.window.set_key_color("black_key", self._black_key_color)
        self.window.set_key_color("black_key_pressed", self._black_key_pressed_color)

        self.window.piano_widget.set_label_visibility(self._show_key_labels, self._show_note_labels)
        self.window.piano_widget.set_animation_speed(self._animation_speed)
        self.window.piano_widget.set_ui_scale(self._ui_scale)
        self.window.piano_widget.set_key_colors(
            self._white_key_color,
            self._white_key_pressed_color,
            self._black_key_color,
            self._black_key_pressed_color,
        )

        self._init_audio_engine()
        self._refresh_instruments()
        self._apply_startup_instrument()
        self._refresh_midi_inputs()
        self._restore_midi_input_device(persist=False, show_warning=False)

        self._app.installEventFilter(self)
        self.window.piano_widget.installEventFilter(self)
        self._app.aboutToQuit.connect(self.shutdown)
        self._stats_timer.start()
        self._sustain_timer.start()
        self._refresh_stats_ui()

        if self._auto_check_updates:
            QTimer.singleShot(1200, lambda: self._trigger_update_check(manual=False))

    @staticmethod
    def _default_icon_path() -> Path:
        root = Path(__file__).resolve().parents[1]
        return root / "icon.ico"

    def _connect_signals(self) -> None:
        self.window.modeChanged.connect(self._on_mode_changed)
        self.window.instrumentChanged.connect(self._on_instrument_changed)
        self.window.bankChanged.connect(self._on_bank_changed)
        self.window.presetChanged.connect(self._on_preset_changed)
        self.window.volumeChanged.connect(self._on_volume_changed)
        self.window.velocityChanged.connect(self._on_velocity_changed)
        self.window.transposeChanged.connect(self._on_transpose_changed)
        self.window.sustainPercentChanged.connect(self._on_sustain_percent_changed)
        self.window.holdSpaceSustainChanged.connect(self._on_hold_space_sustain_changed)
        self.window.showKeyLabelsChanged.connect(self._on_show_key_labels_changed)
        self.window.showNoteLabelsChanged.connect(self._on_show_note_labels_changed)
        self.window.themeModeChanged.connect(self._on_theme_mode_changed)
        self.window.uiScaleChanged.connect(self._on_ui_scale_changed)
        self.window.animationSpeedChanged.connect(self._on_animation_speed_changed)
        self.window.keyColorChanged.connect(self._on_key_color_changed)
        self.window.autoCheckUpdatesChanged.connect(self._on_auto_check_updates_changed)
        self.window.checkUpdatesNowRequested.connect(lambda: self._trigger_update_check(manual=True))
        self.window.settingsToggled.connect(self._on_settings_toggled)
        self.window.controlsToggled.connect(self._on_controls_toggled)
        self.window.statsToggled.connect(self._on_stats_toggled)
        self.window.midiInputDeviceChanged.connect(self._on_midi_input_device_changed)
        self.window.midiInputDropdownOpened.connect(self._on_midi_input_dropdown_opened)
        self.window.recordingToggled.connect(self._on_recording_toggled)
        self.window.saveRecordingRequested.connect(self._on_save_recording_requested)
        self.window.allNotesOffRequested.connect(self._on_all_notes_off_requested)
        self.window.tutorialRequested.connect(self._on_tutorial_requested)
        self.window.tutorialNextRequested.connect(self._advance_tutorial)
        self.window.tutorialBackRequested.connect(self._rewind_tutorial)
        self.window.tutorialSkipRequested.connect(lambda: self._end_tutorial(completed=False))
        self.window.tutorialFinishRequested.connect(lambda: self._end_tutorial(completed=True))
        self.window.websiteRequested.connect(self._on_website_requested)
        self.window.resetDefaultsRequested.connect(self._on_reset_defaults_requested)

        self.window.piano_widget.notePressed.connect(self._on_mouse_note_pressed)
        self.window.piano_widget.noteReleased.connect(self._on_mouse_note_released)
        self.window.piano_widget.dragNoteChanged.connect(self._on_mouse_drag_note_changed)

    def _init_audio_engine(self) -> None:
        try:
            self.audio_engine = self._audio_factory()
            self.audio_available = not isinstance(self.audio_engine, SilentAudioEngine)
            self.audio_engine.set_master_volume(self._volume)
        except Exception as exc:
            self.audio_engine = SilentAudioEngine()
            self.audio_available = False
            _ = exc

    def _refresh_midi_inputs(self) -> None:
        self._maybe_warn_midi_backend_issue()
        devices = self._midi_manager.list_input_devices()
        selected = self._midi_input_device if self._midi_input_device in devices else ""
        self.window.set_midi_input_devices(devices, selected)

    def _on_midi_input_dropdown_opened(self) -> None:
        self._refresh_midi_inputs()
        desired = str(self._midi_input_device).strip()
        if not desired:
            return
        current_getter = getattr(self._midi_manager, "current_device", None)
        current = str(current_getter() if callable(current_getter) else "").strip()
        if current == desired:
            return
        try:
            self._apply_midi_input_device(desired, persist=False)
        except Exception:
            return

    def _restore_midi_input_device(self, persist: bool, show_warning: bool) -> None:
        requested = str(self._midi_input_device).strip()
        try:
            self._apply_midi_input_device(requested, persist=persist)
            return
        except Exception as exc:
            self._midi_input_device = requested
            self._refresh_midi_inputs()
            if persist:
                self._schedule_persist()
            if not show_warning:
                return
            self.window.show_warning(
                "MIDI Input",
                f"Could not open MIDI input device:\n{exc}",
            )

    def _maybe_warn_midi_backend_issue(self) -> None:
        if self._midi_backend_issue_shown:
            return
        getter = getattr(self._midi_manager, "backend_error", None)
        if not callable(getter):
            return
        detail = str(getter() or "").strip()
        if not detail:
            return
        self._midi_backend_issue_shown = True
        self.window.show_warning(
            "MIDI Input",
            "MIDI input backend is unavailable.\n\n"
            f"{detail}\n\n"
            "Install MIDI dependencies and restart OpenPiano.",
        )

    def _apply_midi_input_device(self, device: str, persist: bool) -> None:
        chosen = str(device).strip()
        available = self._midi_manager.list_input_devices()
        if chosen and chosen not in available:
            chosen = ""
        if chosen:
            self._midi_manager.open_device(chosen)
        else:
            self._midi_manager.close()
        self._midi_input_device = chosen
        self.window.set_midi_input_devices(available, self._midi_input_device)
        if persist:
            self._schedule_persist()

    def _queue_midi_note_on(self, note: int, velocity: int) -> None:
        self._midiNoteOnReady.emit(int(note), int(velocity))

    def _queue_midi_note_off(self, note: int) -> None:
        self._midiNoteOffReady.emit(int(note))

    def _on_midi_note_on(self, note: int, velocity: int) -> None:
        if self._tutorial_active:
            return
        source = f"midi:{int(note)}"
        self._activate_external_source(int(note), source, int(velocity))

    def _on_midi_note_off(self, note: int) -> None:
        if self._tutorial_active:
            return
        source = f"midi:{int(note)}"
        self._release_external_source(source)

    def _refresh_instruments(self) -> None:
        try:
            self._instruments = list(self._instrument_provider())
        except Exception as exc:
            self._instruments = []
            _ = exc
        self._instrument_by_id = {item.id: item for item in self._instruments}
        self.window.set_instruments(self._instruments, self._instrument_id)

    def _apply_startup_instrument(self) -> None:
        if not self._instruments:
            self._instrument_id = ""
            self._available_programs = {}
            self.window.set_bank_preset_options([], [], 0, 0)
            return

        if self._instrument_id and self._instrument_id in self._instrument_by_id:
            if self._apply_instrument_selection(
                self._instrument_id,
                self._instrument_bank,
                self._instrument_preset,
                persist=False,
            ):
                return

        fallback = select_fallback_instrument(self._instruments)
        if fallback is None:
            self._instrument_id = ""
            self._available_programs = {}
            self.window.set_bank_preset_options([], [], 0, 0)
            return
        self._apply_instrument_selection(
            fallback.id,
            fallback.default_bank,
            fallback.default_preset,
            persist=False,
        )

    @staticmethod
    def _nearest_value(candidates: list[int], requested: int) -> int:
        if not candidates:
            return requested
        return min(candidates, key=lambda value: abs(value - requested))

    def _normalize_program_selection(
        self,
        programs: dict[int, list[int]],
        requested_bank: int,
        requested_preset: int,
    ) -> tuple[int, int]:
        if not programs:
            return max(0, int(requested_bank)), max(0, min(127, int(requested_preset)))
        banks = sorted(programs.keys())
        selected_bank = (
            int(requested_bank)
            if int(requested_bank) in programs
            else self._nearest_value(banks, int(requested_bank))
        )
        presets = sorted(set(programs.get(selected_bank, [])))
        if not presets:
            return selected_bank, max(0, min(127, int(requested_preset)))
        selected_preset = (
            int(requested_preset)
            if int(requested_preset) in presets
            else self._nearest_value(presets, int(requested_preset))
        )
        return selected_bank, selected_preset

    def _refresh_program_controls(self) -> None:
        banks = sorted(self._available_programs.keys())
        selected_bank = self._instrument_bank
        selected_preset = self._instrument_preset
        if not banks:
            self.window.set_bank_preset_options([], [], selected_bank, selected_preset)
            return
        if selected_bank not in self._available_programs:
            selected_bank = banks[0]
        presets = sorted(set(self._available_programs.get(selected_bank, [])))
        if presets and selected_preset not in presets:
            selected_preset = presets[0]
        self._instrument_bank = selected_bank
        self._instrument_preset = selected_preset
        self.window.set_bank_preset_options(banks, presets, selected_bank, selected_preset)

    def _apply_instrument_selection(
        self,
        instrument_id: str,
        bank: int,
        preset: int,
        persist: bool,
    ) -> bool:
        instrument = self._instrument_by_id.get(instrument_id)
        if instrument is None:
            return False
        try:
            self.audio_engine.set_instrument(str(instrument.path), bank=bank, preset=preset)
            programs = self.audio_engine.get_available_programs()
            current_bank, current_preset = self.audio_engine.get_current_program()
        except Exception as exc:
            self.window.show_warning(
                "Instrument Error",
                f"Failed to load instrument:\n{exc}",
            )
            return False

        normalized_bank, normalized_preset = self._normalize_program_selection(
            programs,
            current_bank,
            current_preset,
        )
        self._instrument_id = instrument.id
        self._instrument_bank = normalized_bank
        self._instrument_preset = normalized_preset
        self._available_programs = {
            int(b): sorted(set(int(p) for p in presets))
            for b, presets in (programs or {}).items()
        }
        self.window.set_instruments(self._instruments, self._instrument_id)
        self._refresh_program_controls()
        if persist:
            self._schedule_persist()
        return True

    def _on_mode_changed(self, mode: str) -> None:
        new_mode: PianoMode = "88" if mode == "88" else "61"
        if new_mode == self._mode:
            return
        self._stop_all_notes()
        self._apply_mode(new_mode, persist=True)
        self._refresh_stats_ui()

    def _apply_mode(self, mode: PianoMode, persist: bool) -> None:
        self._mode = mode
        self._mapping = get_mode_mapping(mode)
        self._binding_to_midi = get_binding_to_midi(mode)
        self._note_labels = get_note_labels(mode)
        self._keys = sorted(self._mapping.keys())
        self._mode_min, self._mode_max = MODE_RANGES[mode]

        self.window.piano_widget.set_mode(mode, self._mapping, self._note_labels)
        self.window.piano_widget.set_label_visibility(self._show_key_labels, self._show_note_labels)
        self.window.piano_widget.set_ui_scale(self._ui_scale)
        self.window.set_mode(mode)
        self.window.set_window_key_count(len(self._keys))
        self.window.refresh_fixed_size()
        if persist:
            self._schedule_persist()

    def _on_instrument_changed(self, instrument_id: str) -> None:
        self._apply_instrument_selection(
            instrument_id,
            self._instrument_bank,
            self._instrument_preset,
            persist=True,
        )

    def _on_bank_changed(self, bank: int) -> None:
        bank_value = max(0, int(bank))
        if bank_value == self._instrument_bank:
            return
        self._instrument_bank = bank_value
        if not self._instrument_id:
            self._refresh_program_controls()
            self._schedule_persist()
            return
        self._apply_instrument_selection(
            self._instrument_id,
            self._instrument_bank,
            self._instrument_preset,
            persist=True,
        )

    def _on_preset_changed(self, preset: int) -> None:
        preset_value = max(0, min(127, int(preset)))
        if preset_value == self._instrument_preset:
            return
        self._instrument_preset = preset_value
        if not self._instrument_id:
            self._refresh_program_controls()
            self._schedule_persist()
            return
        self._apply_instrument_selection(
            self._instrument_id,
            self._instrument_bank,
            self._instrument_preset,
            persist=True,
        )

    def _on_volume_changed(self, volume: float) -> None:
        self._volume = max(0.0, min(1.0, float(volume)))
        self.audio_engine.set_master_volume(self._volume)
        self.window.set_volume(self._volume)
        self._refresh_stats_ui()
        self._schedule_persist()

    def _on_velocity_changed(self, value: int) -> None:
        clamped = max(NOTE_VELOCITY_MIN, min(NOTE_VELOCITY_MAX, int(value)))
        if clamped == self._velocity:
            return
        self._velocity = clamped
        self.window.set_velocity(self._velocity)
        self._schedule_persist()

    def _on_transpose_changed(self, value: int) -> None:
        clamped = max(TRANSPOSE_MIN, min(TRANSPOSE_MAX, int(value)))
        if clamped == self._transpose:
            return
        self._transpose = clamped
        self.window.set_transpose(self._transpose)
        self._refresh_stats_ui()
        self._schedule_persist()

    def _on_sustain_percent_changed(self, value: int) -> None:
        clamped = max(0, min(100, int(value)))
        if clamped == self._sustain_percent:
            return
        self._sustain_percent = clamped
        self.window.set_sustain_percent(self._sustain_percent)
        self._refresh_sustain_deadlines()
        self._refresh_stats_ui()
        self._schedule_persist()

    def _on_hold_space_sustain_changed(self, enabled: bool) -> None:
        mode = bool(enabled)
        if mode == self._hold_space_for_sustain:
            return
        self._hold_space_for_sustain = mode
        self.window.set_hold_space_sustain_mode(self._hold_space_for_sustain)
        self._refresh_sustain_deadlines()
        self._refresh_stats_ui()
        self._schedule_persist()

    def _on_show_key_labels_changed(self, enabled: bool) -> None:
        self._show_key_labels = bool(enabled)
        self.window.piano_widget.set_label_visibility(self._show_key_labels, self._show_note_labels)
        self._schedule_persist()

    def _on_show_note_labels_changed(self, enabled: bool) -> None:
        self._show_note_labels = bool(enabled)
        self.window.piano_widget.set_label_visibility(self._show_key_labels, self._show_note_labels)
        self._schedule_persist()

    def _on_theme_mode_changed(self, mode: str) -> None:
        theme_mode = "light" if mode == "light" else "dark"
        if theme_mode == self._theme_mode:
            return
        self._theme_mode = theme_mode
        self._apply_theme()
        self._schedule_persist()

    def _on_ui_scale_changed(self, scale: float) -> None:
        rounded = _round_scale(scale)
        if abs(rounded - self._ui_scale) < 0.001:
            return
        self._ui_scale = rounded
        self.window.piano_widget.set_ui_scale(self._ui_scale)
        self.window.set_ui_scale(self._ui_scale)
        self._schedule_persist()

    def _on_animation_speed_changed(self, speed: str) -> None:
        chosen = speed if speed in ANIMATION_PROFILE else "instant"
        if chosen == self._animation_speed:
            return
        self._animation_speed = chosen
        self.window.piano_widget.set_animation_speed(self._animation_speed)
        self.window.set_animation_speed(self._animation_speed)
        self._schedule_persist()

    def _on_key_color_changed(self, target: str, color: str) -> None:
        clean = str(color).strip().lower()
        if target == "white_key":
            self._white_key_color = clean
        elif target == "white_key_pressed":
            self._white_key_pressed_color = clean
        elif target == "black_key":
            self._black_key_color = clean
        elif target == "black_key_pressed":
            self._black_key_pressed_color = clean
        else:
            return
        self._apply_theme()
        self._schedule_persist()

    def _on_auto_check_updates_changed(self, enabled: bool) -> None:
        self._auto_check_updates = bool(enabled)
        self.window.set_auto_check_updates(self._auto_check_updates)
        self._schedule_persist()

    def _apply_theme(self) -> None:
        base = get_theme(self._theme_mode)
        effective = apply_key_color_overrides(
            base,
            white=self._white_key_color,
            white_pressed=self._white_key_pressed_color,
            black=self._black_key_color,
            black_pressed=self._black_key_pressed_color,
        )
        self.window.set_theme(effective)
        self.window.piano_widget.set_key_colors(
            self._white_key_color,
            self._white_key_pressed_color,
            self._black_key_color,
            self._black_key_pressed_color,
        )
        self.window.set_theme_mode(self._theme_mode)
        self._refresh_stats_ui()

    def _on_settings_toggled(self, visible: bool) -> None:
        if self._tutorial_active:
            return
        self._settings_open = bool(visible)
        self.window.set_settings_visible(self._settings_open)

    def _on_controls_toggled(self, visible: bool) -> None:
        if self._tutorial_active:
            return
        self._controls_open = bool(visible)
        self.window.set_controls_visible(self._controls_open)
        self._schedule_persist()

    def _on_stats_toggled(self, visible: bool) -> None:
        if self._tutorial_active:
            return
        self._show_stats = bool(visible)
        self.window.set_stats_visible(self._show_stats)
        if self._show_stats:
            self._refresh_stats_ui()
        self._schedule_persist()

    def _on_midi_input_device_changed(self, device: str) -> None:
        self._midi_input_device = str(device).strip()
        self._restore_midi_input_device(persist=True, show_warning=True)

    def _on_recording_toggled(self, active: bool) -> None:
        if bool(active):
            self._recorder.start()
            self._recording_started_at = time.monotonic()
            self._recording_elapsed_seconds = 0
            self.window.set_recording_state(active=True, has_take=False)
            self._set_recording_elapsed_display(0)
            return
        self._record_note_off_for_active_notes()
        self._recorder.stop()
        if self._recording_started_at > 0.0:
            elapsed = max(0, int(time.monotonic() - self._recording_started_at))
            self._recording_elapsed_seconds = elapsed
        self.window.set_recording_state(active=False, has_take=self._recorder.has_take())
        self._set_recording_elapsed_display(self._recording_elapsed_seconds)

    def _on_save_recording_requested(self) -> None:
        if self._recorder.is_recording:
            return
        if not self._recorder.has_take():
            self.window.show_info("Recording", "No recording available to save.")
            return
        path_text, _ = QFileDialog.getSaveFileName(
            self.window,
            "Save MIDI Recording",
            str(Path.home() / f"{APP_NAME}_Take.mid"),
            "MIDI Files (*.mid)",
        )
        if not path_text:
            return
        try:
            self._recorder.save_as(Path(path_text))
        except Exception as exc:
            self.window.show_warning(
                "Recording",
                f"Could not save recording:\n{exc}",
            )
            return
        self.window.show_info("Recording", "Recording saved.")

    def _on_all_notes_off_requested(self) -> None:
        self._stop_all_notes()
    def _on_tutorial_requested(self) -> None:
        self.start_tutorial()

    def _build_tutorial_steps(self) -> list[TutorialStep]:
        return [
            {
                "id": "welcome",
                "title": "Welcome",
                "body": "This tutorial walks through the core controls. Click Next to begin.",
                "target": "",
            },
            {
                "id": "piano",
                "title": "Piano",
                "body": "Use your keyboard or mouse to play notes. Pressed keys highlight instantly.",
                "target": "piano",
            },
            {
                "id": "stats",
                "title": "Stats Bar",
                "body": "Live values show volume, sustain state, KPS, held notes, polyphony, and transpose.",
                "target": "stats",
            },
            {
                "id": "footer",
                "title": "Footer Actions",
                "body": "Use footer links to open settings, controls, hide stats, launch tutorial, or open website.",
                "target": "footer",
            },
            {
                "id": "controls_toggle",
                "title": "Controls Toggle",
                "body": "Use Controls for frequent actions like instrument/program, MIDI In, quick mute, and recording.",
                "target": "controls_toggle",
            },
            {
                "id": "controls_section",
                "title": "Controls Panel",
                "body": "This panel keeps live performance controls in one place.",
                "target": "controls_section",
                "open_controls": True,
            },
            {
                "id": "controls_instrument",
                "title": "Instrument and Program",
                "body": "Select instrument, bank, and preset here. Built-in DEFAULT is pinned first, and GRAND PIANO is pinned second.",
                "target": "controls_instrument",
                "open_controls": True,
            },
            {
                "id": "controls_midi",
                "title": "MIDI Input",
                "body": "Pick a MIDI input device to play from external hardware. The list refreshes each time you open this dropdown, even when no devices are currently available.",
                "target": "controls_midi",
                "open_controls": True,
            },
            {
                "id": "controls_recording",
                "title": "Recording",
                "body": "Start/stop MIDI recording here, then use Save recording to export a .mid take.",
                "target": "controls_recording",
                "open_controls": True,
            },
            {
                "id": "controls_all_notes_off",
                "title": "All Notes OFF",
                "body": "If any note gets stuck, click All Notes OFF to immediately silence all active notes.",
                "target": "controls_all_notes_off",
                "open_controls": True,
            },
            {
                "id": "settings_toggle",
                "title": "Settings Toggle",
                "body": "This button shows or hides the settings panel.",
                "target": "settings_toggle",
            },
            {
                "id": "sound_section",
                "title": "Sound Settings",
                "body": "Tune volume, velocity, transpose, and sustain behavior in this section.",
                "target": "sound_section",
                "open_settings": True,
            },
            {
                "id": "sound_velocity",
                "title": "Velocity",
                "body": "Velocity sets note attack strength for QWERTY and mouse input (1-127). External MIDI input keeps the velocity from your hardware.",
                "target": "sound_velocity",
                "open_settings": True,
            },
            {
                "id": "keyboard_section",
                "title": "Keyboard Settings",
                "body": "Switch key range and toggle keyboard/note labels.",
                "target": "keyboard_section",
                "open_settings": True,
            },
            {
                "id": "keyboard_88_mode",
                "title": "88-Key Mode",
                "body": "88-key mode is available here. The extra keys can be played using Control (ctrl) + (the key) which is indicated with C + (the key).",
                "target": "keyboard_section",
                "open_settings": True,
                "set_mode": "88",
            },
            {
                "id": "interface_section",
                "title": "Interface Settings",
                "body": "Theme, UI size, animation speed, key colors, and updates are here.",
                "target": "interface_section",
                "open_settings": True,
            },
            {
                "id": "reset_defaults",
                "title": "Reset Defaults",
                "body": "Reset everything back to default values when needed.",
                "target": "reset_defaults",
                "open_settings": True,
            },
            {
                "id": "finish",
                "title": "Done",
                "body": "Tutorial complete. Click Finish to close this guide.",
                "target": "",
            },
        ]

    def start_tutorial(self) -> None:
        if self._tutorial_active:
            return
        self._tutorial_steps = self._build_tutorial_steps()
        if not self._tutorial_steps:
            return
        self._tutorial_active = True
        self._tutorial_index = 0
        self._tutorial_prev_settings_open = self._settings_open
        self._tutorial_prev_controls_open = self._controls_open
        self._tutorial_prev_mode = self._mode
        self._stop_all_notes()
        self.window.set_tutorial_mode(True)
        self._show_tutorial_step()

    def _show_tutorial_step(self) -> None:
        if not self._tutorial_active or not self._tutorial_steps:
            return
        while 0 <= self._tutorial_index < len(self._tutorial_steps):
            step = self._tutorial_steps[self._tutorial_index]
            if bool(step.get("open_settings")) and not self._settings_open:
                self._settings_open = True
                self.window.set_settings_visible(True)
            if bool(step.get("open_controls")) and not self._controls_open:
                self._controls_open = True
                self.window.set_controls_visible(True)

            mode_value = str(step.get("set_mode", "")).strip()
            if mode_value in ("61", "88"):
                step_mode: PianoMode = "88" if mode_value == "88" else "61"
                if step_mode != self._mode:
                    self._stop_all_notes()
                    self._apply_mode(step_mode, persist=False)
            elif self._tutorial_prev_mode == "61" and self._mode != "61":
                self._stop_all_notes()
                self._apply_mode("61", persist=False)

            target_key = str(step.get("target", "")).strip()
            targets = self.window.tutorialTargets()
            target_widget = targets.get(target_key) if target_key else None
            if target_key and target_widget is None:
                self._tutorial_index += 1
                continue
            if target_widget is not None:
                self.window.ensure_settings_target_visible(target_widget)
                self.window.ensure_controls_target_visible(target_widget)

            self.window.update_tutorial_step(
                title=str(step.get("title", "Tutorial")),
                body=str(step.get("body", "")),
                index=self._tutorial_index,
                total=len(self._tutorial_steps),
                target_widget=target_widget,
            )
            return

        self._end_tutorial(completed=True)

    def _advance_tutorial(self) -> None:
        if not self._tutorial_active:
            return
        if self._tutorial_index >= len(self._tutorial_steps) - 1:
            self._end_tutorial(completed=True)
            return
        self._tutorial_index += 1
        self._show_tutorial_step()

    def _rewind_tutorial(self) -> None:
        if not self._tutorial_active:
            return
        if self._tutorial_index <= 0:
            self._show_tutorial_step()
            return
        self._tutorial_index -= 1
        self._show_tutorial_step()

    def _end_tutorial(self, completed: bool) -> None:
        _ = completed
        if not self._tutorial_active:
            return
        self._tutorial_active = False
        self._tutorial_steps = []
        self._tutorial_index = 0
        self.window.set_tutorial_mode(False)

        restore_settings_open = bool(self._tutorial_prev_settings_open)
        if self._settings_open != restore_settings_open:
            self._settings_open = restore_settings_open
            self.window.set_settings_visible(self._settings_open)

        restore_controls_open = bool(self._tutorial_prev_controls_open)
        if self._controls_open != restore_controls_open:
            self._controls_open = restore_controls_open
            self.window.set_controls_visible(self._controls_open)

        if self._mode != self._tutorial_prev_mode:
            self._apply_mode(self._tutorial_prev_mode, persist=False)

        self.window.piano_widget.setFocus()

    def _on_website_requested(self) -> None:
        QDesktopServices.openUrl(QUrl(OFFICIAL_WEBSITE_URL))

    @staticmethod
    def _normalized_soundfont_stem(path: Path) -> str:
        return "".join(ch for ch in path.stem.lower() if ch.isalnum())

    def _has_high_quality_soundfont(self) -> bool:
        for instrument in self._instruments:
            if self._normalized_soundfont_stem(instrument.path) == "grandpiano":
                return True
        return False

    def _download_high_quality_soundfont(self, target_path: Path) -> bool:
        request = urllib.request.Request(
            url=HQ_SOUNDFONT_URL,
            headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"},
            method="GET",
        )
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            with urllib.request.urlopen(request, timeout=30.0) as response, target_path.open("wb") as target:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    target.write(chunk)
        except Exception as exc:
            try:
                if target_path.exists():
                    target_path.unlink()
            except Exception:
                pass
            self.window.show_warning(
                "SoundFont Download Failed",
                f"Could not download high quality soundfont:\n{exc}",
            )
            return False

        self._refresh_instruments()
        self.window.show_info(
            "SoundFont Downloaded",
            "High quality soundfont downloaded successfully.\n\n"
            f"Saved to:\n{target_path}",
        )
        return True

    def _maybe_prompt_high_quality_soundfont(self) -> None:
        if self._is_shutdown or self._hq_soundfont_prompt_seen:
            return
        if self._has_high_quality_soundfont():
            self._hq_soundfont_prompt_seen = True
            self._schedule_persist()
            return

        portable_fonts = ensure_portable_fonts_dir()
        target_path = portable_fonts / HQ_SOUNDFONT_FILENAME

        response = self.window.ask_yes_no(
            "Grand Piano SoundFont",
            "Download high quality grand piano SoundFont (~30 MB)?\n\n"
            "This soundfont will be stored in the fonts folder.",
            default_yes=True,
        )
        if response:
            if self._download_high_quality_soundfont(target_path):
                self._hq_soundfont_prompt_seen = True
                self._schedule_persist()
            return

        confirm_skip = self.window.ask_yes_no(
            "Confirm Skip",
            "Are you sure you want to skip this download?\n\n"
            "This prompt will NOT be shown again.",
            default_yes=False,
        )
        if confirm_skip:
            self._hq_soundfont_prompt_seen = True
            self._schedule_persist()

    def _on_reset_defaults_requested(self) -> None:
        if self._tutorial_active:
            return
        self._stop_all_notes()
        defaults = AppSettings()

        self._mode = defaults.mode
        self._volume = defaults.volume
        self._velocity = defaults.velocity
        self._instrument_id = defaults.instrument_id
        self._instrument_bank = defaults.instrument_bank
        self._instrument_preset = defaults.instrument_preset
        self._show_stats = defaults.show_stats
        self._controls_open = defaults.controls_open
        self._settings_open = False
        self._transpose = defaults.transpose
        self._sustain_percent = defaults.sustain_percent
        self._hold_space_for_sustain = defaults.hold_space_for_sustain
        self._show_key_labels = defaults.show_key_labels
        self._show_note_labels = defaults.show_note_labels
        self._theme_mode = defaults.theme_mode
        self._ui_scale = _round_scale(defaults.ui_scale)
        self._animation_speed = defaults.animation_speed
        self._auto_check_updates = defaults.auto_check_updates
        self._midi_input_device = defaults.midi_input_device
        self._white_key_color = defaults.white_key_color
        self._white_key_pressed_color = defaults.white_key_pressed_color
        self._black_key_color = defaults.black_key_color
        self._black_key_pressed_color = defaults.black_key_pressed_color
        self._hq_soundfont_prompt_seen = defaults.hq_soundfont_prompt_seen
        self._space_override_off = False
        self._kps_events.clear()

        self._apply_theme()
        self.window.set_key_color("white_key", self._white_key_color)
        self.window.set_key_color("white_key_pressed", self._white_key_pressed_color)
        self.window.set_key_color("black_key", self._black_key_color)
        self.window.set_key_color("black_key_pressed", self._black_key_pressed_color)
        self.window.set_theme_mode(self._theme_mode)
        self.window.piano_widget.set_animation_speed(self._animation_speed)
        self.window.set_animation_speed(self._animation_speed)
        self.window.piano_widget.set_ui_scale(self._ui_scale)
        self.window.set_ui_scale(self._ui_scale)
        self.window.set_auto_check_updates(self._auto_check_updates)
        self.window.set_volume(self._volume)
        self.window.set_velocity(self._velocity)
        self.audio_engine.set_master_volume(self._volume)
        self.window.set_transpose(self._transpose)
        self.window.set_sustain_percent(self._sustain_percent)
        self.window.set_hold_space_sustain_mode(self._hold_space_for_sustain)
        self.window.set_label_visibility(self._show_key_labels, self._show_note_labels)
        self.window.piano_widget.set_label_visibility(self._show_key_labels, self._show_note_labels)
        self.window.set_stats_visible(self._show_stats)
        self.window.set_settings_visible(False)
        self.window.set_controls_visible(self._controls_open)
        self.window.set_recording_state(active=False, has_take=False)
        self._recording_started_at = 0.0
        self._recording_elapsed_seconds = 0
        self._set_recording_elapsed_display(0)

        self._apply_mode(self._mode, persist=False)
        self._refresh_instruments()
        self._refresh_midi_inputs()
        self._restore_midi_input_device(persist=False, show_warning=False)
        fallback = select_fallback_instrument(self._instruments)
        if fallback is not None:
            self._apply_instrument_selection(
                fallback.id,
                defaults.instrument_bank,
                defaults.instrument_preset,
                persist=False,
            )
        else:
            self._instrument_id = ""
            self._available_programs = {}
            self.window.set_bank_preset_options([], [], 0, 0)
        self._refresh_stats_ui()
        self._schedule_persist()

    def _on_mouse_note_pressed(self, base_note: int) -> None:
        if self._tutorial_active:
            return
        self._current_mouse_base_note = int(base_note)
        self._activate_mouse_source(self._current_mouse_base_note)

    def _on_mouse_note_released(self, _base_note: int) -> None:
        if self._tutorial_active:
            return
        self._release_mouse_source()

    def _on_mouse_drag_note_changed(self, base_note: object) -> None:
        if self._tutorial_active:
            return
        if base_note is None:
            self._current_mouse_base_note = None
            self._release_mouse_source()
            return
        if not isinstance(base_note, int):
            return
        if self._current_mouse_base_note == base_note:
            return
        self._current_mouse_base_note = base_note
        self._activate_mouse_source(base_note)

    def _activate_mouse_source(self, base_note: int) -> None:
        source = "mouse"
        previous = self._source_to_sounding_note.pop(source, None)
        if previous is not None:
            self._release_note_source(previous, source)
        sounding = self._apply_transpose(base_note)
        self._source_to_sounding_note[source] = sounding
        self._activate_note(sounding, source, velocity=self._velocity)
        self._record_kps_event()
        self._mark_stats_dirty()

    def _release_mouse_source(self) -> None:
        source = "mouse"
        sounding = self._source_to_sounding_note.pop(source, None)
        if sounding is None:
            return
        self._release_note_source(sounding, source)
        self._mark_stats_dirty()

    def _activate_external_source(self, base_note: int, source: str, velocity: int = 100) -> None:
        previous = self._source_to_sounding_note.pop(source, None)
        if previous is not None:
            self._release_note_source(previous, source)
        sounding = self._apply_transpose(base_note)
        self._source_to_sounding_note[source] = sounding
        self._activate_note(sounding, source, velocity=velocity)
        self._record_kps_event()
        self._mark_stats_dirty()

    def _release_external_source(self, source: str) -> None:
        sounding = self._source_to_sounding_note.pop(source, None)
        if sounding is None:
            return
        self._release_note_source(sounding, source)
        self._mark_stats_dirty()

    @staticmethod
    def _is_descendant_of(child: object, ancestor: object) -> bool:
        current = child
        while current is not None:
            if current is ancestor:
                return True
            parent_getter = getattr(current, "parent", None)
            if not callable(parent_getter):
                return False
            current = parent_getter()
        return False

    def _is_main_window_key_context(self, watched: QObject) -> bool:
        if watched is self.window or watched is self.window.piano_widget:
            return True
        if self._is_descendant_of(watched, self.window):
            return True
        focus = QApplication.focusWidget()
        if focus is None:
            return False
        if focus is self.window or focus is self.window.piano_widget:
            return True
        return self._is_descendant_of(focus, self.window)

    def eventFilter(self, watched: QObject, event: QEvent) -> bool:              
        if watched is self.window and event.type() == QEvent.Close:
            self.shutdown()
            return False
        if event.type() in {QEvent.ApplicationDeactivate, QEvent.WindowDeactivate}:
            self._stop_all_notes()
            self._refresh_stats_ui()
            return False
        if watched in {self.window, self.window.piano_widget} and event.type() == QEvent.FocusOut:
            self._stop_all_notes()
            self._refresh_stats_ui()
            return False

        if event.type() == QEvent.KeyPress:
            if not self._is_main_window_key_context(watched):
                return super().eventFilter(watched, event)
            key_event = event                            
            if isinstance(key_event, QKeyEvent):
                return self._handle_key_press_event(key_event)
        if event.type() == QEvent.KeyRelease:
            if not self._is_main_window_key_context(watched):
                return super().eventFilter(watched, event)
            key_event = event                            
            if isinstance(key_event, QKeyEvent):
                return self._handle_key_release_event(key_event)
        return super().eventFilter(watched, event)

    def _step_volume(self, delta: float) -> None:
        self._on_volume_changed(self._volume + delta)

    def _step_transpose(self, delta: int) -> None:
        self._on_transpose_changed(self._transpose + delta)

    def _handle_key_press_event(self, event: QKeyEvent) -> bool:
        key = int(event.key())
        if self._tutorial_active:
            if key == int(Qt.Key.Key_Escape) and not event.isAutoRepeat():
                self._end_tutorial(completed=False)
            return True
        if key in {int(Qt.Key.Key_Tab), int(Qt.Key.Key_Backtab)}:
            return True
        if key == int(Qt.Key.Key_Left):
            self._step_transpose(-1)
            return True
        if key == int(Qt.Key.Key_Right):
            self._step_transpose(+1)
            return True
        if key == int(Qt.Key.Key_Up):
            self._step_volume(+0.02)
            return True
        if key == int(Qt.Key.Key_Down):
            self._step_volume(-0.02)
            return True

        if key == int(Qt.Key.Key_Space):
            if event.isAutoRepeat():
                return True
            if not self._space_override_off:
                self._space_override_off = True
            if self._is_sustain_temporarily_off():
                self._release_all_sustained()
                self._mark_stats_dirty()
            return True

        binding = self._binding_from_key_event(event)
        if binding is None:
            return False
        if event.isAutoRepeat():
            return True
        keycodes = self._event_keycodes(event)
        handled = self._handle_binding_press(binding, keycodes)
        if handled:
            self._record_kps_event()
            self._mark_stats_dirty()
        return handled

    def _handle_key_release_event(self, event: QKeyEvent) -> bool:
        key = int(event.key())
        if self._tutorial_active:
            return True
        if key in {int(Qt.Key.Key_Tab), int(Qt.Key.Key_Backtab)}:
            return True
        if key in {
            int(Qt.Key.Key_Left),
            int(Qt.Key.Key_Right),
            int(Qt.Key.Key_Up),
            int(Qt.Key.Key_Down),
        }:
            return True

        if key == int(Qt.Key.Key_Space):
            if event.isAutoRepeat():
                return True
            if self._space_override_off:
                self._space_override_off = False
            if self._is_sustain_temporarily_off():
                self._release_all_sustained()
                self._mark_stats_dirty()
            return True

        if event.isAutoRepeat():
            return True
        keycodes = self._event_keycodes(event)
        binding = self._binding_from_key_event(event)
        handled = self._handle_binding_release(keycodes, binding)
        if handled:
            self._mark_stats_dirty()
        return handled

    @staticmethod
    def _event_keycodes(event: QKeyEvent) -> tuple[int, ...]:
        native = int(event.nativeScanCode())
        key = int(event.key())
        codes: list[int] = []
        if native > 0:
            codes.append(native)
        if key > 0 and key not in codes:
            codes.append(key)
        return tuple(codes)

    @staticmethod
    def _normalize_keycodes(keycodes: int | tuple[int, ...]) -> tuple[int, ...]:
        if isinstance(keycodes, int):
            return (int(keycodes),)
        normalized: list[int] = []
        for code in keycodes:
            value = int(code)
            if value not in normalized:
                normalized.append(value)
        return tuple(normalized)

    def _binding_from_key_event(self, event: QKeyEvent) -> Binding | None:
        text = event.text()
        key_name = self._key_name_from_event(event)
        modifiers = event.modifiers()
        shift = bool(modifiers & Qt.ShiftModifier)
        ctrl = bool(modifiers & Qt.ControlModifier)
        return normalize_key_event(text, key_name, shift=shift, ctrl=ctrl)

    @staticmethod
    def _key_name_from_event(event: QKeyEvent) -> str:
        key = int(event.key())
        key_a = int(Qt.Key.Key_A)
        key_z = int(Qt.Key.Key_Z)
        key_0 = int(Qt.Key.Key_0)
        key_9 = int(Qt.Key.Key_9)

        if key_a <= key <= key_z:
            return chr(ord("a") + (key - key_a))
        if key_0 <= key <= key_9:
            return str(key - key_0)

        key_names: dict[int, str] = {
            int(Qt.Key.Key_Exclam): "exclam",
            int(Qt.Key.Key_At): "at",
            int(Qt.Key.Key_NumberSign): "numbersign",
            int(Qt.Key.Key_Dollar): "dollar",
            int(Qt.Key.Key_Percent): "percent",
            int(Qt.Key.Key_AsciiCircum): "asciicircum",
            int(Qt.Key.Key_Ampersand): "ampersand",
            int(Qt.Key.Key_Asterisk): "asterisk",
            int(Qt.Key.Key_ParenLeft): "parenleft",
            int(Qt.Key.Key_ParenRight): "parenright",
        }
        if key in key_names:
            return key_names[key]

        text = event.text().strip()
        return text.lower() if len(text) == 1 else ""

    def _source_for_binding(self, binding: Binding) -> str:
        if isinstance(binding, tuple):
            return f"kb:{binding[0]}:{binding[1]}"
        return f"kb:{binding}"

    def _apply_transpose(self, base_note: int) -> int:
        return clamp_transposed_note(base_note, self._transpose, self._mode_min, self._mode_max)

    def _register_binding_keycodes(self, binding: Binding, keycodes: tuple[int, ...]) -> None:
        stored = self._binding_to_keycodes.setdefault(binding, set())
        for keycode in keycodes:
            previous = self._keycode_to_binding.get(keycode)
            if previous is not None and previous != binding:
                previous_codes = self._binding_to_keycodes.get(previous)
                if previous_codes is not None:
                    previous_codes.discard(keycode)
                    if not previous_codes:
                        self._binding_to_keycodes.pop(previous, None)
            self._keycode_to_binding[keycode] = binding
            stored.add(keycode)

    def _remove_binding_keycodes(self, binding: Binding) -> None:
        keycodes = self._binding_to_keycodes.pop(binding, set())
        for keycode in keycodes:
            if self._keycode_to_binding.get(keycode) == binding:
                self._keycode_to_binding.pop(keycode, None)

    @staticmethod
    def _release_candidates(binding_hint: Binding | None) -> tuple[Binding, ...]:
        if binding_hint is None:
            return ()
        candidates: list[Binding] = [binding_hint]
        if isinstance(binding_hint, str):
            base = binding_hint.strip().lower()
            if len(base) == 1 and base.isalnum():
                candidates.append(("shift", base))
                candidates.append(("ctrl", base))
        elif isinstance(binding_hint, tuple):
            modifier, base_value = binding_hint
            base = str(base_value).strip().lower()
            if len(base) == 1 and base.isalnum():
                candidates.append(base)
                if modifier == "shift":
                    candidates.append(("ctrl", base))
                elif modifier == "ctrl":
                    candidates.append(("shift", base))
        deduped: list[Binding] = []
        for candidate in candidates:
            if candidate not in deduped:
                deduped.append(candidate)
        return tuple(deduped)

    def _resolve_binding_from_keycodes(self, keycodes: tuple[int, ...]) -> Binding | None:
        for keycode in keycodes:
            binding = self._keycode_to_binding.get(keycode)
            if binding is not None:
                return binding
        return None

    def _handle_binding_press(self, binding: Binding, keycodes: int | tuple[int, ...]) -> bool:
        base_note = self._binding_to_midi.get(binding)
        if base_note is None:
            return False
        if binding in self._active_bindings:
            return False

        source = self._source_for_binding(binding)
        sounding_note = self._apply_transpose(base_note)
        self._active_bindings.add(binding)
        normalized_keycodes = self._normalize_keycodes(keycodes)
        self._register_binding_keycodes(binding, normalized_keycodes)
        self._source_to_sounding_note[source] = sounding_note
        self._activate_note(sounding_note, source, velocity=self._velocity)
        return True

    def _handle_binding_release(self, keycodes: int | tuple[int, ...], binding_hint: Binding | None = None) -> bool:
        normalized_keycodes = self._normalize_keycodes(keycodes)
        binding = self._resolve_binding_from_keycodes(normalized_keycodes)
        if binding is None:
            for candidate in self._release_candidates(binding_hint):
                if candidate in self._active_bindings:
                    binding = candidate
                    break
        if binding is None or binding not in self._active_bindings:
            return False

        self._remove_binding_keycodes(binding)
        self._active_bindings.discard(binding)
        source = self._source_for_binding(binding)
        sounding_note = self._source_to_sounding_note.pop(source, None)
        if sounding_note is None:
            return False
        self._release_note_source(sounding_note, source)
        return True

    def _activate_note(self, note: int, source: str, velocity: int = 100) -> None:
        sources = self._note_sources.setdefault(note, set())
        first_source = len(sources) == 0
        sources.add(source)
        self._sustained_notes.pop(note, None)
        if first_source:
            self.audio_engine.note_on(note, velocity=velocity)
            self._recorder.add_note_on(note, velocity=velocity, timestamp=time.monotonic())
            self.window.piano_widget.set_pressed(note, True)

    def _release_note_source(self, note: int, source: str) -> None:
        sources = self._note_sources.get(note)
        if not sources:
            return
        sources.discard(source)
        if sources:
            return
        self._note_sources.pop(note, None)

        hold_ms = sustain_hold_ms(self._sustain_percent)
        if self._is_sustain_temporarily_off() or hold_ms == 0:
            self._stop_note(note)
            return
                                                                     
        self.window.piano_widget.set_pressed(note, False)
        if hold_ms is None:
            self._sustained_notes[note] = None
            return
        self._sustained_notes[note] = time.monotonic() + (hold_ms / 1000.0)

    def _stop_note(self, note: int) -> None:
        self.audio_engine.note_off(note)
        self._recorder.add_note_off(note, timestamp=time.monotonic())
        self.window.piano_widget.set_pressed(note, False)
        self._sustained_notes.pop(note, None)

    def _release_all_sustained(self) -> None:
        for note in list(self._sustained_notes.keys()):
            self._stop_note(note)
        self._sustained_notes.clear()

    def _record_note_off_for_active_notes(self) -> None:
        if not self._recorder.is_recording:
            return
        notes = set(self._note_sources.keys()) | set(self._sustained_notes.keys())
        if not notes:
            return
        timestamp = time.monotonic()
        for note in notes:
            self._recorder.add_note_off(note, timestamp=timestamp)

    def _stop_all_notes(self) -> None:
        notes = set(self._note_sources.keys()) | set(self._sustained_notes.keys())
        self._active_bindings.clear()
        self._keycode_to_binding.clear()
        self._binding_to_keycodes.clear()
        self._note_sources.clear()
        self._source_to_sounding_note.clear()
        self._sustained_notes.clear()
        self._current_mouse_base_note = None
        timestamp = time.monotonic()
        for note in notes:
            if self._recorder.is_recording:
                self._recorder.add_note_off(note, timestamp=timestamp)
            self.window.piano_widget.set_pressed(note, False)
        self.audio_engine.all_notes_off()

    def _refresh_sustain_deadlines(self) -> None:
        if not self._sustained_notes:
            return
        hold_ms = sustain_hold_ms(self._sustain_percent)
        if hold_ms == 0 or self._is_sustain_temporarily_off():
            self._release_all_sustained()
            return
        if hold_ms is None:
            for note in list(self._sustained_notes.keys()):
                self._sustained_notes[note] = None
            return
        deadline = time.monotonic() + (hold_ms / 1000.0)
        for note in list(self._sustained_notes.keys()):
            self._sustained_notes[note] = deadline

    def _record_kps_event(self) -> None:
        now = time.monotonic()
        self._kps_events.append(now)
        trim_kps_events(self._kps_events, KPS_WINDOW_SECONDS, now=now)

    def _collect_stats(self) -> dict[str, str]:
        return collect_stats_values(
            volume=self._volume,
            sustain_percent=self._sustain_percent,
            sustain_temporarily_off=self._is_sustain_temporarily_off(),
            transpose=self._transpose,
            note_sources=self._note_sources,
            sustained_notes=self._sustained_notes,
            kps_events=self._kps_events,
            kps_window_seconds=KPS_WINDOW_SECONDS,
            stats_order=STATS_ORDER,
        )

    def _refresh_stats_ui(self) -> None:
        values = self._collect_stats()
        sustain_active = (not self._is_sustain_temporarily_off()) and self._sustain_percent > 0
        self.window.set_stats_values(values, sustain_active=sustain_active)
        self._stats_dirty = False

    def _flush_pending_stats(self) -> None:
        if self._stats_dirty or self._recorder.is_recording or self._kps_events:
            self._refresh_stats_ui()

    def _mark_stats_dirty(self) -> None:
        self._stats_dirty = True
        if not self._stats_refresh_timer.isActive():
            self._stats_refresh_timer.start()

    def _set_recording_elapsed_display(self, seconds: int) -> None:
        if hasattr(self.window, "set_recording_elapsed"):
            self.window.set_recording_elapsed(seconds)

    def _on_stats_tick(self) -> None:
        if self._recorder.is_recording and self._recording_started_at > 0.0:
            elapsed = max(0, int(time.monotonic() - self._recording_started_at))
            if elapsed != self._recording_elapsed_seconds:
                self._recording_elapsed_seconds = elapsed
                self._set_recording_elapsed_display(elapsed)
        if self._stats_dirty or self._recorder.is_recording or self._kps_events:
            self._flush_pending_stats()

    def _on_sustain_tick(self) -> None:
        if not self._sustained_notes:
            return
        if self._is_sustain_temporarily_off():
            self._release_all_sustained()
            self._refresh_stats_ui()
            return

        now = time.monotonic()
        expired = [
            note
            for note, deadline in self._sustained_notes.items()
            if deadline is not None and now >= deadline
        ]
        if not expired:
            return
        for note in expired:
            self._stop_note(note)
        self._refresh_stats_ui()

    def _schedule_persist(self) -> None:
        self._save_timer.start()

    def _persist_settings_now(self) -> None:
        settings = AppSettings(
            mode=self._mode,
            instrument_id=self._instrument_id,
            volume=self._volume,
            velocity=self._velocity,
            show_stats=self._show_stats,
            controls_open=self._controls_open,
            transpose=self._transpose,
            sustain_percent=self._sustain_percent,
            hold_space_for_sustain=self._hold_space_for_sustain,
            show_key_labels=self._show_key_labels,
            show_note_labels=self._show_note_labels,
            instrument_bank=self._instrument_bank,
            instrument_preset=self._instrument_preset,
            theme_mode=self._theme_mode,
            ui_scale=self._ui_scale,
            animation_speed=self._animation_speed,                          
            auto_check_updates=self._auto_check_updates,
            midi_input_device=self._midi_input_device,
            white_key_color=self._white_key_color,
            white_key_pressed_color=self._white_key_pressed_color,
            black_key_color=self._black_key_color,
            black_key_pressed_color=self._black_key_pressed_color,
            hq_soundfont_prompt_seen=self._hq_soundfont_prompt_seen,
        )
        save_settings(settings, self._settings_path)

    def _is_sustain_temporarily_off(self) -> bool:
        if self._hold_space_for_sustain:
            return not self._space_override_off
        return self._space_override_off

    def _json_from_url(self, url: str, timeout: float = 8.0) -> dict | None:
        request = urllib.request.Request(
            url=url,
            headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:              
            body = response.read().decode("utf-8", errors="replace")
        payload = json.loads(body)
        return payload if isinstance(payload, dict) else None

    def _text_from_url(self, url: str, timeout: float = 8.0) -> tuple[str, str]:
        request = urllib.request.Request(
            url=url,
            headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:              
            final_url = response.geturl()
            body = response.read().decode("utf-8", errors="replace")
        return body, final_url

    def _detect_latest_version(self) -> tuple[str, str]:
        manifest = self._json_from_url(UPDATE_CHECK_MANIFEST_URL)
        if manifest is not None:
            version = (
                manifest.get("version")
                or manifest.get("latest")
                or manifest.get("app_version")
                or ""
            )
            if isinstance(version, str) and _parse_semver(version):
                download_url = manifest.get("download_url")
                if not isinstance(download_url, str) or not download_url.strip():
                    download_url = UPDATE_GITHUB_DOWNLOAD_URL
                return version, download_url

        body, final_url = self._text_from_url(UPDATE_GITHUB_LATEST_URL)
        match = re.search(r"/tag/v?(\d+\.\d+\.\d+)", final_url)
        if match:
            return match.group(1), UPDATE_GITHUB_DOWNLOAD_URL
        match = re.search(r"/releases/tag/v?(\d+\.\d+\.\d+)", body)
        if match:
            return match.group(1), UPDATE_GITHUB_DOWNLOAD_URL

        rss_text, _ = self._text_from_url(UPDATE_SOURCEFORGE_RSS_URL)
        xml_root = ET.fromstring(rss_text)
        titles = xml_root.findall(".//item/title")
        for title in titles:
            if title.text:
                parsed = _parse_semver(title.text)
                if parsed is not None:
                    return f"{parsed[0]}.{parsed[1]}.{parsed[2]}", OFFICIAL_WEBSITE_URL
        raise RuntimeError("Could not parse latest version from update sources.")

    def _trigger_update_check(self, manual: bool) -> None:
        if self._is_shutdown:
            return
        with self._update_lock:
            if self._update_check_active:
                return
            self._update_check_active = True

        worker = threading.Thread(
            target=self._update_check_worker,
            args=(manual,),
            daemon=True,
        )
        worker.start()

    def _update_check_worker(self, manual: bool) -> None:
        if self._is_shutdown:
            return
        result: dict[str, str | bool]
        try:
            latest, url = self._detect_latest_version()
            current_parsed = _parse_semver(APP_VERSION)
            latest_parsed = _parse_semver(latest)
            if current_parsed is None or latest_parsed is None:
                raise RuntimeError("Invalid version format.")
            if latest_parsed > current_parsed:
                result = {"status": "available", "latest": latest, "url": url}
            else:
                result = {"status": "up_to_date", "latest": latest, "url": url}
        except Exception as exc:
            result = {"status": "error", "error": str(exc)}
        if self._is_shutdown:
            return
        try:
            self._updateResultReady.emit(manual, result)
        except RuntimeError:
            return

    def _finish_update_check(self, manual: bool, result: dict[str, str | bool]) -> None:
        if self._is_shutdown:
            return
        with self._update_lock:
            self._update_check_active = False

        status = str(result.get("status", "error"))
        if status == "available":
            latest = str(result.get("latest", ""))
            url = str(result.get("url", OFFICIAL_WEBSITE_URL))
            response = self.window.ask_yes_no(
                "Update Available",
                f"Version {latest} is available. Open download page now?",
                default_yes=True,
            )
            if response:
                QDesktopServices.openUrl(QUrl(url))
            return

        if status == "up_to_date":
            latest = str(result.get("latest", APP_VERSION))
            if manual:
                self.window.show_info(
                    "Up to Date",
                    f"You are up to date (v{latest}).",
                )
            return

        if manual:
            message = str(result.get("error", "Unknown error"))
            self.window.show_warning(
                "Update Check Failed",
                f"Could not check for updates:\n{message}",
            )

    def shutdown(self) -> None:
        if self._is_shutdown:
            return
        self._is_shutdown = True
        with self._update_lock:
            self._update_check_active = False
        try:
            if self._stats_timer.isActive():
                self._stats_timer.stop()
            if self._stats_refresh_timer.isActive():
                self._stats_refresh_timer.stop()
            if self._sustain_timer.isActive():
                self._sustain_timer.stop()
            if self._save_timer.isActive():
                self._save_timer.stop()
            self._midi_manager.close()
            if self._recorder.is_recording:
                self._record_note_off_for_active_notes()
                self._recorder.stop()
            self._recording_started_at = 0.0
            self._recording_elapsed_seconds = 0
            self._set_recording_elapsed_display(0)
            self._stop_all_notes()
            self.audio_engine.shutdown()
            self._persist_settings_now()
        except Exception:
            return

    def run(self) -> None:
        self.window.show()
        QTimer.singleShot(400, self._maybe_prompt_high_quality_soundfont)








