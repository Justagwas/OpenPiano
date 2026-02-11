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
  <a href="https://Justagwas.com/projects/openpiano">Website</a>
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

It is built to be lightweight and non-dependent on cloud accounts or online dependencies.

## Basic usage

1. Download and install OpenPiano from the [latest Windows release](https://github.com/Justagwas/OpenPiano/releases/latest/download/OpenPianoSetup.exe).
2. Launch the app and play.  
Optionally:
1. Check out the `Tutorial`.
2. Pick a keyboard layout (`61-key` or `88-key`).  
3. Play with either form: keyboard, mouse, or MIDI device.  
4. Change the SoundFont/instrument. 
5. Record a take and export it as `.mid`.  

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

## Input Methods

OpenPiano supports three input paths in the same session:

- `Keyboard`: play directly with your keyboard when no external controller is connected.
- `Mouse`: click and drag on keys for quick testing and note checks.
- `MIDI`: connect a MIDI keyboard/device and select it in the input dropdown.

## SoundFonts and Instruments

Use SoundFonts to change tone instantly while keeping the same play workflow.

- Supports `.sf2` and `.sf3` instruments
- Bank and preset selection for compatible SoundFonts

## Recording and MIDI Export

Record takes directly in the app and export standard MIDI files.

- Capture live play from keyboard, mouse, or MIDI input
- Export to `.mid` for DAW editing, arrangement, or archive

## Configuration

OpenPiano persists app settings in [`OpenPiano_config.json`](https://github.com/Justagwas/OpenPiano/blob/main/OpenPiano/OpenPiano_config.json).

Save location behavior:

- Portable/writable mode: next to the app executable (or next to `OpenPiano.py` in source runs)
- Fallback mode: `%LOCALAPPDATA%\OpenPiano\OpenPiano_config.json`

## Supported Formats

- SoundFonts: `.sf2`, `.sf3`
- MIDI export: `.mid`

## Preview

- Project page with full preview gallery: [justagwas.com/projects/openpiano](https://www.justagwas.com/projects/openpiano)
- OpenPiano Installer Download link: [justagwas.com/projects/openpiano/download](https://www.justagwas.com/projects/openpiano/download)

<details>
<summary>For Developers</summary>

### Requirements

- Python 3.11+

Main dependencies are managed in [`OpenPiano/requirements.txt`](https://github.com/Justagwas/OpenPiano/blob/main/OpenPiano/requirements.txt) (`PySide6`, `pyfluidsynth`, `mido`, `python-rtmidi`).

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

### Build (optional)

```powershell
cd OpenPiano
py -m PyInstaller -F -w --name OpenPiano --icon icon.ico --clean --add-data "icon.ico;." --add-binary "third_party\fluidsynth\bin\*;third_party\fluidsynth\bin" --hidden-import fluidsynth --hidden-import mido --hidden-import mido.backends.rtmidi --hidden-import rtmidi --exclude-module numpy OpenPiano.py
```

Build artifacts are produced in `OpenPiano/dist/`.

### Configuration Files (developer-relevant)

- Runtime settings: [`OpenPiano_config.json`](https://github.com/Justagwas/OpenPiano/blob/main/OpenPiano/OpenPiano_config.json)
- App constants and URLs: [`OpenPiano/openpiano/core/config.py`](https://github.com/Justagwas/OpenPiano/blob/main/OpenPiano/openpiano/core/config.py)
- Build/runtime assets: [`OpenPiano/icon.ico`](https://github.com/Justagwas/OpenPiano/blob/main/OpenPiano/icon.ico), [`OpenPiano/third_party/fluidsynth/bin/`](https://github.com/Justagwas/OpenPiano/tree/main/OpenPiano/third_party/fluidsynth/bin)

</details>

## Security and OS Warnings

- OpenPiano is open source and intended for local desktop use.
- Windows SmartScreen may display "Protected your PC" for newer/unsigned binaries.
- Only run installers downloaded from official OpenPiano release links.
- For private vulnerability reporting, follow [`.github/SECURITY.md`](https://github.com/Justagwas/OpenPiano/blob/main/.github/SECURITY.md).

## Contributing

Contributions are welcome.

Please read [`.github/CONTRIBUTING.md`](https://github.com/Justagwas/OpenPiano/blob/main/.github/CONTRIBUTING.md) before opening issues or pull requests.

## License

Apache License 2.0. See [`LICENSE`](https://github.com/Justagwas/OpenPiano/blob/main/LICENSE).

## Contact

- Email: [email@justagwas.com](mailto:email@justagwas.com)
- Website: <https://www.justagwas.com/projects/openpiano>
