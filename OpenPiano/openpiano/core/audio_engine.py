
from __future__ import annotations

import ctypes
import sys
from pathlib import Path
from typing import Protocol

from openpiano.core.audio_output import default_output_driver, list_output_drivers, output_profiles
from openpiano.core.audio_levels import normalize_volume, playback_gain
from openpiano.core.audio_processing import start_protected_audio_driver
from openpiano.core.config import DEFAULT_AUDIO_POLYPHONY
from openpiano.core.fluidsynth_loader import (
    candidate_dll_dirs,
    configure_dll_search_paths,
    ensure_fluidsynth_loaded,
)
from openpiano.core.normalize import clamp_int
from openpiano.core.piano_key_release import (
    KEY_RELEASE_BANK, KEY_RELEASE_POLYPHONY, PianoKeyRelease, has_piano_key_release,
    has_piano_release_resonance,
)
from openpiano.core.program_selection import normalize_program_selection
from openpiano.core.piano_room import PianoRoom, has_piano_room
from openpiano.core.soundfont_loading import load_soundfont, dispose_soundfont_loader
from openpiano.core.native_audio import native_audio_library
from openpiano.core.piano_damping import staged_piano_damping
from openpiano.core.soundfont_capabilities import inspect_soundfont
from openpiano.core.native_result import check_native_result, release_native_note

AUDIO_SAMPLE_RATE = 48000
_PROGRAM_CACHE_LIMIT = 16


class AudioEngineProtocol(Protocol):
    
    def note_on(self, midi_note: int, velocity: int = 100) -> None:
        ...

    def note_off(self, midi_note: int) -> None:
        ...

    def key_release(self, midi_note: int) -> None:
        ...

    def set_pedal(self, value: int) -> None:
        ...

    def all_notes_off(self) -> None:
        ...

    def set_master_volume(self, volume: float) -> None:
        ...

    def set_instrument(self, soundfont_path: str, bank: int = 0, preset: int = 0) -> None:
        ...

    def select_program(self, bank: int = 0, preset: int = 0) -> None:
        ...

    def get_available_programs(self) -> dict[int, list[int]]:
        ...

    def get_available_program_names(self) -> dict[int, dict[int, str]]:
        ...

    def get_current_program(self) -> tuple[int, int]:
        ...

    def list_output_drivers(self) -> list[str]:
        ...

    def get_output_driver(self) -> str:
        ...

    def set_output_driver(self, driver: str) -> None:
        ...

    def shutdown(self) -> None:
        ...

class SilentAudioEngine:
    
    def note_on(self, midi_note: int, velocity: int = 100) -> None:
        return

    def note_off(self, midi_note: int) -> None:
        return

    def key_release(self, midi_note: int) -> None:
        return

    def set_pedal(self, value: int) -> None:
        return

    def all_notes_off(self) -> None:
        return

    def set_master_volume(self, volume: float) -> None:
        return

    def set_instrument(self, soundfont_path: str, bank: int = 0, preset: int = 0) -> None:
        return

    def select_program(self, bank: int = 0, preset: int = 0) -> None:
        return

    def get_available_programs(self) -> dict[int, list[int]]:
        return {}

    def get_available_program_names(self) -> dict[int, dict[int, str]]:
        return {}

    def get_current_program(self) -> tuple[int, int]:
        return 0, 0

    def list_output_drivers(self) -> list[str]:
        return list_output_drivers()

    def get_output_driver(self) -> str:
        return default_output_driver()

    def set_output_driver(self, driver: str) -> None:
        return

    def shutdown(self) -> None:
        return


