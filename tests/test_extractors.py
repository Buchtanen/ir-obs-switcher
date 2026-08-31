"""Tests for iRacing data extractors."""

from irswitch.iracing.extractors import (
    extract_mode,
    extract_session_fields,
    extract_session_name,
    extract_session_num,
    extract_session_type,
    extract_total_sessions,
    resolve_session_identity,
)
from irswitch.models import DrivingMode


def test_extract_mode_prioritizes_replay() -> None:
    """Test that REPLAY has high priority, but GARAGE overrides it."""
    data = {
        "IsReplay": True,
        "IsOnTrack": True,
        "IsGarageVisible": True,
    }
    # GARAGE has highest priority, overrides REPLAY
    assert extract_mode(data) == DrivingMode.GARAGE


def test_extract_mode_race_when_on_track() -> None:
    """Test RACE mode when on track and in car."""
    # Need to be in car (CamCameraState bit 0 = 0 means in car)
    data = {"IsOnTrack": 1, "CamCameraState": 2}  # Bit 0 = 0, so in car
    assert extract_mode(data) == DrivingMode.RACE


def test_extract_mode_garage_when_garage_visible() -> None:
    """Test GARAGE mode when garage screen is visible."""
    data = {"IsGarageVisible": "true"}
    assert extract_mode(data) == DrivingMode.GARAGE


def test_extract_mode_in_garage_physics_without_screen_is_lobby() -> None:
    """Car-in-stall physics is not garage when the garage UI is hidden."""
    data = {
        "IsInGarage": True,
        "PlayerCarInGarage": True,
        "IsGarageVisible": False,
    }
    assert extract_mode(data) == DrivingMode.LOBBY


def test_extract_mode_session_screen_with_stall_physics_is_lobby() -> None:
    """GetInCar/lobby: stall physics plus session screen must stay LOBBY."""
    data = {
        "IsInGarage": True,
        "PlayerCarInGarage": True,
        "CamCameraState": 1,  # bit 0 = session screen
    }
    assert extract_mode(data) == DrivingMode.LOBBY


def test_extract_mode_garage_fallback_without_visible_flag() -> None:
    """When IsGarageVisible is absent, stall physics without session screen is GARAGE."""
    data = {"PlayerCarInGarage": "true"}
    assert extract_mode(data) == DrivingMode.GARAGE


def test_extract_mode_lobby_by_default() -> None:
    """Test LOBBY mode as default (IDLE is deprecated)."""
    assert extract_mode({}) == DrivingMode.LOBBY


def test_extract_mode_replay_overrides_race() -> None:
    """Test that REPLAY overrides RACE when IsReplay is True."""
    data = {"IsReplay": True, "IsOnTrack": 1, "CamCameraState": 2}
    assert extract_mode(data) == DrivingMode.REPLAY


def test_extract_mode_garage_overrides_replay() -> None:
    """Test that GARAGE overrides REPLAY."""
    data = {"IsReplay": True, "IsGarageVisible": True}
    assert extract_mode(data) == DrivingMode.GARAGE


def test_extract_mode_camera_mismatch_is_replay() -> None:
    """Test that watching different car is REPLAY mode."""
    data = {"CamCarIdx": 1, "PlayerCarIdx": 0, "CamCameraState": 2}
    assert extract_mode(data) == DrivingMode.REPLAY


def test_extract_mode_not_on_track_is_lobby() -> None:
    """Test LOBBY when not on track."""
    data = {"IsOnTrack": 0}
    assert extract_mode(data) == DrivingMode.LOBBY


def test_extract_session_type_from_numeric() -> None:
    """Test extracting session type from numeric SessionType."""
    # Practice (1)
    data = {"SessionType": 1}
    assert extract_session_type(data) == "Practice"

    # Qualify (2)
    data = {"SessionType": 2}
    assert extract_session_type(data) == "Qualify"

    # Race (4)
    data = {"SessionType": 4}
    assert extract_session_type(data) == "Race"

    # Warmup (3)
    data = {"SessionType": 3}
    assert extract_session_type(data) == "Warmup"

    # Test (0) - returns "Test" but should be filtered out in main.py
    data = {"SessionType": 0}
    assert extract_session_type(data) == "Test"


