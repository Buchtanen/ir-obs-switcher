"""Entry point for the core service."""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys

from aiohttp import web

from irswitch.config import AppConfig
from irswitch.iracing.reader import IRacingReader
from irswitch.iracing.extractors import extract_session_type, extract_session_num
from irswitch.logic.policy import Policy
from irswitch.logic.state_machine import StateMachine
from irswitch.models import DrivingMode, SwitchState
from irswitch.obs.client import ObsClient
from irswitch.server.api import create_app, set_current_state, get_current_state, set_state_machine, set_obs_client, get_restart_mode, set_restart_mode
from irswitch.server.event_log import get_event_log, set_event_log, EventLog
from irswitch.server.metrics import get_metrics
from irswitch.util.clock import now_ms
from irswitch.util.loading_tracker import LoadingTimeTracker
from irswitch.util.logging import (
    log_connection_lost,
    log_connection_restored,
    log_scene_switch,
    setup_logging,
)
from irswitch.util.notifications import (
    notify_connection_lost,
    notify_connection_restored,
    set_notifications_enabled,
)
from irswitch.util.hotkeys import start_listener, stop_listener, is_hotkey_pressed, was_hotkey_pressed_recently

logger = logging.getLogger(__name__)


def build_parser() -> argparse.ArgumentParser:
    """Build command line argument parser."""
    parser = argparse.ArgumentParser(description="iRacing OBS scene switcher")
    parser.add_argument("--config", required=True, help="Path to config INI")
    return parser


