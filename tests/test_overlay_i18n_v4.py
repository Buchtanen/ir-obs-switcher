"""V4 overlay i18n: adapter copy tokens resolve in EN + CS catalogs."""

from __future__ import annotations

from irswitch.events.adapters.battle import battle_race_event_to_envelope
from irswitch.events.adapters.bio import bio_race_event_to_envelope
from irswitch.events.adapters.exception_extra import (
    incident_race_event_to_envelope,
    invalid_lap_race_event_to_envelope,
)
from irswitch.events.adapters.lap import lap_race_event_to_envelope
from irswitch.events.adapters.pit import pit_race_event_to_envelope
from irswitch.events.adapters.position import position_race_event_to_envelope
from irswitch.overlay.i18n import CS, EN, copy_catalog_for_renderer, resolve_copy
from irswitch.overlay.protocol import RaceEvent

TOKENS_REQUIRED = frozenset(
    {
        "battle.hunting",
        "battle.hunted",
        "battle.closing_in",
        "battle.approach",
        "battle.attack_range",
        "battle.side_by_side",
        "battle.battle_for_position",
        "battle.won",
        "lap.complete",
        "lap.personal_best",
        "position.gained",
        "position.lost",
        "position.overtake",
        "position.rival_threat",
        "session.final_lap",
        "session.finish",
        "incident",
        "exception.incident",
        "exception.invalid_lap",
        "exception.link_drop",
        "pit.entry",
        "pit.lane",
        "pit.stopped",
        "pit.released",
        "pit.exit",
        "pit.outcome",
        "bio.hr_high",
        "bio.hr_pressure",
        "ble.lost",
        "timing.gain_found",
        "timing.sector_best",
        "timing.sector_split",
    }
)

CS_DIFFERS_FROM_EN = frozenset(
    {
        "battle.hunting",
        "battle.hunted",
        "battle.closing_in",
        "battle.approach",
        "battle.attack_range",
        "battle.side_by_side",
        "battle.battle_for_position",
        "battle.won",
        "lap.complete",
        "lap.personal_best",
        "position.gained",
        "position.lost",
        "position.overtake",
        "position.rival_threat",
        "session.final_lap",
        "session.finish",
        "exception.invalid_lap",
        "exception.link_drop",
        "pit.entry",
        "pit.lane",
        "pit.stopped",
        "pit.released",
        "pit.exit",
        "pit.outcome",
        "bio.hr_high",
        "bio.hr_pressure",
        "ble.lost",
        "timing.gain_found",
        "timing.sector_best",
        "timing.sector_split",
    }
)


def _headline_from_adapter(event: RaceEvent) -> str | None:
    for adapter in (
        lap_race_event_to_envelope,
        battle_race_event_to_envelope,
        position_race_event_to_envelope,
        pit_race_event_to_envelope,
        bio_race_event_to_envelope,
        incident_race_event_to_envelope,
        invalid_lap_race_event_to_envelope,
    ):
        envelope = adapter(event, session_id="sub:1", mode="RACE", now=1.0)
        if envelope is not None:
            token = envelope.copy.headline_token
            return token if token else None
    return None


def test_en_catalog_covers_all_required_tokens() -> None:
    assert TOKENS_REQUIRED <= set(EN)
    assert all(EN[token] for token in TOKENS_REQUIRED)


def test_cs_catalog_matches_en_keys() -> None:
    assert set(CS) == set(EN)
    assert TOKENS_REQUIRED <= set(CS)


def test_cs_differs_from_en_for_key_tokens() -> None:
    for token in CS_DIFFERS_FROM_EN:
        assert CS[token] != EN[token], token


def test_copy_catalog_for_renderer_includes_all_tokens() -> None:
    catalog = copy_catalog_for_renderer("cs")
    assert TOKENS_REQUIRED <= set(catalog)


