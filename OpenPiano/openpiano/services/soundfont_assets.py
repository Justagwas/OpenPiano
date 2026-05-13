from __future__ import annotations

import time
import urllib.request
from pathlib import Path
from threading import Event
from typing import Callable, Iterable

from openpiano.core.instrument_registry import (
    InstrumentInfo,
)


def normalized_soundfont_stem(path: Path) -> str:
    return "".join(ch for ch in path.stem.lower() if ch.isalnum())


def has_high_quality_soundfont(instruments: Iterable[InstrumentInfo]) -> bool:
    return any(normalized_soundfont_stem(instrument.path) == "grandpiano" for instrument in instruments)


def download_file_with_retries(
    *,
    url: str,
    user_agent: str,
    target_path: Path,
    retries: int,
    timeout_seconds: float,
    retry_delay_seconds: float,
    stop_event: Event | None = None,
    progress_callback: Callable[[int, str], None] | None = None,
) -> None:
    request = urllib.request.Request(
        url=url,
        headers={"User-Agent": user_agent},
        method="GET",
    )
    temp_path = target_path.with_suffix(f"{target_path.suffix}.part")
    attempts = max(1, int(retries))
    timeout = float(timeout_seconds)
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        if stop_event is not None and stop_event.is_set():
            raise InterruptedError("SoundFont download canceled.")
        try:
            if temp_path.exists():
                temp_path.unlink()
            with urllib.request.urlopen(request, timeout=timeout) as response, temp_path.open("wb") as target:
                total_raw = str(response.headers.get("Content-Length", "")).strip()
                try:
                    total_bytes = max(0, int(total_raw))
                except Exception:
                    total_bytes = 0
                downloaded = 0
                if progress_callback is not None:
                    progress_callback(0, "Downloading SoundFont...")
                while True:
                    if stop_event is not None and stop_event.is_set():
                        raise InterruptedError("SoundFont download canceled.")
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    target.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback is not None:
                        if total_bytes > 0:
                            raw = min(1.0, max(0.0, downloaded / float(total_bytes)))
                            progress_callback(
                                max(1, min(99, int(round(raw * 100.0)))),
                                f"Downloading SoundFont... {int(round(raw * 100.0))}%",
                            )
                        else:
                            mb = downloaded / (1024.0 * 1024.0)
                            progress_callback(0, f"Downloading SoundFont... {mb:.1f} MB")
            temp_path.replace(target_path)
            if progress_callback is not None:
                progress_callback(100, "SoundFont download complete.")
            return
        except InterruptedError:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass
            raise
        except Exception as exc:
            last_error = exc
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass
            if attempt < attempts:
                delay = retry_delay_seconds * attempt
                if stop_event is not None:
                    if stop_event.wait(delay):
                        raise InterruptedError("SoundFont download canceled.")
                else:
                    time.sleep(delay)

    if last_error is not None:
        raise last_error