class FluidSynthAudioEngine:

    def __init__(
        self,
        sample_rate: int = AUDIO_SAMPLE_RATE,
        polyphony: int = DEFAULT_AUDIO_POLYPHONY,
        channels: int | None = None,
        *,
        piano_recapture: bool = False,
        piano_half_pedal: bool = False,
        piano_contact_blend: bool = False,
        start_output: bool = True,
    ) -> None:
        if piano_contact_blend and not (piano_recapture and piano_half_pedal):
            raise ValueError('Contact blending requires experimental half-pedal.')
        if piano_half_pedal and not piano_recapture:
            raise ValueError('Half-pedal requires experimental piano recapture.')
        configure_dll_search_paths()
        module, error = ensure_fluidsynth_loaded()
        if module is None:
            expected_dirs = ", ".join(str(path) for path in candidate_dll_dirs())
            raise RuntimeError(
                "pyfluidsynth is required for SoundFont playback. "
                f"Could not import fluidsynth (error: {error}). "
                f"Checked DLL dirs: {expected_dirs}"
            )
        if not hasattr(module, "Synth"):
            module_path = getattr(module, "__file__", "<unknown>")
            raise RuntimeError(f"Incompatible fluidsynth module without Synth API: {module_path}")

        self.sample_rate = int(sample_rate)
        if channels is not None:
            polyphony = channels
        self.polyphony = max(16, int(polyphony))
        self.master_volume = 1.0
        self._fluidsynth_module = module
        self._sfid: int | None = None
        self._soundfont_path: str | None = None
        self._soundfont_capabilities = None
        self._bank = 0
        self._preset = 0
        self._output_driver = self._default_output_driver()
        self._available_programs: dict[int, list[int]] = {}
        self._available_program_names: dict[int, dict[int, str]] = {}
        self._program_cache: dict[
            tuple[str, int, int],
            tuple[dict[int, list[int]], dict[int, dict[int, str]]],
        ] = {}
        self._loaded_soundfont_key: tuple[str, int, int] | None = None
        self._active_notes: set[int] = set()
        self._key_release: PianoKeyRelease | None = None
        self._room: PianoRoom | None = None
        self._pedal_value = 0
        self._piano_recapture_requested = bool(piano_recapture)
        self._piano_half_pedal_requested = bool(piano_half_pedal)
        self._piano_contact_blend_requested = bool(piano_contact_blend)
        self._piano_damping = None
        self._synth = None
        self._closed = False
        self._output_started = False
        self._output_profile = None
        try:
            self._create_synth()
            if start_output:
                self.start_output()
            self._set_gain(self.master_volume)
        except BaseException:
            self.shutdown()
            raise

    def start_output(self) -> None:
        if self._closed:
            raise RuntimeError('Audio engine is closed.')
        if not self._output_started:
            self._output_driver = self._start_synth(self._output_driver)
            self._output_started = True

    def stop_output(self) -> None:
        synth = self._synth
        output = getattr(synth, '_openpiano_output', None)
        device_output = getattr(output, 'device_output', None)
        if device_output is not None:
            device_output.stop()
        driver = getattr(synth, 'audio_driver', None)
        if driver:
            delete_driver = self._fluidsynth_module.cfunc('delete_fluid_audio_driver', None,
                ('driver', ctypes.c_void_p, 1))
            delete_driver(driver)
            synth.audio_driver = None
        self._output_started = False

    def failure_count(self) -> int:
        output = getattr(self._synth, '_openpiano_output', None)
        return output.failure_count() if output is not None else 0

    @staticmethod
    def _default_output_driver() -> str:
        return default_output_driver()

    def list_output_drivers(self) -> list[str]:
        return list_output_drivers(self._fluidsynth_module, self._synth.settings)

    def get_output_driver(self) -> str:
        return self._output_driver

    def _new_synth(self):
        try:
            synth = self._fluidsynth_module.Synth(samplerate=float(self.sample_rate),
                **{'synth.polyphony': max(self.polyphony, KEY_RELEASE_POLYPHONY)})
        except TypeError:
            synth = self._fluidsynth_module.Synth(samplerate=float(self.sample_rate))
        if hasattr(synth, "setting"):
            try:
                synth.setting("synth.polyphony", int(self.polyphony))
            except Exception:
                pass
        return synth

    def _create_synth(self) -> None:
        self._synth = self._new_synth()

    def _start_driver_attempts(self, preferred_driver: str | None) -> list[dict[str, object]]:
        attempts: list[dict[str, object]] = []
        preferred = str(preferred_driver or "").strip().lower()
        if sys.platform == "win32":
            available = self.list_output_drivers()
            ordered = [preferred] if preferred in available else []
            ordered.extend(driver for driver in available if driver != preferred)
            for driver in ordered:
                attempts.extend(output_profiles(driver, native_callback=native_audio_library() is not None))
        attempts.append({})
        return attempts

    def _start_synth_with_kwargs(self, kwargs: dict[str, object]) -> str:
        driver = str(kwargs.get("driver", "")).strip().lower()
        device = str(kwargs.get("device", "")).strip()
        if hasattr(self._synth, "setting"):
            if driver:
                self._synth.setting("audio.driver", driver)
            if device and driver:
                self._synth.setting(f"audio.{driver}.device", device)
            if sys.platform == 'win32':
                self._synth.setting('audio.period-size', int(kwargs.get('period_size', 512)))
                self._synth.setting('audio.periods', int(kwargs.get('periods', 8)))
                self._synth.setting('audio.sample-format', str(kwargs.get('sample_format', '16bits')))
                if driver == 'wasapi':
                    self._synth.setting('audio.wasapi.exclusive-mode', 0)

        create_audio_driver = getattr(self._fluidsynth_module, "new_fluid_audio_driver", None)
        if create_audio_driver is None:
            try:
                legacy_kwargs = {key: value for key, value in kwargs.items() if key in ('driver', 'device')}
                self._synth.start(**legacy_kwargs)
                self._output_profile = dict(kwargs)
                return driver
            except TypeError:
                self._synth.start()
                self._output_profile = {}
                return ""

        if (sys.platform == 'win32' and driver == 'wasapi'
                and not device and kwargs.get('sample_format') == 'float'):
            start_protected_audio_driver(self._fluidsynth_module, self._synth, self.sample_rate,
                                         wasapi_periods=int(kwargs.get('periods', 3)))
        else:
            start_protected_audio_driver(self._fluidsynth_module, self._synth, self.sample_rate)
        self._output_profile = dict(kwargs)
        return driver or str(self._synth.get_setting('audio.driver') or '')

    def _start_synth(self, preferred_driver: str | None = None) -> str:
        last_error: Exception | None = None
        for kwargs in self._start_driver_attempts(preferred_driver):
            try:
                return self._start_synth_with_kwargs(kwargs)
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            raise RuntimeError(f"Failed to start FluidSynth driver: {last_error}") from last_error
        raise RuntimeError("Failed to start FluidSynth driver.")

    @staticmethod
    def _clamp_note(value: int) -> int:
        return clamp_int(value, 0, 127, default=0)

    @staticmethod
    def _clamp_velocity(value: int) -> int:
        return clamp_int(value, 1, 127, default=100)

    @staticmethod
    def _clamp_bank(value: int) -> int:
        return clamp_int(value, 0, 16383, default=0)

    @staticmethod
    def _clamp_preset(value: int) -> int:
        return clamp_int(value, 0, 127, default=0)

    def _set_gain(self, gain: float) -> None:
        if hasattr(self._synth, "set_gain"):
            self._synth.set_gain(gain)
            return
        if hasattr(self._synth, "setting"):
            try:
                self._synth.setting("synth.gain", float(gain))
            except Exception:
                pass

    def set_master_volume(self, volume: float) -> None:
        self.master_volume = normalize_volume(volume)
        self._apply_playback_gain()

    def _apply_playback_gain(self) -> None:
        self._set_gain(playback_gain(self.master_volume, self._soundfont_path, self._bank, self._preset,
            capabilities=getattr(self, '_soundfont_capabilities', None)))

    def set_instrument(self, soundfont_path: str, bank: int = 0, preset: int = 0, *, stop_event=None) -> None:
        sf_path = Path(soundfont_path).expanduser()
        if not sf_path.is_file():
            raise FileNotFoundError(f"SoundFont not found: {sf_path}")
        sf_path = sf_path.resolve()

        target_bank = self._clamp_bank(int(bank))
        target_preset = self._clamp_preset(int(preset))
        cache_key = self._soundfont_cache_key(sf_path)
        if (
            self._sfid is not None
            and self._soundfont_path == str(sf_path)
            and self._loaded_soundfont_key == cache_key
        ):
            self.select_program(target_bank, target_preset)
            return

        new_sfid: int | None = None
        old_sfid = self._sfid
        old_key_release = getattr(self, '_key_release', None)
        old_room = getattr(self, '_room', None)
        old_piano_damping = getattr(self, '_piano_damping', None)
        new_room = None
        new_piano_damping = None
        new_key_release = None
        capabilities = inspect_soundfont(sf_path, stop_event=stop_event)
        release_enabled = has_piano_key_release(sf_path, capabilities=capabilities)
        try:
            new_sfid = int(self._sfload(str(sf_path), capabilities=capabilities, stop_event=stop_event))
            cached = self._program_cache.get(cache_key)
            if cached is None:
                available_programs, available_program_names = self._discover_available_programs(
                    new_sfid,
                    preferred_bank=target_bank,
                )
                self._cache_program_metadata(
                    cache_key,
                    available_programs,
                    available_program_names,
                )
            else:
                available_programs = self._copy_programs(cached[0])
                available_program_names = self._copy_program_names(cached[1])
            if release_enabled:
                available_programs.pop(KEY_RELEASE_BANK, None)
                available_program_names.pop(KEY_RELEASE_BANK, None)
            selected_bank, selected_preset = normalize_program_selection(
                available_programs,
                target_bank,
                target_preset,
            )
            check_native_result(self._synth.program_select(0, new_sfid, selected_bank, selected_preset),
                'select the requested SoundFont program')
            if release_enabled:
                new_key_release = PianoKeyRelease(self._synth, new_sfid, self.polyphony,
                    resonance=has_piano_release_resonance(sf_path, capabilities=capabilities))
            self.all_notes_off()
            if old_room is not None:
                old_room.close()
            if (selected_bank, selected_preset) == (0, 0) and has_piano_room(sf_path, capabilities=capabilities):
                new_room = PianoRoom.create(self._synth, self._fluidsynth_module)
                if new_room is not None:
                    new_room.activate()
            if old_piano_damping is not None:
                old_piano_damping.disable()
            if getattr(self, '_piano_recapture_requested', False):
                new_piano_damping = staged_piano_damping(self._fluidsynth_module,
                    self._synth, self.sample_rate, sf_path, selected_bank, selected_preset,
                    half_pedal=getattr(self, '_piano_half_pedal_requested', False),
                    contact_blend=getattr(self, '_piano_contact_blend_requested', False), capabilities=capabilities)
            capabilities.validate_unchanged()
        except Exception:
            if new_room is not None:
                try:
                    new_room.close()
                except Exception:
                    pass
            if new_sfid is not None:
                try:
                    self._sfunload(new_sfid)
                except Exception:
                    pass
            try:
                if old_sfid is not None:
                    self._synth.program_select(0, old_sfid, self._bank, self._preset)
                if old_key_release is not None:
                    old_key_release.select_program()
                if old_room is not None:
                    old_room.activate()
                if old_piano_damping is not None and not old_piano_damping.enabled:
                    old_piano_damping.activate()
                if hasattr(self._synth, 'setting'):
                    self._synth.setting('synth.polyphony', max(self.polyphony, KEY_RELEASE_POLYPHONY) if old_key_release is not None else self.polyphony)
            except Exception:
                pass
            raise

        self._key_release = new_key_release
        self._room = new_room
        self._piano_damping = new_piano_damping
        if old_key_release is not None and not release_enabled:
            self._synth.setting('synth.polyphony', self.polyphony)
        self._sfid = new_sfid
        self._soundfont_path = str(sf_path)
        self._soundfont_capabilities = capabilities
        self._loaded_soundfont_key = cache_key
        self._bank = selected_bank
        self._preset = selected_preset
        self._available_programs = available_programs
        self._available_program_names = available_program_names
        self._apply_playback_gain()
        if old_sfid is not None and old_sfid != new_sfid:
            try:
                self._sfunload(old_sfid)
            except Exception:
                pass

    def select_program(self, bank: int = 0, preset: int = 0) -> None:
        if self._sfid is None:
            raise RuntimeError("No SoundFont is currently loaded.")
        selected_bank, selected_preset = normalize_program_selection(
            self._available_programs,
            self._clamp_bank(int(bank)),
            self._clamp_preset(int(preset)),
        )
        if (selected_bank, selected_preset) == (self._bank, self._preset):
            return
        result = self._synth.program_select(0, self._sfid, selected_bank, selected_preset)
        check_native_result(result, f'select bank {selected_bank}, preset {selected_preset}')
        self.all_notes_off()
        self._bank = selected_bank
        self._preset = selected_preset
        self._apply_playback_gain()

    def note_on(self, midi_note: int, velocity: int = 100) -> None:
        if self._sfid is None:
            return
        room = getattr(self, '_room', None)
        if room is not None:
            room.resume()
        note = self._clamp_note(midi_note)
        if note in self._active_notes:
            release_native_note(self._synth, 0, note)
        check_native_result(self._synth.noteon(0, note, self._clamp_velocity(velocity)), 'start a note')
        piano = getattr(self, '_piano_damping', None)
        if piano is not None:
            piano.press(note, self._clamp_velocity(velocity))
        self._active_notes.add(note)
        release = getattr(self, '_key_release', None)
        if release is not None:
            release.press(note, self._clamp_velocity(velocity))

    def key_release(self, midi_note: int) -> None:
        piano = getattr(self, '_piano_damping', None)
        if piano is not None:
            piano.key_release(self._clamp_note(midi_note))
        release = getattr(self, '_key_release', None)
        if release is not None:
            release.release(self._clamp_note(midi_note))

    @property
    def piano_recapture_enabled(self) -> bool:
        piano = getattr(self, '_piano_damping', None)
        return piano is not None and piano.enabled

    def recording_piano_preroll(self, now: float):
        return self._piano_damping.recording_preroll(now) if self.piano_recapture_enabled else None

    @property
    def piano_half_pedal_enabled(self) -> bool:
        return self.piano_recapture_enabled and self._piano_damping.half_pedal

    @property
    def piano_contact_blend_enabled(self) -> bool:
        return self.piano_half_pedal_enabled and self._piano_damping.contact_blend

    def set_pedal(self, value: int, *, recapture_owned: bool = True,
                  emit_contacts: bool = True) -> None:
        self._pedal_value = max(0, min(127, int(value)))
        piano = getattr(self, '_piano_damping', None)
        if piano is not None:
            contacts = piano.pedal(self._pedal_value if recapture_owned else 0)
            release = getattr(self, '_key_release', None)
            if release is not None and emit_contacts:
                for note, loss in contacts:
                    release.damp(note, retain=True, damping_loss_db=loss,
                                 contact_strength=piano.contact_strength)

    def note_off(self, midi_note: int) -> None:
        note = self._clamp_note(midi_note)
        was_active = note in self._active_notes
        self._active_notes.discard(note)
        if self._sfid is None:
            return
        self.key_release(note)
        piano = getattr(self, '_piano_damping', None)
        captured = piano is not None and piano.damp(note)
        if not captured:
            release_native_note(self._synth, 0, note)
        release = getattr(self, '_key_release', None)
        if release is not None and was_active:
            loss = piano.damping_loss(note) if captured else None
            release.damp(note, enabled=not captured or loss is not None,
                         retain=captured, damping_loss_db=loss or 0.0,
                         contact_strength=piano.contact_strength if captured else 1.0)

    def all_notes_off(self) -> None:
        self._pedal_value = 0
        for note in list(self._active_notes):
            release_native_note(self._synth, 0, note)
        self._active_notes.clear()
        piano = getattr(self, '_piano_damping', None)
        if piano is not None:
            piano.clear()
        release = getattr(self, '_key_release', None)
        if release is not None:
            release.stop()
        if self._sfid is not None:
            check_native_result(self._synth.cc(0, 120, 0), 'silence the piano')
        room = getattr(self, '_room', None)
        if room is not None:
            room.clear()

    def get_available_programs(self) -> dict[int, list[int]]:
        return {bank: list(presets) for bank, presets in self._available_programs.items()}

    def get_available_program_names(self) -> dict[int, dict[int, str]]:
        return {
            int(bank): {int(preset): str(name) for preset, name in preset_names.items()}
            for bank, preset_names in self._available_program_names.items()
        }

    def get_current_program(self) -> tuple[int, int]:
        return self._bank, self._preset

    def set_output_driver(self, driver: str) -> None:
        requested = str(driver).strip().lower()
        available = self.list_output_drivers()
        target = requested if requested in available else (available[0] if available else '')
        if target == self._output_driver:
            return
        self._replace_output(target)

    def restart_output(self) -> None:
        self._replace_output(self._output_driver)

    def _replace_output(self, target: str) -> None:
        if self._closed:
            raise RuntimeError('Audio engine is closed.')
        previous = self._output_driver
        previous_profile = getattr(self, '_output_profile', None)
        was_started = self._output_started
        self.stop_output()
        try:
            self._output_driver = self._start_synth(target)
            self._output_started = True
        except Exception:
            self._output_driver = previous
            if was_started:
                try:
                    self._output_driver = (self._start_synth_with_kwargs(previous_profile)
                        if previous_profile is not None else self._start_synth(previous))
                    self._output_started = True
                except Exception:
                    self._output_started = False
            raise

    @staticmethod
    def _copy_programs(programs: dict[int, list[int]]) -> dict[int, list[int]]:
        return {int(bank): list(presets) for bank, presets in programs.items()}

    @staticmethod
    def _copy_program_names(names: dict[int, dict[int, str]]) -> dict[int, dict[int, str]]:
        return {
            int(bank): {int(preset): str(name) for preset, name in preset_names.items()}
            for bank, preset_names in names.items()
        }

    @staticmethod
    def _soundfont_cache_key(path: Path) -> tuple[str, int, int]:
        stat = path.stat()
        return str(path), int(stat.st_size), int(stat.st_mtime_ns)

    def _cache_program_metadata(
        self,
        cache_key: tuple[str, int, int],
        programs: dict[int, list[int]],
        names: dict[int, dict[int, str]],
    ) -> None:
        path_key = cache_key[0]
        stale_keys = [
            key
            for key in self._program_cache
            if key[0] == path_key and key != cache_key
        ]
        for stale_key in stale_keys:
            self._program_cache.pop(stale_key, None)
        self._program_cache[cache_key] = (
            self._copy_programs(programs),
            self._copy_program_names(names),
        )
        while len(self._program_cache) > _PROGRAM_CACHE_LIMIT:
            oldest_key = next(iter(self._program_cache))
            self._program_cache.pop(oldest_key, None)

    def _bind_fluidsynth_function(self, name: str, result_type, *arguments):
        existing = getattr(self._fluidsynth_module, name, None)
        if callable(existing):
            return existing
        binder = getattr(self._fluidsynth_module, "cfunc", None)
        if not callable(binder):
            return None
        try:
            return binder(name, result_type, *arguments)
        except Exception:
            return None

    def _discover_programs_by_iteration(
        self,
        sfid: int,
    ) -> tuple[dict[int, list[int]], dict[int, dict[int, str]]] | None:
        get_sfont = self._bind_fluidsynth_function(
            "fluid_synth_get_sfont_by_id",
            ctypes.c_void_p,
            ("synth", ctypes.c_void_p, 1),
            ("id", ctypes.c_int, 1),
        )
        iteration_start = self._bind_fluidsynth_function(
            "fluid_sfont_iteration_start",
            None,
            ("sfont", ctypes.c_void_p, 1),
        )
        iteration_next = self._bind_fluidsynth_function(
            "fluid_sfont_iteration_next",
            ctypes.c_void_p,
            ("sfont", ctypes.c_void_p, 1),
        )
        get_bank = self._bind_fluidsynth_function(
            "fluid_preset_get_banknum",
            ctypes.c_int,
            ("preset", ctypes.c_void_p, 1),
        )
        get_number = self._bind_fluidsynth_function(
            "fluid_preset_get_num",
            ctypes.c_int,
            ("preset", ctypes.c_void_p, 1),
        )
        get_name = self._bind_fluidsynth_function(
            "fluid_preset_get_name",
            ctypes.c_char_p,
            ("preset", ctypes.c_void_p, 1),
        )
        if not all(callable(item) for item in (get_sfont, iteration_start, iteration_next, get_bank, get_number)):
            return None
        synth_pointer = getattr(self._synth, "synth", None)
        if synth_pointer is None:
            return None
        try:
            sfont = get_sfont(synth_pointer, sfid)
            if not sfont:
                return None
            iteration_start(sfont)
            programs: dict[int, list[int]] = {}
            names: dict[int, dict[int, str]] = {}
            for _ in range(65536):
                preset_pointer = iteration_next(sfont)
                if not preset_pointer:
                    break
                bank = self._clamp_bank(int(get_bank(preset_pointer)))
                preset = self._clamp_preset(int(get_number(preset_pointer)))
                programs.setdefault(bank, []).append(preset)
                if callable(get_name):
                    raw_name = get_name(preset_pointer)
                    if isinstance(raw_name, bytes):
                        label = raw_name.decode("latin-1", errors="replace").strip()
                    else:
                        label = str(raw_name or "").strip()
                    if label:
                        names.setdefault(bank, {})[preset] = label
            else:
                return None
            if not programs:
                return None
            return programs, names
        except Exception:
            return None

    def _discover_available_programs(
        self,
        sfid: int,
        preferred_bank: int = 0,
    ) -> tuple[dict[int, list[int]], dict[int, dict[int, str]]]:
        iterated = self._discover_programs_by_iteration(sfid)
        if iterated is not None:
            available, names = iterated
            return self._normalize_discovered_programs(available, names)

        available: dict[int, list[int]] = {}
        names: dict[int, dict[int, str]] = {}
        preferred_bank = self._clamp_bank(int(preferred_bank))
        max_bank = max(255, min(16383, preferred_bank + 64))
        empty_bank_run = 0
        found_any = False
        for bank in range(max_bank + 1):
            presets, preset_names = self._discover_bank_presets(sfid, bank)
            if presets:
                available[bank] = presets
                if preset_names:
                    names[bank] = preset_names
                found_any = True
                empty_bank_run = 0
            else:
                empty_bank_run += 1
            if found_any and bank >= max(preferred_bank, 127) and empty_bank_run >= 64:
                break
        return self._normalize_discovered_programs(available, names)

    @staticmethod
    def _normalize_discovered_programs(
        available: dict[int, list[int]],
        names: dict[int, dict[int, str]],
    ) -> tuple[dict[int, list[int]], dict[int, dict[int, str]]]:
        normalized_programs: dict[int, list[int]] = {}
        normalized_names: dict[int, dict[int, str]] = {}
        for bank, presets in available.items():
            deduped_presets = sorted(set(presets))
            if not deduped_presets:
                continue
            normalized_programs[bank] = deduped_presets
            bank_names = names.get(bank, {})
            if not bank_names:
                continue
            filtered_names = {
                int(preset): str(name)
                for preset, name in bank_names.items()
                if int(preset) in deduped_presets and str(name).strip()
            }
            if filtered_names:
                normalized_names[bank] = filtered_names
        return normalized_programs, normalized_names

    def _discover_bank_presets(self, sfid: int, bank: int) -> tuple[list[int], dict[int, str]]:
        presets: list[int] = []
        names: dict[int, str] = {}
        sfpreset_name = getattr(self._synth, "sfpreset_name", None)
        if callable(sfpreset_name):
            for preset in range(128):
                name = self._safe_sfpreset_name(sfid, bank, preset)
                if name:
                    presets.append(preset)
                    names[preset] = name
            return presets, names

        program_select = getattr(self._synth, "program_select", None)
        if callable(program_select):
            for preset in range(128):
                if self._safe_program_exists(sfid, bank, preset):
                    presets.append(preset)
        return presets, names

    def _safe_sfpreset_name(self, sfid: int, bank: int, preset: int) -> str | None:
        try:
            name = self._synth.sfpreset_name(sfid, bank, preset)
        except Exception:
            return None
        if name is None:
            return None
        if isinstance(name, bytes):
            try:
                name = name.decode("utf-8", errors="ignore")
            except Exception:
                name = ""
        text = str(name).strip()
        return text or None

    def _safe_program_exists(self, sfid: int, bank: int, preset: int) -> bool:
        try:
            result = self._synth.program_select(0, sfid, bank, preset)
        except Exception:
            return False

        if result is None:
            return False
        try:
            return int(result) >= 0
        except Exception:
            return bool(result)

    def _sfload(self, soundfont_path: str, *, capabilities=None, stop_event=None) -> int:
        return load_soundfont(self._synth, soundfont_path, module=self._fluidsynth_module,
            capabilities=capabilities, stop_event=stop_event)

    def _sfunload(self, sfid: int) -> None:
        try:
            check_native_result(self._synth.sfunload(sfid, update_midi_preset=False), 'unload the SoundFont')
            return
        except TypeError:
            pass
        try:
            check_native_result(self._synth.sfunload(sfid, False), 'unload the SoundFont')
            return
        except TypeError:
            check_native_result(self._synth.sfunload(sfid), 'unload the SoundFont')

    def shutdown(self) -> None:
        if getattr(self, '_closed', False):
            return
        synth = self._synth
        if synth is None:
            self._closed = True
            return
        self.stop_output()
        self._closed = True
        try:
            self.all_notes_off()
        except Exception:
            pass
        try:
            if self._sfid is not None:
                self._sfunload(self._sfid)
                self._sfid = None
            self._soundfont_path = None
            self._soundfont_capabilities = None
            self._key_release = None
            self._room = None
            self._piano_damping = None
            self._loaded_soundfont_key = None
            self._available_programs = {}
            self._available_program_names = {}
        except Exception:
            pass
        synth.delete()
        dispose_soundfont_loader(synth)
        output = getattr(synth, '_openpiano_output', None)
        if output is not None:
            output.close()
            synth._openpiano_output = None
        for owner in getattr(synth, '_openpiano_piano_owners', ()):
            owner.close()
        self._synth = None
