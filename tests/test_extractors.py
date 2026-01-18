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
