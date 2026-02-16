from __future__ import annotations

import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from urllib.parse import urlparse


_ALLOWED_UPDATE_HOSTS = {
    "github.com",
    "www.github.com",
    "sourceforge.net",
    "www.sourceforge.net",
    "justagwas.com",
    "www.justagwas.com",
}
_REQUEST_RETRIES = 3
_REQUEST_RETRY_DELAY_SECONDS = 0.5
_REQUEST_TIMEOUT_SECONDS = 8.0


def parse_semver(value: str) -> tuple[int, int, int] | None:
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", value or "")
    if not match:
        return None
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


@dataclass(frozen=True, slots=True)
class UpdateEndpoints:
    manifest_url: str
    github_latest_url: str
    github_download_url: str
    sourceforge_rss_url: str
    sourceforge_download_url: str


class UpdateCheckService:
    def __init__(self, app_name: str, app_version: str, endpoints: UpdateEndpoints) -> None:
        self._app_name = str(app_name)
        self._app_version = str(app_version)
        self._endpoints = endpoints

    @staticmethod
    def _request_with_retries(
        request: urllib.request.Request,
        *,
        timeout: float,
        retries: int,
        retry_delay_seconds: float,
    ) -> tuple[bytes, str]:
        attempts = max(1, int(retries))
        timeout_seconds = max(0.1, float(timeout))
        delay_base = max(0.0, float(retry_delay_seconds))
        last_error: Exception | None = None
        for attempt in range(1, attempts + 1):
            try:
                with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
                    return response.read(), str(response.geturl())
            except Exception as exc:
                last_error = exc
                if attempt < attempts and delay_base > 0:
                    time.sleep(delay_base * attempt)
        if last_error is not None:
            raise last_error
        raise RuntimeError("Update request failed.")

    def _json_from_url(
        self,
        url: str,
        timeout: float = _REQUEST_TIMEOUT_SECONDS,
        retries: int = _REQUEST_RETRIES,
    ) -> dict | None:
        request = urllib.request.Request(
            url=url,
            headers={"User-Agent": f"{self._app_name}/{self._app_version}"},
            method="GET",
        )
        payload_bytes, _ = self._request_with_retries(
            request,
            timeout=timeout,
            retries=retries,
            retry_delay_seconds=_REQUEST_RETRY_DELAY_SECONDS,
        )
        body = payload_bytes.decode("utf-8-sig", errors="replace")
        payload = json.loads(body)
        return payload if isinstance(payload, dict) else None

    def _text_from_url(
        self,
        url: str,
        timeout: float = _REQUEST_TIMEOUT_SECONDS,
        retries: int = _REQUEST_RETRIES,
    ) -> tuple[str, str]:
        request = urllib.request.Request(
            url=url,
            headers={"User-Agent": f"{self._app_name}/{self._app_version}"},
            method="GET",
        )
        payload_bytes, final_url = self._request_with_retries(
            request,
            timeout=timeout,
            retries=retries,
            retry_delay_seconds=_REQUEST_RETRY_DELAY_SECONDS,
        )
        body = payload_bytes.decode("utf-8", errors="replace")
        return body, final_url

    @staticmethod
    def _is_allowed_update_url(url: str) -> bool:
        parsed = urlparse(str(url or "").strip())
        if parsed.scheme.lower() != "https":
            return False
        host = (parsed.hostname or "").strip().lower()
        if not host:
            return False
        return host in _ALLOWED_UPDATE_HOSTS

    def sanitize_download_url(self, url: str) -> str:
        candidate = str(url or "").strip()
        if candidate and self._is_allowed_update_url(candidate):
            return candidate
        fallback = str(self._endpoints.github_download_url or "").strip()
        if fallback and self._is_allowed_update_url(fallback):
            return fallback
        return ""

    @staticmethod
    def _normalize_semver(value: str) -> str:
        parsed = parse_semver(value)
        if parsed is None:
            raise RuntimeError("did not contain a valid semantic version")
        return f"{parsed[0]}.{parsed[1]}.{parsed[2]}"

    def _detect_from_manifest(self) -> tuple[str, str]:
        manifest = self._json_from_url(self._endpoints.manifest_url)
        if manifest is None:
            raise RuntimeError("did not return a JSON object")
        version_value = (
            manifest.get("version")
            or manifest.get("latest")
            or manifest.get("app_version")
            or ""
        )
        if not isinstance(version_value, str):
            raise RuntimeError("did not contain a semantic version string")
        version = self._normalize_semver(version_value)
        download_url = (
            manifest.get("download_url")
            or manifest.get("url")
            or manifest.get("download")
            or ""
        )
        sanitized = self.sanitize_download_url(str(download_url))
        if not sanitized:
            raise RuntimeError("download URL was missing/untrusted and fallback URL was invalid")
        return version, sanitized

    def _detect_from_github(self) -> tuple[str, str]:
        body, final_url = self._text_from_url(self._endpoints.github_latest_url)
        match = re.search(r"/tag/v?(\d+\.\d+\.\d+)", final_url)
        if match is None:
            match = re.search(r"/releases/tag/v?(\d+\.\d+\.\d+)", body)
        if match is None:
            raise RuntimeError("latest release page did not contain a valid version tag")
        return self._normalize_semver(match.group(1)), self.sanitize_download_url(self._endpoints.github_download_url)

    def _detect_from_sourceforge(self) -> tuple[str, str]:
        rss_text, _ = self._text_from_url(self._endpoints.sourceforge_rss_url)
        xml_root = ET.fromstring(rss_text)
        titles = xml_root.findall(".//item/title")
        for title in titles:
            if not title.text:
                continue
            parsed = parse_semver(title.text)
            if parsed is None:
                continue
            version = f"{parsed[0]}.{parsed[1]}.{parsed[2]}"
            return version, self.sanitize_download_url(self._endpoints.sourceforge_download_url)
        raise RuntimeError("RSS did not contain a valid semantic version")

    def detect_latest_version(self) -> tuple[str, str]:
        providers = (
            ("latest.json", self._detect_from_manifest),
            ("GitHub", self._detect_from_github),
            ("SourceForge", self._detect_from_sourceforge),
        )
        errors: list[str] = []
        for provider_name, provider in providers:
            try:
                return provider()
            except Exception as exc:
                errors.append(f"{provider_name} failed: {exc}")
        raise RuntimeError("Could not parse latest version from update sources. " + "; ".join(errors))
