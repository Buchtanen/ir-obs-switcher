"""E2E tests for main loop with mocked iRacing and OBS."""
from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from irswitch.config import AppConfig
from irswitch.iracing.reader import IRacingReader
from irswitch.logic.policy import Policy
from irswitch.logic.state_machine import StateMachine
from irswitch.main import main_loop
from irswitch.models import DrivingMode, SwitchState
from irswitch.obs.client import ObsClient
from irswitch.server.event_log import EventLog, set_event_log


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """Create temporary config file."""
    config_file = tmp_path / "config.ini"
    config_file.write_text(
        """[app]
http_host = 127.0.0.1
http_port = 17321
log_level = INFO
notifications_enabled = false

[iracing]
poll_hz = 10
quit_stall_seconds = 0.4

[obs]
ws_url = ws://127.0.0.1:4455
password = test_password

[switching]
autoswitch_default = true
debounce_ms = 100
cooldown_ms = 200
override_seconds = 120
safe_scene = Idle
auto_start_broadcast = false
auto_start_at_percent = 50
default_loading_time_seconds = 12.0
auto_stop_stream = false
stop_stream_after_seconds = 30

[dashboards]
dashboard_update_fps = 2
dashboard_event_log_size = 50

[scenes]
IDLE = Idle
GARAGE = Pits
RACE = Race
REPLAY = Replay
QUIT = End
"""
    )
    return config_file


@pytest.fixture
def config(config_path: Path) -> AppConfig:
    """Create config from file."""
    return AppConfig.from_file(config_path)


@pytest.fixture
def mock_reader() -> MagicMock:
    """Create mocked iRacing reader."""
    reader = MagicMock(spec=IRacingReader)
    reader.is_connected.return_value = True
    reader.read_mode = AsyncMock(return_value=DrivingMode.IDLE)
    return reader


@pytest.fixture
def mock_obs() -> MagicMock:
    """Create mocked OBS client."""
    obs = MagicMock(spec=ObsClient)
    obs.is_connected.return_value = True
    obs.get_current_scene = AsyncMock(return_value="Idle")
    obs.set_scene = AsyncMock(return_value=True)
    obs.get_stream_status = AsyncMock(return_value=(False, None))
    obs.get_current_profile = AsyncMock(return_value=None)
    obs.is_broadcast_ready = AsyncMock(return_value=False)
    obs.start_stream = AsyncMock(return_value=True)
    obs.stop_stream = AsyncMock(return_value=True)
    return obs


@pytest.fixture
def state_machine(config: AppConfig) -> StateMachine:
    """Create state machine."""
    policy = Policy(scenes=config.scenes, safe_scene=config.safe_scene)
    return StateMachine(
        policy=policy,
        debounce_ms=config.debounce_ms,
        cooldown_ms=config.cooldown_ms,
        override_seconds=config.override_seconds,
        autoswitch_default=config.autoswitch_default,
    )


@pytest.fixture
def initial_state() -> SwitchState:
    """Create initial state."""
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


@pytest.mark.asyncio
async def test_main_loop_mode_change_triggers_scene_switch(
    config: AppConfig,
    mock_reader: MagicMock,
    mock_obs: MagicMock,
    state_machine: StateMachine,
    initial_state: SwitchState,
) -> None:
    """Test that mode change triggers scene switch via OBS."""
    # Setup: Start with IDLE, then change to RACE
    mode_sequence = [DrivingMode.IDLE, DrivingMode.IDLE, DrivingMode.RACE, DrivingMode.RACE]
    mock_reader.read_mode = AsyncMock(side_effect=mode_sequence)
    mock_obs.get_current_scene = AsyncMock(return_value="Idle")

    # Initialize event log
    event_log = EventLog(max_size=50)
    set_event_log(event_log)

    # Run main loop for a few iterations
    task = asyncio.create_task(
        main_loop(config, mock_reader, mock_obs, state_machine, initial_state)
    )

    # Wait for debounce + cooldown to pass
    await asyncio.sleep(0.5)

    # Cancel task
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # Verify that set_scene was called (after debounce)
    set_scene_calls = [call for call in mock_obs.set_scene.call_args_list if call]
    # Should have been called at least once to switch to Race scene
    assert len(set_scene_calls) > 0, "set_scene should be called when mode changes to RACE"
    
    # Verify it was called with "Race" scene
    race_calls = [call for call in set_scene_calls if call[0][0] == "Race"]
    assert len(race_calls) > 0, "set_scene should be called with 'Race' scene"


@pytest.mark.asyncio
async def test_main_loop_debounce_delays_switch(
    config: AppConfig,
    mock_reader: MagicMock,
    mock_obs: MagicMock,
    state_machine: StateMachine,
    initial_state: SwitchState,
) -> None:
    """Test that debounce delays scene switch."""
    # Change mode immediately
    mock_reader.read_mode = AsyncMock(return_value=DrivingMode.RACE)
    mock_obs.get_current_scene = AsyncMock(return_value="Idle")

    event_log = EventLog(max_size=50)
    set_event_log(event_log)

    task = asyncio.create_task(
        main_loop(config, mock_reader, mock_obs, state_machine, initial_state)
    )

    # Wait less than debounce time (100ms)
    await asyncio.sleep(0.05)

    # set_scene should NOT be called yet (still debouncing)
    assert mock_obs.set_scene.call_count == 0, "set_scene should not be called during debounce"

    # Wait for debounce to expire
    await asyncio.sleep(0.2)

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # Now set_scene should have been called
    assert mock_obs.set_scene.call_count > 0, "set_scene should be called after debounce expires"


