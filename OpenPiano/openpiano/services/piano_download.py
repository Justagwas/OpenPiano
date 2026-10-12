
from __future__ import annotations

import hashlib
import os
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from openpiano.core.soundfont_loading import _metadata


D274_DOWNLOAD_URL = "https://downloads.justagwas.com/openpiano/Steinway%20D274%20HiFi.sf3"
D274_FILENAME = "Steinway D-274 Hi-Fi.sf3"
D274_SIZE = 396_062_650
D274_SHA256 = "f46a12ccb9eb48b97f85d21d670d1051d546ff91d362e1bff7ab27bba2596ab6"


def _validate_url(url: str) -> None:
    parts = urlsplit(url)
    if (parts.scheme != "https" or parts.hostname != "downloads.justagwas.com"
            or parts.port not in (None, 443) or parts.username or parts.password
            or not parts.path.startswith("/openpiano/") or parts.fragment):
        raise ValueError("The piano download must use the official HTTPS download service.")


class _OfficialRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@dataclass(frozen=True, slots=True)
class PianoDownloadSpec:
    url: str
    filename: str
    size: int
    sha256: str

    def validate(self) -> None:
        _validate_url(self.url)
        if (not self.filename or Path(self.filename).name != self.filename
                or any(c in self.filename for c in '<>:"/\\|?*')
                or not self.filename.lower().endswith(".sf3")
                or self.size <= 0 or not re.fullmatch(r"[0-9a-f]{64}", self.sha256)):
            raise ValueError("The piano download specification is invalid.")


def d274_download_spec() -> PianoDownloadSpec | None:
    if not D274_DOWNLOAD_URL:
        return None
    return PianoDownloadSpec(D274_DOWNLOAD_URL, D274_FILENAME, D274_SIZE, D274_SHA256)


def _publish_no_replace(source: Path, target: Path) -> None:
    if os.name == "nt":
        os.rename(source, target)
    else:
        os.link(source, target)


class PianoDownloadService:
    def __init__(self, spec: PianoDownloadSpec, destination: Path) -> None:
        spec.validate()
        self.spec = spec
        self.destination = Path(destination)

    @staticmethod
    def _check_stop(stop: Event) -> None:
        if stop.is_set():
            raise InterruptedError("Piano download cancelled.")

    def _verify(self, path: Path, stop: Event) -> None:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            if os.fstat(stream.fileno()).st_size != self.spec.size:
                raise ValueError("The downloaded piano has an unexpected size.")
            while block := stream.read(1024 * 1024):
                self._check_stop(stop)
                digest.update(block)
        self._check_stop(stop)
        if digest.hexdigest() != self.spec.sha256:
            raise ValueError("The downloaded piano failed its integrity check.")
        _metadata(path)

    def download(self, stop: Event, progress: Callable[[int, int], None]) -> Path:
        self._check_stop(stop)
        self.destination.mkdir(parents=True, exist_ok=True)
        target = self.destination / self.spec.filename
        if target.exists():
            self._verify(target, stop)
            progress(self.spec.size, self.spec.size)
            return target

        token = uuid.uuid4().hex
        partial = self.destination / f".d274-{token}.part"
        owned_partial = False

        try:
            request = Request(self.spec.url, headers={"User-Agent": "OpenPiano", "Accept-Encoding": "identity"})
            opener = build_opener(_OfficialRedirects())
            with opener.open(request, timeout=15) as response, partial.open("xb") as output:
                owned_partial = True
                _validate_url(response.geturl())
                advertised = response.headers.get("Content-Length")
                if advertised is not None and int(advertised) != self.spec.size:
                    raise ValueError("The piano server reported an unexpected file size.")

                received = 0
                progress(0, self.spec.size)
                while True:
                    self._check_stop(stop)
                    block = response.read1(min(256 * 1024, self.spec.size - received + 1))
                    self._check_stop(stop)
                    if not block:
                        break
                    received += len(block)
                    if received > self.spec.size:
                        raise ValueError("The piano download exceeds its expected size.")
                    output.write(block)
                    progress(received, self.spec.size)

                output.flush()
                os.fsync(output.fileno())

            self._verify(partial, stop)
            self._check_stop(stop)
            _publish_no_replace(partial, target)
            return target
        finally:
            if owned_partial:
                partial.unlink(missing_ok=True)
