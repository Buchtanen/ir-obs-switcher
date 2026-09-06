"""Live LLM polish preempts prepared filler generation."""

from __future__ import annotations

import asyncio
import threading
from typing import Any

from irswitch.commentary.graph import GraphNode, SlotSpec, TtsLimits
from irswitch.commentary.llm_lane import LlmPriorityLane
from irswitch.commentary.polish import PolishOutcome
from irswitch.commentary.prepared_filler import (
    FactProposition,
    PreparedFillerCoordinator,
    PreparedFillerPlan,
)
from irswitch.commentary.tts import (
    CommentaryUtterance,
    ProcessTtsSink,
    TtsResult,
    llm_timeout_notice,
)
from irswitch.overlay.settings import CommentarySettings, PreparedFillerSettings


def _plan() -> PreparedFillerPlan:
    return PreparedFillerPlan.create(
        node_id="prepared.stream.venue",
        semantic_key="stream.venue",
        locale="en",
        scope_key="stream:1",
        stage_epoch=1,
        allowed_stages=("STREAM_LOBBY_INTRO",),
        required=(FactProposition("track", "Spa", "telemetry", "context:1", "Spa"),),
    )


def _variants(count: int = 3) -> list[str]:
    return [f"We are live at Spa. This is prepared variant {name}." for name in "ABCDE"[:count]]


def _utterance(
    text: str = "Buchtanen takes P14.", *, prepared: bool = False
) -> CommentaryUtterance:
    node = GraphNode(
        id="overtake",
        family="position",
        event_types=("OVERTAKE",),
        phases=("RESULT",),
        speak_priority=85,
        cooldown_s=1.0,
        slots=(SlotSpec("position", "int", "14"),),
        hr_states=("unknown",),
        tts=TtsLimits(),
    )
    return CommentaryUtterance(
        node_id="overtake",
        locale="en",
        emotion="unknown",
        text=text,
        event_type="OVERTAKE",
        event_id="e1",
        correlation_id="c1",
        estimated_seconds=1.0,
        node=node,
        priority=85,
        prepared=prepared,
    )


def test_lane_blocks_prepared_until_live_releases() -> None:
    lane = LlmPriorityLane()
    assert lane.allow_prepared()
    lane.request_live()
    assert not lane.allow_prepared()
    lane.request_live()
    assert not lane.allow_prepared()
    lane.release_live()
    assert not lane.allow_prepared()
    lane.release_live()
    assert lane.allow_prepared()


def test_first_live_reservation_preempts_prepared() -> None:
    seen: list[str] = []
    lane = LlmPriorityLane()
    lane.set_hooks(on_preempt=lambda: seen.append("preempt"), on_idle=lambda: seen.append("idle"))
    lane.request_live()
    lane.request_live()
    lane.release_live()
    assert seen == ["preempt"]
    lane.release_live()
    assert seen == ["preempt", "idle"]


def test_coordinator_does_not_start_prepared_while_live_owns_lane() -> None:
    calls = 0

    async def generator(plan: PreparedFillerPlan, count: int, hashes: tuple[str, ...]) -> list[str]:
        nonlocal calls
        calls += 1
        return _variants(count)

    async def exercise() -> None:
        lane = LlmPriorityLane()
        coordinator = PreparedFillerCoordinator(
            PreparedFillerSettings(mode="shadow"),
            generator,
            llm_lane=lane,
        )
        lane.request_live()
        coordinator.reconcile([_plan()], current_stage="STREAM_LOBBY_INTRO")
        await asyncio.sleep(0)
        assert calls == 0
        assert coordinator.status()["inflight"] == 0
        assert coordinator.status()["llmPaused"] is True
        lane.release_live()
        await coordinator.wait_idle()
        assert calls == 1
        assert coordinator.status()["llmPaused"] is False
        await coordinator.close()

    asyncio.run(exercise())


