"""Overtake classifier emitter tests."""

from __future__ import annotations

from irswitch.events.engine import EventEngine
from irswitch.events.overtake import OvertakeClassifierEmitter
from irswitch.events.position import PositionEmitter
from irswitch.overlay.models import OpponentInfo, RaceState
from irswitch.overlay.settings import (
    BattleSettings,
    EventEngineFeatureSettings,
    EventPrioritySettings,
    OverlaySettings,
)


def _state(**overrides: object) -> RaceState:
    base = {
        "connected": True,
        "player_car_idx": 4,
        "position": 7,
        "class_position": 5,
        "on_pit_road": False,
        "car_idx_on_pit_road": (False, False, False, False, False, False),
    }
    base.update(overrides)
    return RaceState(**base)  # type: ignore[arg-type]


def _emitter() -> OvertakeClassifierEmitter:
    return OvertakeClassifierEmitter(
        BattleSettings(position_stable_seconds=1.0),
        EventPrioritySettings(),
    )


def test_real_overtake_emits_overtake_not_position_change() -> None:
    emitter = _emitter()
    ahead = OpponentInfo(car_idx=17, position=6, gap=1.2, closing_rate=0.25)
    emitter.tick(
        _state(
            class_position=6,
            opponent_ahead=ahead,
            gap_ahead=1.2,
            closing_rate_ahead=0.25,
        ),
        0.0,
    )
    emitter.tick(
        _state(
            class_position=5,
            opponent_ahead=OpponentInfo(car_idx=22, position=5, gap=2.0, closing_rate=0.1),
            opponent_behind=OpponentInfo(car_idx=17, position=7, gap=1.0, closing_rate=-0.1),
            gap_ahead=2.0,
            gap_behind=1.0,
            closing_rate_ahead=0.1,
            closing_rate_behind=-0.1,
        ),
        0.2,
    )
    out = emitter.tick(
        _state(
            class_position=5,
            opponent_ahead=OpponentInfo(car_idx=22, position=5, gap=2.0, closing_rate=0.1),
            opponent_behind=OpponentInfo(car_idx=17, position=7, gap=1.0, closing_rate=-0.1),
            gap_ahead=2.0,
            gap_behind=1.0,
            closing_rate_ahead=0.1,
            closing_rate_behind=-0.1,
        ),
        1.2,
    )
    assert len(out) == 1
    assert out[0].name == "overtake"
    assert out[0].data["oldPosition"] == 6
    assert out[0].data["newPosition"] == 5
    assert out[0].data["targetCarIdx"] == 17


def test_distant_gain_stays_position_change() -> None:
    emitter = _emitter()
    emitter.tick(_state(class_position=8), 0.0)
    emitter.tick(_state(class_position=7), 0.2)
    out = emitter.tick(_state(class_position=7), 1.2)
    assert len(out) == 1
    assert out[0].name == "position_change"
    assert out[0].data["direction"] == "gain"


def test_opponent_on_pit_suppresses_overtake() -> None:
    emitter = _emitter()
    ahead = OpponentInfo(car_idx=17, position=6, gap=1.0, closing_rate=0.3)
    pit_flags = [False] * 20
    pit_flags[17] = True
    emitter.tick(
        _state(
            class_position=6,
            opponent_ahead=ahead,
            gap_ahead=1.0,
            closing_rate_ahead=0.3,
            car_idx_on_pit_road=tuple(pit_flags),
        ),
        0.0,
    )
    emitter.tick(
        _state(
            class_position=5,
            opponent_behind=OpponentInfo(car_idx=17, position=7, gap=1.0),
            gap_behind=1.0,
            car_idx_on_pit_road=tuple(pit_flags),
        ),
        0.2,
    )
    out = emitter.tick(
        _state(
            class_position=5,
            opponent_behind=OpponentInfo(car_idx=17, position=7, gap=1.0),
            gap_behind=1.0,
            car_idx_on_pit_road=tuple(pit_flags),
        ),
        1.2,
    )
    assert len(out) == 1
    assert out[0].name == "position_change"


def test_engine_uses_classifier_when_flag_enabled() -> None:
    overlay = OverlaySettings(
        event_engine=EventEngineFeatureSettings(overtake_classifier=True),
    )
    engine = EventEngine(overlay)
    assert isinstance(engine.position, OvertakeClassifierEmitter)


def test_engine_uses_position_emitter_when_flag_disabled() -> None:
    engine = EventEngine(OverlaySettings())
    assert type(engine.position) is PositionEmitter
