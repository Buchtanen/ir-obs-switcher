"""iRSDK SplitTimeInfo → official sector timing points."""

from __future__ import annotations

from irswitch.iracing.sectors import (
    resolve_sector_points,
    sector_start_pcts,
    timing_points_from_pcts,
)
from irswitch.iracing.telemetry import TELEMETRY_VARS, extract_telemetry
from irswitch.race.timing.points import default_sectors


def test_sector_start_pcts_from_split_time_info() -> None:
    pcts = sector_start_pcts(
        {
            "Sectors": [
                {"SectorNum": 2, "SectorStartPct": 0.671},
                {"SectorNum": 0, "SectorStartPct": 0.0},
                {"SectorNum": 1, "SectorStartPct": 0.328},
            ]
        }
    )
    assert pcts == (0.0, 0.328, 0.671)


def test_sector_start_pcts_accepts_percent_units() -> None:
    pcts = sector_start_pcts(
        {
            "Sectors": [
                {"SectorNum": 0, "SectorStartPct": 0.0},
                {"SectorNum": 1, "SectorStartPct": 32.8},
                {"SectorNum": 2, "SectorStartPct": 67.1},
            ]
        }
    )
    assert pcts == (0.0, 0.328, 0.671)


def test_timing_points_skip_sf_and_label_s1_s2() -> None:
    points = timing_points_from_pcts((0.0, 0.328, 0.671))
    assert [p.id for p in points] == ["MS00", "S1", "S2"]
    assert points[1].lap_dist_pct == 0.328
    assert points[2].lap_dist_pct == 0.671


def test_timing_points_emit_s3_when_track_has_four_sectors() -> None:
    points = timing_points_from_pcts((0.0, 0.25, 0.5, 0.75))
    assert [p.id for p in points] == ["MS00", "S1", "S2", "S3"]


def test_resolve_falls_back_to_geometric_when_missing() -> None:
    assert resolve_sector_points(None) == default_sectors()
    assert resolve_sector_points({}) == default_sectors()
    assert resolve_sector_points({"Sectors": [{"SectorNum": 0, "SectorStartPct": 0.0}]}) == (
        default_sectors()
    )


def test_extract_telemetry_includes_sector_starts() -> None:
    snap = extract_telemetry(
        {
            "SplitTimeInfo": {
                "Sectors": [
                    {"SectorNum": 0, "SectorStartPct": 0.0},
                    {"SectorNum": 1, "SectorStartPct": 0.4},
                ]
            }
        },
        timestamp=1.0,
    )
    assert snap.sector_start_pcts == (0.0, 0.4)
    assert "SplitTimeInfo" in TELEMETRY_VARS
