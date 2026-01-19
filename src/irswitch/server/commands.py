"""Command handlers for API."""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from irswitch.logic.state_machine import StateMachine
    from irswitch.models import SwitchState


def handle_override(
    state_machine: StateMachine, current_state: SwitchState, scene: str, seconds: int
) -> SwitchState:
    """
    Handle override command.

    Args:
        state_machine: State machine instance
        current_state: Current switch state
        scene: Scene name to override to
        seconds: Override duration in seconds

    Returns:
        New switch state with override applied
    """
    return state_machine.apply_override(current_state, scene, seconds)


def handle_toggle_autoswitch(
    state_machine: StateMachine, current_state: SwitchState
) -> SwitchState:
    """
    Handle toggle autoswitch command.

    Args:
        state_machine: State machine instance
        current_state: Current switch state

    Returns:
        New switch state with toggled autoswitch
    """
    return state_machine.toggle_autoswitch(current_state)


def handle_get_status(current_state: SwitchState) -> dict:
    """
    Get current status as dictionary.

    Args:
        current_state: Current switch state

    Returns:
        Dictionary representation of state
    """
    return {
        "connected_iracing": current_state.connected_iracing,
        "connected_obs": current_state.connected_obs,
        "autoswitch": current_state.autoswitch,
        "override_scene": current_state.override_scene,
        "override_until": current_state.override_until,
        "mode": current_state.mode.value,
        "target_scene": current_state.target_scene,
        "current_scene": current_state.current_scene,
        "last_switch_ts": current_state.last_switch_ts,
        "reason": current_state.reason,
    }
