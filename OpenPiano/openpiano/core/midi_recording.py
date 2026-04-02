from __future__ import annotations

import importlib
import time
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path

from openpiano.core.fluidsynth_loader import ensure_fluidsynth_loaded


MIDI_EXPORT_EXTENSIONS = {".mid", ".midi"}
WAV_EXPORT_EXTENSIONS = {".wav"}
DEFAULT_RENDER_SAMPLE_RATE = 48000
MAX_RENDER_SAMPLE_RATE = 48000
DEFAULT_RENDER_TAIL_SECONDS = 1.5


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
        return len(self._normalized_events()) > 0

    def clear(self) -> None:
        self._events.clear()
        self._recording = False

    def save_as(
        self,
        path: Path,
        *,
        soundfont_path: Path | None = None,
        bank: int = 0,
        preset: int = 0,
        master_volume: float = 1.0,
        sample_rate: int = DEFAULT_RENDER_SAMPLE_RATE,
    ) -> None:
        destination = Path(path)
        suffix = destination.suffix.lower()
        if not suffix:
            destination = destination.with_suffix(".mid")
            suffix = ".mid"
        destination.parent.mkdir(parents=True, exist_ok=True)

        events = self._normalized_events()
        if not events:
            raise RuntimeError("No recording data available.")

        if suffix in MIDI_EXPORT_EXTENSIONS:
            self._save_midi(destination, events)
            return
        if suffix in WAV_EXPORT_EXTENSIONS:
            self._save_wav(
                destination=destination,
                events=events,
                soundfont_path=soundfont_path,
                bank=bank,
                preset=preset,
                master_volume=master_volume,
                sample_rate=sample_rate,
            )
            return
        raise RuntimeError("Unsupported recording format. Use .mid or .wav.")

    def _save_midi(self, destination: Path, events: list[_MidiEvent]) -> None:
        if self._mido_module is None:
            raise RuntimeError("MIDI recording requires mido.")

        mido = self._mido_module
        midi_file = mido.MidiFile(type=0)
        track = mido.MidiTrack()
        midi_file.tracks.append(track)

        tempo = 500000
        ticks_per_beat = int(getattr(midi_file, "ticks_per_beat", 480))
        last_tick = 0
        for event in events:
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

    def _save_wav(
        self,
        *,
        destination: Path,
        events: list[_MidiEvent],
        soundfont_path: Path | None,
        bank: int,
        preset: int,
        master_volume: float,
        sample_rate: int,
    ) -> None:
        sf_path = Path(soundfont_path) if soundfont_path is not None else None
        if sf_path is None or not sf_path.exists():
            raise RuntimeError("WAV export requires a valid SoundFont file path.")

        module, error = ensure_fluidsynth_loaded()
        if module is None:
            raise RuntimeError(f"WAV export requires pyfluidsynth: {error}")

        render_sample_rate = max(8000, min(MAX_RENDER_SAMPLE_RATE, int(sample_rate)))
        synth = module.Synth(samplerate=float(render_sample_rate))
        sfid: int | None = None
        try:
            sfid = self._synth_sfload(synth, str(sf_path))
            synth.program_select(0, int(sfid), int(bank), int(preset))
            if hasattr(synth, "set_gain"):
                synth.set_gain(max(0.0, min(1.0, float(master_volume))))

            with wave.open(str(destination), "wb") as wav_out:
                wav_out.setnchannels(2)
                wav_out.setsampwidth(2)
                wav_out.setframerate(render_sample_rate)

                current_time = 0.0
                for event in events:
                    event_time = max(current_time, float(event.at_seconds))
                    self._render_wav_segment(
                        synth=synth,
                        wav_out=wav_out,
                        duration_seconds=event_time - current_time,
                        sample_rate=render_sample_rate,
                    )
                    if event.kind == "note_on":
                        synth.noteon(0, int(event.note), int(event.velocity))
                    else:
                        synth.noteoff(0, int(event.note))
                    current_time = event_time

                self._render_wav_segment(
                    synth=synth,
                    wav_out=wav_out,
                    duration_seconds=DEFAULT_RENDER_TAIL_SECONDS,
                    sample_rate=render_sample_rate,
                )
        finally:
            if sfid is not None:
                try:
                    self._synth_sfunload(synth, sfid)
                except Exception:
                    pass
            try:
                synth.delete()
            except Exception:
                pass

    @staticmethod
    def _render_wav_segment(
        *,
        synth,
        wav_out: wave.Wave_write,
        duration_seconds: float,
        sample_rate: int,
    ) -> None:
        total_frames = max(0, int(round(float(duration_seconds) * max(8000, int(sample_rate)))))
        remaining = total_frames
        while remaining > 0:
            chunk = min(4096, remaining)
            wav_out.writeframesraw(MidiRecorder._samples_to_pcm16_bytes(synth.get_samples(int(chunk))))
            remaining -= chunk

    @staticmethod
    def _samples_to_pcm16_bytes(samples) -> bytes:
        values = samples.tolist() if hasattr(samples, "tolist") else list(samples)
        if not values:
            return b""
        first = values[0]
        pcm = array("h")
        if isinstance(first, float):
            for value in values:
                scaled = int(round(float(value) * 32767.0))
                pcm.append(max(-32768, min(32767, scaled)))
            return pcm.tobytes()
        for value in values:
            parsed = int(value)
            pcm.append(max(-32768, min(32767, parsed)))
        return pcm.tobytes()

    @staticmethod
    def _synth_sfload(synth, soundfont_path: str) -> int:
        try:
            return int(synth.sfload(soundfont_path, reset_presets=False))
        except TypeError:
            pass
        try:
            return int(synth.sfload(soundfont_path, False))
        except TypeError:
            return int(synth.sfload(soundfont_path))

    @staticmethod
    def _synth_sfunload(synth, sfid: int) -> None:
        try:
            synth.sfunload(int(sfid), update_midi_preset=False)
            return
        except TypeError:
            pass
        try:
            synth.sfunload(int(sfid), False)
            return
        except TypeError:
            synth.sfunload(int(sfid))

    def _normalized_events(self) -> list[_MidiEvent]:
        ordered = sorted(
            self._events,
            key=lambda item: (
                max(0.0, float(item.at_seconds)),
                0 if item.kind == "note_off" else 1,
                int(item.note),
            ),
        )
        normalized: list[_MidiEvent] = []
        active_notes: set[int] = set()
        for event in ordered:
            timestamp = max(0.0, float(event.at_seconds))
            note = max(0, min(127, int(event.note)))
            if event.kind == "note_on":
                velocity = max(1, min(127, int(event.velocity)))
                if note in active_notes:
                    normalized.append(_MidiEvent(at_seconds=timestamp, kind="note_off", note=note, velocity=0))
                    active_notes.discard(note)
                normalized.append(_MidiEvent(at_seconds=timestamp, kind="note_on", note=note, velocity=velocity))
                active_notes.add(note)
                continue
            if event.kind == "note_off":
                if note not in active_notes:
                    continue
                normalized.append(_MidiEvent(at_seconds=timestamp, kind="note_off", note=note, velocity=0))
                active_notes.discard(note)

        if active_notes:
            last_timestamp = normalized[-1].at_seconds if normalized else 0.0
            for note in sorted(active_notes):
                normalized.append(_MidiEvent(at_seconds=last_timestamp, kind="note_off", note=note, velocity=0))
        return normalized

    def _relative_time(self, timestamp: float | None) -> float:
        point = time.monotonic() if timestamp is None else float(timestamp)
        return max(0.0, point - self._start_time)
