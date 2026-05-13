from __future__ import annotations

from openpiano.services.self_updater import UpdateCheckData


def update_result_payload(check: UpdateCheckData) -> dict[str, object]:
    if not check.update_available:
        return {
            "status": "up_to_date",
            "latest": str(check.latest_version or ""),
            "url": str(check.page_url or ""),
        }
    return {
        "status": "available",
        "latest": str(check.latest_version or ""),
        "url": str(check.page_url or ""),
        "setup_url": str(check.setup_url or ""),
        "setup_sha256": str(check.setup_sha256 or ""),
        "setup_size": int(check.setup_size or 0),
        "released": str(check.released or ""),
        "notes": list(check.notes or []),
        "install_supported": bool(check.install_supported),
        "setup_managed_install": bool(check.setup_managed_install),
        "channel": str(check.channel or "stable"),
        "minimum_supported_version": str(check.minimum_supported_version or "1.0.0"),
        "requires_manual_update": bool(check.requires_manual_update),
    }


def prepared_update_payload(
    payload: dict[str, object],
    *,
    current_version: str,
    fallback_url: str,
) -> dict[str, object]:
    return {
        "update_available": True,
        "current_version": str(current_version or ""),
        "latest": str(payload.get("latest") or ""),
        "url": str(payload.get("url") or fallback_url),
        "setup_url": str(payload.get("setup_url") or ""),
        "setup_sha256": str(payload.get("setup_sha256") or ""),
        "setup_size": int(payload.get("setup_size") or 0),
        "released": str(payload.get("released") or ""),
        "notes": list(payload.get("notes") or []),
        "channel": str(payload.get("channel") or "stable"),
        "minimum_supported_version": str(payload.get("minimum_supported_version") or "1.0.0"),
        "requires_manual_update": bool(payload.get("requires_manual_update", False)),
        "setup_managed_install": bool(payload.get("setup_managed_install", False)),
    }


def update_notes_text(payload: dict[str, object]) -> str:
    notes = [str(item or "").strip() for item in (payload.get("notes") or []) if str(item or "").strip()]
    text = ""
    if notes:
        text = "\n\nWhat's new:\n" + "\n".join((f"- {line}" for line in notes[:8]))
    if bool(payload.get("requires_manual_update", False)):
        minimum_supported = str(payload.get("minimum_supported_version") or "1.0.0").strip() or "1.0.0"
        text += (
            "\n\nYour current version is below the minimum supported "
            f"auto-update baseline ({minimum_supported})."
        )
    return text

