"""Server-side admin health aggregation (blocking vs warnings)."""

from __future__ import annotations

from typing import Any


def evaluate_health(payload: dict[str, Any]) -> dict[str, Any]:
    """Compute ``health`` from an admin status payload (pure).

    ``blocking`` → ``ready=false`` (core connections / required failures).
    ``warnings`` → recommended deps degraded; do not flip ready alone.
    """
    blocking: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []

    switcher = payload.get("switcher")
    if isinstance(switcher, dict):
        if not switcher.get("connected_iracing"):
            blocking.append(
                {
                    "id": "iracing",
                    "reason": "disconnected",
                    "tip": "Start iRacing and wait for shared memory.",
                }
            )
        if not switcher.get("connected_obs"):
            blocking.append(
                {
                    "id": "obs",
                    "reason": "disconnected",
                    "tip": "Start OBS and enable WebSocket server.",
                }
            )
    else:
        warnings.append(
            {
                "id": "switcher",
                "reason": "unavailable",
                "tip": "Switcher runtime not initialized yet.",
            }
        )

    extensions = payload.get("extensions") or {}
    features = payload.get("features") or {}

    overlay = features.get("overlay") or {}
    if overlay.get("enabled") and not overlay.get("active"):
        warnings.append(
            {
                "id": "overlay",
                "reason": str(overlay.get("status") or "idle"),
                "tip": "Overlay is enabled but runtime is not running.",
            }
        )

    ble = extensions.get("ble") or {}
    if ble.get("enabled") and ble.get("status") in {"disconnected", "error"}:
        warnings.append(
            {
                "id": "ble",
                "reason": str(ble.get("status") or "disconnected"),
                "tip": "BLE heart-rate enabled but not connected.",
            }
        )

    lhm = extensions.get("lhm") or {}
    if lhm.get("required") and lhm.get("status") in {
        "unreachable",
        "reachable_empty",
        "error",
        "stale",
    }:
        tip = ""
        detail = lhm.get("detail") or {}
        if isinstance(detail, dict):
            tip = str(detail.get("tip") or "")
        warnings.append(
            {
                "id": "lhm",
                "reason": str(lhm.get("status") or "unreachable"),
                "tip": tip or "Libre Hardware Monitor is required/recommended but unhealthy.",
            }
        )

    sysinfo = extensions.get("sysinfo") or {}
    if sysinfo.get("enabled") and sysinfo.get("status") == "degraded":
        warnings.append(
            {
                "id": "sysinfo",
                "reason": "degraded",
                "tip": "System info is degraded (package sensors missing).",
            }
        )

    commentary = features.get("commentary") or {}
    if commentary.get("enabled") and commentary.get("status") == "idle":
        warnings.append(
            {
                "id": "commentary",
                "reason": "idle",
                "tip": "Commentary enabled but director is not available.",
            }
        )

    return {
        "ready": len(blocking) == 0,
        "blocking": blocking,
        "warnings": warnings,
    }
