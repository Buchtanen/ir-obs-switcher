"""Unit tests for EventFanout peer delivery."""

from __future__ import annotations

from irswitch.events.envelope import make_envelope
from irswitch.events.fanout import EventFanout


def _env(event_type: str = "LAP_COMPLETE", *, now: float = 1.0):
    return make_envelope(
        event_type=event_type,
        phase="RESULT",
        mode="RACE",
        priority=40,
        monotonic_ms=int(now * 1000),
        metrics={},
        correlation_id=event_type,
    )


class _RecordingConsumer:
    def __init__(self) -> None:
        self.batches: list[tuple[list[str], float]] = []

    def on_envelopes(self, envelopes, *, now: float) -> None:
        self.batches.append(([e.event_type for e in envelopes], now))


class _BoomConsumer:
    def on_envelopes(self, envelopes, *, now: float) -> None:
        raise RuntimeError("boom")


def test_fanout_delivers_to_all_consumers() -> None:
    fanout = EventFanout()
    a = _RecordingConsumer()
    b = _RecordingConsumer()
    fanout.register(a)
    fanout.register(b)
    env = _env(now=10.0)
    fanout.emit([env], now=10.0)
    assert a.batches == [(["LAP_COMPLETE"], 10.0)]
    assert b.batches == [(["LAP_COMPLETE"], 10.0)]


def test_fanout_skips_empty_batch() -> None:
    fanout = EventFanout()
    a = _RecordingConsumer()
    fanout.register(a)
    fanout.emit([], now=1.0)
    assert a.batches == []


def test_fanout_isolates_consumer_failures() -> None:
    fanout = EventFanout()
    ok = _RecordingConsumer()
    fanout.register(_BoomConsumer())
    fanout.register(ok)
    fanout.emit([_env(now=2.0)], now=2.0)
    assert ok.batches == [(["LAP_COMPLETE"], 2.0)]


def test_fanout_clear_removes_consumers() -> None:
    fanout = EventFanout()
    a = _RecordingConsumer()
    fanout.register(a)
    assert fanout.consumer_count == 1
    fanout.clear()
    assert fanout.consumer_count == 0
    fanout.emit([_env()], now=1.0)
    assert a.batches == []


def test_commentary_event_consumer_forwards() -> None:
    from irswitch.commentary.consumer import CommentaryEventConsumer

    seen: list[tuple[int, float]] = []

    def observe(envelopes, now: float):
        seen.append((len(envelopes), now))

    consumer = CommentaryEventConsumer(observe)
    fanout = EventFanout()
    fanout.register(consumer)
    fanout.emit([_env(), _env("INCIDENT")], now=3.5)
    assert seen == [(2, 3.5)]
