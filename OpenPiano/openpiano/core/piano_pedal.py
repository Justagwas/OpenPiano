from __future__ import annotations


class PedalState:

    def __init__(self) -> None:
        self.midi_value: int | None = None
        self.space_down = False
        self.restore_automatic_after_space = False

    @property
    def controls_damping(self) -> bool:
        return self.midi_value is not None

    @property
    def value(self) -> int:
        return max(self.midi_value or 0, 127 if self.space_down else 0)

    @property
    def down(self) -> bool:
        return self.value >= 64

    def set_midi(self, value: int) -> None:
        self.midi_value = max(0, min(127, int(value)))
        self.restore_automatic_after_space = False

    def reset(self) -> None:
        self.midi_value = None
        self.space_down = False
        self.restore_automatic_after_space = False
