"""Extraction helpers for iRacing telemetry data."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence

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


def _session_type_from_label(raw: object) -> str | None:
    """Map a session type / name / event string to Practice/Qualify/Race/Warmup/Test."""
    name = str(raw).strip().lower()
    if not name:
        return None
    if "practice" in name or name == "practise":
        return "Practice"
    if "qualify" in name:
        return "Qualify"
    if "race" in name:
        return "Race"
    if "warmup" in name:
        return "Warmup"
    if "test" in name:
        return "Test"
    return None


def _as_mapping(value: object) -> Mapping[str, object] | None:
    if isinstance(value, Mapping):
        return value
    if hasattr(value, "__dict__"):
        raw = getattr(value, "__dict__", None)
        if isinstance(raw, Mapping):
            return raw
    return None


def _session_row_from_session_info(data: Mapping[str, object]) -> Mapping[str, object] | None:
    """Current weekend session row: SessionInfo.Sessions[SessionNum]."""
    info = _as_mapping(data.get("SessionInfo"))
    if info is None:
        return None
    sessions = info.get("Sessions")
    if not isinstance(sessions, Sequence) or isinstance(sessions, (str, bytes)):
        return None
    session_num = as_int(data.get("SessionNum"))
    if session_num is None or session_num < 0 or session_num >= len(sessions):
        return None
    return _as_mapping(sessions[session_num])


def _coerce_session_type_value(raw: object) -> str | None:
    """Numeric legacy map or label string → Practice/Qualify/Race/…"""
    if raw is None:
        return None
    st = as_int(raw)
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
    return _session_type_from_label(raw)


def extract_session_type(data: Mapping[str, object]) -> str | None:
    """Extract current session type from iRacing SDK data.

    Prefer ``SessionInfo.Sessions[SessionNum].SessionType`` (YAML). There is no
    live ``SessionType`` telemetry var in modern irsdk; falling back to
    ``WeekendInfo.EventType`` mis-labels Practice/Qualify as Race on race
    weekends (sectors + session briefs break).
    """
    row = _session_row_from_session_info(data)
    if row is not None:
        for key in ("SessionType", "SessionName"):
            labeled = _coerce_session_type_value(row.get(key))
            if labeled:
                return labeled

    # Legacy / partial fixtures: top-level SessionType or SessionName.
    for key in ("SessionType", "SessionName"):
        labeled = _coerce_session_type_value(data.get(key))
        if labeled:
            return labeled

    # Do **not** use WeekendInfo.EventType — that is the weekend product
    # (often "Race"), not the active session.
    return None


def extract_session_name(data: Mapping[str, object]) -> str | None:
    """Display name of the active session row (not WeekendInfo.EventName)."""
    row = _session_row_from_session_info(data)
    if row is not None:
        for key in ("SessionName", "SessionType"):
            raw = row.get(key)
            if raw is None or raw == "":
                continue
            text = str(raw).strip()
            if text:
                return text
    raw = data.get("SessionName")
    if raw is None or raw == "":
        return None
    text = str(raw).strip()
    return text or None


def extract_session_fields(
    data: Mapping[str, object],
) -> tuple[str | None, str | None, int | None, int | None]:
    """session_type, session_name, session_num, total_sessions from one SDK mapping."""
    return (
        extract_session_type(data),
        extract_session_name(data),
        extract_session_num(data),
        extract_total_sessions(data),
    )


def resolve_session_identity(
    data: Mapping[str, object] | None,
    *,
    prev_type: str | None = None,
    prev_name: str | None = None,
    prev_num: int | None = None,
    prev_total: int | None = None,
) -> tuple[str | None, str | None, int | None, int | None]:
    """Map one SDK dump onto SwitchState session fields.

    Test sessions clear identity. A tick that extracts no session_type keeps
    previous values so a SessionNum-only dump cannot wipe Practice/Qualify/Race
    or invent Race from WeekendInfo.EventType.
    """
    if not data:
        return prev_type, prev_name, prev_num, prev_total
    session_type, session_name, session_num, total_sessions = extract_session_fields(data)
    if session_type == "Test":
        return None, None, None, None
    if session_type is None:
        return (
            prev_type,
            prev_name if session_name is None else session_name,
            prev_num if session_num is None else session_num,
            prev_total if total_sessions is None else total_sessions,
        )
    return session_type, session_name, session_num, total_sessions


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

    info = _as_mapping(data.get("SessionInfo"))
    if info is not None:
        sessions = info.get("Sessions")
        if isinstance(sessions, Sequence) and not isinstance(sessions, (str, bytes)) and sessions:
            return len(sessions)

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
