"""API server entry points."""
from __future__ import annotations

import asyncio
import json
import logging
import secrets
import time
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from aiohttp import web
from aiohttp.web_ws import WebSocketResponse
import aiohttp

# Import OAuth manager creator
from irswitch.oauth import create_oauth_manager, OAuthError

# Application config keys - use AppKey instances to avoid NotAppKeyWarning
APP_CONFIG = web.AppKey("config")
APP_CONFIG_PATH = web.AppKey("config_path")

# Mutable container for config to avoid DeprecationWarning when updating at runtime
# Using a list wrapper allows us to update config without triggering aiohttp's
# "Changing state of started or joined application is deprecated" warning
_config_container: list = [None]  # type: ignore[annotation-type-mismatch]


def get_app_config() -> "AppConfig | None":
    """Get config from container (thread-safe for our use case)."""
    return _config_container[0]


def set_app_config(config: "AppConfig") -> None:
    """Set config in container (thread-safe for our use case)."""
    _config_container[0] = config


if TYPE_CHECKING:
    from irswitch.logic.state_machine import StateMachine
    from irswitch.models import SwitchState
    from irswitch.obs.client import ObsClient

from irswitch import __version__
from irswitch.server.event_log import get_event_log
from irswitch.server.dashboards import handle_gr_status, handle_vr_status, handle_test_widget
from irswitch.server.metrics import get_metrics

logger = logging.getLogger(__name__)

# Global state for WebSocket broadcasting
_websocket_clients: set[web.WebSocketResponse] = set()
_current_state: "SwitchState | None" = None
_state_machine: "StateMachine | None" = None
_obs_client: "ObsClient | None" = None
_reader: Optional[object] = None  # IRacingReader instance
_restart_mode_active: bool = False
_shutdown_event: Optional[asyncio.Event] = None
_oauth_manager: "OAuthManager | None" = None  # YouTube OAuth manager


def reset_state() -> None:
    """Reset global state (for testing)."""
    global _current_state, _state_machine, _websocket_clients, _obs_client, _reader, _restart_mode_active, _shutdown_event
    _current_state = None
    _state_machine = None
    _websocket_clients = set()
    _obs_client = None
    _reader = None
    _restart_mode_active = False
    _shutdown_event = None


def set_shutdown_event(event: asyncio.Event) -> None:
    """Set shutdown event for API-triggered shutdown."""
    global _shutdown_event
    _shutdown_event = event


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


def set_reader(reader: object) -> None:
    """Set the iRacing reader instance for API handlers."""
    global _reader
    _reader = reader


def set_oauth_manager(oauth_manager: "OAuthManager | None") -> None:
    """Set the OAuth manager instance for API handlers."""
    global _oauth_manager
    _oauth_manager = oauth_manager


def get_oauth_manager() -> "OAuthManager | None":
    """Get the OAuth manager instance."""
    return _oauth_manager


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


