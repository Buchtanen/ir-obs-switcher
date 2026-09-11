"""#349 Slice 4 — Qwen/verifier fail-closed (no silent template live fallback).

Sol tip audit: when ``allow_qwen`` is on, authored+Qwen miss still spoke a
template draft; unframed Qwen success skipped #270 verification and still
reached TTS.
"""

from __future__ import annotations

import binascii
from pathlib import Path

import pytest
from test_narrative_runtime import (
    _event_impulse,
    _minimal_commit_pair,
    _result_for,
)

from irswitch.contracts.command import NarrativeCommand
from irswitch.events.freshness_commit import FreshnessGate
from irswitch.events.narrative_realization_bridge import (
    SpeechDraft,
    SpeechDraftCache,
    build_realization_effect,
)
from irswitch.events.narrative_runtime import NarrativeRuntime
from irswitch.events.narrative_verify_frame import (
    VerifyFrame,
    take_live_verify_frame,
)
from irswitch.events.qwen_transport import (
    FakeTransport,
    LlmComponent,
    RealizerService,
    load_transport_goldens,
)
from irswitch.events.semantic_verifier import SemanticVerifier

RACE_SOURCE = Path(__file__).resolve().parents[1] / "src" / "irswitch" / "race" / "runtime.py"


def _ready_component() -> LlmComponent:
    component = LlmComponent()
    component.start_preflight(desired_generation=3, warmup=True)
    component.complete_preflight(generation=3, residency="warmup_succeeded")
    return component


def _sse_chunks(name: str = "role_content_usage_done") -> list[bytes]:
    goldens = load_transport_goldens()
    for row in goldens["sse"]["valid"]:
        if row["id"] == name:
            return [binascii.unhexlify(item) for item in row["chunksHex"]]
    raise AssertionError(name)


@pytest.mark.asyncio
async def test_allow_qwen_miss_fails_closed_without_template() -> None:
    cache = SpeechDraftCache()
    service = RealizerService(transport=FakeTransport(chunks=[]))
    effect = build_realization_effect(
        cache,
        prefer_authored=True,
        allow_qwen=True,
        qwen_service=service,
        llm_component=_ready_component(),
        fallback_text="Template fallback.",
    )
    token = {
        "requestId": "request:qwen:miss",
        "requestOrdinal": 2,
        "dispatchGeneration": 7,
        "beatId": "battle.approach",
    }
    command = await effect(token)
    assert command.kind == "REALIZATION_FAILED"
    assert command.payload["outcome"] == "failed"
    assert command.payload["text"] is None
    assert command.payload["backend"] == "qwen_compiled"
    assert command.payload["failureReason"] == "realization_transport"
    assert take_live_verify_frame(token) is None


@pytest.mark.asyncio
async def test_allow_qwen_still_speaks_cached_authored_draft() -> None:
    cache = SpeechDraftCache()
    frame = VerifyFrame(
        family="battle.approach",
        subject_surface="Alex",
        required_claim_surface="is closing on Morgan",
        actor_bindings=(("live", ("Alex",)),),
        required_actors=frozenset({"live"}),
    )
    cache._drafts.append(
        SpeechDraft(
            text="Alex is closing on Morgan.",
            beat_id="battle.approach",
            source="authored",
            verify_frame=frame,
        )
    )
    service = RealizerService(transport=FakeTransport(chunks=[]))
    effect = build_realization_effect(
        cache,
        prefer_authored=True,
        allow_qwen=True,
        qwen_service=service,
        llm_component=_ready_component(),
        fallback_text="Template fallback.",
    )
    token = {
        "requestId": "request:qwen:authored-cache",
        "requestOrdinal": 2,
        "dispatchGeneration": 7,
        "beatId": "battle.approach",
    }
    command = await effect(token)
    assert command.kind == "REALIZATION_SUCCEEDED"
    assert command.payload["text"] == "Alex is closing on Morgan."
    assert command.payload["backend"] == "authored"
    assert take_live_verify_frame(token) is not None


@pytest.mark.asyncio
async def test_qwen_success_does_not_stash_verify_frame() -> None:
    cache = SpeechDraftCache()
    service = RealizerService(transport=FakeTransport(chunks=_sse_chunks()))
    effect = build_realization_effect(
        cache,
        prefer_authored=True,
        allow_qwen=True,
        qwen_service=service,
        llm_component=_ready_component(),
    )
    token = {
        "requestId": "request:qwen:unframed",
        "requestOrdinal": 2,
        "dispatchGeneration": 7,
        "beatId": "battle.approach",
    }
    command = await effect(token)
    assert command.kind == "REALIZATION_SUCCEEDED"
    assert command.payload["backend"] == "qwen_compiled"
    assert take_live_verify_frame(token) is None


def test_unframed_realization_rejects_when_verifier_attached() -> None:
    """#349: missing #270 frame with live verifier → reject, no TTS."""
    gate = FreshnessGate()
    token, world = _minimal_commit_pair()
    runtime = NarrativeRuntime(
        freshness_gate=gate,
        commit_world_provider=lambda: world,
        semantic_verifier=SemanticVerifier(),
    )
    runtime.enable()
    runtime.admit(_event_impulse("verify:qwen:unframed", revision=52, fanout=52))
    planned = runtime.reduce_next()
    assert planned is not None
    runtime.seed_commit_token_for_test(token)
    rz = runtime.current_realization_token()
    assert rz is not None
    runtime.admit(
        NarrativeCommand.realization_result(
            "verify:qwen:unframed:ok",
            "REALIZATION_SUCCEEDED",
            10_220,
            request_id=str(rz["requestId"]),
            request_ordinal=int(rz["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(rz["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(
                rz,
                text="Alex is closing on Morgan.",
                backend="qwen_compiled",
            ),
        )
    )
    rejected = runtime.reduce_next()
    assert rejected is not None
    assert rejected.lane_after == "idle"
    assert "realization_verify_rejected" in rejected.effects
    assert "semantic_verdict:rejected" in rejected.effects
    assert "semantic_reason:missing_verify_frame" in rejected.effects
    assert "effect:dispatch_tts" not in rejected.effects
    assert "semantic_verdict:skipped_no_frame" not in rejected.effects
    assert runtime.current_utterance_token() is None


def test_race_comment_no_longer_promises_template_on_qwen_miss() -> None:
    race = RACE_SOURCE.read_text(encoding="utf-8")
    assert "Authored/template remain on miss" not in race
    assert "allow_qwen=" in race
