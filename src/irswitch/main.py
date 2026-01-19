"""Entry point for the core service."""
from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys

from aiohttp import web

from irswitch.config import AppConfig
from irswitch.iracing.reader import IRacingReader
from irswitch.logic.policy import Policy
from irswitch.logic.state_machine import StateMachine
from irswitch.models import DrivingMode, SwitchState
from irswitch.obs.client import ObsClient
from irswitch.server.api import create_app, set_current_state, set_state_machine, set_obs_client, get_restart_mode, set_restart_mode
from irswitch.util.clock import now_ms
from irswitch.util.logging import (
    log_connection_lost,
    log_connection_restored,
    log_scene_switch,
    setup_logging,
)
from irswitch.util.notifications import (
    notify_connection_lost,
    notify_connection_restored,
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

    logger.info("Starting main loop")

    while True:
        try:
            # Poll iRacing
            iracing_mode = await reader.read_mode()
            connected_iracing = iracing_mode is not None
            
            # Reset RESTART mode when entering IDLE (active game lobby)
            # But NOT when transitioning from loading screen (None → IDLE)
            # Loading screen returns None, so prev_iracing_mode == None means "was loading"
            import time as time_module
            
            if iracing_mode == DrivingMode.IDLE and get_restart_mode():
                # Only reset if coming from actual game state, not loading screen
                if prev_iracing_mode is not None:
                    # Debug log
                    import json
                    try:
                        with open(r"c:\Users\richa\Projekty\obs-switcher\richa\.cursor\debug.log", "a") as f:
                            f.write(json.dumps({
                                "event": "restart_mode_reset",
                                "mode": iracing_mode.value if iracing_mode else None,
                                "prev_mode": prev_iracing_mode.value if prev_iracing_mode else None,
                                "reason": "entered_idle_from_game",
                                "ts": int(now_ms())
                            }) + "\n")
                    except: pass
                    set_restart_mode(False)
                    logger.info(f"RESTART mode deactivated (entered IDLE from {prev_iracing_mode.value})")
            
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
            
            # Log mode change only (not every cycle)
            if iracing_mode != current_state.mode:
                logger.info(f"iRacing mode changed: {current_state.mode.value} -> {iracing_mode.value if iracing_mode else 'None'}")

            # Get current OBS scene
            obs_current_scene = await obs_client.get_current_scene()
            connected_obs = obs_current_scene is not None

            # Update connection states
            if connected_iracing != current_state.connected_iracing:
                if connected_iracing:
                    log_connection_restored(logger, "iRacing")
                else:
                    log_connection_lost(logger, "iRacing")
                    if config.notifications_enabled:
                        notify_connection_lost("iRacing")

            if connected_obs != current_state.connected_obs:
                if connected_obs:
                    log_connection_restored(logger, "OBS")
                    if config.notifications_enabled:
                        notify_connection_restored("OBS")
                    last_obs_notification_ts = None  # Reset notification timer on successful connection
                else:
                    log_connection_lost(logger, "OBS")
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

            # Tick state machine
            new_state = state_machine.tick(current_state, iracing_mode, obs_current_scene)
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
                        )
                        set_current_state(new_state)

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


async def run_service(config: AppConfig) -> None:
    """Run the service with all components."""
    # Setup logging
    setup_logging(config.log_level)

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

    # Initial state
    logger.info(f"Initializing with safe_scene: {config.safe_scene}, scenes mapping: {dict(config.scenes)}")
    initial_state = SwitchState(
        connected_iracing=reader.is_connected(),
        connected_obs=False,
        autoswitch=config.autoswitch_default,
        override_scene=None,
        override_until=None,
        mode=DrivingMode.IDLE,
        target_scene=config.safe_scene,
        current_scene=config.safe_scene,
        last_switch_ts=None,
        reason="initial",
    )

    # Connect to OBS
    try:
        await obs_client.connect()
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
            )
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

    # Create and start API server
    app = create_app()
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, config.http_host, config.http_port)
    try:
        await site.start()
    except Exception as e:
        raise

    logger.info(f"API server started on http://{config.http_host}:{config.http_port}")

    # Setup signal handlers for graceful shutdown
    shutdown_event = asyncio.Event()

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
        asyncio.run(run_service(config))
        return 0
    except KeyboardInterrupt:
        return 0
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
