"""Tests for API server."""
from __future__ import annotations

import json

import pytest
from aiohttp import web
from aiohttp.test_utils import make_mocked_request

from irswitch.logic.policy import Policy
from irswitch.logic.state_machine import StateMachine
from irswitch.models import DrivingMode, SwitchState
from irswitch.server.api import create_app, set_current_state, set_state_machine, set_obs_client, reset_state


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
    mock_obs = AsyncMock(spec=ObsClient)
    mock_obs.get_stream_status = AsyncMock(return_value=(False, None))
    set_obs_client(mock_obs)
    
    return app


@pytest.mark.asyncio
async def test_get_status(app: web.Application, initial_state: SwitchState) -> None:
    """Test GET /status endpoint."""
    from aiohttp.test_utils import TestServer, TestClient

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
    from aiohttp.test_utils import TestServer, TestClient

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
    from aiohttp.test_utils import TestServer, TestClient

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
    from aiohttp.test_utils import TestServer, TestClient

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post("/override", json={"seconds": 60})
            assert resp.status == 400

            data = await resp.json()
            assert "error" in data


@pytest.mark.asyncio
async def test_override_invalid_seconds(app: web.Application) -> None:
    """Test POST /override with invalid seconds."""
    from aiohttp.test_utils import TestServer, TestClient

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
    from aiohttp.test_utils import TestServer, TestClient

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
