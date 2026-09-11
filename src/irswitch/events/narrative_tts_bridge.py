"""NarrativeRuntime-owned TTS effect bridge (#284 / #349 Slice 3).

Turns utterance tokens into ProcessTtsSink / speak_text playback and streams
mailbox TTS callbacks. Accept is emitted at the enqueue/start boundary;
terminal callbacks follow real idle/cancel/fail outcomes. Backend identity
comes from ``detect_backend`` (or an explicit override), never a hardcoded
``sapi`` label.

Not exported from ``events/__init__.py``. Race wires this as ``tts_effect=``
and drops CommentaryConsumer speech ownership.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any, Literal, Protocol, cast

from irswitch.commentary.graph import GraphNode, TtsLimits
from irswitch.commentary.tts import CommentaryUtterance, detect_backend, speak_text
from irswitch.contracts.command import NarrativeCommand

logger = logging.getLogger(__name__)

EffectWorker = Callable[
    [dict[str, Any]],
    Awaitable[NarrativeCommand | list[NarrativeCommand] | None] | AsyncIterator[NarrativeCommand],
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


def _resolve_backend(explicit: str | None) -> str:
    if explicit is not None and str(explicit).strip():
        return str(explicit).strip().lower()
    return str(detect_backend() or "null").strip().lower() or "null"


def _tts_callback(
    kind: str,
    token: dict[str, Any],
    *,
    mono_ms: int,
    backend: str,
    worker_sequence: int,
) -> NarrativeCommand:
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
        f"tts:{kind}:{utterance_id}:{worker_sequence}",
        kind_lit,
        mono_ms,
        utterance_id=utterance_id,
        utterance_ordinal=utterance_ordinal,
        backend_generation=backend_generation,
        dispatch_generation=dispatch_generation,
        callback={
            "schemaVersion": "tts-callback/2",
            "callbackId": f"cb:{kind}:{utterance_id}:{worker_sequence}",
            "kind": callback_kind,
            "utteranceId": utterance_id,
            "utteranceOrdinal": utterance_ordinal,
            "backend": backend,
            "backendGeneration": backend_generation,
            "dispatchGeneration": dispatch_generation,
            "workerSequence": int(worker_sequence),
            "observedMonoMs": mono_ms,
            "detailCode": detail,
        },
    )


def _interrupt_sink(sink: _EnqueueSink | None) -> None:
    if sink is None:
        return
    interrupt = getattr(sink, "interrupt", None)
    if callable(interrupt):
        try:
            interrupt()
        except Exception:
            logger.debug("narrative tts_effect interrupt failed", exc_info=True)


def build_tts_effect(
    sink: _EnqueueSink | None = None,
    *,
    locale: str = "en",
    idle_timeout_s: float = 30.0,
    backend: str | None = None,
) -> EffectWorker:
    """Build a NarrativeRuntime ``tts_effect`` worker around a process TTS sink.

    Returns an async generator that yields ``PLAYBACK_ACCEPTED`` at the enqueue
    boundary, then a terminal callback after idle/fail/cancel. ``backend`` pins
    identity for tests; otherwise ``detect_backend()`` is used.
    """

    resolved_backend = _resolve_backend(backend)

    async def tts_effect(token: dict[str, Any]) -> AsyncIterator[NarrativeCommand]:
        mono_ms = int(time.monotonic() * 1000)
        text = str(token.get("text") or "").strip()
        if not text:
            yield _tts_callback(
                "PLAYBACK_ACCEPTED",
                token,
                mono_ms=mono_ms,
                backend=resolved_backend,
                worker_sequence=1,
            )
            yield _tts_callback(
                "SPEECH_COMPLETED",
                token,
                mono_ms=mono_ms + 1,
                backend=resolved_backend,
                worker_sequence=2,
            )
            return

        try:
            if sink is not None:
                sink.enqueue(_bridge_utterance(text, token, locale=locale))
            else:
                # speak_text path has no separate accept boundary before audio;
                # accept is still emitted before the blocking speak returns.
                pass
            yield _tts_callback(
                "PLAYBACK_ACCEPTED",
                token,
                mono_ms=mono_ms,
                backend=resolved_backend,
                worker_sequence=1,
            )
            if sink is not None:
                wait_idle = getattr(sink, "wait_idle", None)
                if callable(wait_idle):
                    idle_ok = await asyncio.to_thread(wait_idle, idle_timeout_s)
                    if not idle_ok:
                        yield _tts_callback(
                            "SPEECH_FAILED",
                            token,
                            mono_ms=int(time.monotonic() * 1000),
                            backend=resolved_backend,
                            worker_sequence=2,
                        )
                        return
                # Null / non-waiting sinks complete immediately after accept.
            else:
                await asyncio.to_thread(speak_text, text, locale=locale)
            yield _tts_callback(
                "SPEECH_COMPLETED",
                token,
                mono_ms=int(time.monotonic() * 1000),
                backend=resolved_backend,
                worker_sequence=2,
            )
        except asyncio.CancelledError:
            _interrupt_sink(sink)
            yield _tts_callback(
                "SPEECH_INTERRUPTED",
                token,
                mono_ms=int(time.monotonic() * 1000),
                backend=resolved_backend,
                worker_sequence=2,
            )
            return
        except Exception:
            logger.warning("narrative tts_effect playback failed", exc_info=True)
            _interrupt_sink(sink)
            yield _tts_callback(
                "SPEECH_FAILED",
                token,
                mono_ms=int(time.monotonic() * 1000),
                backend=resolved_backend,
                worker_sequence=2,
            )

    return tts_effect  # type: ignore[return-value]
