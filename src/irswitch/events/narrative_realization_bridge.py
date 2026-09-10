"""NarrativeRuntime-owned realization effect bridge (#284).

Turns plan-dispatch realization tokens into authored REALIZATION_SUCCEEDED
commands. Prefers #267 AuthoredPack lines when the selected beat is in the
pack; otherwise uses shadow draft-cache / event-kind humanized templates.
Not exported from ``events/__init__.py``.
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from irswitch.contracts.authored_pack import (
    AuthoredPack,
    AuthoredRealizer,
    authored_bundle,
    load_authored_pack,
)
from irswitch.contracts.command import NarrativeCommand
from irswitch.contracts.narrative import NarrativeEvent
from irswitch.events.narrative_shadow_consumer import AdaptedPublication
from irswitch.events.qwen_transport import (
    FakeTransport,
    LlmComponent,
    RealizationIntent,
    RealizerService,
    StdlibTransport,
    load_transport_goldens,
)

logger = logging.getLogger(__name__)

EffectWorker = Callable[
    [dict[str, Any]], Awaitable[NarrativeCommand | list[NarrativeCommand] | None]
]

_WORD_RE = re.compile(r"[_\-.]+")
_PACK: AuthoredPack | None = None
_REALIZER: AuthoredRealizer | None = None


def _sha256(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _humanize_kind(kind: str) -> str:
    leaf = kind.split(".")[-1] if kind else "update"
    words = [part for part in _WORD_RE.split(leaf) if part]
    if not words:
        return "Race update."
    title = " ".join(word.capitalize() for word in words)
    return f"{title}."


def _authored_pack() -> AuthoredPack:
    global _PACK
    if _PACK is None:
        _PACK = load_authored_pack()
    return _PACK


def _authored_realizer() -> AuthoredRealizer:
    global _REALIZER
    if _REALIZER is None:
        _REALIZER = AuthoredRealizer(_authored_pack())
    return _REALIZER


def resolve_authored_beat_id(
    kind: str | None,
    *,
    pack: AuthoredPack | None = None,
    event_type: str | None = None,
) -> str | None:
    """Map a narrative kind / V4 event type onto an authored-pack beat id."""

    catalog = pack if pack is not None else _authored_pack()
    beat_ids = set(catalog.beat_ids)
    candidates: list[str] = []
    if kind:
        raw = str(kind)
        candidates.append(raw)
        candidates.append(raw.replace("_", "."))
        candidates.append(raw.replace(".", "_"))
    if event_type:
        # Common V4 → beat id when taxonomy kind uses underscores.
        # Explicit map kept small; pack membership is the gate.
        mapped = {
            "LAP_COMPLETE": "timing.lap.completed",
            "PERSONAL_BEST": "timing.lap.personal_best",
            "SECTOR_BEST": "timing.sector.best",
            "SIDE_BY_SIDE": "battle.side_by_side",
            "BATTLE_WON": "battle.won",
            "PASS": "position.pass",
            "POSITION_GAIN": "position.gained",
            "POSITION_LOSS": "position.lost",
            "LEADER_CHANGE": "position.leader_change",
            "STREAM_STARTED": "stream.started",
            "YELLOW": "session.flag.yellow",
            "GREEN": "session.flag.green",
        }.get(str(event_type).upper())
        if mapped:
            candidates.append(mapped)
    for candidate in candidates:
        if candidate in beat_ids:
            return candidate
    return None


def _claim_surface(claim_id: str) -> str:
    parts = [part for part in claim_id.replace("_", ".").split(".") if part]
    skip = {
        "timing",
        "battle",
        "session",
        "incident",
        "pit",
        "stream",
        "position",
        "race",
    }
    words = [part for part in parts if part not in skip] or parts[-1:]
    return " ".join(words).replace("_", " ")


def _subject_from_event(event: NarrativeEvent | None) -> str:
    if event is None:
        return "The field"
    for key in event.correlation_key:
        value = str(key)
        if value.startswith("car:"):
            return f"Car {value.split(':', 1)[1]}"
        if value.startswith("driver:"):
            return value.split(":", 1)[1].replace("_", " ").title()
    return "The field"


def realize_authored_text(
    beat_id: str,
    *,
    subject: str = "The field",
    claim: str | None = None,
    now_ms: int | None = None,
    spoken_line_ids: tuple[str, ...] = (),
    pack: AuthoredPack | None = None,
    realizer: AuthoredRealizer | None = None,
) -> str | None:
    """Render one AuthoredPack line for ``beat_id``, or None when unavailable."""

    catalog = pack if pack is not None else _authored_pack()
    if beat_id not in catalog.beat_ids:
        return None
    lines = catalog.lines_for(beat_id)
    if not lines:
        return None
    line = lines[0]
    claim_id = line.required_claims[0] if line.required_claims else beat_id
    claim_text = (claim or _claim_surface(claim_id)).strip()
    subject_text = subject.strip() or "The field"
    mono = int(now_ms if now_ms is not None else time.monotonic() * 1000)
    lexicon = {
        "surfaceValueSets": [],
        "relationLexemes": [
            {
                "claimId": claim_id,
                "polarity": "positive",
                "temporalFrame": "current",
                "forms": [claim_text],
            }
        ],
        "connectives": [],
        "forbiddenLexemes": [],
        "subjectSurface": subject_text,
        "subjectActorId": "live",
    }
    try:
        bundle = authored_bundle(
            beat_id=beat_id,
            backend="authored",
            pattern_id=line.pattern_id,
            max_chars=160,
            max_seconds=13.0,
            required_claim_ids=line.required_claims or (claim_id,),
            selected_fact_ids=("fact:live:1",),
            planned_mono_ms=mono,
            expires_mono_ms=mono + 30_000,
            language="en",
            actor_bindings=(("live", (subject_text,)),),
            fact_bindings=(("fact:live:1", beat_id),),
            lexicon=lexicon,
        )
        step = (realizer or _authored_realizer()).realize(
            bundle,
            now_ms=mono,
            spoken_line_ids=spoken_line_ids,
        )
    except Exception:
        logger.debug("authored realize failed for %s", beat_id, exc_info=True)
        return None
    if step.outcome != "succeeded" or not step.text:
        return None
    return " ".join(str(step.text).split())


def realize_qwen_text(
    *,
    beat_id: str,
    request_ordinal: int,
    dispatch_generation: int,
    service: RealizerService,
    component: LlmComponent,
    now_ms: int | None = None,
    compiled_prompt: dict[str, Any] | None = None,
    episode_revision: int = 1,
) -> str | None:
    """Attempt one #269 Qwen realization; never falls back to authored inside transport."""

    if not component.qwen_ready:
        return None
    mono = int(now_ms if now_ms is not None else time.monotonic() * 1000)
    prompt = compiled_prompt
    if prompt is None:
        try:
            prompt = dict(load_transport_goldens()["compiledPrompt"])
        except Exception:
            logger.debug("qwen compiled prompt unavailable", exc_info=True)
            return None
    config_hash = "sha256:" + ("55" * 32)
    bundle_hash = "sha256:" + ("88" * 32)
    intent = RealizationIntent(
        process_instance_id="narrative-runtime",
        request_ordinal=int(request_ordinal),
        dispatch_generation=int(dispatch_generation),
        backend="qwen_compiled",
        plan_id=f"plan:{beat_id}",
        planning_cycle_id=f"cycle:{dispatch_generation}",
        cycle_attempt_ordinal=1,
        bundle_id=f"bundle:{beat_id}",
        bundle_hash=bundle_hash,
        compiled_prompt=prompt,
        component_generation=int(component.applied_generation or 1),
        config_generation=1,
        effective_config_hash=config_hash,
        config_apply_sequence=1,
        capture_prompt="hash",
        capture_completion=True,
        dispatched_mono_ms=mono,
        deadline_mono_ms=mono + 1_500,
        beat_id=str(beat_id),
        episode_revision=int(episode_revision),
        model="qwen3:4b-instruct-2507-q4_K_M",
        temperature=0.2,
        top_p=0.8,
        max_tokens=96,
        seed=17,
        pattern_id=f"{beat_id}:tight:1",
        render_contract_version=2,
        now_ms=mono,
    )
    try:
        step = service.try_start(intent, component=component)
        if step.outcome == "admitted":
            step = service.finish(now_ms=mono + 1)
        if step.outcome != "succeeded" or step.result is None or not step.result.text:
            return None
        return " ".join(str(step.result.text).split())
    except Exception:
        logger.debug("qwen realize failed for %s", beat_id, exc_info=True)
        return None


