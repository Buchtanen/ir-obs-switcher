"""EventEngine emitter registry and fault-isolation tests."""

from __future__ import annotations

import logging

from irswitch.events.engine import EventEngine
from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import OverlaySettings


class _FakeEmitter:
    def __init__(self, name: str) -> None:
        self._name = name

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:
        return [
            CandidateEvent(
                name=self._name,
                channel="test",
                priority=1,
                data={"now": now},
            )
        ]


class _FailingEmitter:
    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:
        raise RuntimeError("emitter failed")


def test_register_appends_emitters_in_order() -> None:
    engine = EventEngine(OverlaySettings())
    engine.register(_FakeEmitter("first"))
    engine.register(_FakeEmitter("second"))

    events = engine.tick(RaceState(connected=True, data_quality="ok"), 12.5)

    assert [event.name for event in events][-2:] == ["first", "second"]


def test_emitter_failure_does_not_abort_later_emitters(caplog) -> None:
    engine = EventEngine(OverlaySettings())
    engine.register(_FailingEmitter())
    engine.register(_FakeEmitter("survived"))

    with caplog.at_level(logging.WARNING, logger="irswitch.events.engine"):
        events = engine.tick(RaceState(connected=True, data_quality="ok"), 3.0)

    assert any(event.name == "survived" for event in events)
    assert "_FailingEmitter tick failed" in caplog.text
