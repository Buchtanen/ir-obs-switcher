"""DecisionLog explainability buffer tests."""

from __future__ import annotations

from irswitch.events.decision_log import DecisionLog


def test_records_decisions_and_trims_oldest_entries() -> None:
    decisions = DecisionLog(max_size=2)

    decisions.record("lap_complete", "emitted", "accepted", {"lap": 4}, monotonic_ms=100)
    decisions.record(
        "incident",
        "suppressed",
        "cooldown",
        {"remaining_ms": 50},
        monotonic_ms=200,
    )
    decisions.record("battle", "preempted", "lower_priority", monotonic_ms=300)

    assert decisions.to_list() == [
        {
            "event_type": "incident",
            "action": "suppressed",
            "reason": "cooldown",
            "details": {"remaining_ms": 50},
            "monotonic_ms": 200,
        },
        {
            "event_type": "battle",
            "action": "preempted",
            "reason": "lower_priority",
            "details": {},
            "monotonic_ms": 300,
        },
    ]


def test_latest_and_clear() -> None:
    decisions = DecisionLog()
    decisions.record("lap_complete", "emitted", "accepted", monotonic_ms=100)
    decisions.record("position_change", "suppressed", "pit_cycle", now=0.2)

    latest = decisions.latest(1)[0]
    assert latest["event_type"] == "position_change"
    assert latest["monotonic_ms"] == 200
    decisions.clear()
    assert decisions.to_list() == []
