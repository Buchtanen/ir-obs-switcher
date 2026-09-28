"""Opt-in free wording must reach playback without claiming semantic verification."""

import asyncio
from dataclasses import replace
from pathlib import Path

import pytest
from test_remote_commentary_runtime import admit, current_batch, drain, reply, setup

from irswitch.contracts.config import parse_commentary_mapping
from irswitch.events.commentary_microplan import plan_from_accepted
from irswitch.events.commentary_model import ModelSettings
from irswitch.events.semantic_verifier import free_wording_reasons

ROOT = Path(__file__).resolve().parents[1]
PARAPHRASE = "Across the line goes Alex, completing that lap in 1:42.315."


def test_free_shape_keeps_decimal_time_and_rejects_multiple_sentence_boundaries():
    assert free_wording_reasons(PARAPHRASE) == []
    for text in (
        "Alex completes the lap! That is a personal best.",
        "What a lap? Alex crosses the line.",
        "Alex completes the lap.\nThat is a personal best.",
    ):
        assert "sentence_count" in free_wording_reasons(text)


@pytest.mark.asyncio
@pytest.mark.parametrize("policy", ["strict", "experimental_free"])
async def test_wording_policy_reaches_tts_with_honest_diagnostics(monkeypatch, policy):
    _, client, sink, runtime = setup(monkeypatch, wording_policy=policy)
    batch = current_batch()
    plan = plan_from_accepted(batch.events[0], batch)
    assert plan is not None and not plan.accepts(PARAPHRASE)

    async def post(*args):
        return reply(PARAPHRASE, plan)

    monkeypatch.setattr(client, "_post", post)
    admit(runtime, batch)
    effects = await drain(runtime, 50)
    free = policy == "experimental_free"
    assert sink.spoken[0].text == (PARAPHRASE if free else plan.allowed[0])
    status = client.status()
    assert status["wordingPolicy"] == policy
    assert status["lastAttempt"]["strictWouldAccept"] is False
    assert status["lastAttempt"]["semanticCheck"] == ("not_enforced" if free else "strict")
    assert status["recentSelections"][-1]["played"] is True
    assert ("semantic_verdict:not_enforced" in effects) is free
    await client.close()
    await runtime.wait_effects_idle()


@pytest.mark.asyncio
async def test_free_policy_change_cancels_pending_speech(monkeypatch):
    cfg, client, sink, runtime = setup(monkeypatch, wording_policy="experimental_free")
    batch = current_batch()
    plan = plan_from_accepted(batch.events[0], batch)
    entered, release = asyncio.Event(), asyncio.Event()

    async def post(*args):
        entered.set()
        await release.wait()
        return reply(PARAPHRASE, plan)

    monkeypatch.setattr(client, "_post", post)
    admit(runtime, batch)
    await drain(runtime, 2)
    await asyncio.wait_for(entered.wait(), 0.5)
    monkeypatch.setattr(client, "_settings", lambda: replace(cfg, wording_policy="strict"))
    release.set()
    await drain(runtime)
    assert not sink.spoken
    assert client.status()["lastReason"] == "config_changed"
    await client.close()


@pytest.mark.asyncio
async def test_client_acceptance_cannot_override_reducer_strict_policy(monkeypatch):
    _, client, sink, runtime = setup(monkeypatch, wording_policy="experimental_free")
    runtime._realization_wording_policy = None
    batch = current_batch()
    plan = plan_from_accepted(batch.events[0], batch)

    async def post(*args):
        return reply(PARAPHRASE, plan)

    monkeypatch.setattr(client, "_post", post)
    admit(runtime, batch)
    effects = await drain(runtime, 50)
    assert client.status()["lastAttempt"]["accepted"] is True
    assert "semantic_verdict:rejected" in effects
    assert not sink.spoken
    await client.close()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text", ["```Bad output.```", "First sentence. Second sentence.", "x" * 201]
)
async def test_free_policy_keeps_output_shape_and_fallback(monkeypatch, text):
    _, client, sink, runtime = setup(monkeypatch, wording_policy="experimental_free")
    batch = current_batch()
    plan = plan_from_accepted(batch.events[0], batch)

    async def post(*args):
        return reply(text, plan)

    monkeypatch.setattr(client, "_post", post)
    admit(runtime, batch)
    await drain(runtime, 50)
    assert sink.spoken[0].text == plan.allowed[0]
    assert not client.status()["lastAttempt"]["accepted"]
    await client.close()


def test_wording_policy_config_is_opt_in_and_local_stays_strict():
    candidate = parse_commentary_mapping(
        {"commentary.llm.wording_policy": "experimental_free"}, repository_root=ROOT
    )
    assert candidate.valid and candidate.snapshot is not None
    cfg = ModelSettings.from_values(dict(candidate.snapshot.values))
    assert cfg.wording_policy == "experimental_free"
    assert cfg.effective_wording_policy == "strict"
    assert ModelSettings().wording_policy == "strict"
    assert not parse_commentary_mapping(
        {"commentary.llm.wording_policy": "off"}, repository_root=ROOT
    ).valid
