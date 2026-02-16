from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def executable_dir() -> Path:
    return Path(sys.executable).resolve().parent


def frozen_bundle_dir() -> Path | None:
    if not getattr(sys, "frozen", False):
        return None
    meipass = getattr(sys, "_MEIPASS", "")
    if not meipass:
        return None
    return Path(meipass)


def resource_root() -> Path:
    bundle = frozen_bundle_dir()
    if bundle is not None:
        return bundle
    return project_root()


def app_local_data_dir(app_name: str) -> Path | None:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        return None
    return Path(local_app_data) / str(app_name or "").strip()


def icon_path_candidates(*, icon_name: str = "icon.ico", extra_dirs: Iterable[Path] | None = None) -> list[Path]:
    name = str(icon_name or "icon.ico").strip() or "icon.ico"
    candidates: list[Path] = []

    bundle = frozen_bundle_dir()
    if bundle is not None:
        candidates.append(bundle / name)
    if getattr(sys, "frozen", False):
        candidates.append(executable_dir() / name)

    for directory in extra_dirs or ():
        candidates.append(Path(directory) / name)

    return candidates
