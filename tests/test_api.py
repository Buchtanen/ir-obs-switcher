"""Tests for API server."""

from __future__ import annotations

import time

import pytest
from aiohttp import web

from irswitch.logic.policy import Policy
from irswitch.logic.state_machine import StateMachine
from irswitch.models import DrivingMode, SwitchState
from irswitch.server.api import (
    APP_CONFIG,
    APP_CONFIG_PATH,
    create_app,
    reset_state,
    set_current_state,
    set_obs_client,
    set_state_machine,
)


@pytest.fixture
def policy() -> Policy:
    """Create policy for testing."""
    return Policy(
        scenes={
            DrivingMode.IDLE: "Idle",
            DrivingMode.RACE: "Race",
        },
        safe_scene="Safe",
    )


@pytest.fixture
def state_machine(policy: Policy) -> StateMachine:
    """Create state machine for testing."""
    return StateMachine(
        policy=policy,
        debounce_ms=100,
        cooldown_ms=200,
        override_seconds=120,
        autoswitch_default=True,
    )


@pytest.fixture
def initial_state() -> SwitchState:
    """Create initial state for testing."""
    return SwitchState(
        connected_iracing=True,
        connected_obs=True,
        autoswitch=True,
        override_scene=None,
        override_until=None,
        mode=DrivingMode.IDLE,
        target_scene="Idle",
        current_scene="Idle",
        last_switch_ts=None,
        reason="initial",
    )


@pytest.fixture
def app(state_machine: StateMachine, initial_state: SwitchState) -> web.Application:
    """Create test application."""
    from unittest.mock import AsyncMock

    from irswitch.obs.client import ObsClient

    app = create_app()
    set_state_machine(state_machine)
    set_current_state(initial_state)

    # Mock OBS client for stream status
    from unittest.mock import MagicMock

    mock_obs = AsyncMock(spec=ObsClient)
    mock_obs.get_stream_status = AsyncMock(return_value=(False, None))
    mock_obs.get_cached_stream_info = MagicMock(return_value=(None, None, False, False))
    mock_obs.get_cached_stream_info_full = MagicMock(return_value=None)
    mock_obs.is_stream_selected = AsyncMock(return_value=(False, False))
    mock_obs.get_current_profile = AsyncMock(return_value=None)
    set_obs_client(mock_obs)

    return app


@pytest.mark.asyncio
async def test_get_status(app: web.Application, initial_state: SwitchState) -> None:
    """Test GET /status endpoint."""
    from aiohttp.test_utils import TestClient, TestServer

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.get("/status")
            assert resp.status == 200

            data = await resp.json()
            assert data["mode"] == "IDLE"
            assert data["current_scene"] == "Idle"
            assert data["autoswitch"] is True
            assert "streaming" in data
            assert "stream_duration_ms" in data


@pytest.mark.asyncio
async def test_get_status_not_initialized() -> None:
    """Test GET /status when service not initialized."""
    from aiohttp.test_utils import TestClient, TestServer

    reset_state()  # Clear any state from previous tests
    app = create_app()
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.get("/status")
            assert resp.status == 503

            data = await resp.json()
            assert "error" in data


@pytest.mark.asyncio
async def test_override(app: web.Application) -> None:
    """Test POST /override endpoint."""
    from aiohttp.test_utils import TestClient, TestServer

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post(
                "/override",
                json={"scene": "TestScene", "seconds": 60},
            )
            assert resp.status == 200

            data = await resp.json()
            assert data["override_scene"] == "TestScene"
            assert data["target_scene"] == "TestScene"
            assert data["override_until"] is not None


@pytest.mark.asyncio
async def test_override_missing_scene(app: web.Application) -> None:
    """Test POST /override with missing scene."""
    from aiohttp.test_utils import TestClient, TestServer

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post("/override", json={"seconds": 60})
            assert resp.status == 400

            data = await resp.json()
            assert "error" in data


@pytest.mark.asyncio
async def test_override_invalid_seconds(app: web.Application) -> None:
    """Test POST /override with invalid seconds."""
    from aiohttp.test_utils import TestClient, TestServer

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post(
                "/override",
                json={"scene": "TestScene", "seconds": -1},
            )
            assert resp.status == 400

            data = await resp.json()
            assert "error" in data