def get_current_state() -> "SwitchState | None":
    """Get current switch state."""
    return _current_state


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
        "version": __version__,
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
        "session_type": state.session_type,
        "session_name": state.session_name,
        "session_num": state.session_num,
        "total_sessions": state.total_sessions if hasattr(state, 'total_sessions') else None,
    }
    
    # Format session_num as "x of y" if total_sessions is available
    if state.session_num is not None:
        total = state.total_sessions if hasattr(state, 'total_sessions') else None
        if total is not None and total > 0:
            # Convert 0-based to 1-based for display: "1 of 3"
            status["session_num_display"] = f"{state.session_num + 1} of {total}"
        else:
            # Just show 1-based number: "1"
            status["session_num_display"] = str(state.session_num + 1)
    else:
        status["session_num_display"] = None

    # Add OAuth status
    oauth_manager = get_oauth_manager()
    if oauth_manager is not None:
        status["oauth_configured"] = True
        status["oauth_authenticated"] = oauth_manager.is_authenticated()
        status["oauth_has_refresh_token"] = oauth_manager.has_refresh_token()
    else:
        status["oauth_configured"] = False
        status["oauth_authenticated"] = False
        status["oauth_has_refresh_token"] = False

    # Add streaming status and OBS profile if OBS client is available
    if _obs_client is not None and state.connected_obs:
        try:
            is_streaming, stream_duration_ms = await _obs_client.get_stream_status()
            status["streaming"] = is_streaming
            status["stream_duration_ms"] = stream_duration_ms
            
            # Get OBS profile
            try:
                obs_profile = await _obs_client.get_current_profile()
                status["obs_profile"] = obs_profile
            except Exception:
                status["obs_profile"] = None
            
            # Get stream selection status
            try:
                is_selected, is_ready_selected = await _obs_client.is_stream_selected()
                status["stream_selected"] = is_selected
                status["stream_ready_selected"] = is_ready_selected
            except Exception:
                status["stream_selected"] = False
                status["stream_ready_selected"] = False
            
            # Get cached stream info (don't make API calls from API endpoint)
            stream_title, stream_description, quota_exceeded = _obs_client.get_cached_stream_info()
            status["stream_title"] = stream_title
            status["stream_description"] = stream_description
            status["youtube_quota_exceeded"] = quota_exceeded
            
            # Get full cached stream info for extended fields
            stream_info_full = _obs_client.get_cached_stream_info_full()
            if stream_info_full:
                status["stream_scheduled_start_time"] = stream_info_full.get("scheduled_start_time")
                status["stream_actual_start_time"] = stream_info_full.get("actual_start_time")
                status["stream_concurrent_viewers"] = stream_info_full.get("concurrent_viewers")
                status["stream_status"] = stream_info_full.get("status")
                status["stream_privacy_status"] = stream_info_full.get("privacy_status")
            else:
                status["stream_scheduled_start_time"] = None
                status["stream_actual_start_time"] = None
                status["stream_concurrent_viewers"] = None
                status["stream_status"] = None
                status["stream_privacy_status"] = None
            
            # Update metrics with streaming status
            from irswitch.server.metrics import get_metrics
            metrics = get_metrics()
            metrics.set_streaming(is_streaming)
            
            # Add cumulative and current session stream duration from metrics
            stream_cumulative, stream_current = metrics.get_stream_duration_seconds()
            if stream_cumulative is not None:
                status["stream_duration_seconds"] = stream_cumulative
                status["stream_duration_current_session_seconds"] = stream_current
        except Exception as e:
            logger.debug(f"Failed to get stream status: {e}")
            status["streaming"] = False
            status["stream_duration_ms"] = None
            status["obs_profile"] = None
            status["stream_selected"] = False
            status["stream_ready_selected"] = False
            status["stream_title"] = None
            status["stream_description"] = None
            status["stream_scheduled_start_time"] = None
            status["stream_actual_start_time"] = None
            status["stream_concurrent_viewers"] = None
            status["stream_status"] = None
            status["stream_privacy_status"] = None
            # Update metrics
            from irswitch.server.metrics import get_metrics
            metrics = get_metrics()
            metrics.set_streaming(False)
    else:
        status["streaming"] = False
        status["stream_duration_ms"] = None
        status["obs_profile"] = None
        status["stream_selected"] = False
        status["stream_ready_selected"] = False
        status["stream_title"] = None
        status["stream_description"] = None
        status["stream_scheduled_start_time"] = None
        status["stream_actual_start_time"] = None
        status["stream_concurrent_viewers"] = None
        status["stream_status"] = None
        status["stream_privacy_status"] = None
        # Update metrics
        from irswitch.server.metrics import get_metrics
        metrics = get_metrics()
        metrics.set_streaming(False)
    
    return status


