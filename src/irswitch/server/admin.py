"""Admin dashboard HTTP API + static pages (live operator shell)."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from aiohttp import web

from irswitch import __version__
from irswitch.overlay.http import _file_response, get_overlay_bus
from irswitch.server.event_log import get_event_log

logger = logging.getLogger(__name__)


def _overlay_runtime() -> Any | None:
    from irswitch.overlay import http as overlay_http

    return getattr(overlay_http, "_overlay_runtime", None)


def _app_config() -> Any | None:
    from irswitch.server.api import get_app_config

    return get_app_config()


def _switcher_state() -> Any | None:
    from irswitch.server.api import _current_state

    return _current_state


def _extension_card(
    *,
    ext_id: str,
    label: str,
    enabled: bool,
    active: bool,
    status: str,
    detail: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "id": ext_id,
        "label": label,
        "enabled": enabled,
        "active": active,
        "status": status,
        "detail": detail or {},
    }


def _feature_card(
    *,
    enabled: bool,
    active: bool,
    status: str,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "enabled": enabled,
        "active": active,
        "status": status,
    }
    payload.update(extra)
    return payload


async def _probe_lhm() -> dict[str, Any]:
    """Non-blocking LHM HTTP probe (worker thread)."""

    def _run() -> dict[str, Any]:
        from irswitch.system.lhm_http import lhm_connection_status

        try:
            return lhm_connection_status(force=False)
        except Exception:
            logger.debug("LHM status probe failed", exc_info=True)
            return {
                "reachable": False,
                "base_url": None,
                "sensor_rows": 0,
                "status": "error",
                "prerequisite_for": ["sysinfo.cpu_package"],
            }

    return await asyncio.to_thread(_run)


def build_admin_status(
    *,
    lhm: dict[str, Any] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Pure-ish aggregator used by GET /api/admin/status and tests."""
    now = time.monotonic() if now is None else now
    cfg = _app_config()
    overlay_cfg = getattr(cfg, "overlay", None) if cfg is not None else None
    bus = get_overlay_bus()
    runtime = _overlay_runtime()
    state = _switcher_state()

    hr = getattr(overlay_cfg, "heart_rate", None) if overlay_cfg is not None else None
    sys_cfg = getattr(overlay_cfg, "system_info", None) if overlay_cfg is not None else None
    commentary_cfg = getattr(overlay_cfg, "commentary", None) if overlay_cfg is not None else None
    tape_cfg = getattr(overlay_cfg, "tape", None) if overlay_cfg is not None else None
    ee = getattr(overlay_cfg, "event_engine", None) if overlay_cfg is not None else None

    bio = bus.bio
    system = bus.system
    ble_enabled = bool(getattr(hr, "enabled", True))
    ble_status = str(bio.status or "disconnected")
    ble_active = ble_status in {"connected", "connecting", "reconnecting"} or bool(bio.connected)

    lhm = lhm or {
        "reachable": False,
        "base_url": None,
        "sensor_rows": 0,
        "status": "unreachable",
        "prerequisite_for": ["sysinfo.cpu_package"],
    }
    lhm_reachable = bool(lhm.get("reachable"))

    sys_enabled = bool(getattr(sys_cfg, "enabled", True))
    has_package = system.cpu.temperature is not None or system.cpu.power is not None
    sys_active = sys_enabled and (runtime is not None)
    if not sys_enabled:
        sys_status = "disabled"
    elif not lhm_reachable and not has_package:
        sys_status = "degraded"
    elif sys_active:
        sys_status = "sampling"
    else:
        sys_status = "idle"

    overlay_enabled = bool(getattr(overlay_cfg, "enabled", True)) if overlay_cfg else True
    overlay_active = overlay_enabled and runtime is not None
    overlay_status = (
        "disabled" if not overlay_enabled else ("running" if overlay_active else "idle")
    )

    commentary_enabled = bool(getattr(commentary_cfg, "enabled", False))
    director = getattr(runtime, "commentary", None) if runtime is not None else None
    busy_until = float(getattr(director, "_busy_until", 0.0) or 0.0) if director else 0.0
    commentary_busy = bool(director is not None and now < busy_until)
    commentary_active = commentary_enabled and commentary_busy
    if not commentary_enabled:
        commentary_status = "disabled"
    elif director is None:
        commentary_status = "idle"
    elif commentary_busy:
        commentary_status = "speaking"
    else:
        commentary_status = "ready"

    tape_enabled = bool(getattr(tape_cfg, "enabled", True))
    tape_writer = getattr(runtime, "_tape", None) or getattr(runtime, "tape", None)
    tape_active = bool(tape_writer)
    tape_status = "disabled" if not tape_enabled else ("recording" if tape_active else "idle")

    switcher: dict[str, Any] | None = None
    if state is not None:
        switcher = {
            "connected_iracing": bool(getattr(state, "connected_iracing", False)),
            "connected_obs": bool(getattr(state, "connected_obs", False)),
            "autoswitch": bool(getattr(state, "autoswitch", False)),
            "mode": getattr(state, "mode", None),
            "current_scene": getattr(state, "current_scene", None),
            "target_scene": getattr(state, "target_scene", None),
            "reason": getattr(state, "reason", None),
            "session_type": getattr(state, "session_type", None),
        }

    return {
        "version": __version__,
        "switcher": switcher,
        "extensions": {
            "ble": _extension_card(
                ext_id="ble",
                label="BLE heart rate",
                enabled=ble_enabled,
                active=ble_active,
                status=ble_status if ble_enabled else "disabled",
                detail={
                    "deviceName": bio.device_name,
                    "bpm": bio.bpm,
                    "hrState": bio.state,
                    "source": getattr(hr, "source", "bluetooth"),
                    "deviceFilter": getattr(hr, "device", "auto"),
                },
            ),
            "lhm": _extension_card(
                ext_id="lhm",
                label="Libre Hardware Monitor",
                enabled=True,
                active=lhm_reachable,
                status=str(lhm.get("status") or ("connected" if lhm_reachable else "unreachable")),
                detail={
                    "baseUrl": lhm.get("base_url"),
                    "sensorRows": int(lhm.get("sensor_rows") or 0),
                    "prerequisiteFor": list(
                        lhm.get("prerequisite_for") or ["sysinfo.cpu_package"]
                    ),
                    "tip": (
                        "Start LibreHardwareMonitor → Options → Remote Web Server → Run; "
                        "File → Hardware must include CPU."
                    ),
                },
            ),
            "sysinfo": _extension_card(
                ext_id="sysinfo",
                label="System info",
                enabled=sys_enabled,
                active=sys_active,
                status=sys_status,
                detail={
                    "cpuTemp": system.cpu.temperature,
                    "cpuPower": system.cpu.power,
                    "cpuLoad": system.cpu.load,
                    "gpuLoad": system.gpu.load,
                    "gpuTemp": system.gpu.temperature,
                    "lhmRequired": True,
                    "lhmReachable": lhm_reachable,
                },
            ),
        },
        "features": {
            "overlay": _feature_card(
                enabled=overlay_enabled,
                active=overlay_active,
                status=overlay_status,
                theme=getattr(overlay_cfg, "theme", None) if overlay_cfg else None,
                activeWidgets=len(bus.active_events or []),
            ),
            "commentary": _feature_card(
                enabled=commentary_enabled,
                active=commentary_active,
                status=commentary_status,
                busy=commentary_busy,
                runtime=director is not None,
            ),
            "tape": _feature_card(
                enabled=tape_enabled,
                active=tape_active,
                status=tape_status,
            ),
            "eventEngine": {
                "v2Payload": bool(getattr(ee, "v2_payload", False)),
                "practice": bool(getattr(ee, "practice", False)),
                "qualiProjection": bool(getattr(ee, "quali_projection", False)),
                "overtakeClassifier": bool(getattr(ee, "overtake_classifier", False)),
                "pitStory": bool(getattr(ee, "pit_story", False)),
                "hrPressure": bool(getattr(ee, "hr_pressure", False)),
            },
        },
    }


