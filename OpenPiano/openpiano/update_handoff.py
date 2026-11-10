from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

if __package__:
    from .update_product import PRODUCT
else:
    from update_product import PRODUCT
_ARMED: Path | None = None
_MAINTENANCE_PENDING = False
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")

from ctypes import wintypes


def sha256_blocks(blocks):
    dll = ctypes.WinDLL("bcrypt")
    handle_type = ctypes.c_void_p
    dll.BCryptOpenAlgorithmProvider.argtypes = [ctypes.POINTER(handle_type), wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.ULONG]
    dll.BCryptCreateHash.argtypes = [handle_type, ctypes.POINTER(handle_type), ctypes.c_void_p, wintypes.ULONG, ctypes.c_void_p, wintypes.ULONG, wintypes.ULONG]
    dll.BCryptHashData.argtypes = [handle_type, ctypes.c_char_p, wintypes.ULONG, wintypes.ULONG]
    dll.BCryptFinishHash.argtypes = [handle_type, ctypes.c_void_p, wintypes.ULONG, wintypes.ULONG]
    dll.BCryptDestroyHash.argtypes = [handle_type]
    dll.BCryptCloseAlgorithmProvider.argtypes = [handle_type, wintypes.ULONG]
    for name in ("BCryptOpenAlgorithmProvider", "BCryptCreateHash", "BCryptHashData", "BCryptFinishHash", "BCryptDestroyHash", "BCryptCloseAlgorithmProvider"):
        getattr(dll, name).restype = wintypes.LONG
    def check(status):
        if status:
            raise OSError("Windows SHA-256 failed: 0x%08X" % (status & 0xffffffff))
    provider, digest = handle_type(), handle_type()
    check(dll.BCryptOpenAlgorithmProvider(ctypes.byref(provider), "SHA256", None, 0))
    try:
        check(dll.BCryptCreateHash(provider, ctypes.byref(digest), None, 0, None, 0, 0))
        try:
            for block in blocks:
                if block:
                    check(dll.BCryptHashData(digest, block, len(block), 0))
            result = ctypes.create_string_buffer(32)
            check(dll.BCryptFinishHash(digest, result, 32, 0))
            return result.raw.hex()
        finally:
            dll.BCryptDestroyHash(digest)
    finally:
        dll.BCryptCloseAlgorithmProvider(provider, 0)




def copy_file(source, destination):
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CopyFileW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.BOOL]
    kernel.CopyFileW.restype = wintypes.BOOL
    if not kernel.CopyFileW(str(source), str(destination), True):
        raise ctypes.WinError(ctypes.get_last_error())


def open_url(url):
    shell = ctypes.WinDLL("shell32", use_last_error=True)
    shell.ShellExecuteW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.c_int]
    shell.ShellExecuteW.restype = ctypes.c_void_p
    return (shell.ShellExecuteW(None, "open", url, None, None, 1) or 0) > 32


def state_root() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    if not base:
        raise RuntimeError("Windows application data is unavailable.")
    return Path(base) / PRODUCT / "update-state"


def _plain_path(path: Path) -> Path:
    path = Path(os.path.abspath(path))
    for part in (path, *path.parents):
        if part.exists():
            info = part.lstat()
            if part.is_symlink() or getattr(info, "st_file_attributes", 0) & 0x400:
                raise RuntimeError("Update paths must not contain links or junctions.")
    return path


def _retry_state_io(operation, *args):
    deadline = time.monotonic() + 2.0
    while True:
        try:
            return operation(*args)
        except OSError as exc:
            retryable = isinstance(exc, PermissionError) or getattr(exc, "winerror", None) in {5, 32, 33}
            if os.name != "nt" or not retryable or time.monotonic() >= deadline:
                raise
            time.sleep(0.02)


def write_state(path: Path, data: dict) -> None:
    _plain_path(path)
    temporary = _plain_path(path.with_name(path.stem + "." + os.urandom(16).hex() + ".tmp"))
    handle = temporary.open("x", encoding="utf-8", newline="\n")
    try:
        with handle:
            json.dump(data, handle, ensure_ascii=True)
            handle.flush()
            os.fsync(handle.fileno())
        _retry_state_io(os.replace, temporary, path)
    finally:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass


