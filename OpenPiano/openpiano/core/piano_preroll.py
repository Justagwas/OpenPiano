from __future__ import annotations

from collections import deque
from dataclasses import dataclass, replace


PREROLL_SECONDS = 128.0


@dataclass(frozen=True, slots=True)
class PianoReplayEvent:
    at_seconds: float
    kind: str
    note: int = 0
    velocity: int = 0
    key_held: bool = True
    strike_age_seconds: float = 0.0


class PianoPreroll:

    def __init__(self) -> None:
        self._events: deque[PianoReplayEvent] = deque()
        self._held: dict[int, PianoReplayEvent] = {}
        self._pedal = 0

    def clear(self) -> None:
        self._events.clear()
        self._held.clear()
        self._pedal = 0

    def remember(self, event: PianoReplayEvent, *, phase_seconds: float = 0.0) -> None:
        if not self._events and not self._held:
            self._events.append(PianoReplayEvent(event.at_seconds - phase_seconds, 'pedal', velocity=self._pedal))
        self._events.append(event)
        self._prune(event.at_seconds)

    def _prune(self, now: float) -> None:
        cutoff = now - PREROLL_SECONDS
        while self._events and self._events[0].at_seconds < cutoff:
            event = self._events.popleft()
            if event.kind == 'note_on':
                self._held[event.note] = event
            elif event.kind == 'key_release' and event.note in self._held:
                self._held[event.note] = replace(self._held[event.note], key_held=False)
            elif event.kind == 'note_off':
                self._held.pop(event.note, None)
            elif event.kind == 'pedal':
                self._pedal = event.velocity

    def snapshot(self, now: float) -> tuple[PianoReplayEvent, ...]:
        self._prune(now)
        events = tuple(event for event in self._events if event.at_seconds <= now)
        origin = now - PREROLL_SECONDS if self._held else (events[0].at_seconds if events else now)
        seeds = [PianoReplayEvent(origin, 'pedal', velocity=self._pedal)]
        for note, strike in sorted(self._held.items()):
            seeds.append(replace(strike, at_seconds=origin,
                strike_age_seconds=strike.strike_age_seconds + origin - strike.at_seconds))
        return (*seeds, *events)