async def build_admin_activity(*, limit: int = 50) -> dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    items: list[dict[str, Any]] = []

    try:
        event_log = get_event_log()
        events = await event_log.get_recent_events(limit)
        for event in events:
            items.append(
                {
                    "at": (event.timestamp or 0) / 1000.0,
                    "source": "switcher",
                    "kind": event.type,
                    "message": event.message,
                    "data": event.data or {},
                }
            )
    except Exception:
        logger.debug("Admin activity: switcher event log failed", exc_info=True)

    runtime = _overlay_runtime()
    director = getattr(runtime, "commentary", None) if runtime is not None else None
    if director is not None and hasattr(director, "decisions"):
        try:
            for row in director.decisions(limit):
                action = str(row.get("action") or "skipped")
                text = str(row.get("text") or "")
                reason = str(row.get("reason") or "")
                message = text if action == "spoken" and text else f"{action}: {reason}"
                items.append(
                    {
                        "at": float(row.get("at") or 0.0),
                        "source": "commentary",
                        "kind": action,
                        "message": message,
                        "data": {
                            "nodeId": row.get("nodeId"),
                            "eventType": row.get("eventType"),
                            "emotion": row.get("emotion"),
                            "reason": reason,
                            "text": text,
                        },
                    }
                )
        except Exception:
            logger.debug("Admin activity: commentary decisions failed", exc_info=True)

    try:
        bus = get_overlay_bus()
        for envelope in list(bus.active_events or [])[:limit]:
            name = (
                envelope.get("name")
                or envelope.get("eventType")
                or envelope.get("type")
                or "widget"
            )
            phase = envelope.get("phase") or envelope.get("state") or ""
            message = f"Widget {name}" + (f" ({phase})" if phase else "")
            items.append(
                {
                    "at": float(
                        envelope.get("at")
                        or envelope.get("ts")
                        or envelope.get("timestamp")
                        or time.time()
                    ),
                    "source": "overlay",
                    "kind": str(name),
                    "message": message,
                    "data": envelope if isinstance(envelope, dict) else {},
                }
            )
    except Exception:
        logger.debug("Admin activity: overlay bus failed", exc_info=True)

    items.sort(key=lambda row: float(row.get("at") or 0.0), reverse=True)
    return {"items": items[:limit]}


