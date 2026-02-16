# OpenPiano

<div align="center">

[![Code: GitHub](https://img.shields.io/badge/Code-GitHub-111827.svg?style=flat&logo=github&logoColor=white)](https://github.com/Justagwas/openpiano)
[![Website](https://img.shields.io/badge/Website-OpenPiano-0ea5e9.svg?style=flat&logo=google-chrome&logoColor=white)](https://Justagwas.com/projects/openpiano)
[![Mirror: SourceForge](https://img.shields.io/badge/Mirror-SourceForge-ff6600.svg?style=flat&logo=sourceforge&logoColor=white)](https://sourceforge.net/projects/openpiano/)

</div>

<p align="center">
  <img
    width="128"
    height="128"
    alt="OpenPiano Logo"
    src="https://github.com/user-attachments/assets/dc0be90d-30fe-40c0-9dd1-a0415daa777f"
  />
</p>

<div align="center">

[![Download (Windows)](https://img.shields.io/badge/Download-Windows%20(OpenPianoSetup.exe)-2563eb.svg?style=flat&logo=windows&logoColor=white)](https://github.com/Justagwas/OpenPiano/releases/latest/download/OpenPianoSetup.exe)

</div>

<p align="center"><b>Lightweight desktop piano you can play instantly with keyboard, mouse, or MIDI</b></p>

<p align="center">OpenPiano is a Windows desktop piano instrument for practice, composition and sound design with SoundFonts, real-time controls, and MIDI recording/export</p>

<div align="center">

[![Version](https://img.shields.io/github/v/tag/Justagwas/OpenPiano.svg?label=Version)](
https://github.com/Justagwas/OpenPiano/tags)
[![Last Commit](https://img.shields.io/github/last-commit/Justagwas/OpenPiano/main.svg?style=flat&cacheSeconds=3600)](
https://github.com/Justagwas/OpenPiano/commits/main)
[![Stars](https://img.shields.io/github/stars/Justagwas/OpenPiano.svg?style=flat&cacheSeconds=3600)](
https://github.com/Justagwas/OpenPiano/stargazers)
[![Open Issues](https://img.shields.io/github/issues/Justagwas/OpenPiano.svg)](
https://github.com/Justagwas/OpenPiano/issues)
[![License](https://img.shields.io/github/license/Justagwas/OpenPiano.svg)](
https://github.com/Justagwas/OpenPiano/blob/main/LICENSE)

</div>

## Overview

OpenPiano is a Windows desktop piano application that lets you play using your computer keyboard, mouse, or a connected MIDI device. It supports 61- and 88-key layouts, customizable keybindings, SoundFont routing, and MIDI recording/export.  

OpenPiano's performance:  
  ~0% CPU usage while idle.  
  ~1% CPU usage during active use.  
  ~90 MB memory footprint.  

## Basic usage

1. Download and install from the [latest release](https://github.com/Justagwas/OpenPiano/releases/latest/download/OpenPianoSetup.exe).  
2. Launch OpenPiano.  
3. Play with keyboard, mouse, or MIDI controller.  
4. Choose your play mode (`61 Keys` or `88 Keys`).  
5. Pick an instrument/program and optional MIDI input device.  
6. Record and export a `.mid` take when needed.  

## Features

- Keyboard, mouse, and MIDI input in one app session.
- 61-key and 88-key layouts with live visual key feedback.
- SoundFont instrument routing (`.sf2` / `.sf3`) with bank/preset selection.
- Custom keybind edit mode with Save, Discard, and undo (`Ctrl+Z`).
- Real-time controls for volume, velocity, sustain, transpose, animation speed, UI scale and more.
- Theme toggle and per-key color customization.
- Built-in tutorial.
- MIDI recording and `.mid` export.
- Runs entirely locally (no account or internet dependency required).

## Feature sections

### Input Modes

OpenPiano supports:

- keyboard play via the mapped piano layout.
- Mouse click/drag play directly on piano keys.
- External MIDI input device routing from the controls panel.

### SoundFonts and Instruments

OpenPiano discovers and loads SoundFonts for playback through FluidSynth. You can switch instrument, bank, and preset live from the Controls panel.

### Keybind Editing and UI Controls

The app includes a focused keybind editor (Save/Discard flow), UI scaling, theme switching, animation speed controls, and key color controls.

### Recording and Export

OpenPiano can capture note events during a live take and export a standard `.mid` file.

## Preview

- Website project page (overview + gallery): <https://www.justagwas.com/projects/openpiano>
- Download page: <https://www.justagwas.com/projects/openpiano/download>
- Releases: <https://github.com/Justagwas/openpiano/releases>

<details>
<summary>For Developers</summary>

### Requirements

- Windows (primary target runtime).
- Python 3.11+.
- Dependencies in [`OpenPiano/requirements.txt`](https://github.com/Justagwas/OpenPiano/blob/main/OpenPiano/requirements.txt).

### Running From Source

```powershell
cd OpenPiano
py -m pip install -r requirements.txt
py OpenPiano.py
```

### Configuration Files

- App constants and release endpoints: [`OpenPiano/openpiano/core/config.py`](https://github.com/Justagwas/OpenPiano/blob/main/OpenPiano/openpiano/core/config.py)
- Runtime settings serialization logic: [`OpenPiano/openpiano/core/settings_store.py`](https://github.com/Justagwas/OpenPiano/blob/main/OpenPiano/openpiano/core/settings_store.py)
- Theme palette definitions: [`OpenPiano/openpiano/core/theme.py`](https://github.com/Justagwas/OpenPiano/blob/main/OpenPiano/openpiano/core/theme.py)
- Tutorial step content: [`OpenPiano/openpiano/services/tutorial_flow.py`](https://github.com/Justagwas/OpenPiano/blob/main/OpenPiano/openpiano/services/tutorial_flow.py)
- Application entry point: [`OpenPiano/OpenPiano.py`](https://github.com/Justagwas/OpenPiano/blob/main/OpenPiano/OpenPiano.py)

</details>

## Security and OS Warnings

- Windows SmartScreen can show warnings for newer or unsigned binaries.
- Download from official links only:
  - <https://github.com/Justagwas/openpiano/releases>
  - <https://www.justagwas.com/projects/openpiano>
  - <https://sourceforge.net/projects/openpiano>
- Security policy and private vulnerability reporting: [`.github/SECURITY.md`](https://github.com/Justagwas/OpenPiano/blob/main/.github/SECURITY.md)

## Contributing

Contributions are welcome.

- Start with [`.github/CONTRIBUTING.md`](https://github.com/Justagwas/OpenPiano/blob/main/.github/CONTRIBUTING.md)
- Follow [`.github/CODE_OF_CONDUCT.md`](https://github.com/Justagwas/OpenPiano/blob/main/.github/CODE_OF_CONDUCT.md)
- Use [Issues](https://github.com/Justagwas/OpenPiano/issues) for bugs, requests, and questions
- Wiki: <https://github.com/Justagwas/openpiano/wiki>

## License

Licensed under the Apache License 2.0.

See [`LICENSE`](https://github.com/Justagwas/OpenPiano/blob/main/LICENSE).

## Contact

- Email: [email@justagwas.com](mailto:email@justagwas.com)
- Website: <https://www.justagwas.com/projects/openpiano>