async def handle_get_status(request: web.Request) -> web.Response:
    """Handle GET /status endpoint."""
    try:
        if _current_state is None:
            return web.json_response({"error": "Service not initialized"}, status=503)

        status = await _get_status_dict(_current_state)
        return web.json_response(status)
    except Exception as e:
        logger.error(f"Error in /status endpoint: {e}", exc_info=True)
        return web.json_response({
            "error": "Internal server error",
            "message": str(e)
        }, status=500)


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

        # Log override event
        event_log = get_event_log()
        await event_log.add_event(
            "override_applied",
            f"Scene override applied: {scene} for {seconds}s",
            {"scene": scene, "seconds": seconds}
        )

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

        # Log autoswitch toggle event
        event_log = get_event_log()
        await event_log.add_event(
            "autoswitch_toggled",
            f"Autoswitch {'enabled' if new_state.autoswitch else 'disabled'}",
            {"autoswitch": new_state.autoswitch}
        )

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


async def handle_health(request: web.Request) -> web.Response:
    """Handle GET /health endpoint."""
    checks = {}
    overall_status = "healthy"
    
    # Check iRacing connection
    iracing_connected = _current_state is not None and _current_state.connected_iracing if _current_state else False
    checks["iracing"] = {
        "status": "connected" if iracing_connected else "disconnected",
        "available": iracing_connected,
    }
    if not iracing_connected:
        overall_status = "degraded"
    
    # Check OBS connection
    obs_connected = _current_state is not None and _current_state.connected_obs if _current_state else False
    checks["obs"] = {
        "status": "connected" if obs_connected else "disconnected",
        "available": obs_connected,
    }
    if not obs_connected:
        overall_status = "degraded"
    
    # Check API server
    checks["api"] = {
        "status": "running",
        "available": True,
    }
    
    # If both critical services are down, mark as unhealthy
    if not iracing_connected and not obs_connected:
        overall_status = "unhealthy"
    
    return web.json_response({
        "status": overall_status,
        "version": __version__,
        "checks": checks,
        "timestamp": int(time.time() * 1000),
    })


async def handle_metrics(request: web.Request) -> web.Response:
    """Handle GET /metrics endpoint."""
    metrics = get_metrics()
    metrics_dict = metrics.to_dict(_current_state)
    return web.json_response(metrics_dict)


async def handle_config_reload(request: web.Request) -> web.Response:
    """Handle POST /config/reload endpoint."""
    import warnings
    from irswitch.config import AppConfig

    config_path = request.app.get(APP_CONFIG_PATH)
    if not config_path:
        return web.json_response({"error": "Config path not available"}, status=500)

    try:
        # Load and validate new config
        new_config = AppConfig.from_file(config_path)

        # Update global config - suppress DeprecationWarning for intentional runtime update
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            request.app[APP_CONFIG] = new_config

        logger.info("Config reloaded successfully")
        return web.json_response({
            "status": "success",
            "message": "Config reloaded successfully",
        })
    except FileNotFoundError as e:
        logger.error(f"Config file not found during reload: {e}")
        return web.json_response({
            "error": f"Config file not found: {e}",
        }, status=400)
    except Exception as e:
        logger.error(f"Failed to reload config: {e}", exc_info=True)
        return web.json_response({
            "error": f"Failed to reload config: {str(e)}",
        }, status=400)


async def handle_shutdown(request: web.Request) -> web.Response:
    """Handle POST /shutdown endpoint."""
    global _shutdown_event
    if _shutdown_event is None:
        return web.json_response({"error": "Shutdown not available"}, status=503)
    
    logger.info("Shutdown requested via API")
    _shutdown_event.set()
    return web.json_response({
        "status": "shutting_down",
        "message": "Service shutdown initiated"
    })


