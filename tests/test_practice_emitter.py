"""Practice timing emitter tests."""

from __future__ import annotations

from irswitch.events.practice import PracticeEmitter
from irswitch.overlay.models import RaceState
from irswitch.overlay.settings import EventPrioritySettings, EventSettings
from irswitch.race.timing import (
    CrossingDetector,
    SegmentReferenceTracker,
    TimingStore,
    default_minisectors,
)


def _practice_state(**overrides: object) -> RaceState:
    base = {"connected": True, "overlay_mode": "PRACTICE"}
    base.update(overrides)
    return RaceState(**base)  # type: ignore[arg-type]


def _ingest(store: TimingStore, det: CrossingDetector, pct: float, ts: float, lap: int = 1) -> None:
    for ev in det.update(car_id="player", lap_number=lap, lap_dist_pct=pct, timestamp=ts):
        store.ingest_crossing(ev)


def test_practice_gain_found_after_reference_segment() -> None:
    store = TimingStore()
    ref = SegmentReferenceTracker()
    emitter = PracticeEmitter(store, ref, EventSettings(), EventPrioritySettings())
    det = CrossingDetector(points=default_minisectors(4))
    _ingest(store, det, 0.0, 0.0)
    _ingest(store, det, 0.30, 2.0)
    _ingest(store, det, 0.60, 3.0)
    emitter.tick(_practice_state(), 3.0)
    _ingest(store, det, 0.05, 4.0, lap=2)
    emitter.tick(_practice_state(), 4.0)
    _ingest(store, det, 0.30, 5.0, lap=2)
    _ingest(store, det, 0.60, 5.4, lap=2)
    out = emitter.tick(_practice_state(), 5.4)
    assert any(e.name == "gain_found" for e in out)
    gain = next(e for e in out if e.name == "gain_found")
    assert gain.data["timingPointId"] == "MS02"
    assert gain.data["delta"] < 0


def test_practice_time_lost_emits_on_slower_segment() -> None:
    store = TimingStore()
    ref = SegmentReferenceTracker()
    emitter = PracticeEmitter(store, ref, EventSettings(), EventPrioritySettings())
    det = CrossingDetector(points=default_minisectors(4))
    _ingest(store, det, 0.0, 0.0)
    _ingest(store, det, 0.30, 1.0)
    _ingest(store, det, 0.60, 2.0)
    emitter.tick(_practice_state(), 2.0)
    _ingest(store, det, 0.05, 3.0, lap=2)
    emitter.tick(_practice_state(), 3.0)
    _ingest(store, det, 0.30, 4.0, lap=2)
    _ingest(store, det, 0.60, 6.0, lap=2)
    out = emitter.tick(_practice_state(), 6.0)
    assert any(e.name == "time_lost" for e in out)


def test_practice_silent_in_race_mode() -> None:
    store = TimingStore()
    ref = SegmentReferenceTracker()
    emitter = PracticeEmitter(store, ref, EventSettings(), EventPrioritySettings())
    det = CrossingDetector(points=default_minisectors(4))
    _ingest(store, det, 0.0, 0.0)
    _ingest(store, det, 0.30, 1.0)
    _ingest(store, det, 0.05, 3.0, lap=2)
    _ingest(store, det, 0.30, 5.0, lap=2)
    assert emitter.tick(_practice_state(overlay_mode="RACE"), 5.0) == []
