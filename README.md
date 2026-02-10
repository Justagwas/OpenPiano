# OpenPiano

OpenPiano is a desktop piano app built with PySide6.

It supports QWERTY play, mouse play, MIDI input, SoundFont instruments, and MIDI recording, with a modern UI and tutorial flow.

## Highlights

- 61-key and 88-key modes
- QWERTY key mapping with on-key labels
- SoundFont instrument, bank, and preset selection
- MIDI In device support (`mido` + `python-rtmidi`)
- MIDI recording and export (`.mid`)
- Stats bar (volume, sustain, KPS, held, polyphony, transpose)
- Theme, UI scale, animation speed, and key color settings
- Built-in update check hooks

## Project Layout

This repository uses a nested app folder:

```text
OpenPiano/
  README.md
  .github/
  OpenPiano/
    OpenPiano.py
    openpiano/
    fonts/
    third_party/
    requirements.txt
```

## Requirements

- Windows 10/11 (primary target)
- Python 3.11+
- FluidSynth runtime files (already included under `OpenPiano/third_party/fluidsynth/bin`)

Install dependencies:

```powershell
cd OpenPiano
py -m pip install -r requirements.txt
```

## Run From Source

```powershell
cd OpenPiano
py OpenPiano.py
```

## Build (PyInstaller)

Run from the `OpenPiano/` app folder:

```powershell
cd OpenPiano
py -m PyInstaller -F -w -i "icon.ico" --version-file="version.txt" --name "OpenPiano" --clean --add-data "fonts;fonts" --add-binary "third_party\fluidsynth\bin\*;fluidsynth" OpenPiano.py
```

## Configuration

Settings are saved to:

```text
%LOCALAPPDATA%\OpenPiano\OpenPiano_config.json
```

## Website

- https://www.justagwas.com/projects/openpiano

## Contributing

Please read `.github/CONTRIBUTING.md`.

## Security

Please read `.github/SECURITY.md`.

## License

Apache License 2.0. See `LICENSE`.
