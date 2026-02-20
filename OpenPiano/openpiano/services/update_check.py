from __future__ import annotations

from dataclasses import dataclass
from threading import Event, Thread

from openpiano.core.config import INNO_SETUP_APP_ID, UPDATE_CHECK_SETUP_URL
from openpiano.core.runtime_paths import app_local_data_dir, executable_dir

from .self_updater import (
    PreparedUpdateInstall,
    ProgressCallback,
    SelfUpdater,
    UpdateCheckData,
    normalize_version,
)


@dataclass(frozen=True, slots=True)
class UpdateEndpoints:
    manifest_url: str
    page_url: str


class UpdateCheckService:
    def __init__(self, app_name: str, app_version: str, endpoints: UpdateEndpoints) -> None:
        self._app_name = str(app_name or "").strip() or "OpenPiano"
        self._app_version = str(app_version or "").strip() or "0.0.0"
        self._endpoints = endpoints
        storage_root = app_local_data_dir(self._app_name) or executable_dir()
        self._updater = SelfUpdater(
            app_name=self._app_name,
            app_version=self._app_version,
            manifest_url=str(endpoints.manifest_url or "").strip(),
            page_url=str(endpoints.page_url or "").strip(),
            setup_url=str(UPDATE_CHECK_SETUP_URL or "").strip(),
            installer_app_id=str(INNO_SETUP_APP_ID or "").strip(),
            install_dir=executable_dir(),
            runtime_storage_dir=storage_root,
        )
        Thread(target=self._updater.recover_pending_update, daemon=True).start()

    def check_for_updates(self, current_version: str, *, stop_event: Event | None = None) -> UpdateCheckData:
        return self._updater.check_for_updates(current_version, stop_event=stop_event)

    def prepare_update(
        self,
        check_data: UpdateCheckData,
        *,
        stop_event: Event | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> PreparedUpdateInstall:
        return self._updater.prepare_update(
            check_data,
            stop_event=stop_event,
            progress_callback=progress_callback,
        )

    def launch_prepared_update(
        self,
        prepared: PreparedUpdateInstall,
        *,
        restart_after_update: bool,
    ) -> None:
        self._updater.launch_prepared_update(
            prepared,
            restart_after_update=bool(restart_after_update),
        )

    def discard_prepared_update(self, prepared: PreparedUpdateInstall) -> None:
        self._updater.discard_prepared_update(prepared)

    def prepare_update_from_payload(
        self,
        payload: dict[str, object],
        *,
        stop_event: Event | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> PreparedUpdateInstall:
        check_data = UpdateCheckData(
            update_available=bool(payload.get("update_available", False)),
            current_version=normalize_version(str(payload.get("current_version") or self._app_version)) or "0.0.0",
            latest_version=normalize_version(str(payload.get("latest") or "")) or "0.0.0",
            page_url=str(payload.get("url") or self._endpoints.page_url or ""),
            setup_url=str(payload.get("setup_url") or ""),
            setup_sha256=str(payload.get("setup_sha256") or ""),
            setup_size=int(payload.get("setup_size") or 0),
            released=str(payload.get("released") or ""),
            notes=[str(item or "").strip() for item in (payload.get("notes") or []) if str(item or "").strip()],
            source="latest.json",
            channel=str(payload.get("channel") or "stable"),
            minimum_supported_version=normalize_version(str(payload.get("minimum_supported_version") or "1.0.0")) or "1.0.0",
            requires_manual_update=bool(payload.get("requires_manual_update", False)),
            setup_managed_install=bool(payload.get("setup_managed_install", False)),
        )
        return self.prepare_update(
            check_data,
            stop_event=stop_event,
            progress_callback=progress_callback,
        )
