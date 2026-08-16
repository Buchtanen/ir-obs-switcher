"""State machine for switching decisions."""

from __future__ import annotations

from collections.abc import Mapping

from irswitch.logic.policy import Policy
from irswitch.models import DrivingMode, SwitchState
from irswitch.util.clock import now_ms

# After LOADING/CONNECTING, wait this long before trusting a first LOBBY/GARAGE.
GRACE_PERIOD_MS = 3000


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
        self._pending_mode: DrivingMode | None = None
        self._pending_since: int | None = None
        self._waiting_for_idle = False  # Grace period: wait until IDLE after reconnect
        self._seen_non_idle = False  # Track if we saw non-IDLE mode during grace period

    def apply_runtime_config(
        self,
        *,
        scenes: Mapping[DrivingMode, str] | None = None,
        safe_scene: str | None = None,
        debounce_ms: int | None = None,
        cooldown_ms: int | None = None,
        override_seconds: int | None = None,
        autoswitch_default: bool | None = None,
    ) -> None:
        """
        Apply hot-reloadable switching settings without resetting debounce state.

        Used by POST /config/reload so main_loop / Policy stay in sync with disk config.
        """
        if scenes is not None or safe_scene is not None:
            new_scenes = scenes if scenes is not None else self._policy.scenes
            new_safe = safe_scene if safe_scene is not None else self._policy.safe_scene
            self._policy.apply_scenes(new_scenes, new_safe)
        if debounce_ms is not None:
            self._debounce_ms = debounce_ms
        if cooldown_ms is not None:
            self._cooldown_ms = cooldown_ms
        if override_seconds is not None:
            self._override_seconds = override_seconds
        if autoswitch_default is not None:
            self._autoswitch_default = autoswitch_default

    def _grace_target(
        self,
        mode: DrivingMode,
        elapsed_ms: int | None,
        current_target: str,
    ) -> tuple[str, str]:
        """
        Resolve target scene while post-load grace period is active.

        GARAGE after load is ignored until it stays stable for GRACE_PERIOD_MS
        (real garage) or LOBBY appears (false stall flicker).
        """
        if mode == DrivingMode.GARAGE and elapsed_ms is not None and elapsed_ms >= GRACE_PERIOD_MS:
            self._waiting_for_idle = False
            self._seen_non_idle = False
            return self._policy.target_for_mode(mode), "grace_period_timeout:GARAGE"

        if mode != DrivingMode.LOBBY:
            self._seen_non_idle = True
            return current_target, f"grace_period_ignore:{mode.value}"

        if self._seen_non_idle:
            self._waiting_for_idle = False
            self._seen_non_idle = False
            return self._policy.target_for_mode(mode), "grace_period_ended:LOBBY"

        if elapsed_ms is not None and elapsed_ms >= GRACE_PERIOD_MS:
            self._waiting_for_idle = False
            self._seen_non_idle = False
            return self._policy.target_for_mode(mode), "grace_period_timeout:LOBBY"

        return current_target, "grace_period_first_lobby"

    def tick(
        self,
        current_state: SwitchState,
        iracing_mode: DrivingMode | None,
        obs_current_scene: str | None,
        is_loading: bool = False,  # True when iRacing is in loading screen (SessionTime empty)
    ) -> SwitchState:
        """
        Process one tick of the state machine.

        Args:
            current_state: Current switch state
            iracing_mode: Current iRacing mode (None if disconnected or loading)
            obs_current_scene: Current OBS scene (None if disconnected)
            is_loading: True when iRacing is in loading screen (SessionTime empty)

        Returns:
            New switch state
        """
        now = now_ms()

        # Update connection states
        iracing_quit = iracing_mode == DrivingMode.QUIT
        iracing_restart = iracing_mode == DrivingMode.RESTART
        # iRacing is connected if mode is not None, not QUIT, not RESTART, and not loading
        connected_iracing = (
            iracing_mode is not None and not iracing_quit and not iracing_restart and not is_loading
        )
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

        # Determine mode and target scene based on new state flow
        # Priority: CONNECTING > LOADING > RESTART > QUIT > LOBBY/GARAGE/RACE/REPLAY

        # Check if both OBS and iRacing are connected
        both_connected = connected_obs and connected_iracing

        if override_scene is not None:
            # Override active - always allow override
            target_scene = override_scene
            mode = current_state.mode  # Keep current mode during override
            reason = f"override_active:{override_scene}"
        elif iracing_restart:
            # RESTART mode - block switching, keep current scene
            mode = DrivingMode.RESTART
            target_scene = current_state.target_scene  # Keep current scene, don't switch
            reason = "restart_mode:no_switch"
            # Reset debounce when entering RESTART
            self._pending_mode = None
            self._pending_since = None
        elif iracing_quit:
            # QUIT mode - switch to QUIT scene
            mode = DrivingMode.QUIT
            target_scene = self._policy.target_for_mode(mode)
            reason = "iracing_quit"
        elif is_loading and both_connected:
            # LOADING - iRacing is in loading screen (only if both are connected)
            # This takes priority over CONNECTING when iRacing is connected but loading
            mode = DrivingMode.LOADING
            target_scene = current_state.target_scene  # Keep current scene, don't switch
            reason = "loading:no_switch"
            # Reset debounce when entering LOADING
            self._pending_mode = None
            self._pending_since = None
        elif not both_connected:
            # CONNECTING - waiting for both OBS and iRacing
            mode = DrivingMode.CONNECTING
            target_scene = self._policy.safe_scene  # Use safe_scene
            reason = "connecting:waiting_for_both"
            # Reset debounce when entering CONNECTING
            self._pending_mode = None
            self._pending_since = None
        elif not current_state.autoswitch:
            # Autoswitch disabled
            # Map IDLE to LOBBY for consistency
            if iracing_mode == DrivingMode.IDLE:
                mode = DrivingMode.LOBBY
            else:
                mode = iracing_mode or current_state.mode
            target_scene = current_state.target_scene  # Keep current target
            reason = "autoswitch_disabled"
        else:
            # Normal operation - map iRacing modes to our states
            # Convert IDLE to LOBBY
            if iracing_mode == DrivingMode.IDLE:
                mode = DrivingMode.LOBBY
            else:
                mode = iracing_mode or DrivingMode.LOBBY

            # Debounce logic: wait for stable state
            was_disconnected = (
                not current_state.connected_iracing or current_state.mode == DrivingMode.CONNECTING
            )
            was_loading = current_state.mode == DrivingMode.LOADING

            # Grace period applies to LOBBY and GARAGE after load/reconnect.
            # IsInGarage is true in the session lobby (car physics in stall), so
            # the first GARAGE after LOADING/CONNECTING is untrusted.
            # RACE/REPLAY switch immediately (after debounce).
            is_game_mode = mode in (
                DrivingMode.RACE,
                DrivingMode.REPLAY,
            )

            if mode != self._pending_mode:
                # Mode changed, reset debounce timer
                self._pending_mode = mode
                self._pending_since = now
                if (was_disconnected or was_loading) and not is_game_mode:
                    # Start grace period - wait for LOBBY AFTER seeing non-LOBBY (inspection)
                    # GARAGE is included: a post-load stall flicker must not switch yet
                    self._waiting_for_idle = True
                    self._seen_non_idle = False
                elif is_game_mode:
                    # RACE/REPLAY - clear grace period, switch immediately after debounce
                    self._waiting_for_idle = False
                    self._seen_non_idle = False

                if self._waiting_for_idle:
                    elapsed = (
                        (now - self._pending_since) if self._pending_since is not None else None
                    )
                    target_scene, reason = self._grace_target(
                        mode, elapsed, current_state.target_scene
                    )
                else:
                    # No grace period or game mode - debounce normally
                    target_scene = current_state.target_scene  # Keep current until debounce expires
                    reason = f"debouncing:{mode.value}"
            elif self._pending_since is not None:
                # Mode is stable, check if debounce expired
                elapsed = now - self._pending_since
                # Check grace period - wait for LOBBY after seeing non-LOBBY
                if self._waiting_for_idle and not is_game_mode:
                    target_scene, reason = self._grace_target(
                        mode, elapsed, current_state.target_scene
                    )
                elif elapsed < self._debounce_ms:
                    # Still debouncing
                    target_scene = current_state.target_scene
                    reason = (
                        f"debouncing:{mode.value} ({(self._debounce_ms - elapsed):.0f}ms remaining)"
                    )
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
        # CONNECTING, LOADING, and RESTART modes should NOT switch scenes
        should_switch = False
        last_switch_ts = current_state.last_switch_ts
        switch_reason = reason

        # Modes that block scene switching
        no_switch_modes = {
            DrivingMode.CONNECTING,
            DrivingMode.LOADING,
            DrivingMode.RESTART,
        }

        if target_scene != current_scene:
            # Target differs from current
            if mode in no_switch_modes:
                # CONNECTING, LOADING, RESTART - don't switch
                should_switch = False
                switch_reason = f"{mode.value}:no_switch"
            elif not current_state.autoswitch:
                # Autoswitch disabled, don't switch
                should_switch = False
            elif override_scene is not None:
                # Override active, switch immediately (even in CONNECTING/LOADING/RESTART)
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
                    switch_reason = (
                        f"cooldown ({(self._cooldown_ms - elapsed_since_switch):.0f}ms remaining)"
                    )

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
            current_scene=(current_scene if should_switch else current_state.current_scene),
            last_switch_ts=last_switch_ts,
            reason=switch_reason,
            session_type=current_state.session_type,
            session_name=current_state.session_name,
            session_num=current_state.session_num,
            stream_extended_info=current_state.stream_extended_info,
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
            session_type=current_state.session_type,
            session_name=current_state.session_name,
            session_num=current_state.session_num,
            stream_extended_info=current_state.stream_extended_info,
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
            session_type=current_state.session_type,
            session_name=current_state.session_name,
            session_num=current_state.session_num,
            stream_extended_info=current_state.stream_extended_info,
        )
