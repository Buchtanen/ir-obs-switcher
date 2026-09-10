"""#284 optional Qwen transport path on Narrative realization_effect."""

from __future__ import annotations

import binascii
from pathlib import Path

import pytest

from irswitch.events import __all__ as events_exports
from irswitch.events.narrative_realization_bridge import (
    SpeechDraftCache,
    build_realization_effect,
    realize_qwen_text,
)
from irswitch.events.qwen_transport import (
    FakeTransport,
    LlmComponent,
    RealizerService,
    load_transport_goldens,
)

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "irswitch"
    / "events"
    / "narrative_realization_bridge.py"
)
RACE_SOURCE = Path(__file__).resolve().parents[1] / "src" / "irswitch" / "race" / "runtime.py"
HASH = "sha256:" + ("55" * 32)
BUNDLE = "sha256:" + ("88" * 32)


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


def test_realize_qwen_text_not_exported() -> None:
    assert "realize_qwen_text" not in events_exports
    assert SOURCE.is_file()


def test_realize_qwen_text_returns_fake_transport_sentence() -> None:
    service = RealizerService(transport=FakeTransport(chunks=_sse_chunks()))
    text = realize_qwen_text(
        beat_id="battle.approach",
        request_ordinal=2,
        dispatch_generation=7,
        service=service,
        component=_ready_component(),
        now_ms=91_000,
    )
    assert text == "Alex is closing on Morgan."


def test_realize_qwen_text_skips_when_component_not_ready() -> None:
    service = RealizerService(transport=FakeTransport(chunks=_sse_chunks()))
    text = realize_qwen_text(
        beat_id="battle.approach",
        request_ordinal=2,
        dispatch_generation=7,
        service=service,
        component=LlmComponent(),
        now_ms=91_000,
    )
    assert text is None


@pytest.mark.asyncio
async def test_realization_effect_uses_qwen_when_authored_misses() -> None:
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
        "requestId": "request:qwen:1",
        "requestOrdinal": 2,
        "dispatchGeneration": 7,
        # Unmapped authored beat → Qwen path.
        "beatId": "battle.approach",
    }
    command = await effect(token)
    assert command.kind == "REALIZATION_SUCCEEDED"
    assert command.payload["text"] == "Alex is closing on Morgan."
    assert command.payload["backend"] == "qwen_compiled"


@pytest.mark.asyncio
async def test_realization_effect_skips_qwen_when_disabled() -> None:
    cache = SpeechDraftCache()
    service = RealizerService(transport=FakeTransport(chunks=_sse_chunks()))
    effect = build_realization_effect(
        cache,
        prefer_authored=True,
        allow_qwen=False,
        qwen_service=service,
        llm_component=_ready_component(),
        fallback_text="Template fallback.",
    )
    token = {
        "requestId": "request:qwen:off",
        "requestOrdinal": 2,
        "dispatchGeneration": 7,
        "beatId": "battle.approach",
    }
    command = await effect(token)
    assert command.kind == "REALIZATION_SUCCEEDED"
    assert command.payload["text"] == "Template fallback."
    assert command.payload["backend"] == "authored"


def test_race_wires_optional_qwen_flag_enabled() -> None:
    race = RACE_SOURCE.read_text(encoding="utf-8")
    assert "_narrative_qwen_enabled" in race
    assert "_narrative_qwen_enabled = True" in race
    assert "allow_qwen=" in race
    assert "RealizerService" in race
    assert "StdlibTransport" in race
    assert "warmup_qwen_component" in race
