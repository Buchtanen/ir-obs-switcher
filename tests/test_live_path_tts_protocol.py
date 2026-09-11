"""#349 Slice 3 — live TTS protocol bridge (no fabricated identity / lifecycle).

Sol tip audit: narrative TTS bridge hardcoded backend=sapi and returned
PLAYBACK_ACCEPTED+SPEECH_COMPLETED only after wait_idle, so start deadlines
and metrics lied about the real backend and accept boundary.
"""

from __future__ import annotations

import asyncio
import inspect
from dataclasses import dataclass, field
from typing import Any

import pytest

from irswitch.commentary.tts import NullTtsSink, detect_backend
from irswitch.contracts.command import NarrativeCommand
from irswitch.events.narrative_ingress import project_runtime_status
from irswitch.events.narrative_runtime import NarrativeRuntime
from irswitch.events.narrative_tts_bridge import build_tts_effect


def _token(**overrides: Any) -> dict[str, Any]:
    base = {
        "utteranceId": "utterance:live:1",
        "utteranceOrdinal": 1,
        "backendGeneration": 3,
        "dispatchGeneration": 7,
        "text": "Gap is closing.",
    }
    base.update(overrides)
    return base


async def _collect(effect: Any, token: dict[str, Any]) -> list[NarrativeCommand]:
    produced = effect(token)
    if inspect.isasyncgen(produced):
        return [command async for command in produced]
    result = await produced
    if result is None:
        return []
    if isinstance(result, NarrativeCommand):
        return [result]
    return list(result)


@dataclass
class _RecordingSink:
    """Enqueue sink with controllable wait_idle / interrupt."""

    spoken: list[Any] = field(default_factory=list)
    interrupted: int = 0
    idle_result: bool = True
    hang_s: float = 0.0

    def enqueue(self, utterance: Any) -> None:
        self.spoken.append(utterance)

    def interrupt(self) -> None:
        self.interrupted += 1

    def wait_idle(self, timeout_s: float = 5.0) -> bool:
        if self.hang_s > 0:
            # Block until cancelled / timeout window elapses for hang tests.
            import time

            deadline = time.monotonic() + min(self.hang_s, max(0.0, float(timeout_s)))
            while time.monotonic() < deadline:
                time.sleep(0.01)
            return False
        return bool(self.idle_result)


@pytest.mark.asyncio
async def test_tts_effect_emits_accept_before_complete_with_real_backend() -> None:
    sink = _RecordingSink()
    backend = detect_backend()
    effect = build_tts_effect(sink, locale="en", backend=backend)
    produced = await _collect(effect, _token())
    assert [command.kind for command in produced] == [
        "PLAYBACK_ACCEPTED",
        "SPEECH_COMPLETED",
    ]
    assert len(sink.spoken) == 1
    accept_payload = produced[0].payload
    complete_payload = produced[1].payload
    assert accept_payload["backend"] == backend
    assert complete_payload["backend"] == backend
    assert accept_payload["backend"] != "sapi" or backend == "sapi"
    assert accept_payload["workerSequence"] == 1
    assert complete_payload["workerSequence"] == 2


@pytest.mark.asyncio
async def test_tts_effect_does_not_hardcode_sapi_when_backend_is_null() -> None:
    """CI Linux typically resolves auto→null; bridge must not invent sapi."""

    effect = build_tts_effect(NullTtsSink(), locale="en", backend="null")
    produced = await _collect(effect, _token())
    assert produced[0].payload["backend"] == "null"
    assert produced[1].payload["backend"] == "null"


@pytest.mark.asyncio
async def test_tts_effect_failed_idle_returns_failed_not_completed() -> None:
    sink = _RecordingSink(idle_result=False)
    effect = build_tts_effect(sink, locale="en", backend="espeak", idle_timeout_s=0.05)
    produced = await _collect(effect, _token())
    assert [command.kind for command in produced] == [
        "PLAYBACK_ACCEPTED",
        "SPEECH_FAILED",
    ]
    assert produced[1].payload["backend"] == "espeak"
    assert produced[1].payload["workerSequence"] == 2


@pytest.mark.asyncio
async def test_tts_effect_cancel_interrupts_sink_and_emits_interrupted() -> None:
    sink = _RecordingSink(hang_s=5.0)
    effect = build_tts_effect(sink, locale="en", backend="espeak", idle_timeout_s=5.0)
    agen = effect(_token())
    assert inspect.isasyncgen(agen)
    first = await agen.__anext__()
    assert first.kind == "PLAYBACK_ACCEPTED"
    task = asyncio.create_task(agen.__anext__())
    await asyncio.sleep(0.05)
    task.cancel()
    try:
        second = await task
    except asyncio.CancelledError:
        await agen.aclose()
        assert sink.interrupted >= 1
    else:
        assert second.kind == "SPEECH_INTERRUPTED"
        assert sink.interrupted >= 1
        assert second.payload["backend"] == "espeak"


@pytest.mark.asyncio
async def test_runtime_projects_speech_backend_from_playback_accepted() -> None:
    sink = NullTtsSink()
    runtime = NarrativeRuntime(tts_effect=build_tts_effect(sink, locale="en", backend="espeak"))
    runtime.enable()
    runtime.admit(
        NarrativeCommand.manual_speak(
            "manual:live-tts",
            8_000,
            text="Hold the inside.",
            admission_ordinal=1,
        )
    )
    reduced = runtime.reduce_next()
    assert reduced is not None
    await runtime.apply_effects(reduced.effects)
    # Drain mailbox callbacks admitted by the tts worker.
    deadline = asyncio.get_running_loop().time() + 2.0
    while asyncio.get_running_loop().time() < deadline and runtime.status().speech_backend is None:
        while runtime.reduce_next() is not None:
            pass
        await asyncio.sleep(0.02)
        while runtime.reduce_next() is not None:
            pass
    status = runtime.status()
    assert status.speech_backend == "espeak"
    projected = project_runtime_status(status)
    assert projected["speech"]["backend"] == "espeak"
    assert projected["components"]["tts"]["backend"] == "espeak"


def test_bridge_source_no_longer_hardcodes_sapi_backend() -> None:
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "irswitch"
        / "events"
        / "narrative_tts_bridge.py"
    )
    text = source.read_text(encoding="utf-8")
    assert '"backend": "sapi"' not in text
    assert "detect_backend" in text or "backend=" in text