def read_state(path: Path) -> dict:
    def read_payload():
        _plain_path(path)
        with path.open("rb") as stream:
            return stream.read(1024 * 1024 + 1)

    payload = _retry_state_io(read_payload)
    if len(payload) > 1024 * 1024:
        raise RuntimeError("Update record is too large.")
    data = json.loads(payload.decode("utf-8"))
    if not isinstance(data, dict) or data.get("product") != PRODUCT:
        raise RuntimeError("Update record belongs to another application.")
    return data


@contextmanager
def state_lease(path: Path, *, root: Path | None = None):
    path = _plain_path(path)
    if path.parent != _plain_path(root if root is not None else state_root()) or not re.fullmatch(r"[0-9a-f]{32}\.json", path.name):
        raise RuntimeError("The update record is outside application storage.")
    lock = _plain_path(path.with_suffix('.lease'))
    stream = lock.open('a+b')
    try:
        if not stream.tell():
            stream.write(b'\0')
            stream.flush()
        stream.seek(0)
        import msvcrt
        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            yield
        finally:
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
    finally:
        stream.close()


def file_version(path: Path) -> str:
    from ctypes import wintypes
    dll = ctypes.WinDLL("version", use_last_error=True)
    dll.GetFileVersionInfoSizeW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD)]
    dll.GetFileVersionInfoSizeW.restype = wintypes.DWORD
    dll.GetFileVersionInfoW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p]
    dll.VerQueryValueW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(wintypes.UINT)]
    size = dll.GetFileVersionInfoSizeW(str(path), None)
    if not size:
        raise RuntimeError("Installed application has no version information.")
    buffer = ctypes.create_string_buffer(size)
    if not dll.GetFileVersionInfoW(str(path), 0, size, buffer):
        raise ctypes.WinError(ctypes.get_last_error())
    pointer, length = ctypes.c_void_p(), wintypes.UINT()
    if not dll.VerQueryValueW(buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)) or length.value < 52:
        raise RuntimeError("Installed application version could not be read.")
    values = ctypes.cast(pointer, ctypes.POINTER(wintypes.DWORD))
    return f"{values[2] >> 16}.{values[2] & 65535}.{values[3] >> 16}"


@contextmanager
def guarded_package(path: Path):
    import msvcrt
    from ctypes import wintypes
    _plain_path(path)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
    kernel.CreateFileW.restype = wintypes.HANDLE
    handle = kernel.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x80, None)
    if handle == ctypes.c_void_p(-1).value:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
    except Exception:
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle(handle)
        raise
    with os.fdopen(fd, "rb") as stream:
        yield stream


def verify_package(stream, sha256: str, size: int) -> None:
    if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256) or type(size) is not int or size <= 0:
        raise RuntimeError("Update integrity information is invalid.")
    if os.fstat(stream.fileno()).st_size != size:
        raise RuntimeError("The installer size changed before installation.")
    stream.seek(0)
    if sha256_blocks(iter(lambda: stream.read(256 * 1024), b"")) != sha256:
        raise RuntimeError("The installer changed before installation.")



def normalize_completion_notes(notes):
    if not isinstance(notes, (list, tuple)):
        return []
    normalized = []
    for note in notes:
        if isinstance(note, str) and note.strip():
            normalized.append(note.strip()[:2000])
            if len(normalized) == 64:
                break
    return normalized


