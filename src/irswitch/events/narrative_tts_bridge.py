"""NarrativeRuntime-owned TTS effect bridge (#284).

Turns utterance tokens into ProcessTtsSink / speak_text playback and returns
mailbox TTS callbacks. Not exported from ``events/__init__.py``. Race wires
this as ``tts_effect=`` and drops CommentaryConsumer speech ownership.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any, Literal, Protocol, cast

from irswitch.commentary.graph import GraphNode, TtsLimits
from irswitch.commentary.tts import CommentaryUtterance, speak_text
from irswitch.contracts.command import NarrativeCommand

logger = logging.getLogger(__name__)

EffectWorker = Callable[
    [dict[str, Any]], Awaitable[NarrativeCommand | list[NarrativeCommand] | None]
]


class _EnqueueSink(Protocol):
    def enqueue(self, utterance: CommentaryUtterance) -> None: ...


_BRIDGE_NODE = GraphNode(
    id="narrative.runtime.bridge",
    family="narrative",
    event_types=("NARRATIVE_RUNTIME",),
    phases=("LIVE",),
    speak_priority=1,
    cooldown_s=0.0,
    slots=(),
    hr_states=("unknown",),
    tts=TtsLimits(),
)


def _bridge_utterance(text: str, token: dict[str, Any], *, locale: str) -> CommentaryUtterance:
    utterance_id = str(token.get("utteranceId") or "utterance:bridge")
    return CommentaryUtterance(
        node_id=_BRIDGE_NODE.id,
        locale=locale,
        emotion="unknown",
        text=text,
        event_type="NARRATIVE_RUNTIME",
        event_id=utterance_id,
        correlation_id=utterance_id,
        estimated_seconds=max(1.0, len(text) / 12.0),
        node=_BRIDGE_NODE,
        priority=0,
    )


def _tts_callback(kind: str, token: dict[str, Any], *, mono_ms: int) -> NarrativeCommand:
    utterance_id = str(token["utteranceId"])
    utterance_ordinal = int(token["utteranceOrdinal"])
    backend_generation = int(token["backendGeneration"])
    dispatch_generation = int(token["dispatchGeneration"])
    kind_map = {
        "PLAYBACK_ACCEPTED": ("playback_accepted", None),
        "SPEECH_COMPLETED": ("completed", None),
        "SPEECH_INTERRUPTED": ("interrupted", "backend_cancelled"),
        "SPEECH_FAILED": ("failed", "backend_rejected"),
    }
    callback_kind, detail = kind_map[kind]
    kind_lit = cast(
        Literal["PLAYBACK_ACCEPTED", "SPEECH_COMPLETED", "SPEECH_INTERRUPTED", "SPEECH_FAILED"],
        kind,
    )
    return NarrativeCommand.tts_callback(
        f"tts:{kind}:{utterance_id}",
        kind_lit,
        mono_ms,
        utterance_id=utterance_id,
        utterance_ordinal=utterance_ordinal,
        backend_generation=backend_generation,
        dispatch_generation=dispatch_generation,
        callback={
            "schemaVersion": "tts-callback/2",
            "callbackId": f"cb:{kind}:{utterance_id}",
            "kind": callback_kind,
            "utteranceId": utterance_id,
            "utteranceOrdinal": utterance_ordinal,
            "backend": "sapi",
            "backendGeneration": backend_generation,
            "dispatchGeneration": dispatch_generation,
            "workerSequence": 1,
            "observedMonoMs": mono_ms,
            "detailCode": detail,
        },
    )


def build_tts_effect(
    sink: _EnqueueSink | None = None,
    *,
    locale: str = "en",
    idle_timeout_s: float = 30.0,
) -> EffectWorker:
    """Build a NarrativeRuntime ``tts_effect`` worker around a process TTS sink."""

    async def tts_effect(token: dict[str, Any]) -> list[NarrativeCommand]:
        mono_ms = int(time.monotonic() * 1000)
        text = str(token.get("text") or "").strip()
        if text:
            try:
                if sink is not None:
                    sink.enqueue(_bridge_utterance(text, token, locale=locale))
                    wait_idle = getattr(sink, "wait_idle", None)
                    if callable(wait_idle):
                        await asyncio.to_thread(wait_idle, idle_timeout_s)
                else:
                    await asyncio.to_thread(speak_text, text, locale=locale)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("narrative tts_effect playback failed", exc_info=True)
                return [_tts_callback("SPEECH_FAILED", token, mono_ms=mono_ms)]
        return [
            _tts_callback("PLAYBACK_ACCEPTED", token, mono_ms=mono_ms),
            _tts_callback("SPEECH_COMPLETED", token, mono_ms=mono_ms + 1),
        ]

    return tts_effect
