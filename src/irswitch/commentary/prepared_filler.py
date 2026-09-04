"""Bounded asynchronous preparation of situation-specific filler variants."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from math import ceil, isfinite
from typing import Any, Protocol

import aiohttp

from irswitch.commentary.graph import (
    PreparedRelation,
    SequenceGraph,
    load_sequence_graph,
    normalize_graph_mode,
)
from irswitch.overlay.settings import CommentarySettings, PreparedFillerSettings

_SENTENCE_END = re.compile(r"[.!?]+(?:[\"'’)]*)?(?:\s+|$)")
_NUMBER = re.compile(r"(?<!\w)-?\d+(?:[.,]\d+)?")
_SPACE = re.compile(r"\s+")
_FORBIDDEN_CLAIM_PATTERNS: dict[str, tuple[re.Pattern[str], ...]] = {
    "cause": tuple(
        re.compile(pattern, re.IGNORECASE)
        for pattern in (
            r"\bbecause\b",
            r"\bdue to\b",
            r"\bcaused by\b",
            r"\bprotože\b",
            r"\bkvůli\b",
            r"\bzpůsobil(?:a|o|i|y)?\b",
        )
    ),
    "prediction": tuple(
        re.compile(pattern, re.IGNORECASE)
        for pattern in (
            r"\bwill (?:win|finish|take|beat)\b",
            r"\bgoing to (?:win|finish|take|beat)\b",
            r"\bexpected to\b",
            r"\b(?:likely|probably)\b",
            r"\bpravděpodobně\b",
            r"\bnejspíš\b",
            r"\burčitě (?:vyhraje|dojede|porazí)\b",
        )
    ),
    "blame": tuple(
        re.compile(pattern, re.IGNORECASE)
        for pattern in (
            r"\b(?:his|her|their) fault\b",
            r"\bto blame\b",
            r"\bmistake by\b",
            r"\bjeho vina\b",
            r"\bjejí vina\b",
            r"\bzavinil(?:a)?\b",
        )
    ),
    "nationality": tuple(
        re.compile(pattern, re.IGNORECASE)
        for pattern in (
            r"\b(?:czech|slovak|german|french|italian|spanish|british|american|dutch|polish|belgian) driver\b",
            r"\b(?:český|slovenský|německý|francouzský|italský|španělský|britský|americký|nizozemský|polský|belgický) jezdec\b",
        )
    ),
    "result_certainty": tuple(
        re.compile(pattern, re.IGNORECASE)
        for pattern in (
            r"\bconfirmed result\b",
            r"\bofficial result\b",
            r"\bfinal classification\b",
            r"\bpotvrzený výsledek\b",
            r"\boficiální výsledek\b",
            r"\bkonečná klasifikace\b",
        )
    ),
    "setup_improvement": tuple(
        re.compile(pattern, re.IGNORECASE)
        for pattern in (
            r"\b(?:improved|better) setup\b",
            r"\bsetup (?:has improved|is better)\b",
            r"\b(?:lepší|zlepšené) nastavení\b",
            r"\bnastavení se zlepšilo\b",
        )
    ),
    "difficulty": tuple(
        re.compile(pattern, re.IGNORECASE)
        for pattern in (
            r"\b(?:hard|difficult|challenging) (?:track|circuit)\b",
            r"\b(?:těžká|obtížná|náročná) (?:trať|dráha)\b",
        )
    ),
}
PREPARED_CONTEXT_FACT_IDS = (
    "track",
    "layout",
    "city",
    "country",
    "circuit_length",
    "turn_count",
    "track_type",
    "track_direction",
    "sky",
    "air_temperature",
    "track_temperature",
    "wind_speed",
    "precipitation",
    "surface_wetness",
    "rubber_state",
    "field_size",
    "class_field_size",
    "overall_sof",
    "class_sof",
    "ai_count",
    "ai_ratio",
    "circulating_cars",
    "traffic_band",
    "hero_position",
    "engine_state",
    "rollout_state",
    "qualifying_position",
    "grid_position",
    "start_position",
    "highest_rated_driver",
    "start_mode",
    "distance_to_start",
    "start_ready",
    "start_set",
    "hr_band",
)


class PreparedFillerHealth(StrEnum):
    DISABLED = "disabled"
    WAITING_CONTEXT = "waiting_context"
    GENERATING = "generating"
    READY = "ready"
    DEGRADED = "degraded"
    FATAL = "fatal"


@dataclass(frozen=True, slots=True)
class FactProposition:
    proposition_id: str
    value: str | int | float
    source: str
    source_revision: str
    spoken_value: str

    def canonical(self) -> dict[str, object]:
        return {
            "id": self.proposition_id,
            "value": self.value,
            "source": self.source,
            "source_revision": self.source_revision,
            "spoken_value": self.spoken_value,
        }


@dataclass(frozen=True, slots=True)
class PreparedFillerPlan:
    plan_id: str
    situation_id: str
    node_id: str
    semantic_key: str
    locale: str
    scope_key: str
    material_revision: str
    stage_epoch: int
    allowed_stages: tuple[str, ...]
    required: tuple[FactProposition, ...]
    optional: tuple[FactProposition, ...] = ()
    contract_revision: str = ""
    relation: str = PreparedRelation.NONE.value
    intent: str = ""
    forbidden_claims: tuple[str, ...] = ()
    anchors: tuple[str, ...] = ()
    tts_max_chars: int = 600
    tts_max_seconds: float = 13.0
    valid_until_ms: int | None = None
    tier: int = 0
    terminal: bool = False

    @classmethod
    def create(
        cls,
        *,
        node_id: str,
        semantic_key: str,
        locale: str,
        scope_key: str,
        stage_epoch: int,
        allowed_stages: Iterable[str],
        required: Iterable[FactProposition],
        optional: Iterable[FactProposition] = (),
        contract_revision: str = "",
        relation: str = PreparedRelation.NONE.value,
        intent: str = "",
        forbidden_claims: Iterable[str] = (),
        anchors: Iterable[str] = (),
        tts_max_chars: int = 600,
        tts_max_seconds: float = 13.0,
        valid_until_ms: int | None = None,
        tier: int = 0,
        terminal: bool = False,
    ) -> PreparedFillerPlan:
        required_facts = tuple(required)
        optional_facts = tuple(optional)
        stages = tuple(allowed_stages)
        situation_id = _digest(
            {
                "node": node_id,
                "semantic": semantic_key,
                "locale": locale,
                "scope": scope_key,
                "contract": contract_revision,
            }
        )
        material_revision = _digest(
            {
                "required": [item.canonical() for item in required_facts],
                "optional": [item.canonical() for item in optional_facts],
            }
        )
        plan_id = _digest(
            {
                "schema": "prepared-filler/1",
                "situation": situation_id,
                "material": material_revision,
            }
        )
        return cls(
            plan_id=plan_id,
            situation_id=situation_id,
            node_id=node_id,
            semantic_key=semantic_key,
            locale=locale,
            scope_key=scope_key,
            material_revision=material_revision,
            stage_epoch=stage_epoch,
            allowed_stages=stages,
            required=required_facts,
            optional=optional_facts,
            contract_revision=contract_revision,
            relation=relation,
            intent=intent,
            forbidden_claims=tuple(forbidden_claims),
            anchors=tuple(anchors),
            tts_max_chars=max(1, int(tts_max_chars)),
            tts_max_seconds=max(0.1, float(tts_max_seconds)),
            valid_until_ms=valid_until_ms,
            tier=tier,
            terminal=terminal,
        )


@dataclass(frozen=True, slots=True)
class PreparedVariant:
    variant_id: str
    plan_id: str
    text: str
    estimated_seconds: float


@dataclass(slots=True)
class VariantExposure:
    spoken_count: int = 0
    last_spoken_ms: int | None = None


@dataclass(slots=True)
class _BufferedPlan:
    plan: PreparedFillerPlan
    variants: dict[str, PreparedVariant] = field(default_factory=dict)
    exposure: dict[str, VariantExposure] = field(default_factory=dict)
    attempts: int = 0
    exhausted: bool = False
    generation_complete: bool = False
    last_error: str | None = None


@dataclass(frozen=True, slots=True)
class PreparedSelection:
    plan: PreparedFillerPlan
    variant: PreparedVariant


class PreparedGenerator(Protocol):
    async def __call__(
        self,
        plan: PreparedFillerPlan,
        count: int,
        existing_hashes: tuple[str, ...],
    ) -> list[str]: ...


class PreparedFillerBuffer:
    def __init__(self, settings: PreparedFillerSettings) -> None:
        self.settings = settings
        self._items: dict[str, _BufferedPlan] = {}
        self._desired: dict[str, PreparedFillerPlan] = {}
        self.current_stage = ""
        self.stale_dropped = 0

    @property
    def desired(self) -> tuple[PreparedFillerPlan, ...]:
        return tuple(self._desired.values())

    def reconcile(self, plans: Iterable[PreparedFillerPlan], *, current_stage: str = "") -> None:
        ordered = sorted(plans, key=lambda plan: (plan.tier, plan.situation_id, plan.plan_id))
        if not current_stage and ordered and ordered[0].allowed_stages:
            current_stage = ordered[0].allowed_stages[0]
        self.current_stage = current_stage
        current = [plan for plan in ordered if current_stage in plan.allowed_stages]
        following = [plan for plan in ordered if current_stage not in plan.allowed_stages]
        selected = current[: self.settings.reserved_current_stage]
        selected.extend(following[: self.settings.reserved_next_stage])
        selected_ids = {plan.situation_id for plan in selected}
        selected.extend(plan for plan in ordered if plan.situation_id not in selected_ids)
        selected = selected[: self.settings.max_ready_plans]
        desired = {plan.situation_id: plan for plan in selected}
        for situation_id in tuple(self._items):
            wanted = desired.get(situation_id)
            if wanted is None or wanted.plan_id != self._items[situation_id].plan.plan_id:
                self.stale_dropped += len(self._items[situation_id].variants)
                del self._items[situation_id]
        for situation_id, plan in desired.items():
            self._items.setdefault(situation_id, _BufferedPlan(plan=plan))
        self._desired = desired

    def need_generation(self) -> list[tuple[PreparedFillerPlan, int, tuple[str, ...]]]:
        jobs: list[tuple[PreparedFillerPlan, int, tuple[str, ...]]] = []
        for plan in sorted(
            self._desired.values(),
            key=lambda item: (
                0 if self.current_stage in item.allowed_stages else 1,
                item.tier,
                item.plan_id,
            ),
        ):
            entry = self._items[plan.situation_id]
            if entry.generation_complete or len(entry.variants) >= self.settings.variants_max:
                continue
            count = self.settings.variants_max - len(entry.variants)
            jobs.append((plan, count, tuple(sorted(entry.variants))))
        return jobs

    def merge(self, plan: PreparedFillerPlan, texts: Iterable[str]) -> int:
        entry = self._items.get(plan.situation_id)
        if entry is None or entry.plan.plan_id != plan.plan_id:
            return 0
        added = 0
        for text in texts:
            normalized = _normalize_text(text)
            if not normalized:
                continue
            variant_id = _digest({"plan": plan.plan_id, "text": normalized})
            if variant_id in entry.variants:
                continue
            entry.variants[variant_id] = PreparedVariant(
                variant_id=variant_id,
                plan_id=plan.plan_id,
                text=text.strip(),
                estimated_seconds=max(0.8, len(text.split()) / 2.7),
            )
            entry.exposure[variant_id] = VariantExposure()
            added += 1
            if len(entry.variants) >= self.settings.variants_max:
                break
        return added

    def note_attempt(self, plan: PreparedFillerPlan, error: str | None) -> None:
        entry = self._items.get(plan.situation_id)
        if entry is None or entry.plan.plan_id != plan.plan_id:
            return
        entry.attempts += 1
        entry.last_error = error
        if entry.attempts >= self.settings.generation_max_attempts:
            entry.generation_complete = True
            entry.exhausted = len(entry.variants) < self.settings.variants_min

    def select(self, stage: str, now_ms: int) -> PreparedSelection | None:
        eligible = self._eligible(stage, now_ms)
        if not eligible:
            return None
        entry = min(
            eligible,
            key=lambda item: (
                item.plan.tier,
                sum(exposure.spoken_count for exposure in item.exposure.values()),
                max(
                    (exposure.last_spoken_ms or -1 for exposure in item.exposure.values()),
                    default=-1,
                ),
                item.plan.semantic_key,
                item.plan.plan_id,
            ),
        )
        return PreparedSelection(entry.plan, self._variant(entry))

    def selections(self, stage: str, now_ms: int) -> tuple[PreparedSelection, ...]:
        return tuple(
            PreparedSelection(entry.plan, self._variant(entry))
            for entry in self._eligible(stage, now_ms)
        )

    def _eligible(self, stage: str, now_ms: int) -> list[_BufferedPlan]:
        eligible: list[_BufferedPlan] = []
        for entry in self._items.values():
            plan = entry.plan
            if stage not in plan.allowed_stages:
                continue
            if plan.valid_until_ms is not None and now_ms > plan.valid_until_ms:
                continue
            if len(entry.variants) < self.settings.variants_min:
                continue
            eligible.append(entry)
        return sorted(eligible, key=lambda item: (item.plan.tier, item.plan.semantic_key))

    @staticmethod
    def _variant(entry: _BufferedPlan) -> PreparedVariant:
        return min(
            entry.variants.values(),
            key=lambda item: (
                entry.exposure[item.variant_id].spoken_count,
                entry.exposure[item.variant_id].last_spoken_ms or -1,
                item.variant_id,
            ),
        )

    def mark_spoken(self, variant_id: str, now_ms: int) -> bool:
        for entry in self._items.values():
            exposure = entry.exposure.get(variant_id)
            if exposure is None:
                continue
            exposure.spoken_count += 1
            exposure.last_spoken_ms = now_ms
            return True
        return False

    def is_current(self, plan_id: str, stage: str, now_ms: int) -> bool:
        return any(
            entry.plan.plan_id == plan_id
            and stage in entry.plan.allowed_stages
            and (entry.plan.valid_until_ms is None or now_ms <= entry.plan.valid_until_ms)
            for entry in self._items.values()
        )

    def stage_drained(self, stage: str) -> bool:
        entries = [entry for entry in self._items.values() if stage in entry.plan.allowed_stages]
        if not entries:
            return False
        return all(
            entry.exhausted
            or (
                len(entry.variants) >= self.settings.variants_min
                and any(item.spoken_count > 0 for item in entry.exposure.values())
            )
            for entry in entries
        )

    def status(self) -> dict[str, object]:
        ready = sum(
            len(entry.variants) >= self.settings.variants_min for entry in self._items.values()
        )
        return {
            "readyPlans": ready,
            "desiredPlans": len(self._desired),
            "variants": sum(len(entry.variants) for entry in self._items.values()),
            "exhaustedPlans": sum(entry.exhausted for entry in self._items.values()),
            "staleDropped": self.stale_dropped,
            "readyCurrentStage": sum(
                self.current_stage in entry.plan.allowed_stages
                and len(entry.variants) >= self.settings.variants_min
                for entry in self._items.values()
            )
            if self.current_stage
            else 0,
            "readyNextStage": sum(
                self.current_stage not in entry.plan.allowed_stages
                and len(entry.variants) >= self.settings.variants_min
                for entry in self._items.values()
            ),
        }

    def has_unfinished(self) -> bool:
        return any(
            not entry.generation_complete and len(entry.variants) < self.settings.variants_min
            for entry in self._items.values()
        )

    def all_exhausted_without_ready(self) -> bool:
        return bool(self._items) and all(
            entry.exhausted and len(entry.variants) < self.settings.variants_min
            for entry in self._items.values()
        )

    def current_plan_ids(self) -> set[str]:
        return {
            entry.plan.plan_id
            for entry in self._items.values()
            if self.current_stage in entry.plan.allowed_stages
        }

    def has_unfinished_current(self) -> bool:
        return any(
            self.current_stage in entry.plan.allowed_stages
            and not entry.generation_complete
            and len(entry.variants) < self.settings.variants_min
            for entry in self._items.values()
        )

    def all_current_exhausted_without_ready(self) -> bool:
        current = [
            entry
            for entry in self._items.values()
            if self.current_stage in entry.plan.allowed_stages
        ]
        return bool(current) and all(
            entry.exhausted and len(entry.variants) < self.settings.variants_min
            for entry in current
        )


class PreparedFillerCoordinator:
    """Owns bounded generation tasks and continuously reconciles the buffer."""

    def __init__(
        self,
        settings: PreparedFillerSettings,
        generator: PreparedGenerator,
        *,
        diagnostic: Callable[[dict[str, Any]], None] | None = None,
    ) -> None:
        self.settings = settings
        self.generator = generator
        self.buffer = PreparedFillerBuffer(settings)
        self.diagnostic = diagnostic
        self.health = PreparedFillerHealth.DISABLED
        self.fatal_episode = 0
        self.fatal_notice_spoken = False
        self.last_error: str | None = None
        self.generated = 0
        self.rejected = 0
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._closed = False
        self._mode = settings.mode
        self._epoch = 0

    def reopen(self) -> None:
        """Allow the same consumer instance to recover after supervisor restart."""
        self._closed = False
        if self.settings.mode == "legacy":
            self.health = PreparedFillerHealth.DISABLED

    def reconcile(self, plans: Iterable[PreparedFillerPlan], *, current_stage: str = "") -> None:
        if self._closed:
            self.health = PreparedFillerHealth.DISABLED
            return
        if self.settings.mode != self._mode:
            self._epoch += 1
            for task in self._tasks.values():
                task.cancel()
            self._tasks.clear()
            self.buffer.reconcile(())
            self._mode = self.settings.mode
            self.last_error = None
        if self.settings.mode == "legacy":
            for task in self._tasks.values():
                task.cancel()
            self._tasks.clear()
            self.buffer.reconcile(())
            self.health = PreparedFillerHealth.DISABLED
            return
        self.buffer.reconcile(plans, current_stage=current_stage)
        desired_ids = {plan.plan_id for plan in self.buffer.desired}
        for plan_id, task in tuple(self._tasks.items()):
            if plan_id not in desired_ids:
                task.cancel()
                del self._tasks[plan_id]
        self._schedule()
        self._refresh_health()

    async def wait_idle(self) -> None:
        while self._tasks:
            tasks = tuple(self._tasks.values())
            await asyncio.gather(*tasks, return_exceptions=True)

    async def close(self) -> None:
        self._closed = True
        self._epoch += 1
        tasks = tuple(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._tasks.clear()
        self.health = PreparedFillerHealth.DISABLED

    def take(self, stage: str, now_ms: int) -> PreparedSelection | None:
        return self.buffer.select(stage, now_ms)

    def mark_spoken(self, variant_id: str, now_ms: int) -> bool:
        return self.buffer.mark_spoken(variant_id, now_ms)

    def fatal_notice(self, locale: str) -> tuple[int, str] | None:
        if self.settings.mode != "active" or self.health != PreparedFillerHealth.FATAL:
            return None
        if self.fatal_notice_spoken:
            return None
        text = (
            "LLM fatal error, nemám texty."
            if locale.strip().lower().startswith("cs")
            else "LLM fatal error, I have no text."
        )
        return self.fatal_episode, text

    def mark_fatal_notice_spoken(self, episode: int) -> bool:
        if episode != self.fatal_episode or self.health != PreparedFillerHealth.FATAL:
            return False
        if self.fatal_notice_spoken:
            return False
        self.fatal_notice_spoken = True
        return True

    def status(self) -> dict[str, object]:
        buffer_status = self.buffer.status()
        desired = (
            buffer_status["desiredPlans"] if isinstance(buffer_status["desiredPlans"], int) else 0
        )
        ready = buffer_status["readyPlans"] if isinstance(buffer_status["readyPlans"], int) else 0
        return {
            "mode": self.settings.mode,
            "health": self.health.value,
            **buffer_status,
            "queuedPlans": max(0, desired - ready),
            "inflight": len(self._tasks),
            "generated": self.generated,
            "rejected": self.rejected,
            "fatalEpisode": self.fatal_episode,
            "fatalNoticeSpoken": self.fatal_notice_spoken,
            "lastErrorCode": self.last_error,
        }

    def _schedule(self) -> None:
        slots = max(0, self.settings.max_inflight - len(self._tasks))
        for plan, count, hashes in self.buffer.need_generation():
            if slots <= 0 or plan.plan_id in self._tasks:
                break
            task = asyncio.create_task(
                self._generate(plan, count, hashes, self._epoch),
                name=f"prepared-filler:{plan.plan_id[:10]}",
            )
            self._tasks[plan.plan_id] = task
            slots -= 1

    async def _generate(
        self, plan: PreparedFillerPlan, count: int, hashes: tuple[str, ...], epoch: int
    ) -> None:
        error: str | None = None
        valid: list[str] = []
        try:
            texts = await asyncio.wait_for(
                self.generator(plan, count, hashes),
                timeout=self.settings.generation_timeout_s,
            )
            valid, errors = validate_generated_variants(plan, texts, self.settings)
            if epoch == self._epoch:
                self.generated += self.buffer.merge(plan, valid)
                self.rejected += len(errors)
            error = errors[0] if errors else None
        except asyncio.CancelledError:
            raise
        except TimeoutError:
            error = "timeout"
            if epoch == self._epoch:
                self.rejected += 1
        except Exception:
            error = "transport"
            if epoch == self._epoch:
                self.rejected += 1
        finally:
            if epoch == self._epoch:
                self.buffer.note_attempt(plan, error)
                self.last_error = error
            current = asyncio.current_task()
            if self._tasks.get(plan.plan_id) is current:
                self._tasks.pop(plan.plan_id, None)
            if not self._closed and epoch == self._epoch:
                self._schedule()
                self._refresh_health()
                self._emit(
                    "generated" if error is None else "rejected",
                    plan,
                    error,
                    accepted_texts=valid,
                )

    def _refresh_health(self) -> None:
        previous = self.health
        status = self.buffer.status()
        ready_plans = (
            status["readyCurrentStage"] if isinstance(status["readyCurrentStage"], int) else 0
        )
        current_ids = self.buffer.current_plan_ids()
        current_inflight = any(plan_id in current_ids for plan_id in self._tasks)
        if not current_ids:
            current = PreparedFillerHealth.WAITING_CONTEXT
        elif ready_plans > 0:
            current = (
                PreparedFillerHealth.DEGRADED if self.last_error else PreparedFillerHealth.READY
            )
        elif current_inflight or self.buffer.has_unfinished_current():
            current = PreparedFillerHealth.GENERATING
        elif self.buffer.all_current_exhausted_without_ready():
            current = PreparedFillerHealth.FATAL
        else:
            current = PreparedFillerHealth.WAITING_CONTEXT
        if current == PreparedFillerHealth.FATAL and previous != current:
            self.fatal_episode += 1
            self.fatal_notice_spoken = False
        elif current in {PreparedFillerHealth.READY, PreparedFillerHealth.DEGRADED}:
            self.fatal_notice_spoken = False
        self.health = current

    def _emit(
        self,
        action: str,
        plan: PreparedFillerPlan,
        reason: str | None,
        *,
        accepted_texts: Iterable[str] = (),
    ) -> None:
        if self.diagnostic is None:
            return
        self.diagnostic(
            {
                "action": action,
                "planId": plan.plan_id,
                "situationId": plan.situation_id,
                "nodeId": plan.node_id,
                "semanticKey": plan.semantic_key,
                "reason": reason,
                "acceptedTexts": list(accepted_texts),
            }
        )


class OpenAICompatiblePreparedGenerator:
    def __init__(
        self,
        commentary: CommentarySettings,
        *,
        history_titles: Callable[[], tuple[str, ...]] | None = None,
    ) -> None:
        self.commentary = commentary
        self.history_titles = history_titles or (lambda: ())

    async def __call__(
        self,
        plan: PreparedFillerPlan,
        count: int,
        existing_hashes: tuple[str, ...],
    ) -> list[str]:
        payload = _generation_request(
            self.commentary,
            plan,
            count,
            existing_hashes,
            history_titles=self.history_titles(),
        )
        url = self.commentary.llm_base_url.rstrip("/")
        if not url.endswith("/chat/completions"):
            url += "/chat/completions"
        timeout = aiohttp.ClientTimeout(total=self.commentary.prepared_filler.generation_timeout_s)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload) as response:
                response.raise_for_status()
                raw = await response.json()
        content = raw["choices"][0]["message"]["content"]
        decoded = json.loads(content)
        if decoded.get("schema") != "prepared-filler/1" or decoded.get("planId") != plan.plan_id:
            raise ValueError("plan_mismatch")
        variants = decoded.get("variants")
        if not isinstance(variants, list):
            raise ValueError("invalid_json")
        return [item for item in variants if isinstance(item, str)][:count]


def build_prepared_filler_plans(
    context: dict[str, Any],
    locale: str,
    *,
    graph: SequenceGraph | None = None,
) -> tuple[PreparedFillerPlan, ...]:
    """Bind immutable facts to concrete current/next-stage graph contracts."""
    sequence_graph = graph or load_sequence_graph()
    editorial = context.get("editorial")
    identity = context.get("identity")
    race = context.get("race")
    story = context.get("story")
    prepared = context.get("prepared")
    if not isinstance(editorial, dict) or not isinstance(identity, dict):
        return ()
    race = race if isinstance(race, dict) else {}
    story = story if isinstance(story, dict) else {}
    prepared = prepared if isinstance(prepared, dict) else {}
    stage = str(editorial.get("stage") or "")
    if stage in {"", "INACTIVE", "WAIT_CONTEXT"}:
        return ()
    session_id = str(context.get("session_id") or "")
    run_epoch = _integer(identity.get("run_epoch"))
    class_id = _positive_integer(race.get("player_car_class")) or 0
    track = _nonempty(editorial.get("track_name"))
    mode = _localized_mode(identity.get("overlay_mode"), locale)
    if not session_id:
        return ()
    revision = f"session:{session_id}:run:{run_epoch}"
    track_fact = FactProposition("track", track, "telemetry", revision, track) if track else None
    mode_fact = FactProposition("session", mode, "telemetry", revision, mode) if mode else None
    field_size = race.get("class_field_size")
    field_fact: FactProposition | None = None
    if isinstance(field_size, int) and not isinstance(field_size, bool) and field_size > 0:
        field_fact = FactProposition(
            "class_field_size", field_size, "telemetry", revision, str(field_size)
        )
    skies_fact: FactProposition | None = None
    weather = story.get("weather")
    if isinstance(weather, dict):
        skies = _nonempty(weather.get("skies"))
        if skies is not None:
            spoken_skies = _localized_skies(skies, locale)
            skies_fact = FactProposition("sky", skies, "telemetry", revision, spoken_skies)
    position = race.get("class_position")
    position_fact: FactProposition | None = None
    hero_position_fact: FactProposition | None = None
    finish_position_fact: FactProposition | None = None
    if isinstance(position, int) and not isinstance(position, bool) and position > 0:
        position_fact = FactProposition(
            "class_position", position, "telemetry", revision, str(position)
        )
        hero_position_fact = FactProposition(
            "hero_position", position, "telemetry", revision, _spoken_position(position, locale)
        )
        finish_position_fact = FactProposition(
            "finish_position", position, "telemetry", revision, _spoken_position(position, locale)
        )
    lap_count = _positive_integer(race.get("lap_completed"))
    lap_fact = (
        FactProposition("completed_laps", lap_count, "telemetry", revision, str(lap_count))
        if lap_count is not None
        else None
    )
    best_lap = _positive_number(race.get("best_lap_time"))
    best_fact = (
        FactProposition(
            "best_lap_seconds",
            best_lap,
            "telemetry",
            revision,
            f"{best_lap:.3f}",
        )
        if best_lap is not None
        else None
    )
    stage_epoch = _integer(editorial.get("stage_epoch"))
    stream_epoch = _integer(editorial.get("stream_epoch"))
    stint_epoch = _integer(editorial.get("stint_epoch"))
    overlay_mode = str(identity.get("overlay_mode") or "").strip().upper()
    graph_mode = normalize_graph_mode(overlay_mode)
    confirmed = bool(race.get("player_finished") or race.get("session_finished"))
    result_status_fact = FactProposition(
        "result_status",
        "confirmed" if confirmed else "unconfirmed",
        "telemetry",
        revision,
        _localized_result_status(confirmed, locale),
    )
    out_lap_fact = FactProposition(
        "out_lap",
        True,
        "editorial_stage",
        revision,
        "výjezdové kolo" if locale.lower().startswith("cs") else "out lap",
    )
    formation_fact = FactProposition(
        "formation_state",
        "formation",
        "editorial_stage",
        revision,
        "formační kolo" if locale.lower().startswith("cs") else "formation lap",
    )
    prepared_facts = {
        fact_id: _prepared_context_fact(fact_id, prepared.get(fact_id), locale, revision)
        for fact_id in PREPARED_CONTEXT_FACT_IDS
    }
    quali_position = _scoped_quali_position(context, class_id)
    grid_position = _scoped_grid_position(context, class_id)
    quali_fact = (
        FactProposition(
            "qualifying_position",
            quali_position,
            "stream_memory",
            revision,
            _spoken_position(quali_position, locale),
        )
        if quali_position is not None
        else None
    )
    grid_fact = (
        FactProposition(
            "grid_position",
            grid_position,
            "stream_memory",
            revision,
            _spoken_position(grid_position, locale),
        )
        if grid_position is not None
        else None
    )
    facts: dict[str, FactProposition | None] = {
        "track": track_fact,
        "session": mode_fact,
        "class_field_size": field_fact,
        "sky": skies_fact,
        "class_position": position_fact,
        "hero_position": hero_position_fact,
        "finish_position": finish_position_fact,
        "completed_laps": lap_fact,
        "best_lap_seconds": best_fact,
        "result_status": result_status_fact,
        "qualifying_position": quali_fact,
        "grid_position": grid_fact,
        "start_position": grid_fact,
        "out_lap": out_lap_fact,
        "formation_state": formation_fact,
        **prepared_facts,
    }
    # Prefer already-normalized race/story values where they are more
    # authoritative than the optional prepared-context enrichment.
    facts.update(
        {
            "track": track_fact or prepared_facts["track"],
            "class_field_size": field_fact or prepared_facts["class_field_size"],
            "sky": skies_fact or prepared_facts["sky"],
            "hero_position": hero_position_fact or prepared_facts["hero_position"],
            "qualifying_position": quali_fact or prepared_facts["qualifying_position"],
            "grid_position": grid_fact or prepared_facts["grid_position"],
            "start_position": grid_fact or prepared_facts["start_position"],
        }
    )
    plans: list[PreparedFillerPlan] = []

    def add_node(
        node_id: str,
        planned_stage: str,
        planned_epoch: int,
    ) -> None:
        node = sequence_graph.node(node_id)
        contract = node.prepared if node is not None else None
        if node is None or contract is None:
            return
        if planned_stage not in contract.allowed_stages:
            return
        if node.modes and graph_mode not in node.modes:
            return
        bound = dict(facts)
        relation_fact = _relation_proposition(
            contract.relation,
            finish_position=_positive_integer(position),
            qualifying_position=quali_position,
            grid_position=grid_position,
            locale=locale,
            revision=revision,
        )
        if relation_fact is not None:
            bound[relation_fact.proposition_id] = relation_fact
        needed: list[FactProposition] = []
        for fact_id in contract.required_facts:
            fact = bound.get(fact_id)
            if fact is None:
                return
            needed.append(fact)
        extras = tuple(
            fact for fact_id in contract.optional_facts if (fact := bound.get(fact_id)) is not None
        )
        contract_revision = _digest(
            {
                "prepared": contract.canonical(),
                "tts": {
                    "max_chars": node.tts.max_chars,
                    "max_seconds": node.tts.max_seconds,
                },
            }
        )
        contract_locale = "cs" if locale.lower().startswith("cs") else "en"
        scope = (
            f"stream:{stream_epoch}:session:{session_id}:run:{run_epoch}:"
            f"stage:{planned_epoch}:stint:{stint_epoch}:class:{class_id or 0}"
        )
        plans.append(
            PreparedFillerPlan.create(
                node_id=node.id,
                semantic_key=node.id,
                locale=locale,
                scope_key=scope,
                stage_epoch=planned_epoch,
                allowed_stages=contract.allowed_stages,
                required=needed,
                optional=extras,
                contract_revision=contract_revision,
                relation=contract.relation.value,
                intent=contract.intent[contract_locale],
                forbidden_claims=(item.value for item in contract.forbidden_claims),
                anchors=contract.anchors[contract_locale],
                tts_max_chars=node.tts.max_chars,
                tts_max_seconds=node.tts.max_seconds,
                tier=contract.tier,
                terminal=contract.terminal,
            )
        )

    def add_conclusion(planned_stage: str, planned_epoch: int) -> None:
        # Result copy is never generated from a changing live position. P/Q waits
        # for the player's finish edge; after eight seconds only a generic close is eligible.
        captured_ms = _integer(context.get("captured_monotonic_ms"))
        started_ms = _integer(editorial.get("stage_started_monotonic_ms"))
        timed_out = (
            planned_stage == stage
            and captured_ms >= started_ms
            and captured_ms - started_ms >= 8_000
        )
        if not confirmed:
            if planned_stage != stage and overlay_mode == "PRACTICE":
                add_node("practice_value_debrief", planned_stage, planned_epoch)
            if timed_out:
                add_node("result_unconfirmed", planned_stage, planned_epoch)
            return
        if overlay_mode == "PRACTICE":
            add_node("practice_checkered_summary", planned_stage, planned_epoch)
            add_node("practice_value_debrief", planned_stage, planned_epoch)
            if bool(prepared.get("lobby_break")):
                add_node("practice_lobby_break", planned_stage, planned_epoch)
            return
        if overlay_mode == "QUALIFYING":
            topic = (
                "quali_result_unclassified"
                if position_fact is None
                else f"quali_result_{result_band(position, field_size)}"
            )
            add_node(topic, planned_stage, planned_epoch)
            add_node("quali_to_race_bridge", planned_stage, planned_epoch)
            return
        topic = _race_result_topic(context, position, field_size, class_id)
        add_node(topic, planned_stage, planned_epoch)

    def add_stage(planned_stage: str, planned_epoch: int) -> None:
        if planned_stage == "STREAM_LOBBY_INTRO":
            for node_id in (
                "stream_intro_venue",
                "stream_intro_circuit_character",
                "stream_intro_conditions",
                "stream_intro_surface_state",
                "stream_intro_field_overall",
                "stream_intro_field_class",
                "stream_intro_ai_field",
            ):
                if node_id == "stream_intro_conditions" and sum(
                    facts.get(fact_id) is not None
                    for fact_id in (
                        "sky",
                        "air_temperature",
                        "track_temperature",
                        "wind_speed",
                        "precipitation",
                    )
                ) < 2:
                    continue
                add_node(node_id, planned_stage, planned_epoch)
            add_node("practice_quiet_track", planned_stage, planned_epoch)
        elif planned_stage == "SESSION_EVENT_INTRO":
            event_intro_node_id = {
                "PRACTICE": "event_intro_practice",
                "QUALIFYING": "event_intro_qualifying",
                "RACE": "event_intro_race",
            }.get(overlay_mode)
            if event_intro_node_id is not None:
                add_node(event_intro_node_id, planned_stage, planned_epoch)
        elif planned_stage == "IN_CAR_PREP":
            add_node("hero_prepares_to_drive", planned_stage, planned_epoch)
            for node_id in (
                "engine_started",
                "rollout_started",
                "practice_quiet_track",
            ):
                add_node(node_id, planned_stage, planned_epoch)
            if bool(prepared.get("returned_to_car")):
                add_node("returned_to_car", planned_stage, planned_epoch)
        elif planned_stage == "OUT_LAP":
            add_node("out_lap_preparation", planned_stage, planned_epoch)
            add_node("out_lap_field_context", planned_stage, planned_epoch)
        elif planned_stage == "GRID_PREP":
            add_node("race_quali_recap_result", planned_stage, planned_epoch)
            add_node("race_grid_field", planned_stage, planned_epoch)
            add_node("race_grid_highest_rated", planned_stage, planned_epoch)
            if str(prepared.get("start_mode") or "") == "rolling":
                add_node("rolling_start_setup", planned_stage, planned_epoch)
            elif str(prepared.get("start_mode") or "") == "standing":
                add_node("standing_start_setup", planned_stage, planned_epoch)
        elif planned_stage == "FORMATION_OR_LIGHTS":
            if bool(prepared.get("start_set")):
                add_node("start_lights_set", planned_stage, planned_epoch)
            elif bool(prepared.get("start_ready")):
                add_node("start_lights_ready", planned_stage, planned_epoch)
            else:
                if str(prepared.get("start_mode") or "") == "rolling":
                    add_node("rolling_start_setup", planned_stage, planned_epoch)
                    add_node("formation_lap_preparation", planned_stage, planned_epoch)
                    add_node("formation_lap_tension", planned_stage, planned_epoch)
                elif str(prepared.get("start_mode") or "") == "standing":
                    add_node("standing_start_setup", planned_stage, planned_epoch)
        elif planned_stage == "SESSION_CONCLUSION":
            add_conclusion(planned_stage, planned_epoch)
        elif planned_stage == "BETWEEN_SESSIONS":
            add_node("stream_chapter_bridge", planned_stage, planned_epoch)

    add_stage(stage, stage_epoch)
    next_stage = _nonempty(editorial.get("next_stage"))
    if next_stage and next_stage != stage:
        add_stage(next_stage, stage_epoch + 1)
    return tuple(plans)


def result_band(position: object, class_size: object) -> str:
    """Return the deterministic class-result branch from specification section 17."""
    pos = _positive_integer(position)
    size = _positive_integer(class_size)
    if pos is None:
        return "unclassified"
    if pos == 1:
        return "pole"
    if pos <= 3 and (size is None or pos <= size):
        return "podium"
    if size is None:
        return "classified"
    if pos > size:
        return "unclassified"
    if size < 6:
        return "classified"
    third = ceil(size / 3)
    if pos <= third:
        return "top_third"
    if pos <= min(size, 2 * third):
        return "middle_third"
    return "rear_third"


def _race_result_topic(
    context: dict[str, Any], position: object, class_size: object, class_id: int
) -> str:
    pos = _positive_integer(position)
    if pos is None:
        return "race_result_unclassified"
    band = result_band(pos, class_size)
    if band == "pole":
        return "race_result_win"
    if band == "podium":
        return "race_result_podium"
    story = context.get("story")
    story = story if isinstance(story, dict) else {}
    identity = context.get("identity")
    identity = identity if isinstance(identity, dict) else {}
    quali = story.get("quali_bag")
    if isinstance(quali, dict) and _same_result_scope(
        quali, class_id, identity.get("subsession_id")
    ):
        quali_position = _positive_integer(quali.get("class_position"))
        if quali_position is not None:
            relation = (
                "gain" if pos < quali_position else "loss" if pos > quali_position else "hold"
            )
            return f"race_result_{relation}_vs_quali"
    grid_position = _positive_integer(story.get("race_grid_position"))
    if (
        grid_position is not None
        and _positive_integer(story.get("race_grid_class_id")) == class_id
        and str(story.get("race_grid_subsession_id") or "")
        == str(identity.get("subsession_id") or "")
    ):
        relation = "gain" if pos < grid_position else "loss" if pos > grid_position else "hold"
        return f"race_result_{relation}_vs_grid"
    return f"race_result_{band}"


def _same_result_scope(value: object, class_id: int, subsession_id: object) -> bool:
    return bool(
        isinstance(value, dict)
        and _positive_integer(value.get("class_id")) == class_id
        and str(value.get("subsession_id") or "") == str(subsession_id or "")
    )


def _scoped_quali_position(context: dict[str, Any], class_id: int) -> int | None:
    story = context.get("story")
    story = story if isinstance(story, dict) else {}
    identity = context.get("identity")
    identity = identity if isinstance(identity, dict) else {}
    bag = story.get("quali_bag")
    if not _same_result_scope(bag, class_id, identity.get("subsession_id")):
        return None
    return _positive_integer(bag.get("class_position")) if isinstance(bag, dict) else None


def _scoped_grid_position(context: dict[str, Any], class_id: int) -> int | None:
    story = context.get("story")
    story = story if isinstance(story, dict) else {}
    identity = context.get("identity")
    identity = identity if isinstance(identity, dict) else {}
    if _positive_integer(story.get("race_grid_class_id")) != class_id or str(
        story.get("race_grid_subsession_id") or ""
    ) != str(identity.get("subsession_id") or ""):
        return None
    return _positive_integer(story.get("race_grid_position"))


def _relation_proposition(
    relation: PreparedRelation,
    *,
    finish_position: int | None,
    qualifying_position: int | None,
    grid_position: int | None,
    locale: str,
    revision: str,
) -> FactProposition | None:
    comparisons = {
        PreparedRelation.FINISH_BETTER_THAN_QUALIFYING: (
            qualifying_position,
            "better",
            "qualifying",
        ),
        PreparedRelation.FINISH_EQUAL_TO_QUALIFYING: (
            qualifying_position,
            "equal",
            "qualifying",
        ),
        PreparedRelation.FINISH_WORSE_THAN_QUALIFYING: (
            qualifying_position,
            "worse",
            "qualifying",
        ),
        PreparedRelation.FINISH_BETTER_THAN_GRID: (grid_position, "better", "grid"),
        PreparedRelation.FINISH_EQUAL_TO_GRID: (grid_position, "equal", "grid"),
        PreparedRelation.FINISH_WORSE_THAN_GRID: (grid_position, "worse", "grid"),
    }
    comparison = comparisons.get(relation)
    if comparison is None or finish_position is None:
        return None
    reference, direction, source = comparison
    if reference is None:
        return None
    valid = {
        "better": finish_position < reference,
        "equal": finish_position == reference,
        "worse": finish_position > reference,
    }[direction]
    if not valid:
        return None
    if locale.lower().startswith("cs"):
        relation_word = {"better": "lepší", "equal": "stejný", "worse": "horší"}[direction]
        reference_word = "kvalifikace" if source == "qualifying" else "startovní pozice"
        spoken = (
            f"potvrzený dojezd na {finish_position}. místě je {relation_word} než "
            f"{reference_word} na {reference}. místě"
            if direction != "equal"
            else (
                f"potvrzený dojezd na {finish_position}. místě je stejný jako "
                f"{reference_word} na {reference}. místě"
            )
        )
    else:
        relation_word = {"better": "better than", "equal": "equal to", "worse": "worse than"}[
            direction
        ]
        reference_word = "qualifying P" if source == "qualifying" else "grid P"
        spoken = (
            f"confirmed finish P{finish_position} is {relation_word} {reference_word}{reference}"
        )
    return FactProposition(
        "result_relation",
        relation.value,
        "derived_relation",
        revision,
        spoken,
    )


def _spoken_position(position: int, locale: str) -> str:
    return f"{position}. místo" if locale.lower().startswith("cs") else f"P{position}"


def _localized_result_status(confirmed: bool, locale: str) -> str:
    if locale.lower().startswith("cs"):
        return "potvrzený výsledek" if confirmed else "výsledek není potvrzený"
    return "confirmed result" if confirmed else "result is not confirmed"


def _prepared_context_fact(
    fact_id: str,
    value: object,
    locale: str,
    revision: str,
) -> FactProposition | None:
    """Turn one normalized producer fact into a localized immutable proposition."""
    if value is None or value == "":
        return None
    cs = locale.lower().startswith("cs")
    canonical_value: str | int | float
    positive_integer_facts = {
        "field_size",
        "class_field_size",
        "overall_sof",
        "class_sof",
        "ai_count",
        "turn_count",
    }
    position_facts = {"hero_position", "qualifying_position", "grid_position", "start_position"}
    if fact_id in positive_integer_facts:
        number = _positive_integer(value)
        if number is None:
            return None
        canonical_value = number
        spoken = str(number)
    elif fact_id == "circulating_cars":
        number = _non_negative_integer(value)
        if number is None:
            return None
        canonical_value = number
        spoken = str(number)
    elif fact_id in position_facts:
        number = _positive_integer(value)
        if number is None:
            return None
        canonical_value = number
        spoken = _spoken_position(number, locale)
    elif fact_id == "circuit_length":
        length = _positive_number(value)
        if length is None:
            return None
        canonical_value = length
        spoken = f"{length:g} km"
    elif fact_id in {"air_temperature", "track_temperature"}:
        temperature = _number_value(value)
        if temperature is None:
            return None
        canonical_value = temperature
        spoken = f"{temperature:g} C"
    elif fact_id == "wind_speed":
        speed = _non_negative_number(value)
        if speed is None:
            return None
        canonical_value = speed
        spoken = f"{speed:g} m/s"
    elif fact_id in {"ai_ratio", "precipitation"}:
        ratio = _ratio(value)
        if ratio is None:
            return None
        canonical_value = ratio
        spoken = f"{round(ratio * 100):d} percent"
    elif fact_id in {"start_ready", "start_set"}:
        if value is not True:
            return None
        canonical_value = "ready" if fact_id == "start_ready" else "set"
        spoken = {
            "start_ready": "světla jsou připravena" if cs else "the start lights are ready",
            "start_set": "světla jsou nastavena" if cs else "the start lights are set",
        }[fact_id]
    else:
        text = _nonempty(value)
        if text is None:
            return None
        canonical_value = text
        vocabulary = {
            "sky": {
                "clear": "jasno" if cs else "clear skies",
                "partly cloudy": "polojasno" if cs else "partly cloudy skies",
                "mostly cloudy": "oblačno" if cs else "mostly cloudy skies",
                "overcast": "zataženo" if cs else "overcast skies",
            },
            "traffic_band": {
                "nearby": "provoz je blízko" if cs else "traffic is nearby",
                "clear": "kolem vozu je volná trať" if cs else "the track around the car is clear",
            },
            "engine_state": {
                "started": "motor nastartoval" if cs else "the engine has started",
            },
            "rollout_state": {
                "moving": "vůz se rozjel" if cs else "the car has begun moving",
            },
            "start_mode": {
                "rolling": "letmý start" if cs else "rolling start",
                "standing": "pevný start" if cs else "standing start",
            },
            "distance_to_start": {
                "near": "vůz se blíží ke startovní čáře"
                if cs
                else "the car is approaching the start line",
            },
            "surface_wetness": {
                "dry": "suchý povrch" if cs else "dry surface",
                "damp": "vlhký povrch" if cs else "damp surface",
                "wet": "mokrý povrch" if cs else "wet surface",
            },
        }
        spoken = vocabulary.get(fact_id, {}).get(text.casefold(), text)
    return FactProposition(fact_id, canonical_value, "prepared_context", revision, spoken)


def validate_generated_variants(
    plan: PreparedFillerPlan,
    texts: Iterable[str],
    settings: PreparedFillerSettings,
) -> tuple[list[str], list[str]]:
    valid: list[str] = []
    errors: list[str] = []
    seen: set[str] = set()
    allowed_numbers = {
        number.replace(",", ".")
        for fact in (*plan.required, *plan.optional)
        for number in _NUMBER.findall(str(fact.spoken_value))
    }
    for raw in texts:
        text = raw.strip()
        normalized = _normalize_text(text)
        if not normalized:
            errors.append("empty_variant")
            continue
        if normalized in seen:
            errors.append("duplicate_variant")
            continue
        sentences = len(_SENTENCE_END.findall(text))
        if sentences < 2 or sentences > 5:
            errors.append("sentence_count")
            continue
        if len(text.split()) / 2.7 > settings.max_utterance_s:
            errors.append("duration")
            continue
        if len(text) > plan.tts_max_chars:
            errors.append("length")
            continue
        if len(text.split()) / 2.7 > plan.tts_max_seconds:
            errors.append("duration")
            continue
        numbers = {number.replace(",", ".") for number in _NUMBER.findall(text)}
        if not numbers.issubset(allowed_numbers):
            errors.append("grounding")
            continue
        if any(_normalize_text(fact.spoken_value) not in normalized for fact in plan.required):
            errors.append("required_fact")
            continue
        unsupported = _unsupported_claim(plan, normalized)
        if unsupported is not None:
            errors.append(f"forbidden_claim:{unsupported}")
            continue
        if _relation_is_contradicted(plan, normalized):
            errors.append("relation_contradiction")
            continue
        seen.add(normalized)
        valid.append(text)
    return valid[: settings.variants_max], errors


def _unsupported_claim(plan: PreparedFillerPlan, normalized: str) -> str | None:
    remainder = normalized
    for fact in plan.required:
        remainder = remainder.replace(_normalize_text(fact.spoken_value), " ")
    for category in plan.forbidden_claims:
        if any(pattern.search(remainder) for pattern in _FORBIDDEN_CLAIM_PATTERNS.get(category, ())):
            return category
    return None


def _relation_is_contradicted(plan: PreparedFillerPlan, normalized: str) -> bool:
    relation = plan.relation
    if not relation.startswith("finish_"):
        return False
    remainder = normalized
    for fact in plan.required:
        remainder = remainder.replace(_normalize_text(fact.spoken_value), " ")
    better = bool(re.search(r"\b(?:better than|improved on|lepší než|polepšil)\b", remainder))
    equal = bool(re.search(r"\b(?:equal to|matched|stejný jako|odpovídá)\b", remainder))
    worse = bool(re.search(r"\b(?:worse than|lost to|horší než|pohoršil)\b", remainder))
    if "_better_" in relation:
        return equal or worse
    if "_equal_" in relation:
        return better or worse
    if "_worse_" in relation:
        return better or equal
    return False


def _generation_request(
    settings: CommentarySettings,
    plan: PreparedFillerPlan,
    count: int,
    existing_hashes: tuple[str, ...],
    *,
    history_titles: tuple[str, ...] = (),
) -> dict[str, object]:
    facts = {
        "schema": "prepared-filler/1",
        "planId": plan.plan_id,
        "nodeId": plan.node_id,
        "semanticKey": plan.semantic_key,
        "editorialStage": list(plan.allowed_stages),
        "locale": plan.locale,
        "requestedVariants": count,
        "existingVariantHashes": list(existing_hashes),
        "required": [item.canonical() for item in plan.required],
        "optional": [item.canonical() for item in plan.optional],
        "contractRevision": plan.contract_revision,
        "relation": plan.relation,
        "intent": plan.intent,
        "forbiddenClaims": list(plan.forbidden_claims),
        "anchors": list(plan.anchors),
        "constraints": {
            "sentencesMin": 2,
            "sentencesMax": 5,
            "maxChars": plan.tts_max_chars,
            "maxSeconds": min(settings.prepared_filler.max_utterance_s, plan.tts_max_seconds),
            "noNewFacts": True,
        },
        "styleMemory": {
            "recentCompletedStreamTitles": list(history_titles[:20]),
            "use": "wording diversity only; never present these titles as current facts",
        },
    }
    return {
        "model": settings.llm_model,
        "temperature": settings.llm_temperature,
        "max_tokens": max(360, settings.llm_max_tokens),
        "think": False,
        "reasoning_effort": "none",
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return only JSON with schema, planId and variants. Write 2-5 sentences per "
                    "variant. Follow the localized intent and relation. Anchors illustrate meaning "
                    "but are not text to copy. Use every required spoken_value exactly. Add no "
                    "facts, numbers, names or forbidden claims."
                ),
            },
            {"role": "user", "content": json.dumps(facts, ensure_ascii=False, sort_keys=True)},
        ],
    }


def _normalize_text(value: object) -> str:
    return _SPACE.sub(" ", str(value).strip().casefold())


def _nonempty(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _localized_mode(value: object, locale: str) -> str | None:
    mode = str(value or "").strip().upper()
    if locale.lower().startswith("cs"):
        return {"PRACTICE": "trénink", "QUALIFYING": "kvalifikace", "RACE": "závod"}.get(mode)
    return {"PRACTICE": "practice", "QUALIFYING": "qualifying", "RACE": "race"}.get(mode)


def _localized_skies(value: str, locale: str) -> str:
    if not locale.lower().startswith("cs"):
        return value
    return {
        "clear": "jasno",
        "partly cloudy": "polojasno",
        "mostly cloudy": "oblačno",
        "overcast": "zataženo",
    }.get(value.casefold(), value)


def _integer(value: object) -> int:
    if isinstance(value, bool):
        return 0
    if not isinstance(value, (str, int, float)):
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def _positive_integer(value: object) -> int | None:
    number = _integer(value)
    return number if number > 0 else None


def _non_negative_integer(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _number_value(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _non_negative_number(value: object) -> float | None:
    number = _number_value(value)
    return number if number is not None and number >= 0 else None


def _ratio(value: object) -> float | None:
    number = _number_value(value)
    return number if number is not None and 0 <= number <= 1 else None


def _positive_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (str, int, float)):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _digest(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
