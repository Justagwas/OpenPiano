
from __future__ import annotations

import ctypes.util
import importlib
import os
import sys
from pathlib import Path
from typing import Protocol

AUDIO_SAMPLE_RATE = 44100
AUDIO_CHANNEL_COUNT = 128

_fluidsynth_module = None
_fluidsynth_error: Exception | None = None


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

    def get_available_programs(self) -> dict[int, list[int]]:
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


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _candidate_dll_dirs() -> list[Path]:
    candidates: list[Path] = []
    root = _project_root()
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.extend([exe_dir / "fluidsynth", exe_dir])
    candidates.append(root / "third_party" / "fluidsynth" / "bin")
    deduped: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        key = os.path.normcase(str(path))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(path)
    return deduped


def _candidate_dll_names() -> tuple[str, ...]:
    return (
        "libfluidsynth-3.dll",
        "libfluidsynth-2.dll",
        "libfluidsynth-1.dll",
        "libfluidsynth.dll",
        "fluidsynth.dll",
    )


def _find_local_fluidsynth_dll() -> Path | None:
    for directory in _candidate_dll_dirs():
        for name in _candidate_dll_names():
            candidate = directory / name
            if candidate.exists():
                return candidate
    return None


def configure_fluidsynth_dll_search_paths() -> list[Path]:
    if sys.platform != "win32":
        return []

    added: list[Path] = []
    for path in _candidate_dll_dirs():
        if not path.exists():
            continue
        try:
            if hasattr(os, "add_dll_directory"):
                os.add_dll_directory(str(path))
        except Exception:
            pass

        current_path = os.environ.get("PATH", "")
        parts = current_path.split(os.pathsep) if current_path else []
        if str(path) not in parts:
            os.environ["PATH"] = f"{path}{os.pathsep}{current_path}" if current_path else str(path)
        added.append(path)
    return added


def _import_fluidsynth_module() -> tuple[object | None, Exception | None]:
    local_dll = _find_local_fluidsynth_dll()
    original_find_library = ctypes.util.find_library
    original_add = getattr(os, "add_dll_directory", None)

    def patched_find_library(name: str) -> str | None:
        normalized = str(name).lower()
        if local_dll is not None and normalized in {
            "fluidsynth",
            "libfluidsynth",
            "libfluidsynth-1",
            "libfluidsynth-2",
            "libfluidsynth-3",
        }:
            return str(local_dll)
        return original_find_library(name)

    def safe_add_dll_directory(path: str) -> object | None:
        if original_add is None:
            return None
        try:
            return original_add(path)
        except FileNotFoundError:
            return None

    try:
        ctypes.util.find_library = patched_find_library                            
        if original_add is not None:
            os.add_dll_directory = safe_add_dll_directory                            
        module = importlib.import_module("fluidsynth")
        return module, None
    except Exception as exc:
        return None, exc
    finally:
        ctypes.util.find_library = original_find_library                            
        if original_add is not None:
            os.add_dll_directory = original_add                            


def _ensure_fluidsynth_loaded() -> None:
    global _fluidsynth_module
    global _fluidsynth_error
    if _fluidsynth_module is not None:
        return

    module, error = _import_fluidsynth_module()
    if module is None:
        _fluidsynth_error = error
        return
    _fluidsynth_module = module
    _fluidsynth_error = None


class SilentAudioEngine:
    
    def note_on(self, midi_note: int, velocity: int = 100) -> None:
        _ = (midi_note, velocity)

    def note_off(self, midi_note: int) -> None:
        _ = midi_note

    def all_notes_off(self) -> None:
        return

    def set_master_volume(self, volume: float) -> None:
        _ = volume

    def set_instrument(self, soundfont_path: str, bank: int = 0, preset: int = 0) -> None:
        _ = (soundfont_path, bank, preset)

    def get_available_programs(self) -> dict[int, list[int]]:
        return {}

    def get_current_program(self) -> tuple[int, int]:
        return 0, 0

    def list_output_drivers(self) -> list[str]:
        return ["dsound", "winmme", "wasapi"] if sys.platform == "win32" else []

    def get_output_driver(self) -> str:
        return "dsound" if sys.platform == "win32" else ""

    def set_output_driver(self, driver: str) -> None:
        _ = driver

    def shutdown(self) -> None:
        return


