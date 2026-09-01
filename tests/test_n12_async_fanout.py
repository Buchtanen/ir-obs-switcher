"""N12 A6 broadcast, backpressure, isolation, and idempotence tests."""

from __future__ import annotations

import asyncio
import time

import pytest

from irswitch.events.async_fanout import AsyncEventFanout
from irswitch.events.envelope import make_envelope
from irswitch.events.stream import (
    CONTEXT_SCHEMA_VERSION,
    FrozenAcceptedEventBatch,
    SessionReset,
    freeze_accepted_event,
    freeze_context,
)
from irswitch.events.worker import StreamWorker


def _context(version: int = 1) -> bytes:
    return freeze_context(
        {
            "schema_version": CONTEXT_SCHEMA_VERSION,
            "version": version,
            "session_id": "session",
            "captured_monotonic_ms": 1_000,
            "identity": {},
            "race": {},
            "bio": {},
            "story": {},
            "situation": {},
            "config": {},
        }
    )


def _batch(
    stream_sequence: int,
    event_sequence: int,
    *,
    event_type: str = "LAP_COMPLETE",
    phase: str = "RESULT",
    priority: int = 50,
    coalesce_key: tuple[str, ...] | None = None,
) -> FrozenAcceptedEventBatch:
    envelope = make_envelope(
        event_type=event_type,
        phase=phase,
        mode="RACE",
        event_id=f"session:{event_type}:{event_sequence}",
        sequence=event_sequence,
        session_id="session",
        priority=priority,
        monotonic_ms=1_000 + event_sequence,
        dedupe_key=event_type,
        correlation_id=f"{event_type}:relation",
        metrics={"sample": event_sequence},
    )
    accepted = freeze_accepted_event(
        envelope,
        audiences=("overlay", "commentary"),
        source="event_engine",
        source_ordinal=0,
        coalesce_key=coalesce_key,
    )
    return FrozenAcceptedEventBatch(
        stream_sequence,
        "session",
        event_sequence,
        1_000 + event_sequence,
        1,
        _context(),
        (accepted,),
    )


@pytest.mark.asyncio
async def test_broadcast_is_non_blocking_and_delivers_identical_ids() -> None:
    fanout = AsyncEventFanout()
    overlay = fanout.subscribe("overlay", capacity=4)
    commentary = fanout.subscribe("commentary", capacity=4)
    item = _batch(1, 1)

    started = time.perf_counter()
    assert fanout.publish(item) == {"overlay": True, "commentary": True}
    assert time.perf_counter() - started < 0.05

    overlay_item, commentary_item = await asyncio.gather(overlay.get(), commentary.get())
    assert overlay_item is commentary_item
    assert overlay_item.events[0].event_id == commentary_item.events[0].event_id


@pytest.mark.asyncio
async def test_slow_commentary_does_not_delay_overlay_worker() -> None:
    fanout = AsyncEventFanout()
    overlay_sub = fanout.subscribe("overlay", capacity=8)
    commentary_sub = fanout.subscribe("commentary", capacity=8)
    overlay_seen = asyncio.Event()
    commentary_release = asyncio.Event()

    async def overlay_handle(item) -> None:
        overlay_seen.set()

    async def commentary_handle(item) -> None:
        await commentary_release.wait()

    overlay_worker = StreamWorker("overlay", overlay_sub, overlay_handle)
    commentary_worker = StreamWorker("commentary", commentary_sub, commentary_handle)
    tasks = [
        asyncio.create_task(overlay_worker.run()),
        asyncio.create_task(commentary_worker.run()),
    ]
    try:
        fanout.publish(_batch(1, 1))
        await asyncio.wait_for(overlay_seen.wait(), timeout=0.2)
        assert not commentary_release.is_set()
        assert overlay_worker.processed == 1
    finally:
        commentary_release.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.asyncio
async def test_update_coalesces_but_finish_is_never_evicted() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("overlay", capacity=2)
    relation = ("session", "front", "1", "2", "1", "hunting")
    fanout.publish(_batch(1, 1, event_type="HUNTING", phase="UPDATE", coalesce_key=relation))
    fanout.publish(_batch(2, 2, event_type="LAP_COMPLETE"))
    fanout.publish(_batch(3, 3, event_type="HUNTING", phase="UPDATE", coalesce_key=relation))

    first = await subscription.get()
    second = await subscription.get()
    ids = {event.event_id for item in (first, second) for event in item.events}
    assert "session:HUNTING:1" not in ids
    assert ids == {"session:HUNTING:3", "session:LAP_COMPLETE:2"}

    fanout.publish(_batch(4, 4, event_type="FINISH", priority=95))
    assert (await subscription.get()).events[0].event_id == "session:FINISH:4"


@pytest.mark.asyncio
async def test_processed_event_id_is_idempotent_and_reset_clears_ledger() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("commentary", capacity=8)
    seen: list[str] = []

    async def handle(item) -> None:
        if isinstance(item, FrozenAcceptedEventBatch):
            seen.extend(event.event_id for event in item.events)

    worker = StreamWorker("commentary", subscription, handle)
    task = asyncio.create_task(worker.run())
    try:
        first = _batch(1, 1)
        duplicate = FrozenAcceptedEventBatch(
            2,
            first.session_id,
            2,
            first.accepted_monotonic_ms,
            first.context_version,
            first.context_payload,
            first.events,
        )
        fanout.publish(first)
        fanout.publish(duplicate)
        fanout.publish(SessionReset("session", "session", "test", 3))
        replay = FrozenAcceptedEventBatch(
            4,
            first.session_id,
            3,
            first.accepted_monotonic_ms,
            first.context_version,
            first.context_payload,
            first.events,
        )
        fanout.publish(replay)
        for _ in range(20):
            if worker.processed >= 3:
                break
            await asyncio.sleep(0)
        assert seen == ["session:LAP_COMPLETE:1", "session:LAP_COMPLETE:1"]
        assert worker.duplicates == 1
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
