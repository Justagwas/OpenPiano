from pathlib import Path
import os
import shutil
import subprocess
import argparse

ROOT = Path(__file__).resolve().parents[1]


def build(destination: Path | None = None) -> None:
    finder = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Microsoft Visual Studio/Installer/vswhere.exe'
    installation = subprocess.check_output([
        str(finder), '-latest', '-prerelease', '-products', '*', '-requires',
        'Microsoft.VisualStudio.Component.VC.Tools.x86.x64', '-property', 'installationPath',
    ], text=True).strip()
    if not installation:
        raise RuntimeError('Install the Visual C++ x64 build tools before building audio_output.c.')
    tools = sorted((Path(installation) / 'VC/Tools/MSVC').iterdir())[-1]
    sdk = Path(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)')) / 'Windows Kits/10'
    sdk_version = sorted((sdk / 'Include').iterdir())[-1].name
    build_env = os.environ.copy()
    compiler = tools / 'bin/Hostx64/x64/cl.exe'
    build_env['PATH'] = str(compiler.parent) + os.pathsep + build_env.get('PATH', '')
    build_env['INCLUDE'] = os.pathsep.join(map(str, [tools / 'include', *[
        sdk / 'Include' / sdk_version / name for name in ('ucrt', 'shared', 'um')]]))
    build_env['LIB'] = os.pathsep.join(map(str, [tools / 'lib/x64', *[
        sdk / 'Lib' / sdk_version / name / 'x64' for name in ('ucrt', 'um')]]))
    destination = destination or ROOT / 'third_party/fluidsynth/bin/openpiano_audio.dll'
    destination = destination.resolve()
    folder = destination.parent / 'objects' if destination.parent != ROOT / 'third_party/fluidsynth/bin' else ROOT / 'build/native-audio'
    folder.mkdir(parents=True, exist_ok=True)
    objects = []
    for name in ('audio_output.c', 'wasapi_output.cpp'):
        obj = folder / (Path(name).stem + '.obj')
        subprocess.run([
            str(compiler), '/nologo', '/c', '/O2', '/W4', '/WX', '/MT', '/fp:precise',
            '/EHsc', '/GR-', str(ROOT / 'native' / name), f'/Fo{obj}',
        ], cwd=folder, env=build_env, check=True)
        objects.append(str(obj))
    subprocess.run([
        str(compiler), '/nologo', '/LD', *objects, 'ole32.lib', 'avrt.lib',
        '/link', '/Brepro', f'/OUT:{folder / "openpiano_audio.dll"}',
        f'/IMPLIB:{folder / "openpiano_audio.lib"}',
    ], cwd=folder, env=build_env, check=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(folder / 'openpiano_audio.dll', destination)
    print(f'Built {destination} ({destination.stat().st_size:,} bytes).')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Build the Windows x64 callback helper using installed Visual C++ tools.')
    parser.add_argument('--output', type=Path, help='Build a trial DLL without replacing the shipped helper.')
    build(parser.parse_args().output)