async def handle_reset(request: web.Request) -> web.Response:
    """Handle POST /reset endpoint - reset state and metrics to CONNECTING."""
    global _current_state, _state_machine
    from irswitch.models import DrivingMode, SwitchState
    from irswitch.server.metrics import get_metrics, reset_metrics
    
    if _state_machine is None:
        return web.json_response({"error": "State machine not available"}, status=503)
    
    # Get safe_scene from policy
    safe_scene = _state_machine._policy.safe_scene
    
    # Get current connection states before reset
    was_iracing_connected = _current_state.connected_iracing if _current_state else False
    was_obs_connected = _current_state.connected_obs if _current_state else False
    
    # Reset metrics
    reset_metrics()
    metrics = get_metrics()
    
    # Restart metrics tracking for currently connected services
    if was_iracing_connected:
        metrics.set_iracing_connected(True)
    if was_obs_connected:
        metrics.set_obs_connected(True)
    
    # Reset restart mode
    set_restart_mode(False)
    
    # Create new CONNECTING state
    new_state = SwitchState(
        connected_iracing=was_iracing_connected,
        connected_obs=was_obs_connected,
        autoswitch=_current_state.autoswitch if _current_state else True,
        override_scene=None,
        override_until=None,
        mode=DrivingMode.CONNECTING,
        target_scene=safe_scene,
        current_scene=safe_scene,
        last_switch_ts=None,
        reason="reset:connecting",
        session_type=None,
        session_name=None,
        session_num=None,
        stream_extended_info=None,
    )
    
    set_current_state(new_state)
    logger.info("State and metrics reset to CONNECTING via API")
    
    status = await _get_status_dict(new_state)
    return web.json_response({
        "status": "reset",
        "message": "State and metrics reset to CONNECTING",
        **status
    })


async def handle_get_events(request: web.Request) -> web.Response:
    """
    Handle GET /api/events endpoint.
    
    Returns last N events from rotating event log (FIFO).
    Event log automatically rotates when full - oldest events are removed.
    """
    try:
        count_str = request.query.get("count", "50")
        count = int(count_str) if count_str.isdigit() else 50
        if count <= 0:
            count = 50
    except (ValueError, TypeError):
        count = 50

    event_log = get_event_log()
    # Get recent events (log automatically rotates to max_size, so this returns last N)
    events = await event_log.get_recent_events(count)

    # Convert events to dict for JSON serialization
    events_dict = [
        {
            "timestamp": e.timestamp,
            "type": e.type,
            "message": e.message,
            "data": e.data,
        }
        for e in events
    ]

    return web.json_response({"events": events_dict})


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


# OAuth state storage for CSRF protection
_oauth_states: dict[str, float] = {}


async def handle_oauth_initiate(request: web.Request) -> web.Response:
    """
    Handle GET /oauth/initiate endpoint - initiates OAuth flow.
    
    Returns authorization URL for user to click and authorize the app.
    """
    oauth_manager = create_oauth_manager()
    
    if oauth_manager is None:
        return web.json_response({
            "error": "OAuth not configured",
            "message": "Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET environment variables",
        }, status=503)
    
    # Generate random state for CSRF protection
    state = secrets.token_urlsafe(32)
    # Store state with timestamp for expiration check (valid for 10 minutes)
    _oauth_states[state] = time.time()
    
    auth_url = oauth_manager.get_authorization_url(state)
    
    logger.info("OAuth authorization URL generated")
    
    return web.json_response({
        "authorization_url": auth_url,
        "state": state,
        "instructions": "Open the authorization URL in a browser, authorize the app, and copy the code from the redirect URL.",
    })


async def handle_oauth_callback(request: web.Request) -> web.Response:
    """
    Handle GET /oauth/callback endpoint - receives OAuth authorization code.
    
    Exchanges code for tokens and saves them.
    """
    oauth_manager = create_oauth_manager()
    
    if oauth_manager is None:
        return web.json_response({
            "error": "OAuth not configured",
            "message": "Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET environment variables",
        }, status=503)
    
    # Get code and state from query parameters
    code = request.query.get("code")
    state = request.query.get("state")
    
    if not code:
        return web.json_response({
            "error": "Missing authorization code",
            "message": "Authorization code not found in callback URL",
        }, status=400)
    
    if not state:
        return web.json_response({
            "error": "Missing state parameter",
            "message": "State parameter not found in callback URL",
        }, status=400)
    
    # Validate state (CSRF protection)
    if state not in _oauth_states:
        return web.json_response({
            "error": "Invalid state",
            "message": "State parameter is invalid or expired",
        }, status=400)
    
    # Check state expiration (10 minutes)
    state_timestamp = _oauth_states.pop(state)
    if time.time() - state_timestamp > 600:
        return web.json_response({
            "error": "State expired",
            "message": "State parameter has expired. Please restart the OAuth flow.",
        }, status=400)
    
    try:
        async with aiohttp.ClientSession() as session:
            token = await oauth_manager.exchange_code_for_tokens(code, session)
            
            logger.info("OAuth authentication successful")
            
            return web.json_response({
                "status": "authenticated",
                "message": "OAuth authentication successful! YouTube API is now authorized.",
                "expires_in_seconds": token.expires_in_seconds(),
                "has_refresh_token": token.refresh_token is not None,
            })
    except OAuthError as e:
        logger.error(f"OAuth error: {e}")
        return web.json_response({
            "error": "OAuth error",
            "message": str(e),
        }, status=500)
    except Exception as e:
        logger.error(f"OAuth callback error: {e}", exc_info=True)
        return web.json_response({
            "error": "Authentication failed",
            "message": str(e),
        }, status=500)


