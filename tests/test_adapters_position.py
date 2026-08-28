"""Position / overtake V4 adapter tests."""

from __future__ import annotations

from irswitch.events.adapters.position import position_race_event_to_envelope
from irswitch.events.manager_v2 import EventManagerV2, event_v4_wire
from irswitch.overlay.protocol import CandidateEvent, RaceEvent


def _position_change_event(*, direction: str) -> RaceEvent:
    old_position = 8 if direction == "gain" else 7
    new_position = 7 if direction == "gain" else 8
    delta = old_position - new_position
    return RaceEvent(
        name="position_change",
        channel="alert",
        priority=70,
        phase="trigger",
        timestamp=1.0,
        data={
            "direction": direction,
            "oldPosition": old_position,
            "newPosition": new_position,
            "delta": delta,
        },
    )


def test_position_gain_envelope_event_type_and_result_phase() -> None:
    envelope = position_race_event_to_envelope(
        _position_change_event(direction="gain"),
        session_id="sub:1",
        mode="RACE",
        now=10.0,
    )
    assert envelope is not None
    assert envelope.event_type == "POSITION_GAINED"
    assert envelope.phase == "RESULT"
    assert envelope.presentation.variant == "position_gained"
    assert envelope.presentation.preferred_state == "RESULT"
    assert envelope.copy.headline_token == "position.gained"


def test_position_loss_envelope_maps_to_position_lost() -> None:
    envelope = position_race_event_to_envelope(
        _position_change_event(direction="loss"),
        session_id="sub:1",
        mode="RACE",
        now=10.0,
    )
    assert envelope is not None
    assert envelope.event_type == "POSITION_LOST"
    assert envelope.presentation.variant == "position_lost"
    assert envelope.presentation.accent == "warning"


def test_overtake_envelope_uses_catalog_state() -> None:
    envelope = position_race_event_to_envelope(
        RaceEvent(
            name="overtake",
            channel="alert",
            priority=80,
            phase="trigger",
            timestamp=2.0,
            data={"oldPosition": 7, "newPosition": 6},
        ),
        session_id="sub:1",
        mode="RACE",
        now=12.0,
    )
    assert envelope is not None
    assert envelope.event_type == "OVERTAKE"
    assert envelope.phase == "RESULT"
    assert envelope.presentation.variant == "overtake"


def test_manager_v2_inject_position_gain_emits_v4() -> None:
    mgr = EventManagerV2(session_id="sub:1")
    race, envelopes = mgr.inject("position_gain", 5.0)
    assert race is not None
    assert len(envelopes) == 1
    env = envelopes[0]
    assert env.event_type == "POSITION_GAINED"
    assert env.phase == "RESULT"
    assert env.sequence == 1
    wire = event_v4_wire(env)
    assert wire["format"] == "v4"
    assert wire["eventType"] == "POSITION_GAINED"
    assert wire["presentation"]["variant"] == "position_gained"


def test_manager_v2_submit_position_change_emits_v4() -> None:
    mgr = EventManagerV2(session_id="sub:1")
    _, envelopes = mgr.submit(
        CandidateEvent(
            name="position_change",
            channel="alert",
            priority=70,
            phase="trigger",
            data={"direction": "gain", "oldPosition": 8, "newPosition": 7, "delta": 1},
        ),
        3.0,
        mode="RACE",
    )
    assert len(envelopes) == 1
    assert envelopes[0].event_type == "POSITION_GAINED"
    assert envelopes[0].phase == "RESULT"
