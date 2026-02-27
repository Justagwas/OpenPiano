from __future__ import annotations

import sys
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEvent, QObject, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QKeyEvent, QMouseEvent
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
)
from openpiano.core.instrument_registry import (
    InstrumentInfo,
    discover_instruments,
    ensure_user_fonts_dir,
    localappdata_fonts_dir,
    select_fallback_instrument,
)
from openpiano.core.keymap import (
    Binding,
    MODE_RANGES,
    PianoMode,
    apply_custom_keybinds,
    binding_to_inline_label,
    build_binding_to_notes,
    deserialize_custom_keybind_payload,
    extract_custom_keybind_overrides,
    get_mode_mapping,
    get_note_labels,
    normalize_mouse_binding,
    normalize_key_event,
    normalize_key_event_layout_scancode,
    normalize_key_event_qwerty_scancode,
    remap_bindings_for_keyboard_mode,
    serialize_custom_keybind_payload,
)
from openpiano.core.music_logic import clamp_transposed_note
from openpiano.core.midi_input import MidiInputManager
from openpiano.core.midi_recording import MidiRecorder
from openpiano.core.normalize import quantize_step
from openpiano.core.object_tree import is_descendant_of
from openpiano.core.program_selection import normalize_available_programs, normalize_program_selection
from openpiano.core.runtime_paths import icon_path_candidates
from openpiano.core.settings_store import (
    AppSettings,
    load_settings,
    save_settings,
)
from openpiano.core.stats_logic import collect_stats_values, trim_kps_events
from openpiano.core.theme import apply_key_color_overrides, get_theme
from openpiano.services.midi_routing import MidiRoutingService
from openpiano.services.note_lifecycle import NoteLifecycleService
from openpiano.services.soundfont_assets import (
    download_file_with_retries,
    has_high_quality_soundfont,
)
from openpiano.services.tutorial_flow import TutorialFlowService, TutorialStep
from openpiano.services.update_check import UpdateCheckService, UpdateEndpoints
from openpiano.ui.main_window import MainWindow


AudioFactory = Callable[[], AudioEngineProtocol]
InstrumentProvider = Callable[[], list[InstrumentInfo]]
MidiManagerFactory = Callable[[Callable[[int, int], None], Callable[[int], None]], MidiInputManager]
RecorderFactory = Callable[[], MidiRecorder]
HQ_SOUNDFONT_URL = "https://downloads.justagwas.com/openpiano/GRAND%20PIANO.sf3"
HQ_SOUNDFONT_FILENAME = "GRAND PIANO.sf3"
HQ_SOUNDFONT_DOWNLOAD_TIMEOUT_SECONDS = 30.0
HQ_SOUNDFONT_DOWNLOAD_RETRIES = 3
HQ_SOUNDFONT_DOWNLOAD_RETRY_DELAY_SECONDS = 0.6


def _round_scale(value: float) -> float:
    return quantize_step(value, UI_SCALE_MIN, UI_SCALE_MAX, UI_SCALE_STEP, digits=2)


