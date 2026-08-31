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
    assert snap.speed_mps is None
    assert snap.car_idx_best_lap_time == ()
    assert snap.car_idx_last_lap_time == ()
    assert snap.session_flags is None


def test_analyzer_copies_speed_times_and_decoded_flags() -> None:
    snap = extract_telemetry(
        {
            "PlayerCarIdx": 0,
            "Speed": 28.5,
            "SessionFlags": 0x00000001 | 0x00000008,
            "CarIdxBestLapTime": [91.2, -1],
            "CarIdxLastLapTime": [90.0, 0],
            "SessionState": 4,
        },
        1.0,
    )
    assert snap.speed_mps == 28.5
    state = RaceContextAnalyzer().analyze(snap)
    assert state.speed_mps == 28.5
    assert state.session_flags == 0x00000009
    assert state.session_flag_names == ("checkered", "yellow")
    assert state.flag_checkered is True
    assert state.flag_yellow is True
    assert state.flag_green is False
    assert state.car_idx_best_lap_time == (91.2, None)
    assert state.car_idx_last_lap_time == (90.0, None)
    assert state.session_finished is False


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
    assert state.session_checkered is True
    assert state.player_finished is False
    assert state.session_finished is False
    assert state.mute_field is False


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


def _finish_snap(**kwargs: object) -> TelemetrySnapshot:
    data: dict[str, object] = {
        "PlayerCarIdx": 0,
        "SessionState": 4,
        "LapCompleted": 10,
        "LapDistPct": 0.5,
        "OnPitRoad": False,
        "PlayerTrackSurface": 3,
    }
    data.update(kwargs)
    return extract_telemetry(data, 1.0)


def test_checkered_mid_lap_is_not_finish() -> None:
    analyzer = RaceContextAnalyzer()
    analyzer.analyze(_finish_snap(SessionState=4, LapCompleted=10, LapDistPct=0.4))
    state = analyzer.analyze(_finish_snap(SessionState=5, LapCompleted=10, LapDistPct=0.5))
    assert state.session_checkered is True
    assert state.player_finished is False
    assert state.mute_field is False
    assert state.session_finished is False


def test_lap_complete_after_checkered_is_finish() -> None:
    analyzer = RaceContextAnalyzer()
    analyzer.analyze(_finish_snap(SessionState=5, LapCompleted=10, LapDistPct=0.9))
    state = analyzer.analyze(_finish_snap(SessionState=5, LapCompleted=11, LapDistPct=0.05))
    assert state.player_finished is True
    assert state.mute_field is True
    assert state.session_finished is True
    assert state.session_checkered is True


def test_dist_wrap_after_checkered_is_finish() -> None:
    analyzer = RaceContextAnalyzer()
    analyzer.analyze(_finish_snap(SessionState=5, LapCompleted=10, LapDistPct=0.92))
    state = analyzer.analyze(_finish_snap(SessionState=5, LapCompleted=10, LapDistPct=0.04))
    assert state.player_finished is True


def test_already_in_pits_at_checkered_is_not_pit_rise_finish() -> None:
    analyzer = RaceContextAnalyzer()
    analyzer.analyze(_finish_snap(SessionState=5, OnPitRoad=True, PlayerTrackSurface=1))
    state = analyzer.analyze(_finish_snap(SessionState=5, OnPitRoad=True, PlayerTrackSurface=1))
    assert state.player_finished is False


def test_pit_rise_after_checkered_finishes_when_was_on_track() -> None:
    analyzer = RaceContextAnalyzer()
    analyzer.analyze(
        _finish_snap(SessionState=5, OnPitRoad=False, LapDistPct=0.4, PlayerTrackSurface=3)
    )
    state = analyzer.analyze(
        _finish_snap(SessionState=5, OnPitRoad=True, LapDistPct=0.41, PlayerTrackSurface=2)
    )
    assert state.player_finished is True


def test_esc_teleport_is_not_pit_rise_finish() -> None:
    analyzer = RaceContextAnalyzer()
    analyzer.analyze(
        _finish_snap(SessionState=5, OnPitRoad=False, LapDistPct=0.80, PlayerTrackSurface=3)
    )
    state = analyzer.analyze(
        _finish_snap(SessionState=5, OnPitRoad=True, LapDistPct=0.12, PlayerTrackSurface=1)
    )
    assert state.player_finished is False


def test_unknown_pit_dropout_does_not_arm_finish() -> None:
    analyzer = RaceContextAnalyzer()
    analyzer.analyze(_finish_snap(SessionState=5, OnPitRoad=False))
    missing = extract_telemetry(
        {
            "PlayerCarIdx": 0,
            "SessionState": 5,
            "LapCompleted": 10,
            "LapDistPct": 0.5,
            "PlayerTrackSurface": 3,
        },
        1.0,
    )
    assert missing.on_pit_road is None
    mid = analyzer.analyze(missing)
    assert mid.player_finished is False
    recovered = analyzer.analyze(_finish_snap(SessionState=5, OnPitRoad=True, PlayerTrackSurface=1))
    assert recovered.player_finished is False


def test_cooldown_without_cross_is_finish_fallback() -> None:
    analyzer = RaceContextAnalyzer()
    analyzer.analyze(_finish_snap(SessionState=5, LapCompleted=10, LapDistPct=0.4))
    state = analyzer.analyze(_finish_snap(SessionState=6, LapCompleted=10, LapDistPct=0.4))
    assert state.session_checkered is False
    assert state.player_finished is True
    assert state.mute_field is True


def test_disconnect_drops_finish_latch() -> None:
    analyzer = RaceContextAnalyzer()
    analyzer.analyze(_finish_snap(SessionState=5, LapCompleted=10, LapDistPct=0.9))
    analyzer.analyze(_finish_snap(SessionState=5, LapCompleted=11, LapDistPct=0.05))
    disconnected = analyzer.analyze(TelemetrySnapshot.disconnected(2.0))
    assert disconnected.player_finished is False
    again = analyzer.analyze(_finish_snap(SessionState=5, LapCompleted=11, LapDistPct=0.2))
    assert again.player_finished is False
