"""EventManager v2 lap vertical slice tests."""

from __future__ import annotations

from irswitch.events.manager_v2 import EventManagerV2, event_v4_wire
from irswitch.overlay.protocol import CandidateEvent


def test_lap_complete_v4_envelope_with_sequence() -> None:
    mgr = EventManagerV2(session_id="sub:1")
    mgr.set_session_id("sub:1")
    race, env = mgr.submit(
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
    assert env is not None
    assert env.event_type == "LAP_COMPLETE"
    assert env.phase == "RESULT"
    assert env.sequence == 1
    assert env.session_id == "sub:1"
    wire = event_v4_wire(env)
    assert wire["format"] == "v4"
    assert wire["eventType"] == "LAP_COMPLETE"
    assert wire["metrics"]["lap"] == 12


def test_personal_best_v4_envelope() -> None:
    mgr = EventManagerV2()
    _, env = mgr.submit(
        CandidateEvent(
            name="personal_best",
            channel="lap",
            priority=60,
            phase="trigger",
            data={"lap": 5, "lapTime": 90.0, "bestLap": 90.0, "personalBest": True},
        ),
        1.0,
        mode="PRACTICE",
    )
    assert env is not None
    assert env.event_type == "PERSONAL_BEST"
    assert env.mode == "PRACTICE"
    assert env.copy.headline_token == "lap.personal_best"


def test_non_lap_event_falls_back_to_legacy_wire() -> None:
    mgr = EventManagerV2()
    race, env = mgr.submit(
        CandidateEvent(name="incident", channel="alert", priority=90, phase="trigger"),
        1.0,
    )
    assert race is not None
    assert env is None
    wire = mgr.publish_wire(env, race)
    assert wire is not None
    assert wire.get("format") != "v4"
    assert wire["name"] == "incident"


def test_tick_exit_stamps_sequence() -> None:
    mgr = EventManagerV2()
    mgr.submit(
        CandidateEvent(
            name="lap_complete", channel="lap", priority=40, phase="trigger", duration=0.5
        ),
        1.0,
    )
    expired = mgr.tick(2.0)
    assert expired
    race, env = expired[0]
    assert race.phase == "exit"
    assert env is not None
    assert env.phase == "EXIT"
    assert env.sequence == 2
