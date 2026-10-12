from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable

from openpiano.core.music_logic import sustain_hold_ms


@dataclass(slots=True)
class NoteStrike:
    started_at: float
    velocity: int
    key_released_at: float | None = None


class NoteLifecycleService:
    def __init__(self, note_sources: dict[int, set[str]], sustained_notes: dict[int, float | None]) -> None:
        self.note_sources = note_sources
        self.sustained_notes = sustained_notes
        self.strikes: dict[int, NoteStrike] = {}
        self.strike_sources: dict[int, set[str]] = {}

    def activate_note(
        self,
        note: int,
        source: str,
        velocity: int,
        *,
        note_on: Callable[[int, int], None],
        record_note_on: Callable[[int, int, float], None],
        set_pressed: Callable[[int, bool], None],
        now: float | None = None,
    ) -> None:
        sources = self.note_sources.setdefault(note, set())
        first_source = len(sources) == 0
        sources.add(source)
        self.sustained_notes.pop(note, None)
        if first_source:
            self.strike_sources[note] = {source}
            timestamp = time.monotonic() if now is None else float(now)
            self.strikes[note] = NoteStrike(timestamp, max(1, min(127, int(velocity))))
            note_on(note, velocity)
            record_note_on(note, velocity, timestamp)
            set_pressed(note, True)
        else:
            self.strike_sources.setdefault(note, set()).add(source)

    def stop_note(
        self,
        note: int,
        *,
        note_off: Callable[[int], None],
        record_note_off: Callable[[int, float], None],
        set_pressed: Callable[[int, bool], None],
        now: float | None = None,
    ) -> None:
        timestamp = time.monotonic() if now is None else float(now)
        note_off(note)
        record_note_off(note, timestamp)
        set_pressed(note, False)
        self.sustained_notes.pop(note, None)
        self.strikes.pop(note, None)
        self.strike_sources.pop(note, None)

    def discard_sources(self, predicate, *, stop_note, set_pressed) -> None:
        notes = set(self.note_sources) | set(self.sustained_notes)
        for note in notes:
            sources = self.note_sources.get(note, set())
            contributors = self.strike_sources.get(note, set(sources))
            affected = any(predicate(source) for source in sources | contributors)
            if not affected:
                continue
            sources.difference_update(source for source in tuple(sources) if predicate(source))
            contributors.difference_update(source for source in tuple(contributors) if predicate(source))
            if not sources:
                self.note_sources.pop(note, None)
                set_pressed(note, False)
                if not contributors or note not in self.sustained_notes:
                    stop_note(note)

    def release_note_source(
        self,
        note: int,
        source: str,
        *,
        sustain_percent: int,
        sustain_temporarily_off: bool,
        stop_note: Callable[[int], None],
        set_pressed: Callable[[int, bool], None],
        key_release: Callable[[int, float], None] | None = None,
        now: float | None = None,
    ) -> None:
        sources = self.note_sources.get(note)
        if not sources or source not in sources:
            return
        sources.discard(source)
        if sources:
            return
        self.note_sources.pop(note, None)

        timestamp = time.monotonic() if now is None else float(now)
        strike = self.strikes.get(note)
        if strike is not None:
            strike.key_released_at = timestamp
        if key_release is not None:
            key_release(note, timestamp)

        hold_ms = sustain_hold_ms(sustain_percent)
        if sustain_temporarily_off or hold_ms == 0:
            stop_note(note)
            return

        set_pressed(note, False)
        if hold_ms is None:
            self.sustained_notes[note] = None
            return
        self.sustained_notes[note] = timestamp + (hold_ms / 1000.0)

    def release_all_sustained(self, *, stop_note: Callable[[int], None]) -> None:
        for note in list(self.sustained_notes.keys()):
            stop_note(note)
            self.strikes.pop(note, None)
        self.sustained_notes.clear()

    def refresh_sustain_deadlines(
        self,
        *,
        sustain_percent: int,
        sustain_temporarily_off: bool,
        release_all_sustained: Callable[[], None],
        now: float | None = None,
    ) -> None:
        if not self.sustained_notes:
            return
        hold_ms = sustain_hold_ms(sustain_percent)
        if hold_ms == 0 or sustain_temporarily_off:
            release_all_sustained()
            return
        if hold_ms is None:
            for note in list(self.sustained_notes.keys()):
                self.sustained_notes[note] = None
            return
        timestamp = time.monotonic() if now is None else float(now)
        deadline = timestamp + (hold_ms / 1000.0)
        for note in list(self.sustained_notes.keys()):
            self.sustained_notes[note] = deadline

    def stop_all_notes(
        self,
        *,
        recorder_is_recording: bool,
        record_note_off: Callable[[int, float], None],
        set_pressed: Callable[[int, bool], None],
        all_notes_off: Callable[[], None],
        record_all_notes_off: Callable[[float], None] | None = None,
        now: float | None = None,
    ) -> None:
        notes = set(self.note_sources.keys()) | set(self.sustained_notes.keys())
        self.note_sources.clear()
        self.sustained_notes.clear()
        self.strikes.clear()
        self.strike_sources.clear()
        timestamp = time.monotonic() if now is None else float(now)
        for note in notes:
            if recorder_is_recording:
                record_note_off(note, timestamp)
            set_pressed(note, False)
        if recorder_is_recording and record_all_notes_off is not None:
            record_all_notes_off(timestamp)
        all_notes_off()
