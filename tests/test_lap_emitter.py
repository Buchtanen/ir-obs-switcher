"""Lap complete emitter: finished lap only, not invalid laps."""

from __future__ import annotations

from irswitch.events.lap import LapEmitter
from irswitch.overlay.models import RaceState
from irswitch.overlay.settings import EventPrioritySettings, EventSettings


def _state(**overrides: object) -> RaceState:
    base: dict[str, object] = {
        "connected": True,
        "lap_completed": 3,
        "last_lap_time": 112.5,
        "best_lap_time": 111.0,
        "incidents": 0,
    }
    base.update(overrides)
    return RaceState(**base)  # type: ignore[arg-type]


def test_lap_complete_emits_on_increment() -> None:
    emitter = LapEmitter(EventSettings(), EventPrioritySettings())
    assert emitter.tick(_state(lap_completed=2, last_lap_time=113.0), 1.0) == []
    out = emitter.tick(_state(lap_completed=3, last_lap_time=112.5), 2.0)
    assert len(out) == 1
    assert out[0].name == "lap_complete"
    assert out[0].data["lap"] == 3


def test_lap_complete_skips_without_scored_time() -> None:
    emitter = LapEmitter(EventSettings(), EventPrioritySettings())
    emitter.tick(_state(lap_completed=2, last_lap_time=113.0), 1.0)
    assert emitter.tick(_state(lap_completed=3, last_lap_time=None), 2.0) == []


def test_lap_complete_skips_when_incidents_invalidate_lap() -> None:
    emitter = LapEmitter(EventSettings(), EventPrioritySettings())
    emitter.tick(_state(lap_completed=2, last_lap_time=113.0, incidents=1), 1.0)
    out = emitter.tick(_state(lap_completed=3, last_lap_time=112.5, incidents=2), 2.0)
    assert out == []
