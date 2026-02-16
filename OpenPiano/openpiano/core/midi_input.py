
from __future__ import annotations

import importlib
import threading
import time
from typing import Callable


NoteOnCallback = Callable[[int, int], None]
NoteOffCallback = Callable[[int], None]


class MidiInputManager:
    
    def __init__(self, on_note_on: NoteOnCallback, on_note_off: NoteOffCallback) -> None:
        self._on_note_on = on_note_on
        self._on_note_off = on_note_off
        self._port = None
        self._port_name = ""
        self._lock = threading.Lock()
        self._poll_thread: threading.Thread | None = None
        self._poll_stop: threading.Event | None = None
        self._mido_module = None
        self._backend_error = ""
        self._load_mido_module()

    def _load_mido_module(self) -> None:
        try:
            module = importlib.import_module("mido")
        except Exception as exc:
            self._backend_error = f"Could not import mido: {type(exc).__name__}: {exc}"
            self._mido_module = None
            return

        try:
                                                                                    
            list(module.get_input_names())
        except Exception as exc:
            self._backend_error = self._format_backend_error(exc)
            self._mido_module = None
            return

        self._mido_module = module
        self._backend_error = ""

    @staticmethod
    def _format_backend_error(exc: Exception) -> str:
        missing_module = str(getattr(exc, "name", "")).strip().lower()
        if isinstance(exc, ModuleNotFoundError) and missing_module == "rtmidi":
            return "Could not load module 'rtmidi'. Install 'python-rtmidi' for this Python environment."
        text = str(exc or "").strip()
        if "midiinwinmm::openport" in text.lower():
            return (
                f"{type(exc).__name__}: {exc}. "
                "The MIDI input may already be in use by another app."
            )
        return f"{type(exc).__name__}: {exc}"

    def backend_error(self) -> str:
        return self._backend_error

    def list_input_devices(self) -> list[str]:
        if self._mido_module is None:
            return []
        try:
            names = list(self._mido_module.get_input_names())
        except Exception as exc:
            self._backend_error = self._format_backend_error(exc)
            return []
        self._backend_error = ""
        return [str(name) for name in names if str(name).strip()]

    def current_device(self) -> str:
        return self._port_name

    def open_device(self, name: str) -> None:
        target = str(name).strip()
        with self._lock:
            self._close_locked()
            if not target:
                return
            if self._mido_module is None:
                detail = f" ({self._backend_error})" if self._backend_error else ""
                raise RuntimeError(f"MIDI input backend not available{detail}.")
            try:
                self._port = self._open_input_with_fallback(target)
            except Exception as exc:
                self._backend_error = self._format_backend_error(exc)
                raise RuntimeError(f"Could not open MIDI input '{target}': {self._backend_error}") from exc
            self._port_name = target
            self._backend_error = ""

    def close(self) -> None:
        with self._lock:
            self._close_locked()

    def _close_locked(self) -> None:
        self._stop_polling_locked()
        port = self._port
        self._port = None
        self._port_name = ""
        if port is None:
            return
        try:
            port.close()
        except Exception:
            return

    def _on_message(self, message) -> None:
        msg_type = str(getattr(message, "type", "")).lower()
        note = int(getattr(message, "note", -1))
        velocity = int(getattr(message, "velocity", 0))
        if note < 0 or note > 127:
            return
        if msg_type == "note_on":
            if velocity <= 0:
                self._on_note_off(note)
            else:
                self._on_note_on(note, velocity)
            return
        if msg_type == "note_off":
            self._on_note_off(note)

    def _open_input_with_fallback(self, target: str):
        first_error: Exception | None = None
                                                                        
        for attempt in range(2):
            try:
                return self._mido_module.open_input(target, callback=self._on_message)
            except Exception as exc:
                if first_error is None:
                    first_error = exc
                if attempt == 0 and self._is_winmm_open_error(exc):
                    time.sleep(0.12)
                    continue
                break

        try:
            port = self._mido_module.open_input(target)
            self._start_polling_locked(port)
            return port
        except Exception:
            if first_error is not None:
                raise first_error
            raise

    @staticmethod
    def _is_winmm_open_error(exc: Exception) -> bool:
        text = str(exc or "").lower()
        return "midiinwinmm::openport" in text or "error creating windows mm midi input port" in text

    def _start_polling_locked(self, port) -> None:
        stop = threading.Event()
        thread = threading.Thread(target=self._poll_loop, args=(port, stop), daemon=True)
        self._poll_stop = stop
        self._poll_thread = thread
        thread.start()

    def _stop_polling_locked(self) -> None:
        stop = self._poll_stop
        thread = self._poll_thread
        self._poll_stop = None
        self._poll_thread = None
        if stop is not None:
            stop.set()
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=0.2)

    def _poll_loop(self, port, stop: threading.Event) -> None:
        while not stop.is_set():
            try:
                messages = list(port.iter_pending())
            except Exception:
                return
            for message in messages:
                self._on_message(message)
            stop.wait(0.01)
