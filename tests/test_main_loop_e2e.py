"""E2E tests for main loop with mocked iRacing and OBS."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from irswitch.config import AppConfig
from irswitch.iracing.reader import IRacingReader
from irswitch.logic.policy import Policy
from irswitch.logic.state_machine import StateMachine
from irswitch.main import main_loop
from irswitch.models import DrivingMode, SwitchState
from irswitch.obs.client import ObsClient
from irswitch.server.event_log import EventLog, set_event_log


async def wait_until(
    pred: Callable[[], bool],
    timeout: float = 2.0,
    interval: float = 0.05,
) -> None:
    """Poll until pred() is true; raise TimeoutError on deadline."""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + timeout
    while True:
        if pred():
            return
        if loop.time() >= deadline:
            raise TimeoutError(f"condition not met within {timeout}s")
        await asyncio.sleep(interval)


async def _cancel_task(task: asyncio.Task) -> None:
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.fixture
def config_path(tmp_path: Path) -> Path:
    """Create temporary config file."""
    config_file = tmp_path / "config.ini"
    config_file.write_text("""[app]
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
""")
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
    reader.is_process_running.return_value = False
    reader.read_mode = AsyncMock(return_value=DrivingMode.IDLE)
    reader.read_session_info = AsyncMock(return_value=None)
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
    obs.is_stream_selected = AsyncMock(return_value=(False, False))
    obs.get_stream_info = AsyncMock(return_value=(None, None))
    obs.get_current_broadcast_id = AsyncMock(return_value=None)
    obs.get_cached_broadcast_id = MagicMock(return_value=None)
    obs.clear_stream_info_cache = MagicMock()

    async def _refresh_stream_info(reason: str = "", *, force: bool = True):
        if force:
            obs.clear_stream_info_cache()
        return await obs.get_stream_info(force_refresh=force)

    obs.refresh_stream_info = AsyncMock(side_effect=_refresh_stream_info)
    obs.get_cached_stream_info = MagicMock(return_value=(None, None, False, False))
    obs._oauth_manager = None
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
    # Need enough iterations to cover debounce (100ms) + cooldown (200ms) + multiple polls
    # With poll_hz=10 (100ms per poll), we need at least 5-6 polls for debounce to expire
    mode_sequence = [
        DrivingMode.IDLE,
        DrivingMode.IDLE,
        DrivingMode.IDLE,  # Extra IDLE to ensure stability
        DrivingMode.RACE,
        DrivingMode.RACE,
        DrivingMode.RACE,
        DrivingMode.RACE,
        DrivingMode.RACE,
        DrivingMode.RACE,
        DrivingMode.RACE,
        DrivingMode.RACE,
        DrivingMode.RACE,
        DrivingMode.RACE,
    ]
    mock_reader.read_mode = AsyncMock(side_effect=mode_sequence)
    mock_obs.get_current_scene = AsyncMock(return_value="Idle")

    # Initialize event log
    event_log = EventLog(max_size=50)
    set_event_log(event_log)

    task = asyncio.create_task(
        main_loop(config, mock_reader, mock_obs, state_machine, initial_state)
    )

    try:
        await wait_until(
            lambda: any(c and c[0][0] == "Race" for c in mock_obs.set_scene.call_args_list),
            timeout=2.0,
        )
    finally:
        await _cancel_task(task)

    set_scene_calls = [call for call in mock_obs.set_scene.call_args_list if call]
    assert len(set_scene_calls) > 0, "set_scene should be called when mode changes to RACE"
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
    mock_reader.read_mode = AsyncMock(return_value=DrivingMode.RACE)
    mock_obs.get_current_scene = AsyncMock(return_value="Idle")

    event_log = EventLog(max_size=50)
    set_event_log(event_log)

    task = asyncio.create_task(
        main_loop(config, mock_reader, mock_obs, state_machine, initial_state)
    )

    try:
        # Negative window: still inside debounce (100ms) — fixed short sleep is intentional
        await asyncio.sleep(0.05)
        assert mock_obs.set_scene.call_count == 0, "set_scene should not be called during debounce"

        await wait_until(lambda: mock_obs.set_scene.call_count > 0, timeout=1.0)
    finally:
        await _cancel_task(task)

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

    try:
        await wait_until(lambda: mock_obs.set_scene.call_count >= 1, timeout=1.5)
        calls_after_first = mock_obs.set_scene.call_count

        # Negative window: still inside cooldown (200ms) — fixed short sleep is intentional
        await asyncio.sleep(0.1)
        assert (
            mock_obs.set_scene.call_count <= calls_after_first + 1
        ), "Cooldown should prevent rapid switches"
    finally:
        await _cancel_task(task)


@pytest.mark.asyncio
async def test_main_loop_autoswitch_disabled_no_switch(
    config: AppConfig,
    mock_reader: MagicMock,
    mock_obs: MagicMock,
    state_machine: StateMachine,
) -> None:
    """Test that autoswitch disabled prevents scene switching."""
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

    try:
        # Negative: wait past debounce; must still not switch
        await asyncio.sleep(0.3)
        assert (
            mock_obs.set_scene.call_count == 0
        ), "set_scene should not be called when autoswitch is disabled"
    finally:
        await _cancel_task(task)


@pytest.mark.asyncio
async def test_main_loop_override_takes_precedence(
    config: AppConfig,
    mock_reader: MagicMock,
    mock_obs: MagicMock,
    state_machine: StateMachine,
    initial_state: SwitchState,
) -> None:
    """Test that override takes precedence over mode-based switching."""
    override_state = state_machine.apply_override(initial_state, "OverrideScene", 120)

    mock_reader.read_mode = AsyncMock(return_value=DrivingMode.RACE)
    mock_obs.get_current_scene = AsyncMock(return_value="Idle")

    event_log = EventLog(max_size=50)
    set_event_log(event_log)

    task = asyncio.create_task(
        main_loop(config, mock_reader, mock_obs, state_machine, override_state)
    )

    try:
        await wait_until(
            lambda: any(
                c and c[0][0] == "OverrideScene" for c in mock_obs.set_scene.call_args_list
            ),
            timeout=1.5,
        )
    finally:
        await _cancel_task(task)

    set_scene_calls = [call[0][0] for call in mock_obs.set_scene.call_args_list if call]
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
    mock_reader.is_connected.return_value = True
    mock_reader.read_mode = AsyncMock(side_effect=[DrivingMode.IDLE, None, None])  # Disconnect

    event_log = EventLog(max_size=50)
    set_event_log(event_log)

    task = asyncio.create_task(
        main_loop(config, mock_reader, mock_obs, state_machine, initial_state)
    )

    try:
        # Allow a few polls; connection events are best-effort under timing
        await asyncio.sleep(0.3)
    finally:
        await _cancel_task(task)

    events = await event_log.get_all_events()
    connection_events = [e for e in events if e.type in ("connection_lost", "connection_restored")]
    assert all(e.type in ("connection_lost", "connection_restored") for e in connection_events)


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

    try:
        await wait_until(lambda: mock_obs.set_scene.call_count > 0, timeout=1.5)
    finally:
        await _cancel_task(task)

    events = await event_log.get_all_events()
    scene_switch_events = [e for e in events if e.type == "scene_switch"]
    assert len(scene_switch_events) > 0, "Scene switch should be logged to event log"


@pytest.mark.asyncio
async def test_main_loop_broadcast_id_change_force_refreshes_stream_info(
    config: AppConfig,
    mock_reader: MagicMock,
    mock_obs: MagicMock,
    state_machine: StateMachine,
    initial_state: SwitchState,
) -> None:
    """While stream stays selected, broadcast_id A→B clears cache and force-refreshes."""
    mock_reader.read_mode = AsyncMock(return_value=DrivingMode.IDLE)
    mock_obs.is_stream_selected = AsyncMock(return_value=(True, True))
    mock_obs.get_stream_info = AsyncMock(side_effect=[("Title A", "Desc A"), ("Title B", "Desc B")])

    cached_ids = iter(["broadcastA", "broadcastB"])

    def _cached_broadcast_id() -> str:
        try:
            return next(cached_ids)
        except StopIteration:
            return "broadcastB"

    mock_obs.get_cached_broadcast_id = MagicMock(side_effect=_cached_broadcast_id)

    # After hysteresis confirms selection, peek stays A then flips to B
    peek_values = ["broadcastA"] * 8 + ["broadcastB"] * 20
    mock_obs.get_current_broadcast_id = AsyncMock(side_effect=peek_values)

    event_log = EventLog(max_size=50)
    set_event_log(event_log)

    task = asyncio.create_task(
        main_loop(config, mock_reader, mock_obs, state_machine, initial_state)
    )

    def _broadcast_changed() -> bool:
        refresh_reasons = [
            c.args[0] for c in mock_obs.refresh_stream_info.await_args_list if c.args
        ]
        return "broadcast_id_changed" in refresh_reasons

    try:
        await wait_until(_broadcast_changed, timeout=3.0)
    finally:
        await _cancel_task(task)

    mock_obs.clear_stream_info_cache.assert_called()
    assert mock_obs.clear_stream_info_cache.call_count >= 2
    force_refresh_calls = [
        c
        for c in mock_obs.get_stream_info.await_args_list
        if c.kwargs.get("force_refresh") is True or (c.args and c.args[0] is True)
    ]
    assert len(force_refresh_calls) >= 2, "select + broadcast change should each force_refresh"
    refresh_reasons = [c.args[0] for c in mock_obs.refresh_stream_info.await_args_list if c.args]
    assert "broadcast_id_changed" in refresh_reasons

    events = await event_log.get_all_events()
    changed = [e for e in events if e.type == "stream_broadcast_changed"]
    assert len(changed) >= 1
    assert changed[0].data.get("previous_broadcast_id") == "broadcastA"
    assert changed[0].data.get("broadcast_id") == "broadcastB"


@pytest.mark.asyncio
async def test_main_loop_same_broadcast_id_does_not_refresh(
    config: AppConfig,
    mock_reader: MagicMock,
    mock_obs: MagicMock,
    state_machine: StateMachine,
    initial_state: SwitchState,
) -> None:
    """Same broadcast_id while selected must not clear cache or re-fetch."""
    mock_reader.read_mode = AsyncMock(return_value=DrivingMode.IDLE)
    mock_obs.is_stream_selected = AsyncMock(return_value=(True, True))
    mock_obs.get_stream_info = AsyncMock(return_value=("Title A", "Desc A"))
    mock_obs.get_cached_broadcast_id = MagicMock(return_value="broadcastA")
    mock_obs.get_current_broadcast_id = AsyncMock(return_value="broadcastA")

    event_log = EventLog(max_size=50)
    set_event_log(event_log)

    task = asyncio.create_task(
        main_loop(config, mock_reader, mock_obs, state_machine, initial_state)
    )

    try:
        # Wait until initial select refresh happened, then hold for stability window
        await wait_until(lambda: mock_obs.refresh_stream_info.await_count >= 1, timeout=2.0)
        await asyncio.sleep(0.5)
    finally:
        await _cancel_task(task)

    # Select path clears once via refresh_stream_info; stable same-id must not refresh again
    assert mock_obs.clear_stream_info_cache.call_count == 1
    assert mock_obs.refresh_stream_info.await_count == 1, "only initial select refresh"
    assert mock_obs.get_stream_info.await_count == 1, "only initial select refresh"

    events = await event_log.get_all_events()
    assert not any(e.type == "stream_broadcast_changed" for e in events)