def test_extract_session_type_from_string_session_type() -> None:
    """YAML / pyirsdk often expose SessionType as Practice/Qualify/Race text."""
    assert extract_session_type({"SessionType": "Practice"}) == "Practice"
    assert extract_session_type({"SessionType": "Qualify"}) == "Qualify"
    assert extract_session_type({"SessionType": "Race"}) == "Race"
    assert extract_session_type({"SessionType": "Lone Qualify"}) == "Qualify"


def test_extract_session_type_from_session_name() -> None:
    """Test extracting session type from SessionName string."""
    data = {"SessionName": "Practice Session"}
    assert extract_session_type(data) == "Practice"

    data = {"SessionName": "Qualifying Session"}
    assert extract_session_type(data) == "Qualify"

    data = {"SessionName": "Race Session"}
    assert extract_session_type(data) == "Race"

    data = {"SessionName": "Warmup Session"}
    assert extract_session_type(data) == "Warmup"


def test_extract_session_type_from_session_info_row() -> None:
    """Live path: SessionInfo.Sessions[SessionNum], not WeekendInfo.EventType."""
    data = {
        "SessionNum": 1,
        "WeekendInfo": {"EventType": "Race"},
        "SessionInfo": {
            "Sessions": [
                {"SessionType": "Practice", "SessionName": "PRACTICE"},
                {"SessionType": "Lone Qualify", "SessionName": "QUALIFY"},
                {"SessionType": "Race", "SessionName": "RACE"},
            ]
        },
    }
    assert extract_session_type(data) == "Qualify"


def test_extract_session_type_follows_session_num_on_race_weekend() -> None:
    """Switcher chapters need Practice→Qualify→Race from SessionNum, not EventType."""
    weekend = {
        "WeekendInfo": {"EventType": "Race"},
        "SessionInfo": {
            "Sessions": [
                {"SessionType": "Practice", "SessionName": "PRACTICE"},
                {"SessionType": "Lone Qualify", "SessionName": "QUALIFY"},
                {"SessionType": "Race", "SessionName": "RACE"},
            ]
        },
    }
    assert extract_session_type({**weekend, "SessionNum": 0}) == "Practice"
    assert extract_session_type({**weekend, "SessionNum": 1}) == "Qualify"
    assert extract_session_type({**weekend, "SessionNum": 2}) == "Race"


def test_extract_session_type_ignores_event_type_without_session_info() -> None:
    data = {"SessionNum": 1, "WeekendInfo": {"EventType": "Race"}}
    assert extract_session_type(data) is None
    kept = resolve_session_identity(
        data,
        prev_type="Qualify",
        prev_name="QUALIFY",
        prev_num=1,
        prev_total=3,
    )
    assert kept == ("Qualify", "QUALIFY", 1, 3)


def test_extract_session_name_prefers_session_info_row() -> None:
    data = {
        "SessionNum": 1,
        "SessionName": None,
        "WeekendInfo": {"EventName": "Okayama International Raceway"},
        "SessionInfo": {
            "Sessions": [
                {"SessionType": "Practice", "SessionName": "PRACTICE"},
                {"SessionType": "Lone Qualify", "SessionName": "QUALIFY"},
            ]
        },
    }
    assert extract_session_name(data) == "QUALIFY"


def test_extract_total_sessions_from_session_info_rows() -> None:
    data = {
        "SessionInfo": {
            "Sessions": [
                {"SessionType": "Practice"},
                {"SessionType": "Qualify"},
                {"SessionType": "Race"},
            ]
        }
    }
    assert extract_total_sessions(data) == 3


def test_extract_session_fields_from_session_info_row() -> None:
    data = {
        "SessionNum": 1,
        "WeekendInfo": {"EventType": "Race", "EventName": "Okayama"},
        "SessionInfo": {
            "Sessions": [
                {"SessionType": "Practice", "SessionName": "PRACTICE"},
                {"SessionType": "Lone Qualify", "SessionName": "QUALIFY"},
                {"SessionType": "Race", "SessionName": "RACE"},
            ]
        },
    }
    assert extract_session_fields(data) == ("Qualify", "QUALIFY", 1, 3)


def test_resolve_session_identity_follows_session_num() -> None:
    weekend = {
        "WeekendInfo": {"EventType": "Race"},
        "SessionInfo": {
            "Sessions": [
                {"SessionType": "Practice", "SessionName": "PRACTICE"},
                {"SessionType": "Lone Qualify", "SessionName": "QUALIFY"},
                {"SessionType": "Race", "SessionName": "RACE"},
            ]
        },
    }
    practice = resolve_session_identity({**weekend, "SessionNum": 0})
    qualify = resolve_session_identity({**weekend, "SessionNum": 1}, prev_type=practice[0])
    race = resolve_session_identity({**weekend, "SessionNum": 2}, prev_type=qualify[0])
    assert practice[0] == "Practice"
    assert qualify[0] == "Qualify"
    assert race[0] == "Race"


