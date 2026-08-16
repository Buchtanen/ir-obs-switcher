"""Extraction helpers for iRacing telemetry data."""

from __future__ import annotations

import logging
from collections.abc import Mapping

from irswitch.models import DrivingMode

logger = logging.getLogger(__name__)


def as_bool(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).lower() in {"1", "true", "yes", "on"}


def as_int(value: object) -> int | None:
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


def optional_bool(data: Mapping[str, object], key: str) -> bool | None:
    """Return bool flag when the key is present; None if missing."""
    if key not in data:
        return None
    value = data.get(key)
    if value is None:
        return None
    return as_bool(value)


def extract_mode(data: Mapping[str, object]) -> DrivingMode:
    """
    Extract driving mode from iRacing SDK data.

    Priority order: GARAGE > REPLAY > RACE > LOBBY
    Note: SETTINGS detection was removed - iRacing SDK doesn't report it reliably.
    Note: IDLE is deprecated, use LOBBY instead.

    GARAGE uses IsGarageVisible (garage UI). IsInGarage / PlayerCarInGarage only
    mean car physics are running in the stall — that is also true in the lobby
    after loading, so they are not sufficient on their own.
    """
    # Get all relevant variables
    is_replay = as_bool(data.get("IsReplay"))
    player_car_idx = data.get("PlayerCarIdx")
    cam_car_idx = data.get("CamCarIdx")
    cam_camera_state = data.get("CamCameraState")
    is_on_track = as_bool(data.get("IsOnTrack")) or as_bool(data.get("IsOnTrackCar"))
    garage_visible = optional_bool(data, "IsGarageVisible")

    # Determine if player is in car based on CamCameraState
    is_in_car = False
    is_session_screen = False
    cam_state = as_int(cam_camera_state)
    if cam_state is not None:
        # Bit 0: session screen (menu/UI) - if set, not in car
        is_session_screen = (cam_state & 0x01) != 0
        is_in_car = not is_session_screen
    else:
        car_idx = as_int(player_car_idx)
        if car_idx is not None:
            is_in_car = car_idx >= 0

    if garage_visible is True:
        is_in_garage = True
    elif garage_visible is False:
        is_in_garage = False
    else:
        # Older/partial snapshots: stall physics plus not on session screen
        car_in_stall = as_bool(data.get("PlayerCarInGarage")) or as_bool(data.get("IsInGarage"))
        is_in_garage = car_in_stall and not is_session_screen

    # Check camera mismatch (watching replay of other car)
    cam_mismatch = False
    if cam_car_idx is not None and player_car_idx is not None:
        cam_idx = as_int(cam_car_idx)
        player_idx = as_int(player_car_idx)
        if cam_idx is not None and player_idx is not None:
            cam_mismatch = cam_idx != player_idx

    # Decide mode - Priority order: GARAGE > REPLAY > RACE > LOBBY
    mode = DrivingMode.LOBBY
    if is_in_garage:
        mode = DrivingMode.GARAGE
    elif is_replay:
        mode = DrivingMode.REPLAY
    elif cam_mismatch:
        mode = DrivingMode.REPLAY
    elif is_on_track and not is_in_car:
        mode = DrivingMode.REPLAY
    elif is_on_track and is_in_car:
        mode = DrivingMode.RACE

    return mode


def extract_session_type(data: Mapping[str, object]) -> str | None:
    """
    Extract session type from iRacing SDK data.

    Returns:
        Session type string: "Practice", "Qualify", "Race", "Warmup", "Test", or None
    """
    session_type = data.get("SessionType")
    session_name = data.get("SessionName")
    result: str | None = None

    # Try SessionType first (numeric: 0=test, 1=practice, 2=qualify, 3=warmup, 4=race)
    if session_type is not None:
        st = as_int(session_type)
        if st is not None:
            type_map = {
                0: "Test",
                1: "Practice",
                2: "Qualify",
                3: "Warmup",
                4: "Race",
            }
            if st in type_map:
                return type_map[st]

    # Fallback: try to parse SessionName
    if session_name is not None:
        name = str(session_name).lower()
        if "practice" in name:
            result = "Practice"
        elif "qualify" in name or "qualifying" in name:
            result = "Qualify"
        elif "race" in name:
            result = "Race"
        elif "warmup" in name:
            result = "Warmup"
        elif "test" in name:
            result = "Test"
        else:
            result = None

        if result:
            return result

    # Try WeekendInfo.EventType as fallback
    weekend_info = data.get("WeekendInfo")
    if weekend_info is not None:
        if isinstance(weekend_info, dict):
            event_type = weekend_info.get("EventType")
        elif hasattr(weekend_info, "__dict__"):
            event_type = weekend_info.__dict__.get("EventType")
        elif hasattr(weekend_info, "EventType"):
            event_type = weekend_info.EventType
        else:
            event_type = None

        if event_type is not None:
            event_type_str = str(event_type)
            # Map common event types
            if event_type_str.lower() in ["practice", "practise"]:
                result = "Practice"
            elif event_type_str.lower() in ["qualify", "qualifying"]:
                result = "Qualify"
            elif event_type_str.lower() == "race":
                result = "Race"
            elif event_type_str.lower() == "warmup":
                result = "Warmup"
            elif event_type_str.lower() == "test":
                result = "Test"
            else:
                result = event_type_str  # Return as-is if not recognized

            if result:
                return result

    return None


def extract_session_num(data: Mapping[str, object]) -> int | None:
    """
    Extract session number from iRacing SDK data.

    Returns:
        Session number (0-based) or None
    """
    session_num = data.get("SessionNum")
    if session_num is not None:
        value = as_int(session_num)
        if value is not None:
            # Return 0-based value (iRacing SDK uses 0-based indexing)
            # Conversion to 1-based for display happens in main.py
            return value
    return None


def extract_total_sessions(data: Mapping[str, object]) -> int | None:
    """
    Extract total number of sessions from iRacing SDK data.

    Tries to get from WeekendInfo if available, otherwise returns None.

    Returns:
        Total number of sessions or None if not available
    """

    # Try SessionTotalSessions first (direct field from iRacing)
    if "SessionTotalSessions" in data:
        value = as_int(data.get("SessionTotalSessions"))
        if value is not None:
            return value

    # Try WeekendInfo first (if it's a dict/object with sessions)
    weekend_info = data.get("WeekendInfo")
    if weekend_info is not None:
        # WeekendInfo might be a dict-like object
        if isinstance(weekend_info, dict):
            # Try common field names
            for field in ["NumSessions", "SessionCount", "TotalSessions", "n_sessions"]:
                if field in weekend_info:
                    value = as_int(weekend_info.get(field))
                    if value is not None:
                        return value
            # Try to get length of sessions array if it exists
            if "Sessions" in weekend_info:
                sessions = weekend_info["Sessions"]
                if isinstance(sessions, (list, tuple)):
                    result = len(sessions)
                    return result

    # Try direct fields in data
    for field in ["NumSessions", "SessionCount", "TotalSessions", "n_sessions"]:
        if field in data:
            value = as_int(data.get(field))
            if value is not None:
                return value
    return None
