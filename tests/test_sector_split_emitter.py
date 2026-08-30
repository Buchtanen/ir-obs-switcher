"""S1/S2 split callouts in Practice/Quali, silent in Race."""

from __future__ import annotations

from irswitch.events.sector_split import SectorSplitEmitter
from irswitch.overlay.models import RaceState
from irswitch.overlay.settings import EventPrioritySettings, EventSettings
from irswitch.race.timing import CrossingDetector, TimingStore, default_sectors


def _state(**overrides: object) -> RaceState:
    base: dict[str, object] = {"connected": True, "overlay_mode": "PRACTICE"}
    base.update(overrides)
    return RaceState(**base)  # type: ignore[arg-type]


def _ingest(store: TimingStore, det: CrossingDetector, pct: float, ts: float, lap: int) -> None:
    for ev in det.update(car_id="player", lap_number=lap, lap_dist_pct=pct, timestamp=ts):
        store.ingest_crossing(ev)


def test_default_sectors_are_s1_s2() -> None:
    points = default_sectors()
    assert [p.id for p in points] == ["MS00", "S1", "S2"]
    assert points[1].lap_dist_pct == 1.0 / 3.0
    assert points[2].lap_dist_pct == 2.0 / 3.0


def test_sector_split_emits_s1_time_in_practice() -> None:
    store = TimingStore()
    det = CrossingDetector(points=default_sectors())
    emitter = SectorSplitEmitter(store, EventSettings(), EventPrioritySettings())
    _ingest(store, det, 0.90, 1.0, lap=1)
    _ingest(store, det, 0.02, 2.0, lap=2)
    emitter.tick(_state(), 2.0)
    _ingest(store, det, 0.40, 35.0, lap=2)
    out = emitter.tick(_state(), 35.0)
    assert [e.name for e in out] == ["sector_split"]
    assert out[0].data["sector"] == "S1"
    assert out[0].data["segmentTime"] == 33.0


def test_sector_split_emits_in_quali() -> None:
    store = TimingStore()
    det = CrossingDetector(points=default_sectors())
    emitter = SectorSplitEmitter(store, EventSettings(), EventPrioritySettings())
    _ingest(store, det, 0.90, 1.0, lap=1)
    _ingest(store, det, 0.02, 2.0, lap=2)
    _ingest(store, det, 0.40, 35.0, lap=2)
    out = emitter.tick(_state(overlay_mode="QUALIFYING"), 35.0)
    assert any(e.name == "sector_split" for e in out)


def test_sector_split_silent_in_race() -> None:
    store = TimingStore()
    det = CrossingDetector(points=default_sectors())
    emitter = SectorSplitEmitter(store, EventSettings(), EventPrioritySettings())
    _ingest(store, det, 0.90, 1.0, lap=1)
    _ingest(store, det, 0.02, 2.0, lap=2)
    _ingest(store, det, 0.40, 35.0, lap=2)
    assert emitter.tick(_state(overlay_mode="RACE"), 35.0) == []


def test_sector_split_emits_s3_when_present() -> None:
    from irswitch.race.timing.points import TimingPoint

    points = (
        TimingPoint(id="MS00", lap_dist_pct=0.0, label="START_FINISH"),
        TimingPoint(id="S1", lap_dist_pct=0.25, label="S1"),
        TimingPoint(id="S2", lap_dist_pct=0.5, label="S2"),
        TimingPoint(id="S3", lap_dist_pct=0.75, label="S3"),
    )
    store = TimingStore()
    det = CrossingDetector(points=points)
    emitter = SectorSplitEmitter(store, EventSettings(), EventPrioritySettings())
    _ingest(store, det, 0.90, 1.0, lap=1)
    _ingest(store, det, 0.02, 2.0, lap=2)
    _ingest(store, det, 0.80, 80.0, lap=2)
    out = emitter.tick(_state(), 80.0)
    names = [e.data["sector"] for e in out]
    assert "S3" in names


def test_sector_split_silent_after_checkered() -> None:
    store = TimingStore()
    det = CrossingDetector(points=default_sectors())
    emitter = SectorSplitEmitter(store, EventSettings(), EventPrioritySettings())
    _ingest(store, det, 0.90, 1.0, lap=1)
    _ingest(store, det, 0.02, 2.0, lap=2)
    _ingest(store, det, 0.40, 35.0, lap=2)
    assert emitter.tick(_state(session_finished=True), 35.0) == []
