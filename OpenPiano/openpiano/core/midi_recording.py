from __future__ import annotations

import importlib
import os
import tempfile
import time
import wave
from array import array
from dataclasses import dataclass
from pathlib import Path
from threading import Event

from openpiano.core.fluidsynth_loader import ensure_fluidsynth_loaded
from openpiano.core.audio_levels import playback_gain
from openpiano.core.audio_processing import SynthOutput
from openpiano.core.piano_damping import staged_piano_damping
from openpiano.core.soundfont_loading import load_soundfont, dispose_soundfont_loader
from openpiano.core.piano_room import PianoRoom, has_piano_room
from openpiano.core.soundfont_capabilities import inspect_soundfont
from openpiano.core.native_result import check_native_result, release_native_note
from openpiano.core.config import DEFAULT_AUDIO_POLYPHONY
from openpiano.core.piano_key_release import (
    KEY_RELEASE_POLYPHONY, PianoKeyRelease, has_piano_key_release, has_piano_release_resonance,
)


MIDI_EXPORT_EXTENSIONS = {".mid", ".midi"}
WAV_EXPORT_EXTENSIONS = {".wav"}
DEFAULT_RENDER_SAMPLE_RATE = 48000
MAX_RENDER_SAMPLE_RATE = 48000
DEFAULT_RENDER_TAIL_SECONDS = 1.5
MAX_RENDER_TAIL_SECONDS = 30.0
RENDER_TAIL_SILENCE_SECONDS = 0.25


@dataclass(slots=True)
class _MidiEvent:
    at_seconds: float
    kind: str
    note: int
    velocity: int
    key_held: bool = True
    key_release_fallback: bool = True
    controls_damping: bool = False
    pedal_source: str = ''
    pedal_input_value: int = 0
    damping_resonance: bool = True
    strike_age_seconds: float = 0.0
    recapture_owned: bool = True
    midi_only_snapshot: bool = False
    native_release: bool = False


class _PrerollWriter:

    def __init__(self, writer, frames: int) -> None:
        self.writer = writer
        self.remaining_bytes = max(0, frames) * 4

    def writeframesraw(self, pcm: bytes) -> None:
        skipped = min(self.remaining_bytes, len(pcm))
        self.remaining_bytes -= skipped
        if skipped < len(pcm):
            self.writer.writeframesraw(pcm[skipped:])


