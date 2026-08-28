"""Legacy WS down-converter from V4 envelopes."""

from __future__ import annotations

from irswitch.events.envelope import make_envelope
from irswitch.overlay.protocol import legacy_from_envelope


def test_legacy_from_lap_complete_envelope() -> None:
    env = make_envelope(
        event_type="LAP_COMPLETE",
        phase="RESULT",
        metrics={"lap": 8, "lapTime": 93.2},
        priority=40,
        monotonic_ms=12000,
    )
    legacy = legacy_from_envelope(env)
    assert legacy["type"] == "event"
    assert legacy["name"] == "lap_complete"
    assert legacy["phase"] == "trigger"
    assert legacy["channel"] == "lap"
    assert legacy["data"]["lap"] == 8
