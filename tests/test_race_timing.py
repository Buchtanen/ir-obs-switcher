"""Timing crossing and store tests (Spec §6, §23)."""

from __future__ import annotations

from irswitch.race.timing import (
    CrossingDetector,
    TimingStore,
    default_minisectors,
)


def test_default_minisectors_count_and_sf() -> None:
    points = default_minisectors(20)
    assert len(points) == 20
    assert points[0].id == "MS00"
    assert points[0].lap_dist_pct == 0.0
    assert points[1].lap_dist_pct == 0.05


def test_lap_increment_emits_single_sf_crossing() -> None:
    det = CrossingDetector(points=default_minisectors(4))
    events = det.update(car_id="player", lap_number=5, lap_dist_pct=0.99, timestamp=10.0)
    assert events == []
    events = det.update(car_id="player", lap_number=6, lap_dist_pct=0.02, timestamp=11.0)
    assert len(events) == 1
    assert events[0].timing_point_id == "MS00"
    assert events[0].lap_number == 6


def test_wrap_without_lap_increment_does_not_flood_minisektors() -> None:
    det = CrossingDetector(points=default_minisectors(4))
    det.update(car_id="player", lap_number=3, lap_dist_pct=0.10, timestamp=1.0)
    events = det.update(car_id="player", lap_number=3, lap_dist_pct=0.02, timestamp=2.0)
    assert events == []


def test_reverse_motion_no_crossing() -> None:
    det = CrossingDetector(points=default_minisectors(4))
    det.update(car_id="player", lap_number=2, lap_dist_pct=0.40, timestamp=1.0)
    events = det.update(car_id="player", lap_number=2, lap_dist_pct=0.20, timestamp=2.0)
    assert events == []


def test_forward_minisector_crossings() -> None:
    det = CrossingDetector(points=default_minisectors(4))
    det.update(car_id="player", lap_number=1, lap_dist_pct=0.10, timestamp=0.0)
    events = det.update(car_id="player", lap_number=1, lap_dist_pct=0.55, timestamp=1.0)
    ids = [e.timing_point_id for e in events]
    assert "MS01" in ids
    assert "MS02" in ids
    assert "MS00" not in ids


def test_timing_store_dedupe_and_cap() -> None:
    store = TimingStore(max_records=3)
    det = CrossingDetector(points=default_minisectors(4))
    det.update(car_id="p", lap_number=1, lap_dist_pct=0.0, timestamp=0.0)
    for ts, pct in [(1.0, 0.30), (2.0, 0.30), (3.0, 0.60), (4.0, 0.90)]:
        for ev in det.update(car_id="p", lap_number=1, lap_dist_pct=pct, timestamp=ts):
            first = store.ingest_crossing(ev)
            dup = store.ingest_crossing(ev)
            if first is not None:
                assert dup is None
    assert len(store) == 3
    assert len(store._seen_keys) == 3


def test_timing_store_reset() -> None:
    store = TimingStore()
    det = CrossingDetector(points=default_minisectors(4))
    det.update(car_id="p", lap_number=1, lap_dist_pct=0.0, timestamp=0.0)
    ev = det.update(car_id="p", lap_number=1, lap_dist_pct=0.30, timestamp=1.0)[0]
    assert store.ingest_crossing(ev) is not None
    store.reset()
    assert len(store) == 0
    assert store.ingest_crossing(ev) is not None
