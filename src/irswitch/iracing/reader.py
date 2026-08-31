"""Wrapper around pyirsdk shared memory reader."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Iterable

import irsdk

from irswitch.iracing.extractors import as_bool, extract_mode
from irswitch.iracing.telemetry import TELEMETRY_VARS, extract_telemetry
from irswitch.models import DrivingMode
from irswitch.overlay.models import TelemetrySnapshot

logger = logging.getLogger(__name__)

# YAML weekend row lives here. Live telemetry has no SessionType var in modern irsdk.
SESSION_INFO_VARS: tuple[str, ...] = (
    "SessionType",
    "SessionName",
    "SessionNum",
    "SessionTotalSessions",
    "SessionTime",
    "SessionState",
    "SessionStateNum",
    "WeekendInfo",
    "SessionInfo",
)


def _as_int(value: object) -> int | None:
    """Best-effort conversion of SDK values to int."""
    if value is None:
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    try:
        return int(str(value))
    except ValueError:
        return None


def is_iracing_process_running() -> bool:
    """
    Check if iRacing process is running (iRacingSim64DX11.exe).

    This can detect iRacing even during loading screen when SDK is not yet connected.

    Returns:
        True if iRacing process is running, False otherwise
    """
    try:
        import subprocess
        import sys

        # On Windows, prevent subprocess from creating a console window
        # This is important when running as --noconsole EXE
        startupinfo = None
        if sys.platform == "win32":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = subprocess.SW_HIDE
            # Also use CREATE_NO_WINDOW flag to prevent console window
            creationflags = subprocess.CREATE_NO_WINDOW
        else:
            creationflags = 0

        # Use tasklist to check for iRacing process (Windows)
        result = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq iRacingSim64DX11.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=2,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )
        # If process is found, tasklist returns the process info
        # If not found, it returns "INFO: No tasks are running..."
        return "iRacingSim64DX11.exe" in result.stdout
    except Exception as e:
        logger.debug(f"Failed to check iRacing process: {e}")
        return False


class IRacingReader:
    """Async wrapper for pyirsdk shared memory reader."""

    def __init__(self, poll_hz: int, quit_stall_seconds: float) -> None:
        """
        Initialize iRacing reader.

        Args:
            poll_hz: Polling frequency in Hz
            quit_stall_seconds: Seconds of SessionTime stall before QUIT is detected
        """
        self.poll_hz = poll_hz
        self._sdk = irsdk.IRSDK()
        self._last_session_time: float | None = None
        self._last_session_change_ts: float | None = None
        self._quit_stall_seconds = quit_stall_seconds
        self._last_mode: DrivingMode | None = None
        self._last_session_state: int | None = None
        self._last_session_time_value: float | None = None
        # Cache for process detection (check only once per second to reduce system load)
        self._process_running_cache: bool | None = None
        self._process_running_cache_ts: float | None = None
        self._process_check_interval_s = 1.0  # Check process status max once per second
        # Raw SDK mapping from the latest successful telemetry read (session briefs).
        self._last_telemetry_data: dict[str, object] = {}

    def startup(self) -> None:
        """Startup the SDK (synchronous, called once)."""
        self._sdk.startup()

    def is_process_running(self) -> bool:
        """
        Check if iRacing process is running.

        This detects iRacing even during loading screen when SDK is not connected.
        Uses caching to reduce system load - checks max once per second.

        Returns:
            True if iRacing process is running, False otherwise
        """
        import time

        now = time.monotonic()

        # Use cache if it's still valid (less than 1 second old)
        if (
            self._process_running_cache is not None
            and self._process_running_cache_ts is not None
            and now - self._process_running_cache_ts < self._process_check_interval_s
        ):
            return self._process_running_cache

        # Cache expired or not set - check process
        result = is_iracing_process_running()
        self._process_running_cache = result
        self._process_running_cache_ts = now
        return result

    def is_connected(self) -> bool:
        """Check if iRacing is connected."""
        # pyirsdk may need periodic refresh to detect new connections
        # Try calling startup() again if not initialized - some SDK versions need this
        if not self._sdk.is_initialized:
            # Try to refresh SDK state by calling startup again
            # This is safe - startup() can be called multiple times
            try:
                self._sdk.startup()
            except Exception:
                pass

        is_initialized = bool(self._sdk.is_initialized)
        # CRITICAL FIX: Use is_connected property, not is_initialized
        # is_initialized only means shared memory exists (can persist after iRacing quits)
        # is_connected checks if iRacing process is actually running
        is_connected_real = is_initialized and bool(self._sdk.is_connected)
        return is_connected_real

    def read_vars(self, names: Iterable[str]) -> dict[str, object]:
        """
        Read variables from iRacing SDK (synchronous).

        Args:
            names: Variable names to read

        Returns:
            Dictionary mapping variable names to values
        """
        result: dict[str, object] = {}
        for name in names:
            try:
                value = self._sdk[name]
                result[name] = value
            except (KeyError, AttributeError):
                # Variable not available - expected when iRacing is disconnected
                # or variable doesn't exist
                result[name] = None
        return result

    def get_all_vars(self) -> dict[str, object]:
        """
        Get all available variables from iRacing SDK (synchronous).

        Returns:
            Dictionary mapping all available variable names to values
        """
        if not self.is_connected():
            return {}

        result: dict[str, object] = {}
        try:
            # Try to get all variables by iterating through SDK
            # pyirsdk may have different ways to access all vars
            # Try common approaches
            if hasattr(self._sdk, "var_dict"):
                # Some SDK versions expose var_dict
                for name, _var in self._sdk.var_dict.items():
                    try:
                        result[name] = self._sdk[name]
                    except (KeyError, AttributeError):
                        pass
            elif hasattr(self._sdk, "__iter__"):
                # Try iterating SDK object
                for name in self._sdk:
                    try:
                        result[name] = self._sdk[name]
                    except (KeyError, AttributeError):
                        pass
            else:
                # Fallback: try to access common variable names
                # This is a limited approach but better than nothing
                common_vars = [
                    "SessionTime",
                    "SessionState",
                    "SessionStateNum",
                    "SessionType",
                    "SessionName",
                    "SessionNum",
                    "SessionTotalSessions",
                    "IsReplay",
                    "IsOnTrack",
                    "IsOnTrackCar",
                    "PlayerCarInGarage",
                    "IsInGarage",
                    "IsGarageVisible",
                    "IsInCar",
                    "PlayerCarIdx",
                    "CamCarIdx",
                    "CamCameraState",
                    "IsOnTrackSession",
                    "SessionFlags",
                    "Speed",
                    "CarIdxBestLapTime",
                    "CarIdxLastLapTime",
                    "WeekendInfo",
                    "SessionInfo",
                ]
                for name in common_vars:
                    try:
                        result[name] = self._sdk[name]
                    except (KeyError, AttributeError):
                        result[name] = None
        except Exception as e:
            logger.debug(f"Failed to get all vars: {e}")

        return result

    async def read_session_info(self) -> dict[str, object] | None:
        """
        Read session information from iRacing (async).

        Returns:
            Dictionary with session info (SessionType, SessionName, SessionNum, etc.) or None if disconnected
        """
        if not self.is_connected():
            return None

        # Variables for session type detection. SessionType is legacy; current
        # session is SessionInfo.Sessions[SessionNum] (YAML).
        session_var_names = list(SESSION_INFO_VARS)

        try:
            data = await asyncio.wait_for(
                asyncio.to_thread(self.read_vars, session_var_names), timeout=2.0
            )
            return data
        except Exception as e:
            logger.debug(f"Failed to read session info: {e}")
            return None

    async def read_mode(self) -> DrivingMode | None:
        """
        Read and extract driving mode from iRacing (async).

        Returns:
            DrivingMode or None if iRacing is disconnected
        """
        # Check connection before reading
        if not self.is_connected():
            return None

        # Variables needed for mode detection
        var_names = [
            "IsReplay",
            "IsOnTrack",
            "IsOnTrackCar",
            "PlayerCarInGarage",
            "IsInGarage",
            "IsGarageVisible",
            "SessionState",
            "SessionStateNum",
            "IsInCar",
            "PlayerCarIdx",
            "CamCarIdx",
            "CamCameraState",
            "SessionTime",
            "IsOnTrackSession",
            "SessionFlags",
            "Speed",
        ]

        try:
            # Run synchronous read in thread to avoid blocking
            # Add timeout to prevent hanging if iRacing SDK blocks
            data = await asyncio.wait_for(
                asyncio.to_thread(self.read_vars, var_names),
                timeout=2.0,  # 2 second timeout
            )

            session_state_num = data.get("SessionStateNum")
            session_time = data.get("SessionTime")
            cam_camera_state = data.get("CamCameraState")
            session_state = data.get("SessionState")
            session_state_int = _as_int(session_state)

            # Detect loading screen using multiple indicators (based on iRacing SDK documentation):
            # 1. SessionTime is None or empty list (legacy check) - telemetry not available yet
            # 2. SessionState is 0 (irsdk_StateInvalid) - indicates loading/invalid state
            #    According to docs: "SessionState=0 (Invalid) usually means sim hasn't finished loading and no session is running"
            #    Note: SessionStateNum is not available in SDK, use SessionState instead
            # 3. SessionTime is 0.0 and SessionState is 0 (initial loading state)
            # 4. SDK is not connected (telemetry file doesn't exist or is not available) - loading screen
            # 5. Transition to loading: SessionState changed from non-0 to 0 (detecting loading screen during session transition)
            # 6. Transition to loading: SessionTime changed from non-0 to 0.0 (detecting loading screen during session transition)
            is_loading_by_time = session_time is None or (
                isinstance(session_time, list) and len(session_time) == 0
            )
            is_loading_by_state = (
                session_state_int == 0 if session_state_int is not None else False
            )  # irsdk_StateInvalid = loading/lobby
            is_loading_by_initial = (
                isinstance(session_time, (int, float))
                and abs(float(session_time)) < 0.001
                and session_state_int == 0
            )
            is_loading_by_sdk_unavailable = (
                not self.is_connected()
            )  # SDK not ready = loading screen

            # Detect transition to loading: SessionState changed from non-0 to 0
            # Also detect if we're transitioning from a running session (state 4) to loading (state 0)
            is_loading_by_state_transition = False
            if session_state_int is not None:
                if session_state_int == 0:
                    # Loading state detected - check if we transitioned from a non-loading state
                    if self._last_session_state is not None and self._last_session_state != 0:
                        is_loading_by_state_transition = True
                # Always update last_session_state (even if None, to track first connection)
                self._last_session_state = session_state_int

            # Detect transition to loading: SessionTime changed from non-0 to 0.0
            # Also detect if we're transitioning from a running session (high time) to loading (0.0)
            is_loading_by_time_transition = False
            if isinstance(session_time, (int, float)):
                session_time_float = float(session_time)
                if abs(session_time_float) < 0.001:
                    # Loading time detected - check if we transitioned from a non-loading time
                    if (
                        self._last_session_time_value is not None
                        and abs(self._last_session_time_value) >= 0.001
                    ):
                        is_loading_by_time_transition = True
                # Always update last_session_time_value (even if None, to track first connection)
                self._last_session_time_value = session_time_float
            elif session_time is None:
                # SessionTime is None - this is also a loading indicator
                # Check if we transitioned from a non-None value
                if self._last_session_time_value is not None:
                    is_loading_by_time_transition = True
                self._last_session_time_value = None

            if (
                is_loading_by_time
                or is_loading_by_state
                or is_loading_by_initial
                or is_loading_by_sdk_unavailable
                or is_loading_by_state_transition
                or is_loading_by_time_transition
            ):
                return None

            # Detect stalled session time (potential QUIT)
            if isinstance(session_time, (int, float)):
                now_ts = time.monotonic()
                is_session_screen = False
                if cam_camera_state is not None:
                    try:
                        cam_state_int = _as_int(cam_camera_state)
                        if cam_state_int is None:
                            raise ValueError("CamCameraState not int-like")
                        # Bit 0: session screen (menu/UI)
                        is_session_screen = (cam_state_int & 0x01) != 0
                    except (ValueError, TypeError):
                        pass

                if self._last_session_time is None or session_time != self._last_session_time:
                    self._last_session_time = float(session_time)
                    self._last_session_change_ts = now_ts
                else:
                    if self._last_session_change_ts is None:
                        self._last_session_change_ts = now_ts
                    stall_for = now_ts - self._last_session_change_ts
                    if stall_for >= self._quit_stall_seconds:
                        # IsOnTrackCar may stay true (cached) after game exit, so only check IsOnTrack
                        # CRITICAL: Don't detect QUIT if session_state is 4 (active session)
                        # In LOBBY, SessionTime can be constant but session_state is still 4
                        session_state_active = session_state_int == 4
                        if (
                            is_session_screen
                            and not as_bool(data.get("IsOnTrack"))
                            and not session_state_active
                        ):
                            logger.debug(f"QUIT detected: SessionTime stalled for {stall_for:.1f}s")
                            return DrivingMode.QUIT

            # Check if we can actually read meaningful data
            # If all key variables are None, we're likely disconnected
            key_vars = ["IsReplay", "IsOnTrack", "SessionStateNum", "PlayerCarIdx"]
            all_none = all(data.get(var) is None for var in key_vars)
            if all_none:
                return None

            # Detect "no session" state (QUIT or not yet in session)
            # BUT: if SessionState is 0, this is likely loading screen, not QUIT
            # So we should return None for loading screen, not continue to QUIT detection
            no_session = (
                (
                    session_time is None
                    or (isinstance(session_time, (int, float)) and abs(float(session_time)) < 0.001)
                )
                and (session_state_num is None or session_state_num == 0)
                and (cam_camera_state is None or cam_camera_state == 0)
                and not as_bool(data.get("IsOnTrack"))
                and not as_bool(data.get("IsOnTrackCar"))
            )
            # If SessionState is 0, this is loading screen, not QUIT
            # Return None to indicate loading screen
            if no_session:
                return None

            # If session state is 0 (invalid) and SessionTime is None, likely disconnected
            if session_state_num is not None:
                try:
                    state_num = _as_int(session_state_num)
                    if state_num is None:
                        raise ValueError("SessionStateNum not int-like")
                    if state_num == 0 and session_time is None:
                        return None
                except (ValueError, TypeError):
                    pass

            mode = extract_mode(data)
            self._last_mode = mode
            return mode
        except TimeoutError:
            logger.warning("read_mode() - timeout reading iRacing data, treating as disconnected")
            return None
        except Exception as e:
            logger.debug(f"read_mode() - exception: {e}", exc_info=True)
            return None

    def last_telemetry_data(self) -> dict[str, object]:
        """Copy of the raw var dict from the last successful ``read_telemetry``."""
        return dict(self._last_telemetry_data)

    def session_sdk_payload(self) -> dict[str, object]:
        """Telemetry dump when YAML SessionInfo is already in the overlay cache.

        ``SessionNum`` alone is not identity — live irsdk has no SessionType var.
        Empty when overlay has not read YAML yet — caller should ``read_session_info``.
        """
        cached = self.last_telemetry_data()
        if cached.get("SessionInfo") is not None:
            return cached
        return {}

    async def read_telemetry(self) -> TelemetrySnapshot:
        """
        Read overlay telemetry vars. Extraction only — no race logic.

        Returns a disconnected snapshot when iRacing is down. Never raises
        to the caller except CancelledError.
        """
        now = time.monotonic()
        if not self.is_connected():
            self._last_telemetry_data = {}
            return TelemetrySnapshot.disconnected(now)
        try:
            data = await asyncio.wait_for(
                asyncio.to_thread(self.read_vars, TELEMETRY_VARS),
                timeout=2.0,
            )
            self._last_telemetry_data = dict(data) if data else {}
            return extract_telemetry(data, now)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.debug("read_telemetry() failed", exc_info=True)
            self._last_telemetry_data = {}
            return TelemetrySnapshot.disconnected(now)