def warmup_qwen_component(
    component: LlmComponent,
    transport: FakeTransport | StdlibTransport,
    *,
    generation: int = 1,
    model: str = "qwen3:4b-instruct-2507-q4_K_M",
    endpoint: str = "http://127.0.0.1:11434/v1/chat/completions",
    timeout_ms: int = 500,
) -> bool:
    """Run #269 preflight warmup against ``transport``; soft-fail closed.

    Returns True when the component becomes ``qwen_ready``. Transport errors and
    non-200 responses leave Qwen ineligible while authored/template paths remain.
    """

    from irswitch.contracts.primitives import canonical_json
    from irswitch.events.qwen_transport import TransportError, warmup_request_body

    component.start_preflight(desired_generation=int(generation), warmup=True)
    body = canonical_json(warmup_request_body(model)).encode("utf-8")
    try:
        response = transport.post(
            endpoint,
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            body=body,
            stream=False,
            timeout_ms=max(1, int(timeout_ms)),
        )
        if int(response.status) != 200:
            component.complete_preflight(generation=int(generation), residency="warmup_failed")
            return False
    except TransportError:
        component.complete_preflight(generation=int(generation), residency="warmup_failed")
        return False
    except Exception:
        logger.debug("qwen warmup failed", exc_info=True)
        component.complete_preflight(generation=int(generation), residency="warmup_failed")
        return False
    component.complete_preflight(generation=int(generation), residency="warmup_succeeded")
    return bool(component.qwen_ready)


