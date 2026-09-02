"""Tests for remainder emitters (rival threat, target locked, invalid lap)."""

from __future__ import annotations

from dataclasses import replace

import pytest

from irswitch.events.invalid_lap import InvalidLapEmitter
from irswitch.events.rival_threat import RivalThreatEmitter
from irswitch.events.target_locked import TargetLockedEmitter
from irswitch.overlay.models import OpponentInfo
from irswitch.overlay.replay import _race_from_dict


def test_invalid_lap_emits_on_incident_lap() -> None:
    emitter = InvalidLapEmitter()
    state = replace(
        _race_from_dict({"connected": True, "lap_completed": 3, "incidents": 1}),
        overlay_mode="PRACTICE",
    )
    assert emitter.tick(state, 0.0) == []
    state = replace(
        _race_from_dict({"connected": True, "lap_completed": 4, "incidents": 2}),
        overlay_mode="PRACTICE",
    )
    events = emitter.tick(state, 1.0)
    assert len(events) == 1
    assert events[0].name == "invalid_lap"


def test_rival_threat_emits_when_closing_fast() -> None:
    emitter = RivalThreatEmitter()
    state = replace(
        _race_from_dict({"connected": True}),
        overlay_mode="RACE",
        position=7,
        gap_behind=1.2,
        closing_rate_behind=0.4,
        opponent_behind=OpponentInfo(car_idx=23, position=8),
    )
    events = emitter.tick(state, 0.0)
    assert len(events) == 1
    assert events[0].name == "rival_threat"
    assert events[0].data["rivalPosition"] == 8


def test_rival_threat_prefers_class_position() -> None:
    emitter = RivalThreatEmitter()
    state = replace(
        _race_from_dict({"connected": True}),
        overlay_mode="RACE",
        class_position=5,
        gap_behind=1.2,
        closing_rate_behind=0.4,
        opponent_behind=OpponentInfo(car_idx=23, position=18, class_position=6),
    )
    events = emitter.tick(state, 0.0)
    assert events[0].data["rivalPosition"] == 6


@pytest.mark.parametrize("gap", [-1.0, float("nan"), float("inf")])
def test_rival_threat_rejects_invalid_gap(gap: float) -> None:
    state = replace(
        _race_from_dict({"connected": True}),
        overlay_mode="RACE",
        position=7,
        gap_behind=gap,
        closing_rate_behind=0.4,
        opponent_behind=OpponentInfo(car_idx=23, position=8),
    )
    assert RivalThreatEmitter().tick(state, 0.0) == []


def test_rival_threat_clears_during_enter_cooldown() -> None:
    emitter = RivalThreatEmitter()
    active = replace(
        _race_from_dict({"connected": True}),
        overlay_mode="RACE",
        position=7,
        gap_behind=1.2,
        closing_rate_behind=0.4,
        opponent_behind=OpponentInfo(car_idx=23, position=8),
    )
    assert emitter.tick(active, 0.0)[0].phase == "enter"
    exited = emitter.tick(replace(active, gap_behind=float("nan")), 1.0)
    assert len(exited) == 1 and exited[0].phase == "exit"


def test_rival_threat_requires_rival_to_be_behind_in_class() -> None:
    state = replace(
        _race_from_dict({"connected": True}),
        overlay_mode="RACE",
        class_position=5,
        gap_behind=1.2,
        closing_rate_behind=0.4,
        opponent_behind=OpponentInfo(car_idx=23, position=8, class_position=4),
    )
    assert RivalThreatEmitter().tick(state, 0.0) == []


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
