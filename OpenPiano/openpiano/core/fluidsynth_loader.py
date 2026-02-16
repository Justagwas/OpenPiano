from __future__ import annotations

import ctypes.util
import importlib
import os
import sys
from pathlib import Path

from openpiano.core.runtime_paths import executable_dir, project_root

_fluidsynth_module: object | None = None
_fluidsynth_error: Exception | None = None
_dll_dir_handles: dict[str, object] = {}


def candidate_dll_dirs() -> list[Path]:
    candidates: list[Path] = []
    root = project_root()
    if getattr(sys, "frozen", False):
        exe_dir = executable_dir()
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
    for directory in candidate_dll_dirs():
        for name in _candidate_dll_names():
            candidate = directory / name
            if candidate.exists():
                return candidate
    return None


def configure_dll_search_paths() -> list[Path]:
    if sys.platform != "win32":
        return []

    added: list[Path] = []
    for path in candidate_dll_dirs():
        if not path.exists():
            continue
        try:
            if hasattr(os, "add_dll_directory"):
                key = os.path.normcase(str(path.resolve()))
                if key not in _dll_dir_handles:
                    handle = os.add_dll_directory(str(path))
                    if handle is not None:
                        _dll_dir_handles[key] = handle
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


def ensure_fluidsynth_loaded() -> tuple[object | None, Exception | None]:
    global _fluidsynth_module
    global _fluidsynth_error

    if _fluidsynth_module is not None:
        return _fluidsynth_module, None

    module, error = _import_fluidsynth_module()
    if module is None:
        _fluidsynth_error = error
        return None, _fluidsynth_error

    _fluidsynth_module = module
    _fluidsynth_error = None
    return _fluidsynth_module, None
