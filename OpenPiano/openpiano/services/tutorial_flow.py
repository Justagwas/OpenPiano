from __future__ import annotations

from typing import Literal, TypeAlias


PianoMode: TypeAlias = Literal["61", "88"]
TutorialStep: TypeAlias = dict[str, str | bool]


class TutorialFlowService:
    def __init__(self) -> None:
        self._active = False
        self._steps: list[TutorialStep] = []
        self._index = 0

    @staticmethod
    def build_default_steps() -> list[TutorialStep]:
        return [
            {
                "id": "welcome",
                "title": "Welcome",
                "body": "This tutorial walks through the core controls. Click Next to begin.",
                "target": "",
            },
            {
                "id": "piano",
                "title": "Piano",
                "body": "Use your keyboard or mouse to play notes. Pressed keys highlight instantly.",
                "target": "piano",
            },
            {
                "id": "stats",
                "title": "Stats Bar",
                "body": "Live values show volume, sustain state, Keys Per Second, held notes, polyphony, and transpose.",
                "target": "stats",
            },
            {
                "id": "footer",
                "title": "Footer Actions",
                "body": "Use footer links to open settings, controls, hide stats, open the official website, or relaunch this tutorial from the right side.",
                "target": "footer",
            },
            {
                "id": "controls_toggle",
                "title": "Controls Toggle",
                "body": "Use Controls for frequent actions like changing Instrument (soundfonts), MIDI In, quick note mute, and recording.",
                "target": "controls_toggle",
            },
            {
                "id": "controls_section",
                "title": "Controls Panel",
                "body": "This panel keeps live performance controls in one place.",
                "target": "controls_section",
                "open_controls": True,
            },
            {
                "id": "controls_instrument",
                "title": "Instrument and Program",
                "body": "Select instrument, bank, and preset here. By default the DEFAULT and GRAND PIANO soundfonts are pinned.",
                "target": "controls_instrument",
                "open_controls": True,
            },
            {
                "id": "controls_midi",
                "title": "MIDI Input",
                "body": "Pick a MIDI input device to play from external hardware. The list refreshes each time you open this dropdown, even when no devices are currently available.",
                "target": "controls_midi",
                "open_controls": True,
            },
            {
                "id": "controls_recording",
                "title": "Recording",
                "body": "Start/stop MIDI recording here, then use Save recording to export a .mid take.",
                "target": "controls_recording",
                "open_controls": True,
            },
            {
                "id": "controls_all_notes_off",
                "title": "All Notes OFF",
                "body": "If any note gets stuck, click All Notes OFF to immediately silence all active notes.",
                "target": "controls_all_notes_off",
                "open_controls": True,
            },
            {
                "id": "settings_toggle",
                "title": "Settings Toggle",
                "body": "This button shows or hides the settings panel.",
                "target": "settings_toggle",
            },
            {
                "id": "sound_section",
                "title": "Sound Settings",
                "body": "Tune volume, velocity, transpose, and sustain behavior in this section.",
                "target": "sound_section",
                "open_settings": True,
            },
            {
                "id": "sound_velocity",
                "title": "Velocity",
                "body": "Velocity sets note attack strength for QWERTY and mouse input (1-127). External MIDI input keeps the velocity from your hardware.",
                "target": "sound_velocity",
                "open_settings": True,
            },
            {
                "id": "soundfont_folder",
                "title": "Custom SoundFonts",
                "body": "To use your own soundfonts, place .sf2 or .sf3 files in this folder:\n{soundfonts_dir}",
                "target": "sound_section",
                "open_settings": True,
            },
            {
                "id": "keyboard_section",
                "title": "Keyboard Settings",
                "body": "Switch key range and toggle keyboard/note labels.",
                "target": "keyboard_section",
                "open_settings": True,
            },
            {
                "id": "keyboard_keybinds",
                "title": "Change Keybinds",
                "body": "Click Change Keybinds to enter focused edit mode. While active, other controls are blocked. Select a piano key, press a keyboard/mouse combination, use Ctrl+Z to undo the last change, then press Save to apply or Discard to cancel.",
                "target": "keyboard_keybinds",
                "open_settings": True,
            },
            {
                "id": "keyboard_88_mode",
                "title": "88-Key Mode",
                "body": "88-key mode is available here. The extra keys can be played using Ctrl + (letter), indicated with C + (letter).",
                "target": "keyboard_section",
                "open_settings": True,
                "set_mode": "88",
            },
            {
                "id": "interface_section",
                "title": "Interface Settings",
                "body": "Theme, UI size, animation speed, key colors, and updates are here.",
                "target": "interface_section",
                "open_settings": True,
            },
            {
                "id": "reset_defaults",
                "title": "Reset Defaults",
                "body": "Reset everything back to default values when needed.",
                "target": "reset_defaults",
                "open_settings": True,
            },
            {
                "id": "finish",
                "title": "Done",
                "body": "Tutorial complete. Click Finish to close this guide.",
                "target": "",
            },
        ]

    def start(self) -> bool:
        if self._active:
            return False
        steps = self.build_default_steps()
        if not steps:
            return False
        self._active = True
        self._steps = steps
        self._index = 0
        return True

    def end(self) -> None:
        self._active = False
        self._steps = []
        self._index = 0

    @property
    def active(self) -> bool:
        return self._active

    @property
    def steps(self) -> list[TutorialStep]:
        return list(self._steps)

    @property
    def index(self) -> int:
        return self._index

    def current_step(self) -> TutorialStep | None:
        if not self._active:
            return None
        if self._index < 0 or self._index >= len(self._steps):
            return None
        return self._steps[self._index]

    def advance(self) -> bool:
        if not self._active:
            return False
        if self._index >= len(self._steps) - 1:
            return False
        self._index += 1
        return True

    def rewind(self) -> bool:
        if not self._active:
            return False
        if self._index <= 0:
            return False
        self._index -= 1
        return True