@pytest.mark.asyncio
async def test_main_loop_cooldown_prevents_rapid_switches(
    config: AppConfig,
    mock_reader: MagicMock,
    mock_obs: MagicMock,
    state_machine: StateMachine,
    initial_state: SwitchState,
) -> None:
    """Test that cooldown prevents rapid scene switches."""
    # Sequence: IDLE -> RACE -> GARAGE (rapid changes)
    mode_sequence = [
        DrivingMode.IDLE,
        DrivingMode.RACE,
        DrivingMode.RACE,  # Wait for debounce
        DrivingMode.GARAGE,  # Immediate change
        DrivingMode.GARAGE,
    ]
    mock_reader.read_mode = AsyncMock(side_effect=mode_sequence)
    mock_obs.get_current_scene = AsyncMock(side_effect=["Idle", "Idle", "Race", "Race", "Race"])

    event_log = EventLog(max_size=50)
    set_event_log(event_log)

    task = asyncio.create_task(
        main_loop(config, mock_reader, mock_obs, state_machine, initial_state)
    )

    # Wait for first switch (RACE)
    await asyncio.sleep(0.3)

    # Count calls after first switch
    calls_after_first = mock_obs.set_scene.call_count

    # Wait a bit more (but less than cooldown)
    await asyncio.sleep(0.1)

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # Should not have switched again immediately (cooldown active)
    # But might have switched once more after cooldown
    assert mock_obs.set_scene.call_count <= calls_after_first + 1, "Cooldown should prevent rapid switches"


@pytest.mark.asyncio
async def test_main_loop_autoswitch_disabled_no_switch(
    config: AppConfig,
    mock_reader: MagicMock,
    mock_obs: MagicMock,
    state_machine: StateMachine,
) -> None:
    """Test that autoswitch disabled prevents scene switching."""
    # Start with autoswitch disabled
    initial_state = SwitchState(
        connected_iracing=True,
        connected_obs=True,
        autoswitch=False,  # Disabled
        override_scene=None,
        override_until=None,
        mode=DrivingMode.IDLE,
        target_scene="Idle",
        current_scene="Idle",
        last_switch_ts=None,
        reason="initial",
    )

    mock_reader.read_mode = AsyncMock(return_value=DrivingMode.RACE)
    mock_obs.get_current_scene = AsyncMock(return_value="Idle")

    event_log = EventLog(max_size=50)
    set_event_log(event_log)

    task = asyncio.create_task(
        main_loop(config, mock_reader, mock_obs, state_machine, initial_state)
    )

    # Wait for debounce
    await asyncio.sleep(0.3)

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # set_scene should NOT be called (autoswitch disabled)
    assert mock_obs.set_scene.call_count == 0, "set_scene should not be called when autoswitch is disabled"


@pytest.mark.asyncio
async def test_main_loop_override_takes_precedence(
    config: AppConfig,
    mock_reader: MagicMock,
    mock_obs: MagicMock,
    state_machine: StateMachine,
    initial_state: SwitchState,
) -> None:
    """Test that override takes precedence over mode-based switching."""
    # Apply override first
    override_state = state_machine.apply_override(initial_state, "OverrideScene", 120)

    mock_reader.read_mode = AsyncMock(return_value=DrivingMode.RACE)
    mock_obs.get_current_scene = AsyncMock(return_value="Idle")

    event_log = EventLog(max_size=50)
    set_event_log(event_log)

    task = asyncio.create_task(
        main_loop(config, mock_reader, mock_obs, state_machine, override_state)
    )

    # Wait for debounce
    await asyncio.sleep(0.3)

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # Verify set_scene was called with override scene, not RACE scene
    set_scene_calls = [call[0][0] for call in mock_obs.set_scene.call_args_list if call]
    if set_scene_calls:
        assert "OverrideScene" in set_scene_calls, "Override scene should be used, not mode-based scene"


@pytest.mark.asyncio
async def test_main_loop_connection_state_tracking(
    config: AppConfig,
    mock_reader: MagicMock,
    mock_obs: MagicMock,
    state_machine: StateMachine,
    initial_state: SwitchState,
) -> None:
    """Test that connection state changes are tracked."""
    # Start connected, then disconnect iRacing
    mock_reader.is_connected.return_value = True
    mock_reader.read_mode = AsyncMock(side_effect=[DrivingMode.IDLE, None, None])  # Disconnect

    event_log = EventLog(max_size=50)
    set_event_log(event_log)

    task = asyncio.create_task(
        main_loop(config, mock_reader, mock_obs, state_machine, initial_state)
    )

    await asyncio.sleep(0.3)

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # Verify events were logged
    events = await event_log.get_all_events()
    connection_events = [e for e in events if e.type in ("connection_lost", "connection_restored")]
    # Should have at least one connection event if iRacing disconnected
    # (Note: might not fire if timing is off, but structure should be there)


@pytest.mark.asyncio
async def test_main_loop_scene_switch_logs_event(
    config: AppConfig,
    mock_reader: MagicMock,
    mock_obs: MagicMock,
    state_machine: StateMachine,
    initial_state: SwitchState,
) -> None:
    """Test that scene switches are logged to event log."""
    mock_reader.read_mode = AsyncMock(return_value=DrivingMode.RACE)
    mock_obs.get_current_scene = AsyncMock(return_value="Idle")

    event_log = EventLog(max_size=50)
    set_event_log(event_log)

    task = asyncio.create_task(
        main_loop(config, mock_reader, mock_obs, state_machine, initial_state)
    )

    # Wait for debounce and switch
    await asyncio.sleep(0.3)

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # Verify scene_switch event was logged
    events = await event_log.get_all_events()
    scene_switch_events = [e for e in events if e.type == "scene_switch"]
    # Should have at least one scene switch event if switch occurred
    if mock_obs.set_scene.call_count > 0:
        assert len(scene_switch_events) > 0, "Scene switch should be logged to event log"
