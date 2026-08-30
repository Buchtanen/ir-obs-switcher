"""EventManager v2 lap + battle slice tests."""

from __future__ import annotations

from irswitch.events.manager_v2 import EventManagerV2, event_v4_wire
from irswitch.overlay.protocol import CandidateEvent


def test_lap_complete_v4_envelope_with_sequence() -> None:
    mgr = EventManagerV2(session_id="sub:1")
    mgr.set_session_id("sub:1")
    race, envelopes = mgr.submit(
        CandidateEvent(
            name="lap_complete",
            channel="lap",
            priority=40,
            phase="trigger",
            duration=4.0,
            data={"lap": 12, "lapTime": 92.1, "bestLap": 91.5, "deltaToBest": 0.6},
        ),
        10.0,
        mode="RACE",
    )
    assert race is not None
    assert len(envelopes) == 1
    env = envelopes[0]
    assert env.event_type == "LAP_COMPLETE"
    assert env.phase == "RESULT"
    assert env.sequence == 1
    wire = event_v4_wire(env)
    assert wire["format"] == "v4"


def test_battle_enter_emits_active_followup() -> None:
    mgr = EventManagerV2()
    _, envelopes = mgr.submit(
        CandidateEvent(
            name="battle",
            channel="battle",
            priority=20,
            phase="enter",
            data={"state": "hunting", "targetCarIdx": 17, "gap": 2.0, "closingRate": 0.3},
        ),
        1.0,
        mode="RACE",
    )
    assert len(envelopes) == 2
    assert envelopes[0].phase == "ENTER"
    assert envelopes[1].phase == "ACTIVE"
    assert envelopes[0].event_type == "HUNTING"
    assert envelopes[0].sequence == 1
    assert envelopes[1].sequence == 2
    assert len(mgr.active_stories_v4()) == 1


def test_battle_update_single_envelope() -> None:
    mgr = EventManagerV2()
    mgr.submit(
        CandidateEvent(
            name="battle",
            channel="battle",
            priority=20,
            phase="enter",
            data={"state": "hunted", "targetCarIdx": 8, "gap": 1.0},
        ),
        1.0,
    )
    _, envelopes = mgr.submit(
        CandidateEvent(
            name="battle",
            channel="battle",
            priority=20,
            phase="update",
            data={"state": "hunted", "targetCarIdx": 8, "gap": 0.8},
        ),
        2.0,
    )
    assert len(envelopes) == 1
    assert envelopes[0].phase == "UPDATE"


def test_unsupported_event_falls_back_to_legacy_wire() -> None:
    mgr = EventManagerV2()
    race, envelopes = mgr.submit(
        CandidateEvent(name="cpu_temp_high", channel="system", priority=10, phase="trigger"),
        1.0,
    )
    assert race is not None
    assert envelopes == []
    wires = mgr.publish_wire(envelopes, race)
    assert wires[0]["name"] == "cpu_temp_high"
    assert wires[0].get("format") != "v4"
