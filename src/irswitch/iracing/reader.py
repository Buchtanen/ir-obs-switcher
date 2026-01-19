"""Wrapper around pyirsdk shared memory reader."""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Iterable, Optional

import irsdk

from irswitch.iracing.extractors import extract_mode
from irswitch.models import DrivingMode

logger = logging.getLogger(__name__)


def _as_bool(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).lower() in {"1", "true", "yes", "on"}


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

    def startup(self) -> None:
        """Startup the SDK (synchronous, called once)."""
        self._sdk.startup()

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
        
        return bool(self._sdk.is_initialized)

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

    async def read_session_info(self) -> Optional[dict[str, object]]:
        """
        Read session information from iRacing (async).
        
        Returns:
            Dictionary with session info (SessionType, SessionName, SessionNum, etc.) or None if disconnected
        """
        if not self.is_connected():
            return None
        
        # Variables for session type detection
        session_var_names = [
            "SessionType",  # 0=test, 1=practice, 2=qualify, 3=warmup, 4=race
            "SessionName",  # Name of the session
            "SessionNum",   # Session number in weekend (0-based)
            "SessionTime", # Current session time
            "SessionState", # Session state string
            "SessionStateNum", # Session state number
        ]
        
        try:
            data = await asyncio.wait_for(
                asyncio.to_thread(self.read_vars, session_var_names),
                timeout=2.0
            )
            return data
        except Exception as e:
            logger.debug(f"Failed to read session info: {e}")
            return None

    async def read_mode(self) -> Optional[DrivingMode]:
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
            "SessionState",
            "SessionStateNum",
            "IsInCar",
            "PlayerCarIdx",
            "CamCarIdx",
            "CamCameraState",
            "SessionTime",
            "IsOnTrackSession",
            "SessionFlags",
        ]

        try:
            # Run synchronous read in thread to avoid blocking
            # Add timeout to prevent hanging if iRacing SDK blocks
            data = await asyncio.wait_for(
                asyncio.to_thread(self.read_vars, var_names),
                timeout=2.0  # 2 second timeout
            )

            session_state_num = data.get("SessionStateNum")
            session_time = data.get("SessionTime")
            cam_camera_state = data.get("CamCameraState")

            # Detect loading screen (SessionTime is empty list or None)
            # During loading, iRacing returns empty arrays instead of values
            # Return None to signal "loading" state - distinct from IDLE
            if session_time is None or (isinstance(session_time, list) and len(session_time) == 0):
                return None

            # Detect stalled session time (potential QUIT)
            if isinstance(session_time, (int, float)):
                now_ts = time.monotonic()
                is_session_screen = False
                if cam_camera_state is not None:
                    try:
                        cam_state = int(cam_camera_state)
                        # Bit 0: session screen (menu/UI)
                        is_session_screen = (cam_state & 0x01) != 0
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
                        if is_session_screen and not _as_bool(data.get("IsOnTrack")):
                            logger.debug(f"QUIT detected: SessionTime stalled for {stall_for:.1f}s")
                            return DrivingMode.QUIT

            # Check if we can actually read meaningful data
            # If all key variables are None, we're likely disconnected
            key_vars = ["IsReplay", "IsOnTrack", "SessionStateNum", "PlayerCarIdx"]
            all_none = all(data.get(var) is None for var in key_vars)
            if all_none:
                return None

            # Detect "no session" state (QUIT or not yet in session)
            no_session = (
                (session_time is None or session_time == 0.0) and
                (session_state_num is None or session_state_num == 0) and
                (cam_camera_state is None or cam_camera_state == 0) and
                not _as_bool(data.get("IsOnTrack")) and
                not _as_bool(data.get("IsOnTrackCar"))
            )
            if no_session:
                return None

            # If session state is 0 (invalid) and SessionTime is None, likely disconnected
            if session_state_num is not None:
                try:
                    state_num = int(session_state_num)
                    if state_num == 0 and session_time is None:
                        return None
                except (ValueError, TypeError):
                    pass
            
            mode = extract_mode(data)
            self._last_mode = mode
            return mode
        except asyncio.TimeoutError:
            logger.warning("read_mode() - timeout reading iRacing data, treating as disconnected")
            return None
        except Exception as e:
            logger.debug(f"read_mode() - exception: {e}", exc_info=True)
            return None