@dataclass(frozen=True, slots=True)
class SpeechDraft:
    text: str
    beat_id: str | None = None
    source: str = "template"


@dataclass
class SpeechDraftCache:
    """Latest speakable drafts observed from shadow-adapted publications."""

    max_drafts: int = 8
    _drafts: list[SpeechDraft] = field(default_factory=list)
    _spoken_line_ids: list[str] = field(default_factory=list)

    def observe_publication(self, publication: AdaptedPublication) -> None:
        for event in publication.events:
            draft = draft_from_event(event)
            if draft is not None:
                self._drafts.append(draft)
        if len(self._drafts) > self.max_drafts:
            self._drafts = self._drafts[-self.max_drafts :]

    def consume(self, *, fallback: str = "Race update.") -> SpeechDraft:
        if self._drafts:
            return self._drafts.pop(0)
        return SpeechDraft(text=fallback, beat_id=None, source="fallback")

    def note_spoken_line(self, line_id: str | None) -> None:
        if not line_id:
            return
        self._spoken_line_ids.append(str(line_id))
        if len(self._spoken_line_ids) > 32:
            self._spoken_line_ids = self._spoken_line_ids[-32:]

    @property
    def spoken_line_ids(self) -> tuple[str, ...]:
        return tuple(self._spoken_line_ids)


def draft_from_event(event: NarrativeEvent) -> SpeechDraft | None:
    """Build a speakable draft, preferring AuthoredPack when the beat maps."""

    kind = str(getattr(event, "kind", "") or "")
    event_type = None
    envelope = getattr(event, "source_envelope", None)
    if envelope is not None:
        event_type = str(getattr(envelope, "event_type", "") or "") or None
        if not kind:
            kind = event_type or ""
    if not kind and not event_type:
        return None
    beat_id = resolve_authored_beat_id(kind, event_type=event_type)
    if beat_id is not None:
        authored = realize_authored_text(
            beat_id,
            subject=_subject_from_event(event),
            now_ms=int(getattr(event, "occurred_mono_ms", 0) or 0) or None,
        )
        if authored:
            return SpeechDraft(text=authored, beat_id=beat_id, source="authored")
    text = _humanize_kind(kind or event_type or "update")
    normalized = " ".join(text.split())
    if not 1 <= len(normalized) <= 400:
        return None
    return SpeechDraft(text=normalized, beat_id=beat_id, source="template")