@pytest.mark.asyncio
async def test_toggle_autoswitch(app: web.Application) -> None:
    """Test POST /autoswitch/toggle endpoint."""
    from aiohttp.test_utils import TestClient, TestServer

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            # Toggle off
            resp = await client.post("/autoswitch/toggle")
            assert resp.status == 200

            data = await resp.json()
            assert data["autoswitch"] is False

            # Toggle on
            resp = await client.post("/autoswitch/toggle")
            assert resp.status == 200

            data = await resp.json()
            assert data["autoswitch"] is True


@pytest.mark.asyncio
async def test_health_healthy(app: web.Application) -> None:
    """Test GET /health endpoint when both services are connected."""
    from aiohttp.test_utils import TestClient, TestServer

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.get("/health")
            assert resp.status == 200

            data = await resp.json()
            assert data["status"] == "healthy"
            assert "checks" in data
            assert "timestamp" in data

            checks = data["checks"]
            assert "iracing" in checks
            assert "obs" in checks
            assert "api" in checks

            assert checks["iracing"]["status"] == "connected"
            assert checks["iracing"]["available"] is True
            assert checks["obs"]["status"] == "connected"
            assert checks["obs"]["available"] is True
            assert checks["api"]["status"] == "running"
            assert checks["api"]["available"] is True


@pytest.mark.asyncio
async def test_health_degraded() -> None:
    """Test GET /health endpoint when one service is disconnected."""
    from aiohttp.test_utils import TestClient, TestServer

    from irswitch.models import DrivingMode, SwitchState
    from irswitch.server.api import create_app, reset_state, set_current_state

    reset_state()
    app = create_app()

    # Set state with one disconnected
    state = SwitchState(
        connected_iracing=True,
        connected_obs=False,  # OBS disconnected
        autoswitch=True,
        override_scene=None,
        override_until=None,
        mode=DrivingMode.IDLE,
        target_scene="Idle",
        current_scene="Idle",
        last_switch_ts=None,
        reason="test",
    )
    set_current_state(state)

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.get("/health")
            assert resp.status == 200

            data = await resp.json()
            assert data["status"] == "degraded"
            assert data["checks"]["iracing"]["available"] is True
            assert data["checks"]["obs"]["available"] is False


@pytest.mark.asyncio
async def test_health_unhealthy() -> None:
    """Test GET /health endpoint when both services are disconnected."""
    from aiohttp.test_utils import TestClient, TestServer

    from irswitch.models import DrivingMode, SwitchState
    from irswitch.server.api import create_app, reset_state, set_current_state

    reset_state()
    app = create_app()

    # Set state with both disconnected
    state = SwitchState(
        connected_iracing=False,
        connected_obs=False,
        autoswitch=True,
        override_scene=None,
        override_until=None,
        mode=DrivingMode.IDLE,
        target_scene="Idle",
        current_scene="Idle",
        last_switch_ts=None,
        reason="test",
    )
    set_current_state(state)

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.get("/health")
            assert resp.status == 200

            data = await resp.json()
            assert data["status"] == "unhealthy"
            assert data["checks"]["iracing"]["available"] is False
            assert data["checks"]["obs"]["available"] is False


@pytest.mark.asyncio
async def test_metrics(app: web.Application, initial_state: SwitchState) -> None:
    """Test GET /metrics endpoint."""
    from aiohttp.test_utils import TestClient, TestServer

    from irswitch.server.metrics import get_metrics, reset_metrics

    # Reset metrics for clean test
    reset_metrics()
    metrics = get_metrics()

    # Record some test data
    metrics.record_scene_switch(50.0)
    metrics.record_scene_switch(75.0)
    metrics.record_error("test_error")
    metrics.set_iracing_connected(True)
    metrics.set_obs_connected(True)

    # Wait a bit so connection durations are > 0
    time.sleep(0.05)  # 50ms should be enough for durations to be > 0

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.get("/metrics")
            assert resp.status == 200

            data = await resp.json()
            assert "scene_switches_total" in data
            assert data["scene_switches_total"] == 2
            assert "uptime_seconds" in data
            assert data["uptime_seconds"] >= 0  # Can be 0 if test runs very fast
            assert "errors_total" in data
            assert data["errors_total"]["test_error"] == 1
            assert "scene_switch_latency_avg_ms" in data
            assert data["scene_switch_latency_avg_ms"] == 62.5  # (50 + 75) / 2
            assert "iracing_connected_duration_seconds" in data
            assert "obs_connected_duration_seconds" in data
            assert "current_state" in data


