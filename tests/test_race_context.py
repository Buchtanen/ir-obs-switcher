"""Telemetry extraction and race context."""

from irswitch.iracing.telemetry import extract_telemetry
from irswitch.overlay.models import TelemetrySnapshot
from irswitch.overlay.settings import BattleSettings
from irswitch.race.context import RaceContextAnalyzer
from irswitch.race.history import GapHistory
from irswitch.race.opponents import relevant_ahead_behind


def _car_array(**kwargs: object) -> TelemetrySnapshot:
    n = 4
    zeros_f = [0.0] * n
    zeros_i = [0] * n
    zeros_b = [False] * n
    zeros_s = [4] * n
    snap = extract_telemetry(
        {
            "PlayerCarIdx": 1,
            "PlayerCarPosition": 7,
            "PlayerCarClassPosition": 5,
            "PlayerCarClass": 1,
            "LapCompleted": 11,
            "LapLastLapTime": 90.0,
            "OnPitRoad": False,
            "SessionState": 4,
            "CarIdxLapDistPct": kwargs.get("pct", zeros_f),
            "CarIdxLapCompleted": kwargs.get("laps", zeros_i),
            "CarIdxClass": kwargs.get("classes", [1, 1, 1, 2]),
            "CarIdxClassPosition": kwargs.get("cpos", [3, 5, 4, 1]),
            "CarIdxPosition": kwargs.get("pos", [3, 7, 6, 1]),
            "CarIdxOnPitRoad": kwargs.get("pit", zeros_b),
            "CarIdxTrackSurface": kwargs.get("surf", zeros_s),
        },
        timestamp=1.0,
    )
    return snap


def test_extract_telemetry_null_safe() -> None:
    snap = extract_telemetry({}, 0.0)
    assert snap.connected is True
    assert snap.position is None
    assert snap.car_idx_lap_dist_pct == ()


def test_extract_player_track_surface_and_tow() -> None:
    snap = extract_telemetry(
        {"PlayerCarIdx": 0, "PlayerTrackSurface": 3, "PlayerCarTowTime": 2.5, "SessionState": 5},
        1.0,
    )
    assert snap.player_track_surface == 3
    assert snap.player_tow_time == 2.5
    state = RaceContextAnalyzer().analyze(snap)
    assert state.player_track_surface == 3
    assert state.player_tow_time == 2.5
    assert state.session_finished is True
    assert state.session_checkered is True


def test_checkered_on_track_without_tow_is_not_after_session() -> None:
    snap = extract_telemetry(
        {
            "PlayerCarIdx": 0,
            "PlayerTrackSurface": 3,
            "OnPitRoad": False,
            "LapCompleted": 11,
            "SessionState": 5,
        },
        1.0,
    )
    state = RaceContextAnalyzer().analyze(snap)
    assert state.session_checkered is True
    assert state.session_finished is False


def test_gap_history_closing_rate_regression() -> None:
    hist = GapHistory(window_seconds=3.0)
    # gap falls 4.8 → 2.7 over 3s → closing ~0.7 s/s
    samples = [(0.0, 4.8), (0.5, 4.6), (1.0, 4.3), (1.5, 4.0), (2.0, 3.6), (2.5, 3.1), (3.0, 2.7)]
    for t, g in samples:
        hist.add(t, g)
    rate = hist.closing_rate()
    assert rate is not None
    assert 0.6 < rate < 0.8


def test_relevant_opponent_skips_other_class_and_pit() -> None:
    # player idx 1 at lap+pct 11.50, class 1
    # car 0: class 1, ahead slightly
    # car 2: class 1, in pit — ignore
    # car 3: class 2 nearby — ignore
    snap = _car_array(
        pct=[0.52, 0.50, 0.51, 0.53],
        laps=[11, 11, 11, 11],
        pit=[False, False, True, False],
        classes=[1, 1, 1, 2],
    )
    ahead, behind = relevant_ahead_behind(snap)
    assert ahead == 0
    assert behind is None


def test_analyzer_lapped_car_not_preferred() -> None:
    analyzer = RaceContextAnalyzer(BattleSettings(gap_history_seconds=3.0))
    # car 0 is a full lap ahead (lapped the field the other way / we're lapped)
    snap = _car_array(
        pct=[0.50, 0.50, 0.49, 0.1],
        laps=[12, 11, 11, 10],
        classes=[1, 1, 1, 1],
        cpos=[4, 5, 6, 9],
        pos=[4, 7, 8, 20],
        pit=[False, False, False, False],
    )
    state = analyzer.analyze(snap)
    assert state.connected
    assert state.opponent_ahead is not None
    assert state.opponent_ahead.car_idx != 3  # car 3 is a lap down
