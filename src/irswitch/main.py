"""Entry point for the core service."""

from __future__ import annotations

import argparse
import asyncio
import logging
import signal
import sys
import threading
import webbrowser

import aiohttp
from aiohttp import web

from irswitch.config import AppConfig
from irswitch.i18n import set_language
from irswitch.iracing.extractors import (
    extract_session_num,
    extract_session_type,
    extract_total_sessions,
)
from irswitch.iracing.reader import IRacingReader
from irswitch.logic.policy import Policy
from irswitch.logic.state_machine import StateMachine
from irswitch.models import DrivingMode, SwitchState
from irswitch.oauth import create_oauth_manager
from irswitch.obs.client import ObsClient
from irswitch.server.api import (
    APP_CONFIG,
    APP_CONFIG_PATH,
    create_app,
    get_current_state,
    get_restart_mode,
    set_current_state,
    set_obs_client,
    set_reader,
    set_restart_mode,
    set_state_machine,
)
from irswitch.server.event_log import EventLog, get_event_log, set_event_log
from irswitch.server.metrics import get_metrics
from irswitch.util.clock import now_ms
from irswitch.util.hotkeys import (
    is_hotkey_pressed,
    start_listener,
    stop_listener,
    was_hotkey_pressed_recently,
)
from irswitch.util.loading_tracker import LoadingTimeTracker
from irswitch.util.logging import (
    log_connection_lost,
    log_connection_restored,
    log_scene_switch,
    setup_logging,
)
from irswitch.util.notifications import set_notifications_enabled

logger = logging.getLogger(__name__)

# Cache thresholds for stream selection data (module-level constants)
STREAM_CACHE_FRESH_MS = 5000  # 5 seconds - fresh cache, use directly
STREAM_CACHE_GRACE_MS = 10000  # 10 seconds - stale cache, use API fallback