async def main_loop(
    config: AppConfig,
    reader: IRacingReader,
    obs_client: ObsClient,
    state_machine: StateMachine,
    initial_state: SwitchState,
) -> None:
    """
    Main event loop coordinating all components.

    Args:
        config: Application configuration
        reader: iRacing reader
        obs_client: OBS client
        state_machine: State machine
        initial_state: Initial switch state
    """
    current_state = initial_state
    set_current_state(current_state)

    # Calculate polling interval
    poll_interval = 1.0 / config.poll_hz
    
    # Track last notification time to avoid spam
    last_obs_notification_ts: float | None = None
    obs_notification_cooldown_ms = 30000  # 30 seconds
    
    # Track time in active gameplay mode for debounced sticky mode reset
    active_mode_start_ts: float | None = None
    active_mode_reset_delay_s = 3.0  # Wait 3 seconds in active mode before resetting sticky mode
    
    # Track previous mode to detect loading→active transitions
    prev_iracing_mode: DrivingMode | None = None

    # Loading tracker
    loading_tracker = LoadingTimeTracker(
        default_loading_time_seconds=config.default_loading_time_seconds
    )

    # Auto-start broadcast tracking
    loading_start_ts: float | None = None
    auto_start_scheduled_ts: float | None = None
    auto_start_triggered = False

    # Auto-stop stream tracking
    quit_detected_ts: float | None = None
    stream_stopped_after_quit = False
    quit_reset_active = False  # Flag to prevent QUIT mode after reset

    logger.info("Starting main loop")

    while True:
        try:
            # Poll iRacing
            iracing_mode = await reader.read_mode()

            # Loading screen detection and tracking
            is_loading = iracing_mode is None
            was_loading = prev_iracing_mode is None

            if is_loading and not was_loading:
                # Loading started (transition from mode to None)
                loading_tracker.start_loading()
                loading_start_ts = now_ms()
                auto_start_scheduled_ts = None
                auto_start_triggered = False
                logger.debug("Loading screen detected, starting tracker")
                
                # Try to read session info during loading
                session_info = await reader.read_session_info()
                session_type = None
                session_num = None
                session_name = None
                if session_info:
                    session_type = extract_session_type(session_info)
                    session_num = extract_session_num(session_info)
                    session_name = session_info.get("SessionName")
                    logger.info(f"Session info during loading: type={session_type}, num={session_num}, name={session_name}")
                
                await event_log.add_event(
                    "loading_started",
                    f"iRacing loading screen started" + (f" - {session_type}" if session_type else ""),
                    {
                        "previous_mode": prev_iracing_mode.value if prev_iracing_mode else None,
                        "session_type": session_type,
                        "session_num": session_num,
                        "session_name": str(session_name) if session_name else None,
                    }
                )

            elif not is_loading and was_loading:
                # Loading ended (transition from None to mode)
                duration = loading_tracker.end_loading()
                loading_start_ts = None
                auto_start_scheduled_ts = None
                auto_start_triggered = False
                if duration is not None:
                    logger.info(f"Loading screen ended, duration: {duration:.2f}s")
                    await event_log.add_event(
                        "loading_ended",
                        f"iRacing loading screen ended, duration: {duration:.2f}s",
                        {"duration_seconds": duration, "new_mode": iracing_mode.value if iracing_mode else None}
                    )
            
            # Auto-start broadcast logic (during loading)
            if is_loading and config.auto_start_broadcast and loading_start_ts is not None:
                if auto_start_scheduled_ts is None:
                    # Calculate when to start broadcast
                    avg_loading = loading_tracker.get_average_loading_time()
                    use_default = len(loading_tracker.history) == 0
                    if use_default:
                        logger.info(
                            f"No loading history available, using default: "
                            f"{config.default_loading_time_seconds}s"
                        )
                    
                    start_delay_ms = int(avg_loading * config.auto_start_at_percent / 100.0 * 1000)
                    auto_start_scheduled_ts = loading_start_ts + start_delay_ms
                    logger.debug(
                        f"Auto-start broadcast scheduled at {start_delay_ms}ms "
                        f"({config.auto_start_at_percent}% of {avg_loading:.2f}s average)"
                    )
                
                current_ts = now_ms()
                if not auto_start_triggered and current_ts >= auto_start_scheduled_ts:
                    # Time to check and start broadcast
                    is_ready = await obs_client.is_broadcast_ready()
                    is_streaming, _ = await obs_client.get_stream_status()
                    
                    if is_ready and not is_streaming:
                        success = await obs_client.start_stream()
                        if success:
                            logger.info("Auto-started broadcast during loading")
                            await event_log.add_event(
                                "stream_started",
                                "Stream started automatically during loading (broadcast ready)",
                                {"reason": "auto_start_loading", "broadcast_ready": True, "was_streaming": False}
                            )
                        else:
                            logger.warning("Failed to auto-start broadcast during loading")
                            await event_log.add_event(
                                "stream_start_failed",
                                "Failed to auto-start stream during loading",
                                {"reason": "auto_start_loading", "broadcast_ready": True, "error": "start_failed"}
                            )
                    else:
                        if not is_ready:
                            logger.debug("Broadcast not ready for auto-start")
                            await event_log.add_event(
                                "stream_start_skipped",
                                "Stream start skipped: broadcast not ready",
                                {"reason": "auto_start_loading", "broadcast_ready": False, "was_streaming": is_streaming}
                            )
                        if is_streaming:
                            logger.debug("Stream already running, skipping auto-start")
                            await event_log.add_event(
                                "stream_start_skipped",
                                "Stream start skipped: already running",
                                {"reason": "auto_start_loading", "broadcast_ready": is_ready, "was_streaming": True}
                            )
                    
                    auto_start_triggered = True  # Only try once per loading
            
            # QUIT mode handling: reset to CONNECTING after 15 seconds
            # If quit_reset_active is True, ignore QUIT mode and treat as disconnected
            if quit_reset_active:
                # After reset, ignore QUIT mode until iRacing disconnects or mode changes
                if iracing_mode != DrivingMode.QUIT:
                    # Mode changed away from QUIT, clear reset flag
                    quit_reset_active = False
                    quit_detected_ts = None
                    stream_stopped_after_quit = False
                else:
                    # Still in QUIT mode, but we've reset - treat as disconnected
                    iracing_mode = None
            
            if iracing_mode == DrivingMode.QUIT and not quit_reset_active:
                if quit_detected_ts is None:
                    quit_detected_ts = now_ms()
                    stream_stopped_after_quit = False
                    logger.debug("QUIT detected, starting reset timer")
                
                elapsed_ms = now_ms() - quit_detected_ts
                quit_reset_seconds = 15  # Always reset QUIT after 15 seconds
                
                # Auto-stop stream logic (if enabled)
                if config.auto_stop_stream and not stream_stopped_after_quit:
                    if elapsed_ms >= config.stop_stream_after_seconds * 1000:
                        is_streaming, _ = await obs_client.get_stream_status()
                        if is_streaming:
                            success = await obs_client.stop_stream()
                            if success:
                                logger.info(f"Auto-stopped stream {config.stop_stream_after_seconds}s after QUIT")
                                await event_log.add_event(
                                    "stream_stopped",
                                    f"Stream stopped automatically {config.stop_stream_after_seconds}s after QUIT (was running)",
                                    {"reason": "auto_stop_quit", "was_streaming": True, "delay_seconds": config.stop_stream_after_seconds}
                                )
                            else:
                                logger.warning("Failed to auto-stop stream after QUIT")
                                await event_log.add_event(
                                    "stream_stop_failed",
                                    f"Failed to auto-stop stream {config.stop_stream_after_seconds}s after QUIT",
                                    {"reason": "auto_stop_quit", "was_streaming": True, "error": "stop_failed"}
                                )
                        else:
                            logger.debug("Stream not running, skipping auto-stop")
                            await event_log.add_event(
                                "stream_stop_skipped",
                                f"Stream stop skipped: not running {config.stop_stream_after_seconds}s after QUIT",
                                {"reason": "auto_stop_quit", "was_streaming": False, "delay_seconds": config.stop_stream_after_seconds}
                            )
                        
                        stream_stopped_after_quit = True
                
                # Reset QUIT to CONNECTING after 15 seconds (regardless of stream status)
                if elapsed_ms >= quit_reset_seconds * 1000:
                    logger.info(f"QUIT mode reset to CONNECTING after {quit_reset_seconds}s")
                    # Switch to safe scene
                    if obs_client.is_connected():
                        await obs_client.set_scene(config.safe_scene)
                        logger.info(f"Switched to safe scene after QUIT reset: {config.safe_scene}")
                    # Set flag to ignore QUIT mode and treat as disconnected
                    quit_reset_active = True
                    iracing_mode = None
                    # Reset QUIT tracking
                    quit_detected_ts = None
                    stream_stopped_after_quit = False
            elif iracing_mode != DrivingMode.QUIT:
                # Reset QUIT tracking when not in QUIT mode
                quit_detected_ts = None
                stream_stopped_after_quit = False
                quit_reset_active = False
            
            # Reset RESTART mode when entering LOBBY (active game lobby)
            # But NOT when transitioning from loading screen (None → LOBBY)
            # Loading screen returns None, so prev_iracing_mode == None means "was loading"
            import time as time_module
            
            # Map IDLE to LOBBY for RESTART reset check
            current_mode_for_restart = DrivingMode.LOBBY if iracing_mode == DrivingMode.IDLE else iracing_mode
            
            if current_mode_for_restart == DrivingMode.LOBBY and get_restart_mode():
                # Only reset if coming from actual game state, not loading screen
                if prev_iracing_mode is not None:
                    # Debug log
                    import json
                    try:
                        with open(r"c:\Users\richa\Projekty\obs-switcher\richa\.cursor\debug.log", "a") as f:
                            f.write(json.dumps({
                                "event": "restart_mode_reset",
                                "mode": current_mode_for_restart.value if current_mode_for_restart else None,
                                "prev_mode": prev_iracing_mode.value if prev_iracing_mode else None,
                                "reason": "entered_lobby_from_game",
                                "ts": int(now_ms())
                            }) + "\n")
                    except: pass
                    set_restart_mode(False)
                    logger.info(f"RESTART mode deactivated (entered LOBBY from {prev_iracing_mode.value})")
            
            # Update previous mode for future use
            prev_iracing_mode = iracing_mode
            
            # Check for RESTART: QUIT + hotkey pressed (or sticky mode)
            if iracing_mode == DrivingMode.QUIT:
                hotkey_now = is_hotkey_pressed()
                hotkey_recent = was_hotkey_pressed_recently()
                restart_mode_active = get_restart_mode()
                # Debug log
                import json, os
                try:
                    with open(r"c:\Users\richa\Projekty\obs-switcher\richa\.cursor\debug.log", "a") as f:
                        f.write(json.dumps({
                            "event": "quit_hotkey_check",
                            "hotkey_now": hotkey_now,
                            "hotkey_recent": hotkey_recent,
                            "restart_mode_active": restart_mode_active,
                            "ts": int(now_ms())
                        }) + "\n")
                except: pass
                
                # Activate RESTART mode on hotkey, or use sticky mode
                if hotkey_now or hotkey_recent:
                    if not restart_mode_active:
                        set_restart_mode(True)
                        logger.info("RESTART mode activated (hotkey pressed)")
                    iracing_mode = DrivingMode.RESTART
                elif restart_mode_active:
                    # Sticky mode - keep using RESTART until IDLE
                    iracing_mode = DrivingMode.RESTART
            
            # Get current OBS scene first (needed for state machine)
            obs_current_scene = await obs_client.get_current_scene()
            
            # Detect loading screen (iracing_mode is None when SessionTime is empty)
            is_loading = iracing_mode is None
            
            # Sync local current_state with global state (in case it was changed via API, e.g. toggle autoswitch)
            global_state = get_current_state()
            if global_state is not None:
                current_state = global_state
            
            # Tick state machine to get new state
            new_state = state_machine.tick(current_state, iracing_mode, obs_current_scene, is_loading=is_loading)
            
            # Use connection states from state machine (already handles QUIT/RESTART correctly)
            connected_iracing = new_state.connected_iracing
            connected_obs = new_state.connected_obs
            
            # Update session info when entering RACE, GARAGE, or LOBBY mode
            session_type = new_state.session_type
            session_name = new_state.session_name
            session_num = new_state.session_num
            
            # Read session info when mode changes to RACE, GARAGE, or LOBBY
            # Also read when transitioning from LOADING to LOBBY (session info should be available)
            if new_state.mode in (DrivingMode.RACE, DrivingMode.GARAGE, DrivingMode.LOBBY) and new_state.connected_iracing:
                if new_state.mode != current_state.mode or new_state.session_type is None:
                    # Mode changed to RACE/GARAGE/LOBBY or session info not yet set
                    # #region agent log
                    try:
                        with open(r"c:\Users\richa\Projekty\obs-switcher\richa\.cursor\debug.log", "a") as f:
                            f.write(json.dumps({
                                "location": "main.py:before_read_session_info",
                                "message": "About to read session info",
                                "data": {
                                    "mode": new_state.mode.value,
                                    "current_mode": current_state.mode.value,
                                    "connected_iracing": new_state.connected_iracing,
                                    "current_session_type": new_state.session_type,
                                },
                                "timestamp": int(now_ms()),
                                "sessionId": "debug-session",
                                "runId": "run1",
                                "hypothesisId": "A"
                            }) + "\n")
                    except: pass
                    # #endregion
                    session_info = await reader.read_session_info()
                    # #region agent log
                    try:
                        with open(r"c:\Users\richa\Projekty\obs-switcher\richa\.cursor\debug.log", "a") as f:
                            f.write(json.dumps({
                                "location": "main.py:after_read_session_info",
                                "message": "After read session info",
                                "data": {
                                    "session_info": session_info,
                                    "has_session_info": session_info is not None,
                                },
                                "timestamp": int(now_ms()),
                                "sessionId": "debug-session",
                                "runId": "run1",
                                "hypothesisId": "B"
                            }) + "\n")
                    except: pass
                    # #endregion
                    if session_info:
                        session_type = extract_session_type(session_info)
                        session_num = extract_session_num(session_info)
                        session_name = session_info.get("SessionName")
                        # #region agent log
                        try:
                            with open(r"c:\Users\richa\Projekty\obs-switcher\richa\.cursor\debug.log", "a") as f:
                                f.write(json.dumps({
                                    "location": "main.py:after_extract",
                                    "message": "After extract session info",
                                    "data": {
                                        "session_type": session_type,
                                        "session_name": session_name,
                                        "session_num": session_num,
                                    },
                                    "timestamp": int(now_ms()),
                                    "sessionId": "debug-session",
                                    "runId": "run1",
                                    "hypothesisId": "C"
                                }) + "\n")
                        except: pass
                        # #endregion
                        # Ignore Test sessions - don't set session info for Test
                        if session_type == "Test":
                            session_type = None
                            session_num = None
                            session_name = None
                        elif session_type or session_name or session_num is not None:
                            logger.info(f"Session info updated: type={session_type}, num={session_num}, name={session_name}")
            
            # Update state with session info if changed
            if (session_type != new_state.session_type or 
                session_name != new_state.session_name or 
                session_num != new_state.session_num):
                # #region agent log
                try:
                    with open(r"c:\Users\richa\Projekty\obs-switcher\richa\.cursor\debug.log", "a") as f:
                        f.write(json.dumps({
                            "location": "main.py:before_update_state",
                            "message": "Before updating state with session info",
                            "data": {
                                "old_session_type": new_state.session_type,
                                "new_session_type": session_type,
                                "old_session_name": new_state.session_name,
                                "new_session_name": session_name,
                                "old_session_num": new_state.session_num,
                                "new_session_num": session_num,
                            },
                            "timestamp": int(now_ms()),
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "D"
                        }) + "\n")
                except: pass
                # #endregion
                new_state = SwitchState(
                    connected_iracing=new_state.connected_iracing,
                    connected_obs=new_state.connected_obs,
                    autoswitch=new_state.autoswitch,
                    override_scene=new_state.override_scene,
                    override_until=new_state.override_until,
                    mode=new_state.mode,
                    target_scene=new_state.target_scene,
                    current_scene=new_state.current_scene,
                    last_switch_ts=new_state.last_switch_ts,
                    reason=new_state.reason,
                    session_type=session_type,
                    session_name=session_name,
                    session_num=session_num,
                )
                # #region agent log
                try:
                    with open(r"c:\Users\richa\Projekty\obs-switcher\richa\.cursor\debug.log", "a") as f:
                        f.write(json.dumps({
                            "location": "main.py:after_update_state",
                            "message": "After updating state with session info",
                            "data": {
                                "state_session_type": new_state.session_type,
                                "state_session_name": new_state.session_name,
                                "state_session_num": new_state.session_num,
                            },
                            "timestamp": int(now_ms()),
                            "sessionId": "debug-session",
                            "runId": "run1",
                            "hypothesisId": "D"
                        }) + "\n")
                except: pass
                # #endregion
            
            # Log mode change only (not every cycle) - compare with new_state.mode, not current_state.mode
            if new_state.mode != current_state.mode:
                logger.info(f"iRacing mode changed: {current_state.mode.value} -> {new_state.mode.value}")

            # Update connection states
            event_log = get_event_log()
            metrics = get_metrics()
            
            # Only log connection changes if not in QUIT/RESTART mode (to avoid spam)
            # QUIT/RESTART are considered disconnected, so connection state changes during these modes are expected
            is_quit_or_restart = new_state.mode in (DrivingMode.QUIT, DrivingMode.RESTART)
            
            if connected_iracing != current_state.connected_iracing:
                metrics.set_iracing_connected(connected_iracing)
                # Only log if not in QUIT/RESTART mode, or if transitioning TO connected (not FROM)
                if not is_quit_or_restart or connected_iracing:
                    if connected_iracing:
                        log_connection_restored(logger, "iRacing")
                        await event_log.add_event("connection_restored", "iRacing connection restored")
                    else:
                        log_connection_lost(logger, "iRacing")
                        await event_log.add_event("connection_lost", "iRacing connection lost")
                        if config.notifications_enabled:
                            notify_connection_lost("iRacing")

            if connected_obs != current_state.connected_obs:
                metrics.set_obs_connected(connected_obs)
                if connected_obs:
                    log_connection_restored(logger, "OBS")
                    await event_log.add_event("connection_restored", "OBS connection restored")
                    # Note: OBS connection restored notification removed (only show connection lost)
                    last_obs_notification_ts = None  # Reset notification timer on successful connection
                else:
                    log_connection_lost(logger, "OBS")
                    await event_log.add_event("connection_lost", "OBS connection lost")
                    if config.notifications_enabled:
                        notify_connection_lost("OBS")
                    # Try to reconnect OBS
                    if not obs_client.is_connected():
                        try:
                            await obs_client.connect(max_retries=1, initial_backoff=1.0)
                        except Exception as e:
                            logger.debug(f"OBS reconnection attempt failed: {e}")
                            # Determine connection failure reason for notification
                            error_str = str(e).lower()
                            error_type = type(e).__name__
                            is_auth_failed = (
                                "failed to identify" in error_str or
                                "authentication" in error_str or
                                "password" in error_str or
                                error_type == "OBSSDKError"
                            )
                            is_connection_refused = (
                                "connection refused" in error_str or
                                "10061" in error_str or
                                error_type == "ConnectionRefusedError"
                            )
                            connection_failed = is_auth_failed and not is_connection_refused
                            
                            # Notify user about failed reconnection attempt (with cooldown)
                            current_time = now_ms()
                            should_notify = (
                                config.notifications_enabled and
                                (last_obs_notification_ts is None or
                                 current_time - last_obs_notification_ts >= obs_notification_cooldown_ms)
                            )
                            if should_notify:
                                try:
                                    notify_connection_lost("OBS", was_connected=False, connection_failed=connection_failed)
                                    last_obs_notification_ts = current_time
                                except Exception as notify_error:
                                    logger.error(f"Failed to show notification: {notify_error}")
            elif not connected_obs and not obs_client.is_connected():
                # OBS is not connected and state hasn't changed (still trying to connect)
                # Try to reconnect periodically
                current_time = now_ms()
                should_retry = (
                    last_obs_notification_ts is None or
                    current_time - last_obs_notification_ts >= obs_notification_cooldown_ms
                )
                if should_retry:
                    try:
                        await obs_client.connect(max_retries=1, initial_backoff=1.0)
                    except Exception as e:
                        logger.debug(f"OBS periodic reconnection attempt failed: {e}")
                        # Determine connection failure reason for notification
                        error_str = str(e).lower()
                        error_type = type(e).__name__
                        is_auth_failed = (
                            "failed to identify" in error_str or
                            "authentication" in error_str or
                            "password" in error_str or
                            error_type == "OBSSDKError"
                        )
                        is_connection_refused = (
                            "connection refused" in error_str or
                            "10061" in error_str or
                            error_type == "ConnectionRefusedError"
                        )
                        connection_failed = is_auth_failed and not is_connection_refused
                        
                        # Notify user about failed connection attempt (with cooldown)
                        if config.notifications_enabled:
                            try:
                                notify_connection_lost("OBS", was_connected=False, connection_failed=connection_failed)
                                last_obs_notification_ts = current_time
                            except Exception as notify_error:
                                logger.error(f"Failed to show notification: {notify_error}")

            # State machine already ticked above (with session info updated if needed)
            set_current_state(new_state)

            # Check if scene switch is needed
            if new_state.target_scene != new_state.current_scene:
                # Check if we should actually switch
                should_switch = True
                if not new_state.autoswitch and new_state.override_scene is None:
                    should_switch = False

                # Check if required OBS profile is active (if configured)
                if should_switch and config.required_profile:
                    current_profile = await obs_client.get_current_profile()
                    if current_profile != config.required_profile:
                        should_switch = False
                        logger.debug(
                            f"Skipping scene switch: OBS profile mismatch "
                            f"(current: {current_profile}, required: {config.required_profile})"
                        )

                if should_switch and obs_client.is_connected():
                    switch_start = now_ms()
                    success = await obs_client.set_scene(new_state.target_scene)
                    if success:
                        latency = now_ms() - switch_start
                        log_scene_switch(
                            logger,
                            new_state.target_scene,
                            new_state.reason,
                            latency_ms=latency,
                        )
                        # Track metrics
                        metrics = get_metrics()
                        metrics.record_scene_switch(latency)
                        
                        await event_log.add_event(
                            "scene_switch",
                            f"Scene switched to: {new_state.target_scene}",
                            {"scene": new_state.target_scene, "reason": new_state.reason, "latency_ms": latency}
                        )
                        # Update state with new current scene
                        new_state = SwitchState(
                            connected_iracing=new_state.connected_iracing,
                            connected_obs=new_state.connected_obs,
                            autoswitch=new_state.autoswitch,
                            override_scene=new_state.override_scene,
                            override_until=new_state.override_until,
                            mode=new_state.mode,
                            target_scene=new_state.target_scene,
                            current_scene=new_state.target_scene,  # Updated after switch
                            last_switch_ts=new_state.last_switch_ts,
                            reason=new_state.reason,
                            session_type=new_state.session_type,
                            session_name=new_state.session_name,
                            session_num=new_state.session_num,
                        )
                        set_current_state(new_state)
                    else:
                        # Track failed scene switch
                        metrics = get_metrics()
                        metrics.record_error("scene_switch_failed")

            current_state = new_state

            # Sleep until next poll
            await asyncio.sleep(poll_interval)

        except asyncio.CancelledError:
            logger.info("Main loop cancelled")
            break
        except Exception as e:
            logger.error(f"Error in main loop: {e}", exc_info=True)
            # Continue loop even on error
            await asyncio.sleep(poll_interval)