def test_adapter_copy_tokens_resolve_en_and_cs() -> None:
    samples: list[RaceEvent] = [
        RaceEvent(
            name="lap_complete",
            channel="alert",
            priority=40,
            phase="trigger",
            timestamp=0.0,
            data={"lap": 1, "lapTime": 90.0},
        ),
        RaceEvent(
            name="personal_best",
            channel="alert",
            priority=60,
            phase="trigger",
            timestamp=0.0,
            data={"lap": 2, "lapTime": 89.0},
        ),
        RaceEvent(
            name="battle",
            channel="alert",
            priority=20,
            phase="enter",
            timestamp=0.0,
            data={"state": "hunting", "gap": 1.0},
        ),
        RaceEvent(
            name="battle",
            channel="alert",
            priority=20,
            phase="enter",
            timestamp=0.0,
            data={"state": "approach", "gap": 1.2},
        ),
        RaceEvent(
            name="battle",
            channel="alert",
            priority=20,
            phase="enter",
            timestamp=0.0,
            data={"state": "attack_range", "gap": 0.4},
        ),
        RaceEvent(
            name="battle",
            channel="alert",
            priority=20,
            phase="enter",
            timestamp=0.0,
            data={"state": "side_by_side", "gap": 0.05},
        ),
        RaceEvent(
            name="position_change",
            channel="alert",
            priority=70,
            phase="trigger",
            timestamp=0.0,
            data={"direction": "gain", "oldPosition": 8, "newPosition": 7, "delta": 1},
        ),
        RaceEvent(
            name="overtake",
            channel="alert",
            priority=80,
            phase="trigger",
            timestamp=0.0,
            data={"oldPosition": 7, "newPosition": 6},
        ),
        RaceEvent(
            name="pit_story",
            channel="session",
            priority=50,
            phase="enter",
            timestamp=0.0,
            data={"state": "entry", "correlationId": "pit:1"},
        ),
        RaceEvent(
            name="pit_story",
            channel="session",
            priority=50,
            phase="update",
            timestamp=0.0,
            data={"state": "lane", "correlationId": "pit:1"},
        ),
        RaceEvent(
            name="pit_story",
            channel="session",
            priority=50,
            phase="update",
            timestamp=0.0,
            data={"state": "stopped", "correlationId": "pit:1"},
        ),
        RaceEvent(
            name="pit_story",
            channel="session",
            priority=50,
            phase="update",
            timestamp=0.0,
            data={"state": "released", "correlationId": "pit:1"},
        ),
        RaceEvent(
            name="pit_story",
            channel="session",
            priority=50,
            phase="update",
            timestamp=0.0,
            data={"state": "exit", "correlationId": "pit:1"},
        ),
        RaceEvent(
            name="pit_story",
            channel="session",
            priority=50,
            phase="trigger",
            timestamp=0.0,
            data={"state": "outcome", "correlationId": "pit:1"},
        ),
        RaceEvent(
            name="hr_pressure",
            channel="bio",
            priority=35,
            phase="enter",
            timestamp=0.0,
            data={"state": "hr_pressure", "bpm": 160},
        ),
        RaceEvent(
            name="battle",
            channel="battle",
            priority=30,
            phase="enter",
            timestamp=0.0,
            data={"state": "battle_for_position", "gap": 0.5},
        ),
        RaceEvent(
            name="rival_threat",
            channel="alert",
            priority=70,
            phase="enter",
            timestamp=0.0,
            data={"gap": 1.0, "closingRate": 0.5, "targetCarIdx": 3, "targetName": "X"},
        ),
        RaceEvent(
            name="incident",
            channel="alert",
            priority=90,
            phase="trigger",
            timestamp=0.0,
            data={"value": 2, "total": 4},
        ),
        RaceEvent(
            name="invalid_lap",
            channel="alert",
            priority=88,
            phase="trigger",
            timestamp=0.0,
            data={"lap": 4},
        ),
    ]

    seen: set[str] = set()
    for event in samples:
        token = _headline_from_adapter(event)
        assert token, f"no adapter token for {event.name} {event.data}"
        seen.add(token)
        assert resolve_copy(token, "en") == EN[token]
        assert resolve_copy(token, "cs") == CS[token]

    assert "pit.lane" in seen
    assert "pit.outcome" in seen
    assert "position.overtake" in seen
    assert "battle.side_by_side" in seen
    assert "battle.battle_for_position" in seen
    assert "position.rival_threat" in seen
    assert "exception.incident" in seen
    assert "exception.invalid_lap" in seen


def test_rival_threat_and_battle_for_position_set_max_hold() -> None:
    rival = position_race_event_to_envelope(
        RaceEvent(
            name="rival_threat",
            channel="alert",
            priority=70,
            phase="enter",
            timestamp=0.0,
            data={"gap": 1.0, "closingRate": 0.5, "targetCarIdx": 3},
        ),
        session_id="s",
        mode="RACE",
        now=1.0,
    )
    assert rival is not None
    assert rival.presentation.max_hold_ms == 8000

    duel = battle_race_event_to_envelope(
        RaceEvent(
            name="battle",
            channel="battle",
            priority=30,
            phase="enter",
            timestamp=0.0,
            data={"state": "battle_for_position"},
        ),
        session_id="s",
        mode="RACE",
        now=1.0,
    )
    assert duel is not None
    assert duel.presentation.max_hold_ms == 8000
    hunting = battle_race_event_to_envelope(
        RaceEvent(
            name="battle",
            channel="battle",
            priority=20,
            phase="enter",
            timestamp=0.0,
            data={"state": "hunting", "gap": 1.0},
        ),
        session_id="s",
        mode="RACE",
        now=1.0,
    )
    assert hunting is not None
    assert hunting.presentation.max_hold_ms == 0


def test_pit_lane_adapter_emits_pit_lane_token() -> None:
    envelope = pit_race_event_to_envelope(
        RaceEvent(
            name="pit_story",
            channel="session",
            priority=50,
            phase="update",
            timestamp=1.0,
            data={"state": "lane", "correlationId": "pit:sub:1:2", "position": 5},
        ),
        session_id="sub:1",
        mode="RACE",
        now=2.0,
    )
    assert envelope is not None
    assert envelope.event_type == "PIT_LANE"
    assert envelope.copy.headline_token == "pit.lane"
