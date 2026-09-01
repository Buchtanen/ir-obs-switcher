"""N12 peer consumer domain and failure-isolation tests."""

from __future__ import annotations

import time

import pytest

from irswitch.commentary.consumer import CommentaryConsumer
from irswitch.commentary.director import CommentaryDirector
from irswitch.commentary.graph import parse_sequence_graph
from irswitch.commentary.tts import NullTtsSink
from irswitch.events.async_fanout import AsyncEventFanout
from irswitch.events.envelope import make_envelope
from irswitch.events.stream import (
    CONTEXT_SCHEMA_VERSION,
    FillerResult,
    FrozenAcceptedEventBatch,
    SessionReset,
    freeze_accepted_event,
    freeze_context,
)
from irswitch.overlay.bus import OverlayBus
from irswitch.overlay.consumer import OverlayConsumer
from irswitch.overlay.settings import CommentarySchedulerSettings, CommentarySettings


def _graph():
    return parse_sequence_graph(
        {
            "version": 1,
            "locales": ["en"],
            "nodes": {
                "lap": {
                    "family": "lap",
                    "event_types": ["LAP_COMPLETE"],
                    "phases": ["RESULT"],
                    "speak_priority": 50,
                    "cooldown_s": 0,
                    "slots": [],
                    "hr_states": ["unknown"],
                    "variants": {"en": {"neutral": ["A lap is complete."]}},
                }
            },
            "edges": [],
        }
    )


def _context(*, version: int = 1, session_id: str = "session") -> bytes:
    return freeze_context(
        {
            "schema_version": CONTEXT_SCHEMA_VERSION,
            "version": version,
            "session_id": session_id,
            "captured_monotonic_ms": int(time.monotonic() * 1000),
            "identity": {},
            "race": {},
            "bio": {"status": "connected", "connected": True, "hr_state": "focused"},
            "story": {"hero": {"speakable_names": ["Alex"]}},
            "situation": {},
            "config": {},
        }
    )


def _batch(
    *,
    stream_sequence: int = 1,
    event_sequence: int = 1,
    audience: tuple[str, ...] = ("overlay", "commentary"),
    accepted_ms: int | None = None,
    overlay_wire: dict | None = None,
) -> FrozenAcceptedEventBatch:
    envelope = make_envelope(
        event_type="LAP_COMPLETE",
        phase="RESULT",
        mode="RACE",
        event_id=f"session:LAP_COMPLETE:{event_sequence}",
        sequence=event_sequence,
        session_id="session",
        priority=50,
        monotonic_ms=int(time.monotonic() * 1000),
        dedupe_key="lap",
        correlation_id=f"lap:{event_sequence}",
    )
    accepted = freeze_accepted_event(
        envelope,
        audiences=audience,  # type: ignore[arg-type]
        source="event_engine",
        source_ordinal=0,
        overlay_payload=overlay_wire,
    )
    return FrozenAcceptedEventBatch(
        stream_sequence,
        "session",
        event_sequence,
        accepted_ms if accepted_ms is not None else int(time.monotonic() * 1000),
        1,
        _context(),
        (accepted,),
    )


@pytest.mark.asyncio
async def test_overlay_consumer_uses_frozen_public_wire_and_discards_commentary_only() -> None:
    class _RecordingBus(OverlayBus):
        def __init__(self) -> None:
            super().__init__()
            self.wires: list[dict] = []

        async def publish_event(self, envelope: dict) -> None:
            self.wires.append(envelope)
            await super().publish_event(envelope)

    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("overlay")
    bus = _RecordingBus()
    consumer = OverlayConsumer(subscription, bus)
    custom_wire = {"type": "event", "name": "lap_complete", "format": "legacy"}

    await consumer.handle(_batch(overlay_wire=custom_wire))
    assert bus.wires[-1] == custom_wire

    commentary_only = _batch(
        stream_sequence=2,
        event_sequence=2,
        audience=("commentary",),
    )
    before = len(bus.wires)
    await consumer.handle(commentary_only)
    assert len(bus.wires) == before


@pytest.mark.asyncio
async def test_commentary_consumer_thaws_and_speaks_without_overlay_bus() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("commentary")
    subscription.replace_latest_context(_context())
    sink = NullTtsSink()
    settings = CommentarySettings(enabled=True, cooldown_s=0)
    director = CommentaryDirector(graph=_graph(), settings=settings, sink=sink)
    consumer = CommentaryConsumer(subscription, director, lambda: (settings, "en"))

    await consumer.handle(_batch())

    assert [item.text for item in sink.spoken] == ["A lap is complete."]
    assert director.hero_names() == ("Alex",)


@pytest.mark.asyncio
async def test_commentary_consumer_uses_event_time_ttl_and_is_idempotent() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("commentary")
    subscription.replace_latest_context(_context())
    sink = NullTtsSink()
    settings = CommentarySettings(
        enabled=True,
        cooldown_s=0,
        scheduler=CommentarySchedulerSettings(default_ttl_s=1.0),
    )
    director = CommentaryDirector(graph=_graph(), settings=settings, sink=sink)
    consumer = CommentaryConsumer(subscription, director, lambda: (settings, "en"))
    expired = _batch(accepted_ms=int((time.monotonic() - 2.0) * 1000))

    await consumer.handle(expired)
    await consumer.handle(expired)

    assert sink.spoken == []
    assert consumer.expired == 1
    assert consumer.duplicates == 1
    assert director.decisions()[-1]["reason"] == "event_expired"


@pytest.mark.asyncio
async def test_reset_clears_duplicate_ledger() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("commentary")
    subscription.replace_latest_context(_context())
    sink = NullTtsSink()
    settings = CommentarySettings(enabled=True, cooldown_s=0)
    director = CommentaryDirector(graph=_graph(), settings=settings, sink=sink)
    consumer = CommentaryConsumer(subscription, director, lambda: (settings, "en"))
    batch = _batch()

    await consumer.handle(batch)
    await consumer.handle(SessionReset("session", "session", "test", 2))
    await consumer.handle(
        FrozenAcceptedEventBatch(
            3,
            batch.session_id,
            2,
            batch.accepted_monotonic_ms,
            batch.context_version,
            batch.context_payload,
            batch.events,
        )
    )

    assert len(sink.spoken) == 2


def test_filler_request_is_bounded_and_completed_by_typed_result() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("commentary")
    subscription.replace_latest_context(_context())
    settings = CommentarySettings(enabled=True)
    director = CommentaryDirector(graph=_graph(), settings=settings, sink=NullTtsSink())
    consumer = CommentaryConsumer(subscription, director, lambda: (settings, "en"))

    assert consumer._request_filler(time.monotonic()) is None
    assert consumer._request_filler(time.monotonic()) is None
    request = consumer.take_filler_request()
    assert request is not None
    consumer.complete_filler(FillerResult(request.request_id, "no_fact"))
    assert consumer.status_snapshot()["fillerOutstanding"] is False
