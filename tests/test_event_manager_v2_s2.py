"""S2 gate: preemption EXIT envelopes, pit-cycle suppression, DecisionLog."""

from __future__ import annotations

from irswitch.events.manager_v2 import EventManagerV2
from irswitch.overlay.protocol import CandidateEvent


def test_pit_cycle_suppresses_position_change() -> None:
    mgr = EventManagerV2()
    mgr.update_pit_state(True, 1.0)
    race, envelopes = mgr.submit(
        CandidateEvent(
            name="position_change",
            channel="alert",
            priority=70,
            phase="trigger",
            data={"direction": "gain", "oldPosition": 8, "newPosition": 7, "delta": 1},
        ),
        1.0,
    )
    assert race is None
    assert envelopes == []
    latest = mgr.decisions.latest(1)[0]
    assert latest["action"] == "suppressed"
    assert latest["reason"] == "pit_cycle"


def test_pit_cycle_grace_after_exit() -> None:
    mgr = EventManagerV2()
    mgr.update_pit_state(True, 1.0)
    mgr.update_pit_state(False, 2.0)
    race, envelopes = mgr.submit(
        CandidateEvent(
            name="overtake",
            channel="alert",
            priority=80,
            phase="trigger",
            data={"oldPosition": 7, "newPosition": 6},
        ),
        2.5,
    )
    assert race is None
    assert envelopes == []
    assert mgr.decisions.latest(1)[0]["reason"] == "pit_cycle"


def test_lap_preemption_emits_exit_envelope() -> None:
    mgr = EventManagerV2(session_id="sub:1")
    mgr.submit(
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
    assert len(mgr.active_stories_v4()) == 0  # RESULT not tracked
    _, envelopes = mgr.submit(
        CandidateEvent(
            name="personal_best",
            channel="lap",
            priority=60,
            phase="trigger",
            duration=4.0,
            data={"lap": 12, "lapTime": 90.0, "bestLap": 90.0, "deltaToBest": 0.0},
        ),
        10.5,
        mode="RACE",
    )
    phases = [env.phase for env in envelopes]
    assert "EXIT" in phases
    assert "RESULT" in phases
    exit_env = next(env for env in envelopes if env.phase == "EXIT")
    assert exit_env.event_type == "LAP_COMPLETE"
    preempt = mgr.decisions.latest(3)
    assert any(entry["action"] == "preempted" for entry in preempt)


def test_battle_stories_survive_correlated_updates() -> None:
    mgr = EventManagerV2()
    _, first = mgr.submit(
        CandidateEvent(
            name="battle",
            channel="battle",
            priority=20,
            phase="enter",
            data={"state": "hunting", "targetCarIdx": 17, "gap": 2.0},
        ),
        1.0,
    )
    assert len(first) == 2
    assert len(mgr.active_stories_v4()) == 1
    _, updated = mgr.submit(
        CandidateEvent(
            name="battle",
            channel="battle",
            priority=20,
            phase="update",
            data={"state": "hunting", "targetCarIdx": 17, "gap": 1.5},
        ),
        2.0,
    )
    assert len(updated) == 1
    assert updated[0].phase == "UPDATE"
    assert len(mgr.active_stories_v4()) == 1
    assert mgr.active_stories_v4()[0]["metrics"]["gap"] == 1.5


def test_cooldown_suppression_logged() -> None:
    mgr = EventManagerV2()
    mgr.submit(
        CandidateEvent(
            name="incident",
            channel="alert",
            priority=90,
            phase="trigger",
            duration=2.0,
            cooldown=5.0,
        ),
        1.0,
    )
    mgr.submit(
        CandidateEvent(
            name="incident",
            channel="alert",
            priority=90,
            phase="trigger",
            duration=2.0,
            cooldown=5.0,
        ),
        2.0,
    )
    latest = mgr.decisions.latest(1)[0]
    assert latest["reason"] == "cooldown"
    assert latest["action"] == "suppressed"
