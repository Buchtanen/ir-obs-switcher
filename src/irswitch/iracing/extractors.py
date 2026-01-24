"""Extraction helpers for iRacing telemetry data."""
from __future__ import annotations

import logging
from typing import Mapping, Optional

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


def extract_mode(data: Mapping[str, object]) -> DrivingMode:
    """
    Extract driving mode from iRacing SDK data.
    
    Priority order: GARAGE > REPLAY > RACE > LOBBY
    Note: SETTINGS detection was removed - iRacing SDK doesn't report it reliably.
    Note: IDLE is deprecated, use LOBBY instead.
    """
    # Get all relevant variables
    is_replay = as_bool(data.get("IsReplay"))
    player_car_idx = data.get("PlayerCarIdx")
    cam_car_idx = data.get("CamCarIdx")
    cam_camera_state = data.get("CamCameraState")
    is_on_track = as_bool(data.get("IsOnTrack")) or as_bool(data.get("IsOnTrackCar"))
    is_in_garage = as_bool(data.get("PlayerCarInGarage")) or as_bool(data.get("IsInGarage"))
    
    # Determine if player is in car based on CamCameraState
    is_in_car = False
    if cam_camera_state is not None:
        try:
            cam_state = int(cam_camera_state)
            # Bit 0: session screen (menu/UI) - if set, not in car
            is_session_screen = (cam_state & 0x01) != 0
            is_in_car = not is_session_screen
        except (ValueError, TypeError):
            pass
    elif player_car_idx is not None:
        try:
            car_idx = int(player_car_idx)
            is_in_car = car_idx >= 0
        except (ValueError, TypeError):
            pass
    
    # Check camera mismatch (watching replay of other car)
    cam_mismatch = False
    if cam_car_idx is not None and player_car_idx is not None:
        try:
            cam_idx = int(cam_car_idx)
            player_idx = int(player_car_idx)
            cam_mismatch = cam_idx != player_idx
        except (ValueError, TypeError):
            pass

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


def extract_session_type(data: Mapping[str, object]) -> Optional[str]:
    """
    Extract session type from iRacing SDK data.
    
    Returns:
        Session type string: "Practice", "Qualify", "Race", "Warmup", "Test", or None
    """
    session_type = data.get("SessionType")
    session_name = data.get("SessionName")
    
    # Try SessionType first (numeric: 0=test, 1=practice, 2=qualify, 3=warmup, 4=race)
    if session_type is not None:
        try:
            st = int(session_type)
            type_map = {
                0: "Test",
                1: "Practice",
                2: "Qualify",
                3: "Warmup",
                4: "Race",
            }
            if st in type_map:
                result = type_map[st]
                return result
        except (ValueError, TypeError):
            pass
    
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
        elif hasattr(weekend_info, '__dict__'):
            event_type = weekend_info.__dict__.get("EventType")
        elif hasattr(weekend_info, 'EventType'):
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


def extract_session_num(data: Mapping[str, object]) -> Optional[int]:
    """
    Extract session number from iRacing SDK data.
    
    Returns:
        Session number (0-based) or None
    """
    session_num = data.get("SessionNum")
    if session_num is not None:
        try:
            result = int(session_num)
            # Return 0-based value (iRacing SDK uses 0-based indexing)
            # Conversion to 1-based for display happens in main.py
            return result
        except (ValueError, TypeError):
            pass
    return None


def extract_total_sessions(data: Mapping[str, object]) -> Optional[int]:
    """
    Extract total number of sessions from iRacing SDK data.
    
    Tries to get from WeekendInfo if available, otherwise returns None.
    
    Returns:
        Total number of sessions or None if not available
    """
    
    # Try SessionTotalSessions first (direct field from iRacing)
    if "SessionTotalSessions" in data:
        try:
            result = int(data["SessionTotalSessions"])
            return result
        except (ValueError, TypeError):
            pass
    
    # Try WeekendInfo first (if it's a dict/object with sessions)
    weekend_info = data.get("WeekendInfo")
    if weekend_info is not None:
        # WeekendInfo might be a dict-like object
        if isinstance(weekend_info, dict):
            # Try common field names
            for field in ["NumSessions", "SessionCount", "TotalSessions", "n_sessions"]:
                if field in weekend_info:
                    try:
                        result = int(weekend_info[field])
                        return result
                    except (ValueError, TypeError):
                        pass
            # Try to get length of sessions array if it exists
            if "Sessions" in weekend_info:
                sessions = weekend_info["Sessions"]
                if isinstance(sessions, (list, tuple)):
                    result = len(sessions)
                    return result
    
    # Try direct fields in data
    for field in ["NumSessions", "SessionCount", "TotalSessions", "n_sessions"]:
        if field in data:
            try:
                result = int(data[field])
                return result
            except (ValueError, TypeError):
                pass
    return None