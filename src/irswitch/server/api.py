"""API server entry points."""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING

from aiohttp import web
from aiohttp.web_ws import WebSocketResponse

if TYPE_CHECKING:
    from irswitch.logic.state_machine import StateMachine
    from irswitch.models import SwitchState
    from irswitch.obs.client import ObsClient

logger = logging.getLogger(__name__)

# Global state for WebSocket broadcasting
_websocket_clients: set[web.WebSocketResponse] = set()
_current_state: "SwitchState | None" = None
_state_machine: "StateMachine | None" = None
_obs_client: "ObsClient | None" = None
_restart_mode_active: bool = False


def reset_state() -> None:
    """Reset global state (for testing)."""
    global _current_state, _state_machine, _websocket_clients, _obs_client, _restart_mode_active
    _current_state = None
    _state_machine = None
    _websocket_clients = set()
    _obs_client = None
    _restart_mode_active = False


def set_restart_mode(active: bool) -> None:
    """Set RESTART mode active state."""
    global _restart_mode_active
    _restart_mode_active = active


def get_restart_mode() -> bool:
    """Get RESTART mode active state."""
    return _restart_mode_active


def set_state_machine(state_machine: "StateMachine") -> None:
    """Set the state machine instance for API handlers."""
    global _state_machine
    _state_machine = state_machine


def set_obs_client(obs_client: "ObsClient") -> None:
    """Set the OBS client instance for API handlers."""
    global _obs_client
    _obs_client = obs_client


async def _broadcast_state_update(state: "SwitchState") -> None:
    """Broadcast state update to all WebSocket clients with streaming info."""
    global _websocket_clients
    
    if not _websocket_clients:
        return
    
    # Get full status including streaming info
    status = await _get_status_dict(state)
    message = json.dumps(status)
    disconnected = set()

    for ws in _websocket_clients:
        try:
            if not ws.closed:
                await ws.send_str(message)
            else:
                disconnected.add(ws)
        except Exception as e:
            logger.warning(f"Error broadcasting to WebSocket client: {e}")
            disconnected.add(ws)

    # Remove disconnected clients
    _websocket_clients -= disconnected


def set_current_state(state: "SwitchState") -> None:
    """Update current state and broadcast to WebSocket clients."""
    global _current_state, _websocket_clients
    _current_state = state

    # Broadcast to all WebSocket clients (async task for stream status)
    if _websocket_clients:
        asyncio.create_task(_broadcast_state_update(state))


async def _get_status_dict(state: "SwitchState") -> dict:
    """Convert SwitchState to dictionary with streaming info."""
    status = {
        "connected_iracing": state.connected_iracing,
        "connected_obs": state.connected_obs,
        "autoswitch": state.autoswitch,
        "override_scene": state.override_scene,
        "override_until": state.override_until,
        "mode": state.mode.value,
        "target_scene": state.target_scene,
        "current_scene": state.current_scene,
        "last_switch_ts": state.last_switch_ts,
        "reason": state.reason,
        "restart_mode_active": _restart_mode_active,
    }
    
    # Add streaming status if OBS client is available
    if _obs_client is not None and state.connected_obs:
        try:
            is_streaming, stream_duration_ms = await _obs_client.get_stream_status()
            status["streaming"] = is_streaming
            status["stream_duration_ms"] = stream_duration_ms
        except Exception as e:
            logger.debug(f"Failed to get stream status: {e}")
            status["streaming"] = False
            status["stream_duration_ms"] = None
    else:
        status["streaming"] = False
        status["stream_duration_ms"] = None
    
    return status


async def handle_get_status(request: web.Request) -> web.Response:
    """Handle GET /status endpoint."""
    if _current_state is None:
        return web.json_response({"error": "Service not initialized"}, status=503)

    status = await _get_status_dict(_current_state)
    return web.json_response(status)


async def handle_override(request: web.Request) -> web.Response:
    """Handle POST /override endpoint."""
    if _state_machine is None or _current_state is None:
        return web.json_response({"error": "Service not initialized"}, status=503)

    try:
        data = await request.json()
        scene = data.get("scene")
        seconds = data.get("seconds", 120)

        if not scene:
            return web.json_response({"error": "scene is required"}, status=400)

        if not isinstance(seconds, int) or seconds <= 0:
            return web.json_response({"error": "seconds must be a positive integer"}, status=400)

        new_state = _state_machine.apply_override(_current_state, scene, seconds)
        set_current_state(new_state)

        status = await _get_status_dict(new_state)
        return web.json_response(status)

    except json.JSONDecodeError:
        return web.json_response({"error": "Invalid JSON"}, status=400)
    except Exception as e:
        logger.error(f"Error handling override: {e}", exc_info=True)
        return web.json_response({"error": "Internal server error"}, status=500)


async def handle_toggle_autoswitch(request: web.Request) -> web.Response:
    """Handle POST /autoswitch/toggle endpoint."""
    if _state_machine is None or _current_state is None:
        return web.json_response({"error": "Service not initialized"}, status=503)

    try:
        new_state = _state_machine.toggle_autoswitch(_current_state)
        set_current_state(new_state)

        status = await _get_status_dict(new_state)
        return web.json_response(status)

    except Exception as e:
        logger.error(f"Error toggling autoswitch: {e}", exc_info=True)
        return web.json_response({"error": "Internal server error"}, status=500)


async def handle_restart_mode_reset(request: web.Request) -> web.Response:
    """Handle POST /restart-mode/reset endpoint."""
    global _restart_mode_active
    
    _restart_mode_active = False
    logger.info("RESTART mode deactivated via API")
    
    if _current_state is not None:
        status = await _get_status_dict(_current_state)
        return web.json_response(status)
    
    return web.json_response({"restart_mode_active": False})


async def handle_websocket(request: web.Request) -> web.WebSocketResponse:
    """Handle WebSocket /ws endpoint."""
    ws = WebSocketResponse()
    await ws.prepare(request)

    _websocket_clients.add(ws)
    logger.info("WebSocket client connected")

    # Send current state immediately
    if _current_state is not None:
        status = await _get_status_dict(_current_state)
        await ws.send_str(json.dumps(status))

    try:
        async for msg in ws:
            # Echo back or handle messages if needed
            if msg.type == web.WSMsgType.TEXT:
                # For now, just keep connection alive
                pass
            elif msg.type == web.WSMsgType.ERROR:
                logger.warning(f"WebSocket error: {ws.exception()}")
                break
    finally:
        _websocket_clients.discard(ws)
        logger.info("WebSocket client disconnected")

    return ws


def create_app() -> web.Application:
    """
    Create aiohttp application with REST and WebSocket endpoints.

    Returns:
        Configured aiohttp application
    """
    app = web.Application()

    # CORS middleware for local development (new-style middleware)
    @web.middleware
    async def cors_middleware(request: web.Request, handler):
        if request.method == "OPTIONS":
            response = web.Response()
        else:
            response = await handler(request)

        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    app.middlewares.append(cors_middleware)

    # Routes
    app.router.add_get("/status", handle_get_status)
    app.router.add_post("/override", handle_override)
    app.router.add_post("/autoswitch/toggle", handle_toggle_autoswitch)
    app.router.add_post("/restart-mode/reset", handle_restart_mode_reset)
    app.router.add_get("/ws", handle_websocket)

    return app
