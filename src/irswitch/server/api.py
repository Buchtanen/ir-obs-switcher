"""API server entry points."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

import aiohttp
from aiohttp import web
from aiohttp.web_ws import WebSocketResponse

from irswitch import __version__
from irswitch.config import AppConfig
from irswitch.oauth import OAuthError, create_oauth_manager
from irswitch.server.app_keys import APP_CONFIG, APP_CONFIG_PATH
from irswitch.server.dashboards import (
    handle_gr_status,
    handle_test_widget,
    handle_vr_status,
)
from irswitch.server.event_log import get_event_log
from irswitch.server.metrics import get_metrics
from irswitch.server.task_registry import TaskRegistry

# Mutable container for config to avoid DeprecationWarning when updating at runtime
# Using a list wrapper allows us to update config without triggering aiohttp's
# "Changing state of started or joined application is deprecated" warning
_config_container: list[AppConfig | None] = [None]


def get_app_config() -> AppConfig | None:
    """Get config from container (thread-safe for our use case)."""
    return _config_container[0]


def set_app_config(config: AppConfig) -> None:
    """Set config in container (thread-safe for our use case)."""
    _config_container[0] = config


if TYPE_CHECKING:
    from irswitch.logic.state_machine import StateMachine
    from irswitch.models import SwitchState
    from irswitch.oauth import OAuthManager
    from irswitch.obs.client import ObsClient

logger = logging.getLogger(__name__)

# Global state for WebSocket broadcasting
_websocket_clients: set[web.WebSocketResponse] = set()
_current_state: SwitchState | None = None
_state_machine: StateMachine | None = None
_obs_client: ObsClient | None = None
_reader: object | None = None  # IRacingReader instance
_restart_mode_active: bool = False
_shutdown_event: asyncio.Event | None = None
_oauth_manager: OAuthManager | None = None  # YouTube OAuth manager
_task_registry = TaskRegistry()


def reset_state() -> None:
    """Reset global state (for testing)."""
    global _current_state, _state_machine, _websocket_clients, _obs_client, _reader, _restart_mode_active, _shutdown_event, _task_registry
    _current_state = None
    _state_machine = None
    _websocket_clients = set()
    _obs_client = None
    _reader = None
    _restart_mode_active = False
    _shutdown_event = None
    _task_registry = TaskRegistry()


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


def set_state_machine(state_machine: StateMachine) -> None:
    """Set the state machine instance for API handlers."""
    global _state_machine
    _state_machine = state_machine


def set_obs_client(obs_client: ObsClient) -> None:
    """Set the OBS client instance for API handlers."""
    global _obs_client
    _obs_client = obs_client


def set_reader(reader: object) -> None:
    """Set the iRacing reader instance for API handlers."""
    global _reader
    _reader = reader


def set_oauth_manager(oauth_manager: OAuthManager | None) -> None:
    """Set the OAuth manager instance for API handlers."""
    global _oauth_manager
    _oauth_manager = oauth_manager


def get_oauth_manager() -> OAuthManager | None:
    """Get the OAuth manager instance."""
    return _oauth_manager


def _create_oauth_manager_from_config(request: web.Request | None = None) -> OAuthManager | None:
    """
    Create OAuth manager from config.ini or environment variables.

    Priority: config.ini > environment variables

    Args:
        request: Optional web request to get config from app context
    """
    config = None

    # Try to get config from request.app first (preferred)
    if request is not None:
        config = request.app.get(APP_CONFIG)

    # Fall back to container if no request provided
    if config is None:
        config = get_app_config()

    # Try to get credentials from config first
    client_id = None
    client_secret = None

    if config and config.oauth_client_id and config.oauth_client_secret:
        client_id = config.oauth_client_id
        client_secret = config.oauth_client_secret
        logger.debug("Using OAuth credentials from config.ini")

    # Fall back to environment variables if not in config
    return create_oauth_manager(
        client_id=client_id,
        client_secret=client_secret,
    )


async def _broadcast_state_update(state: SwitchState) -> None:
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


def get_current_state() -> SwitchState | None:
    """Get current switch state."""
    return _current_state


def set_current_state(state: SwitchState) -> None:
    """Update current state and broadcast to WebSocket clients."""
    global _current_state, _websocket_clients
    _current_state = state

    # Broadcast to all WebSocket clients (tracked task; replace avoids pile-up)
    if _websocket_clients:
        _task_registry.spawn("ws_broadcast", _broadcast_state_update(state), replace=True)


async def _get_status_dict(state: SwitchState) -> dict:
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
        "total_sessions": (state.total_sessions if hasattr(state, "total_sessions") else None),
    }

    # Format session_num as "x of y" if total_sessions is available
    if state.session_num is not None:
        total = state.total_sessions if hasattr(state, "total_sessions") else None
        if total is not None and total > 0:
            # Convert 0-based to 1-based for display: "1 of 3"
            status["session_num_display"] = f"{state.session_num + 1} of {total}"
        else:
            # Just show 1-based number: "1"
            status["session_num_display"] = str(state.session_num + 1)
    else:
        status["session_num_display"] = None

    # Add OAuth status
    # Use global OAuth manager (set in main.py) or try to create from config
    oauth_manager = get_oauth_manager()
    if oauth_manager is None:
        # Fallback: try to create from config if global manager not set
        config = get_app_config()
        if config:
            oauth_manager = create_oauth_manager(
                client_id=config.oauth_client_id,
                client_secret=config.oauth_client_secret,
            )

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
            stream_title, stream_description, quota_exceeded, api_key_missing = (
                _obs_client.get_cached_stream_info()
            )
            status["stream_title"] = stream_title
            status["stream_description"] = stream_description
            status["youtube_quota_exceeded"] = quota_exceeded
            status["youtube_api_key_missing"] = api_key_missing

            # Get full cached stream info for extended fields
            stream_info_full = _obs_client.get_cached_stream_info_full()
            if stream_info_full and isinstance(stream_info_full, dict):
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
        return web.json_response({"error": "Internal server error", "message": str(e)}, status=500)


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
            {"scene": scene, "seconds": seconds},
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
            {"autoswitch": new_state.autoswitch},
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
    iracing_connected = (
        _current_state is not None and _current_state.connected_iracing if _current_state else False
    )
    checks["iracing"] = {
        "status": "connected" if iracing_connected else "disconnected",
        "available": iracing_connected,
    }
    if not iracing_connected:
        overall_status = "degraded"

    # Check OBS connection
    obs_connected = (
        _current_state is not None and _current_state.connected_obs if _current_state else False
    )
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

    return web.json_response(
        {
            "status": overall_status,
            "version": __version__,
            "checks": checks,
            "timestamp": int(time.time() * 1000),
        }
    )


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
        return web.json_response(
            {
                "status": "success",
                "message": "Config reloaded successfully",
            }
        )
    except FileNotFoundError as e:
        logger.error(f"Config file not found during reload: {e}")
        return web.json_response(
            {
                "error": f"Config file not found: {e}",
            },
            status=400,
        )
    except Exception as e:
        logger.error(f"Failed to reload config: {e}", exc_info=True)
        return web.json_response(
            {
                "error": f"Failed to reload config: {str(e)}",
            },
            status=400,
        )


async def handle_shutdown(request: web.Request) -> web.Response:
    """Handle POST /shutdown endpoint."""
    global _shutdown_event
    if _shutdown_event is None:
        return web.json_response({"error": "Shutdown not available"}, status=503)

    logger.info("Shutdown requested via API")
    await _task_registry.cancel_all()
    _shutdown_event.set()
    return web.json_response({"status": "shutting_down", "message": "Service shutdown initiated"})


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
    return web.json_response(
        {
            "status": "reset",
            "message": "State and metrics reset to CONNECTING",
            **status,
        }
    )


async def handle_stream_reinit(request: web.Request) -> web.Response:
    """
    Handle POST /stream/reinit — clear stream-info cache and force-refresh from OBS/YouTube.

    Use when the user selected or created a different broadcast in OBS Manage Broadcast.
    Does not change OBS broadcast selection and does not start/stop streaming.
    """
    global _current_state

    if _obs_client is None or not _obs_client.is_connected():
        return web.json_response(
            {
                "error": "OBS not connected",
                "message": "Connect OBS before reinitializing stream info",
            },
            status=503,
        )

    try:
        _obs_client.clear_stream_info_cache()
        title, description = await _obs_client.get_stream_info(force_refresh=True)
        stream_info_full = _obs_client.get_cached_stream_info_full()

        # Propagate extended info into current SwitchState for WS/status consumers
        from irswitch.models import SwitchState

        state_for_status: SwitchState | None
        if _current_state is not None:
            new_state = SwitchState(
                connected_iracing=_current_state.connected_iracing,
                connected_obs=_current_state.connected_obs,
                autoswitch=_current_state.autoswitch,
                override_scene=_current_state.override_scene,
                override_until=_current_state.override_until,
                mode=_current_state.mode,
                target_scene=_current_state.target_scene,
                current_scene=_current_state.current_scene,
                last_switch_ts=_current_state.last_switch_ts,
                reason=_current_state.reason,
                session_type=_current_state.session_type,
                session_name=_current_state.session_name,
                session_num=_current_state.session_num,
                stream_extended_info=stream_info_full,
            )
            set_current_state(new_state)
            state_for_status = new_state
        else:
            state_for_status = None

        event_log = get_event_log()
        await event_log.add_event(
            "stream_info_refreshed",
            "Stream info reinitialized from OBS/YouTube",
            {
                "stream_title": title,
                "has_description": bool(description),
                "broadcast_id": _obs_client.get_cached_broadcast_id(),
            },
        )

        logger.info(
            "Stream info reinitialized via API (title=%s)",
            title or "(none)",
        )

        status: dict = {}
        if state_for_status is not None:
            status = await _get_status_dict(state_for_status)

        return web.json_response(
            {
                "status": "ok",
                "message": "Stream info refreshed",
                "stream_title": title,
                "stream_description": description,
                **status,
            }
        )
    except Exception as e:
        logger.error(f"Failed to reinit stream info: {e}", exc_info=True)
        return web.json_response(
            {
                "error": "Failed to reinitialize stream info",
                "details": str(e),
            },
            status=500,
        )


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
    oauth_manager = _create_oauth_manager_from_config(request)

    if oauth_manager is None:
        return web.json_response(
            {
                "error": "OAuth not configured",
                "message": "Set OAuth credentials in config.ini [oauth] section or GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET environment variables",
            },
            status=503,
        )

    # Generate random state for CSRF protection
    state = secrets.token_urlsafe(32)
    # Store state with timestamp for expiration check (valid for 10 minutes)
    _oauth_states[state] = time.time()

    auth_url = oauth_manager.get_authorization_url(state)

    logger.info("OAuth authorization URL generated")

    return web.json_response(
        {
            "authorization_url": auth_url,
            "state": state,
            "instructions": "Open the authorization URL in a browser, authorize the app, and copy the code from the redirect URL.",
        }
    )


async def handle_oauth_callback(request: web.Request) -> web.Response:
    """
    Handle GET /oauth/callback endpoint - receives OAuth authorization code.

    Exchanges code for tokens and saves them.
    """
    oauth_manager = _create_oauth_manager_from_config(request)

    if oauth_manager is None:
        return web.json_response(
            {
                "error": "OAuth not configured",
                "message": "Set OAuth credentials in config.ini [oauth] section or GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET environment variables",
            },
            status=503,
        )

    # Get code and state from query parameters
    code = request.query.get("code")
    state = request.query.get("state")

    if not code:
        return web.json_response(
            {
                "error": "Missing authorization code",
                "message": "Authorization code not found in callback URL",
            },
            status=400,
        )

    if not state:
        return web.json_response(
            {
                "error": "Missing state parameter",
                "message": "State parameter not found in callback URL",
            },
            status=400,
        )

    # Validate state (CSRF protection)
    if state not in _oauth_states:
        return web.json_response(
            {
                "error": "Invalid state",
                "message": "State parameter is invalid or expired",
            },
            status=400,
        )

    # Check state expiration (10 minutes)
    state_timestamp = _oauth_states.pop(state)
    if time.time() - state_timestamp > 600:
        return web.json_response(
            {
                "error": "State expired",
                "message": "State parameter has expired. Please restart the OAuth flow.",
            },
            status=400,
        )

    try:
        async with aiohttp.ClientSession() as session:
            token = await oauth_manager.exchange_code_for_tokens(code, session)

            logger.info("OAuth authentication successful")

            # Update OAuth manager in OBS client to enable YouTube API access
            if _obs_client is not None:
                _obs_client.set_oauth_manager(oauth_manager)
                logger.info("OAuth manager updated in OBS client")

                # Force refresh stream info to get YouTube stream data (non-blocking)
                try:

                    async def refresh_stream_info():
                        try:
                            await _obs_client.get_stream_info(force_refresh=True)
                            logger.info("Stream info refreshed after OAuth authorization")
                        except Exception as e:
                            logger.warning(
                                f"Failed to refresh stream info after OAuth: {e}", exc_info=True
                            )

                    _task_registry.spawn(
                        "oauth_refresh_stream", refresh_stream_info(), replace=True
                    )
                except Exception as e:
                    logger.warning(f"Failed to schedule stream info refresh: {e}", exc_info=True)

            return web.json_response(
                {
                    "status": "authenticated",
                    "message": "OAuth authentication successful! YouTube API is now authorized.",
                    "expires_in_seconds": token.expires_in_seconds(),
                    "has_refresh_token": token.refresh_token is not None,
                }
            )
    except OAuthError as e:
        logger.error(f"OAuth error: {e}")
        return web.json_response(
            {
                "error": "OAuth error",
                "message": str(e),
            },
            status=500,
        )
    except Exception as e:
        logger.error(f"OAuth callback error: {e}", exc_info=True)
        return web.json_response(
            {
                "error": "Authentication failed",
                "message": str(e),
            },
            status=500,
        )


async def handle_oauth_status(request: web.Request) -> web.Response:
    """
    Handle GET /oauth/status endpoint - check OAuth authentication status.
    """
    oauth_manager = _create_oauth_manager_from_config(request)

    if oauth_manager is None:
        return web.json_response(
            {
                "configured": False,
                "message": "OAuth not configured - set OAuth credentials in config.ini [oauth] section or GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET environment variables",
            }
        )

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

            # If OAuth is authenticated but OBS client doesn't have the manager, update it
            if _obs_client is not None and _obs_client._oauth_manager is None:
                _obs_client.set_oauth_manager(oauth_manager)
                logger.info("OAuth manager updated in OBS client from status check")

                # Try to refresh stream info if OAuth was just authenticated (non-blocking)
                try:

                    async def refresh_stream_info():
                        try:
                            await _obs_client.get_stream_info(force_refresh=True)
                            logger.info("Stream info refreshed after OAuth status check")
                        except Exception as e:
                            logger.debug(f"Failed to refresh stream info: {e}", exc_info=True)

                    _task_registry.spawn(
                        "oauth_refresh_stream", refresh_stream_info(), replace=True
                    )
                except Exception as e:
                    logger.debug(f"Failed to schedule stream info refresh: {e}", exc_info=True)

    return web.json_response(
        {
            "configured": True,
            "authenticated": authenticated,
            "has_refresh_token": has_refresh,
            "token": token_info,
        }
    )


async def handle_oauth_revoke(request: web.Request) -> web.Response:
    """
    Handle POST /oauth/revoke endpoint - revoke OAuth tokens.
    """
    oauth_manager = _create_oauth_manager_from_config(request)

    if oauth_manager is None:
        return web.json_response(
            {
                "error": "OAuth not configured",
                "message": "Set OAuth credentials in config.ini [oauth] section or GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET environment variables",
            },
            status=503,
        )

    try:
        async with aiohttp.ClientSession() as session:
            await oauth_manager.revoke_token(session)

        return web.json_response(
            {
                "status": "revoked",
                "message": "OAuth tokens have been revoked",
            }
        )
    except Exception as e:
        logger.error(f"OAuth revoke error: {e}")
        return web.json_response(
            {
                "error": "Revoke failed",
                "message": str(e),
            },
            status=500,
        )


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
    app.router.add_post("/stream/reinit", handle_stream_reinit)
    app.router.add_get("/gr-status", handle_gr_status)
    app.router.add_get("/vr-status", handle_vr_status)
    app.router.add_get("/test", handle_test_widget)
    app.router.add_get("/ws", handle_websocket)
    app.router.add_get("/oauth/initiate", handle_oauth_initiate)
    app.router.add_get("/oauth/callback", handle_oauth_callback)
    app.router.add_get("/oauth/status", handle_oauth_status)
    app.router.add_post("/oauth/revoke", handle_oauth_revoke)

    # Static asset routes for favicon and app icons
    # Handle both normal execution and PyInstaller bundled EXE
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # Running as PyInstaller EXE - assets are in the extracted temp directory
        assets_path = Path(sys._MEIPASS) / "assets"
    else:
        # Normal execution - __file__ is in src/irswitch/server/api.py, so go up 4 levels to reach project root
        assets_path = Path(__file__).resolve().parents[3] / "assets"

    # Only add static route if assets directory exists
    if assets_path.exists():
        app.router.add_static("/assets/", assets_path)
    else:
        logger.warning(
            f"Assets directory not found at {assets_path}, static assets will not be available"
        )

    async def handle_favicon(request: web.Request) -> web.StreamResponse:
        """Handle GET /favicon.ico endpoint."""
        favicon_path = assets_path / "favicon" / "favicon.ico"
        if favicon_path.exists():
            return web.FileResponse(favicon_path)
        else:
            return web.Response(status=404)

    async def handle_apple_touch_icon(request: web.Request) -> web.StreamResponse:
        """Handle GET /apple-touch-icon.png endpoint."""
        icon_path = assets_path / "favicon" / "apple-touch-icon.png"
        if icon_path.exists():
            return web.FileResponse(icon_path)
        else:
            return web.Response(status=404)

    app.router.add_get("/favicon.ico", handle_favicon)
    app.router.add_get("/apple-touch-icon.png", handle_apple_touch_icon)

    async def _cancel_tracked_tasks(app: web.Application) -> None:
        """Cancel API background tasks on app cleanup."""
        await _task_registry.cancel_all()

    app.on_cleanup.append(_cancel_tracked_tasks)

    return app
