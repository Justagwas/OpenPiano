from __future__ import annotations

import time
import urllib.request
from pathlib import Path
from typing import Iterable

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
        try:
            if temp_path.exists():
                temp_path.unlink()
            with urllib.request.urlopen(request, timeout=timeout) as response, temp_path.open("wb") as target:
                while True:
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    target.write(chunk)
            temp_path.replace(target_path)
            return
        except Exception as exc:
            last_error = exc
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass
            if attempt < attempts:
                time.sleep(retry_delay_seconds * attempt)

    if last_error is not None:
        raise last_error
