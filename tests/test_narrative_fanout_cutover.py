"""#284 shadow fanout cutover: EventSubscription → ingress → reduce (+ status attach)."""

from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from test_narrative_context_batch import _event, _fact_view, _timeline

from irswitch.commentary.mailbox import NarrativeMailbox
from irswitch.events.narrative_ingress import NarrativeIngress
from irswitch.events.narrative_runtime import NarrativeRuntime
from irswitch.events.narrative_runtime_http import (
    get_narrative_runtime,
    register_narrative_runtime_routes,
    set_narrative_runtime,
)
from irswitch.events.narrative_shadow_consumer import (
    AdaptedPublication,
    NarrativeShadowConsumer,
)

RACE_SOURCE = Path(__file__).resolve().parents[1] / "src" / "irswitch" / "race" / "runtime.py"
RUNTIME_SOURCE = (
    Path(__file__).resolve().parents[1] / "src" / "irswitch" / "events" / "narrative_runtime.py"
)


def _adapted(*, fanout: int = 11, count: int = 1) -> AdaptedPublication:
    return AdaptedPublication(
        timeline=_timeline(),
        fact_view=_fact_view(count),
        events=tuple(_event(index) for index in range(count)),
        fanout_stream_sequence=fanout,
        command_id_prefix=f"cutover:{fanout}",
        enqueued_mono_ms=3_000,
    )


def test_runtime_preserves_empty_injected_mailbox_identity() -> None:
    text = RUNTIME_SOURCE.read_text(encoding="utf-8")
    assert "mailbox if mailbox is not None else NarrativeMailbox()" in text
    assert "mailbox or NarrativeMailbox()" not in text
    mailbox = NarrativeMailbox()
    assert len(mailbox) == 0
    runtime = NarrativeRuntime(mailbox=mailbox)
    assert runtime._mailbox is mailbox


def test_shadow_cutover_reduces_admitted_commands_without_run() -> None:
    mailbox = NarrativeMailbox()
    ingress = NarrativeIngress(mailbox)
    runtime = NarrativeRuntime(mailbox=mailbox)
    runtime.enable()
    consumer = NarrativeShadowConsumer(
        enabled=True,
        ingress=ingress,
        runtime=runtime,
    )
    result = consumer.handle_adapted_publication(_adapted(count=2))
    assert result.accepted is True
    assert "shadow_reduced" in result.effects
    assert consumer.reduced == 1
    assert len(mailbox) == 0
    assert runtime.status().runtime_state == "ready"
    # Actor loop must stay idle — cutover uses reduce_next only.
    assert not hasattr(consumer, "_runtime_task")


def test_shadow_without_runtime_still_admits_only() -> None:
    mailbox = NarrativeMailbox()
    consumer = NarrativeShadowConsumer(
        enabled=True,
        ingress=NarrativeIngress(mailbox),
    )
    result = consumer.handle_adapted_publication(_adapted())
    assert result.accepted is True
    assert "shadow_reduced" not in result.effects
    assert consumer.reduced == 0
    assert len(mailbox) == 1


@pytest.mark.asyncio
async def test_module_runtime_attach_feeds_http_status() -> None:
    set_narrative_runtime(None)
    mailbox = NarrativeMailbox()
    runtime = NarrativeRuntime(mailbox=mailbox)
    runtime.enable()
    set_narrative_runtime(runtime)
    try:
        assert get_narrative_runtime() is runtime
        app = web.Application()
        register_narrative_runtime_routes(app)
        async with TestServer(app) as server:
            async with TestClient(server) as client:
                resp = await client.get("/api/commentary/runtime")
                assert resp.status == 200
                data = await resp.json()
                assert data["schemaVersion"] == "commentary-runtime/2"
                assert data["status"] == "ready"
    finally:
        set_narrative_runtime(None)


def test_race_shadow_cutover_wires_runtime_when_flag_on_still_default_off() -> None:
    race = RACE_SOURCE.read_text(encoding="utf-8")
    assert "_narrative_shadow_enabled = True" in race
    assert "NarrativeRuntime(mailbox=" in race
    assert "set_narrative_runtime" in race
    assert "adapt_batch_for_shadow" in race
    assert "runtime=self.narrative_runtime" in race or "runtime=runtime" in race
    # Must not start actor loop from race wiring.
    assert "narrative_runtime.run()" not in race
    assert "self.narrative_runtime.run()" not in race
