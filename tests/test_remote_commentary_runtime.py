"""Run the production adapter → director → model → verifier → TTS composition."""

import asyncio
import json
import time
from dataclasses import replace

import pytest
from test_n12_consumers import _batch

from irswitch.commentary.mailbox import NarrativeMailbox
from irswitch.commentary.tts import NullTtsSink
from irswitch.contracts.command import NarrativeCommand
from irswitch.events.commentary_microplan import plan_from_accepted
from irswitch.events.commentary_model import ModelClient, ModelSettings
from irswitch.events.freshness_commit import FreshnessGate
from irswitch.events.narrative import partition_context_batches
from irswitch.events.narrative_realization_bridge import build_realization_effect
from irswitch.events.narrative_runtime import NarrativeRuntime
from irswitch.events.narrative_shadow_adapter import adapt_batch_for_shadow
from irswitch.events.narrative_tts_bridge import build_tts_effect
from irswitch.events.opportunity_queue import OpportunityQueue
from irswitch.events.semantic_verifier import SemanticVerifier
from irswitch.events.story_director import StoryDirector
from irswitch.events.stream import freeze_accepted_event, thaw_envelope


def current_batch():
    batch = _batch()
    envelope = thaw_envelope(batch.events[0].envelope)
    envelope.metrics = {"lapTime": 102.315}
    event = freeze_accepted_event(
        envelope, audiences=("commentary",), source="event_engine", source_ordinal=0
    )
    return replace(batch, events=(event,))


def reply(text, plan):
    return {
        "model": "provider-reported-model",
        "choices": [
            {
                "finish_reason": "stop",
                "message": {
                    "content": json.dumps(
                        {
                            "action": "speak",
                            "used_fact_ids": [key for key, _ in plan.facts],
                            "candidates": [{"style_id": "natural", "text": text}],
                        }
                    )
                },
            }
        ],
    }


def setup(monkeypatch, mode="live", wording_policy="strict"):
    monkeypatch.setenv("IRSWITCH_LLM_API_KEY", "unit-secret")
    cfg = ModelSettings(
        enabled=True,
        provider="remote",
        mode=mode,
        wording_policy=wording_policy,
        warmup=False,
        base_url="https://llm.buchtovo.cz/v1",
        model="openai/gpt-oss-120b",
    )
    client = ModelClient(lambda: cfg)
    sink = NullTtsSink()
    opportunities = OpportunityQueue()
    runtime = NarrativeRuntime(
        mailbox=NarrativeMailbox(),
        story_director=StoryDirector(),
        opportunity_queue=opportunities,
        freshness_gate=FreshnessGate(opportunities),
        realization_effect=build_realization_effect(model_client=client),
        tts_effect=build_tts_effect(sink, locale="en", backend="null"),
        semantic_verifier=SemanticVerifier(),
        realization_config_signature=lambda: client.settings().signature,
        realization_wording_policy=lambda: client.settings().effective_wording_policy,
        on_microplan_spoken=client.note_spoken,
    )
    runtime.enable()
    return cfg, client, sink, runtime


def admit(runtime, batch):
    publication = adapt_batch_for_shadow(batch, narrative_run_active=True)
    assert publication is not None
    part = partition_context_batches(
        timeline=publication.timeline,
        fact_view=publication.fact_view,
        events=publication.events,
        fanout_stream_sequence=publication.fanout_stream_sequence,
    )[0]
    runtime.admit(NarrativeCommand.context_batch("context:1", int(time.monotonic() * 1000), part))


async def drain(runtime, count=16):
    effects = []
    for _ in range(count):
        step = runtime.reduce_next()
        if step is not None:
            effects.extend(step.effects)
            await runtime.apply_effects(step.effects)
        await asyncio.sleep(0.001)
    return effects


@pytest.mark.asyncio
async def test_real_admitted_bundle_paraphrase_reaches_tts_and_spoken_memory(monkeypatch):
    _, client, sink, runtime = setup(monkeypatch)
    batch = current_batch()
    plan = plan_from_accepted(batch.events[0], batch)
    assert plan is not None

    async def post(*args):
        await asyncio.sleep(0.01)
        return reply("Alex posts a lap of 1:42.315.", plan)

    monkeypatch.setattr(client, "_post", post)
    admit(runtime, batch)
    effects = await drain(runtime, 50)
    assert "realization_committed" in effects
    assert sink.spoken[0].text == "Alex posts a lap of 1:42.315."
    assert client.was_spoken(plan)
    assert client.status()["lastAttempt"]["modelReported"] == "provider-reported-model"
    await client.close()
    await runtime.wait_effects_idle()


