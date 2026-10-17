# OpenPiano

<div align="center">

[![Code: GitHub](https://img.shields.io/badge/Code-GitHub-111827.svg?style=flat&logo=github&logoColor=white)](https://github.com/Justagwas/openpiano)
[![Website](https://img.shields.io/badge/Website-OpenPiano-0ea5e9.svg?style=flat&logo=google-chrome&logoColor=white)](https://www.justagwas.com/projects/openpiano/)
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

<p align="center"><b>Play, practice, and record piano on your computer.</b></p>

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

OpenPiano turns your Windows computer into a playable piano. Start with the computer keyboard or mouse, connect a MIDI controller such as a musical keyboard, and watch every note appear on the piano as you play.

Choose a 61 or 88 key layout, personalize the controls and appearance, explore different instrument sounds, and record an idea without leaving the application.

## Features

- 61 and 88 key piano layouts with clear visual feedback.
- Computer keyboard, mouse, and MIDI controller input in the same session.
- Included Default and Grand Piano sounds, an optional Steinway D-274 download, and compatible SF2/SF3 instrument files.
- Custom key mappings with save, discard, and undo.
- Adjustable volume, note strength, sustain, pitch, animation speed, and interface size.
- Themes and individual piano key colors.
- A built-in tutorial that can be reopened at any time.
- Performance recording to editable MIDI notes or rendered WAV audio.
- Local playing and recording without an account, with installer and standalone versions.

## Basic usage

1. Get the [Windows installer or standalone app](https://www.justagwas.com/projects/openpiano/). Choose the installer for a normal setup, or standalone to run without installing.
2. Launch OpenPiano and choose your computer-keyboard layout when prompted.
3. Choose the 61 or 88 key range under **Settings > Keyboard**.
4. Play with the labeled computer keys, click or glide across the piano, or select a connected MIDI controller.
5. Open **Controls** to choose an instrument or MIDI input. Use **Settings > Sound** to adjust volume, velocity (note strength), sustain, or transpose (pitch).
6. Select **Start Recording** when you want to keep a performance.
7. Select **Stop Recording**, then **Save recording**. Choose `.mid` for editable notes or `.wav` for rendered audio, and select where to save it.

Save a take before starting another recording; a new take replaces the previous one in memory. The Windows app includes two piano sounds, so you can start playing without a separate sound download.

## Using OpenPiano

### Make the keyboard your own

Show the note names or computer-key labels you need, then customize the mappings under **Settings > Keyboard > Change Keybinds**. Assign notes to different keys, undo an assignment with **Ctrl+Z**, and choose **Save** or **Discard** when finished.

The computer keyboard and mouse use the note strength set under **Settings > Sound**. A MIDI controller supplies its own note strength and can send sustain-pedal input. The [playing guide](https://github.com/Justagwas/OpenPiano/wiki/Playing-OpenPiano) explains sustain, transpose, and keyboard ranges.

### Choose your sound

OpenPiano includes Default and Grand Piano SoundFonts, listed as **OpenPiano Built-in**. A SoundFont is an instrument sound file. For another piano sound, use **Settings > Download Hi-Fi D-274 Piano (~400 MB)**. The optional Steinway D-274 download is listed as **OpenPiano External**. You can also add compatible SF2 or SF3 files to `%LOCALAPPDATA%\OpenPiano\soundfonts`, then restart the app.

Use **Controls** to select the instrument, bank and preset. Adjust volume, note strength, sustain and pitch in **Settings > Sound**.

The included SoundFonts use calibrated preset levels to reduce volume jumps while preserving touch response. 100% is the standard level; the range up to 200% provides additional gain and can engage overload protection during louder playing. WAV export uses the same preset levels.

### Keep the performance

Save a take as MIDI when you want to edit its notes, timing, velocity and recorded sustain-pedal events in music software. MIDI does not include the instrument sound. Choose WAV for a stereo audio file rendered with the SoundFont, bank, preset and volume selected when you export. WAV is rendered from the take; it is not a recording of every live sound-setting change.

### Installer, standalone and local files

Both Windows versions include the components and piano sounds needed to start playing. No separate Python installation or sound download is required.

Settings and user SoundFonts normally stay under `%LOCALAPPDATA%\OpenPiano`, including with standalone. Moving the executable does not move those files. Save recordings to the location you choose. Playing and recording work locally; updates, optional downloads, and links you open can use the internet.

## Project resources

- Project page: <https://www.justagwas.com/projects/openpiano/>
- Download page: <https://www.justagwas.com/projects/openpiano/download/>
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
  - <https://www.justagwas.com/projects/openpiano/download/>
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
- Website: <https://www.justagwas.com/projects/openpiano/>

## License

Licensed under the GNU General Public License v3.0 (GPL-3.0).

See [`LICENSE`](https://github.com/Justagwas/OpenPiano/blob/main/LICENSE).