async def run_service(config: AppConfig, config_path: str) -> None:
    """Run the service with all components."""
    # Setup logging (always to console, optionally to file)
    setup_logging(
        level=config.log_level,
        log_file=config.log_file,
        max_bytes=config.log_max_bytes,
        backup_count=config.log_backup_count
    )
    
    # Set global notifications flag
    set_notifications_enabled(config.notifications_enabled)
    logger.info(f"Notifications enabled: {config.notifications_enabled}")

    logger.info("Starting iRacing OBS switcher service")

    # Start hotkey listener if configured
    hotkey_started = False
    if config.restart_hotkey:
        hotkey_started = start_listener(config.restart_hotkey)
        if hotkey_started:
            logger.info(f"Hotkey listener started for RESTART: {config.restart_hotkey}")
        else:
            logger.warning(f"Failed to start hotkey listener for: {config.restart_hotkey}")

    # Initialize components
    reader = IRacingReader(
        poll_hz=config.poll_hz,
        quit_stall_seconds=config.quit_stall_seconds,
    )
    reader.startup()

    obs_client = ObsClient(ws_url=config.obs_ws_url, password=config.obs_password)

    policy = Policy(scenes=config.scenes, safe_scene=config.safe_scene)
    state_machine = StateMachine(
        policy=policy,
        debounce_ms=config.debounce_ms,
        cooldown_ms=config.cooldown_ms,
        override_seconds=config.override_seconds,
        autoswitch_default=config.autoswitch_default,
    )
    set_state_machine(state_machine)
    set_obs_client(obs_client)
    
    # Initialize event log
    event_log = EventLog(max_size=config.dashboard_event_log_size)
    set_event_log(event_log)
    
    # Initialize metrics (will be used in main loop)
    metrics = get_metrics()
    # Set initial connection states
    metrics.set_iracing_connected(reader.is_connected())
    metrics.set_obs_connected(False)  # Will be updated after OBS connection attempt

    # Initial state
    logger.info(f"Initializing with safe_scene: {config.safe_scene}, scenes mapping: {dict(config.scenes)}")
    initial_state = SwitchState(
        connected_iracing=reader.is_connected(),
        connected_obs=False,
        autoswitch=config.autoswitch_default,
        override_scene=None,
        override_until=None,
        mode=DrivingMode.CONNECTING,
        target_scene=config.safe_scene,
        current_scene=config.safe_scene,
        last_switch_ts=None,
        reason="initial",
        session_type=None,
        session_name=None,
        session_num=None,
    )

    # Try to connect to OBS (non-blocking - don't wait too long on startup)
    # Use fewer retries and shorter timeout on startup so API server can start quickly
    try:
        await obs_client.connect(max_retries=1, initial_backoff=0.5)
        if obs_client.is_connected():
            # Validate scene mappings after connection
            available_scenes = await obs_client.get_scene_list()
            if available_scenes:
                # Check all configured scenes exist
                missing_scenes = []
                all_configured_scenes = set(config.scenes.values()) | {config.safe_scene}
                
                for scene_name in all_configured_scenes:
                    if scene_name not in available_scenes:
                        missing_scenes.append(scene_name)
                
                if missing_scenes:
                    available_list = ", ".join(sorted(available_scenes))
                    missing_list = ", ".join(sorted(missing_scenes))
                    error_msg = (
                        f"Configuration error: The following scenes are not available in OBS: {missing_list}\n"
                        f"Available scenes in OBS: {available_list}\n"
                        f"Please update your config.ini file to use only available scene names."
                    )
                    logger.error(error_msg)
                    # Also show notification if enabled
                    if config.notifications_enabled:
                        from irswitch.util.notifications import show_toast
                        try:
                            show_toast(
                                "iRacing OBS Switcher - Configuration Error",
                                f"Missing scenes: {missing_list}\nAvailable: {available_list}"
                            )
                        except Exception:
                            pass  # Notification is optional
                else:
                    logger.info(f"Scene validation passed. All {len(all_configured_scenes)} configured scenes exist in OBS.")
                    logger.debug(f"Available OBS scenes: {', '.join(sorted(available_scenes))}")
            
            initial_state = SwitchState(
                connected_iracing=initial_state.connected_iracing,
                connected_obs=True,
                autoswitch=initial_state.autoswitch,
                override_scene=initial_state.override_scene,
                override_until=initial_state.override_until,
                mode=initial_state.mode,
                target_scene=initial_state.target_scene,
                current_scene=initial_state.current_scene,
                last_switch_ts=initial_state.last_switch_ts,
                reason=initial_state.reason,
                session_type=initial_state.session_type,
                session_name=initial_state.session_name,
                session_num=initial_state.session_num,
            )
            # Update metrics for OBS connection
            metrics.set_obs_connected(True)
        else:
            # Connection failed after retries (OBS never connected)
            # This shouldn't happen if connect() raises exception, but handle it anyway
            logger.warning("Failed to connect to OBS on startup after retries. Will retry in main loop.")
            # Notify user about failed connection on startup
            if config.notifications_enabled:
                notify_connection_lost("OBS", was_connected=False, connection_failed=False)
    except Exception as e:
        logger.warning(f"Failed to connect to OBS on startup: {e}. Will retry in main loop.")
        # Determine connection failure reason (check in priority order)
        error_str = str(e).lower()
        error_type = type(e).__name__
        
        # Priority 1: Authentication/identification error (OBS running, wrong password)
        is_auth_failed = (
            "failed to identify" in error_str or
            "authentication" in error_str or
            "password" in error_str or
            error_type == "OBSSDKError"
        )
        
        # Priority 2: Connection refused (OBS not running or WebSocket disabled)
        is_connection_refused = (
            "connection refused" in error_str or
            "10061" in error_str or
            error_type == "ConnectionRefusedError"
        )
        
        # Determine connection_failed flag
        # True only if OBS is running but connection failed (auth error)
        # False if OBS is not running (connection refused) or unknown error
        connection_failed = is_auth_failed and not is_connection_refused
        
        # Notify user about failed connection on startup
        if config.notifications_enabled:
            try:
                notify_connection_lost("OBS", was_connected=False, connection_failed=connection_failed)
            except Exception as notify_error:
                logger.error(f"Failed to show notification: {notify_error}")

    # Set initial state BEFORE starting API server (so dashboards have state available)
    set_current_state(initial_state)
    logger.info(f"Initial state set: mode={initial_state.mode.value}, scene={initial_state.current_scene}, connected_obs={initial_state.connected_obs}, connected_iracing={initial_state.connected_iracing}")

    # Create and start API server
    logger.info("Creating API server...")
    try:
        app = create_app()
        app["config"] = config  # Store config in app for dashboard access
        app["config_path"] = config_path  # Store config path for hot reload
        logger.info("API application created successfully")
    except Exception as e:
        logger.error(f"Failed to create API application: {e}", exc_info=True)
        raise
    
    logger.info("Setting up AppRunner...")
    try:
        runner = web.AppRunner(app)
        await runner.setup()
        logger.info("AppRunner setup complete")
    except Exception as e:
        logger.error(f"Failed to setup AppRunner: {e}", exc_info=True)
        raise
    
    logger.info(f"Starting TCP site on {config.http_host}:{config.http_port}...")
    try:
        site = web.TCPSite(runner, config.http_host, config.http_port)
        await site.start()
        logger.info(f"API server started successfully on http://{config.http_host}:{config.http_port}")
    except OSError as e:
        error_str = str(e).lower()
        if "address already in use" in error_str or "10048" in error_str or "address in use" in error_str:
            logger.error(f"Port {config.http_port} is already in use. Please stop the other application or change the port in config.ini")
        else:
            logger.error(f"Failed to start API server (OSError): {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Failed to start API server: {e}", exc_info=True)
        raise
    
    # Start background task to continue trying to connect to OBS if not connected yet
    async def background_obs_connect():
        """Background task to keep trying to connect to OBS."""
        # Wait a bit before first attempt (to let API server start)
        await asyncio.sleep(2.0)
        
        while True:
            try:
                if not obs_client.is_connected():
                    try:
                        await obs_client.connect(max_retries=1, initial_backoff=5.0)
                        if obs_client.is_connected():
                            logger.info("OBS connected via background task")
                            # Update state to reflect OBS connection
                            current = get_current_state()
                            if current:
                                new_state = SwitchState(
                                    connected_iracing=current.connected_iracing,
                                    connected_obs=True,
                                    autoswitch=current.autoswitch,
                                    override_scene=current.override_scene,
                                    override_until=current.override_until,
                                    mode=current.mode,
                                    target_scene=current.target_scene,
                                    current_scene=current.current_scene,
                                    last_switch_ts=current.last_switch_ts,
                                    reason=current.reason,
                                    session_type=current.session_type,
                                    session_name=current.session_name,
                                    session_num=current.session_num,
                                )
                                set_current_state(new_state)
                    except Exception as e:
                        logger.debug(f"Background OBS connection attempt failed: {e}")
                    await asyncio.sleep(10.0)  # Wait 10 seconds before next attempt
                else:
                    # Already connected, check periodically if still connected
                    await asyncio.sleep(30.0)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in background OBS connection task: {e}", exc_info=True)
                await asyncio.sleep(10.0)
    
    obs_connect_task = asyncio.create_task(background_obs_connect())
    logger.info("Background OBS connection task started")

    # Setup signal handlers for graceful shutdown
    shutdown_event = asyncio.Event()
    
    # Make shutdown event available to API
    from irswitch.server.api import set_shutdown_event
    set_shutdown_event(shutdown_event)
    
    def signal_handler() -> None:
        logger.info("Shutdown signal received")
        shutdown_event.set()

    # Signal handlers only work on Unix, on Windows use try/except
    try:
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, signal_handler)
    except NotImplementedError:
        # Windows doesn't support add_signal_handler
        # Will handle KeyboardInterrupt in main() instead
        pass

    # Run main loop
    main_task = asyncio.create_task(
        main_loop(config, reader, obs_client, state_machine, initial_state)
    )

    try:
        # Wait for shutdown signal
        await shutdown_event.wait()
    finally:
        # Cancel background tasks
        obs_connect_task.cancel()
        try:
            await obs_connect_task
        except asyncio.CancelledError:
            pass
        
        # Cancel main loop
        main_task.cancel()
        try:
            await main_task
        except asyncio.CancelledError:
            pass

        # Cleanup
        stop_listener()  # Stop hotkey listener
        await obs_client.disconnect()
        await runner.cleanup()
        logger.info("Service stopped")


def main() -> int:
    """Main entry point."""
    parser = build_parser()
    args = parser.parse_args()

    try:
        config = AppConfig.from_file(args.config)
    except Exception as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        return 1

    try:
        asyncio.run(run_service(config, args.config))
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
