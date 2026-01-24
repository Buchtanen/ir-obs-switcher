from irswitch.iracing.extractors import extract_mode
from irswitch.models import DrivingMode


def test_extract_mode_prioritizes_replay() -> None:
    data = {
        "IsReplay": True,
        "IsOnTrack": True,
        "PlayerCarInGarage": True,
    }
    assert extract_mode(data) == DrivingMode.REPLAY


def test_extract_mode_race_when_on_track() -> None:
    data = {"IsOnTrack": 1}
    assert extract_mode(data) == DrivingMode.RACE


def test_extract_mode_garage_when_in_garage() -> None:
    data = {"PlayerCarInGarage": "true"}
    assert extract_mode(data) == DrivingMode.GARAGE


def test_extract_mode_idle_by_default() -> None:
    assert extract_mode({}) == DrivingMode.IDLE


def test_extract_mode_settings_from_session_state() -> None:
    """Test SETTINGS mode detection from SessionState."""
    data = {"SessionState": "menu"}
    assert extract_mode(data) == DrivingMode.SETTINGS
    
    data = {"SessionState": "settings"}
    assert extract_mode(data) == DrivingMode.SETTINGS


def test_extract_mode_settings_from_session_state_num() -> None:
    """Test SETTINGS mode detection from SessionStateNum == 0."""
    data = {"SessionStateNum": 0}
    assert extract_mode(data) == DrivingMode.SETTINGS


def test_extract_mode_settings_priority() -> None:
    """Test that SETTINGS has priority over RACE and GARAGE, but not REPLAY."""
    # SETTINGS should override RACE
    data = {"SessionState": "menu", "IsOnTrack": True}
    assert extract_mode(data) == DrivingMode.SETTINGS
    
    # SETTINGS should override GARAGE
    data = {"SessionState": "menu", "PlayerCarInGarage": True}
    assert extract_mode(data) == DrivingMode.SETTINGS
    
    # REPLAY should override SETTINGS
    data = {"SessionState": "menu", "IsReplay": True}
    assert extract_mode(data) == DrivingMode.REPLAY


# Session info extraction tests
from irswitch.iracing.extractors import (
    extract_session_type,
    extract_session_num,
    extract_total_sessions,
)


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


def test_extract_session_type_from_weekend_info() -> None:
    """Test extracting session type from WeekendInfo.EventType."""
    data = {"WeekendInfo": {"EventType": "Practice"}}
    assert extract_session_type(data) == "Practice"
    
    data = {"WeekendInfo": {"EventType": "Qualify"}}
    assert extract_session_type(data) == "Qualify"
    
    data = {"WeekendInfo": {"EventType": "Race"}}
    assert extract_session_type(data) == "Race"


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
    data = {
        "SessionTotalSessions": 3,
        "WeekendInfo": {"Sessions": 5}
    }
    assert extract_total_sessions(data) == 3