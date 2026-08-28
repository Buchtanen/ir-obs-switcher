"""Tests for remainder emitters (rival threat, target locked, invalid lap)."""

from __future__ import annotations

from dataclasses import replace

from irswitch.events.invalid_lap import InvalidLapEmitter
from irswitch.events.rival_threat import RivalThreatEmitter
from irswitch.events.target_locked import TargetLockedEmitter
from irswitch.overlay.models import OpponentInfo
from irswitch.overlay.replay import _race_from_dict


def test_invalid_lap_emits_on_incident_lap() -> None:
    emitter = InvalidLapEmitter()
    state = replace(_race_from_dict({"connected": True, "lap_completed": 3, "incidents": 1}))
    assert emitter.tick(state, 0.0) == []
    state = replace(_race_from_dict({"connected": True, "lap_completed": 4, "incidents": 2}))
    events = emitter.tick(state, 1.0)
    assert len(events) == 1
    assert events[0].name == "invalid_lap"


def test_rival_threat_emits_when_closing_fast() -> None:
    emitter = RivalThreatEmitter()
    state = replace(
        _race_from_dict({"connected": True}),
        overlay_mode="RACE",
        gap_behind=1.2,
        closing_rate_behind=0.4,
        opponent_behind=OpponentInfo(car_idx=23, position=8),
    )
    events = emitter.tick(state, 0.0)
    assert len(events) == 1
    assert events[0].name == "rival_threat"


def test_target_locked_once_per_reference() -> None:
    emitter = TargetLockedEmitter()
    state = replace(
        _race_from_dict({"connected": True, "best_lap_time": 91.9, "lap_completed": 2}),
        overlay_mode="PRACTICE",
    )
    first = emitter.tick(state, 0.0)
    second = emitter.tick(state, 1.0)
    assert len(first) == 1
    assert first[0].name == "target_locked"
    assert second == []
