
from __future__ import annotations

import importlib
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class _MidiEvent:
    at_seconds: float
    kind: str
    note: int
    velocity: int


class MidiRecorder:
    
    def __init__(self) -> None:
        self._events: list[_MidiEvent] = []
        self._recording = False
        self._start_time = 0.0
        self._mido_module = self._load_mido_module()

    @staticmethod
    def _load_mido_module():
        try:
            return importlib.import_module("mido")
        except Exception:
            return None

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start(self) -> None:
        self._events.clear()
        self._recording = True
        self._start_time = time.monotonic()

    def stop(self) -> None:
        self._recording = False

    def add_note_on(self, note: int, velocity: int, timestamp: float | None = None) -> None:
        if not self._recording:
            return
        note_value = max(0, min(127, int(note)))
        vel_value = max(1, min(127, int(velocity)))
        self._events.append(
            _MidiEvent(
                at_seconds=self._relative_time(timestamp),
                kind="note_on",
                note=note_value,
                velocity=vel_value,
            )
        )

    def add_note_off(self, note: int, timestamp: float | None = None) -> None:
        if not self._recording:
            return
        note_value = max(0, min(127, int(note)))
        self._events.append(
            _MidiEvent(
                at_seconds=self._relative_time(timestamp),
                kind="note_off",
                note=note_value,
                velocity=0,
            )
        )

    def has_take(self) -> bool:
        return len(self._events) > 0

    def clear(self) -> None:
        self._events.clear()
        self._recording = False

    def save_as(self, path: Path) -> None:
        if self._mido_module is None:
            raise RuntimeError("MIDI recording requires mido.")
        if not self._events:
            raise RuntimeError("No recording data available.")

        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)

        mido = self._mido_module
        midi_file = mido.MidiFile(type=0)
        track = mido.MidiTrack()
        midi_file.tracks.append(track)

        tempo = 500000
        ticks_per_beat = int(getattr(midi_file, "ticks_per_beat", 480))
        last_tick = 0
        ordered_events = sorted(self._events, key=lambda item: item.at_seconds)
        for event in ordered_events:
            absolute_tick = int(
                round(
                    mido.second2tick(
                        max(0.0, float(event.at_seconds)),
                        ticks_per_beat,
                        tempo,
                    )
                )
            )
            delta = max(0, absolute_tick - last_tick)
            last_tick = absolute_tick
            message = mido.Message(event.kind, note=event.note, velocity=event.velocity, time=delta)
            track.append(message)
        track.append(mido.MetaMessage("end_of_track", time=0))
        midi_file.save(str(destination))

    def _relative_time(self, timestamp: float | None) -> float:
        point = time.monotonic() if timestamp is None else float(timestamp)
        return max(0.0, point - self._start_time)

