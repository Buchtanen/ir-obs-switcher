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

    from irswitch.logic.stream_chapters import StreamChaptersSettings
    from irswitch.obs.client import ObsClient
    from irswitch.server.api import get_stream_chapter_tracker

    app = create_app()
    set_state_machine(state_machine)
    set_current_state(initial_state)
    get_stream_chapter_tracker().apply_settings(StreamChaptersSettings())
    get_stream_chapter_tracker().clear()

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
            assert "applied_live" in data
            assert "needs_restart" in data
            assert isinstance(data["applied_live"], list)
            assert isinstance(data["needs_restart"], list)
            assert APP_CONFIG in app
            from irswitch.logic.policy import Policy
            from irswitch.logic.state_machine import StateMachine
            from irswitch.models import DrivingMode
            from irswitch.server.api import get_app_config, set_app_config, set_state_machine

            # Shared holder must mirror reloaded app config
            shared = get_app_config()
            assert shared is not None
            assert shared.poll_hz == 10
            assert shared.debounce_ms == 500

            # Seed baseline so the next reload can produce a meaningful diff
            set_app_config(shared)

            # With SM wired, reload must push switching knobs into Policy/SM
            policy = Policy(
                scenes={DrivingMode.IDLE: "IdleOld"},
                safe_scene="SafeOld",
            )
            sm = StateMachine(
                policy=policy,
                debounce_ms=1,
                cooldown_ms=1,
                override_seconds=1,
                autoswitch_default=False,
            )
            set_state_machine(sm)

            config_file.write_text("""[app]
http_host = 127.0.0.1
http_port = 9090
log_level = INFO
notifications_enabled = true
log_file =
log_max_bytes = 10485760
log_backup_count = 5

[iracing]
poll_hz = 20
quit_stall_seconds = 0.4

[obs]
ws_url = ws://127.0.0.1:4455
password = test_password
required_profile =

[switching]
autoswitch_default = true
debounce_ms = 777
cooldown_ms = 888
override_seconds = 99
safe_scene = SafeNew
auto_start_broadcast = false
auto_start_at_percent = 50
default_loading_time_seconds = 12.0
auto_stop_stream = false
stop_stream_after_seconds = 30

[hotkeys]
restart_hotkey =

[scenes]
IDLE = IdleNew
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
            resp2 = await client.post("/config/reload")
            assert resp2.status == 200
            data2 = await resp2.json()
            assert "switching.debounce_ms" in data2["applied_live"]
            assert "iracing.poll_hz" in data2["applied_live"]
            assert "scenes.IDLE" in data2["applied_live"]
            assert "app.http_port" in data2["needs_restart"]
            shared2 = get_app_config()
            assert shared2 is not None
            assert shared2.poll_hz == 20
            assert shared2.debounce_ms == 777
            assert sm._debounce_ms == 777
            assert sm._cooldown_ms == 888
            assert sm._override_seconds == 99
            assert sm._policy.safe_scene == "SafeNew"
            assert sm._policy.scenes[DrivingMode.IDLE] == "IdleNew"


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
async def test_logging_level_get_and_set(app: web.Application) -> None:
    """Test GET/POST /logging/level runtime toggle (non-persistent)."""
    import logging

    from aiohttp.test_utils import TestClient, TestServer

    from irswitch.util.logging import set_runtime_log_level

    set_runtime_log_level("INFO")

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.get("/logging/level")
            assert resp.status == 200
            data = await resp.json()
            assert data["level"] == "INFO"
            assert data["persistent"] is False

            resp_dbg = await client.post("/logging/level", json={"level": "DEBUG"})
            assert resp_dbg.status == 200
            dbg = await resp_dbg.json()
            assert dbg["status"] == "success"
            assert dbg["level"] == "DEBUG"
            assert dbg["persistent"] is False
            assert logging.getLogger().getEffectiveLevel() == logging.DEBUG

            resp_info = await client.post("/logging/level", json={"level": "info"})
            assert resp_info.status == 200
            info = await resp_info.json()
            assert info["level"] == "INFO"
            assert logging.getLogger().getEffectiveLevel() == logging.INFO

            resp_bad = await client.post("/logging/level", json={"level": "WARNING"})
            assert resp_bad.status == 400
            bad = await resp_bad.json()
            assert "error" in bad

            resp_missing = await client.post("/logging/level", json={})
            assert resp_missing.status == 400


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


@pytest.mark.asyncio
async def test_restart_success(app: web.Application, tmp_path) -> None:
    """POST /restart spawns first, then shuts down (fail-closed contract)."""
    import asyncio
    from unittest.mock import patch

    from aiohttp.test_utils import TestClient, TestServer

    from irswitch.server.api import APP_CONFIG_PATH, set_shutdown_event

    shutdown_event = asyncio.Event()
    set_shutdown_event(shutdown_event)
    config_path = tmp_path / "config.ini"
    config_path.write_text("[app]\nhttp_port = 17321\n", encoding="utf-8")
    app[APP_CONFIG_PATH] = config_path

    with patch("irswitch.util.process_restart.spawn_detached_restart") as spawn:
        async with TestServer(app) as server:
            async with TestClient(server) as client:
                resp = await client.post("/restart")
                assert resp.status == 200

                data = await resp.json()
                assert data["status"] == "restarting"
                assert "message" in data

                spawn.assert_called_once()
                assert spawn.call_args.kwargs["config_path"] == config_path
                assert shutdown_event.is_set()


@pytest.mark.asyncio
async def test_restart_spawn_fail_does_not_shutdown(app: web.Application, tmp_path) -> None:
    """POST /restart must not shut down when spawn fails (fail-closed)."""
    import asyncio
    from unittest.mock import patch

    from aiohttp.test_utils import TestClient, TestServer

    from irswitch.server.api import APP_CONFIG_PATH, set_shutdown_event

    shutdown_event = asyncio.Event()
    set_shutdown_event(shutdown_event)
    config_path = tmp_path / "config.ini"
    config_path.write_text("[app]\nhttp_port = 17321\n", encoding="utf-8")
    app[APP_CONFIG_PATH] = config_path

    with patch(
        "irswitch.util.process_restart.spawn_detached_restart",
        side_effect=OSError("spawn denied"),
    ) as spawn:
        async with TestServer(app) as server:
            async with TestClient(server) as client:
                resp = await client.post("/restart")
                assert resp.status == 500

                data = await resp.json()
                assert "error" in data
                assert "spawn" in data["error"].lower()

                spawn.assert_called_once()
                assert not shutdown_event.is_set()


@pytest.mark.asyncio
async def test_restart_not_available(app: web.Application) -> None:
    """POST /restart returns 503 when shutdown event is not wired."""
    from aiohttp.test_utils import TestClient, TestServer

    from irswitch.server.api import set_shutdown_event

    set_shutdown_event(None)

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post("/restart")
            assert resp.status == 503

            data = await resp.json()
            assert "error" in data
            assert "not available" in data["error"].lower()


@pytest.mark.asyncio
async def test_stream_reinit_obs_not_connected(app: web.Application) -> None:
    """POST /stream/reinit returns 503 when OBS is unavailable."""
    from aiohttp.test_utils import TestClient, TestServer

    from irswitch.server.api import set_obs_client

    set_obs_client(None)

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post("/stream/reinit")
            assert resp.status == 503
            data = await resp.json()
            assert "OBS not connected" in data["error"]


@pytest.mark.asyncio
async def test_stream_reinit_success(app: web.Application, initial_state: SwitchState) -> None:
    """POST /stream/reinit clears cache and force-refreshes stream info."""
    from unittest.mock import AsyncMock, MagicMock

    from aiohttp.test_utils import TestClient, TestServer

    from irswitch.models import SwitchState
    from irswitch.server.api import set_current_state, set_obs_client
    from irswitch.server.event_log import EventLog, set_event_log

    set_event_log(EventLog(max_size=10))

    obs = MagicMock()
    obs.is_connected.return_value = True
    obs.clear_stream_info_cache = MagicMock()
    obs.get_stream_info = AsyncMock(return_value=("Race Night", "desc"))
    obs.refresh_stream_info = AsyncMock(return_value=("Race Night", "desc"))
    obs.get_cached_stream_info_full.return_value = {
        "title": "Race Night",
        "description": "desc",
    }
    obs.get_cached_broadcast_id.return_value = "broadcast123"
    obs.get_stream_status = AsyncMock(return_value=(False, None))
    obs.get_current_profile = AsyncMock(return_value="Racing")
    obs.is_stream_selected = AsyncMock(return_value=(True, True))
    obs.get_cached_stream_info.return_value = ("Race Night", "desc", False, False)
    set_obs_client(obs)

    connected = SwitchState(
        connected_iracing=initial_state.connected_iracing,
        connected_obs=True,
        autoswitch=initial_state.autoswitch,
        override_scene=None,
        override_until=None,
        mode=initial_state.mode,
        target_scene=initial_state.target_scene,
        current_scene=initial_state.current_scene,
        last_switch_ts=None,
        reason=initial_state.reason,
        session_type=None,
        session_name=None,
        session_num=None,
        stream_extended_info=None,
    )
    set_current_state(connected)

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post("/stream/reinit")
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "ok"
            assert data["stream_title"] == "Race Night"
            obs.refresh_stream_info.assert_awaited_once_with("api_reinit", force=True)


def _app_config_with_chapters(tmp_path, *, enabled: bool = True):
    from pathlib import Path

    from irswitch.config import AppConfig

    path = Path(tmp_path) / "config.ini"
    path.write_text(f"""[app]
http_host = 127.0.0.1
http_port = 17321
log_level = INFO

[iracing]
poll_hz = 5

[obs]
ws_url = ws://127.0.0.1:4455
password = test

[switching]
autoswitch_default = true
debounce_ms = 100
cooldown_ms = 100
override_seconds = 120
safe_scene = Idle

[scenes]
IDLE = Idle
GARAGE = Pits
RACE = Race
REPLAY = Replay

[stream_chapters]
enabled = {"true" if enabled else "false"}
start_title = Stream start
trigger_session_types = Practice,Qualify,Race
""")
    return AppConfig.from_file(path)


@pytest.mark.asyncio
async def test_status_omits_stream_chapters_when_disabled(app: web.Application, tmp_path) -> None:
    """Disabled feature must not expose stream_chapters on /status."""
    from aiohttp.test_utils import TestClient, TestServer

    from irswitch.server.api import set_app_config

    set_app_config(_app_config_with_chapters(tmp_path, enabled=False))

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.get("/status")
            assert resp.status == 200
            data = await resp.json()
            assert "stream_chapters" not in data


@pytest.mark.asyncio
async def test_ws_stream_chapters_snapshot_and_event(
    app: web.Application, initial_state: SwitchState, tmp_path
) -> None:
    """WS /ws sends status, snapshot, then stream_chapter on session change."""
    import asyncio
    from dataclasses import replace
    from unittest.mock import AsyncMock, MagicMock

    from aiohttp.test_utils import TestClient, TestServer

    from irswitch.obs.client import ObsClient
    from irswitch.server.api import reset_state, set_app_config, set_current_state, set_obs_client

    set_app_config(_app_config_with_chapters(tmp_path, enabled=True))

    mock_obs = AsyncMock(spec=ObsClient)
    mock_obs.get_stream_status = AsyncMock(return_value=(True, 60_000))
    mock_obs.get_cached_stream_info = MagicMock(return_value=(None, None, False, False))
    mock_obs.get_cached_stream_info_full = MagicMock(return_value=None)
    mock_obs.is_stream_selected = AsyncMock(return_value=(True, False))
    mock_obs.get_current_profile = AsyncMock(return_value=None)
    set_obs_client(mock_obs)

    racing = replace(initial_state, session_type="Practice", connected_obs=True)
    set_current_state(racing)
    await asyncio.sleep(0.05)

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            async with client.ws_connect("/ws") as ws:
                status_msg = await ws.receive_json()
                assert "mode" in status_msg
                assert "type" not in status_msg
                assert status_msg.get("streaming") is True
                assert isinstance(status_msg.get("stream_chapters"), list)
                assert status_msg["stream_chapters"][0]["title"] == "Stream start"
                assert status_msg["stream_chapters"][0]["offset_seconds"] == 0

                snap = await ws.receive_json()
                assert snap["type"] == "stream_chapters_snapshot"
                assert snap["chapters"][0]["title"] == "Stream start"

                set_current_state(replace(racing, session_type="Race"))
                # Drain status broadcast + chapter event
                chapter_event = None
                for _ in range(5):
                    msg = await asyncio.wait_for(ws.receive_json(), timeout=2.0)
                    if msg.get("type") == "stream_chapter":
                        chapter_event = msg
                        break
                assert chapter_event is not None
                assert chapter_event["chapter"]["session_type"] == "Race"
                assert chapter_event["chapter"]["title"] == "Race"
                assert isinstance(chapter_event["chapter"]["offset_seconds"], int)

    reset_state()


@pytest.mark.asyncio
async def test_ws_no_chapter_messages_when_disabled(
    app: web.Application, initial_state: SwitchState, tmp_path
) -> None:
    """With feature off, WS only sends flat status."""
    import asyncio
    from dataclasses import replace

    from aiohttp.test_utils import TestClient, TestServer

    from irswitch.server.api import set_app_config, set_current_state

    set_app_config(_app_config_with_chapters(tmp_path, enabled=False))
    set_current_state(replace(initial_state, session_type="Race"))
    await asyncio.sleep(0.05)

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            async with client.ws_connect("/ws") as ws:
                status_msg = await ws.receive_json()
                assert "mode" in status_msg
                assert "stream_chapters" not in status_msg
                # No second message should arrive promptly
                try:
                    extra = await asyncio.wait_for(ws.receive(timeout=0.2), timeout=0.3)
                    if extra.type.name == "TEXT":
                        data = extra.json()
                        assert data.get("type") not in (
                            "stream_chapter",
                            "stream_chapters_snapshot",
                        )
                except TimeoutError:
                    pass