class PianoAppController(QObject):
    _updateResultReady = Signal(bool, object)
    _updateInstallReady = Signal(object)
    _updateInstallProgressReady = Signal(int, str)
    _updateInstallHandoffRequested = Signal(object)
    _midiNoteOnReady = Signal(int, int)
    _midiNoteOffReady = Signal(int)
    _hqSoundfontDownloadReady = Signal(object)
    _midiDropdownRefreshReady = Signal(object)

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
        self._sustain_fade = max(0, min(100, int(settings.sustain_fade)))
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
        self._keyboard_input_mode = settings.keyboard_input_mode
        self._keyboard_layout_choice_seen = bool(settings.keyboard_layout_choice_seen)
        self._space_override_off = False
        self._sustain_gate_percent = 0.0 if self._is_sustain_temporarily_off() else 100.0
        self._default_keybind_map_full = self._build_default_keybind_map_full(self._keyboard_input_mode)
        self._custom_keybind_overrides = deserialize_custom_keybind_payload(settings.custom_keybinds)
        self._keybind_committed_map_full = apply_custom_keybinds(
            self._default_keybind_map_full,
            self._custom_keybind_overrides,
        )
        self._keybind_staging_map_full: dict[int, Binding] = dict(self._keybind_committed_map_full)
        self._keybind_edit_active = False
        self._keybind_selected_note: int | None = None
        self._keybind_edit_undo_stack: list[tuple[int, Binding]] = []
        self._keyboard_layout_prompt_active = False

        self._mapping: dict[int, Binding] = {}
        self._binding_to_notes: dict[Binding, tuple[int, ...]] = {}
        self._note_labels: dict[int, str] = {}
        self._keys: list[int] = []
        self._mode_min = 36
        self._mode_max = 96

        self._active_bindings: set[Binding] = set()
        self._active_binding_sources: dict[Binding, tuple[str, ...]] = {}
        self._keycode_to_binding: dict[int, Binding] = {}
        self._binding_to_keycodes: dict[Binding, set[int]] = {}
        self._note_sources: dict[int, set[str]] = {}
        self._source_to_sounding_note: dict[str, int] = {}
        self._sustained_notes: dict[int, float | None] = {}
        self._note_lifecycle = NoteLifecycleService(self._note_sources, self._sustained_notes)
        self._current_mouse_base_note: int | None = None
        self._kps_events: deque[float] = deque()
        self._stats_dirty = False

        self._instruments: list[InstrumentInfo] = []
        self._instrument_by_id: dict[str, InstrumentInfo] = {}
        self._available_programs: dict[int, list[int]] = {}
        self._available_program_names: dict[int, dict[int, str]] = {}
        self._tutorial_active = False
        self._tutorial_steps: list[TutorialStep] = []
        self._tutorial_index = 0
        self._tutorial_prev_settings_open = False
        self._tutorial_prev_controls_open = False
        self._tutorial_prev_mode: PianoMode = self._mode
        self._tutorial_flow = TutorialFlowService()

        self.audio_engine: AudioEngineProtocol = SilentAudioEngine()
        self.audio_available = False

        self._update_lock = threading.Lock()
        self._update_stop_event = threading.Event()
        self._update_check_active = False
        self._update_install_active = False
        self._update_handoff_event = threading.Event()
        self._update_handoff_continue = False
        self._update_handoff_restart = True
        self._updateResultReady.connect(self._finish_update_check)
        self._updateInstallReady.connect(self._finish_update_install)
        self._updateInstallProgressReady.connect(self._on_update_install_progress)
        self._updateInstallHandoffRequested.connect(self._on_update_install_handoff_requested)
        self._midiNoteOnReady.connect(self._on_midi_note_on)
        self._midiNoteOffReady.connect(self._on_midi_note_off)
        self._hqSoundfontDownloadReady.connect(self._finish_high_quality_soundfont_download)
        self._midiDropdownRefreshReady.connect(self._finish_midi_dropdown_refresh)

        self._midi_manager = self._midi_manager_factory(self._queue_midi_note_on, self._queue_midi_note_off)
        self._midi_routing = MidiRoutingService(self._midi_manager)
        self._hq_soundfont_download_active = False
        self._midi_dropdown_refresh_active = False
        self._recorder = self._recorder_factory()
        self._recording_started_at = 0.0
        self._recording_elapsed_seconds = 0
        self._update_service = UpdateCheckService(
            app_name=APP_NAME,
            app_version=APP_VERSION,
            endpoints=UpdateEndpoints(
                manifest_url=UPDATE_CHECK_MANIFEST_URL,
                page_url=OFFICIAL_WEBSITE_URL,
            ),
        )

        base_theme = get_theme(self._theme_mode)
        effective_theme = apply_key_color_overrides(
            base_theme,
            white=self._white_key_color,
            white_pressed=self._white_key_pressed_color,
            black=self._black_key_color,
            black_pressed=self._black_key_pressed_color,
        )
        if icon_path is None:
            candidates = icon_path_candidates(extra_dirs=[Path(__file__).resolve().parents[1]])
            resolved_icon = next((path for path in candidates if path.exists()), candidates[-1] if candidates else None)
        else:
            resolved_icon = icon_path
        self.window = MainWindow(
            theme=effective_theme,
            icon_path=resolved_icon,
        )

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
        self._apply_ui_state_to_window()
        self.window.set_recording_elapsed(0)

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

    def _connect_signals(self) -> None:
        self.window.modeChanged.connect(self._on_mode_changed)
        self.window.instrumentChanged.connect(self._on_instrument_changed)
        self.window.bankChanged.connect(self._on_bank_changed)
        self.window.presetChanged.connect(self._on_preset_changed)
        self.window.volumeChanged.connect(self._on_volume_changed)
        self.window.velocityChanged.connect(self._on_velocity_changed)
        self.window.transposeChanged.connect(self._on_transpose_changed)
        self.window.sustainPercentChanged.connect(self._on_sustain_percent_changed)
        self.window.sustainFadeChanged.connect(self._on_sustain_fade_changed)
        self.window.holdSpaceSustainChanged.connect(self._on_hold_space_sustain_changed)
        self.window.showKeyLabelsChanged.connect(self._on_show_key_labels_changed)
        self.window.showNoteLabelsChanged.connect(self._on_show_note_labels_changed)
        self.window.changeKeybindsRequested.connect(self._on_change_keybinds_requested)
        self.window.changeKeyboardLayoutRequested.connect(self._on_change_keyboard_layout_requested)
        self.window.doneKeybindsRequested.connect(self._on_done_keybinds_requested)
        self.window.discardKeybindsRequested.connect(self._on_discard_keybinds_requested)
        self.window.keybindEditActionBlocked.connect(self._on_keybind_edit_action_blocked)
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
        self.window.updateProgressCanceled.connect(self._on_update_progress_canceled)

        self.window.piano_widget.notePressed.connect(self._on_mouse_note_pressed)
        self.window.piano_widget.noteReleased.connect(self._on_mouse_note_released)
        self.window.piano_widget.dragNoteChanged.connect(self._on_mouse_drag_note_changed)
        self.window.piano_widget.keybindKeySelected.connect(self._on_keybind_note_selected)

    def _apply_ui_state_to_window(self) -> None:
        self.window.set_volume(self._volume)
        self.window.set_velocity(self._velocity)
        self.window.set_transpose(self._transpose)
        self.window.set_sustain_percent(self._sustain_percent)
        self.window.set_sustain_fade(self._sustain_fade)
        self.window.set_hold_space_sustain_mode(self._hold_space_for_sustain)
        self.window.set_label_visibility(self._show_key_labels, self._show_note_labels)
        self.window.set_theme_mode(self._theme_mode)
        self.window.set_ui_scale(self._ui_scale)
        self.window.set_animation_speed(self._animation_speed)
        self.window.set_auto_check_updates(self._auto_check_updates)
        self.window.set_stats_visible(self._show_stats)
        self.window.set_settings_visible(self._settings_open)
        self.window.set_controls_visible(self._controls_open)
        self.window.set_recording_state(active=False, has_take=False)
        self.window.set_key_color("white_key", self._white_key_color)
        self.window.set_key_color("white_key_pressed", self._white_key_pressed_color)
        self.window.set_key_color("black_key", self._black_key_color)
        self.window.set_key_color("black_key_pressed", self._black_key_pressed_color)
        self.window.set_keybind_edit_mode(self._keybind_edit_active)

        self._sync_piano_label_visibility()
        self.window.piano_widget.set_animation_speed(self._animation_speed)
        self.window.piano_widget.set_ui_scale(self._ui_scale)
        self.window.piano_widget.set_key_colors(
            self._white_key_color,
            self._white_key_pressed_color,
            self._black_key_color,
            self._black_key_pressed_color,
        )

    def _sync_piano_label_visibility(self) -> None:
        show_key_labels = True if self._keybind_edit_active else self._show_key_labels
        self.window.piano_widget.set_label_visibility(show_key_labels, self._show_note_labels)

    @staticmethod
    def _build_default_keybind_map_full(keyboard_input_mode: str) -> dict[int, Binding]:
        base = get_mode_mapping("88")
        if str(keyboard_input_mode or "").strip().lower() == "layout":
            return remap_bindings_for_keyboard_mode(base, "layout")
        return base

    @staticmethod
    def _build_keyboard_token_map(
        source_mapping: dict[int, Binding],
        target_mapping: dict[int, Binding],
    ) -> dict[str, str]:
        token_map: dict[str, str] = {}
        for note, source_binding in source_mapping.items():
            target_binding = target_mapping.get(note)
            if target_binding is None:
                continue
            source_kind, source_token, source_ctrl, source_shift, source_alt = source_binding
            target_kind, target_token, target_ctrl, target_shift, target_alt = target_binding
            if source_kind != "keyboard" or target_kind != "keyboard":
                continue
            if (source_ctrl, source_shift, source_alt) != (target_ctrl, target_shift, target_alt):
                continue
            if source_token not in token_map:
                token_map[source_token] = target_token
        return token_map

    @staticmethod
    def _translate_keyboard_binding(
        binding: Binding,
        source_to_qwerty: dict[str, str],
        qwerty_to_target: dict[str, str],
    ) -> Binding:
        source_kind, token, ctrl, shift, alt = binding
        if source_kind != "keyboard":
            return binding
        qwerty_token = source_to_qwerty.get(token, token)
        target_token = qwerty_to_target.get(qwerty_token, qwerty_token)
        return ("keyboard", target_token, bool(ctrl), bool(shift), bool(alt))

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
        self._midi_routing.refresh_inputs(
            preferred_device=self._midi_input_device,
            set_devices=self.window.set_midi_input_devices,
            show_warning=self.window.show_warning,
        )

    def _on_midi_input_dropdown_opened(self) -> None:
        if self._is_shutdown or self._midi_dropdown_refresh_active:
            return
        self._midi_routing.maybe_warn_backend_issue(self.window.show_warning)
        preferred = str(self._midi_input_device).strip()
        self._midi_dropdown_refresh_active = True
        worker = threading.Thread(
            target=self._midi_dropdown_refresh_worker,
            args=(preferred,),
            daemon=True,
        )
        worker.start()

    def _midi_dropdown_refresh_worker(self, preferred_device: str) -> None:
        preferred = str(preferred_device).strip()
        devices: list[str] = []
        selected = ""
        applied = ""
        try:
            devices = self._midi_manager.list_input_devices()
            selected = preferred if preferred and preferred in devices else ""
            if preferred and selected:
                current_getter = getattr(self._midi_manager, "current_device", None)
                current = str(current_getter() if callable(current_getter) else "").strip()
                if current != preferred:
                    try:
                        self._midi_manager.open_device(preferred)
                        applied = preferred
                    except Exception:
                        applied = ""
        except Exception:
            devices = []
            selected = ""
            applied = ""

        if self._is_shutdown:
            return
        try:
            self._midiDropdownRefreshReady.emit(
                {
                    "devices": devices,
                    "selected": selected,
                    "applied": applied,
                }
            )
        except RuntimeError:
            return

    def _finish_midi_dropdown_refresh(self, result: dict[str, object]) -> None:
        self._midi_dropdown_refresh_active = False
        if self._is_shutdown:
            return
        devices_raw = result.get("devices", [])
        devices: list[str] = []
        if isinstance(devices_raw, list):
            for item in devices_raw:
                text = str(item).strip()
                if text:
                    devices.append(text)
        selected = str(result.get("selected", "")).strip()
        applied = str(result.get("applied", "")).strip()
        if applied:
            self._midi_input_device = applied
            selected = applied
        self.window.set_midi_input_devices(devices, selected)

    def _restore_midi_input_device(self, persist: bool, show_warning: bool) -> None:
        self._midi_input_device = self._midi_routing.restore_device(
            preferred_device=self._midi_input_device,
            set_devices=self.window.set_midi_input_devices,
            show_warning=self.window.show_warning,
            warning_enabled=show_warning,
        )
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
            self._available_program_names = {}
            self._set_bank_preset_options([], [], 0, 0)
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
            self._available_program_names = {}
            self._set_bank_preset_options([], [], 0, 0)
            return
        self._apply_instrument_selection(
            fallback.id,
            fallback.default_bank,
            fallback.default_preset,
            persist=False,
        )

    def _refresh_program_controls(self) -> None:
        banks = sorted(self._available_programs.keys())
        selected_bank = self._instrument_bank
        selected_preset = self._instrument_preset
        if not banks:
            self._set_bank_preset_options([], [], selected_bank, selected_preset)
            return
        if selected_bank not in self._available_programs:
            selected_bank = banks[0]
        presets = sorted(set(self._available_programs.get(selected_bank, [])))
        if presets and selected_preset not in presets:
            selected_preset = presets[0]
        self._instrument_bank = selected_bank
        self._instrument_preset = selected_preset
        preset_names = self._available_program_names.get(selected_bank, {})
        self._set_bank_preset_options(banks, presets, selected_bank, selected_preset, preset_names=preset_names)

    def _set_bank_preset_options(
        self,
        banks: list[int],
        presets: list[int],
        selected_bank: int,
        selected_preset: int,
        *,
        preset_names: dict[int, str] | None = None,
    ) -> None:
        try:
            self.window.set_bank_preset_options(
                banks,
                presets,
                selected_bank,
                selected_preset,
                preset_names=preset_names or {},
            )
        except TypeError:
            self.window.set_bank_preset_options(banks, presets, selected_bank, selected_preset)

    @staticmethod
    def _normalize_program_name_map(
        raw_names: object,
        programs: dict[int, list[int]],
    ) -> dict[int, dict[int, str]]:
        if not isinstance(raw_names, dict):
            return {}
        normalized: dict[int, dict[int, str]] = {}
        for bank, presets in programs.items():
            bank_key = int(bank)
            bank_names = raw_names.get(bank_key)
            if bank_names is None:
                bank_names = raw_names.get(str(bank_key))
            if not isinstance(bank_names, dict):
                continue
            for preset in presets:
                preset_key = int(preset)
                value = bank_names.get(preset_key)
                if value is None:
                    value = bank_names.get(str(preset_key))
                if not isinstance(value, str):
                    continue
                label = " ".join(value.split()).strip()
                if not label:
                    continue
                normalized.setdefault(bank_key, {})[preset_key] = label
        return normalized

    def _read_available_program_names(self, programs: dict[int, list[int]]) -> dict[int, dict[int, str]]:
        getter = getattr(self.audio_engine, "get_available_program_names", None)
        if not callable(getter):
            return {}
        try:
            raw_names = getter()
        except Exception:
            return {}
        return self._normalize_program_name_map(raw_names, programs)

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

        normalized_bank, normalized_preset = normalize_program_selection(
            programs=programs,
            requested_bank=current_bank,
            requested_preset=current_preset,
        )
        self._instrument_id = instrument.id
        self._instrument_bank = normalized_bank
        self._instrument_preset = normalized_preset
        self._available_programs = normalize_available_programs(programs)
        self._available_program_names = self._read_available_program_names(self._available_programs)
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
        if self._keybind_edit_active:
            self._apply_mode(new_mode, persist=True, mapping_full=self._keybind_staging_map_full)
        else:
            self._apply_mode(new_mode, persist=True)
        self._refresh_stats_ui()

    def _apply_mode(
        self,
        mode: PianoMode,
        persist: bool,
        mapping_full: dict[int, Binding] | None = None,
    ) -> None:
        self._mode = mode
        full_map = mapping_full if mapping_full is not None else self._keybind_committed_map_full
        mode_min, mode_max = MODE_RANGES[mode]
        self._mapping = {note: full_map[note] for note in range(mode_min, mode_max + 1)}
        self._binding_to_notes = build_binding_to_notes(self._mapping)
        self._note_labels = get_note_labels(mode)
        self._keys = sorted(self._mapping.keys())
        self._mode_min, self._mode_max = MODE_RANGES[mode]

        self.window.piano_widget.set_mode(mode, self._mapping, self._note_labels)
        self._sync_piano_label_visibility()
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

    def _on_sustain_fade_changed(self, value: int) -> None:
        clamped = max(0, min(100, int(value)))
        if clamped == self._sustain_fade:
            return
        self._sustain_fade = clamped
        self.window.set_sustain_fade(self._sustain_fade)
        self._apply_sustain_gate_target()
        self._refresh_sustain_deadlines()
        self._refresh_stats_ui()
        self._schedule_persist()

    def _on_hold_space_sustain_changed(self, enabled: bool) -> None:
        mode = bool(enabled)
        if mode == self._hold_space_for_sustain:
            return
        self._hold_space_for_sustain = mode
        self.window.set_hold_space_sustain_mode(self._hold_space_for_sustain)
        self._apply_sustain_gate_target()
        self._refresh_sustain_deadlines()
        self._refresh_stats_ui()
        self._schedule_persist()

    def _on_show_key_labels_changed(self, enabled: bool) -> None:
        self._show_key_labels = bool(enabled)
        self._sync_piano_label_visibility()
        self._schedule_persist()

    def _on_show_note_labels_changed(self, enabled: bool) -> None:
        self._show_note_labels = bool(enabled)
        self._sync_piano_label_visibility()
        self._schedule_persist()

    def _set_keybind_editor_status(self, text: str = "") -> None:
        self.window.set_keybind_edit_mode(self._keybind_edit_active, text)

    def _on_keybind_edit_action_blocked(self) -> None:
        if not self._keybind_edit_active:
            return
        self._set_keybind_editor_status(
            "Keybind editing is active. Press Save to apply changes or Discard to cancel.",
        )

    def _on_change_keybinds_requested(self) -> None:
        if self._tutorial_active or self._keybind_edit_active:
            return
        self._stop_all_notes()
        self._keybind_edit_active = True
        self._keybind_selected_note = None
        self._keybind_staging_map_full = dict(self._keybind_committed_map_full)
        self._keybind_edit_undo_stack.clear()
        self.window.piano_widget.set_keybind_edit_mode(True, None)
        self._apply_mode(self._mode, persist=False, mapping_full=self._keybind_staging_map_full)
        self.window.piano_widget.set_label_visibility(True, self._show_note_labels)
        self._set_keybind_editor_status(
            "Select a key on the piano, then press a keyboard combo or mouse combo. Press Save or Discard when finished. Ctrl+Z undoes the last change.",
        )
        self.window.piano_widget.setFocus()

    def _on_done_keybinds_requested(self) -> None:
        if not self._keybind_edit_active:
            return
        self._keybind_committed_map_full = dict(self._keybind_staging_map_full)
        self._custom_keybind_overrides = extract_custom_keybind_overrides(
            self._default_keybind_map_full,
            self._keybind_committed_map_full,
        )
        self._keybind_edit_active = False
        self._keybind_selected_note = None
        self._keybind_edit_undo_stack.clear()
        self.window.piano_widget.set_keybind_edit_mode(False, None)
        self._apply_mode(self._mode, persist=False)
        self.window.piano_widget.set_label_visibility(self._show_key_labels, self._show_note_labels)
        self._set_keybind_editor_status("")
        self._persist_settings_now()

    def _on_discard_keybinds_requested(self) -> None:
        if not self._keybind_edit_active:
            return
        self._keybind_staging_map_full = dict(self._keybind_committed_map_full)
        self._keybind_edit_active = False
        self._keybind_selected_note = None
        self._keybind_edit_undo_stack.clear()
        self.window.piano_widget.set_keybind_edit_mode(False, None)
        self._apply_mode(self._mode, persist=False)
        self.window.piano_widget.set_label_visibility(self._show_key_labels, self._show_note_labels)
        self._set_keybind_editor_status("Changes discarded.")

    def _on_keybind_note_selected(self, note: int) -> None:
        if not self._keybind_edit_active:
            return
        if note not in self._keybind_staging_map_full:
            return
        self._keybind_selected_note = int(note)
        self.window.piano_widget.set_selected_keybind_note(self._keybind_selected_note)
        note_label = self._note_labels.get(self._keybind_selected_note, f"MIDI {self._keybind_selected_note}")
        binding = self._keybind_staging_map_full.get(self._keybind_selected_note)
        binding_label = binding_to_inline_label(binding) if binding is not None else "None"
        self._set_keybind_editor_status(
            f"{note_label} selected. Press a combo to assign. Current: {binding_label}",
        )

    def _assign_binding_to_selected_note(self, binding: Binding) -> bool:
        if not self._keybind_edit_active or self._keybind_selected_note is None:
            return False
        target_note = int(self._keybind_selected_note)
        if target_note not in self._keybind_staging_map_full:
            return False
        previous_binding = self._keybind_staging_map_full[target_note]
        if binding == previous_binding:
            note_label = self._note_labels.get(target_note, f"MIDI {target_note}")
            binding_label = binding_to_inline_label(binding)
            self._set_keybind_editor_status(
                f"{note_label} is already mapped to {binding_label}. Select another key or click Save/Discard.",
            )
            return True
        self._keybind_edit_undo_stack.append((target_note, previous_binding))
        self._keybind_staging_map_full[target_note] = binding
        self._apply_mode(self._mode, persist=False, mapping_full=self._keybind_staging_map_full)
        self.window.piano_widget.set_keybind_edit_mode(True, target_note)
        self.window.piano_widget.set_selected_keybind_note(target_note)
        note_label = self._note_labels.get(target_note, f"MIDI {target_note}")
        binding_label = binding_to_inline_label(binding)
        self._set_keybind_editor_status(
            f"{note_label} mapped to {binding_label}. Select another key or click Save/Discard.",
        )
        return True

    def _undo_last_keybind_assignment(self) -> bool:
        if not self._keybind_edit_active:
            return False
        if not self._keybind_edit_undo_stack:
            self._set_keybind_editor_status("No keybind changes to undo. Press Save or Discard.")
            return True
        note, previous_binding = self._keybind_edit_undo_stack.pop()
        self._keybind_selected_note = int(note)
        self._keybind_staging_map_full[self._keybind_selected_note] = previous_binding
        self._apply_mode(self._mode, persist=False, mapping_full=self._keybind_staging_map_full)
        self.window.piano_widget.set_keybind_edit_mode(True, self._keybind_selected_note)
        self.window.piano_widget.set_selected_keybind_note(self._keybind_selected_note)
        note_label = self._note_labels.get(self._keybind_selected_note, f"MIDI {self._keybind_selected_note}")
        binding_label = binding_to_inline_label(previous_binding)
        self._set_keybind_editor_status(
            f"Undo applied. {note_label} reverted to {binding_label}. Press Save or Discard when finished.",
        )
        return True

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
            self.window.set_recording_elapsed(0)
            return
        self._record_note_off_for_active_notes()
        self._recorder.stop()
        if self._recording_started_at > 0.0:
            elapsed = max(0, int(time.monotonic() - self._recording_started_at))
            self._recording_elapsed_seconds = elapsed
        self.window.set_recording_state(active=False, has_take=self._recorder.has_take())
        self.window.set_recording_elapsed(self._recording_elapsed_seconds)

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
        if self._keybind_edit_active:
            return
        self.start_tutorial()

    def _sync_tutorial_state_from_service(self) -> None:
        self._tutorial_active = self._tutorial_flow.active
        self._tutorial_steps = self._tutorial_flow.steps
        self._tutorial_index = self._tutorial_flow.index

    def start_tutorial(self) -> None:
        if self._tutorial_flow.active:
            return
        if not self._tutorial_flow.start():
            return
        self._sync_tutorial_state_from_service()
        self._tutorial_prev_settings_open = self._settings_open
        self._tutorial_prev_controls_open = self._controls_open
        self._tutorial_prev_mode = self._mode
        self._stop_all_notes()
        self.window.set_tutorial_mode(True)
        self._show_tutorial_step()

    def _show_tutorial_step(self) -> None:
        if not self._tutorial_flow.active:
            return
        while self._tutorial_flow.active:
            step = self._tutorial_flow.current_step()
            if step is None:
                break
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
                if not self._tutorial_flow.advance():
                    break
                self._sync_tutorial_state_from_service()
                continue
            if target_widget is not None:
                self.window.ensure_settings_target_visible(target_widget)
                self.window.ensure_controls_target_visible(target_widget)

            self._sync_tutorial_state_from_service()
            self.window.update_tutorial_step(
                title=str(step.get("title", "Tutorial")),
                body=self._format_tutorial_step_body(step),
                index=self._tutorial_index,
                total=len(self._tutorial_steps),
                target_widget=target_widget,
            )
            return

        self._end_tutorial(completed=True)

    def _advance_tutorial(self) -> None:
        if not self._tutorial_flow.active:
            return
        if not self._tutorial_flow.advance():
            self._end_tutorial(completed=True)
            return
        self._sync_tutorial_state_from_service()
        self._show_tutorial_step()

    def _rewind_tutorial(self) -> None:
        if not self._tutorial_flow.active:
            return
        if not self._tutorial_flow.rewind():
            self._show_tutorial_step()
            return
        self._sync_tutorial_state_from_service()
        self._show_tutorial_step()

    def _end_tutorial(self, completed: bool) -> None:
        _ = completed
        if not self._tutorial_flow.active:
            return
        self._tutorial_flow.end()
        self._sync_tutorial_state_from_service()
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

    def _format_tutorial_step_body(self, step: TutorialStep) -> str:
        body = str(step.get("body", ""))
        if "{soundfonts_dir}" not in body:
            return body
        soundfonts_dir = localappdata_fonts_dir()
        return body.replace("{soundfonts_dir}", str(soundfonts_dir))

    def _has_high_quality_soundfont(self) -> bool:
        return has_high_quality_soundfont(self._instruments)

    def _download_high_quality_soundfont(self, target_path: Path) -> bool:
        if self._hq_soundfont_download_active:
            return False
        self._hq_soundfont_download_active = True
        worker = threading.Thread(
            target=self._download_high_quality_soundfont_worker,
            args=(target_path,),
            daemon=True,
        )
        worker.start()
        return True

    def _download_high_quality_soundfont_worker(self, target_path: Path) -> None:
        retries = max(1, int(HQ_SOUNDFONT_DOWNLOAD_RETRIES))
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            try:
                self._hqSoundfontDownloadReady.emit(
                    {
                        "ok": False,
                        "path": target_path,
                        "error": f"Could not prepare download destination:\n{exc}",
                    }
                )
            except RuntimeError:
                return
            return

        try:
            download_file_with_retries(
                url=HQ_SOUNDFONT_URL,
                user_agent=f"{APP_NAME}/{APP_VERSION}",
                target_path=target_path,
                retries=retries,
                timeout_seconds=HQ_SOUNDFONT_DOWNLOAD_TIMEOUT_SECONDS,
                retry_delay_seconds=HQ_SOUNDFONT_DOWNLOAD_RETRY_DELAY_SECONDS,
            )
        except Exception as exc:
            try:
                self._hqSoundfontDownloadReady.emit(
                    {
                        "ok": False,
                        "path": target_path,
                        "error": (
                            "Could not download high quality soundfont after "
                            f"{retries} attempt(s):\n{exc}"
                        ),
                    }
                )
            except RuntimeError:
                return
            return

        try:
            self._hqSoundfontDownloadReady.emit({"ok": True, "path": target_path, "error": ""})
        except RuntimeError:
            return

    def _finish_high_quality_soundfont_download(self, result: dict[str, object]) -> None:
        self._hq_soundfont_download_active = False
        if self._is_shutdown:
            return
        ok = bool(result.get("ok"))
        path_value = result.get("path")
        target_path = path_value if isinstance(path_value, Path) else Path(str(path_value or ""))
        error = str(result.get("error", "")).strip()
        if not ok:
            self.window.show_warning(
                "SoundFont Download Failed",
                error or "Could not download high quality soundfont.",
            )
            return
        self._refresh_instruments()
        self._hq_soundfont_prompt_seen = True
        self._schedule_persist()
        self.window.show_info(
            "SoundFont Downloaded",
            "High quality soundfont downloaded successfully.\n\n"
            f"Saved to:\n{target_path}",
        )

    def _maybe_prompt_high_quality_soundfont(self) -> None:
        if self._is_shutdown or self._hq_soundfont_prompt_seen:
            return
        if not self._keyboard_layout_choice_seen:
            return
        if self._has_high_quality_soundfont():
            self._hq_soundfont_prompt_seen = True
            self._schedule_persist()
            return

        user_fonts = ensure_user_fonts_dir()
        target_path = user_fonts / HQ_SOUNDFONT_FILENAME

        response = self.window.ask_yes_no(
            "Grand Piano SoundFont",
            "Download high quality grand piano SoundFont (~8 MB)?\n\n"
            "This soundfont will be stored in your user soundfonts folder.",
            default_yes=True,
        )
        if response:
            if not self._download_high_quality_soundfont(target_path):
                self.window.show_info(
                    "SoundFont Download",
                    "A SoundFont download is already in progress.",
                )
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
        self._sustain_fade = defaults.sustain_fade
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
        self._keyboard_input_mode = defaults.keyboard_input_mode
        self._keyboard_layout_choice_seen = defaults.keyboard_layout_choice_seen
        self._default_keybind_map_full = self._build_default_keybind_map_full(self._keyboard_input_mode)
        self._custom_keybind_overrides = {}
        self._keybind_committed_map_full = dict(self._default_keybind_map_full)
        self._keybind_staging_map_full = dict(self._default_keybind_map_full)
        self._keybind_edit_active = False
        self._keybind_selected_note = None
        self._keybind_edit_undo_stack.clear()
        self._space_override_off = False
        self._sustain_gate_percent = self._sustain_gate_target()
        self._kps_events.clear()

        self._apply_theme()
        self._apply_ui_state_to_window()
        self.audio_engine.set_master_volume(self._volume)
        self._recording_started_at = 0.0
        self._recording_elapsed_seconds = 0
        self.window.set_recording_elapsed(0)

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
            self._available_program_names = {}
            self._set_bank_preset_options([], [], 0, 0)
        self._refresh_stats_ui()
        self._schedule_persist()

    def _on_mouse_note_pressed(self, base_note: int) -> None:
        if self._tutorial_active or self._keybind_edit_active or self._keyboard_layout_prompt_active:
            return
        self._current_mouse_base_note = int(base_note)
        self._activate_mouse_source(self._current_mouse_base_note)

    def _on_mouse_note_released(self, _base_note: int) -> None:
        if self._tutorial_active or self._keybind_edit_active or self._keyboard_layout_prompt_active:
            return
        self._release_mouse_source()

    def _on_mouse_drag_note_changed(self, base_note: object) -> None:
        if self._tutorial_active or self._keybind_edit_active or self._keyboard_layout_prompt_active:
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

    def _is_main_window_key_context(self, watched: QObject) -> bool:
        if watched is self.window or watched is self.window.piano_widget:
            return True
        if is_descendant_of(watched, self.window):
            return True
        focus = QApplication.focusWidget()
        if focus is None:
            return False
        if focus is self.window or focus is self.window.piano_widget:
            return True
        return is_descendant_of(focus, self.window)

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

        if self._keybind_edit_active and event.type() == QEvent.MouseButtonPress:
            if self._is_main_window_key_context(watched):
                mouse_event = event
                if isinstance(mouse_event, QMouseEvent):
                    target = self.window.event_widget_at_pointer(watched, mouse_event)
                    if not self.window.is_keybind_edit_allowed_target(target):
                        self._on_keybind_edit_action_blocked()
                        mouse_event.accept()
                        return True
                    if is_descendant_of(target, self.window.piano_widget) and self._handle_keybind_mouse_press_event(mouse_event):
                        return True

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
        if self._keyboard_layout_prompt_active:
            return True
        key = int(event.key())
        if self._tutorial_active:
            if key == int(Qt.Key.Key_Escape) and not event.isAutoRepeat():
                self._end_tutorial(completed=False)
            return True
        if self._keybind_edit_active:
            if event.isAutoRepeat():
                return True
            modifiers = event.modifiers()
            if (
                bool(modifiers & Qt.ControlModifier)
                and not bool(modifiers & Qt.AltModifier)
                and int(event.key()) == int(Qt.Key.Key_Z)
            ):
                return self._undo_last_keybind_assignment()
            binding = self._binding_from_key_event(event)
            if binding is None:
                if self._keybind_selected_note is None:
                    self._set_keybind_editor_status("Select a piano key first, then press a combo.")
                return True
            self._assign_binding_to_selected_note(binding)
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
            state_changed = False
            if not self._space_override_off:
                self._space_override_off = True
                state_changed = True
            if state_changed:
                self._apply_sustain_gate_target()
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
        if self._keyboard_layout_prompt_active:
            return True
        key = int(event.key())
        if self._tutorial_active:
            return True
        if self._keybind_edit_active:
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
            state_changed = False
            if self._space_override_off:
                self._space_override_off = False
                state_changed = True
            if state_changed:
                self._apply_sustain_gate_target()
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
        alt = bool(modifiers & Qt.AltModifier)
        native_scan_code = int(event.nativeScanCode())
        if self._keyboard_input_mode == "qwerty":
            mapped = normalize_key_event_qwerty_scancode(
                native_scan_code,
                shift=shift,
                ctrl=ctrl,
                alt=alt,
            )
            if mapped is not None:
                return mapped
        else:
            mapped = normalize_key_event_layout_scancode(
                native_scan_code,
                shift=shift,
                ctrl=ctrl,
                alt=alt,
            )
            if mapped is not None:
                return mapped
        return normalize_key_event(text, key_name, shift=shift, ctrl=ctrl, alt=alt)

    def _handle_keybind_mouse_press_event(self, event: QMouseEvent) -> bool:
        if not self._keybind_edit_active:
            return False
        button = event.button()
        if button == Qt.MouseButton.LeftButton:
            return False
        button_name_map = {
            Qt.MouseButton.RightButton: "right",
            Qt.MouseButton.MiddleButton: "middle",
            Qt.MouseButton.BackButton: "x1",
            Qt.MouseButton.ForwardButton: "x2",
        }
        button_name = button_name_map.get(button, str(button).split(".")[-1])
        modifiers = event.modifiers()
        binding = normalize_mouse_binding(
            button_name,
            shift=bool(modifiers & Qt.ShiftModifier),
            ctrl=bool(modifiers & Qt.ControlModifier),
            alt=bool(modifiers & Qt.AltModifier),
        )
        if binding is None:
            event.accept()
            return True
        if self._keybind_selected_note is None:
            self._set_keybind_editor_status("Select a piano key first, then press a combo.")
            event.accept()
            return True
        self._assign_binding_to_selected_note(binding)
        event.accept()
        return True

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
        source, token, ctrl, shift, alt = binding
        return f"bind:{source}:{token}:{1 if ctrl else 0}:{1 if shift else 0}:{1 if alt else 0}"

    def _apply_transpose(self, base_note: int) -> int:
        return clamp_transposed_note(base_note, self._transpose, self._mode_min, self._mode_max)

    def _audio_note_on_safe(self, midi_note: int, velocity: int) -> None:
        try:
            self.audio_engine.note_on(midi_note, velocity=velocity)
        except Exception:
            return

    def _audio_note_off_safe(self, midi_note: int) -> None:
        try:
            self.audio_engine.note_off(midi_note)
        except Exception:
            return

    def _audio_all_notes_off_safe(self) -> None:
        try:
            self.audio_engine.all_notes_off()
        except Exception:
            return

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
        source, token, _, _, _ = binding_hint
        candidates: list[Binding] = [binding_hint]
        if source == "keyboard":
            for ctrl in (False, True):
                for shift in (False, True):
                    for alt in (False, True):
                        candidate: Binding = (source, token, ctrl, shift, alt)
                        if candidate not in candidates:
                            candidates.append(candidate)
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
        base_notes = self._binding_to_notes.get(binding, ())
        if not base_notes:
            return False
        if binding in self._active_bindings:
            return False

        source = self._source_for_binding(binding)
        self._active_bindings.add(binding)
        source_keys: list[str] = []
        normalized_keycodes = self._normalize_keycodes(keycodes)
        self._register_binding_keycodes(binding, normalized_keycodes)
        for base_note in base_notes:
            sounding_note = self._apply_transpose(base_note)
            source_key = f"{source}:{base_note}"
            source_keys.append(source_key)
            self._source_to_sounding_note[source_key] = sounding_note
            self._activate_note(sounding_note, source_key, velocity=self._velocity)
        self._active_binding_sources[binding] = tuple(source_keys)
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
        sources = self._active_binding_sources.pop(binding, ())
        released = False
        for source in sources:
            sounding_note = self._source_to_sounding_note.pop(source, None)
            if sounding_note is None:
                continue
            self._release_note_source(sounding_note, source)
            released = True
        return released

    def _activate_note(self, note: int, source: str, velocity: int = 100) -> None:
        self._note_lifecycle.activate_note(
            note,
            source,
            velocity,
            note_on=self._audio_note_on_safe,
            record_note_on=lambda midi_note, vel, ts: self._recorder.add_note_on(midi_note, velocity=vel, timestamp=ts),
            set_pressed=self.window.piano_widget.set_pressed,
        )

    def _release_note_source(self, note: int, source: str) -> None:
        effective_sustain = self._effective_sustain_percent()
        self._note_lifecycle.release_note_source(
            note,
            source,
            sustain_percent=effective_sustain,
            sustain_temporarily_off=effective_sustain <= 0,
            stop_note=self._stop_note,
            set_pressed=self.window.piano_widget.set_pressed,
        )

    def _stop_note(self, note: int) -> None:
        self._note_lifecycle.stop_note(
            note,
            note_off=self._audio_note_off_safe,
            record_note_off=lambda midi_note, ts: self._recorder.add_note_off(midi_note, timestamp=ts),
            set_pressed=self.window.piano_widget.set_pressed,
        )

    def _release_all_sustained(self) -> None:
        self._note_lifecycle.release_all_sustained(stop_note=self._stop_note)

    def _sustain_gate_target(self) -> float:
        return 0.0 if self._is_sustain_temporarily_off() else 100.0

    def _sustain_gate_step(self) -> float:
        fade = max(0, min(100, int(self._sustain_fade)))
        if fade <= 0:
            return 100.0
        duration_ms = 12.0 + (float(fade) / 100.0) * 776.0
        return max(0.1, (float(SUSTAIN_TICK_MS) / duration_ms) * 100.0)

    def _effective_sustain_percent(self) -> int:
        base = max(0, min(100, int(self._sustain_percent)))
        gate = max(0.0, min(100.0, float(self._sustain_gate_percent)))
        return max(0, min(100, int(round(base * (gate / 100.0)))))

    def _apply_sustain_gate_target(self) -> bool:
        target = self._sustain_gate_target()
        current = float(self._sustain_gate_percent)
        if self._sustain_fade <= 0:
            if abs(current - target) <= 0.001:
                return False
            previous_effective = self._effective_sustain_percent()
            self._sustain_gate_percent = target
            current_effective = self._effective_sustain_percent()
            if current_effective != previous_effective:
                self._refresh_sustain_deadlines()
            if current_effective <= 0 and self._sustained_notes:
                self._release_all_sustained()
            return True
        return False

    def _advance_sustain_gate(self) -> bool:
        target = self._sustain_gate_target()
        current = float(self._sustain_gate_percent)
        if abs(current - target) <= 0.001:
            return False
        step = self._sustain_gate_step()
        if target > current:
            next_value = min(target, current + step)
        else:
            next_value = max(target, current - step)
        if abs(next_value - current) <= 0.001:
            return False
        previous_effective = self._effective_sustain_percent()
        self._sustain_gate_percent = next_value
        current_effective = self._effective_sustain_percent()
        if current_effective != previous_effective:
            self._refresh_sustain_deadlines()
        if current_effective <= 0 and self._sustained_notes:
            self._release_all_sustained()
        return True

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
        space_was_overridden = self._space_override_off
        previous_gate = float(self._sustain_gate_percent)
        self._active_bindings.clear()
        self._active_binding_sources.clear()
        self._keycode_to_binding.clear()
        self._binding_to_keycodes.clear()
        self._source_to_sounding_note.clear()
        self._current_mouse_base_note = None
        self._space_override_off = False
        self._sustain_gate_percent = self._sustain_gate_target()
        self._note_lifecycle.stop_all_notes(
            recorder_is_recording=self._recorder.is_recording,
            record_note_off=lambda midi_note, ts: self._recorder.add_note_off(midi_note, timestamp=ts),
            set_pressed=self.window.piano_widget.set_pressed,
            all_notes_off=self._audio_all_notes_off_safe,
        )
        if space_was_overridden or abs(previous_gate - self._sustain_gate_percent) > 0.001:
            self._mark_stats_dirty()

    def _refresh_sustain_deadlines(self) -> None:
        effective_sustain = self._effective_sustain_percent()
        self._note_lifecycle.refresh_sustain_deadlines(
            sustain_percent=effective_sustain,
            sustain_temporarily_off=effective_sustain <= 0,
            release_all_sustained=self._release_all_sustained,
        )

    def _record_kps_event(self) -> None:
        now = time.monotonic()
        self._kps_events.append(now)
        trim_kps_events(self._kps_events, KPS_WINDOW_SECONDS, now=now)

    def _collect_stats(self) -> dict[str, str]:
        effective_sustain = self._effective_sustain_percent()
        return collect_stats_values(
            volume=self._volume,
            sustain_percent=effective_sustain,
            sustain_temporarily_off=effective_sustain <= 0,
            transpose=self._transpose,
            note_sources=self._note_sources,
            sustained_notes=self._sustained_notes,
            kps_events=self._kps_events,
            kps_window_seconds=KPS_WINDOW_SECONDS,
            stats_order=STATS_ORDER,
        )

    def _refresh_stats_ui(self) -> None:
        values = self._collect_stats()
        sustain_active = self._effective_sustain_percent() > 0
        self.window.set_stats_values(values, sustain_active=sustain_active)
        self._stats_dirty = False

    def _flush_pending_stats(self) -> None:
        if self._stats_dirty or self._recorder.is_recording or self._kps_events:
            self._refresh_stats_ui()

    def _mark_stats_dirty(self) -> None:
        self._stats_dirty = True
        if not self._stats_refresh_timer.isActive():
            self._stats_refresh_timer.start()

    def _on_stats_tick(self) -> None:
        if self._recorder.is_recording and self._recording_started_at > 0.0:
            elapsed = max(0, int(time.monotonic() - self._recording_started_at))
            if elapsed != self._recording_elapsed_seconds:
                self._recording_elapsed_seconds = elapsed
                self.window.set_recording_elapsed(elapsed)
        if self._stats_dirty or self._recorder.is_recording or self._kps_events:
            self._flush_pending_stats()

    def _on_sustain_tick(self) -> None:
        transition_changed = self._advance_sustain_gate()
        effective_sustain = self._effective_sustain_percent()
        if effective_sustain <= 0:
            if self._sustained_notes:
                self._release_all_sustained()
                self._refresh_stats_ui()
                return
            if transition_changed:
                self._refresh_stats_ui()
            return
        if not self._sustained_notes:
            if transition_changed:
                self._refresh_stats_ui()
            return

        now = time.monotonic()
        expired = [
            note
            for note, deadline in self._sustained_notes.items()
            if deadline is not None and now >= deadline
        ]
        if not expired:
            if transition_changed:
                self._refresh_stats_ui()
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
            sustain_fade=self._sustain_fade,
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
            keyboard_input_mode=self._keyboard_input_mode,
            keyboard_layout_choice_seen=self._keyboard_layout_choice_seen,
            custom_keybinds=serialize_custom_keybind_payload(self._custom_keybind_overrides),
        )
        save_settings(settings, self._settings_path)

    def _maybe_prompt_keyboard_input_mode(self) -> None:
        if self._is_shutdown or self._keyboard_layout_choice_seen:
            return
        app = QApplication.instance()
        platform_name = str(app.platformName() if app is not None else "").strip().lower()
        if platform_name in {"offscreen", "minimal", "minimalegl"}:
            self._apply_keyboard_input_mode("layout", mark_choice_seen=True, persist_now=True)
            return

        choice = self._ask_keyboard_input_mode_choice()
        self._apply_keyboard_input_mode(choice, mark_choice_seen=True, persist_now=True)

    def _on_change_keyboard_layout_requested(self) -> None:
        if self._tutorial_active or self._keybind_edit_active:
            return
        choice = self._ask_keyboard_input_mode_choice()
        self._apply_keyboard_input_mode(choice, mark_choice_seen=True, persist_now=True)

    def _ask_keyboard_input_mode_choice(self) -> str | None:
        self._keyboard_layout_prompt_active = True
        self._stop_all_notes()
        piano_widget = self.window.piano_widget
        was_enabled = bool(piano_widget.isEnabled())
        if was_enabled:
            piano_widget.setEnabled(False)
        try:
            return self.window.ask_keyboard_input_mode_choice()
        finally:
            if was_enabled:
                piano_widget.setEnabled(True)
            self._keyboard_layout_prompt_active = False
            self._stop_all_notes()
            piano_widget.setFocus(Qt.ActiveWindowFocusReason)
            self._refresh_stats_ui()

    def _apply_keyboard_input_mode(self, choice: str | None, *, mark_choice_seen: bool, persist_now: bool) -> None:
        target = "qwerty" if str(choice or "").strip().lower() == "qwerty" else "layout"
        previous = self._keyboard_input_mode
        target_default_keybinds = self._build_default_keybind_map_full(target)
        should_translate = previous != target or target == "layout"
        if should_translate:
            self._stop_all_notes()
            qwerty_defaults = get_mode_mapping("88")
            source_defaults = dict(self._default_keybind_map_full)
            source_to_qwerty = (
                self._build_keyboard_token_map(source_defaults, qwerty_defaults)
                if previous == "layout"
                else {}
            )
            qwerty_to_target = (
                self._build_keyboard_token_map(qwerty_defaults, target_default_keybinds)
                if target == "layout"
                else {}
            )
            translated: dict[int, Binding] = {}
            for note, binding in self._keybind_committed_map_full.items():
                translated[note] = self._translate_keyboard_binding(
                    binding,
                    source_to_qwerty,
                    qwerty_to_target,
                )
            self._keybind_committed_map_full = translated
            self._keybind_staging_map_full = dict(self._keybind_committed_map_full)
            self._default_keybind_map_full = target_default_keybinds
            self._custom_keybind_overrides = extract_custom_keybind_overrides(
                self._default_keybind_map_full,
                self._keybind_committed_map_full,
            )
            self._keyboard_input_mode = target
            self._apply_mode(self._mode, persist=False)
            self._refresh_stats_ui()
        else:
            self._keyboard_input_mode = target
            self._apply_mode(self._mode, persist=False)
            self._refresh_stats_ui()
        if mark_choice_seen:
            self._keyboard_layout_choice_seen = True
        if persist_now:
            self._persist_settings_now()
        else:
            self._schedule_persist()

    def _is_sustain_temporarily_off(self) -> bool:
        if self._hold_space_for_sustain:
            return not self._space_override_off
        return self._space_override_off

    def _trigger_update_check(self, manual: bool) -> None:
        if self._is_shutdown:
            return
        with self._update_lock:
            if self._update_check_active or self._update_install_active:
                if manual:
                    self.window.show_info("Update Check", "An update operation is already in progress.")
                return
            self._update_stop_event.clear()
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
        result: dict[str, object]
        try:
            check = self._update_service.check_for_updates(
                APP_VERSION,
                stop_event=self._update_stop_event,
            )
            if check.update_available:
                result = {
                    "status": "available",
                    "latest": str(check.latest_version or ""),
                    "url": str(check.page_url or ""),
                    "setup_url": str(check.setup_url or ""),
                    "setup_sha256": str(check.setup_sha256 or ""),
                    "setup_size": int(check.setup_size or 0),
                    "released": str(check.released or ""),
                    "notes": list(check.notes or []),
                    "install_supported": bool(check.install_supported),
                    "setup_managed_install": bool(check.setup_managed_install),
                    "channel": str(check.channel or "stable"),
                    "minimum_supported_version": str(check.minimum_supported_version or "1.0.0"),
                    "requires_manual_update": bool(check.requires_manual_update),
                }
            else:
                result = {
                    "status": "up_to_date",
                    "latest": str(check.latest_version or ""),
                    "url": str(check.page_url or ""),
                }
        except Exception as exc:
            result = {"status": "error", "error": str(exc)}
        if self._is_shutdown:
            return
        try:
            self._updateResultReady.emit(manual, result)
        except RuntimeError:
            return

    def _trigger_update_install(self, payload: dict[str, object]) -> None:
        self._update_stop_event.clear()
        with self._update_lock:
            if self._update_install_active:
                return
            self._update_install_active = True
        self.window.show_update_progress(
            "Updating OpenPiano",
            "Preparing update...",
            allow_cancel=True,
        )
        self.window.set_update_progress(0, "Preparing update...")
        worker = threading.Thread(
            target=self._update_install_worker,
            args=(dict(payload),),
            daemon=True,
        )
        worker.start()

    def _update_install_worker(self, payload: dict[str, object]) -> None:
        if self._is_shutdown:
            return
        result: dict[str, object]

        def _progress(percent: int, message: str) -> None:
            if self._is_shutdown:
                return
            try:
                self._updateInstallProgressReady.emit(int(percent), str(message or ""))
            except RuntimeError:
                return

        prepared_update = None
        try:
            prepared_update = self._update_service.prepare_update_from_payload(
                {
                    "update_available": True,
                    "current_version": APP_VERSION,
                    "latest": str(payload.get("latest") or ""),
                    "url": str(payload.get("url") or OFFICIAL_WEBSITE_URL),
                    "setup_url": str(payload.get("setup_url") or ""),
                    "setup_sha256": str(payload.get("setup_sha256") or ""),
                    "setup_size": int(payload.get("setup_size") or 0),
                    "released": str(payload.get("released") or ""),
                    "notes": list(payload.get("notes") or []),
                    "channel": str(payload.get("channel") or "stable"),
                    "minimum_supported_version": str(payload.get("minimum_supported_version") or "1.0.0"),
                    "requires_manual_update": bool(payload.get("requires_manual_update", False)),
                    "setup_managed_install": bool(payload.get("setup_managed_install", False)),
                },
                stop_event=self._update_stop_event,
                progress_callback=_progress,
            )
            if self._is_shutdown:
                return
            self._update_handoff_continue = False
            self._update_handoff_restart = True
            self._update_handoff_event.clear()
            try:
                self._updateInstallHandoffRequested.emit(
                    {
                        "version": str(getattr(prepared_update, "latest_version", "") or payload.get("latest") or ""),
                        "url": str(payload.get("url") or OFFICIAL_WEBSITE_URL),
                        "requires_elevation": bool(getattr(prepared_update, "requires_elevation", False)),
                    }
                )
            except RuntimeError:
                return
            while not self._update_handoff_event.is_set():
                if self._is_shutdown:
                    return
                if self._update_stop_event.is_set():
                    raise InterruptedError("Update operation stopped.")
                time.sleep(0.05)
            if not self._update_handoff_continue:
                if prepared_update is not None:
                    self._update_service.discard_prepared_update(prepared_update)
                result = {
                    "status": "aborted",
                    "url": str(payload.get("url") or OFFICIAL_WEBSITE_URL),
                }
            else:
                self._update_service.launch_prepared_update(
                    prepared_update,
                    restart_after_update=bool(self._update_handoff_restart),
                )
                version = str(getattr(prepared_update, "latest_version", "") or payload.get("latest") or "")
                result = {
                    "status": "ready",
                    "version": str(version or ""),
                    "url": str(payload.get("url") or OFFICIAL_WEBSITE_URL),
                    "restart_after_update": bool(self._update_handoff_restart),
                }
        except InterruptedError:
            if prepared_update is not None:
                try:
                    self._update_service.discard_prepared_update(prepared_update)
                except Exception:
                    pass
            result = {
                "status": "canceled",
                "url": str(payload.get("url") or OFFICIAL_WEBSITE_URL),
            }
        except Exception as exc:
            if prepared_update is not None:
                try:
                    self._update_service.discard_prepared_update(prepared_update)
                except Exception:
                    pass
            result = {
                "status": "error",
                "error": str(exc),
                "url": str(payload.get("url") or OFFICIAL_WEBSITE_URL),
            }
        if self._is_shutdown:
            return
        try:
            self._updateInstallReady.emit(result)
        except RuntimeError:
            return

    def _on_update_install_progress(self, percent: int, message: str) -> None:
        if self._is_shutdown:
            return
        self.window.set_update_progress(int(percent), str(message or ""))

    def _on_update_install_handoff_requested(self, payload: dict[str, object]) -> None:
        if self._is_shutdown:
            self._update_handoff_continue = False
            self._update_handoff_event.set()
            return
        version = str(payload.get("version") or "")
        requires_elevation = bool(payload.get("requires_elevation", False))
        self.window.set_update_progress(99, "Ready to hand off to the installer. Waiting for your confirmation...")
        continue_update, restart_after = self.window.ask_update_handoff(
            version=version,
            default_restart=True,
            requires_elevation=requires_elevation,
        )
        self._update_handoff_continue = bool(continue_update)
        self._update_handoff_restart = bool(restart_after)
        self._update_handoff_event.set()

    def _on_update_progress_canceled(self) -> None:
        if self._is_shutdown:
            return
        with self._update_lock:
            if not self._update_install_active:
                return
        self.window.set_update_progress(0, "Canceling update...")
        self._update_stop_event.set()

    def _finish_update_check(self, manual: bool, result: dict[str, object]) -> None:
        if self._is_shutdown:
            return
        with self._update_lock:
            self._update_check_active = False
        self._update_stop_event.clear()

        status = str(result.get("status", "error"))
        if status == "available":
            latest = str(result.get("latest", ""))
            url = str(result.get("url", "") or OFFICIAL_WEBSITE_URL)
            install_supported = bool(
                result.get("install_supported", False)
                and result.get("setup_url")
                and result.get("setup_sha256")
                and int(result.get("setup_size") or 0) > 0
            )
            requires_manual_update = bool(result.get("requires_manual_update", False))
            if not getattr(sys, "frozen", False):
                install_supported = False
            if requires_manual_update:
                install_supported = False
            notes = [str(item or "").strip() for item in (result.get("notes") or []) if str(item or "").strip()]
            notes_text = ""
            if notes:
                notes_text = "\n\nWhat's new:\n" + "\n".join((f"- {line}" for line in notes[:8]))
            if requires_manual_update:
                minimum_supported = str(result.get("minimum_supported_version") or "1.0.0").strip() or "1.0.0"
                notes_text += (
                    "\n\nYour current version is below the minimum supported "
                    f"auto-update baseline ({minimum_supported})."
                )
            proceed, auto_install = self.window.ask_update_install_preference(
                latest_version=latest,
                details_text=notes_text,
                install_supported=install_supported,
            )
            if proceed:
                if install_supported and auto_install:
                    self._trigger_update_install(result)
                else:
                    QDesktopServices.openUrl(QUrl(url))
            return

        if status == "up_to_date":
            if manual:
                self.window.show_info(
                    "Up to Date",
                    "You are already on the latest version.",
                )
            return

        if manual:
            message = str(result.get("error", "Unknown error"))
            self.window.show_warning(
                "Update Check Failed",
                f"Could not check for updates:\n{message}",
            )

    def _finish_update_install(self, payload: dict[str, object]) -> None:
        if self._is_shutdown:
            return
        with self._update_lock:
            self._update_install_active = False
        self._update_stop_event.clear()
        status = str(payload.get("status", "error"))
        if status == "canceled":
            self.window.close_update_progress()
            self.window.show_info(
                "Update Canceled",
                "Update was canceled before installation started.",
            )
            return
        if status == "aborted":
            self.window.close_update_progress()
            self.window.show_info(
                "Update Canceled",
                "Update was aborted. No installer was launched.",
            )
            return
        if status == "ready":
            version = str(payload.get("version") or "")
            if bool(payload.get("restart_after_update", True)):
                self.window.set_update_progress(
                    100,
                    f"Handing off to installer for v{version or 'latest'} (app will restart after update).",
                )
            else:
                self.window.set_update_progress(
                    100,
                    f"Handing off to installer for v{version or 'latest'}...",
                )
            QTimer.singleShot(250, self.window.close)
            return
        self.window.close_update_progress()
        message = str(payload.get("error", "Unknown error"))
        self.window.show_warning(
            "Update Install Failed",
            f"Could not install update:\n{message}",
        )
        fallback_url = str(payload.get("url") or OFFICIAL_WEBSITE_URL).strip()
        if not fallback_url:
            return
        open_fallback = self.window.ask_yes_no(
            "Update Install Failed",
            "Would you like to open the download page instead?",
            default_yes=True,
        )
        if open_fallback:
            QDesktopServices.openUrl(QUrl(fallback_url))

    @staticmethod
    def _safe_call(action: Callable[[], None]) -> None:
        try:
            action()
        except Exception:
            pass

    def shutdown(self) -> None:
        if self._is_shutdown:
            return
        self._is_shutdown = True
        self._update_stop_event.set()
        self._hq_soundfont_download_active = False
        self._midi_dropdown_refresh_active = False
        with self._update_lock:
            self._update_check_active = False
            self._update_install_active = False

        if self._stats_timer.isActive():
            self._stats_timer.stop()
        if self._stats_refresh_timer.isActive():
            self._stats_refresh_timer.stop()
        if self._sustain_timer.isActive():
            self._sustain_timer.stop()
        if self._save_timer.isActive():
            self._save_timer.stop()

        self._safe_call(self._midi_manager.close)
        self._safe_call(
            lambda: self._record_note_off_for_active_notes()
            if self._recorder.is_recording
            else None
        )
        self._safe_call(
            lambda: self._recorder.stop()
            if self._recorder.is_recording
            else None
        )
        self._recording_started_at = 0.0
        self._recording_elapsed_seconds = 0
        self._safe_call(lambda: self.window.set_recording_elapsed(0))
        self._safe_call(self._stop_all_notes)
        self._safe_call(self.audio_engine.shutdown)
        self._safe_call(self.window.close_update_progress)
        self._safe_call(self._persist_settings_now)

    def run(self) -> None:
        self.window.show()
        QTimer.singleShot(400, self._post_startup_prompts)

    def _post_startup_prompts(self) -> None:
        self._maybe_prompt_keyboard_input_mode()
        self._maybe_prompt_high_quality_soundfont()