def draft_text_from_event(event: NarrativeEvent) -> str | None:
    """Compatibility helper returning only speakable text."""

    draft = draft_from_event(event)
    return None if draft is None else draft.text


def realization_result_payload(
    token: dict[str, Any], text: str, *, backend: str = "authored"
) -> dict[str, Any]:
    normalized = " ".join(str(text).split())
    now_ms = int(time.monotonic() * 1000)
    request_id = str(token["requestId"])
    return {
        "schemaVersion": "realization-result/2",
        "resultId": f"result:{request_id}",
        "requestId": request_id,
        "requestOrdinal": int(token["requestOrdinal"]),
        "dispatchGeneration": int(token["dispatchGeneration"]),
        "backend": backend,
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
    prefer_authored: bool = True,
    allow_qwen: bool = False,
    qwen_service: RealizerService | None = None,
    llm_component: LlmComponent | None = None,
) -> EffectWorker:
    """Build a NarrativeRuntime ``realization_effect``.

    Order: authored pack (when preferred + mapped) → optional #269 Qwen
    (when ``allow_qwen`` and component ready) → shadow draft / template fallback.
    Qwen transport failure never invents authored fallback inside the transport;
    this bridge may still speak a template draft after a Qwen miss.
    """

    cache = draft_cache if draft_cache is not None else SpeechDraftCache()

    async def realization_effect(token: dict[str, Any]) -> NarrativeCommand:
        mono_ms = int(time.monotonic() * 1000)
        text: str | None = None
        backend = "authored"
        beat_id = token.get("beatId")
        resolved: str | None = None
        if isinstance(beat_id, str) and beat_id:
            resolved = resolve_authored_beat_id(beat_id) or beat_id
        if prefer_authored and resolved is not None:
            text = realize_authored_text(
                resolved,
                now_ms=mono_ms,
                spoken_line_ids=cache.spoken_line_ids,
            )
        if (
            text is None
            and allow_qwen
            and qwen_service is not None
            and llm_component is not None
            and isinstance(beat_id, str)
            and beat_id
        ):
            qwen_text = realize_qwen_text(
                beat_id=str(beat_id),
                request_ordinal=int(token["requestOrdinal"]),
                dispatch_generation=int(token["dispatchGeneration"]),
                service=qwen_service,
                component=llm_component,
                now_ms=mono_ms,
            )
            if qwen_text:
                text = qwen_text
                backend = "qwen_compiled"
        if text is None:
            draft = cache.consume(fallback=fallback_text)
            text = draft.text
            backend = "authored" if draft.source == "authored" else "authored"
            if prefer_authored and draft.beat_id and draft.source != "authored":
                authored = realize_authored_text(
                    draft.beat_id,
                    now_ms=mono_ms,
                    spoken_line_ids=cache.spoken_line_ids,
                )
                if authored:
                    text = authored
            if (
                text == draft.text
                and allow_qwen
                and qwen_service is not None
                and llm_component is not None
                and draft.beat_id
                and draft.source != "authored"
            ):
                qwen_text = realize_qwen_text(
                    beat_id=str(draft.beat_id),
                    request_ordinal=int(token["requestOrdinal"]),
                    dispatch_generation=int(token["dispatchGeneration"]),
                    service=qwen_service,
                    component=llm_component,
                    now_ms=mono_ms,
                )
                if qwen_text:
                    text = qwen_text
                    backend = "qwen_compiled"
        try:
            return NarrativeCommand.realization_result(
                f"effect:rz:{token['requestId']}",
                "REALIZATION_SUCCEEDED",
                mono_ms,
                request_id=str(token["requestId"]),
                request_ordinal=int(token["requestOrdinal"]),
                dispatch_generation=int(token["dispatchGeneration"]),
                result=realization_result_payload(token, text, backend=backend),
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