class MidiRecorder:
    def __init__(self) -> None:
        self._events: list[_MidiEvent] = []
        self._recording = False
        self._start_time = 0.0
        self._preroll_events: list[_MidiEvent] = []
        self._take_end_at: float | None = None
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
        self._preroll_events.clear()
        self._take_end_at = None
        self._recording = True
        self._start_time = time.monotonic()

    def stop(self) -> None:
        if self._recording and self._preroll_events:
            self._take_end_at = self._relative_time(None)
        self._recording = False

    def capture_piano_preroll(self, events) -> bool:
        if not self._recording or events is None:
            return False
        self._preroll_events = [_MidiEvent(
            event.at_seconds - self._start_time, event.kind, event.note, event.velocity,
            key_held=event.key_held, strike_age_seconds=event.strike_age_seconds,
            controls_damping=True, pedal_source='preroll', recapture_owned=True,
            key_release_fallback=False)
            for event in events if event.at_seconds <= self._start_time]
        return bool(self._preroll_events)

    def add_note_on(self, note: int, velocity: int, timestamp: float | None = None, *,
                    key_held: bool = True, strike_age_seconds: float = 0.0,
                    midi_only_snapshot: bool = False) -> None:
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
                key_held=key_held,
                strike_age_seconds=max(0.0, float(strike_age_seconds)),
                midi_only_snapshot=midi_only_snapshot,
            )
        )

    def add_note_off(self, note: int, timestamp: float | None = None, *,
                     key_release_fallback: bool = True, damping_resonance: bool = True) -> None:
        if not self._recording:
            return
        note_value = max(0, min(127, int(note)))
        self._events.append(
            _MidiEvent(
                at_seconds=self._relative_time(timestamp),
                kind="note_off",
                note=note_value,
                velocity=0,
                key_release_fallback=key_release_fallback,
                damping_resonance=damping_resonance,
            )
        )

    def add_key_release(self, note: int, timestamp: float | None = None) -> None:
        if self._recording:
            self._events.append(_MidiEvent(self._relative_time(timestamp), 'key_release',
                max(0, min(127, int(note))), 0))

    def add_all_notes_off(self, timestamp: float | None = None) -> None:
        if self._recording:
            self._events.append(_MidiEvent(self._relative_time(timestamp), 'all_notes_off', 0, 0))

    def add_pedal(self, value: int, timestamp: float | None = None, *,
                  controls_damping: bool = True, source: str = 'midi', input_value: int | None = None,
                  recapture_owned: bool | None = None) -> None:
        if self._recording:
            value = max(0, min(127, int(value)))
            raw = value if input_value is None else max(0, min(127, int(input_value)))
            self._events.append(_MidiEvent(self._relative_time(timestamp), 'pedal', 0, value,
                controls_damping=controls_damping, pedal_source=source, pedal_input_value=raw,
                recapture_owned=controls_damping if recapture_owned is None else recapture_owned))

    def has_take(self) -> bool:
        return bool(self._normalized_events() or self._preroll_events)

    def clear(self) -> None:
        self._events.clear()
        self._preroll_events.clear()
        self._take_end_at = None
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
        stop_event: Event | None = None,
        piano_recapture: bool = False,
        piano_half_pedal: bool = False,
        piano_contact_blend: bool = False,
    ) -> None:
        if piano_contact_blend and not (piano_recapture and piano_half_pedal):
            raise ValueError('Contact blending requires experimental half-pedal.')
        if piano_half_pedal and not piano_recapture:
            raise ValueError('Half-pedal requires experimental piano recapture.')
        destination = Path(path)
        suffix = destination.suffix.lower()
        if not suffix:
            destination = destination.with_suffix(".mid")
            suffix = ".mid"
        destination.parent.mkdir(parents=True, exist_ok=True)

        events = self._normalized_events(for_wav=suffix in WAV_EXPORT_EXTENSIONS)
        if not events:
            if self._preroll_events and suffix in MIDI_EXPORT_EXTENSIONS:
                raise RuntimeError('This take contains an existing piano tail. Save it as WAV to preserve that sound.')
            raise RuntimeError("No recording data available.")

        if suffix not in MIDI_EXPORT_EXTENSIONS | WAV_EXPORT_EXTENSIONS:
            raise RuntimeError("Unsupported recording format. Use .mid or .wav.")

        self._ensure_export_not_stopped(stop_event)
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                dir=str(destination.parent),
                prefix=f".{destination.stem}.",
                suffix=destination.suffix,
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
            if suffix in MIDI_EXPORT_EXTENSIONS:
                self._save_midi(temp_path, events)
            else:
                self._save_wav(
                    destination=temp_path,
                    events=events,
                    soundfont_path=soundfont_path,
                    bank=bank,
                    preset=preset,
                    master_volume=master_volume,
                    sample_rate=sample_rate,
                    stop_event=stop_event,
                    piano_recapture=piano_recapture,
                    piano_half_pedal=piano_half_pedal,
                    piano_contact_blend=piano_contact_blend,
                )
            self._ensure_export_not_stopped(stop_event)
            os.replace(temp_path, destination)
            temp_path = None
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass

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
        for event in self._midi_export_events(events):
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
            if event.kind == 'all_notes_off':
                message = mido.Message('control_change', control=120, value=0, time=delta)
            elif event.kind == 'pedal':
                message = mido.Message('control_change', control=64, value=event.velocity, time=delta)
            else:
                message = mido.Message(event.kind, note=event.note, velocity=event.velocity, time=delta)
            track.append(message)
        track.append(mido.MetaMessage("end_of_track", time=0))
        midi_file.save(str(destination))

    @staticmethod
    def _midi_export_events(events: list[_MidiEvent]) -> list[_MidiEvent]:
        result: list[_MidiEvent] = []
        open_notes: set[int] = set()
        released_keys: set[int] = set()
        controlled = False
        for event in events:
            note, at = event.note, event.at_seconds
            if event.kind == 'pedal':
                if event.controls_damping:
                    result.append(event)
                    controlled = True
                    for key in sorted(open_notes & released_keys):
                        result.append(_MidiEvent(at, 'note_off', key, 0))
                        open_notes.discard(key)
                elif controlled:
                    result.append(_MidiEvent(at, 'pedal', 0, 0))
                    controlled = False
                continue
            if event.kind == 'key_release':
                released_keys.add(note)
                if controlled and note in open_notes:
                    result.append(_MidiEvent(at, 'note_off', note, 0))
                    open_notes.discard(note)
                continue
            if event.kind == 'note_on':
                result.append(event)
                open_notes.add(note)
                released_keys.discard(note)
                if not event.key_held:
                    released_keys.add(note)
                    if controlled:
                        result.append(_MidiEvent(at, 'note_off', note, 0))
                        open_notes.discard(note)
                continue
            if event.kind == 'note_off':
                if note in open_notes:
                    result.append(event)
                    open_notes.discard(note)
                released_keys.discard(note)
                continue
            if event.kind == 'all_notes_off':
                result.append(event)
                open_notes.clear()
                released_keys.clear()
        return result

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
        stop_event: Event | None,
        piano_recapture: bool = False,
        piano_half_pedal: bool = False,
        piano_contact_blend: bool = False,
    ) -> None:
        sf_path = Path(soundfont_path) if soundfont_path is not None else None
        if sf_path is None or not sf_path.exists():
            raise RuntimeError("WAV export requires a valid SoundFont file path.")

        module, error = ensure_fluidsynth_loaded()
        if module is None:
            raise RuntimeError(f"WAV export requires pyfluidsynth: {error}")

        render_sample_rate = max(8000, min(MAX_RENDER_SAMPLE_RATE, int(sample_rate)))
        capabilities = inspect_soundfont(sf_path, stop_event=stop_event)
        release_enabled = (int(bank), int(preset)) == (0, 0) and has_piano_key_release(sf_path, capabilities=capabilities)
        polyphony = max(DEFAULT_AUDIO_POLYPHONY, KEY_RELEASE_POLYPHONY) if release_enabled else DEFAULT_AUDIO_POLYPHONY
        try:
            synth = module.Synth(samplerate=float(render_sample_rate), **{'synth.polyphony': polyphony})
        except TypeError:
            synth = module.Synth(samplerate=float(render_sample_rate))
        sfid: int | None = None
        output = damping = None
        try:
            if hasattr(synth, "setting"):
                synth.setting("synth.polyphony", polyphony)
            sfid = self._synth_sfload(synth, str(sf_path), module=module, stop_event=stop_event,
                capabilities=capabilities)
            check_native_result(synth.program_select(0, int(sfid), int(bank), int(preset)), 'select the WAV program')
            key_release = (
                PianoKeyRelease(synth, int(sfid), DEFAULT_AUDIO_POLYPHONY,
                    resonance=has_piano_release_resonance(sf_path, capabilities=capabilities))
                if release_enabled
                else None
            )
            room = (PianoRoom.create(synth, module)
                    if (int(bank), int(preset)) == (0, 0) and has_piano_room(sf_path, capabilities=capabilities) else None)
            if room is not None:
                room.activate()
            capabilities.validate_unchanged()
            gain = playback_gain(master_volume, sf_path, int(bank), int(preset), capabilities=capabilities)
            if hasattr(synth, "set_gain"):
                synth.set_gain(gain)
            else:
                synth.setting("synth.gain", float(gain))
            output = SynthOutput(module, synth, render_sample_rate)
            damping = (staged_piano_damping(module, synth, render_sample_rate,
                sf_path, int(bank), int(preset), half_pedal=piano_half_pedal,
                contact_blend=piano_contact_blend, capabilities=capabilities)
                if piano_recapture else None)
            if damping is not None:
                damping.attach(output)
            origin = min(0.0, events[0].at_seconds)
            if origin < 0.0 and damping is None:
                raise RuntimeError('This take begins during a recaptured tail; WAV export requires its D-274 recapture renderer.')

            with wave.open(str(destination), "wb") as wav_out:
                wav_out.setnchannels(2)
                wav_out.setsampwidth(2)
                wav_out.setframerate(render_sample_rate)

                writer = _PrerollWriter(wav_out, int(round(-origin * render_sample_rate)))
                current_time = origin
                current_frame = 0
                for event in events:
                    self._ensure_export_not_stopped(stop_event)
                    event_time = max(current_time, float(event.at_seconds))
                    event_frame = max(current_frame, int(round((event_time - origin) * render_sample_rate)))
                    self._render_wav_segment(
                        synth=synth,
                        output=output,
                        wav_out=writer,
                        duration_seconds=(event_frame - current_frame) / render_sample_rate,
                        sample_rate=render_sample_rate,
                        stop_event=stop_event,
                    )
                    if event.kind == "note_on":
                        if room is not None:
                            room.resume()
                        check_native_result(synth.noteon(0, int(event.note), int(event.velocity)), 'render a recorded attack')
                        if damping is not None:
                            damping.press(int(event.note), int(event.velocity), at_seconds=event_time,
                                key_held=event.key_held, strike_age_seconds=event.strike_age_seconds)
                        if key_release is not None:
                            key_release.press(int(event.note), int(event.velocity), key_held=event.key_held,
                                at_seconds=event_time, strike_age_seconds=event.strike_age_seconds)
                    elif event.kind == 'key_release':
                        if damping is not None:
                            damping.key_release(int(event.note), at_seconds=event_time)
                        if key_release is not None:
                            key_release.release(int(event.note))
                    elif event.kind == 'all_notes_off':
                        check_native_result(synth.cc(0, 120, 0), 'silence the recorded piano')
                        if damping is not None:
                            damping.clear()
                        if key_release is not None:
                            key_release.stop()
                        if room is not None:
                            room.clear()
                    elif event.kind == 'pedal':
                        synth._openpiano_pedal_value = event.velocity
                        if damping is not None:
                            contacts = damping.pedal(event.velocity if event.recapture_owned else 0,
                                                      at_seconds=event_time)
                            if key_release is not None and event.pedal_source not in ('panic', 'take_end'):
                                for note, loss in contacts:
                                    key_release.damp(note, at_seconds=event_time, retain=True,
                                                     damping_loss_db=loss,
                                                     contact_strength=damping.contact_strength)
                    elif event.kind == 'note_off':
                        if key_release is not None:
                            if event.key_release_fallback:
                                key_release.release(int(event.note))
                            else:
                                key_release.forget(int(event.note))
                        captured = (damping is not None and not event.native_release
                                    and damping.damp(int(event.note), at_seconds=event_time))
                        if not captured:
                            release_native_note(synth, 0, int(event.note))
                        if key_release is not None:
                            loss = damping.damping_loss(int(event.note)) if captured else None
                            key_release.damp(int(event.note), at_seconds=event_time,
                                             enabled=event.damping_resonance and (not captured or loss is not None),
                                             retain=captured, damping_loss_db=loss or 0.0,
                                             contact_strength=damping.contact_strength if captured else 1.0)
                    current_time = event_time
                    current_frame = event_frame

                self._render_wav_tail(
                    output=output,
                    wav_out=writer,
                    sample_rate=render_sample_rate,
                    stop_event=stop_event,
                )
        finally:
            if sfid is not None:
                try:
                    self._synth_sfunload(synth, sfid)
                except Exception:
                    pass
            synth.delete()
            dispose_soundfont_loader(synth)
            if output is not None:
                output.close()
            for owner in getattr(synth, '_openpiano_piano_owners', ()):
                owner.close()

    @staticmethod
    def _render_wav_tail(
        *,
        output: SynthOutput,
        wav_out: wave.Wave_write,
        sample_rate: int,
        stop_event: Event | None,
    ) -> None:
        minimum = int(round(DEFAULT_RENDER_TAIL_SECONDS * sample_rate))
        maximum = int(round(MAX_RENDER_TAIL_SECONDS * sample_rate))
        silence_needed = int(round(RENDER_TAIL_SILENCE_SECONDS * sample_rate))
        rendered = quiet_frames = 0
        while rendered < maximum:
            MidiRecorder._ensure_export_not_stopped(stop_event)
            boundary = minimum if rendered < minimum else maximum
            frames = min(4096, boundary - rendered)
            pcm = array("h")
            pcm.frombytes(output.pcm16(frames))
            quiet_frames = quiet_frames + frames if all(abs(value) <= 1 for value in pcm) else 0
            rendered += frames
            if rendered == maximum:
                fade_frames = min(frames, int(round(0.05 * sample_rate)))
                for i in range(fade_frames):
                    gain = (fade_frames - i - 1) / max(1, fade_frames - 1)
                    index = 2 * (frames - fade_frames + i)
                    pcm[index] = round(pcm[index] * gain)
                    pcm[index + 1] = round(pcm[index + 1] * gain)
            wav_out.writeframesraw(pcm.tobytes())
            if rendered >= minimum and quiet_frames >= silence_needed:
                break

    @staticmethod
    def _render_wav_segment(
        *,
        synth,
        output: SynthOutput,
        wav_out: wave.Wave_write,
        duration_seconds: float,
        sample_rate: int,
        stop_event: Event | None,
    ) -> None:
        total_frames = max(0, int(round(float(duration_seconds) * max(8000, int(sample_rate)))))
        remaining = total_frames
        while remaining > 0:
            MidiRecorder._ensure_export_not_stopped(stop_event)
            chunk = min(4096, remaining)
            wav_out.writeframesraw(output.pcm16(int(chunk)))
            remaining -= chunk

    @staticmethod
    def _ensure_export_not_stopped(stop_event: Event | None) -> None:
        if stop_event is not None and stop_event.is_set():
            raise InterruptedError("Recording export cancelled.")

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
    def _synth_sfload(synth, soundfont_path: str, *, module=None, stop_event: Event | None = None, capabilities=None) -> int:
        return load_soundfont(synth, soundfont_path, module=module, stop_event=stop_event, capabilities=capabilities)

    @staticmethod
    def _synth_sfunload(synth, sfid: int) -> None:
        try:
            check_native_result(synth.sfunload(int(sfid), update_midi_preset=False), 'unload the export SoundFont')
            return
        except TypeError:
            pass
        try:
            check_native_result(synth.sfunload(int(sfid), False), 'unload the export SoundFont')
            return
        except TypeError:
            check_native_result(synth.sfunload(int(sfid)), 'unload the export SoundFont')

    def _normalized_events(self, *, for_wav: bool = False) -> list[_MidiEvent]:
        prefix = self._preroll_events if for_wav else []
        minimum_time = min(0.0, prefix[0].at_seconds) if prefix else 0.0
        events = [*prefix, *(event for event in self._events
                            if not (prefix and event.midi_only_snapshot))]
        if prefix:
            ending = self._take_end_at if self._take_end_at is not None else max(
                (event.at_seconds for event in self._events), default=0.0)
            events.append(_MidiEvent(max(0.0, ending),
                                      'end', 0, 0))
        ordered = sorted(
            events,
            key=lambda item: max(minimum_time, float(item.at_seconds)),
        )
        normalized: list[_MidiEvent] = []
        active_notes: set[int] = set()
        physical_notes: set[int] = set()
        pedal_value = 0
        pedal_controlled = False
        for event in ordered:
            timestamp = max(minimum_time, float(event.at_seconds))
            note = max(0, min(127, int(event.note)))
            if event.kind == 'end':
                normalized.append(_MidiEvent(timestamp, 'end', 0, 0))
                continue
            if event.kind == 'pedal':
                normalized.append(_MidiEvent(timestamp, 'pedal', 0,
                    max(0, min(127, int(event.velocity))), controls_damping=event.controls_damping,
                    pedal_source=event.pedal_source, pedal_input_value=event.pedal_input_value,
                    recapture_owned=event.recapture_owned))
                pedal_value = event.velocity
                pedal_controlled = event.controls_damping
                continue
            if event.kind == "note_on":
                velocity = max(1, min(127, int(event.velocity)))
                if note in active_notes:
                    normalized.append(_MidiEvent(at_seconds=timestamp, kind="note_off", note=note, velocity=0,
                        key_release_fallback=False, damping_resonance=False, native_release=True))
                    active_notes.discard(note)
                normalized.append(_MidiEvent(at_seconds=timestamp, kind="note_on", note=note, velocity=velocity,
                    key_held=event.key_held, strike_age_seconds=event.strike_age_seconds))
                active_notes.add(note)
                if event.key_held:
                    physical_notes.add(note)
                else:
                    physical_notes.discard(note)
                continue
            if event.kind == 'key_release':
                if note in active_notes and note in physical_notes:
                    normalized.append(_MidiEvent(timestamp, 'key_release', note, 0))
                    physical_notes.discard(note)
                continue
            if event.kind == 'all_notes_off':
                if pedal_controlled and pedal_value != 0:
                    normalized.append(_MidiEvent(timestamp, 'pedal', 0, 0,
                        controls_damping=True, pedal_source='panic'))
                    pedal_value = 0
                if normalized:
                    normalized.append(_MidiEvent(timestamp, 'all_notes_off', 0, 0))
                active_notes.clear()
                physical_notes.clear()
                continue
            if event.kind == "note_off":
                if note not in active_notes:
                    continue
                normalized.append(_MidiEvent(at_seconds=timestamp, kind="note_off", note=note, velocity=0,
                    key_release_fallback=event.key_release_fallback, damping_resonance=event.damping_resonance))
                active_notes.discard(note)
                physical_notes.discard(note)

        if active_notes:
            last_timestamp = normalized[-1].at_seconds if normalized else 0.0
            for note in sorted(active_notes):
                normalized.append(_MidiEvent(at_seconds=last_timestamp, kind="note_off", note=note, velocity=0,
                    key_release_fallback=False, damping_resonance=False))
        if pedal_controlled and pedal_value >= 64 and normalized:
            normalized.append(_MidiEvent(normalized[-1].at_seconds, 'pedal', 0, 0,
                controls_damping=True, pedal_source='take_end'))
        if not any(event.kind == 'note_on' for event in normalized):
            return []
        return normalized

    def _relative_time(self, timestamp: float | None) -> float:
        point = time.monotonic() if timestamp is None else float(timestamp)
        return max(0.0, point - self._start_time)
