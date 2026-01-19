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