async def handle_oauth_flow(config: AppConfig) -> None:
    """
    Automated OAuth flow at startup.

    If OAuth credentials are configured but not yet authorized:
    1. Calls /oauth/initiate to get authorization URL with valid state
    2. Opens browser for user authorization
    3. Waits for OAuth callback to complete
    4. Only then proceeds with main functionality
    """
    oauth_manager = create_oauth_manager()

    if oauth_manager is None:
        logger.debug("OAuth not configured - skipping OAuth flow")
        return

    # Check if already authenticated
    if oauth_manager.is_authenticated():
        logger.info("OAuth already authenticated")
        return

    logger.info("OAuth not authenticated - initiating automated OAuth flow")

    # Call /oauth/initiate to get authorization URL with valid state
    # This ensures state is stored in _oauth_states for callback validation
    api_url = f"http://127.0.0.1:{config.http_port}/oauth/initiate"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(api_url) as response:
                if response.status != 200:
                    logger.error(f"Failed to initiate OAuth: {response.status}")
                    return

                data = await response.json()
                auth_url = data["authorization_url"]
                # State is now stored in _oauth_states by handle_oauth_initiate
    except Exception as e:
        logger.error(f"Failed to call /oauth/initiate: {e}")
        return

    logger.info("Opening browser for OAuth authorization...")
    logger.info(f"Authorization URL: {auth_url[:80]}...")

    # Open browser in new thread (non-blocking)
    def open_browser():
        try:
            webbrowser.open(auth_url)
        except Exception as e:
            logger.warning(f"Failed to open browser: {e}")

    threading.Thread(target=open_browser, daemon=True).start()

    # Wait for user to complete authorization
    logger.info("Waiting for OAuth authorization... (complete in browser)")

    # Poll for authentication status
    max_wait_seconds = 300  # 5 minutes timeout
    poll_interval = 2.0
    waited: float = 0.0

    while waited < max_wait_seconds:
        await asyncio.sleep(poll_interval)
        waited += poll_interval

        # Reload token from disk to check if it was saved
        loaded = await oauth_manager.load_token()
        is_auth = oauth_manager.is_authenticated()
        logger.debug(f"OAuth poll: loaded={loaded}, is_authenticated={is_auth}")

        if is_auth:
            logger.info("OAuth authorization completed successfully!")
            return

        # Show progress
        remaining = max_wait_seconds - waited
        logger.info(f"Waiting for OAuth... ({remaining}s remaining)")

    logger.warning("OAuth authorization timed out - continuing without YouTube API access")


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

    # Track previous mode to detect loading�active transitions
    prev_iracing_mode: DrivingMode | None = None
    prev_was_loading_process = False

    # Loading tracker
    loading_tracker = LoadingTimeTracker(
        default_loading_time_seconds=config.default_loading_time_seconds
    )

    # Auto-start broadcast tracking
    loading_start_ts = None  # type: float | None
    auto_start_scheduled_ts = None  # type: float | None
    auto_start_triggered = False

    # Auto-stop stream tracking
    quit_detected_ts: float | None = None
    stream_stopped_after_quit = False
    quit_reset_active = False  # Flag to prevent QUIT mode after reset
    quit_reset_disconnect_ts: float | None = (
        None  # Timestamp when iRacing disconnected after QUIT reset
    )
    last_valid_mode: DrivingMode | None = (
        None  # Track last valid mode (not None) for QUIT detection
    )

    # Stream title tracking
    last_stream_title: str | None = None
    last_stream_selected: bool = False  # Track if stream was selected
    last_stream_ready_selected: bool = False  # Track if stream is ready (selected and configured)
    last_stream_selection_check_ts: float = 0.0  # Timestamp of last stream selection check
    stream_selection_consecutive_readings: int = 0  # Consecutive readings for stability
    stream_selection_min_confirm_count: int = (
        3  # Need 3 consecutive same readings to confirm change
    )

    event_log = get_event_log()
    logger.info("Starting main loop")

    while True:
        try:
            # Poll iRacing
            iracing_mode = await reader.read_mode()
            # Store actual iRacing mode before it might be modified by quit_reset_active
            actual_iracing_mode = iracing_mode

            # Loading screen detection and tracking
            # NEW: Use process detection for more accurate loading screen detection
            # Loading screen = iRacing process is running but SDK is not connected
            # Process check uses subprocess (tasklist); keep it off the event loop
            iracing_process_running = await asyncio.to_thread(reader.is_process_running)
            sdk_connected = reader.is_connected()

            # Loading screen: process running but SDK not connected
            is_loading = iracing_process_running and not sdk_connected
            was_loading = prev_iracing_mode is None and not sdk_connected

            # Track first connection for auto-start stream logic
            # When we go from loading (process running, SDK not connected) to connected,
            # this is the end of loading screen
            prev_loading_process = prev_was_loading_process

            # First connection: was loading (process running, SDK not connected) and now connected
            is_first_connection = (
                prev_loading_process and sdk_connected and iracing_mode is not None
            )

            # Update tracking
            prev_was_loading_process = is_loading

            # Start loading tracking when we detect loading screen (process running, SDK not connected)
            if is_loading and not prev_loading_process and loading_start_ts is None:
                # Loading screen started - start tracking
                loading_start_ts = now_ms()
                auto_start_scheduled_ts = None
                auto_start_triggered = False
                loading_tracker.start_loading()
                logger.info("Loading screen detected (iRacing process running, SDK not connected)")
                await event_log.add_event(
                    "loading_started",
                    "iRacing loading screen started (process detected)",
                    {"process_running": True, "sdk_connected": False},
                )

            # Handle first connection (end of loading) - for auto-start purposes
            if is_first_connection:
                logger.info("First connection detected - loading screen ended")

            # Update last_valid_mode when we have a valid mode (not None, not QUIT, not RESTART)
            if iracing_mode is not None and iracing_mode not in (
                DrivingMode.QUIT,
                DrivingMode.RESTART,
                DrivingMode.CONNECTING,
                DrivingMode.LOADING,
            ):
                last_valid_mode = iracing_mode

            # Detect "implicit QUIT" - when iRacing was in game (had a valid mode) and process stops
            # Use last_valid_mode instead of prev_iracing_mode because prev might be None during loading
            # IMPORTANT: Don't detect QUIT during loading screen (process running, SDK not connected)
            was_in_game = last_valid_mode is not None
            is_now_truly_disconnected = (
                iracing_mode is None and not sdk_connected and not iracing_process_running
            )
            implicit_quit = was_in_game and is_now_truly_disconnected and not quit_reset_active

            # If we're already in QUIT mode (quit_detected_ts is set), continue QUIT mode
            # until it resets (after 15 seconds)
            if quit_detected_ts is not None and iracing_mode is None and not quit_reset_active:
                iracing_mode = DrivingMode.QUIT

            if implicit_quit:
                # Treat this as QUIT mode
                iracing_mode = DrivingMode.QUIT
                logger.info(
                    f"Implicit QUIT detected - iRacing process stopped after being in {last_valid_mode.value if last_valid_mode else 'game'}"
                )
                # DON'T clear last_valid_mode here - it will be cleared after QUIT reset
                # This allows QUIT mode to persist until the 15-second reset

            # Only track loading if we're transitioning from a known mode (not None) to None
            # This prevents tracking loading on first iteration when prev_iracing_mode is None
            # IMPORTANT: Don't reset loading_start_ts if it's already set and auto_start hasn't triggered yet
            # This preserves the first_connection loading_start_ts for auto-start
            if is_loading and not was_loading and prev_iracing_mode is not None:
                # Loading started (transition from mode to None)
                # Only set loading_start_ts if it's not already set or auto_start has already triggered
                if loading_start_ts is None or auto_start_triggered:
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
                    logger.info(
                        f"Session info during loading: type={session_type}, num={session_num}, name={session_name}"
                    )

                await event_log.add_event(
                    "loading_started",
                    "iRacing loading screen started"
                    + (f" - {session_type}" if session_type else ""),
                    {
                        "previous_mode": (prev_iracing_mode.value if prev_iracing_mode else None),
                        "session_type": session_type,
                        "session_num": session_num,
                        "session_name": str(session_name) if session_name else None,
                    },
                )

            elif not is_loading and was_loading and not is_first_connection:
                # Loading ended (transition from None to mode)
                # Skip this block on first connection - we want to keep loading_start_ts for auto-start
                # Only end loading if tracker is actually tracking a loading
                if loading_tracker.is_loading():
                    duration = loading_tracker.end_loading()
                else:
                    # Loading tracker is not tracking, but we detected a transition from None to mode
                    # This can happen if loading was never started (e.g., QUIT mode)
                    duration = None
                loading_start_ts = None
                auto_start_scheduled_ts = None
                auto_start_triggered = False
                if duration is not None:
                    logger.info(f"Loading screen ended, duration: {duration:.2f}s")
                    await event_log.add_event(
                        "loading_ended",
                        f"iRacing loading screen ended, duration: {duration:.2f}s",
                        {
                            "duration_seconds": duration,
                            "new_mode": iracing_mode.value if iracing_mode else None,
                        },
                    )

            # QUIT mode handling: reset to CONNECTING after 15 seconds
            # If quit_reset_active is True, ignore QUIT mode and treat as disconnected
            if quit_reset_active:
                # After reset, ignore QUIT mode until iRacing actually disconnects and stays disconnected
                # Check if iRacing is actually disconnected (not just QUIT mode)
                if not reader.is_connected():
                    # iRacing disconnected - start tracking disconnect time
                    if quit_reset_disconnect_ts is None:
                        quit_reset_disconnect_ts = now_ms()
                    # Only clear reset flag after iRacing has been disconnected for at least 2 seconds
                    elif now_ms() - quit_reset_disconnect_ts >= 2000:
                        # iRacing has been disconnected for 2+ seconds - clear reset flag
                        quit_reset_active = False
                        quit_detected_ts = None
                        stream_stopped_after_quit = False
                        quit_reset_disconnect_ts = None
                elif iracing_mode is not None and iracing_mode != DrivingMode.QUIT:
                    # Mode changed away from QUIT to something else (e.g., IDLE, RACE) - clear reset flag
                    quit_reset_active = False
                    quit_detected_ts = None
                    stream_stopped_after_quit = False
                    quit_reset_disconnect_ts = None
                else:
                    # Still in QUIT mode (or None after reset), but we've reset - treat as disconnected
                    # Reset disconnect timestamp if iRacing reconnected
                    quit_reset_disconnect_ts = None
                    if iracing_mode == DrivingMode.QUIT:
                        # Ignore QUIT mode - set to None to force CONNECTING state
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
                                logger.info(
                                    f"Auto-stopped stream {config.stop_stream_after_seconds}s after QUIT"
                                )
                                await event_log.add_event(
                                    "stream_stopped",
                                    f"Stream stopped automatically {config.stop_stream_after_seconds}s after QUIT (was running)",
                                    {
                                        "reason": "auto_stop_quit",
                                        "was_streaming": True,
                                        "delay_seconds": config.stop_stream_after_seconds,
                                    },
                                )
                            else:
                                logger.warning("Failed to auto-stop stream after QUIT")
                                await event_log.add_event(
                                    "stream_stop_failed",
                                    f"Failed to auto-stop stream {config.stop_stream_after_seconds}s after QUIT",
                                    {
                                        "reason": "auto_stop_quit",
                                        "was_streaming": True,
                                        "error": "stop_failed",
                                    },
                                )
                        else:
                            logger.debug("Stream not running, skipping auto-stop")
                            await event_log.add_event(
                                "stream_stop_skipped",
                                f"Stream stop skipped: not running {config.stop_stream_after_seconds}s after QUIT",
                                {
                                    "reason": "auto_stop_quit",
                                    "was_streaming": False,
                                    "delay_seconds": config.stop_stream_after_seconds,
                                },
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
                    quit_reset_disconnect_ts = None  # Will be set when iRacing actually disconnects
                    iracing_mode = None
                    # Reset QUIT tracking
                    quit_detected_ts = None
                    stream_stopped_after_quit = False
                    last_valid_mode = None  # Clear last_valid_mode after QUIT reset
            elif iracing_mode is not None and iracing_mode != DrivingMode.QUIT:
                # Reset QUIT tracking when not in QUIT mode (but not when None after reset)
                # Only clear if iRacing is actually connected and in a non-QUIT mode
                quit_detected_ts = None
                stream_stopped_after_quit = False
                quit_reset_active = False

            # Reset RESTART mode when entering LOBBY (active game lobby)
            # But NOT when transitioning from loading screen (None → LOBBY)
            # Loading screen returns None, so prev_iracing_mode == None means "was loading"

            # Map IDLE to LOBBY for RESTART reset check
            current_mode_for_restart = (
                DrivingMode.LOBBY if iracing_mode == DrivingMode.IDLE else iracing_mode
            )

            if current_mode_for_restart == DrivingMode.LOBBY and get_restart_mode():
                # Only reset if coming from actual game state, not loading screen
                if prev_iracing_mode is not None:
                    set_restart_mode(False)
                    logger.info(
                        f"RESTART mode deactivated (entered LOBBY from {prev_iracing_mode.value})"
                    )

            # Update previous mode for future use
            prev_iracing_mode = iracing_mode

            # Check for RESTART: QUIT + hotkey pressed (or sticky mode)
            if iracing_mode == DrivingMode.QUIT:
                hotkey_now = is_hotkey_pressed()
                hotkey_recent = was_hotkey_pressed_recently()
                restart_mode_active = get_restart_mode()

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
            # Note: is_first_connection is already calculated earlier in the loop (line ~161)
            # We use the existing value here instead of recalculating

            # Sync local current_state with global state (in case it was changed via API, e.g. toggle autoswitch)
            global_state = get_current_state()
            if global_state is not None:
                current_state = global_state

            # Tick state machine to get new state
            new_state = state_machine.tick(
                current_state, iracing_mode, obs_current_scene, is_loading=is_loading
            )

            # Auto-start broadcast logic (during loading)
            # Use state machine's LOADING mode instead of is_loading flag
            is_loading_state = new_state.mode == DrivingMode.LOADING
            # Initialize loading_start_ts if we're in LOADING state and it's not set
            if is_loading_state and loading_start_ts is None:
                loading_start_ts = now_ms()
                loading_tracker.start_loading()
                auto_start_scheduled_ts = None
                auto_start_triggered = False
            elif (
                not is_loading_state
                and loading_start_ts is not None
                and not is_first_connection
                and auto_start_triggered
            ):
                # Loading ended, reset tracking (but not on first connection or while waiting for auto-start)
                duration = loading_tracker.end_loading()
                loading_start_ts = None
                auto_start_scheduled_ts = None
                auto_start_triggered = False

            # Reset auto-start tracking when iRacing truly disconnects (CONNECTING state AND process not running)
            # This prevents auto-start from triggering after iRacing quits
            # BUT: Don't reset during loading screen (process running, SDK not connected)
            is_truly_disconnected = (
                new_state.mode == DrivingMode.CONNECTING and not iracing_process_running
            )
            if is_truly_disconnected and loading_start_ts is not None and not is_first_connection:
                # iRacing truly disconnected (process not running) - cancel any pending auto-start
                loading_start_ts = None
                auto_start_scheduled_ts = None
                auto_start_triggered = False
            # Check if we're in LOADING state (either from state machine or directly from is_loading)
            is_loading_state = new_state.mode == DrivingMode.LOADING
            is_loading_direct = (
                is_loading and new_state.connected_iracing
            )  # Loading when iRacing is connected but mode is None
            # First connection is treated as "end of loading" - we should try auto-start immediately
            # Also try auto-start if loading_start_ts is set and auto_start hasn't triggered yet
            has_pending_auto_start = loading_start_ts is not None and not auto_start_triggered
            # Auto-start should only happen when:
            # 1. In LOADING state (iRacing connected, loading screen)
            # 2. Loading screen via process detection (process running, SDK not connected)
            # 3. First connection (just connected to iRacing)
            # 4. Pending auto-start AND (iRacing is connected OR loading screen)
            iracing_is_connected_or_loading = (
                new_state.connected_iracing or is_first_connection or is_loading
            )
            should_try_auto_start = (
                is_loading_state
                or is_loading_direct
                or is_first_connection
                or is_loading
                or (has_pending_auto_start and iracing_is_connected_or_loading)
            )

            if (
                should_try_auto_start
                and config.auto_start_broadcast
                and loading_start_ts is not None
            ):
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
                if (
                    not auto_start_triggered
                    and auto_start_scheduled_ts is not None
                    and current_ts >= auto_start_scheduled_ts
                ):
                    # Calculate cache age for decision making
                    cache_age_ms = current_ts - last_stream_selection_check_ts

                    # Determine data source: fresh cache, stale cache with API fallback, or forced API
                    if last_stream_selected and cache_age_ms <= STREAM_CACHE_FRESH_MS:
                        # Fresh cache - use cached values directly
                        is_ready = last_stream_ready_selected
                        is_streaming = False  # ready_selected implies not streaming
                        data_source = "cache_fresh"
                        logger.debug(f"Using fresh cache for auto-start (age={cache_age_ms}ms)")
                    elif last_stream_selected and cache_age_ms <= STREAM_CACHE_GRACE_MS:
                        # Stale cache - use API fallback for reliability
                        is_ready = await obs_client.is_broadcast_ready()
                        is_streaming, _ = await obs_client.get_stream_status()
                        data_source = "cache_stale_api"
                        logger.debug(f"Stale cache, using API fallback (age={cache_age_ms}ms)")
                    else:
                        # Cache too old or no cache - forced API call
                        is_ready = await obs_client.is_broadcast_ready()
                        is_streaming, _ = await obs_client.get_stream_status()
                        data_source = "api_fallback"
                        logger.debug(f"Cache expired, using API (age={cache_age_ms}ms)")

                    # Attempt to start stream
                    if is_ready and not is_streaming:
                        success = await obs_client.start_stream()
                        if success:
                            logger.info(f"Auto-started broadcast during loading ({data_source})")
                            await event_log.add_event(
                                "stream_started",
                                f"Stream started automatically during loading ({data_source})",
                                {
                                    "reason": "auto_start_loading",
                                    "data_source": data_source,
                                    "cache_age_ms": cache_age_ms,
                                },
                            )
                        else:
                            logger.warning("Failed to auto-start broadcast during loading")
                            await event_log.add_event(
                                "stream_start_failed",
                                "Failed to auto-start stream during loading",
                                {
                                    "reason": "auto_start_loading",
                                    "data_source": data_source,
                                    "error": "start_failed",
                                },
                            )
                    else:
                        if not is_ready:
                            logger.debug("Broadcast not ready for auto-start")
                            await event_log.add_event(
                                "stream_start_skipped",
                                "Stream start skipped: broadcast not ready",
                                {
                                    "reason": "auto_start_loading",
                                    "data_source": data_source,
                                    "cache_age_ms": cache_age_ms,
                                },
                            )
                        if is_streaming:
                            logger.debug("Stream already running, skipping auto-start")
                            await event_log.add_event(
                                "stream_start_skipped",
                                "Stream start skipped: already running",
                                {
                                    "reason": "auto_start_loading",
                                    "data_source": data_source,
                                },
                            )

                    auto_start_triggered = True  # Only try once per loading

            # Use connection states from state machine (already handles QUIT/RESTART correctly)
            connected_iracing = new_state.connected_iracing
            connected_obs = new_state.connected_obs

            # Update session info when entering RACE, GARAGE, or LOBBY mode
            session_type = new_state.session_type
            session_name = new_state.session_name
            session_num = new_state.session_num
            total_sessions = (
                new_state.total_sessions if hasattr(new_state, "total_sessions") else None
            )

            # Check if iRacing is actually connected (not just state machine's view)
            # Use reader.is_connected() to check actual connection status
            iracing_actually_connected = reader.is_connected()
            # Read session info when mode changes to RACE, GARAGE, or LOBBY
            # Also read when transitioning from LOADING to LOBBY (session info should be available)
            # Use actual_iracing_mode (before quit_reset_active modification) to check if we're in LOBBY/RACE/GARAGE
            # This ensures session info is read even when quit_reset_active forces CONNECTING state
            actual_mode_for_session = actual_iracing_mode
            if (
                actual_mode_for_session == DrivingMode.LOBBY
                or actual_mode_for_session == DrivingMode.IDLE
            ):
                actual_mode_for_session = DrivingMode.LOBBY
            is_actual_race_garage_lobby = actual_mode_for_session in (
                DrivingMode.RACE,
                DrivingMode.GARAGE,
                DrivingMode.LOBBY,
            )

            if is_actual_race_garage_lobby and iracing_actually_connected:
                if new_state.mode != current_state.mode or new_state.session_type is None:
                    # Mode changed to RACE/GARAGE/LOBBY or session info not yet set
                    session_info = await reader.read_session_info()
                    if session_info:
                        session_type = extract_session_type(session_info)
                        session_num = extract_session_num(session_info)
                        total_sessions = extract_total_sessions(session_info)
                        # Also try direct SessionTotalSessions from iRacing
                        if total_sessions is None:
                            session_total_raw = session_info.get("SessionTotalSessions")
                            if isinstance(session_total_raw, (int, float)):
                                total_sessions = int(session_total_raw)
                            elif isinstance(session_total_raw, str):
                                try:
                                    total_sessions = int(session_total_raw)
                                except ValueError:
                                    pass

                        session_name_raw = session_info.get("SessionName")
                        session_name = str(session_name_raw) if session_name_raw else None
                        # Try WeekendInfo for session name if SessionName is not available
                        if not session_name:
                            weekend_info = session_info.get("WeekendInfo")
                            if weekend_info is not None:
                                if isinstance(weekend_info, dict):
                                    # Try common session name fields in WeekendInfo
                                    session_name_val = (
                                        weekend_info.get("SessionName")
                                        or weekend_info.get("SessionDisplayName")
                                        or weekend_info.get("EventName")
                                    )
                                    session_name = (
                                        str(session_name_val) if session_name_val else None
                                    )
                                elif hasattr(weekend_info, "__dict__"):
                                    session_name_val = (
                                        weekend_info.__dict__.get("SessionName")
                                        or weekend_info.__dict__.get("SessionDisplayName")
                                        or weekend_info.__dict__.get("EventName")
                                    )
                                    session_name = (
                                        str(session_name_val) if session_name_val else None
                                    )
                                elif hasattr(weekend_info, "SessionName"):
                                    session_name = str(weekend_info.SessionName)
                                elif hasattr(weekend_info, "SessionDisplayName"):
                                    session_name = str(weekend_info.SessionDisplayName)
                                elif hasattr(weekend_info, "EventName"):
                                    session_name = str(weekend_info.EventName)
                        # Ignore Test sessions - don't set session info for Test
                        if session_type == "Test":
                            session_type = None
                            session_num = None
                            session_name = None
                            total_sessions = None
                        elif session_type or session_name or session_num is not None:
                            # Format session_num as "x of y" if total_sessions is available
                            session_num_display = None
                            if session_num is not None:
                                if total_sessions is not None and total_sessions > 0:
                                    # Convert 0-based to 1-based for display: "1 of 3"
                                    session_num_display = f"{session_num + 1} of {total_sessions}"
                                else:
                                    # Just show 1-based number: "1"
                                    session_num_display = str(session_num + 1)
                            logger.info(
                                f"Session info updated: type={session_type}, num={session_num_display}, name={session_name}"
                            )

            # Update state with session info if changed
            if (
                session_type != new_state.session_type
                or session_name != new_state.session_name
                or session_num != new_state.session_num
                or total_sessions
                != (new_state.total_sessions if hasattr(new_state, "total_sessions") else None)
            ):
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
                    total_sessions=total_sessions,
                    stream_extended_info=new_state.stream_extended_info,
                )

            # Update connection states
            event_log = get_event_log()

            # Log mode change only (not every cycle) - compare with new_state.mode, not current_state.mode
            if new_state.mode != current_state.mode:
                logger.info(
                    f"iRacing mode changed: {current_state.mode.value} -> {new_state.mode.value}"
                )
                # Add event for mode change to game modes
                if new_state.mode in (
                    DrivingMode.RACE,
                    DrivingMode.GARAGE,
                    DrivingMode.LOBBY,
                ):
                    await event_log.add_event(
                        "game_started",
                        f"Game started: {new_state.mode.value}",
                        {"mode": new_state.mode.value},
                    )
            metrics = get_metrics()

            # Only log connection changes if not in QUIT/RESTART mode (to avoid spam)
            # QUIT/RESTART are considered disconnected, so connection state changes during these modes are expected
            is_quit_or_restart = new_state.mode in (
                DrivingMode.QUIT,
                DrivingMode.RESTART,
            )

            if connected_iracing != current_state.connected_iracing:
                metrics.set_iracing_connected(connected_iracing)
                # Only log if not in QUIT/RESTART mode, or if transitioning TO connected (not FROM)
                if not is_quit_or_restart or connected_iracing:
                    if connected_iracing:
                        log_connection_restored(logger, "iRacing")
                        await event_log.add_event(
                            "connection_restored", "iRacing connection restored"
                        )
                    else:
                        log_connection_lost(logger, "iRacing")
                        await event_log.add_event("connection_lost", "iRacing connection lost")

            if connected_obs != current_state.connected_obs:
                metrics.set_obs_connected(connected_obs)
                if connected_obs:
                    log_connection_restored(logger, "OBS")
                    await event_log.add_event("connection_restored", "OBS connection restored")
                    # If we're in CONNECTING state and OBS just connected, switch to safe_scene
                    if new_state.mode == DrivingMode.CONNECTING and obs_client.is_connected():
                        obs_current = await obs_client.get_current_scene()
                        if new_state.target_scene != obs_current:
                            # Switch to safe_scene if not already on it
                            switch_start = now_ms()
                            success = await obs_client.set_scene(new_state.target_scene)
                            if success:
                                latency = now_ms() - switch_start
                                log_scene_switch(
                                    logger,
                                    new_state.target_scene,
                                    "obs_connected_safe_scene",
                                    latency_ms=latency,
                                )
                                metrics = get_metrics()
                                metrics.record_scene_switch(latency)
                                await event_log.add_event(
                                    "scene_switch",
                                    f"Scene switched to safe scene after OBS connection: {new_state.target_scene}",
                                    {
                                        "scene": new_state.target_scene,
                                        "reason": "obs_connected_safe_scene",
                                        "latency_ms": latency,
                                    },
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
                                    last_switch_ts=now_ms(),
                                    reason=new_state.reason,
                                    session_type=new_state.session_type,
                                    session_name=new_state.session_name,
                                    session_num=new_state.session_num,
                                )
                                set_current_state(new_state)
                else:
                    log_connection_lost(logger, "OBS")
                    await event_log.add_event("connection_lost", "OBS connection lost")
                    # Reset stream title tracking when OBS disconnects
                    last_stream_title = None
                    last_stream_selected = False
                    # Reconnect is owned solely by background_obs_connect task
            # When OBS is down, background_obs_connect owns reconnect (avoid dual connect races)

            # State machine already ticked above (with session info updated if needed)
            set_current_state(new_state)

            # Check stream selection status (without periodic title fetching)
            if connected_obs and obs_client.is_connected():
                try:
                    is_streaming, _ = await obs_client.get_stream_status()
                    is_selected, is_ready_selected = await obs_client.is_stream_selected()

                    # Update cache timestamp for auto-start logic
                    current_check_ts = now_ms()
                    last_stream_selection_check_ts = current_check_ts

                    # Apply hysteresis/debouncing to stream selection detection
                    # Require multiple consecutive readings to confirm change
                    if is_selected != last_stream_selected:
                        stream_selection_consecutive_readings += 1
                        if (
                            stream_selection_consecutive_readings
                            >= stream_selection_min_confirm_count
                        ):
                            # Confirmed change - process it
                            stream_selection_consecutive_readings = 0

                            if is_selected:
                                # Stream was selected - NOW fetch title (only when needed)
                                logger.info(
                                    f"Stream selected in OBS (streaming: {is_streaming}, ready: {is_ready_selected})"
                                )
                                try:
                                    # Use force_refresh=True to ensure we get fresh data from YouTube API
                                    # This is especially important if OAuth was already authenticated at startup
                                    stream_title, stream_description = (
                                        await obs_client.get_stream_info(force_refresh=True)
                                    )
                                    await event_log.add_event(
                                        "stream_selected",
                                        "Stream selected in OBS",
                                        {
                                            "is_streaming": is_streaming,
                                            "is_ready": is_ready_selected,
                                            "stream_title": stream_title,
                                        },
                                    )
                                    if stream_title:
                                        logger.info(f"Stream title detected: {stream_title}")
                                        last_stream_title = stream_title
                                except Exception as e:
                                    logger.warning(
                                        f"Failed to get stream info when stream selected: {e}"
                                    )
                                    await event_log.add_event(
                                        "stream_selected",
                                        "Stream selected in OBS",
                                        {
                                            "is_streaming": is_streaming,
                                            "is_ready": is_ready_selected,
                                            "stream_title": None,
                                        },
                                    )
                            else:
                                logger.info("Stream deselected in OBS")
                                await event_log.add_event(
                                    "stream_deselected", "Stream deselected in OBS", {}
                                )
                                last_stream_title = None
                            last_stream_selected = is_selected
                            last_stream_ready_selected = is_ready_selected
                        else:
                            # Still accumulating confirming readings
                            logger.debug(
                                f"Stream selection unstable: {is_selected} (reading {stream_selection_consecutive_readings}/{stream_selection_min_confirm_count})"
                            )
                    else:
                        # Same as last reading, reset counter
                        stream_selection_consecutive_readings = 0
                        last_stream_selected = is_selected
                        last_stream_ready_selected = is_ready_selected

                        # Check if stream is selected and OAuth is ready, but stream info is not loaded
                        # This handles the case where OAuth becomes ready after stream is already selected
                        # Only check once per stream selection to avoid infinite loop
                        if is_selected and is_ready_selected and not last_stream_title:
                            # Check if OAuth manager is set and authenticated
                            if (
                                obs_client._oauth_manager
                                and obs_client._oauth_manager.is_authenticated()
                            ):
                                # Check cached stream info first - if it exists, use it
                                cached_title, cached_desc, _, _ = (
                                    obs_client.get_cached_stream_info()
                                )
                                if cached_title:
                                    logger.info(f"Using cached stream title: {cached_title}")
                                    last_stream_title = cached_title
                                else:
                                    # OAuth is ready and stream is selected - fetch stream info
                                    logger.info(
                                        "Stream selected and OAuth ready - fetching stream info from YouTube API"
                                    )
                                    try:
                                        stream_title, stream_description = (
                                            await obs_client.get_stream_info(force_refresh=True)
                                        )
                                        if stream_title:
                                            logger.info(f"Stream title detected: {stream_title}")
                                            last_stream_title = stream_title
                                            await event_log.add_event(
                                                "stream_info_loaded",
                                                "Stream info loaded from YouTube API",
                                                {"stream_title": stream_title},
                                            )
                                        else:
                                            logger.debug(
                                                "Stream selected and OAuth ready, but stream title is None after API call"
                                            )
                                    except Exception as e:
                                        logger.warning(
                                            f"Failed to get stream info when OAuth ready: {e}",
                                            exc_info=True,
                                        )
                            else:
                                logger.debug(
                                    f"Stream selected but OAuth not ready (manager: {obs_client._oauth_manager is not None}, "
                                    f"authenticated: {obs_client._oauth_manager.is_authenticated() if obs_client._oauth_manager else False})"
                                )
                except Exception as e:
                    logger.debug(f"Failed to check stream selection: {e}")

            # Check if scene switch is needed
            if new_state.target_scene != new_state.current_scene:
                # Check if we should actually switch
                should_switch = True
                if not new_state.autoswitch and new_state.override_scene is None:
                    should_switch = False

                # Check if required OBS profile is active (if configured)
                if should_switch and config.required_profile:
                    current_profile = await obs_client.get_current_profile(use_cache=True)
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
                            {
                                "scene": new_state.target_scene,
                                "reason": new_state.reason,
                                "latency_ms": latency,
                            },
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
        backup_count=config.log_backup_count,
        use_colors=config.log_colors,
    )

    # Set global notifications flag
    set_notifications_enabled(config.notifications_enabled)
    logger.info(f"Notifications enabled: {config.notifications_enabled}")

    # Initialize i18n with configured language
    set_language(config.language)
    logger.info(f"Language set to: {config.language}")

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
    set_reader(reader)

    # Initialize OAuth manager
    # Try config file first, then fall back to environment variables
    oauth_manager = create_oauth_manager(
        client_id=config.oauth_client_id,
        client_secret=config.oauth_client_secret,
    )
    from irswitch.server.api import set_oauth_manager

    set_oauth_manager(oauth_manager)

    # Pass OAuth manager to OBS client for YouTube API access
    if oauth_manager:
        obs_client.set_oauth_manager(oauth_manager)

    # Initialize event log
    event_log = EventLog(max_size=config.dashboard_event_log_size)
    set_event_log(event_log)

    # Add application started event
    await event_log.add_event(
        "application_started", "Application started", {"config_path": config_path}
    )

    # Initialize metrics (will be used in main loop)
    metrics = get_metrics()
    # Set initial connection states
    metrics.set_iracing_connected(reader.is_connected())
    metrics.set_obs_connected(False)  # Will be updated after OBS connection attempt

    # Initial state
    logger.info(
        f"Initializing with safe_scene: {config.safe_scene}, scenes mapping: {dict(config.scenes)}"
    )
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
        stream_extended_info=None,
    )

    # Try to connect to OBS (non-blocking - don't wait too long on startup)
    # Use fewer retries and shorter timeout on startup so API server can start quickly
    try:
        await obs_client.connect(max_retries=1, initial_backoff=0.5)
        if obs_client.is_connected():
            # Log and event for successful OBS connection at startup
            log_connection_restored(logger, "OBS")
            await event_log.add_event("connection_restored", "OBS connection detected at startup")

            # If OAuth is already authenticated, check if stream is selected and refresh stream info
            if oauth_manager and oauth_manager.is_authenticated():
                logger.info(
                    "OAuth authenticated - checking stream selection and refreshing stream info"
                )
                try:
                    # Check if stream is selected
                    is_selected, is_ready_selected = await obs_client.is_stream_selected()
                    if is_selected and is_ready_selected:
                        logger.info(
                            "Stream selected and OAuth ready - refreshing stream info from YouTube API"
                        )
                        stream_title, stream_description = await obs_client.get_stream_info(
                            force_refresh=True
                        )
                        if stream_title:
                            logger.info(
                                f"Stream info refreshed from YouTube API after OBS connection: {stream_title}"
                            )
                        else:
                            logger.warning(
                                "Stream selected and OAuth ready, but stream title is None after refresh"
                            )
                    else:
                        logger.debug(
                            "Stream not selected yet - will refresh when stream is selected"
                        )
                except Exception as e:
                    logger.warning(
                        f"Failed to check stream selection or refresh stream info: {e}",
                        exc_info=True,
                    )

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
                else:
                    logger.info(
                        f"Scene validation passed. All {len(all_configured_scenes)} configured scenes exist in OBS."
                    )
                    logger.debug(f"Available OBS scenes: {', '.join(sorted(available_scenes))}")

            # Get current scene from OBS and switch to safe_scene if needed
            obs_current_scene = await obs_client.get_current_scene()
            if obs_current_scene is None:
                obs_current_scene = config.safe_scene
            if obs_current_scene != config.safe_scene:
                # Switch to safe_scene on startup
                logger.info(
                    f"Switching to safe scene on startup: {config.safe_scene} (current: {obs_current_scene})"
                )
                success = await obs_client.set_scene(config.safe_scene)
                if success:
                    obs_current_scene = config.safe_scene
                    logger.info(f"Switched to safe scene on startup: {config.safe_scene}")
                else:
                    logger.warning(
                        f"Failed to switch to safe scene on startup: {config.safe_scene}"
                    )

            initial_state = SwitchState(
                connected_iracing=initial_state.connected_iracing,
                connected_obs=True,
                autoswitch=initial_state.autoswitch,
                override_scene=initial_state.override_scene,
                override_until=initial_state.override_until,
                mode=initial_state.mode,
                target_scene=initial_state.target_scene,
                current_scene=obs_current_scene,  # Use actual OBS scene (should be safe_scene now)
                last_switch_ts=(
                    now_ms()
                    if obs_current_scene == config.safe_scene
                    else initial_state.last_switch_ts
                ),
                reason=initial_state.reason,
                session_type=initial_state.session_type,
                session_name=initial_state.session_name,
                session_num=initial_state.session_num,
                stream_extended_info=initial_state.stream_extended_info,
            )
            # Update metrics for OBS connection
            metrics.set_obs_connected(True)
        else:
            # Connection failed after retries (OBS never connected)
            # This shouldn't happen if connect() raises exception, but handle it anyway
            logger.warning(
                "Failed to connect to OBS on startup after retries. Will retry in main loop."
            )
    except Exception as e:
        logger.warning(f"Failed to connect to OBS on startup: {e}. Will retry in main loop.")

    # Set initial state BEFORE starting API server (so dashboards have state available)
    set_current_state(initial_state)
    logger.info(
        f"Initial state set: mode={initial_state.mode.value}, scene={initial_state.current_scene}, connected_obs={initial_state.connected_obs}, connected_iracing={initial_state.connected_iracing}"
    )

    # Create and start API server
    logger.info("Creating API server...")
    try:
        app = create_app()
        app[APP_CONFIG] = config  # Store config in app for dashboard access
        app[APP_CONFIG_PATH] = config_path  # type: ignore[misc]  # Store config path for hot reload

        # Also set config in API module's container for backward compatibility
        from irswitch.server.api import set_app_config

        set_app_config(config)

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
        logger.info(
            f"API server started successfully on http://{config.http_host}:{config.http_port}"
        )
    except OSError as e:
        error_str = str(e).lower()
        if (
            "address already in use" in error_str
            or "10048" in error_str
            or "address in use" in error_str
        ):
            logger.error(
                f"Port {config.http_port} is already in use. Please stop the other application or change the port in config.ini"
            )
        else:
            logger.error(f"Failed to start API server (OSError): {e}", exc_info=True)
        raise
    except Exception as e:
        logger.error(f"Failed to start API server: {e}", exc_info=True)
        raise

    # --- Automatic OAuth Flow ---
    await handle_oauth_flow(config)
    # --------------------------

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
                            log_connection_restored(logger, "OBS")
                            event_log_instance = get_event_log()
                            await event_log_instance.add_event(
                                "connection_restored",
                                "OBS connection restored via background task",
                            )
                            metrics.set_obs_connected(True)
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
                                    stream_extended_info=current.stream_extended_info,
                                )
                                set_current_state(new_state)
                    except Exception as e:
                        logger.debug(f"Background OBS connection attempt failed: {e}")
                    await asyncio.sleep(5.0)  # Backoff between reconnect attempts
                else:
                    # Connected: short poll so disconnect is noticed without dual main-loop reconnect
                    await asyncio.sleep(5.0)
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