async def handle_admin_status(_request: web.Request) -> web.Response:
    try:
        lhm = await _probe_lhm()
        payload = build_admin_status(lhm=lhm)
        return web.json_response(payload)
    except Exception:
        logger.exception("GET /api/admin/status failed")
        return web.json_response({"error": "admin status failed"}, status=500)


async def handle_admin_activity(request: web.Request) -> web.Response:
    try:
        raw = request.rel_url.query.get("limit") or "50"
        limit = int(raw)
    except ValueError:
        limit = 50
    try:
        payload = await build_admin_activity(limit=limit)
        return web.json_response(payload)
    except Exception:
        logger.exception("GET /api/admin/activity failed")
        return web.json_response({"error": "admin activity failed"}, status=500)


async def handle_admin_page(_request: web.Request) -> web.StreamResponse:
    return _file_response("admin/index.html")


async def handle_admin_extensions_page(_request: web.Request) -> web.StreamResponse:
    return _file_response("admin/extensions.html")


async def handle_admin_features_page(_request: web.Request) -> web.StreamResponse:
    return _file_response("admin/features.html")


async def handle_admin_activity_page(_request: web.Request) -> web.StreamResponse:
    return _file_response("admin/activity.html")


def register_admin_routes(app: web.Application) -> None:
    from irswitch.overlay.http import web_root

    app.router.add_get("/admin", handle_admin_page)
    app.router.add_get("/admin/", handle_admin_page)
    app.router.add_get("/admin/extensions", handle_admin_extensions_page)
    app.router.add_get("/admin/features", handle_admin_features_page)
    app.router.add_get("/admin/activity", handle_admin_activity_page)
    app.router.add_get("/api/admin/status", handle_admin_status)
    app.router.add_get("/api/admin/activity", handle_admin_activity)
    admin_static = web_root() / "admin"
    if admin_static.is_dir():
        app.router.add_static("/admin/web/", admin_static)
