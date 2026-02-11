#Check out my other projects! https://justagwas.com/projects
#The OFFICIAL Repo - https://github.com/Justagwas/openpiano
from __future__ import annotations

import ctypes
import os
import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from openpiano.app_controller import PianoAppController
from openpiano.core.config import APP_NAME


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


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationDisplayName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    instance_guard = SingleInstanceGuard("OpenPianoMutex")
    if not instance_guard.acquire():
        QMessageBox.information(
            None,
            APP_NAME,
            "OpenPiano is already running.",
        )
        return 0

    try:
        controller = PianoAppController(app)
        controller.run()
        return app.exec()
    finally:
        instance_guard.release()


if __name__ == "__main__":
    raise SystemExit(main())