async def handle_oauth_status(request: web.Request) -> web.Response:
    """
    Handle GET /oauth/status endpoint - check OAuth authentication status.
    """
    oauth_manager = create_oauth_manager()
    
    if oauth_manager is None:
        return web.json_response({
            "configured": False,
            "message": "OAuth not configured - set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET",
        })
    
    authenticated = oauth_manager.is_authenticated()
    has_refresh = oauth_manager.has_refresh_token()
    
    # Try to get token info if authenticated
    token_info = None
    if authenticated:
        # Load token from disk
        await oauth_manager.load_token()
        if oauth_manager._token:
            token = oauth_manager._token
            token_info = {
                "expires_in_seconds": token.expires_in_seconds(),
                "is_expired": token.is_expired(),
            }
    
    return web.json_response({
        "configured": True,
        "authenticated": authenticated,
        "has_refresh_token": has_refresh,
        "token": token_info,
    })


async def handle_oauth_revoke(request: web.Request) -> web.Response:
    """
    Handle POST /oauth/revoke endpoint - revoke OAuth tokens.
    """
    oauth_manager = create_oauth_manager()
    
    if oauth_manager is None:
        return web.json_response({
            "error": "OAuth not configured",
        }, status=503)
    
    try:
        async with aiohttp.ClientSession() as session:
            await oauth_manager.revoke_token(session)
        
        return web.json_response({
            "status": "revoked",
            "message": "OAuth tokens have been revoked",
        })
    except Exception as e:
        logger.error(f"OAuth revoke error: {e}")
        return web.json_response({
            "error": "Revoke failed",
            "message": str(e),
        }, status=500)


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
    app.router.add_get("/api/events", handle_get_events)
    app.router.add_get("/health", handle_health)
    app.router.add_get("/metrics", handle_metrics)
    app.router.add_post("/config/reload", handle_config_reload)
    app.router.add_post("/shutdown", handle_shutdown)
    app.router.add_post("/reset", handle_reset)
    app.router.add_get("/gr-status", handle_gr_status)
    app.router.add_get("/vr-status", handle_vr_status)
    app.router.add_get("/test", handle_test_widget)
    app.router.add_get("/ws", handle_websocket)
    app.router.add_get("/oauth/initiate", handle_oauth_initiate)
    app.router.add_get("/oauth/callback", handle_oauth_callback)
    app.router.add_get("/oauth/status", handle_oauth_status)
    app.router.add_post("/oauth/revoke", handle_oauth_revoke)

    # Static asset routes for favicon and app icons
    # __file__ is in src/irswitch/server/api.py, so go up 4 levels to reach project root
    assets_path = Path(__file__).resolve().parents[3] / "assets"
    app.router.add_static("/assets/", assets_path)
    app.router.add_get("/favicon.ico", lambda r: web.FileResponse(assets_path / "favicon" / "favicon.ico"))
    app.router.add_get("/apple-touch-icon.png", lambda r: web.FileResponse(assets_path / "favicon" / "apple-touch-icon.png"))

    return app
