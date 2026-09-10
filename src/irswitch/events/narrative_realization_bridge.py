"""NarrativeRuntime-owned realization effect bridge (#284).

Turns plan-dispatch realization tokens into authored REALIZATION_SUCCEEDED
commands with speakable text sourced from a shadow draft cache. Not exported
from ``events/__init__.py``. Race wires this as ``realization_effect=`` so
live context batches can reach ``tts_effect``.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from irswitch.contracts.command import NarrativeCommand
from irswitch.events.narrative import NarrativeEvent
from irswitch.events.narrative_shadow_consumer import AdaptedPublication

logger = logging.getLogger(__name__)

EffectWorker = Callable[
    [dict[str, Any]], Awaitable[NarrativeCommand | list[NarrativeCommand] | None]
]

_WORD_RE = re.compile(r"[_\-.]+")


def _sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _humanize_kind(kind: str) -> str:
    leaf = kind.split(".")[-1] if kind else "update"
    words = [part for part in _WORD_RE.split(leaf) if part]
    if not words:
        return "Race update."
    title = " ".join(word.capitalize() for word in words)
    return f"{title}."


@dataclass
class SpeechDraftCache:
    """Latest speakable drafts observed from shadow-adapted publications."""

    max_drafts: int = 8
    _drafts: list[str] = field(default_factory=list)

    def observe_publication(self, publication: AdaptedPublication) -> None:
        for event in publication.events:
            text = draft_text_from_event(event)
            if text:
                self._drafts.append(text)
        if len(self._drafts) > self.max_drafts:
            self._drafts = self._drafts[-self.max_drafts :]

    def consume(self, *, fallback: str = "Race update.") -> str:
        if self._drafts:
            return self._drafts.pop(0)
        return fallback


def draft_text_from_event(event: NarrativeEvent) -> str | None:
    kind = str(getattr(event, "kind", "") or "")
    if not kind:
        envelope = getattr(event, "source_envelope", None)
        kind = str(getattr(envelope, "event_type", "") or "")
    if not kind:
        return None
    text = _humanize_kind(kind)
    normalized = " ".join(text.split())
    if not 1 <= len(normalized) <= 400:
        return None
    return normalized


def realization_result_payload(token: dict[str, Any], text: str) -> dict[str, Any]:
    normalized = " ".join(str(text).split())
    now_ms = int(time.monotonic() * 1000)
    request_id = str(token["requestId"])
    return {
        "schemaVersion": "realization-result/2",
        "resultId": f"result:{request_id}",
        "requestId": request_id,
        "requestOrdinal": int(token["requestOrdinal"]),
        "dispatchGeneration": int(token["dispatchGeneration"]),
        "backend": "authored",
        "outcome": "succeeded",
        "text": normalized,
        "textHash": _sha256(normalized),
        "failureReason": None,
        "modelReported": None,
        "transportStartedMonoMs": now_ms,
        "responseStartedMonoMs": now_ms,
        "firstContentMonoMs": now_ms,
        "completedMonoMs": now_ms + 1,
        "promptTokens": None,
        "completionTokens": None,
        "totalTokens": None,
        "usageSource": "unavailable",
        "finishReason": None,
        "resultHash": _sha256(f"{request_id}:{normalized}"),
    }


def build_realization_effect(
    draft_cache: SpeechDraftCache | None = None,
    *,
    fallback_text: str = "Race update.",
) -> EffectWorker:
    """Build a NarrativeRuntime ``realization_effect`` from shadow speech drafts."""

    cache = draft_cache if draft_cache is not None else SpeechDraftCache()

    async def realization_effect(token: dict[str, Any]) -> NarrativeCommand:
        text = cache.consume(fallback=fallback_text)
        mono_ms = int(time.monotonic() * 1000)
        try:
            return NarrativeCommand.realization_result(
                f"effect:rz:{token['requestId']}",
                "REALIZATION_SUCCEEDED",
                mono_ms,
                request_id=str(token["requestId"]),
                request_ordinal=int(token["requestOrdinal"]),
                dispatch_generation=int(token["dispatchGeneration"]),
                result=realization_result_payload(token, text),
            )
        except Exception:
            logger.warning("narrative realization_effect failed", exc_info=True)
            return NarrativeCommand.realization_result(
                f"effect:rz-fail:{token['requestId']}",
                "REALIZATION_FAILED",
                mono_ms,
                request_id=str(token["requestId"]),
                request_ordinal=int(token["requestOrdinal"]),
                dispatch_generation=int(token["dispatchGeneration"]),
                result={
                    "schemaVersion": "realization-result/2",
                    "resultId": f"result-fail:{token['requestId']}",
                    "requestId": str(token["requestId"]),
                    "requestOrdinal": int(token["requestOrdinal"]),
                    "dispatchGeneration": int(token["dispatchGeneration"]),
                    "backend": "authored",
                    "outcome": "failed",
                    "text": None,
                    "textHash": None,
                    "failureReason": "realization_invalid_response",
                    "modelReported": None,
                    "transportStartedMonoMs": mono_ms,
                    "responseStartedMonoMs": mono_ms,
                    "firstContentMonoMs": None,
                    "completedMonoMs": mono_ms + 1,
                    "promptTokens": None,
                    "completionTokens": None,
                    "totalTokens": None,
                    "usageSource": "unavailable",
                    "finishReason": None,
                    "resultHash": _sha256(f"fail:{token['requestId']}"),
                },
            )

    return realization_effect
