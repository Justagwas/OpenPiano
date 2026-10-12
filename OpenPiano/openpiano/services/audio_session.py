from __future__ import annotations

import threading
import logging
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QObject, Signal

from openpiano.core.audio_engine import FluidSynthAudioEngine


_cleanup_quarantine = []


class AudioCleanupError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AudioSelection:
    serial: int
    instrument_id: str
    path: str
    bank: int
    preset: int
    volume: float
    persist: bool = False
    startup: bool = False
    retry: bool = False


@dataclass(frozen=True, slots=True)
class AudioPreparation:
    request: AudioSelection
    engine: object | None = None
    error: Exception | None = None
    terminal: bool = False


class AudioSession(QObject):
    prepared = Signal(object)
    activated = Signal(object)
    failed = Signal(object)
    closed = Signal()

    def __init__(self, factory: Callable, current, parent=None) -> None:
        super().__init__(parent)
        self._factory = factory
        self._current = current
        self._condition = threading.Condition()
        self._serial = 0
        self._pending = None
        self._cancel = threading.Event()
        self._ready = None
        self._decision = None
        self._acknowledged = False
        self._closing = False
        self._terminal_error = None
        self._closed = threading.Event()
        self._thread = threading.Thread(target=self._run, name='OpenPiano audio preparation', daemon=False)
        self._thread.start()

    def request(self, instrument_id, path, bank, preset, volume, *, persist=False, startup=False, retry=False):
        with self._condition:
            if self._closing or self._terminal_error is not None:
                return None
            self._serial += 1
            request = AudioSelection(self._serial, instrument_id, path, bank, preset,
                                     volume, persist, startup, retry)
            self._pending = request
            self._cancel.set()
            self._condition.notify_all()
            return request

    def is_latest(self, request) -> bool:
        with self._condition:
            return not self._closing and self._terminal_error is None and request.serial == self._serial

    @property
    def terminal_error(self):
        with self._condition:
            return self._terminal_error

    def accept(self, result) -> bool:
        with self._condition:
            if self._closing or self._terminal_error is not None or result is not self._ready or result.request.serial != self._serial:
                return False
            self._decision = 'accept'
            self._condition.notify_all()
            return True

    def acknowledge(self) -> None:
        with self._condition:
            self._acknowledged = True
            self._condition.notify_all()

    def close(self) -> None:
        with self._condition:
            self._closing = True
            self._pending = None
            self._cancel.set()
            self._condition.notify_all()

    def wait_closed(self, timeout=None) -> bool:
        if self._closed.wait(timeout):
            self._thread.join()
            return True
        return False

    @staticmethod
    def _dispose(engine) -> None:
        if engine is None or any(engine is failed for failed in _cleanup_quarantine):
            return
        try:
            engine.shutdown()
        except BaseException as error:
            _cleanup_quarantine.append(engine)
            raise AudioCleanupError('Audio resource cleanup failed; restart is required.') from error

    def _fail_terminal(self, error, request) -> None:
        with self._condition:
            if self._terminal_error is not None:
                return
            self._terminal_error = error
            request = self._pending or request
            self._pending = None
            self._ready = None
            self._cancel.set()
            self._condition.notify_all()
        logging.getLogger(__name__).error('Audio preparation stopped', exc_info=(type(error), error, error.__traceback__))
        self._emit(self.failed, AudioPreparation(request, error=error, terminal=True))

    def _emit(self, signal, value=None) -> None:
        try:
            if value is None:
                signal.emit()
            else:
                signal.emit(value)
        except RuntimeError:
            self.close()

    def _prepare(self, request, cancel):
        candidate = self._factory()
        try:
            candidate.set_master_volume(request.volume)
            if isinstance(candidate, FluidSynthAudioEngine):
                candidate.set_instrument(request.path, bank=request.bank, preset=request.preset, stop_event=cancel)
            else:
                candidate.set_instrument(request.path, bank=request.bank, preset=request.preset)
            if cancel.is_set():
                raise InterruptedError('SoundFont loading cancelled.')
            start = getattr(candidate, 'start_output', None)
            if callable(start):
                start()
            if cancel.is_set():
                raise InterruptedError('SoundFont loading cancelled.')
            return candidate
        except BaseException:
            self._dispose(candidate)
            raise

    def _run(self) -> None:
        candidate = None
        request = None
        try:
            while True:
                with self._condition:
                    self._condition.wait_for(lambda: self._closing or self._pending is not None)
                    if self._closing:
                        return
                    request = self._pending
                    self._pending = None
                    cancel = self._cancel = threading.Event()
                try:
                    if request.retry:
                        self._current.restart_output()
                        result = AudioPreparation(request, self._current)
                        self._emit(self.activated, result)
                        with self._condition:
                            self._condition.wait_for(lambda: self._closing or self._acknowledged)
                            self._acknowledged = False
                        continue
                    candidate = self._prepare(request, cancel)
                except AudioCleanupError:
                    raise
                except Exception as error:
                    if self.is_latest(request):
                        self._emit(self.failed, AudioPreparation(request, error=error))
                    continue
                result = AudioPreparation(request, candidate)
                with self._condition:
                    if self._closing or cancel.is_set() or request.serial != self._serial:
                        discard = True
                    else:
                        discard = False
                        self._ready = result
                        self._decision = None
                        self._emit(self.prepared, result)
                        self._condition.wait_for(lambda: self._closing or self._decision is not None
                                                 or request.serial != self._serial)
                        discard = self._closing or self._decision != 'accept'
                        self._ready = None
                if discard:
                    self._dispose(candidate)
                    candidate = None
                    continue
                retiring, self._current = self._current, None
                self._dispose(retiring)
                self._current = candidate
                candidate = None
                self._emit(self.activated, result)
                with self._condition:
                    self._condition.wait_for(lambda: self._closing or self._acknowledged)
                    self._acknowledged = False
        except BaseException as error:
            self._fail_terminal(error, request)
            with self._condition:
                self._condition.wait_for(lambda: self._closing)
        finally:
            try:
                for engine in (candidate, self._current):
                    try:
                        self._dispose(engine)
                    except AudioCleanupError as error:
                        self._fail_terminal(error, request)
            finally:
                self._current = None
                self._closed.set()
                self._emit(self.closed)
