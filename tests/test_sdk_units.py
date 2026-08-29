"""iRacing SDK sentinels and HUD time formats."""

from irswitch.iracing.sdk_units import (
    PLACEHOLDER,
    as_completed_lap_time,
    as_current_lap_time,
    as_est_time,
    as_grid_position,
    as_lap_dist_pct,
    as_non_negative_int,
    as_session_laps_remain,
    as_session_time_remain,
    format_delta,
    format_gap,
    format_lap_time,
    format_session_clock,
)
from irswitch.iracing.telemetry import extract_telemetry
from irswitch.overlay.http import web_root


def test_completed_lap_time_drops_sdk_sentinels() -> None:
    assert as_completed_lap_time(-1) is None
    assert as_completed_lap_time(0) is None
    assert as_completed_lap_time(94.372) == 94.372
    assert as_current_lap_time(0) == 0.0
    assert as_current_lap_time(-1) is None


def test_unlimited_session_markers() -> None:
    assert as_session_laps_remain(32767) is None
    assert as_session_laps_remain(3.0) == 3.0
    assert as_session_time_remain(604800) is None
    assert as_session_time_remain(120.0) == 120.0


def test_pct_is_fraction_not_percent() -> None:
    assert as_lap_dist_pct(-1) is None
    assert as_lap_dist_pct(0.42) == 0.42
    assert as_lap_dist_pct(42) is None


def test_positions_and_laps_reject_not_in_world() -> None:
    assert as_grid_position(0) is None
    assert as_grid_position(7) == 7
    assert as_non_negative_int(-1) is None
    assert as_non_negative_int(0) == 0
    assert as_est_time(-1) is None
    assert as_est_time(45.2) == 45.2


def test_format_lap_time_matches_iracing_f3() -> None:
    assert format_lap_time(112.084) == "1:52.084"
    assert format_lap_time(45.1) == "0:45.100"
    assert format_lap_time(-1) == PLACEHOLDER
    assert format_lap_time(None) == PLACEHOLDER
    assert format_lap_time(59.9996) == "1:00.000"


def test_format_delta_and_gap() -> None:
    assert format_delta(-0.318) == "-0.318"
    assert format_delta(0.318) == "+0.318"
    assert format_delta(0) == "+0.000"
    assert format_gap(1.91) == "1.91 s"
    assert format_gap(-2.5) == "2.50 s"
    assert format_session_clock(3847.2) == "1:04:07"
    assert format_session_clock(94) == "1:34"


def test_extract_telemetry_sanitizes_sdk_garbage() -> None:
    snap = extract_telemetry(
        {
            "LapCurrentLapTime": -1,
            "LapLastLapTime": -1,
            "LapBestLapTime": 0,
            "SessionLapsRemain": 32767,
            "LapDistPct": -1,
            "PlayerCarPosition": 0,
            "LapCompleted": -1,
            "CarIdxLapDistPct": [-1.0, 0.4],
            "CarIdxEstTime": [-1.0, 12.0],
            "CarIdxLapCompleted": [-1, 3],
            "CarIdxPosition": [0, 4],
        },
        1.0,
    )
    assert snap.current_lap_time is None
    assert snap.last_lap_time is None
    assert snap.best_lap_time is None
    assert snap.session_laps_remain is None
    assert snap.player_lap_dist_pct is None
    assert snap.position is None
    assert snap.lap_completed is None
    assert snap.car_idx_lap_dist_pct == (None, 0.4)
    assert snap.car_idx_est_time == (None, 12.0)
    assert snap.car_idx_lap_completed == (None, 3)
    assert snap.car_idx_position == (None, 4)


def test_overlay_js_shares_python_format_contract() -> None:
    js_root = web_root() / "overlay" / "js"
    display = (js_root / "display-v4.js").read_text(encoding="utf-8")
    legacy = (js_root / "display.js").read_text(encoding="utf-8")
    timing = (js_root / "timing-format.js").read_text(encoding="utf-8")
    assert "timing-format.js" in display
    assert "timing-format.js" in legacy
    assert "fmtLapTime" in timing
