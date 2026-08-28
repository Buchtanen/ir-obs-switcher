"""Battle intensity ladder tests."""

from __future__ import annotations

from irswitch.events.adapters.battle import battle_race_event_to_envelope
from irswitch.events.battle import BattleEmitter
from irswitch.events.battle_intensity import resolve_hunting_intensity
from irswitch.overlay.models import OpponentInfo, RaceState
from irswitch.overlay.protocol import RaceEvent
from irswitch.overlay.settings import HuntingSettings


def _state(**overrides: object) -> RaceState:
    base = {
        "connected": True,
        "player_car_idx": 4,
        "position": 7,
        "class_position": 5,
    }
    base.update(overrides)
    return RaceState(**base)  # type: ignore[arg-type]


def _hunting_cfg() -> HuntingSettings:
    return HuntingSettings(activation_delay=0.0, exit_delay=1.5)


def test_hunting_progresses_to_attack_range() -> None:
    emitter = BattleEmitter(_hunting_cfg(), _hunting_cfg())
    ahead = OpponentInfo(car_idx=17, position=6, gap=2.0, closing_rate=0.3)
    out = emitter.tick(
        _state(opponent_ahead=ahead, gap_ahead=2.0, closing_rate_ahead=0.3),
        1.0,
    )
    assert any(e.phase == "enter" and e.data["state"] == "hunting" for e in out)

    ahead_close = OpponentInfo(car_idx=17, position=6, gap=1.2, closing_rate=0.25)
    out = emitter.tick(
        _state(opponent_ahead=ahead_close, gap_ahead=1.2, closing_rate_ahead=0.25),
        2.0,
    )
    assert any(e.phase == "enter" and e.data["state"] == "approach" for e in out)

    ahead_attack = OpponentInfo(car_idx=17, position=6, gap=0.6, closing_rate=0.22)
    out = emitter.tick(
        _state(opponent_ahead=ahead_attack, gap_ahead=0.6, closing_rate_ahead=0.22),
        3.0,
    )
    assert any(e.phase == "enter" and e.data["state"] == "attack_range" for e in out)


def test_intensity_hysteresis_prevents_oscillation() -> None:
    cfg = _hunting_cfg()
    emitter = BattleEmitter(cfg, cfg)
    ahead = OpponentInfo(car_idx=17, position=6, gap=2.0, closing_rate=0.3)
    emitter.tick(_state(opponent_ahead=ahead, gap_ahead=2.0, closing_rate_ahead=0.3), 1.0)
    emitter.tick(
        _state(
            opponent_ahead=OpponentInfo(car_idx=17, position=6, gap=0.6, closing_rate=0.25),
            gap_ahead=0.6,
            closing_rate_ahead=0.25,
        ),
        2.0,
    )
    emitter.tick(
        _state(
            opponent_ahead=OpponentInfo(car_idx=17, position=6, gap=0.32, closing_rate=0.25),
            gap_ahead=0.32,
            closing_rate_ahead=0.25,
        ),
        3.0,
    )
    emitter.tick(
        _state(
            opponent_ahead=OpponentInfo(car_idx=17, position=6, gap=0.32, closing_rate=0.25),
            gap_ahead=0.32,
            closing_rate_ahead=0.25,
        ),
        4.0,
    )
    assert emitter.hunting.intensity == "side_by_side"

    for step, gap in enumerate([0.40, 0.38, 0.42, 0.36], start=5):
        emitter.tick(
            _state(
                opponent_ahead=OpponentInfo(car_idx=17, position=6, gap=gap, closing_rate=0.25),
                gap_ahead=gap,
                closing_rate_ahead=0.25,
            ),
            float(step),
        )
    assert emitter.hunting.intensity == "side_by_side"


def test_resolve_hunting_intensity_stepwise() -> None:
    cfg = _hunting_cfg()
    assert resolve_hunting_intensity(1.2, 0.2, "hunting", cfg) == "approach"
    assert resolve_hunting_intensity(0.6, 0.2, "approach", cfg) == "attack_range"
    assert resolve_hunting_intensity(0.32, 0.2, "attack_range", cfg) == "side_by_side"
    assert resolve_hunting_intensity(0.40, 0.2, "side_by_side", cfg) == "side_by_side"
    assert resolve_hunting_intensity(0.50, 0.2, "side_by_side", cfg) == "attack_range"


def test_battle_adapter_maps_attack_range_envelope() -> None:
    envelope = battle_race_event_to_envelope(
        RaceEvent(
            name="battle",
            channel="battle",
            priority=20,
            phase="enter",
            timestamp=1.0,
            data={
                "state": "attack_range",
                "targetCarIdx": 17,
                "targetPosition": 6,
                "gap": 0.6,
                "closingRate": 0.22,
            },
        ),
        session_id="sub:1",
        mode="RACE",
        now=10.0,
    )
    assert envelope is not None
    assert envelope.event_type == "ATTACK_RANGE"
    assert envelope.presentation.variant == "attack_range"
    assert envelope.copy.headline_token == "battle.attack_range"
