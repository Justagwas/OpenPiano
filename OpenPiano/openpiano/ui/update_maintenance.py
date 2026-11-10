from __future__ import annotations

import queue
import threading

from PySide6.QtCore import QObject, QTimer
from PySide6.QtWidgets import QApplication

from ..update_cleanup import acknowledge_recovery, maintain_updates, pending_recovery
from ..update_handoff import PRODUCT, open_url, take_maintenance_request


class UpdateMaintenance(QObject):
    def __init__(self, parent):
        super().__init__(parent)
        self.window = parent
        self.results = queue.SimpleQueue()
        self.worker = None
        self.remaining = 0
        self.notice = None
        self.notifying = False
        self.shown = set()
        self.timer = QTimer(self)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self._poll)
        self.retry_timer = QTimer(self)
        self.retry_timer.setSingleShot(True)
        self.retry_timer.timeout.connect(self._start)
        self.activity_timer = QTimer(self)
        self.activity_timer.setInterval(2000)
        self.activity_timer.timeout.connect(self._check_request)
        self.activity_timer.start()

    def _check_request(self):
        if not self.notifying and take_maintenance_request():
            self.kick()

    def kick(self):
        if self.notifying:
            return
        self.remaining = 20
        if self.worker is None and not self.retry_timer.isActive():
            self.retry_timer.start(0)

    def _start(self):
        if self.worker is not None:
            return
        results = self.results

        def run():
            try:
                results.put((maintain_updates(), pending_recovery()))
            except Exception:
                results.put(({'retry': False}, None))

        self.remaining -= 1
        self.worker = threading.Thread(target=run, name=PRODUCT + '-update-maintenance', daemon=True)
        self.worker.start()
        self.timer.start()

    def _poll(self):
        if self.notifying:
            return
        if self.worker is not None and not self.worker.is_alive():
            self.worker = None
            try:
                result, notice = self.results.get_nowait()
            except queue.Empty:
                result, notice = {}, None
            if notice is not None and str(notice[0]) not in self.shown:
                self.notice = notice
            if result.get('retry') and self.remaining > 0:
                self.retry_timer.start(2000)
        if self.notice is not None and self.window.isVisible() and QApplication.activeModalWidget() is None:
            path, data = self.notice
            self.notice = None
            self.shown.add(str(path))
            from .update_dialog import show_update_failure
            self.notifying = True
            try:
                choice = show_update_failure(self.window, data.get('error') or 'An earlier update was interrupted.')
            finally:
                self.notifying = False
            try:
                acknowledge_recovery(path)
            except (OSError, RuntimeError, ValueError):
                pass
            if choice == 'manual':
                open_url('https://www.justagwas.com/projects/' + PRODUCT.lower() + '/download')
        if self.worker is None and self.notice is None:
            self.timer.stop()


def start_update_maintenance(parent):
    service = getattr(parent, '_update_maintenance', None)
    if service is None:
        service = UpdateMaintenance(parent)
        parent._update_maintenance = service
    service.kick()
