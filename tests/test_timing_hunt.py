"""P/Q hunt-by-time vs CarIdxBestLapTime. No DriverInfo."""

from __future__ import annotations

from pathlib import Path

from irswitch.overlay.models import RaceState, TelemetrySnapshot
from irswitch.race.observer import RaceObserver
from irswitch.race.timing_hunt import TimingHuntFsm, hero_pace_s

ROOT = Path(__file__).resolve().parents[1]
HUNT_SRC = ROOT / "src" / "irswitch" / "race" / "timing_hunt.py"
QUALI_SRC = ROOT / "src" / "irswitch" / "events" / "quali.py"


def _snap(
    *,
    bests: tuple[float | None, ...],
    class_positions: tuple[int | None, ...] = (1, 2, 3),
    current_lap_time: float = 46.02,
    dist: float = 0.5,
) -> TelemetrySnapshot:
    return TelemetrySnapshot(
        connected=True,
        player_car_idx=2,
        class_position=3,
        player_car_class=1,
        current_lap_time=current_lap_time,
        player_lap_dist_pct=dist,
        car_idx_class=(1, 1, 1),
        car_idx_class_position=class_positions,
        car_idx_best_lap_time=bests,
    )


def _state(mode: str = "QUALIFYING") -> RaceState:
    return RaceState(
        connected=True,
        overlay_mode=mode,
        class_position=3,
        current_lap_time=46.02,
        player_lap_dist_pct=0.5,
        player_car_idx=2,
    )


def test_hero_projected_matches_rival_best() -> None:
    snap = _snap(bests=(90.0, 92.0, 93.0))
    assert hero_pace_s(snap, _state()) == 92.04


def test_pace_hunt_when_hero_is_on_the_p_n_time() -> None:
    fsm = TimingHuntFsm()
    out = fsm.tick(_snap(bests=(90.0, 92.0, 93.0)), _state(), 1.0)
    assert len(out) == 1
    assert out[0].event_type == "PACE_HUNT"
    assert out[0].metrics["position"] == 2
    assert out[0].metrics["rivalTime"] == 92.0
    assert fsm.tick(_snap(bests=(90.0, 92.0, 93.0)), _state(), 2.0) == []


def test_all_unset_best_times_are_silent() -> None:
    fsm = TimingHuntFsm()
    assert fsm.tick(_snap(bests=(None, None, None)), _state(), 1.0) == []
    assert fsm.tick(_snap(bests=()), _state(), 1.0) == []


def test_race_session_does_not_pace_hunt() -> None:
    fsm = TimingHuntFsm()
    assert fsm.tick(_snap(bests=(90.0, 92.0, 93.0)), _state("RACE"), 1.0) == []


def test_observer_drains_pace_hunt_and_formats_without_names() -> None:
    observer = RaceObserver()
    snap = _snap(bests=(90.0, 92.0, 93.0))
    observer.observe(snap, _state(), now=1.0)
    derived = observer.take_derived_envelopes()
    assert [env.event_type for env in derived] == ["PACE_HUNT"]
    text = observer.format_filler_text(derived[0], locale="en")
    assert text == "He's hunting the P2 time."
    hunt_src = HUNT_SRC.read_text(encoding="utf-8")
    assert "car_idx_driver_name" not in hunt_src
    assert "DriverInfo" not in hunt_src


def test_quali_position_attack_is_own_pb_not_rival_time() -> None:
    source = QUALI_SRC.read_text(encoding="utf-8")
    assert "best_lap_time" in source
    assert "CarIdxBestLapTime" not in source
    assert "timing_hunt.py" in source