def test_resolve_session_identity_keeps_previous_when_dump_empty() -> None:
    assert resolve_session_identity(
        {},
        prev_type="Practice",
        prev_name="PRACTICE",
        prev_num=0,
        prev_total=3,
    ) == ("Practice", "PRACTICE", 0, 3)
    assert resolve_session_identity(
        None,
        prev_type="Qualify",
        prev_name="QUALIFY",
        prev_num=1,
        prev_total=3,
    ) == ("Qualify", "QUALIFY", 1, 3)


def test_resolve_session_identity_clears_test_session() -> None:
    assert resolve_session_identity(
        {"SessionType": 0, "SessionName": "Test"},
        prev_type="Practice",
        prev_name="PRACTICE",
        prev_num=0,
        prev_total=1,
    ) == (None, None, None, None)


def test_extract_session_type_ignores_weekend_event_type_race() -> None:
    """EventType=Race must not label Practice/Qualify sessions as Race."""
    data = {"WeekendInfo": {"EventType": "Race"}}
    assert extract_session_type(data) is None


def test_extract_session_type_from_weekend_info() -> None:
    """Weekend EventType alone is not a session type (product, not session)."""
    assert extract_session_type({"WeekendInfo": {"EventType": "Practice"}}) is None
    assert extract_session_type({"WeekendInfo": {"EventType": "Qualify"}}) is None
    assert extract_session_type({"WeekendInfo": {"EventType": "Race"}}) is None


def test_extract_session_type_priority() -> None:
    """Test that SessionType has priority over SessionName."""
    # SessionType should take priority
    data = {"SessionType": 1, "SessionName": "Race Session"}
    assert extract_session_type(data) == "Practice"


def test_extract_session_type_missing() -> None:
    """Test extracting session type when missing."""
    assert extract_session_type({}) is None


def test_extract_session_type_none() -> None:
    """Test extracting session type when None."""
    data = {"SessionType": None}
    assert extract_session_type(data) is None


def test_extract_session_type_invalid_numeric() -> None:
    """Test extracting session type with invalid numeric value."""
    data = {"SessionType": 99}  # Invalid value
    # Should try SessionName or WeekendInfo as fallback
    result = extract_session_type(data)
    # Result depends on fallback, but should not crash
    assert result is None or isinstance(result, str)


def test_extract_session_num_valid() -> None:
    """Test extracting valid session number."""
    data = {"SessionNum": 0}
    assert extract_session_num(data) == 0

    data = {"SessionNum": 2}
    assert extract_session_num(data) == 2


def test_extract_session_num_missing() -> None:
    """Test extracting session number when missing."""
    assert extract_session_num({}) is None


def test_extract_session_num_none() -> None:
    """Test extracting session number when None."""
    data = {"SessionNum": None}
    assert extract_session_num(data) is None


def test_extract_total_sessions_valid() -> None:
    """Test extracting valid total sessions."""
    data = {"SessionCount": 3}
    assert extract_total_sessions(data) == 3

    data = {"SessionCount": 1}
    assert extract_total_sessions(data) == 1


def test_extract_total_sessions_missing() -> None:
    """Test extracting total sessions when missing."""
    assert extract_total_sessions({}) is None


def test_extract_total_sessions_none() -> None:
    """Test extracting total sessions when None."""
    data = {"SessionCount": None}
    assert extract_total_sessions(data) is None


def test_extract_total_sessions_zero() -> None:
    """Test extracting total sessions when zero."""
    data = {"SessionCount": 0}
    assert extract_total_sessions(data) == 0


def test_extract_total_sessions_from_session_total_sessions() -> None:
    """Test extracting total sessions from SessionTotalSessions field."""
    data = {"SessionTotalSessions": 3}
    assert extract_total_sessions(data) == 3


def test_extract_total_sessions_priority() -> None:
    """Test that SessionTotalSessions has priority over WeekendInfo."""
    data = {"SessionTotalSessions": 3, "WeekendInfo": {"Sessions": 5}}
    assert extract_total_sessions(data) == 3
