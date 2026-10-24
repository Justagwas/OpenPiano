"""
OpenPiano - Virtual Piano for Windows

Copyright 2026 Justagwas

This program is licensed under the GNU General Public License v3.0
See the LICENSE file in the project root for the full license text.

Official Project Page:
https://justagwas.com/projects/openpiano

Official Source Code:
https://github.com/justagwas/openpiano
https://sourceforge.net/projects/openpiano

SPDX-License-Identifier: GPL-3.0-or-later
"""
from __future__ import annotations

import ctypes
import os
import signal
import sys
from pathlib import Path

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from openpiano.core.config import APP_NAME
from openpiano.core.runtime_paths import icon_path_candidates


class SingleInstanceGuard:
    def __init__(self, mutex_name: str) -> None:
        self._mutex_name = str(mutex_name or "").strip() or "OpenPianoMutex"
        self._handle = None

    def acquire(self) -> bool:
        if os.name != "nt":
            return True
        try:
            kernel32 = ctypes.windll.kernel32
            kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_wchar_p]
            kernel32.CreateMutexW.restype = ctypes.c_void_p
            handle = kernel32.CreateMutexW(None, 0, self._mutex_name)
            if not handle:
                return False
            error_already_exists = 183
            if kernel32.GetLastError() == error_already_exists:
                kernel32.CloseHandle(handle)
                return False
            self._handle = handle
            return True
        except Exception:
            return True

    def release(self) -> None:
        if os.name != "nt":
            return
        if self._handle is None:
            return
        try:
            ctypes.windll.kernel32.CloseHandle(self._handle)
        except Exception:
            pass      
        self._handle = None


def _resolve_icon_path() -> Path | None:
    candidates = icon_path_candidates(extra_dirs=[Path(__file__).resolve().parent])
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    signal.signal(signal.SIGINT, lambda _signum, _frame: app.exit(130))
    icon_path = _resolve_icon_path()
    if icon_path is not None:
        app.setWindowIcon(QIcon(str(icon_path)))
    instance_guard = SingleInstanceGuard("OpenPianoMutex")
    if not instance_guard.acquire():
        QMessageBox.information(
            None,
            APP_NAME,
            "OpenPiano is already running.",
        )
        return 0

    controller = None
    splash = None
    try:
        from openpiano.ui.loading_splash import create_loading_splash
        splash = create_loading_splash(APP_NAME)
        splash.show()
        app.processEvents()
        from openpiano.app_controller import PianoAppController
        controller = PianoAppController(app, icon_path=icon_path, startup_status=splash.set_status)
        splash.close()
        controller.run()
        from PySide6.QtCore import QTimer
        from openpiano.ui.update_dialog import show_update_completion
        QTimer.singleShot(0, controller.window, lambda: show_update_completion(controller.window))
        try:
            return app.exec()
        except KeyboardInterrupt:
            app.quit()
            return 130
    finally:
        if splash is not None:
            splash.close()
        if controller is not None:
            controller.shutdown()
            controller.wait_for_audio_shutdown()
        instance_guard.release()
        from openpiano.update_handoff import commit_pending_update
        commit_pending_update()


if __name__ == "__main__":
    raise SystemExit(main())
