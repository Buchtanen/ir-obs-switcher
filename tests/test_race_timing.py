"""Timing crossing and store tests (Spec §6, §23)."""

from __future__ import annotations

import pytest

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
    for ts, pct in [(1.0, 0.30), (2.0, 0.60), (3.0, 0.60), (4.0, 0.90)]:
        for ev in det.update(car_id="p", lap_number=1, lap_dist_pct=pct, timestamp=ts):
            first = store.ingest_crossing(ev)
            dup = store.ingest_crossing(ev)
            if first is not None:
                assert dup is None
    assert len(store) == 3
    assert len(store._seen_keys) == 3
    assert store.append_count == 3


def test_timing_store_records_since_at_cap() -> None:
    """Emitter polling must not miss records when the store is at max_records."""
    store = TimingStore(max_records=3)
    det = CrossingDetector(points=default_minisectors(4))
    det.update(car_id="p", lap_number=1, lap_dist_pct=0.0, timestamp=0.0)
    cursor = 0
    ingested = 0
    steps = [(1.0, 0.30, 1), (2.0, 0.60, 1), (3.0, 0.90, 1), (4.0, 0.02, 2)]
    for ts, pct, lap in steps:
        for ev in det.update(car_id="p", lap_number=lap, lap_dist_pct=pct, timestamp=ts):
            if store.ingest_crossing(ev) is not None:
                ingested += 1
        pending = store.records_since(cursor)
        assert pending, f"expected new records after ts={ts}"
        cursor = store.append_count
    assert ingested == 4
    assert store.append_count == 4


def test_timing_store_eviction_refreshes_last_crossing() -> None:
    store = TimingStore(max_records=2)
    det = CrossingDetector(points=default_minisectors(4))
    det.update(car_id="p", lap_number=1, lap_dist_pct=0.0, timestamp=0.0)
    for ts, pct in [(1.0, 0.30), (2.0, 0.60), (3.0, 0.90)]:
        for ev in det.update(car_id="p", lap_number=1, lap_dist_pct=pct, timestamp=ts):
            store.ingest_crossing(ev)
    last = store._last_crossing["p"]
    assert last.timing_point_id == "MS03"
    assert last in store._records
    sf = det.update(car_id="p", lap_number=2, lap_dist_pct=0.02, timestamp=4.0)[0]
    record = store.ingest_crossing(sf)
    assert record is not None
    assert record.segment_time == pytest.approx(1.0)


def test_timing_store_reset() -> None:
    store = TimingStore()
    det = CrossingDetector(points=default_minisectors(4))
    det.update(car_id="p", lap_number=1, lap_dist_pct=0.0, timestamp=0.0)
    ev = det.update(car_id="p", lap_number=1, lap_dist_pct=0.30, timestamp=1.0)[0]
    assert store.ingest_crossing(ev) is not None
    store.reset()
    assert len(store) == 0
    assert store.ingest_crossing(ev) is not None
