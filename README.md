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
    src="OpenPiano/icon.ico"
  />
</p>

<div align="center">

[![Download (Windows)](https://img.shields.io/badge/Download-Windows%20(OpenPianoSetup.exe)-2563eb.svg?style=flat&logo=windows&logoColor=white)](https://github.com/Justagwas/OpenPiano/releases/latest/download/OpenPianoSetup.exe)

</div>

<p align="center"><b>A desktop piano for playing, practice, and quick musical ideas</b></p>

<p align="center">Play with a computer keyboard, mouse, or MIDI controller, choose your sound, and record the performance when it is worth keeping</p>

<div align="center">

[![Version](https://img.shields.io/github/v/tag/Justagwas/openpiano.svg?label=Version)](https://github.com/Justagwas/openpiano/tags)
[![License](https://img.shields.io/github/license/Justagwas/openpiano.svg)](https://github.com/Justagwas/openpiano/blob/main/LICENSE)
[![Last Commit](https://img.shields.io/github/last-commit/Justagwas/openpiano/main.svg?style=flat&cacheSeconds=3600)](https://github.com/Justagwas/openpiano/commits/main)
[![Open Issues](https://img.shields.io/github/issues/Justagwas/openpiano.svg)](https://github.com/Justagwas/openpiano/issues)
[![Stars](https://img.shields.io/github/stars/Justagwas/openpiano.svg?style=flat&cacheSeconds=3600)](https://github.com/Justagwas/openpiano/stargazers)
![Downloads (7d)](https://img.shields.io/badge/dynamic/json?style=flat&url=https%3A%2F%2Fdownload-stats-worker.justagwas.workers.dev%2Fdownloads%2Fopenpiano%3Frange%3Dweek&query=%24.data.weekly.all&label=Downloads%20(7d))

</div>

## Overview

OpenPiano turns a Windows computer into a playable piano. Start with the computer keyboard or mouse, connect a MIDI controller when you want a more traditional feel, and watch every note appear on the piano as you play.

Choose a 61 or 88 key layout, personalize the controls and appearance, explore different instrument sounds, and record an idea without leaving the application.

OpenPiano's performance:  
  ~0% CPU usage while idle.  
  ~1% CPU usage during active use.  
  ~90 MB memory footprint.  

## Basic usage

1. Download and install from the [latest release](https://github.com/Justagwas/OpenPiano/releases/latest/download/OpenPianoSetup.exe).  
2. Launch OpenPiano.  
3. Choose the 61 or 88 key piano.
4. Play with the labeled computer keys, click or glide across the piano, or select a connected MIDI controller.
5. Open **Controls** to choose an instrument and adjust volume, touch, sustain, or pitch.
6. Select **Start Recording** when you want to keep a performance.
7. Save the take as editable MIDI or ready to play WAV audio.

## Features

- 61 and 88 key piano layouts with clear visual feedback.
- Computer keyboard, mouse, and MIDI controller input in the same session.
- Included sounds and support for compatible SF2 or SF3 instrument sound files.
- Custom key mappings with save, discard, and undo.
- Controls for volume, touch, sustain, pitch, animation speed, interface size, and more.
- Themes and individual piano key colors.
- A built in tutorial that can be reopened at any time.
- Recording to editable MIDI or ready to play WAV audio.
- Local operation without an account or performance tracking.

## Using OpenPiano

### Play your way

All three input methods can be used in the same session:

- Follow the labels and play from the computer keyboard.
- Click or drag across the piano with a mouse.
- Connect a MIDI controller for a more traditional playing experience.

The piano display, instrument sound, sustain, and recorder follow the same performance, so changing input method feels natural.

### Choose your sound

OpenPiano includes both its compact default piano and a richer Grand Piano sound, so you can begin immediately. Optionally, you can add your own Soundfont.

Use the Controls panel to select an instrument and adjust the playing experience without leaving the main piano.

The included soundfonts use calibrated preset levels to reduce volume jumps while preserving touch response. 100% is the standard level; the range up to 200% provides additional gain and can engage overload protection during louder playing. WAV export uses the same preset levels.

### Keep the performance

Save a take as MIDI when you want to edit its notes later. Choose WAV when you want an audio file that already sounds the way it did in OpenPiano.

## Project resources

- Project page: <https://www.justagwas.com/projects/openpiano>
- Download page: <https://www.justagwas.com/projects/openpiano/download>
- Documentation: <https://github.com/Justagwas/OpenPiano/wiki>
- Releases: <https://github.com/Justagwas/OpenPiano/releases>

<details>
<summary>For Developers</summary>

### Requirements

- Windows (primary runtime target).
- Python 3.11 or later.
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

- Windows SmartScreen may display a warning for a new or unsigned release.
- Obtain OpenPiano only from the official distribution locations:
  - <https://github.com/Justagwas/OpenPiano/releases>
  - <https://www.justagwas.com/projects/openpiano/download>
  - <https://sourceforge.net/projects/openpiano/>
- Refer to the repository [Security Policy](https://github.com/Justagwas/OpenPiano/security/policy) for private vulnerability reporting.

## Contributing

Contributions are welcome.

- Start with [`.github/CONTRIBUTING.md`](https://github.com/Justagwas/OpenPiano/blob/main/.github/CONTRIBUTING.md)
- Follow the shared [Code of Conduct](https://github.com/Justagwas/.github/blob/main/CODE_OF_CONDUCT.md)
- Use [Issues](https://github.com/Justagwas/OpenPiano/issues) for defect reports, feature proposals, and questions
- Wiki: <https://github.com/Justagwas/OpenPiano/wiki>

## Contact

- Email: [email@justagwas.com](mailto:email@justagwas.com)
- Website: <https://www.justagwas.com/projects/openpiano>

## License

Licensed under the GNU General Public License v3.0 (GPL-3.0).

See [`LICENSE`](https://github.com/Justagwas/OpenPiano/blob/main/LICENSE).
