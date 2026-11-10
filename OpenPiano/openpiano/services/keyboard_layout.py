from __future__ import annotations

import sys
from typing import Callable

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, QTimer
from PySide6.QtWidgets import QApplication


class KeyboardLayoutMonitor(QAbstractNativeEventFilter):
    def __init__(self, app: QApplication, parent: QObject, changed: Callable[[], None]) -> None:
        super().__init__()
        self._app = app
        self._installed = False
        self._timer = QTimer(parent)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(changed)
        if sys.platform == "win32" and app.platformName().lower() == "windows":
            app.installNativeEventFilter(self)
            self._installed = True

    def nativeEventFilter(self, event_type, message):
        if bytes(event_type) in {b"windows_generic_MSG", b"windows_dispatcher_MSG"}:
            from ctypes import wintypes

            event = wintypes.MSG.from_address(int(message))
            if event.message == 0x0051 and not self._timer.isActive():
                self._timer.start(0)
        return False, 0

    def close(self) -> None:
        self._timer.stop()
        if self._installed:
            self._app.removeNativeEventFilter(self)
            self._installed = False