class FluidSynthAudioEngine:
    
    def __init__(self, sample_rate: int = AUDIO_SAMPLE_RATE, channels: int = AUDIO_CHANNEL_COUNT) -> None:
        configure_fluidsynth_dll_search_paths()
        _ensure_fluidsynth_loaded()
        if _fluidsynth_module is None:
            expected_dirs = ", ".join(str(path) for path in _candidate_dll_dirs())
            raise RuntimeError(
                "pyfluidsynth is required for SoundFont playback. "
                f"Could not import fluidsynth (error: {_fluidsynth_error}). "
                f"Checked DLL dirs: {expected_dirs}"
            )
        if not hasattr(_fluidsynth_module, "Synth"):
            module_path = getattr(_fluidsynth_module, "__file__", "<unknown>")
            raise RuntimeError(f"Incompatible fluidsynth module without Synth API: {module_path}")

        self.sample_rate = int(sample_rate)
        self.channels = max(16, int(channels))
        self.master_volume = 1.0
        self._sfid: int | None = None
        self._soundfont_path: str | None = None
        self._bank = 0
        self._preset = 0
        self._output_driver = self._default_output_driver()
        self._available_programs: dict[int, list[int]] = {}
        self._active_notes: set[int] = set()
        self._synth = _fluidsynth_module.Synth(samplerate=float(self.sample_rate))
                                                                                
        if hasattr(self._synth, "setting"):
            try:
                self._synth.setting("synth.polyphony", int(self.channels))
            except Exception:
                pass
        self._output_driver = self._start_synth(self._output_driver)
        self._set_gain(self.master_volume)

    @staticmethod
    def _default_output_driver() -> str:
        if sys.platform == "win32":
            return "dsound"
        return ""

    def list_output_drivers(self) -> list[str]:
        if sys.platform == "win32":
            return ["dsound", "winmme", "wasapi"]
        return []

    def get_output_driver(self) -> str:
        return self._output_driver

    def _start_synth(self, preferred_driver: str | None = None) -> str:
        attempts: list[dict[str, str]] = []
        preferred = str(preferred_driver or "").strip().lower()
        if sys.platform == "win32":
            ordered = [preferred] if preferred else []
            ordered.extend(driver for driver in self.list_output_drivers() if driver and driver != preferred)
            attempts.extend([{"driver": driver} for driver in ordered if driver])
        attempts.append({})

        last_error: Exception | None = None
        selected = ""
        for kwargs in attempts:
            try:
                self._synth.start(**kwargs)
                selected = str(kwargs.get("driver", "")).strip().lower()
                return selected
            except TypeError:
                try:
                    self._synth.start()
                    selected = str(kwargs.get("driver", "")).strip().lower()
                    return selected
                except Exception as exc:
                    last_error = exc
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            raise RuntimeError(f"Failed to start FluidSynth driver: {last_error}") from last_error
        raise RuntimeError("Failed to start FluidSynth driver.")

    @staticmethod
    def _clamp_note(value: int) -> int:
        return max(0, min(127, int(value)))

    @staticmethod
    def _clamp_velocity(value: int) -> int:
        return max(1, min(127, int(value)))

    @staticmethod
    def _clamp_bank(value: int) -> int:
        return max(0, min(16383, int(value)))

    @staticmethod
    def _clamp_preset(value: int) -> int:
        return max(0, min(127, int(value)))

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
        clamped = max(0.0, min(1.0, float(volume)))
        self.master_volume = clamped
        self._set_gain(clamped)

    def set_instrument(self, soundfont_path: str, bank: int = 0, preset: int = 0) -> None:
        sf_path = Path(soundfont_path)
        if not sf_path.exists():
            raise FileNotFoundError(f"SoundFont not found: {sf_path}")

        target_bank = self._clamp_bank(int(bank))
        target_preset = self._clamp_preset(int(preset))

        new_sfid: int | None = None
        old_sfid = self._sfid
        try:
            new_sfid = int(self._sfload(str(sf_path)))
            available_programs = self._discover_available_programs(new_sfid, preferred_bank=target_bank)
            selected_bank, selected_preset = self._resolve_program_selection(
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
        self._bank = selected_bank
        self._preset = selected_preset
        self._available_programs = available_programs
        if old_sfid is not None and old_sfid != new_sfid:
            try:
                self._sfunload(old_sfid)
            except Exception:
                pass

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

    def get_current_program(self) -> tuple[int, int]:
        return self._bank, self._preset

    def set_output_driver(self, driver: str) -> None:
        requested = str(driver).strip().lower()
        available = self.list_output_drivers()
        target = requested if requested in available else (available[0] if available else "")
        if target == self._output_driver:
            return

        soundfont_path = self._soundfont_path
        bank = self._bank
        preset = self._preset
        master_volume = self.master_volume

        self.all_notes_off()
        try:
            self._synth.delete()
        except Exception:
            pass

        self._synth = _fluidsynth_module.Synth(samplerate=float(self.sample_rate))
        if hasattr(self._synth, "setting"):
            try:
                self._synth.setting("synth.polyphony", int(self.channels))
            except Exception:
                pass
        self._output_driver = self._start_synth(target)
        self._set_gain(master_volume)
        self._active_notes.clear()
        self._sfid = None
        self._available_programs = {}

        if soundfont_path and Path(soundfont_path).exists():
            self.set_instrument(soundfont_path, bank=bank, preset=preset)
        self.set_master_volume(master_volume)

    @staticmethod
    def _nearest_value(candidates: list[int], value: int) -> int:
        if not candidates:
            return value
        return min(candidates, key=lambda item: abs(item - value))

    def _resolve_program_selection(
        self,
        available_programs: dict[int, list[int]],
        requested_bank: int,
        requested_preset: int,
    ) -> tuple[int, int]:
        if not available_programs:
            return requested_bank, requested_preset

        banks = sorted(available_programs.keys())
        selected_bank = (
            requested_bank
            if requested_bank in available_programs
            else self._nearest_value(banks, requested_bank)
        )
        presets = sorted(available_programs.get(selected_bank, []))
        if not presets:
            return selected_bank, requested_preset
        selected_preset = (
            requested_preset
            if requested_preset in presets
            else self._nearest_value(presets, requested_preset)
        )
        return selected_bank, selected_preset

    def _discover_available_programs(self, sfid: int, preferred_bank: int = 0) -> dict[int, list[int]]:
        available: dict[int, list[int]] = {}
        preferred_bank = self._clamp_bank(int(preferred_bank))
        max_bank = max(255, min(16383, preferred_bank + 64))
        empty_bank_run = 0
        found_any = False

        for bank in range(0, max_bank + 1):
            presets = self._discover_bank_presets(sfid, bank)
            if presets:
                available[bank] = presets
                found_any = True
                empty_bank_run = 0
            else:
                empty_bank_run += 1
            if found_any and bank >= max(preferred_bank, 127) and empty_bank_run >= 64:
                break

        if preferred_bank not in available:
            preferred_presets = self._discover_bank_presets(sfid, preferred_bank)
            if preferred_presets:
                available[preferred_bank] = preferred_presets

        return {bank: sorted(set(presets)) for bank, presets in available.items() if presets}

    def _discover_bank_presets(self, sfid: int, bank: int) -> list[int]:
        presets: list[int] = []
        sfpreset_name = getattr(self._synth, "sfpreset_name", None)
        if callable(sfpreset_name):
            for preset in range(128):
                name = self._safe_sfpreset_name(sfid, bank, preset)
                if name:
                    presets.append(preset)
            return presets

        program_select = getattr(self._synth, "program_select", None)
        if callable(program_select):
            for preset in range(128):
                if self._safe_program_exists(sfid, bank, preset):
                    presets.append(preset)
        return presets

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
            self._available_programs = {}
        except Exception:
            pass
        try:
            self._synth.delete()
        except Exception:
            pass
