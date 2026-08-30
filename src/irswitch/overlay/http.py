"""Overlay HTTP/WebSocket handlers. Separate from switcher /ws."""

from __future__ import annotations

import logging
import mimetypes
import sys
from pathlib import Path
from typing import Any

from aiohttp import web
from aiohttp.web_ws import WebSocketResponse

from irswitch.events.manager import DEBUG_EVENT_NAMES
from irswitch.overlay.bus import OverlayBus
from irswitch.overlay.config_io import apply_overlay_values
from irswitch.overlay.display import AssetManifest
from irswitch.overlay.display_v4 import V4AssetResolver
from irswitch.overlay.i18n import copy_catalog_for_renderer, normalize_language
from irswitch.overlay.schema import overlay_values, schema_as_dicts

logger = logging.getLogger(__name__)

mimetypes.add_type("video/webm", ".webm")

CSRF_HEADER = "X-Requested-With"
CSRF_VALUE = "irswitch"

_overlay_bus: OverlayBus | None = None
_overlay_runtime: Any = None
_overlay_clients: set[WebSocketResponse] = set()


def web_root() -> Path:
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / "irswitch" / "web"
    return Path(__file__).resolve().parents[1] / "web"


def get_overlay_bus() -> OverlayBus:
    global _overlay_bus
    if _overlay_bus is None:
        _overlay_bus = OverlayBus()
    return _overlay_bus


def set_overlay_bus(bus: OverlayBus | None) -> None:
    global _overlay_bus
    _overlay_bus = bus


def get_overlay_runtime() -> Any | None:
    """Public read-only accessor for the process overlay runtime (None when down)."""
    return _overlay_runtime


def set_overlay_runtime(runtime: Any) -> None:
    global _overlay_runtime
    _overlay_runtime = runtime


def reset_overlay_server() -> None:
    global _overlay_bus, _overlay_runtime, _overlay_clients
    _overlay_bus = None
    _overlay_runtime = None
    _overlay_clients = set()


def _is_localhost(request: web.Request) -> bool:
    peer = request.remote or ""
    return peer in {"127.0.0.1", "::1", "localhost"}


def _require_csrf(request: web.Request) -> web.Response | None:
    if not _is_localhost(request):
        return web.json_response({"error": "localhost only"}, status=403)
    if request.headers.get(CSRF_HEADER) != CSRF_VALUE:
        return web.json_response({"error": "missing CSRF header"}, status=403)
    return None


def _file_response(relative: str) -> web.FileResponse | web.Response:
    path = web_root() / relative
    if not path.is_file():
        return web.Response(text=f"Missing {relative}", status=404)
    return web.FileResponse(path)


def presentation_payload() -> dict[str, Any]:
    """Theme id + resolved asset slots for the overlay HUD. Missing files are null."""
    theme = "cyber_racing"
    v4_assets = False
    v4_renderer = False
    language = "en"
    try:
        from irswitch.server.api import get_app_config

        cfg = get_app_config()
        if cfg is not None:
            theme = cfg.overlay.theme or theme
            v4_assets = bool(cfg.overlay.v4.assets)
            v4_renderer = bool(cfg.overlay.v4.renderer)
            language = cfg.overlay.language or language
    except Exception:
        logger.debug("Overlay theme lookup failed", exc_info=True)
    dumped = AssetManifest(theme, web_root()).to_dict()
    payload: dict[str, Any] = {"theme": dumped["theme"], "assets": dumped["assets"]}
    if v4_assets or v4_renderer:
        v4_block: dict[str, Any] = {
            "assets": v4_assets,
            "renderer": v4_renderer,
            "manifestUrl": "/overlay/web/themes-v4/manifest.json",
            "catalogUrl": "/overlay/web/themes-v4/event_catalog.json",
            "language": language,
            "copyCatalog": copy_catalog_for_renderer(language),
            "resolved": None,
            "manifestError": None,
        }
        try:
            resolver = V4AssetResolver.load(theme, web_root())
            v4_block["resolved"] = resolver.to_dict()
        except Exception as exc:
            # Broken/missing V4 manifest must not take down snapshot or WS boot.
            logger.warning("V4 manifest resolve failed: %s", exc)
            v4_block["manifestError"] = str(exc) or exc.__class__.__name__
        payload["v4"] = v4_block
    return payload


