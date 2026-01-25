"""Tests for state machine."""

from __future__ import annotations

import pytest

from irswitch.logic.policy import Policy
from irswitch.logic.state_machine import StateMachine
from irswitch.models import DrivingMode, SwitchState


@pytest.fixture
def policy() -> Policy:
    """Create policy for testing."""
    return Policy(
        scenes={
            DrivingMode.IDLE: "Idle",
            DrivingMode.GARAGE: "Pits",
            DrivingMode.RACE: "Race",
            DrivingMode.REPLAY: "Replay",
        },
        safe_scene="Safe",
    )


@pytest.fixture
def state_machine(policy: Policy) -> StateMachine:
    """Create state machine for testing."""
    return StateMachine(
        policy=policy,
        debounce_ms=900,
        cooldown_ms=1000,
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


def test_tick_mode_change_triggers_debounce(
    state_machine: StateMachine, initial_state: SwitchState
) -> None:
    """Test that mode change triggers debounce."""
    from unittest.mock import patch

    time_ms = 1000000

    def mock_now_ms() -> int:
        return time_ms

    with patch("irswitch.logic.state_machine.now_ms", side_effect=mock_now_ms):
        # First tick: mode changes to RACE
        new_state = state_machine.tick(initial_state, DrivingMode.RACE, "Idle")

        assert new_state.mode == DrivingMode.RACE
        assert new_state.target_scene == "Idle"  # Still old scene (debouncing)
        assert "debouncing" in new_state.reason
        assert new_state.current_scene == "Idle"  # No switch yet


def test_tick_debounce_expires_and_switches(
    state_machine: StateMachine, initial_state: SwitchState
) -> None:
    """Test that debounce expires and scene switches."""
    from unittest.mock import patch

    time_ms = 1000000

    def mock_now_ms() -> int:
        return time_ms

    with patch("irswitch.logic.state_machine.now_ms", side_effect=mock_now_ms):
        # First tick: mode changes
        state1 = state_machine.tick(initial_state, DrivingMode.RACE, "Idle")
        assert "debouncing" in state1.reason

        # Advance time past debounce (1000ms later)
        time_ms += 1000
        state2 = state_machine.tick(state1, DrivingMode.RACE, "Idle")

        assert state2.target_scene == "Race"
        assert "debounced" in state2.reason or "mode:RACE" in state2.reason


def test_tick_cooldown_prevents_rapid_switches(
    state_machine: StateMachine, initial_state: SwitchState
) -> None:
    """Test that cooldown prevents rapid switches."""
    from unittest.mock import patch

    # Mock time to control monotonic time
    time_ms = 1000000  # Start at 1 second in ms

    def mock_now_ms() -> int:
        return time_ms

    with patch("irswitch.logic.state_machine.now_ms", side_effect=mock_now_ms):
        # Switch to RACE - wait for debounce
        state1 = state_machine.tick(initial_state, DrivingMode.RACE, "Idle")
        assert "debouncing" in state1.reason

        # Advance time past debounce (900ms)
        time_ms += 1000
        state2 = state_machine.tick(state1, DrivingMode.RACE, "Idle")
        assert state2.current_scene == "Race" or state2.target_scene == "Race"
        assert state2.last_switch_ts is not None

        # Update current_scene to match target after switch
        if state2.target_scene == "Race" and state2.current_scene != "Race":
            state2 = SwitchState(
                connected_iracing=state2.connected_iracing,
                connected_obs=state2.connected_obs,
                autoswitch=state2.autoswitch,
                override_scene=state2.override_scene,
                override_until=state2.override_until,
                mode=state2.mode,
                target_scene=state2.target_scene,
                current_scene=state2.target_scene,  # Simulate switch happened
                last_switch_ts=state2.last_switch_ts,
                reason=state2.reason,
            )

        # Immediately try to switch to GARAGE (500ms later, less than cooldown 1000ms)
        time_ms += 500
        state3 = state_machine.tick(state2, DrivingMode.GARAGE, "Race")
        # Wait for debounce
        time_ms += 1000
        state3 = state_machine.tick(state3, DrivingMode.GARAGE, "Race")

        assert state3.target_scene == "Pits"
        assert "cooldown" in state3.reason or state3.current_scene == "Race"

        # After cooldown expires (1500ms total from switch = 2000ms from start)
        time_ms = state2.last_switch_ts + 1500
        state4 = state_machine.tick(state3, DrivingMode.GARAGE, "Race")
        # Wait for debounce
        time_ms += 1000
        state4 = state_machine.tick(state4, DrivingMode.GARAGE, "Race")

        assert state4.target_scene == "Pits"


def test_tick_override_active(state_machine: StateMachine, initial_state: SwitchState) -> None:
    """Test that override takes precedence."""
    from unittest.mock import patch

    time_ms = 1000000

    def mock_now_ms() -> int:
        return time_ms

    with patch("irswitch.logic.state_machine.now_ms", side_effect=mock_now_ms):
        # Apply override
        override_state = state_machine.apply_override(initial_state, "OverrideScene", 120)
        assert override_state.override_scene == "OverrideScene"
        assert override_state.target_scene == "OverrideScene"

        # Tick with different mode - should still use override
        new_state = state_machine.tick(override_state, DrivingMode.RACE, "Idle")
        assert new_state.target_scene == "OverrideScene"
        assert "override_active" in new_state.reason


def test_tick_override_expires(state_machine: StateMachine, initial_state: SwitchState) -> None:
    """Test that override expires after time limit."""
    from unittest.mock import patch

    # Mock time
    time_ms = 1000000
    override_until = time_ms + 2000  # 2 seconds from now

    def mock_now_ms() -> int:
        return time_ms

    # Apply override
    override_state = state_machine.apply_override(initial_state, "OverrideScene", 2)
    # Manually set override_until to known value
    override_state = SwitchState(
        connected_iracing=override_state.connected_iracing,
        connected_obs=override_state.connected_obs,
        autoswitch=override_state.autoswitch,
        override_scene=override_state.override_scene,
        override_until=override_until,
        mode=override_state.mode,
        target_scene=override_state.target_scene,
        current_scene=override_state.current_scene,
        last_switch_ts=override_state.last_switch_ts,
        reason=override_state.reason,
    )

    # Advance time past override expiration (3 seconds later = 1000ms past expiration)
    time_ms = override_until + 1000

    with patch("irswitch.logic.state_machine.now_ms", side_effect=mock_now_ms):
        # First tick: override expires, mode changes to RACE (will debounce)
        new_state = state_machine.tick(override_state, DrivingMode.RACE, "Idle")
        assert new_state.override_scene is None
        assert new_state.override_until is None
        # After override expires, mode change triggers debounce
        assert "debouncing" in new_state.reason or new_state.target_scene == "Race"

        # Wait for debounce to expire
        time_ms += 1000
        new_state = state_machine.tick(new_state, DrivingMode.RACE, "Idle")
        assert new_state.target_scene == "Race"  # Back to normal mode


def test_tick_autoswitch_disabled(state_machine: StateMachine, initial_state: SwitchState) -> None:
    """Test that autoswitch disabled prevents switching."""
    from unittest.mock import patch

    time_ms = 1000000

    def mock_now_ms() -> int:
        return time_ms

    with patch("irswitch.logic.state_machine.now_ms", side_effect=mock_now_ms):
        # Disable autoswitch
        disabled_state = state_machine.toggle_autoswitch(initial_state)
        assert disabled_state.autoswitch is False

        # Try to switch mode
        new_state = state_machine.tick(disabled_state, DrivingMode.RACE, "Idle")
        assert new_state.target_scene == "Idle"  # Keeps current target
        assert "autoswitch_disabled" in new_state.reason


def test_tick_iracing_disconnected(state_machine: StateMachine, initial_state: SwitchState) -> None:
    """Test behavior when iRacing disconnects."""
    from unittest.mock import patch

    time_ms = 1000000

    def mock_now_ms() -> int:
        return time_ms

    with patch("irswitch.logic.state_machine.now_ms", side_effect=mock_now_ms):
        new_state = state_machine.tick(initial_state, None, "Idle")

        assert new_state.connected_iracing is False
        assert new_state.target_scene == "Safe"  # Uses safe scene when disconnected
        assert new_state.mode == DrivingMode.CONNECTING


def test_apply_override(state_machine: StateMachine, initial_state: SwitchState) -> None:
    """Test applying override."""
    override_state = state_machine.apply_override(initial_state, "TestScene", 60)

    assert override_state.override_scene == "TestScene"
    assert override_state.target_scene == "TestScene"
    assert override_state.override_until is not None
    assert "override_applied" in override_state.reason


def test_toggle_autoswitch(state_machine: StateMachine, initial_state: SwitchState) -> None:
    """Test toggling autoswitch."""
    # Toggle off
    off_state = state_machine.toggle_autoswitch(initial_state)
    assert off_state.autoswitch is False
    assert "autoswitch_toggled:False" in off_state.reason

    # Toggle on
    on_state = state_machine.toggle_autoswitch(off_state)
    assert on_state.autoswitch is True
    assert "autoswitch_toggled:True" in on_state.reason


def test_tick_same_scene_no_switch(state_machine: StateMachine, initial_state: SwitchState) -> None:
    """Test that no switch occurs when target equals current."""
    from unittest.mock import patch

    time_ms = 1000000

    def mock_now_ms() -> int:
        return time_ms

    with patch("irswitch.logic.state_machine.now_ms", side_effect=mock_now_ms):
        # Already on Idle, mode is IDLE
        new_state = state_machine.tick(initial_state, DrivingMode.IDLE, "Idle")

        assert new_state.target_scene == "Idle"
        assert new_state.current_scene == "Idle"
        assert new_state.last_switch_ts == initial_state.last_switch_ts  # No switch occurred
