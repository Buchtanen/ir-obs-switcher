"""#284 NarrativeShadowConsumer — optional peer beside CommentaryConsumer."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from test_n12_consumers import _batch
from test_narrative_context_batch import _event, _fact_view, _timeline

from irswitch.commentary.mailbox import NarrativeMailbox
from irswitch.events import __all__ as events_exports
from irswitch.events.async_fanout import AsyncEventFanout
from irswitch.events.narrative_ingress import NarrativeIngress
from irswitch.events.narrative_runtime import NarrativeRuntime
from irswitch.events.narrative_shadow_consumer import (
    AdaptedPublication,
    NarrativeShadowConsumer,
)
from irswitch.events.stream import FrozenAcceptedEventBatch

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "irswitch"
    / "events"
    / "narrative_shadow_consumer.py"
)
RACE_SOURCE = Path(__file__).resolve().parents[1] / "src" / "irswitch" / "race" / "runtime.py"


def _adapted(*, fanout: int = 11, count: int = 1) -> AdaptedPublication:
    return AdaptedPublication(
        timeline=_timeline(),
        fact_view=_fact_view(count),
        events=tuple(_event(index) for index in range(count)),
        fanout_stream_sequence=fanout,
        command_id_prefix=f"shadow:{fanout}",
        enqueued_mono_ms=2_500,
    )


def test_shadow_source_documents_default_off_boundary() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    assert "enabled: bool = False" in text
    assert "CommentaryConsumer" in text
    assert "does not speak" in text
    assert "NarrativeShadowConsumer" not in events_exports
    assert "AdaptedPublication" not in events_exports
    race = RACE_SOURCE.read_text(encoding="utf-8")
    assert "_narrative_shadow_enabled = False" in race
    assert "NarrativeShadowConsumer" in race


def test_disabled_shadow_consumer_is_noop() -> None:
    mailbox = NarrativeMailbox()
    ingress = NarrativeIngress(mailbox)
    consumer = NarrativeShadowConsumer(enabled=False, ingress=ingress)
    result = consumer.handle_adapted_publication(_adapted())
    assert result.accepted is False
    assert result.reason == "shadow_disabled"
    assert "shadow_disabled" in result.effects
    assert consumer.processed == 0
    assert len(mailbox) == 0


def test_enabled_shadow_admits_via_ingress_without_live_tts() -> None:
    mailbox = NarrativeMailbox()
    ingress = NarrativeIngress(mailbox)
    consumer = NarrativeShadowConsumer(enabled=True, ingress=ingress)
    result = consumer.handle_adapted_publication(_adapted(count=2))
    assert result.accepted is True
    assert result.reason == "accepted"
    assert "ingress_publication_complete" in result.effects
    assert result.command_ids == ("shadow:11:0",)
    assert consumer.processed == 1
    assert len(mailbox) == 1
    command = mailbox.dequeue()
    assert command is not None
    assert command.kind == "APPLY_CONTEXT_BATCH"

    mailbox2 = NarrativeMailbox()
    ingress2 = NarrativeIngress(mailbox2)
    consumer2 = NarrativeShadowConsumer(enabled=True, ingress=ingress2)
    assert consumer2.handle_adapted_publication(_adapted(fanout=11)).accepted
    runtime = NarrativeRuntime(mailbox=mailbox2)
    runtime.enable()
    reduced = runtime.reduce_next()
    assert reduced is not None
    assert reduced.kind == "APPLY_CONTEXT_BATCH"


@pytest.mark.asyncio
async def test_enabled_run_drains_subscription_through_adapter() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("narrative_shadow", capacity=8)
    mailbox = NarrativeMailbox()
    ingress = NarrativeIngress(mailbox)

    def _adapter(batch: FrozenAcceptedEventBatch) -> AdaptedPublication | None:
        seq = batch.stream_sequence
        return AdaptedPublication(
            timeline=_timeline(),
            fact_view=_fact_view(1),
            events=(_event(0, fanout=seq),),
            fanout_stream_sequence=seq,
            command_id_prefix=f"shadow:{seq}",
            enqueued_mono_ms=2_500,
        )

    consumer = NarrativeShadowConsumer(
        subscription,
        enabled=True,
        ingress=ingress,
        publication_adapter=_adapter,
    )
    task = asyncio.create_task(consumer.run())
    try:
        fanout.publish(_batch(stream_sequence=21))
        for _ in range(50):
            if consumer.processed >= 1:
                break
            await asyncio.sleep(0.02)
        assert consumer.processed == 1
        assert len(mailbox) == 1
        command = mailbox.dequeue()
        assert command is not None
        assert command.external_order is not None
        assert command.external_order.fanout_stream_sequence == 21
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert consumer.running is False


@pytest.mark.asyncio
async def test_enabled_without_adapter_skips_batch_without_admit() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("narrative_shadow", capacity=8)
    mailbox = NarrativeMailbox()
    consumer = NarrativeShadowConsumer(
        subscription,
        enabled=True,
        ingress=NarrativeIngress(mailbox),
    )
    task = asyncio.create_task(consumer.run())
    try:
        fanout.publish(_batch(stream_sequence=9))
        for _ in range(50):
            if consumer.skipped >= 1:
                break
            await asyncio.sleep(0.02)
        assert consumer.skipped == 1
        assert consumer.processed == 0
        assert len(mailbox) == 0
    finally:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task


@pytest.mark.asyncio
async def test_disabled_run_returns_immediately_without_draining() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("narrative_shadow", capacity=8)
    consumer = NarrativeShadowConsumer(subscription, enabled=False)
    fanout.publish(_batch(stream_sequence=3))
    await consumer.run()
    assert consumer.running is False
    assert consumer.processed == 0
    assert subscription.snapshot(producer_stream_sequence=3).depth == 1