async def handle_overlay_i18n(request: web.Request) -> web.Response:
    """Return overlay copy catalog for the configured language (+ EN fallback)."""
    language = "en"
    try:
        from irswitch.server.api import get_app_config

        cfg = get_app_config()
        if cfg is not None:
            language = normalize_language(cfg.overlay.language)
    except Exception:
        logger.debug("Overlay language lookup failed", exc_info=True)
    return web.json_response(
        {"language": language, "copyCatalog": copy_catalog_for_renderer(language)}
    )


async def handle_overlay_page(request: web.Request) -> web.StreamResponse:
    return _file_response("overlay/index.html")


async def handle_overlay_debug_page(request: web.Request) -> web.StreamResponse:
    return _file_response("debug/index.html")


async def handle_overlay_demo_page(request: web.Request) -> web.StreamResponse:
    return _file_response("demo/index.html")


async def handle_overlay_golden_page(request: web.Request) -> web.StreamResponse:
    return _file_response("overlay/golden.html")


async def handle_config_page(request: web.Request) -> web.StreamResponse:
    return _file_response("config/index.html")


async def handle_overlay_ws(request: web.Request) -> WebSocketResponse:
    ws = WebSocketResponse()
    await ws.prepare(request)
    bus = get_overlay_bus()
    _overlay_clients.add(ws)
    await bus.add_client(ws, extra=presentation_payload())
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.ERROR:
                break
    finally:
        bus.discard_client(ws)
        _overlay_clients.discard(ws)
    return ws


async def handle_overlay_snapshot(request: web.Request) -> web.Response:
    payload = get_overlay_bus().snapshot()
    payload.update(presentation_payload())
    return web.json_response(payload)


async def handle_debug_emit(request: web.Request) -> web.Response:
    denied = _require_csrf(request)
    if denied is not None:
        return denied
    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)
    name = str(body.get("name") or "")
    if name not in DEBUG_EVENT_NAMES:
        return web.json_response(
            {"error": "unknown event", "allowed": list(DEBUG_EVENT_NAMES)}, status=400
        )
    runtime = _overlay_runtime
    bus = get_overlay_bus()
    now = __import__("time").monotonic()
    manager_v2 = getattr(runtime, "manager_v2", None)
    if manager_v2 is not None:
        race_event, envelopes = manager_v2.inject(name, now, body.get("data"))
        if race_event is None:
            return web.json_response({"error": "inject rejected"}, status=409)
        wires = manager_v2.publish_wire(envelopes, race_event)
        for wire in wires:
            await bus.publish_event(wire)
        bus.set_active_events(manager_v2.active_events())
        bus.set_active_stories_v4(manager_v2.active_stories_v4())
        await bus.flush_state()
        return web.json_response(
            {"status": "ok", "events": wires, "format": "v4" if envelopes else "legacy"}
        )
    manager = getattr(runtime, "manager", None)
    if manager is None:
        from irswitch.events.manager import EventManager

        manager = EventManager()
    event = manager.inject(name, now, body.get("data"))
    if event is None:
        return web.json_response({"error": "inject rejected"}, status=409)
    await bus.publish_event(event.to_envelope())
    bus.set_active_events(manager.active_events())
    await bus.flush_state()
    return web.json_response({"status": "ok", "event": event.to_envelope()})


async def handle_debug_catalog(request: web.Request) -> web.Response:
    return web.json_response({"events": list(DEBUG_EVENT_NAMES)})