def stage_runtime(install: Path, staging: Path) -> None:
    manifest_path = _plain_path(install / "update-runtime.json")
    with guarded_package(manifest_path) as manifest_stream:
        payload = manifest_stream.read(256 * 1024 + 1)
    if len(payload) > 256 * 1024:
        raise RuntimeError("The updater runtime manifest is too large.")
    manifest = json.loads(payload.decode("utf-8"))
    if not isinstance(manifest, dict) or type(manifest.get("format")) is not int or manifest.get("format") != 1 or manifest.get("product") != PRODUCT:
        raise RuntimeError("The updater runtime manifest does not match this application.")
    if manifest.get('version') != file_version(install / (PRODUCT + '.exe')):
        raise RuntimeError("The updater runtime does not match the installed version.")
    helper = install / 'UpdateHelper.exe'
    with guarded_package(helper) as helper_stream:
        helper_size = os.fstat(helper_stream.fileno()).st_size
        verify_package(helper_stream, manifest.get('helper_sha256', ''), helper_size)
        helper_copy = _plain_path(staging / 'UpdateHelper.exe')
        copy_file(helper, helper_copy)
        with guarded_package(helper_copy) as copy_stream:
            verify_package(copy_stream, manifest['helper_sha256'], helper_size)
    entries = manifest.get("files")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 64:
        raise RuntimeError("The updater runtime manifest has an invalid file list.")
    validated, seen, total = [], set(), 0
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise RuntimeError("The updater runtime entry is invalid.")
        relative = Path(entry["path"])
        if relative.is_absolute() or relative.drive or len(relative.parts) < 2 or relative.parts[0] != "_internal" or any(part in {"..", "."} or ":" in part or part.endswith((' ', '.')) for part in relative.parts):
            raise RuntimeError("The updater runtime path is outside the application bundle.")
        key = os.path.normcase(str(relative))
        if key in seen:
            raise RuntimeError("The updater runtime manifest contains duplicate paths.")
        seen.add(key)
        size, expected_hash = entry.get("size"), entry.get("sha256")
        if type(size) is not int or not 0 < size <= 64 * 1024 * 1024 or not isinstance(expected_hash, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
            raise RuntimeError("The updater runtime integrity information is invalid.")
        total += size
        if total > 256 * 1024 * 1024:
            raise RuntimeError("The updater runtime exceeds its size limit.")
        source = _plain_path(install / relative)
        if not source.is_file():
            raise RuntimeError("An updater runtime file is missing.")
        destination = _plain_path(staging / relative)
        if destination.exists():
            raise RuntimeError("The updater runtime destination already exists.")
        validated.append((source, destination, expected_hash, size))
    required = {os.path.normcase(str(Path("_internal") / f"python{sys.version_info.major}{sys.version_info.minor}.dll")), os.path.normcase(str(Path("_internal") / "base_library.zip"))}
    if not required.issubset(seen):
        raise RuntimeError("The updater runtime manifest is incomplete.")
    for source, destination, expected_hash, size in validated:
        with guarded_package(source) as source_stream:
            verify_package(source_stream, expected_hash, size)
            destination.parent.mkdir(parents=True, exist_ok=True)
            _plain_path(destination.parent)
            copy_file(source, destination)
            with guarded_package(destination) as destination_stream:
                verify_package(destination_stream, expected_hash, size)


def arm_update(*, setup_path: Path, sha256: str, size: int, version: str,
               current_version: str, notes, install_dir: Path, mode: str,
               restart: bool, staging_root: Path) -> None:
    global _ARMED, _MAINTENANCE_PENDING
    if _ARMED is not None:
        raise RuntimeError("An update is already waiting to install.")
    if os.name != "nt" or not getattr(sys, "frozen", False):
        raise RuntimeError("Installation is available only in the installed Windows application.")
    if not _VERSION.fullmatch(version) or not _VERSION.fullmatch(current_version):
        raise RuntimeError("Update version information is invalid.")
    if tuple(map(int, version.split('.'))) <= tuple(map(int, current_version.split('.'))):
        raise RuntimeError("The update must be newer than the installed version.")
    if mode not in {"/CURRENTUSER", "/ALLUSERS"}:
        raise RuntimeError("Unknown installation scope.")
    staging = _plain_path(staging_root)
    setup = _plain_path(setup_path)
    install = _plain_path(install_dir)
    expected_storage = _plain_path(state_root().parent)
    if staging.parent != expected_storage or not re.fullmatch(PRODUCT.lower() + r"-update-[0-9a-f]{32}", staging.name):
        raise RuntimeError("Update staging is outside this application's storage.")
    if setup.parent != staging or not setup.is_file():
        raise RuntimeError("The installer is outside its owned staging directory.")
    executable = install / (PRODUCT + ".exe")
    if executable != _plain_path(Path(sys.executable)):
        raise RuntimeError("The update destination does not match the running application.")
    helper = install / "UpdateHelper.exe"
    if not helper.is_file():
        raise RuntimeError("The update helper is missing. Download and run the latest installer.")
    _plain_path(helper)
    helper_copy = _plain_path(staging / "UpdateHelper.exe")
    if helper_copy.exists():
        raise RuntimeError("This update has already been handed off.")
    stage_runtime(install, staging)
    root = _plain_path(state_root())
    root.mkdir(parents=True, exist_ok=True)
    record = root / (os.urandom(16).hex() + ".json")
    data = dict(product=PRODUCT, state="arming", parent_pid=os.getpid(),
                bootloader_pid=os.getppid(), staging=str(staging), setup=str(setup),
                sha256=sha256.lower(), size=int(size), previous_version=current_version,
                version=version, notes=normalize_completion_notes(notes),
                install_dir=str(install), mode=mode, restart=bool(restart), created=time.time())
    write_state(record, data)
    try:
        process = subprocess.Popen([str(helper_copy), "--transaction", str(record)],
                                   cwd=str(staging), close_fds=True,
                                   creationflags=subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            result = read_state(record)
            if result.get("state") == "ready":
                _ARMED = record
                return
            if result.get("state") == "failed" or process.poll() is not None:
                raise RuntimeError(result.get("error") or "The update helper could not start.")
            time.sleep(0.05)
        raise RuntimeError("The update helper did not respond. The application will stay open.")
    except Exception:
        data.update(state="aborted")
        write_state(record, data)
        _MAINTENANCE_PENDING = True
        raise


def abort_pending_update() -> None:
    global _ARMED, _MAINTENANCE_PENDING
    if _ARMED is None:
        return
    path = _ARMED
    data = read_state(path)
    data["state"] = "aborted"
    write_state(path, data)
    _ARMED = None
    _MAINTENANCE_PENDING = True


def take_maintenance_request() -> bool:
    global _MAINTENANCE_PENDING
    pending = _MAINTENANCE_PENDING
    _MAINTENANCE_PENDING = False
    return pending


def commit_pending_update() -> None:
    global _ARMED
    if _ARMED is None:
        return
    path = _ARMED
    data = read_state(path)
    if data.get("state") != "ready":
        _ARMED = None
        ctypes.windll.user32.MessageBoxW(None, "The update could not start because the handoff expired. Download and run the latest installer.", PRODUCT + " update", 0x10)
        return
    data["state"] = "committed"
    write_state(path, data)
    _ARMED = None


def pending_completion(version: str) -> tuple[Path, dict] | None:
    try:
        root = _plain_path(state_root())
        if not root.exists():
            return None
        for path in sorted(root.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                data = read_state(path)
                if data.get("state") == "success" and data.get("version") == version:
                    return path, {**data, "notes": normalize_completion_notes(data.get("notes"))}
            except (OSError, ValueError, RuntimeError):
                continue
    except (OSError, RuntimeError):
        pass
    return None


def acknowledge_completion(path: Path) -> None:
    data = read_state(path)
    if data.get("state") == "success":
        data["state"] = "consumed"
        write_state(path, data)


def _process_handles(data: dict):
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    handles = []
    expected = os.path.normcase(str(Path(data["install_dir"]) / (PRODUCT + ".exe")))
    try:
        for pid in {int(data["parent_pid"]), int(data["bootloader_pid"])}:
            handle = kernel.OpenProcess(0x100000 | 0x1000, False, pid)
            if not handle:
                if pid == int(data["parent_pid"]):
                    raise RuntimeError("The application exited before accepting the update.")
                continue
            buffer, length = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
            if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
                kernel.CloseHandle(handle)
                raise RuntimeError("The application process could not be verified.")
            if os.path.normcase(buffer.value) != expected:
                kernel.CloseHandle(handle)
                if pid == int(data["parent_pid"]):
                    raise RuntimeError("The update belongs to another application process.")
                continue
            handles.append(handle)
    except Exception:
        for opened in handles:
            kernel.CloseHandle(opened)
        raise
    return kernel, handles


def installer_arguments(data: dict, log: Path) -> list[str]:
    return ["/SILENT", "/SP-", "/NORESTART", "/NOCLOSEAPPLICATIONS",
            "/NOFORCECLOSEAPPLICATIONS", "/SKIPLAUNCH", "/RESTARTEXITCODE=3010",
            data["mode"], "/DIR=" + data["install_dir"], "/LOG=" + str(log)]


def run_transaction(record: Path) -> int:
    try:
        with state_lease(record):
            return _run_transaction(record)
    except (OSError, RuntimeError):
        return 1


def _run_transaction(record: Path) -> int:
    kernel, handles = None, []
    data = {}
    committed = False
    acknowledged = False
    try:
        root = _plain_path(state_root())
        if _plain_path(record).parent != root or not re.fullmatch(r"[0-9a-f]{32}\.json", record.name):
            raise RuntimeError("The update record is outside application storage.")
        data = read_state(record)
        if data.get("state") != "arming":
            return 1
        data['helper_pid'] = os.getpid()
        staging, setup = _plain_path(Path(data["staging"])), _plain_path(Path(data["setup"]))
        install = _plain_path(Path(data["install_dir"]))
        if staging.parent != root.parent or setup.parent != staging or not re.fullmatch(PRODUCT.lower() + r"-update-[0-9a-f]{32}", staging.name):
            raise RuntimeError("The update package is outside owned staging.")
        if _plain_path(Path(sys.executable)).parent != staging:
            raise RuntimeError("The helper must run from update staging.")
        if not _VERSION.fullmatch(str(data.get("version", ""))) or data.get("mode") not in {"/CURRENTUSER", "/ALLUSERS"}:
            raise RuntimeError("The update parameters are invalid.")
        if file_version(install / (PRODUCT + ".exe")) != data.get("previous_version"):
            raise RuntimeError("The installed version changed before accepting the update.")
        if tuple(map(int, data["version"].split("."))) <= tuple(map(int, str(data.get("previous_version", "")).split("."))):
            raise RuntimeError("The update must be newer than the installed version.")
        kernel, handles = _process_handles(data)
        with guarded_package(setup) as package:
            verify_package(package, data["sha256"], int(data["size"]))
            data["state"] = "ready"
            write_state(record, data)
            acknowledged = True
            deadline = time.monotonic() + 300
            while time.monotonic() < deadline:
                phase = read_state(record).get("state")
                if phase == "committed":
                    committed = True
                    break
                if phase == "aborted":
                    return 1
                time.sleep(0.05)
            if not committed:
                raise RuntimeError("The application did not finish accepting the update.")
            deadline = time.monotonic() + 60
            for handle in handles:
                remaining = max(0, int((deadline - time.monotonic()) * 1000))
                if kernel.WaitForSingleObject(handle, remaining) != 0:
                    raise RuntimeError("The application is still running. Installation was not started.")
            verify_package(package, data["sha256"], int(data["size"]))
            if file_version(install / (PRODUCT + ".exe")) != data["previous_version"]:
                raise RuntimeError("Another installation changed the application. Installation was not started.")
            data["state"] = "installing"
            write_state(record, data)
            process = subprocess.Popen([str(setup), *installer_arguments(data, record.with_suffix('.log'))], cwd=str(staging))
            data['installer_pid'] = process.pid
            write_state(record, data)
            code = process.wait()
            data["exit_code"] = code
            if code == 3010:
                raise RuntimeError("Installation needs a Windows restart. Restart Windows before opening the application.")
            if code in {2, 5}:
                raise RuntimeError("Installation was canceled. Download and run the latest installer when you are ready to retry.")
            if code != 0:
                raise RuntimeError(f"Installation did not finish (code {code}). Download and run the latest installer to retry.")
            if file_version(install / (PRODUCT + ".exe")) != data["version"]:
                raise RuntimeError("The installed application version does not match the update.")
        data.update(state="success", finished=time.time())
        write_state(record, data)
        if data.get("restart"):
            try:
                subprocess.Popen([str(install / (PRODUCT + ".exe"))], cwd=str(install))
            except OSError:
                ctypes.windll.user32.MessageBoxW(None, "The update is installed. Open the application to continue.", PRODUCT, 0x40)
        try:
            setup.unlink()
        except OSError:
            pass
        return 0
    except Exception as exc:
        if data:
            data.update(state="failed", error=str(exc), finished=time.time())
            try:
                write_state(record, data)
            except (OSError, RuntimeError):
                pass
        if committed or acknowledged:
            answer = ctypes.windll.user32.MessageBoxW(None, f"{exc}\n\nOpen the download page?", PRODUCT + " update", 0x14)
            if answer == 6:
                open_url("https://www.justagwas.com/projects/" + PRODUCT.lower() + "/download")
        return 1
    finally:
        if kernel is not None:
            for handle in handles:
                kernel.CloseHandle(handle)


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] != "--transaction" or os.name != "nt":
        raise SystemExit(2)
    raise SystemExit(run_transaction(Path(sys.argv[2])))
