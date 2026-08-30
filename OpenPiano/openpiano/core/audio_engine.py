
from __future__ import annotations

import ctypes
import sys
from pathlib import Path
from typing import Protocol

from openpiano.core.audio_output import default_output_driver, list_output_drivers
from openpiano.core.fluidsynth_loader import (
    candidate_dll_dirs,
    configure_dll_search_paths,
    ensure_fluidsynth_loaded,
)
from openpiano.core.normalize import clamp_float, clamp_int
from openpiano.core.program_selection import normalize_program_selection

AUDIO_SAMPLE_RATE = 44100
DEFAULT_AUDIO_POLYPHONY = 128
_PROGRAM_CACHE_LIMIT = 16


class AudioEngineProtocol(Protocol):
    
    def note_on(self, midi_note: int, velocity: int = 100) -> None:
        ...

    def note_off(self, midi_note: int) -> None:
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
    ) -> None:
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
        self._create_synth()
        self._output_driver = self._start_synth(self._output_driver)
        self._set_gain(self.master_volume)

    @staticmethod
    def _default_output_driver() -> str:
        return default_output_driver()

    def list_output_drivers(self) -> list[str]:
        return list_output_drivers()

    def get_output_driver(self) -> str:
        return self._output_driver

    def _new_synth(self):
        synth = self._fluidsynth_module.Synth(samplerate=float(self.sample_rate))
        if hasattr(synth, "setting"):
            try:
                synth.setting("synth.polyphony", int(self.polyphony))
            except Exception:
                pass
        return synth

    def _create_synth(self) -> None:
        self._synth = self._new_synth()

    def _start_driver_attempts(self, preferred_driver: str | None) -> list[dict[str, str]]:
        attempts: list[dict[str, str]] = []
        preferred = str(preferred_driver or "").strip().lower()
        if sys.platform == "win32":
            ordered = [preferred] if preferred else []
            ordered.extend(driver for driver in self.list_output_drivers() if driver and driver != preferred)
            attempts.extend([{"driver": driver} for driver in ordered if driver])
        attempts.append({})
        return attempts

    def _start_synth_with_kwargs(self, kwargs: dict[str, str]) -> str:
        driver = str(kwargs.get("driver", "")).strip().lower()
        device = str(kwargs.get("device", "")).strip()
        if hasattr(self._synth, "setting"):
            if driver:
                self._synth.setting("audio.driver", driver)
            if device and driver:
                self._synth.setting(f"audio.{driver}.device", device)

        create_audio_driver = getattr(self._fluidsynth_module, "new_fluid_audio_driver", None)
        if create_audio_driver is None:
            try:
                self._synth.start(**kwargs)
                return driver
            except TypeError:
                self._synth.start()
                return ""

        self._synth.audio_driver = create_audio_driver(self._synth.settings, self._synth.synth)
        if not self._synth.audio_driver:
            raise RuntimeError(f"Could not start FluidSynth audio driver '{driver or 'default'}'.")
        return driver

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
        clamped = clamp_float(volume, 0.0, 1.0, default=1.0)
        self.master_volume = clamped
        self._set_gain(clamped)

    def set_instrument(self, soundfont_path: str, bank: int = 0, preset: int = 0) -> None:
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
        try:
            new_sfid = int(self._sfload(str(sf_path)))
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
            selected_bank, selected_preset = normalize_program_selection(
                available_programs,
                target_bank,
                target_preset,
            )
            self._synth.program_select(0, new_sfid, selected_bank, selected_preset)
        except Exception:
            if new_sfid is not None:
                try:
                    self._sfunload(new_sfid)
                except Exception:
                    pass
            raise

        self.all_notes_off()
        self._sfid = new_sfid
        self._soundfont_path = str(sf_path)
        self._loaded_soundfont_key = cache_key
        self._bank = selected_bank
        self._preset = selected_preset
        self._available_programs = available_programs
        self._available_program_names = available_program_names
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
        self.all_notes_off()
        result = self._synth.program_select(0, self._sfid, selected_bank, selected_preset)
        if result is not None:
            try:
                if int(result) < 0:
                    raise RuntimeError(
                        f"FluidSynth could not select bank {selected_bank}, preset {selected_preset}."
                    )
            except (TypeError, ValueError):
                pass
        self._bank = selected_bank
        self._preset = selected_preset

    def note_on(self, midi_note: int, velocity: int = 100) -> None:
        if self._sfid is None:
            return
        note = self._clamp_note(midi_note)
        if note in self._active_notes:
            self._synth.noteoff(0, note)
        self._synth.noteon(0, note, self._clamp_velocity(velocity))
        self._active_notes.add(note)

    def note_off(self, midi_note: int) -> None:
        note = self._clamp_note(midi_note)
        self._active_notes.discard(note)
        if self._sfid is None:
            return
        self._synth.noteoff(0, note)

    def all_notes_off(self) -> None:
        for note in list(self._active_notes):
            self._synth.noteoff(0, note)
        self._active_notes.clear()
        if self._sfid is not None:
            self._synth.cc(0, 123, 0)

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
        target = requested if requested in available else (available[0] if available else "")
        if target == self._output_driver:
            return

        old_synth = self._synth
        old_output_driver = self._output_driver
        old_sfid = self._sfid
        old_soundfont_path = self._soundfont_path
        old_loaded_soundfont_key = self._loaded_soundfont_key
        old_bank = self._bank
        old_preset = self._preset
        old_programs = self._available_programs
        old_program_names = self._available_program_names
        old_active_notes = set(self._active_notes)
        candidate = self._new_synth()
        try:
            self._synth = candidate
            self._sfid = None
            self._soundfont_path = None
            self._loaded_soundfont_key = None
            self._available_programs = {}
            self._available_program_names = {}
            self._active_notes = set()
            candidate_driver = self._start_synth(target)
            self._set_gain(self.master_volume)
            if old_soundfont_path and Path(old_soundfont_path).is_file():
                self.set_instrument(old_soundfont_path, bank=old_bank, preset=old_preset)
        except Exception:
            try:
                candidate.delete()
            except Exception:
                pass
            self._synth = old_synth
            self._output_driver = old_output_driver
            self._sfid = old_sfid
            self._soundfont_path = old_soundfont_path
            self._loaded_soundfont_key = old_loaded_soundfont_key
            self._bank = old_bank
            self._preset = old_preset
            self._available_programs = old_programs
            self._available_program_names = old_program_names
            self._active_notes = old_active_notes
            raise

        for note in old_active_notes:
            try:
                old_synth.noteoff(0, note)
            except Exception:
                pass
        try:
            if old_sfid is not None:
                try:
                    old_synth.sfunload(old_sfid, update_midi_preset=False)
                except TypeError:
                    old_synth.sfunload(old_sfid)
        except Exception:
            pass
        try:
            old_synth.delete()
        except Exception:
            pass
        self._output_driver = candidate_driver

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
        # A replaced file at the same path supersedes its old metadata. Keeping
        # one entry per path also prevents repeated in-place edits from growing
        # the cache indefinitely.
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

    def _sfload(self, soundfont_path: str) -> int:
        try:
            return int(self._synth.sfload(soundfont_path, reset_presets=False))
        except TypeError:
            pass
        try:
            return int(self._synth.sfload(soundfont_path, False))
        except TypeError:
            return int(self._synth.sfload(soundfont_path))

    def _sfunload(self, sfid: int) -> None:
        try:
            self._synth.sfunload(sfid, update_midi_preset=False)
            return
        except TypeError:
            pass
        try:
            self._synth.sfunload(sfid, False)
            return
        except TypeError:
            self._synth.sfunload(sfid)

    def shutdown(self) -> None:
        try:
            self.all_notes_off()
        except Exception:
            pass
        try:
            if self._sfid is not None:
                self._sfunload(self._sfid)
                self._sfid = None
            self._soundfont_path = None
            self._loaded_soundfont_key = None
            self._available_programs = {}
            self._available_program_names = {}
        except Exception:
            pass
        try:
            self._synth.delete()
        except Exception:
            pass
