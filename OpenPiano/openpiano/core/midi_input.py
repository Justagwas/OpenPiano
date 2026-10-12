
from __future__ import annotations

import importlib
import threading
import time
from dataclasses import dataclass
from typing import Callable


NoteOnCallback = Callable[[int, int], None]
NoteOffCallback = Callable[[int], None]
PedalCallback = Callable[[int], None]
MIDI_POLL_INTERVAL_SECONDS = 0.002


@dataclass(frozen=True, slots=True)
class MidiInputEvent:
    kind: str
    channel: int
    note: int = 0
    value: int = 0
    generation: int = 0
    sequence: int = 0
    timestamp: float = 0.0


class MidiInputManager:
    
    def __init__(self, on_note_on: NoteOnCallback, on_note_off: NoteOffCallback) -> None:
        self._on_note_on = on_note_on
        self._on_note_off = on_note_off
        self._on_pedal: PedalCallback | None = None
        self._on_disconnect: Callable[[int], None] | None = None
        self._on_event: Callable[[MidiInputEvent], None] | None = None
        self._sequence = 0
        self._pedal_values: dict[int, int] = {}
        self._generation = 0
        self._port = None
        self._port_name = ""
        self._lock = threading.Lock()
        self._message_lock = threading.Lock()
        self._watch_stop: threading.Event | None = None
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
            with self._lock:
                names = list(self._mido_module.get_input_names())
        except Exception as exc:
            self._backend_error = self._format_backend_error(exc)
            return []
        self._backend_error = ""
        return [str(name) for name in names if str(name).strip()]

    def current_device(self) -> str:
        return self._port_name

    def set_pedal_callback(self, callback: PedalCallback) -> None:
        self._on_pedal = callback

    def set_disconnect_callback(self, callback: Callable[[int], None]) -> None:
        self._on_disconnect = callback

    def set_event_callback(self, callback: Callable[[MidiInputEvent], None]) -> None:
        self._on_event = callback

    def input_snapshot(self) -> tuple[int, int, dict[int, int]]:
        with self._message_lock:
            return self._generation, self._sequence, dict(self._pedal_values)

    def input_generation(self) -> int:
        return self._generation

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
            self._start_watchdog_locked()

    def close(self) -> None:
        with self._lock:
            self._close_locked()

    def _close_locked(self) -> None:
        with self._message_lock:
            self._generation += 1
            self._pedal_values.clear()
        if self._watch_stop is not None:
            self._watch_stop.set()
            self._watch_stop = None
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
        channel = int(getattr(message, 'channel', 0))
        if not 0 <= channel <= 15:
            return
        received_at = time.monotonic()
        if msg_type == 'control_change':
            control = int(getattr(message, 'control', -1))
            if control not in (64, 120, 121, 123):
                return
            value = int(getattr(message, 'value', -1))
            if not 0 <= value <= 127:
                return
            if control == 64:
                if self._pedal_values.get(channel) == value:
                    return
                self._pedal_values[channel] = value
            elif control == 121:
                self._pedal_values[channel] = 0
            if self._on_event is not None:
                self._emit_event('control_change', channel, control, value, received_at)
            elif control in (64, 121) and self._on_pedal is not None:
                self._on_pedal(max(self._pedal_values.values()))
            return
        note = int(getattr(message, "note", -1))
        velocity = int(getattr(message, "velocity", 0))
        if note < 0 or note > 127:
            return
        if msg_type not in ('note_on', 'note_off') or not 0 <= velocity <= 127:
            return
        if self._on_event is not None:
            kind = 'note_off' if msg_type == 'note_off' or velocity == 0 else 'note_on'
            self._emit_event(kind, channel, note, velocity, received_at)
            return
        if msg_type == "note_on":
            if velocity <= 0:
                self._on_note_off(note)
            else:
                self._on_note_on(note, velocity)
            return
        if msg_type == "note_off":
            self._on_note_off(note)

    def _emit_event(self, kind, channel, note, value, timestamp) -> None:
        self._sequence += 1
        self._on_event(MidiInputEvent(kind, channel, note, value,
            self._generation, self._sequence, timestamp))

    def _open_input_with_fallback(self, target: str):
        first_error: Exception | None = None
        generation = self._generation
        def callback(message):
            with self._message_lock:
                if generation == self._generation:
                    self._on_message(message)
                                                                        
        for attempt in range(2):
            try:
                return self._mido_module.open_input(target, callback=callback)
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
        thread = threading.Thread(target=self._poll_loop, args=(port, stop, self._generation), daemon=True)
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

    def _poll_loop(self, port, stop: threading.Event, generation: int) -> None:
        while not stop.is_set():
            try:
                messages = list(port.iter_pending())
            except Exception:
                if generation == self._generation and self._on_disconnect is not None:
                    self._on_disconnect(generation)
                return
            for message in messages:
                with self._message_lock:
                    if stop.is_set() or generation != self._generation:
                        return
                    self._on_message(message)
            stop.wait(MIDI_POLL_INTERVAL_SECONDS)

    def _start_watchdog_locked(self) -> None:
        stop = threading.Event()
        self._watch_stop = stop
        threading.Thread(target=self._watch_connection, args=(stop, self._generation), daemon=True).start()

    def _watch_connection(self, stop: threading.Event, generation: int) -> None:
        while not stop.wait(1.0):
            disconnected = False
            with self._lock:
                if generation != self._generation or self._port is None:
                    return
                try:
                    disconnected = bool(getattr(self._port, 'closed', False)) or (
                        self._port_name not in self._mido_module.get_input_names())
                except Exception:
                    continue
                if disconnected:
                    self._close_locked()
                    closed_generation = self._generation
            if disconnected:
                if self._on_disconnect is not None:
                    self._on_disconnect(closed_generation)
                return