@pytest.mark.asyncio
async def test_config_reload_success(app: web.Application, tmp_path) -> None:
    """Test POST /config/reload endpoint with valid config."""

    from aiohttp.test_utils import TestClient, TestServer

    # Create a temporary config file
    config_file = tmp_path / "test_config.ini"
    config_file.write_text("""[app]
http_host = 127.0.0.1
http_port = 8080
log_level = INFO
notifications_enabled = true
log_file =
log_max_bytes = 10485760
log_backup_count = 5

[iracing]
poll_hz = 10
quit_stall_seconds = 0.4

[obs]
ws_url = ws://127.0.0.1:4455
password = test_password
required_profile =

[switching]
autoswitch_default = true
debounce_ms = 500
cooldown_ms = 1000
override_seconds = 120
safe_scene = Safe
auto_start_broadcast = false
auto_start_at_percent = 50
default_loading_time_seconds = 12.0
auto_stop_stream = false
stop_stream_after_seconds = 30

[hotkeys]
restart_hotkey =

[scenes]
IDLE = Idle
GARAGE = Pits
RACE = Race
REPLAY = Replay
QUIT = End
RESTART = Restart

[dashboards]
dashboard_update_fps = 2
dashboard_gr_background_image =
dashboard_gr_logo_obs =
dashboard_gr_logo_iracing =
dashboard_gr_logo_app =
dashboard_vr_icons_path =
dashboard_event_log_size = 50
""")

    app[APP_CONFIG_PATH] = str(config_file)

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post("/config/reload")
            assert resp.status == 200

            data = await resp.json()
            assert data["status"] == "success"
            assert "message" in data
            assert APP_CONFIG in app


@pytest.mark.asyncio
async def test_config_reload_file_not_found(app: web.Application) -> None:
    """Test POST /config/reload endpoint with non-existent config file."""
    from aiohttp.test_utils import TestClient, TestServer

    app[APP_CONFIG_PATH] = "/nonexistent/config.ini"

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post("/config/reload")
            assert resp.status == 400

            data = await resp.json()
            assert "error" in data
            assert "not found" in data["error"].lower()


@pytest.mark.asyncio
async def test_config_reload_no_config_path(app: web.Application) -> None:
    """Test POST /config/reload endpoint when config_path is not set."""
    from aiohttp.test_utils import TestClient, TestServer

    # Remove config_path if it exists
    if APP_CONFIG_PATH in app:
        del app[APP_CONFIG_PATH]

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post("/config/reload")
            assert resp.status == 500

            data = await resp.json()
            assert "error" in data
            assert "not available" in data["error"].lower()


@pytest.mark.asyncio
async def test_shutdown_success(app: web.Application) -> None:
    """Test POST /shutdown endpoint."""
    import asyncio

    from aiohttp.test_utils import TestClient, TestServer

    from irswitch.server.api import set_shutdown_event

    # Set up shutdown event
    shutdown_event = asyncio.Event()
    set_shutdown_event(shutdown_event)

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post("/shutdown")
            assert resp.status == 200

            data = await resp.json()
            assert data["status"] == "shutting_down"
            assert "message" in data

            # Verify event was set
            assert shutdown_event.is_set()


@pytest.mark.asyncio
async def test_shutdown_not_available(app: web.Application) -> None:
    """Test POST /shutdown endpoint when shutdown is not available."""
    from aiohttp.test_utils import TestClient, TestServer

    from irswitch.server.api import set_shutdown_event

    # Clear shutdown event
    set_shutdown_event(None)

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post("/shutdown")
            assert resp.status == 503

            data = await resp.json()
            assert "error" in data
            assert "not available" in data["error"].lower()
