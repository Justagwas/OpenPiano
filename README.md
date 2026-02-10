<p align="center">
  <img
    width="192"
    height="192"
    alt="OpenPiano Logo"
    src="https://github.com/user-attachments/assets/dc0be90d-30fe-40c0-9dd1-a0415daa777f"
  />
</p>

<h1 align="center">OpenPiano</h1>

<h3 align="center">Play piano with your keyboard, mouse, or MIDI device</h3>

<p align="center">
  A local-first desktop piano for practice, composition, and sound design<br/>
  with SoundFonts, real-time controls, and MIDI recording/export.
</p>

<p align="center">
  <a href="https://github.com/Justagwas/OpenPiano/releases/latest/download/OpenPianoSetup.exe">
    <img
      src="https://img.shields.io/badge/Download%20for%20Windows-2563eb?style=for-the-badge&logo=windows&logoColor=white"
      alt="Download OpenPiano for Windows"
    />
  </a>
</p>

<p align="center">
  <a href="https://Justagwas.com/projects/OpenPiano">Website</a>
  &nbsp;•&nbsp;
  <a href="https://github.com/Justagwas/OpenPiano/releases">Releases</a>
  &nbsp;•&nbsp;
  <a href="https://github.com/Justagwas/OpenPiano/issues">Issues</a>
  &nbsp;•&nbsp;
  <a href="https://github.com/Justagwas/OpenPiano/wiki">Documentation</a>
  &nbsp;•&nbsp;
  <a href="https://github.com/Justagwas/OpenPiano/blob/main/LICENSE">License</a>
</p>

---

## Overview

OpenPiano is a Windows desktop piano app that lets you play and practice using your PC keyboard, mouse, or a MIDI controller.

It is built for fast local workflows: audition SoundFonts, rehearse phrases, and export MIDI takes without cloud accounts or online dependencies.

## Basic usage

1. Download and install OpenPiano from the Windows release link above.
2. Launch the app and pick a keyboard layout (`61-key` or `88-key`).
3. Choose an input method (QWERTY keyboard, mouse, or MIDI device).
4. Select a SoundFont/instrument, then play.
5. Optionally record a take and export it as `.mid`.

## Features

- 61-key and 88-key layouts with live key feedback
- QWERTY keyboard play with key-label support
- Mouse play and drag interaction
- MIDI input device support
- SoundFont support (`.sf2`, `.sf3`) with bank/preset selection
- Real-time controls for volume, velocity, sustain, and transpose
- MIDI recording and `.mid` export
- Stats display (KPS, held keys, polyphony, transpose, sustain)
- Theme, UI scale, animation speed, and key color customization
- Built-in update checking

## Input Methods

OpenPiano supports three input paths in the same session:

- `Keyboard`: play directly from QWERTY when no external controller is connected.
- `Mouse`: click and drag on keys for quick testing and note checks.
- `MIDI`: connect a MIDI keyboard/device and select it in the input dropdown.

## SoundFonts and Instruments

Use SoundFonts to change tone instantly while keeping the same play workflow.

- Supports `.sf2` and `.sf3` instruments
- Bank and preset selection for compatible SoundFonts
- Bundled fonts are available in `OpenPiano/fonts`

## Recording and MIDI Export

Record takes directly in the app and export standard MIDI files.

- Capture live play from keyboard, mouse, or MIDI input
- Export to `.mid` for DAW editing, arrangement, or archive

## Configuration

OpenPiano persists app settings in `OpenPiano_config.json`.

Save location behavior:

- Portable/writable mode: next to the app executable (or next to `OpenPiano.py` in source runs)
- Fallback mode: `%LOCALAPPDATA%\OpenPiano\OpenPiano_config.json`

## Supported Formats

- SoundFonts: `.sf2`, `.sf3`
- MIDI export: `.mid`

## Preview

- Project page with full preview gallery: `https://www.justagwas.com/projects/openpiano`
- Download page and release details: `https://www.justagwas.com/projects/openpiano/download`

<details>
<summary>For Developers</summary>

### Requirements

- Windows 10/11
- Python 3.11+
- `pip`

Main dependencies are managed in `OpenPiano/requirements.txt` (`PySide6`, `pyfluidsynth`, `mido`, `python-rtmidi`).

### Running From Source

```powershell
cd OpenPiano
py -m pip install -r requirements.txt
py OpenPiano.py
```

If your environment has resolver issues, install core packages directly:

```powershell
py -m pip install PySide6 pyfluidsynth mido python-rtmidi
```

### Testing (optional)

```powershell
cd OpenPiano
py -m unittest discover -s tests -p "test_*.py" -v
```

### Build (optional)

```powershell
cd OpenPiano
py -m PyInstaller OpenPiano.spec
```

Build artifacts are produced in `OpenPiano/dist/`.

### Configuration Files (developer-relevant)

- Runtime settings: `OpenPiano_config.json`
- App constants and URLs: `OpenPiano/openpiano/core/config.py`
- Packaging spec: `OpenPiano/OpenPiano.spec`

</details>

## Security and OS Warnings

- OpenPiano is open source and intended for local desktop use.
- Windows SmartScreen may display "Protected your PC" for newer/unsigned binaries.
- Only run installers downloaded from official OpenPiano release links.
- For private vulnerability reporting, follow `.github/SECURITY.md`.

## Contributing

Contributions are welcome.

Please read `.github/CONTRIBUTING.md` before opening issues or pull requests.

## License

Apache License 2.0. See `LICENSE`.

## Contact

`email@justagwas.com`