def _redact_switcher(config: Any) -> dict[str, Any]:
    return {
        "app.http_host": config.http_host,
        "app.http_port": config.http_port,
        "app.log_level": config.log_level,
        "iracing.poll_hz": config.poll_hz,
        "obs.ws_url": config.obs_ws_url,
        "obs.password": "***" if config.obs_password else None,
        "switching.safe_scene": config.safe_scene,
        "switching.debounce_ms": config.debounce_ms,
        "switching.cooldown_ms": config.cooldown_ms,
        "switching.autoswitch_default": config.autoswitch_default,
    }


async def handle_get_config(request: web.Request) -> web.Response:
    from irswitch.server.api import get_app_config

    config = get_app_config()
    if config is None:
        config = request.app.get("config")
    if config is None:
        return web.json_response({"error": "config unavailable"}, status=500)
    return web.json_response(
        {
            "schema": schema_as_dicts(),
            "overlay": overlay_values(config.overlay),
            "switcher": _redact_switcher(config),
        }
    )


async def handle_put_config(request: web.Request) -> web.Response:
    denied = _require_csrf(request)
    if denied is not None:
        return denied
    from irswitch.config import AppConfig
    from irswitch.config_reload import classify_reload_diff
    from irswitch.server.api import get_app_config, set_app_config
    from irswitch.server.app_keys import APP_CONFIG as APP_CONFIG_KEY
    from irswitch.server.app_keys import APP_CONFIG_PATH as APP_CONFIG_PATH_KEY

    try:
        body = await request.json()
    except Exception:
        return web.json_response({"error": "invalid JSON"}, status=400)
    values = body.get("values")
    if not isinstance(values, dict):
        return web.json_response({"error": "values object required"}, status=400)

    config_path = request.app.get(APP_CONFIG_PATH_KEY)
    if not config_path:
        return web.json_response({"error": "Config path not available"}, status=500)
    try:
        applied = apply_overlay_values(Path(config_path), values)
        old_config = get_app_config()
        new_config = AppConfig.from_file(config_path)
        applied_live, needs_restart = classify_reload_diff(old_config, new_config)
        set_app_config(new_config)
        import warnings

        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            request.app[APP_CONFIG_KEY] = new_config
    except ValueError as exc:
        return web.json_response({"error": str(exc)}, status=400)
    except Exception as exc:
        logger.warning("Config write failed: %s", exc, exc_info=True)
        return web.json_response({"error": "write failed"}, status=500)
    return web.json_response(
        {
            "status": "ok",
            "applied": applied,
            "applied_live": applied_live,
            "needs_restart": needs_restart,
        }
    )


def register_overlay_routes(app: web.Application) -> None:
    root = web_root()
    app.router.add_get("/overlay", handle_overlay_page)
    app.router.add_get("/overlay/", handle_overlay_page)
    app.router.add_get("/overlay/debug", handle_overlay_debug_page)
    app.router.add_get("/overlay/demo", handle_overlay_demo_page)
    app.router.add_get("/overlay/demo/", handle_overlay_demo_page)
    app.router.add_get("/overlay/golden", handle_overlay_golden_page)
    app.router.add_get("/config", handle_config_page)
    from irswitch.commentary.http import register_commentary_routes

    register_commentary_routes(app)
    app.router.add_get("/ws/overlay", handle_overlay_ws)
    app.router.add_get("/api/overlay/snapshot", handle_overlay_snapshot)
    app.router.add_get("/api/overlay/i18n", handle_overlay_i18n)
    app.router.add_get("/api/overlay/debug/events", handle_debug_catalog)
    app.router.add_post("/overlay/debug/emit", handle_debug_emit)
    app.router.add_get("/api/config", handle_get_config)
    app.router.add_put("/api/config", handle_put_config)
    if root.is_dir():
        app.router.add_static("/overlay/static/", root / "overlay")
        app.router.add_static("/overlay/web/", root)