def test_live_reservation_cancels_inflight_prepared() -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def generator(plan: PreparedFillerPlan, count: int, hashes: tuple[str, ...]) -> list[str]:
        started.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled.set()
            raise

    async def exercise() -> None:
        lane = LlmPriorityLane()
        coordinator = PreparedFillerCoordinator(
            PreparedFillerSettings(mode="shadow"),
            generator,
            llm_lane=lane,
        )
        coordinator.reconcile([_plan()], current_stage="STREAM_LOBBY_INTRO")
        await asyncio.wait_for(started.wait(), timeout=1)
        lane.request_live()
        await asyncio.wait_for(cancelled.wait(), timeout=1)
        await asyncio.sleep(0)
        assert coordinator.status()["inflight"] == 0
        assert coordinator.buffer.attempt_count(_plan()) == 0
        await coordinator.close()

    asyncio.run(exercise())


def test_live_tts_enqueue_holds_lane_until_polish_finishes(monkeypatch: Any) -> None:
    started = threading.Event()
    release = threading.Event()
    lane = LlmPriorityLane()

    def polish(text: str, *_args: Any, **_kwargs: Any) -> PolishOutcome:
        started.set()
        release.wait(timeout=2.0)
        return PolishOutcome(
            text="polished overtake",
            outcome="ok",
            latency_ms=1.0,
            skeleton=text,
            request={},
            attempts=1,
        )

    monkeypatch.setattr("irswitch.commentary.tts.polish_skeleton", polish)
    monkeypatch.setattr(
        "irswitch.commentary.tts.speak_text",
        lambda text, **_kwargs: TtsResult("test", True),
    )
    sink = ProcessTtsSink(
        CommentarySettings(llm_polish=True, tts_backend="null"),
        llm_lane=lane,
    )
    sink.enqueue(_utterance())
    assert started.wait(timeout=1.0)
    assert not lane.allow_prepared()
    release.set()
    assert sink.wait_idle(timeout_s=2.0)
    assert lane.allow_prepared()


def test_prepared_utterance_does_not_hold_lane() -> None:
    lane = LlmPriorityLane()
    sink = ProcessTtsSink(
        CommentarySettings(llm_polish=True, tts_backend="null"),
        llm_lane=lane,
    )
    sink.enqueue(_utterance(prepared=True))
    assert sink.wait_idle(timeout_s=2.0)
    assert lane.allow_prepared()
    assert lane.live_count == 0


def test_llm_timeout_notice_is_localized() -> None:
    assert llm_timeout_notice("cs") == "LLM nestihl dodat komentáře."
    assert llm_timeout_notice("en") == "LLM did not deliver the commentary in time."


def test_polish_timeout_speaks_notice(monkeypatch: Any) -> None:
    spoken: list[str] = []
    debug: list[dict[str, Any]] = []

    def polish(text: str, *_args: Any, **_kwargs: Any) -> PolishOutcome:
        return PolishOutcome(
            text=text,
            outcome="fallback_timeout",
            latency_ms=12000.0,
            skeleton=text,
            request={},
            attempts=1,
        )

    monkeypatch.setattr("irswitch.commentary.tts.polish_skeleton", polish)
    monkeypatch.setattr(
        "irswitch.commentary.tts.speak_text",
        lambda text, **_kwargs: spoken.append(text) or TtsResult("test", True),
    )
    sink = ProcessTtsSink(
        CommentarySettings(llm_polish=True, tts_backend="null"),
        on_story_debug=debug.append,
    )
    sink.enqueue(_utterance())
    assert sink.wait_idle(timeout_s=2.0)
    assert spoken == ["LLM did not deliver the commentary in time."]
    assert any(row.get("reason") == "llm_timeout_notice" for row in debug)


def test_polish_retry_exhausted_stays_silent(monkeypatch: Any) -> None:
    spoken: list[str] = []

    def polish(text: str, *_args: Any, **_kwargs: Any) -> PolishOutcome:
        return PolishOutcome(
            text=text,
            outcome="retry_exhausted",
            latency_ms=1.0,
            skeleton=text,
            request={},
            attempts=2,
        )

    monkeypatch.setattr("irswitch.commentary.tts.polish_skeleton", polish)
    monkeypatch.setattr(
        "irswitch.commentary.tts.speak_text",
        lambda text, **_kwargs: spoken.append(text) or TtsResult("test", True),
    )
    sink = ProcessTtsSink(CommentarySettings(llm_polish=True, tts_backend="null"))
    sink.enqueue(_utterance())
    assert sink.wait_idle(timeout_s=2.0)
    assert spoken == []
