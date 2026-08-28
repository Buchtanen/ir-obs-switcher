"""Qualifying projection emitter tests."""

from __future__ import annotations

from irswitch.events.quali import QualiEmitter
from irswitch.overlay.models import RaceState
from irswitch.overlay.settings import EventPrioritySettings, EventSettings
from irswitch.race.timing import (
    CrossingDetector,
    SegmentReferenceTracker,
    TimingStore,
    default_minisectors,
)


def _quali_state(**overrides: object) -> RaceState:
    base = {
        "connected": True,
        "overlay_mode": "QUALIFYING",
        "best_lap_time": 92.0,
        "position": 7,
        "current_lap_time": 46.0,
        "player_lap_dist_pct": 0.5,
    }
    base.update(overrides)
    return RaceState(**base)  # type: ignore[arg-type]


def test_quali_projected_lap_from_lap_progress() -> None:
    store = TimingStore()
    ref = SegmentReferenceTracker()
    emitter = QualiEmitter(store, ref, EventSettings(), EventPrioritySettings())
    out = emitter.tick(_quali_state(), 1.0)
    assert any(e.name == "projected_lap" and e.phase == "enter" for e in out)
    proj = next(e for e in out if e.name == "projected_lap")
    assert proj.data["projectedTime"] == 92.0
    assert proj.data["confidence"] >= 0.35


def test_quali_position_attack_when_projected_beats_best() -> None:
    store = TimingStore()
    ref = SegmentReferenceTracker()
    emitter = QualiEmitter(store, ref, EventSettings(), EventPrioritySettings())
    out = emitter.tick(
        _quali_state(current_lap_time=40.0, player_lap_dist_pct=0.6, best_lap_time=92.0),
        1.0,
    )
    assert any(e.name == "position_attack" for e in out)


def test_quali_silent_below_min_dist_pct() -> None:
    store = TimingStore()
    ref = SegmentReferenceTracker()
    emitter = QualiEmitter(store, ref, EventSettings(), EventPrioritySettings())
    out = emitter.tick(
        _quali_state(current_lap_time=10.0, player_lap_dist_pct=0.05),
        1.0,
    )
    assert out == []


def test_quali_update_phase_on_second_projection() -> None:
    store = TimingStore()
    ref = SegmentReferenceTracker()
    emitter = QualiEmitter(store, ref, EventSettings(), EventPrioritySettings())
    emitter.tick(_quali_state(), 1.0)
    out = emitter.tick(_quali_state(current_lap_time=44.0), 2.0)
    assert any(e.name == "projected_lap" and e.phase == "update" for e in out)


def test_quali_crossing_projection() -> None:
    store = TimingStore()
    ref = SegmentReferenceTracker()
    emitter = QualiEmitter(store, ref, EventSettings(), EventPrioritySettings())
    det = CrossingDetector(points=default_minisectors(4))
    det.update(car_id="player", lap_number=1, lap_dist_pct=0.0, timestamp=0.0)
    stamps = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    pcts = [0.10, 0.20, 0.30, 0.40, 0.50, 0.55, 0.60, 0.70, 0.80, 0.90]
    for ts, pct in zip(stamps, pcts, strict=True):
        for ev in det.update(car_id="player", lap_number=1, lap_dist_pct=pct, timestamp=ts):
            store.ingest_crossing(ev)
    out = emitter.tick(_quali_state(player_lap_dist_pct=None, current_lap_time=None), 10.0)
    assert any(e.name == "projected_lap" for e in out)


def test_quali_silent_when_disconnected() -> None:
    store = TimingStore()
    ref = SegmentReferenceTracker()
    emitter = QualiEmitter(store, ref, EventSettings(), EventPrioritySettings())
    assert emitter.tick(_quali_state(connected=False), 1.0) == []


def test_quali_suppresses_near_duplicate_projections() -> None:
    store = TimingStore()
    ref = SegmentReferenceTracker()
    emitter = QualiEmitter(store, ref, EventSettings(), EventPrioritySettings())
    first = emitter.tick(_quali_state(), 1.0)
    assert any(e.name == "projected_lap" for e in first)
    second = emitter.tick(_quali_state(current_lap_time=46.01), 2.0)
    assert second == []
