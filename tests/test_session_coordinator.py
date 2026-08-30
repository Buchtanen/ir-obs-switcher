"""SessionCoordinator and overlay mode routing tests."""

from __future__ import annotations

from irswitch.iracing.telemetry import extract_telemetry
from irswitch.overlay.session import (
    MODE_GENERIC,
    MODE_PRACTICE,
    MODE_QUALIFYING,
    MODE_RACE,
    SessionCoordinator,
    build_session_key,
    overlay_mode_from_session_type,
)
from irswitch.race.context import RaceContextAnalyzer


def test_overlay_mode_mapping() -> None:
    assert overlay_mode_from_session_type("Practice") == MODE_PRACTICE
    assert overlay_mode_from_session_type("Qualify") == MODE_QUALIFYING
    assert overlay_mode_from_session_type("Race") == MODE_RACE
    assert overlay_mode_from_session_type("Warmup") == MODE_GENERIC
    assert overlay_mode_from_session_type(None) == MODE_GENERIC
    assert overlay_mode_from_session_type("SomethingElse") == MODE_GENERIC


def test_build_session_key() -> None:
    assert build_session_key(subsession_id=None, session_num=None, track_id=None) is None
    assert build_session_key(subsession_id="42", session_num=1, track_id="99") == "42:1:99"


def test_session_coordinator_reset_on_key_change() -> None:
    hits: list[int] = []
    coord = SessionCoordinator(warmup_sec=3.0)
    coord.add_reset_hook(lambda: hits.append(1))
    assert coord.observe(session_key="a:0:t", connected=True, now=10.0) is True
    assert hits == [1]
    assert coord.observe(session_key="a:0:t", connected=True, now=11.0) is False
    assert hits == [1]
    assert coord.observe(session_key="a:1:t", connected=True, now=12.0) is True
    assert hits == [1, 1]


def test_session_coordinator_warmup_after_reconnect() -> None:
    coord = SessionCoordinator(warmup_sec=4.0)
    coord.observe(session_key="s:0:t", connected=True, now=100.0)
    assert not coord.in_warmup(100.5)  # first connect: no warm-up
    coord.note_connection(False, 110.0)
    coord.note_connection(True, 111.0)
    assert coord.in_warmup(112.0)
    assert not coord.in_warmup(116.0)


def test_extract_telemetry_session_fields() -> None:
    snap = extract_telemetry(
        {
            "PlayerCarIdx": 0,
            "SessionNum": 2,
            "SessionTime": 12.5,
            "SessionFlags": 4,
            "SessionType": 4,
            "SubSessionID": 777,
            "TrackID": 123,
            "LapDistPct": 0.42,
        },
        1.0,
    )
    assert snap.session_num == 2
    assert snap.session_time == 12.5
    assert snap.session_flags == 4
    assert snap.subsession_id == "777"
    assert snap.track_id == "123"
    assert snap.player_lap_dist_pct == 0.42
    assert snap.session_type == "Race"


def test_analyzer_passes_overlay_mode() -> None:
    snap = extract_telemetry(
        {
            "PlayerCarIdx": 0,
            "PlayerCarPosition": 1,
            "PlayerCarClassPosition": 1,
            "SessionType": 1,
            "CarIdxLapDistPct": [0.1],
            "CarIdxLapCompleted": [1],
            "CarIdxClass": [1],
            "CarIdxClassPosition": [1],
            "CarIdxPosition": [1],
            "CarIdxOnPitRoad": [0],
            "CarIdxEstTime": [0.0],
            "CarIdxTrackSurface": [3],
        },
        1.0,
    )
    state = RaceContextAnalyzer().analyze(snap)
    assert state.overlay_mode == MODE_PRACTICE
    assert state.session_type == "Practice"


def test_extract_telemetry_session_type_from_session_name() -> None:
    """Live overlay vars often omit SessionType; SessionName must still set overlay_mode."""
    snap = extract_telemetry({"PlayerCarIdx": 0, "SessionName": "Race", "SessionNum": 2}, 1.0)
    assert snap.session_type == "Race"
    assert RaceContextAnalyzer().analyze(snap).overlay_mode == MODE_RACE


def test_extract_telemetry_session_ids_from_weekend_info() -> None:
    snap = extract_telemetry(
        {"WeekendInfo": {"SubSessionID": 777, "TrackID": 123, "EventType": "Race"}},
        1.0,
    )
    assert snap.subsession_id == "777"
    assert snap.track_id == "123"
    assert snap.session_type == "Race"


def test_telemetry_vars_include_session_identity() -> None:
    from irswitch.iracing.telemetry import TELEMETRY_VARS

    for name in (
        "SessionType",
        "SessionName",
        "SubSessionID",
        "TrackID",
        "WeekendInfo",
        "DriverInfo",
        "SplitTimeInfo",
        "PlayerTrackSurface",
        "PlayerCarTowTime",
    ):
        assert name in TELEMETRY_VARS
