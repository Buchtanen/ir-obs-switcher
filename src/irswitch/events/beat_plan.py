"""Immutable BeatPlan and idle-lane just-in-time planner (v2 issue #261).

Not live-wired and not exported from ``events/__init__.py``. Does not import
commentary or overlay packages or emit an utterance.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from irswitch.contracts.catalog_loader import load_narrative_catalog
from irswitch.contracts.primitives import (
    ContractViolation,
    CycleAttemptOrdinal,
    Identifier,
    LineageId,
    MonotonicMs,
    OccurrenceId,
    PlanningSeedMaterial,
    SchemaVersion,
    Sha256Hash,
    deterministic_planning_seed,
    validate_occurrence_lineage,
)

SCHEMA_VERSION = "beat-plan/2"
PROMPT_SCHEMA = "prompt-options/2"
GLOBAL_CONSECUTIVE_CAP = 3
STREAM_NULL_BEATS = frozenset({"stream.started", "filler.lobby"})
BUSY_LANES = frozenset({"building", "committed", "speaking", "stopping"})
SELF_CONTAINED_POLICIES = frozenset({"critical", "result"})
ROLE_MAP = {
    "opening": "opening",
    "update": "update",
    "outcome": "outcome",
    "result": "outcome",
    "recap": "recap",
    "transition": "transition",
    "filler": "filler",
    "single": "filler",
}
G0_FORBIDDEN = (
    "unbound.cause",
    "unbound.intent",
    "unbound.emotion",
    "unsupported.certainty",
    "unsupported.future_outcome",
    "unsupported.weather_inference",
    "unsupported.medical_inference",
    "unbound.entity",
    "unbound.number",
    "unbound.unit",
)
CANDIDATE_SOURCES = frozenset({"event_opportunity", "story_successor", "episode_beat", "filler"})
SOURCE_CLASSES = frozenset({"detector", "direct", "lifecycle", "silence", "successor"})
POLARITIES = frozenset({"positive", "negative"})
FRAMES = frozenset({"current", "projected", "historical"})


def _id(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ContractViolation(f"{field} must be an ID")
    return str(Identifier(value))


def _optional_id(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _id(value, field)


def _ids(values: tuple[str, ...], field: str, *, minimum: int, maximum: int) -> tuple[str, ...]:
    items = tuple(_id(item, field) for item in values)
    if len(items) != len(set(items)):
        raise ContractViolation(f"{field} must be unique")
    if not minimum <= len(items) <= maximum:
        raise ContractViolation(f"{field} count must be {minimum}..{maximum}")
    return items


def _mono(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractViolation(f"{field} must be monotonic milliseconds")
    return int(MonotonicMs(value))


def _hash(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ContractViolation(f"{field} must be a hash")
    return str(Sha256Hash(value))


@dataclass(frozen=True, slots=True)
class CandidateOrder:
    reducer_sequence: int
    source_ordinal: int

    def __post_init__(self) -> None:
        if isinstance(self.reducer_sequence, bool) or not isinstance(self.reducer_sequence, int):
            raise ContractViolation("candidateOrder.reducerSequence must be an integer")
        if isinstance(self.source_ordinal, bool) or not isinstance(self.source_ordinal, int):
            raise ContractViolation("candidateOrder.sourceOrdinal must be an integer")
        if self.reducer_sequence < 0 or self.source_ordinal < 0:
            raise ContractViolation("candidateOrder fields must be nonnegative")

    def key(self) -> tuple[int, int]:
        return (self.reducer_sequence, self.source_ordinal)

    def to_dict(self) -> dict[str, int]:
        return {
            "reducerSequence": self.reducer_sequence,
            "sourceOrdinal": self.source_ordinal,
        }

    @classmethod
    def from_dict(cls, value: object) -> CandidateOrder:
        if not isinstance(value, dict):
            raise ContractViolation("candidateOrder must be an object")
        return cls(
            reducer_sequence=int(value["reducerSequence"]),
            source_ordinal=int(value["sourceOrdinal"]),
        )


@dataclass(frozen=True, slots=True)
class FunnelLink:
    source_class: str
    candidate_id: str | None
    detector_observation_id: str | None
    event_id: str | None
    material_revision: int | None
    opportunity_id: str | None
    plan_id: str | None
    utterance_id: str | None
    tape_channel: str

    def __post_init__(self) -> None:
        if self.source_class not in SOURCE_CLASSES:
            raise ContractViolation("unknown funnel sourceClass")
        _id(self.tape_channel, "tapeChannel")

    def to_dict(self) -> dict[str, Any]:
        return {
            "sourceClass": self.source_class,
            "candidateId": self.candidate_id,
            "detectorObservationId": self.detector_observation_id,
            "eventId": self.event_id,
            "materialRevision": self.material_revision,
            "opportunityId": self.opportunity_id,
            "planId": self.plan_id,
            "utteranceId": self.utterance_id,
            "tapeChannel": self.tape_channel,
        }

    @classmethod
    def from_dict(cls, value: object) -> FunnelLink:
        if not isinstance(value, dict):
            raise ContractViolation("funnel must be an object")
        return cls(
            source_class=str(value["sourceClass"]),
            candidate_id=value.get("candidateId"),
            detector_observation_id=value.get("detectorObservationId"),
            event_id=value.get("eventId"),
            material_revision=value.get("materialRevision"),
            opportunity_id=value.get("opportunityId"),
            plan_id=value.get("planId"),
            utterance_id=value.get("utteranceId"),
            tape_channel=str(value["tapeChannel"]),
        )


@dataclass(frozen=True, slots=True)
class BoundClaim:
    claim_id: str
    predicate: str
    subject_id: str | None
    object_id: str | None
    polarity: str
    temporal_frame: str
    attributes: tuple[str, ...]
    fact_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _id(self.claim_id, "claimId")
        _id(self.predicate, "predicate")
        if self.polarity not in POLARITIES:
            raise ContractViolation("claim polarity must be positive|negative")
        if self.temporal_frame not in FRAMES:
            raise ContractViolation("claim temporalFrame is invalid")
        object.__setattr__(
            self, "attributes", _ids(self.attributes, "attributes", minimum=0, maximum=32)
        )
        if self.fact_ids:
            object.__setattr__(
                self, "fact_ids", _ids(self.fact_ids, "factIds", minimum=1, maximum=16)
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "claimId": self.claim_id,
            "predicate": self.predicate,
            "subjectId": self.subject_id,
            "objectId": self.object_id,
            "polarity": self.polarity,
            "temporalFrame": self.temporal_frame,
            "attributes": list(self.attributes),
            "factIds": list(self.fact_ids),
        }

    @classmethod
    def from_dict(cls, value: object) -> BoundClaim:
        if not isinstance(value, dict):
            raise ContractViolation("claim must be an object")
        return cls(
            claim_id=str(value["claimId"]),
            predicate=str(value["predicate"]),
            subject_id=value.get("subjectId"),
            object_id=value.get("objectId"),
            polarity=str(value["polarity"]),
            temporal_frame=str(value["temporalFrame"]),
            attributes=tuple(value.get("attributes") or ()),
            fact_ids=tuple(value.get("factIds") or ()),
        )


@dataclass(frozen=True, slots=True)
class PromptOptions:
    schema_version: str
    freedom: str
    pattern_choice: str
    optional_claim_limit: int
    allow_clause_reorder: bool
    max_sentences: int
    temperature: float
    top_p: float
    seed: int

    @classmethod
    def tight(cls, seed: int) -> PromptOptions:
        return cls(
            schema_version=PROMPT_SCHEMA,
            freedom="tight",
            pattern_choice="fixed",
            optional_claim_limit=0,
            allow_clause_reorder=False,
            max_sentences=1,
            temperature=0.15,
            top_p=0.75,
            seed=int(seed),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "freedom": self.freedom,
            "patternChoice": self.pattern_choice,
            "optionalClaimLimit": self.optional_claim_limit,
            "allowClauseReorder": self.allow_clause_reorder,
            "maxSentences": self.max_sentences,
            "temperature": self.temperature,
            "topP": self.top_p,
            "seed": self.seed,
        }

    @classmethod
    def from_dict(cls, value: object) -> PromptOptions:
        if not isinstance(value, dict):
            raise ContractViolation("promptOptions must be an object")
        return cls(
            schema_version=str(value["schemaVersion"]),
            freedom=str(value["freedom"]),
            pattern_choice=str(value["patternChoice"]),
            optional_claim_limit=int(value["optionalClaimLimit"]),
            allow_clause_reorder=bool(value["allowClauseReorder"]),
            max_sentences=int(value["maxSentences"]),
            temperature=float(value["temperature"]),
            top_p=float(value["topP"]),
            seed=int(value["seed"]),
        )


def tight_prompt_options(
    *,
    stream_epoch: int,
    opportunity_id: str | None,
    episode_id: str,
    episode_revision: int,
    beat_id: str,
    cycle_attempt_ordinal: int,
) -> PromptOptions:
    seed = deterministic_planning_seed(
        PlanningSeedMaterial(
            stream_epoch=stream_epoch,
            opportunity_id=opportunity_id,
            episode_id=episode_id,
            episode_revision=episode_revision,
            beat_id=beat_id,
            cycle_attempt_ordinal=cycle_attempt_ordinal,
        )
    )
    return PromptOptions.tight(seed)


@dataclass(frozen=True, slots=True)
class BeatPlan:
    schema_version: str
    plan_id: str
    planning_cycle_id: str
    cycle_attempt_ordinal: int
    beat_id: str
    episode_id: str
    opportunity_id: str | None
    candidate_source: str
    funnel: FunnelLink
    candidate_order: CandidateOrder
    beat_role: str
    stream_epoch: int
    occurrence_id: str | None
    lineage_id: str | None
    episode_revision: int
    required_claims: tuple[BoundClaim, ...]
    optional_claims: tuple[BoundClaim, ...]
    forbidden_claim_types: tuple[str, ...]
    selected_fact_ids: tuple[str, ...]
    realization_family: str
    realization_pattern: str
    realization_backend: str
    prompt_options: PromptOptions
    language: str
    style_card_id: str | None
    max_chars: int
    max_seconds: float
    planned_mono_ms: int
    expires_mono_ms: int
    source_refs: tuple[str, ...]
    catalog_hash: str
    effective_config_hash: str
    config_apply_sequence: int
    fact_view_revision: int

    def __post_init__(self) -> None:
        SchemaVersion(self.schema_version)
        if self.schema_version != SCHEMA_VERSION:
            raise ContractViolation("BeatPlan schemaVersion must be beat-plan/2")
        CycleAttemptOrdinal(self.cycle_attempt_ordinal)
        if self.language != "en":
            raise ContractViolation("BeatPlan language must be en")
        if self.expires_mono_ms <= self.planned_mono_ms:
            raise ContractViolation("expiresMonoMs must be greater than plannedMonoMs")
        if not 1 <= self.max_chars <= 512:
            raise ContractViolation("maxChars must be 1..512")

    def is_valid_at(self, now_ms: int) -> bool:
        return self.planned_mono_ms <= int(now_ms) < self.expires_mono_ms

    def identity(self) -> tuple[str, str, int]:
        return (self.beat_id, self.episode_id, self.episode_revision)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "planId": self.plan_id,
            "planningCycleId": self.planning_cycle_id,
            "cycleAttemptOrdinal": self.cycle_attempt_ordinal,
            "beatId": self.beat_id,
            "episodeId": self.episode_id,
            "opportunityId": self.opportunity_id,
            "candidateSource": self.candidate_source,
            "funnel": self.funnel.to_dict(),
            "candidateOrder": self.candidate_order.to_dict(),
            "beatRole": self.beat_role,
            "streamEpoch": self.stream_epoch,
            "occurrenceId": self.occurrence_id,
            "lineageId": self.lineage_id,
            "episodeRevision": self.episode_revision,
            "requiredClaims": [claim.to_dict() for claim in self.required_claims],
            "optionalClaims": [claim.to_dict() for claim in self.optional_claims],
            "forbiddenClaimTypes": list(self.forbidden_claim_types),
            "selectedFactIds": list(self.selected_fact_ids),
            "realizationFamily": self.realization_family,
            "realizationPattern": self.realization_pattern,
            "realizationBackend": self.realization_backend,
            "promptOptions": self.prompt_options.to_dict(),
            "language": self.language,
            "styleCardId": self.style_card_id,
            "maxChars": self.max_chars,
            "maxSeconds": self.max_seconds,
            "plannedMonoMs": self.planned_mono_ms,
            "expiresMonoMs": self.expires_mono_ms,
            "sourceRefs": list(self.source_refs),
            "catalogHash": self.catalog_hash,
            "effectiveConfigHash": self.effective_config_hash,
            "configApplySequence": self.config_apply_sequence,
            "factViewRevision": self.fact_view_revision,
        }

    @classmethod
    def from_dict(cls, value: object) -> BeatPlan:
        if not isinstance(value, dict):
            raise ContractViolation("BeatPlan must be an object")
        return cls(
            schema_version=str(value["schemaVersion"]),
            plan_id=str(value["planId"]),
            planning_cycle_id=str(value["planningCycleId"]),
            cycle_attempt_ordinal=int(value["cycleAttemptOrdinal"]),
            beat_id=str(value["beatId"]),
            episode_id=str(value["episodeId"]),
            opportunity_id=value.get("opportunityId"),
            candidate_source=str(value["candidateSource"]),
            funnel=FunnelLink.from_dict(value["funnel"]),
            candidate_order=CandidateOrder.from_dict(value["candidateOrder"]),
            beat_role=str(value["beatRole"]),
            stream_epoch=int(value["streamEpoch"]),
            occurrence_id=value.get("occurrenceId"),
            lineage_id=value.get("lineageId"),
            episode_revision=int(value["episodeRevision"]),
            required_claims=tuple(BoundClaim.from_dict(item) for item in value["requiredClaims"]),
            optional_claims=tuple(BoundClaim.from_dict(item) for item in value["optionalClaims"]),
            forbidden_claim_types=tuple(value["forbiddenClaimTypes"]),
            selected_fact_ids=tuple(value["selectedFactIds"]),
            realization_family=str(value["realizationFamily"]),
            realization_pattern=str(value["realizationPattern"]),
            realization_backend=str(value["realizationBackend"]),
            prompt_options=PromptOptions.from_dict(value["promptOptions"]),
            language=str(value["language"]),
            style_card_id=value.get("styleCardId"),
            max_chars=int(value["maxChars"]),
            max_seconds=float(value["maxSeconds"]),
            planned_mono_ms=int(value["plannedMonoMs"]),
            expires_mono_ms=int(value["expiresMonoMs"]),
            source_refs=tuple(value["sourceRefs"]),
            catalog_hash=str(value["catalogHash"]),
            effective_config_hash=str(value["effectiveConfigHash"]),
            config_apply_sequence=int(value["configApplySequence"]),
            fact_view_revision=int(value["factViewRevision"]),
        )


@dataclass(frozen=True, slots=True)
class PlanIntent:
    beat_id: str
    episode_id: str
    episode_revision: int
    stream_epoch: int
    occurrence_id: str | None
    lineage_id: str | None
    candidate_source: str
    funnel: FunnelLink
    opportunity_id: str | None
    required_claims: tuple[BoundClaim, ...]
    optional_claims: tuple[BoundClaim, ...]
    source_refs: tuple[str, ...]
    catalog_hash: str
    effective_config_hash: str
    config_apply_sequence: int
    fact_view_revision: int
    planned_mono_ms: int
    expires_mono_ms: int
    story_id: str | None
    speech_complete: bool
    is_closing: bool
    is_critical: bool
    consecutive_accepted: int
    future_beat_ids: tuple[str, ...]
    max_chars: int
    max_seconds: float
    style_card_id: str | None
    realization_pattern: str
    candidate_order: CandidateOrder
    selected_fact_ids: tuple[str, ...] | None = None


@dataclass(frozen=True, slots=True)
class PlanStep:
    reason: str
    plan: BeatPlan | None = None
    opportunity_consumed: bool = False


@dataclass
class BeatPlanner:
    """Create at most two idle-lane BeatPlans per planning impulse."""

    _catalog: Any = field(init=False, repr=False)
    _ordinals: dict[str, int] = field(default_factory=dict)
    _by_identity: dict[tuple[str, str, int], BeatPlan] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self._catalog = load_narrative_catalog().require_catalog()

    def plan(self, intent: PlanIntent, *, lane: str, planning_cycle_id: str) -> PlanStep:
        if lane in BUSY_LANES:
            return PlanStep(reason="lane_busy")
        if intent.future_beat_ids:
            return PlanStep(reason="future_successor_forbidden")
        claims = intent.required_claims + intent.optional_claims
        if not claims or any(not claim.fact_ids for claim in claims):
            return PlanStep(reason="source_guard_failed")
        claim_facts = tuple(
            dict.fromkeys(fact_id for claim in claims for fact_id in claim.fact_ids)
        )
        if intent.selected_fact_ids is not None and tuple(intent.selected_fact_ids) != claim_facts:
            return PlanStep(reason="ledger_dump_forbidden")
        if not self._occurrence_ok(intent):
            return PlanStep(reason="source_guard_failed")
        if self._consecutive_blocked(intent):
            return PlanStep(reason="consecutive_cap")
        if self._self_contained_blocked(intent):
            return PlanStep(reason="not_self_contained")

        identity = (intent.beat_id, intent.episode_id, intent.episode_revision)
        existing = self._by_identity.get(identity)
        if existing is not None:
            merged = _merge_refs(existing.source_refs, intent.source_refs)
            updated = replace(existing, source_refs=merged)
            self._by_identity[identity] = updated
            return PlanStep(reason="deduped", plan=updated)

        used = self._ordinals.get(planning_cycle_id, 0)
        if used >= 2:
            return PlanStep(reason="planning_cycle_exhausted")
        ordinal = used + 1
        plan = self._build(intent, planning_cycle_id, ordinal, claim_facts)
        self._ordinals[planning_cycle_id] = ordinal
        self._by_identity[identity] = plan
        return PlanStep(reason="planned", plan=plan)

    def _occurrence_ok(self, intent: PlanIntent) -> bool:
        allow_stream = intent.beat_id in STREAM_NULL_BEATS
        if intent.occurrence_id is None and intent.lineage_id is None:
            return allow_stream
        if intent.occurrence_id is None or intent.lineage_id is None:
            return False
        try:
            validate_occurrence_lineage(
                OccurrenceId.parse(intent.occurrence_id),
                LineageId.parse(intent.lineage_id),
                allow_stream_scope=allow_stream,
            )
        except ContractViolation:
            return False
        return True

    def _consecutive_blocked(self, intent: PlanIntent) -> bool:
        if intent.is_closing or intent.is_critical:
            return False
        cap = GLOBAL_CONSECUTIVE_CAP
        if intent.story_id:
            cap = min(cap, self._catalog.story(intent.story_id).max_consecutive_non_closing_beats)
        return intent.consecutive_accepted >= cap

    def _self_contained_blocked(self, intent: PlanIntent) -> bool:
        if not intent.speech_complete:
            return False
        if intent.is_closing or intent.is_critical:
            return False
        beat = self._catalog.beat(intent.beat_id)
        return beat.policy.id not in SELF_CONTAINED_POLICIES

    def _build(
        self,
        intent: PlanIntent,
        planning_cycle_id: str,
        ordinal: int,
        claim_facts: tuple[str, ...],
    ) -> BeatPlan:
        beat = self._catalog.beat(intent.beat_id)
        if intent.candidate_source not in CANDIDATE_SOURCES:
            raise ContractViolation("unknown candidateSource")
        plan_id = _id(f"bp:{planning_cycle_id}:{ordinal}", "planId")
        options = tight_prompt_options(
            stream_epoch=intent.stream_epoch,
            opportunity_id=intent.opportunity_id,
            episode_id=intent.episode_id,
            episode_revision=intent.episode_revision,
            beat_id=intent.beat_id,
            cycle_attempt_ordinal=ordinal,
        )
        funnel = replace(intent.funnel, plan_id=plan_id, opportunity_id=intent.opportunity_id)
        return BeatPlan(
            schema_version=SCHEMA_VERSION,
            plan_id=plan_id,
            planning_cycle_id=_id(planning_cycle_id, "planningCycleId"),
            cycle_attempt_ordinal=ordinal,
            beat_id=_id(intent.beat_id, "beatId"),
            episode_id=_id(intent.episode_id, "episodeId"),
            opportunity_id=_optional_id(intent.opportunity_id, "opportunityId"),
            candidate_source=intent.candidate_source,
            funnel=funnel,
            candidate_order=intent.candidate_order,
            beat_role=ROLE_MAP[beat.role],
            stream_epoch=intent.stream_epoch,
            occurrence_id=intent.occurrence_id,
            lineage_id=intent.lineage_id,
            episode_revision=intent.episode_revision,
            required_claims=intent.required_claims,
            optional_claims=intent.optional_claims,
            forbidden_claim_types=G0_FORBIDDEN,
            selected_fact_ids=_ids(claim_facts, "selectedFactIds", minimum=1, maximum=32),
            realization_family=beat.realization.family,
            realization_pattern=_id(intent.realization_pattern, "realizationPattern"),
            realization_backend=beat.realization.backend,
            prompt_options=options,
            language="en",
            style_card_id=intent.style_card_id,
            max_chars=intent.max_chars,
            max_seconds=intent.max_seconds,
            planned_mono_ms=_mono(intent.planned_mono_ms, "plannedMonoMs"),
            expires_mono_ms=_mono(intent.expires_mono_ms, "expiresMonoMs"),
            source_refs=_ids(intent.source_refs, "sourceRefs", minimum=1, maximum=32),
            catalog_hash=_hash(intent.catalog_hash, "catalogHash"),
            effective_config_hash=_hash(intent.effective_config_hash, "effectiveConfigHash"),
            config_apply_sequence=intent.config_apply_sequence,
            fact_view_revision=intent.fact_view_revision,
        )


def _merge_refs(existing: tuple[str, ...], incoming: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = list(existing)
    for item in incoming:
        if item not in merged:
            merged.append(item)
    return tuple(merged)
