"""N12.0 characterization of the pre-V2 synchronous event path.

These tests deliberately describe the landing state from #181.  The async
regression tests live beside the V2 transport once it replaces this path.
"""

from __future__ import annotations

import time

from irswitch.events.envelope import EventEnvelope, make_envelope
from irswitch.events.fanout import EventFanout
from irswitch.race.observer import RaceObserver


def _event(event_type: str, sequence: int) -> EventEnvelope:
    return make_envelope(
        event_type=event_type,
        phase="RESULT",
        mode="RACE",
        event_id=f"session:{event_type}:{sequence}",
        sequence=sequence,
        session_id="session",
        priority=50,
        monotonic_ms=1_000,
        correlation_id=event_type.lower(),
        metrics={"source": event_type.lower()},
    )


class _SlowConsumer:
    def __init__(self, delay_s: float) -> None:
        self.delay_s = delay_s
        self.seen: list[str] = []

    def on_envelopes(self, envelopes: list[EventEnvelope], *, now: float) -> None:
        time.sleep(self.delay_s)
        self.seen.extend(envelope.event_id for envelope in envelopes)


class _RecordingConsumer:
    def __init__(self) -> None:
        self.seen: list[str] = []

    def on_envelopes(self, envelopes: list[EventEnvelope], *, now: float) -> None:
        self.seen.extend(envelope.event_id for envelope in envelopes)


def test_n12_baseline_fanout_is_ordered_but_inline() -> None:
    """#181 fan-out waits for the first consumer before invoking its peer."""
    fanout = EventFanout()
    slow = _SlowConsumer(0.025)
    peer = _RecordingConsumer()
    fanout.register(slow)
    fanout.register(peer)

    started = time.perf_counter()
    fanout.emit([_event("INCIDENT", 1), _event("INCIDENT_AFTERMATH", 2)], now=1.0)
    elapsed = time.perf_counter() - started

    assert elapsed >= 0.02
    assert slow.seen == ["session:INCIDENT:1", "session:INCIDENT_AFTERMATH:2"]
    assert peer.seen == slow.seen


def test_n12_baseline_fanout_shares_mutable_envelopes() -> None:
    """Freeze the mutable-reference hazard that A1 must remove at the V2 boundary."""

    class _MutatingConsumer:
        def on_envelopes(self, envelopes: list[EventEnvelope], *, now: float) -> None:
            envelopes[0].metrics["consumer"] = "mutated"

    class _MetricsConsumer:
        def __init__(self) -> None:
            self.metrics: dict[str, object] = {}

        def on_envelopes(self, envelopes: list[EventEnvelope], *, now: float) -> None:
            self.metrics = dict(envelopes[0].metrics)

    fanout = EventFanout()
    recorder = _MetricsConsumer()
    fanout.register(_MutatingConsumer())
    fanout.register(recorder)
    fanout.emit([_event("LAP_COMPLETE", 1)], now=1.0)

    assert recorder.metrics["consumer"] == "mutated"


def test_n12_baseline_source_order_is_documented() -> None:
    """The #181 derived drain order is stable before shared arbitration moves it."""

    class _Pending:
        def __init__(self, name: str, sequence: int) -> None:
            self._event = _event(name, sequence)

        def take_pending(self) -> list[EventEnvelope]:
            return [self._event]

    observer = RaceObserver()
    observer.narrative = _Pending("SESSION_PREVIEW", 1)  # type: ignore[assignment]
    observer.aftermath = _Pending("INCIDENT_AFTERMATH", 2)  # type: ignore[assignment]
    observer.flags = _Pending("SESSION_FLAG", 3)  # type: ignore[assignment]
    observer.timing_hunt = _Pending("PACE_HUNT", 4)  # type: ignore[assignment]
    observer.grid_story = _Pending("GRID_STORY", 5)  # type: ignore[assignment]

    assert [item.event_type for item in observer.take_derived_envelopes()] == [
        "SESSION_PREVIEW",
        "INCIDENT_AFTERMATH",
        "SESSION_FLAG",
        "PACE_HUNT",
        "GRID_STORY",
    ]