@pytest.mark.asyncio
@pytest.mark.parametrize("wording_policy", ["strict", "experimental_free"])
async def test_shadow_does_not_wait_or_speak_model_output(monkeypatch, wording_policy):
    _, client, sink, runtime = setup(monkeypatch, "shadow", wording_policy)
    entered = asyncio.Event()
    cancelled = asyncio.Event()

    async def post(*args):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(client, "_post", post)
    batch = current_batch()
    plan = plan_from_accepted(batch.events[0], batch)
    admit(runtime, batch)
    await drain(runtime)
    assert entered.is_set()
    assert sink.spoken and sink.spoken[0].text == plan.allowed[0]
    assert client.was_spoken(plan)
    await client.close()
    assert cancelled.is_set()
    await runtime.wait_effects_idle()


@pytest.mark.asyncio
async def test_unsupported_input_finishes_instead_of_hanging(monkeypatch):
    _, client, sink, runtime = setup(monkeypatch)
    token = {"requestId": "missing:plan", "requestOrdinal": 1, "dispatchGeneration": 1}
    command = await build_realization_effect(model_client=client)(token)
    assert command.kind == "REALIZATION_FAILED"
    admit(runtime, _batch())  # LAP_COMPLETE without lapTime is insufficient evidence.
    effects = await drain(runtime)
    assert "realization_failed" in effects
    assert not sink.spoken and not client.status()["attemptCount"]
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("global_disable", [False, True])
async def test_config_changed_while_awaiting_cannot_speak_even_fallback(
    monkeypatch, global_disable
):
    cfg, client, sink, runtime = setup(monkeypatch)
    batch = current_batch()
    plan = plan_from_accepted(batch.events[0], batch)
    entered, release = asyncio.Event(), asyncio.Event()

    async def post(*args):
        entered.set()
        await release.wait()
        return reply(plan.allowed[0], plan)

    monkeypatch.setattr(client, "_post", post)
    admit(runtime, batch)
    await drain(runtime, 2)
    await asyncio.wait_for(entered.wait(), 0.5)
    monkeypatch.setattr(
        client, "_settings", lambda: replace(cfg, enabled=False, speech_enabled=not global_disable)
    )
    release.set()
    await drain(runtime)
    assert not sink.spoken
    assert client.status()["lastReason"] == "config_changed"
    await client.close()


@pytest.mark.asyncio
async def test_client_restart_after_supervisor_close(monkeypatch):
    _, client, _, _ = setup(monkeypatch)
    batch = current_batch()
    plan = plan_from_accepted(batch.events[0], batch)

    async def post(*args):
        return reply(plan.allowed[0], plan)

    monkeypatch.setattr(client, "_post", post)
    await client.close()
    client.start()
    assert await client.realize(plan) == plan.allowed[0]
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("wording_policy", ["strict", "experimental_free"])
async def test_expired_bundle_never_speaks_fallback(monkeypatch, wording_policy):
    _, client, sink, runtime = setup(monkeypatch, wording_policy=wording_policy)
    batch = current_batch()
    envelope = thaw_envelope(batch.events[0].envelope)
    envelope.monotonic_ms -= 6000
    accepted = freeze_accepted_event(
        envelope, audiences=("commentary",), source="test", source_ordinal=0
    )
    admit(runtime, replace(batch, events=(accepted,)))
    await drain(runtime)
    assert not sink.spoken
    assert client.status()["totalAttempts"] == 0
    await client.close()


@pytest.mark.asyncio
async def test_commit_to_tts_gap_rechecks_expiry(monkeypatch):
    _, client, sink, runtime = setup(monkeypatch)
    batch = current_batch()
    current = plan_from_accepted(batch.events[0], batch)
    admit(runtime, batch)
    token = {
        "utteranceId": "expired:utterance",
        "utteranceOrdinal": 1,
        "backendGeneration": 1,
        "dispatchGeneration": 1,
        "text": current.allowed[0],
        "microplan": replace(current, expires_ms=0).to_dict(),
    }
    await runtime._run_worker(build_tts_effect(sink, backend="null"), token, "_tts_task")
    assert not sink.spoken
    assert runtime.reduce_next() is not None
    await client.close()
