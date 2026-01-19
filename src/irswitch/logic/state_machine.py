"""State machine for switching decisions."""
from __future__ import annotations

from typing import Optional

from irswitch.logic.policy import Policy
from irswitch.models import DrivingMode, SwitchState
from irswitch.util.clock import now_ms


class StateMachine:
    """
    State machine for scene switching with debounce, cooldown, and override logic.

    Debounce: waits for stable state before switching (delays switch by X ms)
    Cooldown: minimum interval between switches
    Override: temporary scene switch with time limit
    """

    def __init__(
        self,
        policy: Policy,
        debounce_ms: int,
        cooldown_ms: int,
        override_seconds: int,
        autoswitch_default: bool,
    ) -> None:
        """
        Initialize state machine.

        Args:
            policy: Scene mapping policy
            debounce_ms: Delay before switching (debounce)
            cooldown_ms: Minimum interval between switches
            override_seconds: Default override duration in seconds
            autoswitch_default: Default autoswitch state
        """
        self._policy = policy
        self._debounce_ms = debounce_ms
        self._cooldown_ms = cooldown_ms
        self._override_seconds = override_seconds
        self._autoswitch_default = autoswitch_default

        # Internal state for debounce
        self._pending_mode: Optional[DrivingMode] = None
        self._pending_since: Optional[float] = None
        self._waiting_for_idle = False  # Grace period: wait until IDLE after reconnect
        self._seen_non_idle = False  # Track if we saw non-IDLE mode during grace period

    def tick(
        self,
        current_state: SwitchState,
        iracing_mode: Optional[DrivingMode],
        obs_current_scene: Optional[str],
    ) -> SwitchState:
        """
        Process one tick of the state machine.

        Args:
            current_state: Current switch state
            iracing_mode: Current iRacing mode (None if disconnected)
            obs_current_scene: Current OBS scene (None if disconnected)

        Returns:
            New switch state
        """
        now = now_ms()

        # Update connection states
        iracing_quit = iracing_mode == DrivingMode.QUIT
        iracing_restart = iracing_mode == DrivingMode.RESTART
        connected_iracing = iracing_mode is not None and not iracing_quit and not iracing_restart
        connected_obs = obs_current_scene is not None
        current_scene = obs_current_scene or current_state.current_scene

        # Check override expiration
        override_scene = current_state.override_scene
        override_until = current_state.override_until
        override_expired = override_until is not None and now >= override_until
        if override_expired:
            override_scene = None
            override_until = None
            # Reset debounce when override expires to allow immediate mode detection
            self._pending_mode = None
            self._pending_since = None

        # Determine target scene
        if override_scene is not None:
            # Override active
            target_scene = override_scene
            mode = current_state.mode  # Keep current mode during override
            reason = f"override_active:{override_scene}"
            # Don't debounce when override is active
        elif not current_state.autoswitch:
            # Autoswitch disabled
            target_scene = current_state.target_scene  # Keep current target
            mode = iracing_mode or current_state.mode
            reason = "autoswitch_disabled"
            # Don't debounce when autoswitch is disabled
        elif not connected_iracing:
            # iRacing disconnected, quit, or restart
            if iracing_restart:
                mode = DrivingMode.RESTART
                # Switch to RESTART scene (or safe_scene if not configured)
                target_scene = self._policy.target_for_mode(mode)
                reason = "iracing_restart"
            elif iracing_quit:
                mode = DrivingMode.QUIT
                # Switch to QUIT scene (or safe_scene if not configured)
                target_scene = self._policy.target_for_mode(mode)
                reason = "iracing_quit"
            else:
                mode = current_state.mode
                target_scene = current_state.target_scene
                reason = "iracing_disconnected"
            # Don't debounce when iRacing is disconnected
        else:
            # Normal operation - determine mode and target
            mode = iracing_mode
            # Skip debounce when transitioning from disconnected/loading to connected
            # This prevents "sticky" scene after loading screen
            was_disconnected = not current_state.connected_iracing
            
            # Debounce logic: wait for stable state
            if mode != self._pending_mode:
                # Mode changed, reset debounce timer
                self._pending_mode = mode
                self._pending_since = now
                if was_disconnected:
                    # Start grace period - wait for IDLE AFTER seeing non-IDLE (inspection)
                    self._waiting_for_idle = True
                    self._seen_non_idle = False
                
                if self._waiting_for_idle:
                    # Grace period active - wait for IDLE after seeing non-IDLE
                    if mode != DrivingMode.IDLE:
                        self._seen_non_idle = True
                        target_scene = current_state.target_scene  # Keep current scene
                        reason = f"grace_period_ignore:{mode.value}"
                    elif self._seen_non_idle:
                        # IDLE after non-IDLE (inspection done) - end grace period
                        self._waiting_for_idle = False
                        self._seen_non_idle = False
                        target_scene = self._policy.target_for_mode(mode)
                        reason = f"grace_period_ended:IDLE"
                    else:
                        # First IDLE before inspection - keep waiting
                        target_scene = self._policy.target_for_mode(mode)  # Apply IDLE scene
                        reason = f"grace_period_first_idle"
                else:
                    target_scene = current_state.target_scene  # Keep current until debounce expires
                    reason = f"debouncing:{mode.value}"
            elif self._pending_since is not None:
                # Mode is stable, check if debounce expired
                elapsed = now - self._pending_since
                # Check grace period - wait for IDLE after seeing non-IDLE
                if self._waiting_for_idle:
                    if mode != DrivingMode.IDLE:
                        self._seen_non_idle = True
                        target_scene = current_state.target_scene  # Keep current scene
                        reason = f"grace_period_ignore:{mode.value}"
                    elif self._seen_non_idle:
                        # IDLE after non-IDLE - end grace period
                        self._waiting_for_idle = False
                        self._seen_non_idle = False
                        target_scene = self._policy.target_for_mode(mode)
                        reason = f"grace_period_ended:IDLE"
                    else:
                        # First IDLE before inspection - keep waiting but apply IDLE scene
                        target_scene = self._policy.target_for_mode(mode)
                        reason = f"grace_period_first_idle"
                elif elapsed < self._debounce_ms:
                    # Still debouncing
                    target_scene = current_state.target_scene
                    reason = f"debouncing:{mode.value} ({(self._debounce_ms - elapsed):.0f}ms remaining)"
                else:
                    # Debounce expired, use new target
                    target_scene = self._policy.target_for_mode(mode)
                    reason = f"mode:{mode.value} (debounced)"
                    self._pending_since = None
            else:
                # No pending mode, use current mode directly
                target_scene = self._policy.target_for_mode(mode)
                reason = f"mode:{mode.value}"

        # Check if switch is needed
        should_switch = False
        last_switch_ts = current_state.last_switch_ts
        switch_reason = reason

        if target_scene != current_scene:
            # Target differs from current
            if not current_state.autoswitch:
                # Autoswitch disabled, don't switch
                should_switch = False
            elif override_scene is not None:
                # Override active, switch immediately
                should_switch = True
                switch_reason = f"override_active:{override_scene}"
            elif last_switch_ts is None:
                # Never switched before, allow switch
                should_switch = True
            else:
                # Check cooldown
                elapsed_since_switch = now - last_switch_ts
                if elapsed_since_switch >= self._cooldown_ms:
                    # Cooldown expired, allow switch
                    should_switch = True
                else:
                    # Still in cooldown
                    should_switch = False
                    switch_reason = f"cooldown ({(self._cooldown_ms - elapsed_since_switch):.0f}ms remaining)"

        # Update last_switch_ts if we're switching
        if should_switch:
            last_switch_ts = now
        else:
            last_switch_ts = current_state.last_switch_ts

        return SwitchState(
            connected_iracing=connected_iracing,
            connected_obs=connected_obs,
            autoswitch=current_state.autoswitch,
            override_scene=override_scene,
            override_until=override_until,
            mode=mode,
            target_scene=target_scene,
            current_scene=current_scene if should_switch else current_state.current_scene,
            last_switch_ts=last_switch_ts,
            reason=switch_reason,
        )

    def apply_override(self, current_state: SwitchState, scene: str, seconds: int) -> SwitchState:
        """
        Apply scene override with time limit.

        Args:
            current_state: Current switch state
            scene: Scene name to override to
            seconds: Override duration in seconds

        Returns:
            New switch state with override applied
        """
        now = now_ms()
        override_until = now + (seconds * 1000)

        return SwitchState(
            connected_iracing=current_state.connected_iracing,
            connected_obs=current_state.connected_obs,
            autoswitch=current_state.autoswitch,
            override_scene=scene,
            override_until=override_until,
            mode=current_state.mode,
            target_scene=scene,
            current_scene=current_state.current_scene,
            last_switch_ts=current_state.last_switch_ts,
            reason=f"override_applied:{scene}",
        )

    def toggle_autoswitch(self, current_state: SwitchState) -> SwitchState:
        """
        Toggle autoswitch on/off.

        Args:
            current_state: Current switch state

        Returns:
            New switch state with toggled autoswitch
        """
        return SwitchState(
            connected_iracing=current_state.connected_iracing,
            connected_obs=current_state.connected_obs,
            autoswitch=not current_state.autoswitch,
            override_scene=current_state.override_scene,
            override_until=current_state.override_until,
            mode=current_state.mode,
            target_scene=current_state.target_scene,
            current_scene=current_state.current_scene,
            last_switch_ts=current_state.last_switch_ts,
            reason=f"autoswitch_toggled:{not current_state.autoswitch}",
        )
