"""Admin dashboard HTTP API + static pages (live operator shell)."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from aiohttp import web

from irswitch import __version__
from irswitch.overlay.http import _file_response, get_overlay_bus, get_overlay_runtime
from irswitch.server.admin_health import evaluate_health
from irswitch.server.event_log import get_event_log

logger = logging.getLogger(__name__)

ADMIN_SCHEMA_VERSION = 1
_SOURCE_PRIORITY = {"commentary": 0, "overlay": 1, "switcher": 2}


def _app_config() -> Any | None:
    from irswitch.server.api import get_app_config

    return get_app_config()


def _switcher_state() -> Any | None:
    from irswitch.server.api import get_current_state

    return get_current_state()


def _mono_to_wall(
    mono_s: float, *, now_mono: float | None = None, now_wall: float | None = None
) -> float:
    """Convert monotonic seconds to wall-clock epoch seconds."""
    now_mono = time.monotonic() if now_mono is None else now_mono
    now_wall = time.time() if now_wall is None else now_wall
    return now_wall - (now_mono - float(mono_s))


def _severity_for(status: str, *, required: bool = True) -> str:
    s = (status or "").lower()
    if s in {"disabled", "not_required"}:
        return "disabled" if s == "disabled" else "idle"
    if s in {"connected", "sampling", "running", "speaking", "ready", "recording"}:
        return "ok"
    if s in {"degraded", "connecting", "reconnecting", "unreachable", "reachable_empty", "stale"}:
        return "warn" if required else "idle"
    if s in {"error", "disconnected"}:
        return "bad" if required else "idle"
    if s in {"idle"}:
        return "idle"
    return "idle"


def _extension_card(
    *,
    ext_id: str,
    label: str,
    enabled: bool | None,
    available: bool,
    active: bool,
    status: str,
    detail: dict[str, Any] | None = None,
    required: bool | None = None,
    requirement_mode: str | None = None,
    busy: bool = False,
) -> dict[str, Any]:
    required_flag = bool(enabled) if required is None else bool(required)
    card: dict[str, Any] = {
        "id": ext_id,
        "label": label,
        "available": available,
        "active": active,
        "busy": busy,
        "status": status,
        "severity": _severity_for(status, required=required_flag),
        "detail": detail or {},
    }
    if enabled is not None:
        card["enabled"] = enabled
    if required is not None:
        card["required"] = required
    if requirement_mode is not None:
        card["requirementMode"] = requirement_mode
    return card


def _feature_card(
    *,
    enabled: bool,
    available: bool,
    active: bool,
    status: str,
    busy: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "enabled": enabled,
        "available": available,
        "active": active,
        "busy": busy,
        "status": status,
        "severity": _severity_for(status, required=enabled),
    }
    payload.update(extra)
    return payload


async def _probe_lhm() -> dict[str, Any]:
    """Non-blocking LHM status read (worker thread). Prefer cache via force=False."""

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
                "checked_at": time.monotonic(),
                "last_success_at": None,
                "stale": True,
                "error_code": "probe_exception",
            }

    return await asyncio.to_thread(_run)


def _runtime_snapshot(runtime: Any | None, now: float) -> dict[str, Any]:
    if runtime is None or not hasattr(runtime, "status_snapshot"):
        return {}
    try:
        snap = runtime.status_snapshot(now)
        return snap if isinstance(snap, dict) else {}
    except Exception:
        logger.debug("Overlay runtime status_snapshot failed", exc_info=True)
        return {}


def build_admin_status(
    *,
    lhm: dict[str, Any] | None = None,
    now: float | None = None,
) -> dict[str, Any]:
    """Aggregator used by GET /api/admin/status and tests."""
    now = time.monotonic() if now is None else now
    now_wall = time.time()
    cfg = _app_config()
    overlay_cfg = getattr(cfg, "overlay", None) if cfg is not None else None
    bus = get_overlay_bus()
    runtime = get_overlay_runtime()
    snap = _runtime_snapshot(runtime, now)
    state = _switcher_state()

    sys_cfg = getattr(overlay_cfg, "system_info", None) if overlay_cfg is not None else None
    ee = getattr(overlay_cfg, "event_engine", None) if overlay_cfg is not None else None

    bio_snap = snap.get("bio") if isinstance(snap.get("bio"), dict) else {}
    system_snap = snap.get("system") if isinstance(snap.get("system"), dict) else {}
    commentary_snap = snap.get("commentary") if isinstance(snap.get("commentary"), dict) else {}
    tape_snap = snap.get("tape") if isinstance(snap.get("tape"), dict) else {}

    # Prefer live bus metrics for sysinfo detail numbers when present.
    system = bus.system
    bio = bus.bio

    ble_enabled = bool(
        bio_snap.get("enabled", getattr(getattr(overlay_cfg, "heart_rate", None), "enabled", True))
    )
    ble_status = str(bio_snap.get("status") or bio.status or "disconnected")
    if not ble_enabled:
        ble_status = "disabled"
    ble_available = bool(bio_snap.get("available", runtime is not None))
    ble_active = ble_enabled and ble_status in {"connected", "connecting", "reconnecting"}

    lhm = lhm or {
        "reachable": False,
        "base_url": None,
        "sensor_rows": 0,
        "status": "unreachable",
        "prerequisite_for": ["sysinfo.cpu_package"],
        "checked_at": now,
        "last_success_at": None,
        "stale": False,
        "error_code": None,
    }
    lhm_reachable = bool(lhm.get("reachable"))
    sensor_rows = int(lhm.get("sensor_rows") or 0)
    lhm_raw_status = str(lhm.get("status") or "unreachable")

    sys_enabled = bool(
        system_snap.get(
            "enabled", getattr(sys_cfg, "enabled", True) if sys_cfg is not None else True
        )
    )
    cpu_enabled = bool(getattr(sys_cfg, "cpu_enabled", True) if sys_cfg is not None else True)
    lhm_required = sys_enabled and cpu_enabled
    requirement_mode = "recommended" if lhm_required else "optional"
    if not lhm_required:
        lhm_status = "not_required"
        lhm_active = False
        lhm_tip = None
    elif lhm_raw_status == "connected" or (lhm_reachable and sensor_rows > 0):
        lhm_status = "connected"
        lhm_active = True
        lhm_tip = None
    elif lhm_raw_status == "reachable_empty" or (lhm_reachable and sensor_rows == 0):
        lhm_status = "reachable_empty"
        lhm_active = False
        lhm_tip = (
            "LibreHardwareMonitor is reachable but no CPU sensors were found. "
            "Enable File → Hardware → CPU."
        )
    else:
        lhm_status = (
            lhm_raw_status if lhm_raw_status in {"unreachable", "error", "stale"} else "unreachable"
        )
        lhm_active = False
        lhm_tip = (
            "Start LibreHardwareMonitor → Options → Remote Web Server → Run; "
            "File → Hardware must include CPU."
        )

    has_package = system.cpu.temperature is not None or system.cpu.power is not None
    sys_available = bool(system_snap.get("available", runtime is not None))
    sys_active = sys_enabled and sys_available
    if not sys_enabled:
        sys_status = "disabled"
    elif lhm_required and not lhm_reachable and not has_package:
        sys_status = "degraded"
    else:
        sys_status = str(system_snap.get("status") or ("sampling" if sys_active else "idle"))

    overlay_enabled = bool(
        snap.get("enabled", getattr(overlay_cfg, "enabled", True) if overlay_cfg else True)
    )
    overlay_available = bool(snap.get("available", runtime is not None))
    overlay_running = bool(snap.get("running", False))
    overlay_active = (
        overlay_enabled and overlay_available and (overlay_running or runtime is not None)
    )
    overlay_status = str(
        snap.get("status")
        or ("disabled" if not overlay_enabled else ("running" if overlay_running else "idle"))
    )
    # Match Slice 1.1 product semantics: active = enabled && available (runtime present).
    if runtime is not None and overlay_enabled:
        overlay_active = True
        if overlay_status == "idle" and overlay_running:
            overlay_status = "running"

    commentary_enabled = bool(commentary_snap.get("enabled", False))
    commentary_available = bool(commentary_snap.get("available", False))
    commentary_busy = bool(commentary_snap.get("busy", False))
    commentary_active = commentary_enabled and commentary_available
    commentary_status = str(
        commentary_snap.get("status")
        or (
            "disabled"
            if not commentary_enabled
            else ("speaking" if commentary_busy else ("ready" if commentary_available else "idle"))
        )
    )

    tape_enabled = bool(tape_snap.get("enabled", True))
    tape_available = bool(tape_snap.get("available", False))
    tape_active = bool(tape_snap.get("pathOpen", False))
    tape_status = str(
        tape_snap.get("status")
        or ("disabled" if not tape_enabled else ("recording" if tape_active else "idle"))
    )

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

    checked_at_mono = lhm.get("checked_at")
    last_ok_mono = lhm.get("last_success_at")
    lhm_detail: dict[str, Any] = {
        "connection": "reachable" if lhm_reachable else "unreachable",
        "lastBaseUrl": lhm.get("base_url"),
        "sensorRows": sensor_rows,
        "prerequisiteFor": list(lhm.get("prerequisite_for") or ["sysinfo.cpu_package"]),
        "checkedAt": (
            _mono_to_wall(float(checked_at_mono), now_mono=now, now_wall=now_wall)
            if checked_at_mono is not None
            else None
        ),
        "lastSuccessAt": (
            _mono_to_wall(float(last_ok_mono), now_mono=now, now_wall=now_wall)
            if last_ok_mono is not None
            else None
        ),
        "stale": bool(lhm.get("stale", False)),
        "errorCode": lhm.get("error_code"),
    }
    if lhm_tip:
        lhm_detail["tip"] = lhm_tip

    payload = {
        "schemaVersion": ADMIN_SCHEMA_VERSION,
        "version": __version__,
        "runtime": {
            "overlay": runtime is not None,
            "switcher": state is not None,
        },
        "switcher": switcher,
        "extensions": {
            "ble": _extension_card(
                ext_id="ble",
                label="BLE heart rate",
                enabled=ble_enabled,
                available=ble_available,
                active=ble_active,
                status=ble_status,
                detail={
                    "deviceName": bio_snap.get("deviceName", bio.device_name),
                    "bpm": bio_snap.get("bpm", bio.bpm),
                    "hrState": bio_snap.get("hrState", bio.state),
                    "source": bio_snap.get("source", "bluetooth"),
                    "deviceFilter": bio_snap.get("deviceFilter", "auto"),
                },
            ),
            "lhm": _extension_card(
                ext_id="lhm",
                label="Libre Hardware Monitor",
                enabled=None,
                required=lhm_required,
                requirement_mode=requirement_mode,
                available=lhm_reachable,
                active=lhm_active,
                status=lhm_status,
                detail=lhm_detail,
            ),
            "sysinfo": _extension_card(
                ext_id="sysinfo",
                label="System info",
                enabled=sys_enabled,
                available=sys_available,
                active=sys_active,
                status=sys_status,
                detail={
                    "cpuTemp": system.cpu.temperature,
                    "cpuPower": system.cpu.power,
                    "cpuLoad": system.cpu.load,
                    "gpuLoad": system.gpu.load,
                    "gpuTemp": system.gpu.temperature,
                    "lhmRequired": lhm_required,
                    "lhmRequirementMode": requirement_mode,
                    "lhmReachable": lhm_reachable,
                },
            ),
        },
        "features": {
            "overlay": _feature_card(
                enabled=overlay_enabled,
                available=overlay_available,
                active=overlay_active,
                status=overlay_status,
                theme=getattr(overlay_cfg, "theme", None) if overlay_cfg else None,
                activeWidgets=len(bus.active_events or []),
                mode=snap.get("mode"),
            ),
            "commentary": _feature_card(
                enabled=commentary_enabled,
                available=commentary_available,
                active=commentary_active,
                status=commentary_status,
                busy=commentary_busy,
                runtime=commentary_available,
                lastSpokeAt=commentary_snap.get("lastSpokeAt"),
            ),
            "tape": _feature_card(
                enabled=tape_enabled,
                available=tape_available,
                active=tape_active,
                status=tape_status,
                path=tape_snap.get("path"),
                sessionKey=tape_snap.get("sessionKey"),
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
    payload["health"] = evaluate_health(payload)
    return payload


def _activity_sort_key(row: dict[str, Any]) -> tuple[float, int, str]:
    return (
        -float(row.get("occurredAt") or 0.0),
        _SOURCE_PRIORITY.get(str(row.get("source") or ""), 9),
        str(row.get("dedupeKey") or ""),
    )


async def build_admin_activity(*, limit: int = 50) -> dict[str, Any]:
    limit = max(1, min(int(limit), 200))
    items: list[dict[str, Any]] = []
    now_mono = time.monotonic()
    now_wall = time.time()

    try:
        event_log = get_event_log()
        events = await event_log.get_recent_events(limit)
        for event in events:
            mono_s = (event.timestamp or 0) / 1000.0
            occurred = _mono_to_wall(mono_s, now_mono=now_mono, now_wall=now_wall)
            dedupe = f"switcher:{event.type}:{event.timestamp}:{event.message}"
            items.append(
                {
                    "occurredAt": occurred,
                    "monoMs": int(event.timestamp or 0),
                    "dedupeKey": dedupe,
                    "source": "switcher",
                    "kind": event.type,
                    "message": event.message,
                    "ephemeral": False,
                    "data": event.data or {},
                }
            )
    except Exception:
        logger.debug("Admin activity: switcher event log failed", exc_info=True)

    runtime = get_overlay_runtime()
    director = getattr(runtime, "commentary", None) if runtime is not None else None
    if director is not None and hasattr(director, "decisions"):
        try:
            for row in director.decisions(limit):
                action = str(row.get("action") or "skipped")
                text = str(row.get("text") or "")
                reason = str(row.get("reason") or "")
                mono_s = float(row.get("at") or 0.0)
                occurred = (
                    _mono_to_wall(mono_s, now_mono=now_mono, now_wall=now_wall)
                    if mono_s > 0
                    else now_wall
                )
                message = text if action == "spoken" and text else f"{action}: {reason}"
                node = row.get("nodeId") or ""
                dedupe = f"commentary:{action}:{node}:{mono_s}:{text}"
                items.append(
                    {
                        "occurredAt": occurred,
                        "monoMs": int(mono_s * 1000),
                        "dedupeKey": dedupe,
                        "source": "commentary",
                        "kind": action,
                        "message": message,
                        "ephemeral": False,
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
        activity_log = getattr(bus, "activity_log", None)
        if activity_log is not None and hasattr(activity_log, "latest"):
            for row in activity_log.latest(limit):
                items.append(dict(row))
    except Exception:
        logger.debug("Admin activity: overlay lifecycle log failed", exc_info=True)

    items.sort(key=_activity_sort_key)
    return {"schemaVersion": ADMIN_SCHEMA_VERSION, "items": items[:limit]}


async def handle_admin_status(_request: web.Request) -> web.Response:
    try:
        lhm = await _probe_lhm()
        payload = build_admin_status(lhm=lhm)
        return web.json_response(payload)
    except Exception:
        logger.exception("GET /api/admin/status failed")
        return web.json_response({"error": "admin status failed"}, status=500)


async def handle_admin_activity(request: web.Request) -> web.Response:
    raw = request.rel_url.query.get("limit")
    limit = 50
    if raw is not None:
        try:
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
