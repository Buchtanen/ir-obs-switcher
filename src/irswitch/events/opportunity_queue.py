"""Expiring EventOpportunity queue and post-beat arbitration policy (v2 #283).

Not live-wired and not exported from ``events/__init__.py``. Reads immutable
ExposureStore channel pressure only. Does not import commentary, overlay, or a
director package. An opportunity never stores text, a prompt, or a BeatPlan.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field, replace
from typing import Any

from irswitch.contracts.catalog_loader import (
    NarrativeCatalog,
    PolicyProfile,
    load_narrative_catalog,
)
from irswitch.contracts.coverage_matrix import can_create_event_opportunity
from irswitch.contracts.primitives import (
    ContractViolation,
    Identifier,
    LineageId,
    MonotonicMs,
    OccurrenceId,
    Sha256Hash,
    StreamEpoch,
    validate_occurrence_lineage,
)
from irswitch.events.beat_plan import CandidateOrder, FunnelLink
from irswitch.events.exposure_store import ChannelPressureView

SCHEMA_VERSION = "event-opportunity/2"
OPPORTUNITY_CAPACITY = 128
BY_TAPE_CHANNEL_STATUS_CAP = 128
BY_TAPE_CHANNEL_COUNTER_KEYS = (
    "kick",
    "accepted",
    "queued",
    "selected",
    "started",
    "expired",
)


def project_by_tape_channel_status(
    counters_by_channel: Mapping[str, Mapping[str, object]],
    *,
    capacity: int = BY_TAPE_CHANNEL_STATUS_CAP,
) -> dict[str, dict[str, int]]:
    """Status ``byTapeChannel``: nonzero rows only, sorted by id, capped."""

    if capacity <= 0:
        return {}
    projected: dict[str, dict[str, int]] = {}
    for channel in sorted(counters_by_channel):
        if not isinstance(channel, str):
            continue
        counters = counters_by_channel[channel]
        if not isinstance(counters, Mapping):
            continue
        row: dict[str, int] = {}
        valid = True
        for key in BY_TAPE_CHANNEL_COUNTER_KEYS:
            value = counters.get(key, 0)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                valid = False
                break
            row[key] = int(value)
        if not valid or not any(row.values()):
            continue
        projected[channel] = row
        if len(projected) >= capacity:
            break
    return projected


def cohort_funnel_rates(counters: Mapping[str, object]) -> dict[str, float | None]:
    """Cohort-valid funnel rates for one channel; ``None`` means stage N/A."""

    def _nonneg(key: str) -> int:
        value = counters.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            return 0
        return int(value)

    kick = _nonneg("kick")
    accepted = _nonneg("accepted")
    queued = _nonneg("queued")
    selected = _nonneg("selected")
    started = _nonneg("started")
    expired = _nonneg("expired")

    kick_to_accepted: float | None = (accepted / kick) if kick > 0 else None
    # Speakable accepted cohort only — visual-only ends after accepted.
    speakable_signal = queued + selected + started + expired
    accepted_to_queued: float | None = (
        (queued / accepted) if accepted > 0 and speakable_signal > 0 else None
    )
    selected_to_started: float | None = (started / selected) if selected > 0 else None
    return {
        "kickToAccepted": kick_to_accepted,
        "acceptedToQueued": accepted_to_queued,
        "selectedToStarted": selected_to_started,
    }


SWITCH_MARGIN = 8.0
SELECTION_THRESHOLD = 35.0
GLOBAL_MIN_INTERVAL_MS = 4_000
SUCCESSOR_BASE = 58.0
SAME_STORY_BONUS = 6.0
MATERIAL_REVISION_BONUS = 6.0
POLICY_ORDER = (
    "critical",
    "result",
    "live_story",
    "transient",
    "context",
    "filler",
)
POLICY_PROFILES = tuple((item,) for item in POLICY_ORDER)
URGENCY_RANK = {"background": 0, "context": 1, "story": 2, "critical": 3}
RELATIONS = frozenset({"opens", "updates", "resolves", "conflicts", "independent"})
RELATION_IDS = {
    "opens": "opens_episode",
    "updates": "updates_active_episode",
    "resolves": "resolves_active_episode",
    "conflicts": "conflicts_with_focused_episode",
    "independent": "independent_of_focused_episode",
}
EVENT_SOURCES = frozenset({"detector", "direct", "lifecycle"})
STREAM_NULL_KINDS = frozenset({"stream.started", "filler.lobby"})
STATES = frozenset(
    {"pending", "reserved", "consumed", "expired", "superseded", "invalidated", "evicted"}
)
TERMINAL = frozenset({"consumed", "expired", "superseded", "invalidated", "evicted"})
CADENCE_SCOPES = {
    "critical": "semantic_revision",
    "result": "semantic",
    "live_story": "episode",
    "transient": "semantic",
    "context": "tape_channel",
    "filler": "silence_impulse",
}


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


def _finite(value: object, field: str, *, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ContractViolation(f"{field} must be a finite number")
    number = float(value)
    if not math.isfinite(number) or not low <= number <= high:
        raise ContractViolation(f"{field} must be finite {low}..{high}")
    return number


def _hash(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ContractViolation(f"{field} must be a hash")
    return str(Sha256Hash(value))


@dataclass(frozen=True, slots=True)
class EventOpportunity:
    schema_version: str
    opportunity_id: str
    event_id: str | None
    event_kind: str
    source_order: dict[str, Any] | None
    funnel: FunnelLink
    candidate_order: CandidateOrder
    stream_epoch: int
    occurrence_id: str | None
    lineage_id: str | None
    episode_id: str
    correlation_key: tuple[str, ...]
    tape_channel: str
    created_mono_ms: int
    expires_mono_ms: int
    base_priority: float
    urgency: str
    penalty_coefficient: float
    material_revision: int
    state: str
    reservation_token: str | None
    terminal_reason: str | None
    policy_hash: str
    source_fact_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.schema_version != SCHEMA_VERSION:
            raise ContractViolation("EventOpportunity schemaVersion must be event-opportunity/2")
        _id(self.opportunity_id, "opportunityId")
        _id(self.event_kind, "eventKind")
        _id(self.episode_id, "episodeId")
        _id(self.tape_channel, "tapeChannel")
        if not isinstance(self.funnel, FunnelLink):
            raise ContractViolation("funnel must be FunnelLink")
        if not isinstance(self.candidate_order, CandidateOrder):
            raise ContractViolation("candidateOrder must be CandidateOrder")
        if self.urgency not in URGENCY_RANK:
            raise ContractViolation("urgency must be background|context|story|critical")
        if self.state not in STATES:
            raise ContractViolation("unknown opportunity state")
        if self.source_order is not None and not isinstance(self.source_order, dict):
            raise ContractViolation("sourceOrder must be an object or null")
        created = _mono(self.created_mono_ms, "createdMonoMs")
        expires = _mono(self.expires_mono_ms, "expiresMonoMs")
        if expires <= created:
            raise ContractViolation("expiresMonoMs must be strictly after createdMonoMs")
        epoch = int(StreamEpoch(self.stream_epoch).require_active())
        object.__setattr__(self, "stream_epoch", epoch)
        object.__setattr__(
            self, "base_priority", _finite(self.base_priority, "basePriority", low=0, high=100)
        )
        object.__setattr__(
            self,
            "penalty_coefficient",
            _finite(self.penalty_coefficient, "penaltyCoefficient", low=0, high=4),
        )
        if isinstance(self.material_revision, bool) or not isinstance(self.material_revision, int):
            raise ContractViolation("materialRevision must be an integer")
        if self.material_revision < 0:
            raise ContractViolation("materialRevision must be nonnegative")
        object.__setattr__(
            self,
            "correlation_key",
            _ids(self.correlation_key, "correlationKey", minimum=0, maximum=8),
        )
        object.__setattr__(
            self,
            "source_fact_ids",
            _ids(self.source_fact_ids, "sourceFactIds", minimum=1, maximum=32),
        )
        object.__setattr__(self, "policy_hash", _hash(self.policy_hash, "policyHash"))
        event_id = _optional_id(self.event_id, "eventId")
        if self.funnel.source_class == "silence":
            if event_id is not None or self.funnel.event_id is not None:
                raise ContractViolation("silence opportunity requires null eventId")
        elif self.funnel.source_class not in EVENT_SOURCES:
            raise ContractViolation("event opportunity sourceClass is invalid")
        elif event_id is None:
            raise ContractViolation("event-derived opportunities require eventId")
        object.__setattr__(self, "event_id", event_id)
        if self.funnel.opportunity_id != self.opportunity_id:
            raise ContractViolation("funnel opportunityId must match")
        if self.funnel.tape_channel != self.tape_channel:
            raise ContractViolation("funnel tapeChannel must match")
        occurrence = None if self.occurrence_id is None else OccurrenceId.parse(self.occurrence_id)
        lineage = None if self.lineage_id is None else LineageId.parse(self.lineage_id)
        allow_stream = self.event_kind in STREAM_NULL_KINDS
        validate_occurrence_lineage(occurrence, lineage, allow_stream_scope=allow_stream)
        if occurrence is not None and int(occurrence.stream_epoch) != epoch:
            raise ContractViolation("occurrenceId streamEpoch must match")
        if self.state == "reserved":
            if self.reservation_token is None or self.terminal_reason is not None:
                raise ContractViolation("reserved requires a token and null terminalReason")
            _id(self.reservation_token, "reservationToken")
        elif self.state in TERMINAL:
            if self.reservation_token is not None or self.terminal_reason is None:
                raise ContractViolation("terminal state requires a reason and null token")
            _id(self.terminal_reason, "terminalReason")
        elif self.reservation_token is not None or self.terminal_reason is not None:
            raise ContractViolation("pending requires null token and terminalReason")

    def is_valid_at(self, now_ms: int) -> bool:
        now = _mono(now_ms, "nowMs")
        return self.created_mono_ms <= now < self.expires_mono_ms

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": self.schema_version,
            "opportunityId": self.opportunity_id,
            "eventId": self.event_id,
            "eventKind": self.event_kind,
            "sourceOrder": None if self.source_order is None else dict(self.source_order),
            "funnel": self.funnel.to_dict(),
            "candidateOrder": self.candidate_order.to_dict(),
            "streamEpoch": self.stream_epoch,
            "occurrenceId": self.occurrence_id,
            "lineageId": self.lineage_id,
            "episodeId": self.episode_id,
            "correlationKey": list(self.correlation_key),
            "tapeChannel": self.tape_channel,
            "createdMonoMs": self.created_mono_ms,
            "expiresMonoMs": self.expires_mono_ms,
            "basePriority": self.base_priority,
            "urgency": self.urgency,
            "penaltyCoefficient": self.penalty_coefficient,
            "materialRevision": self.material_revision,
            "state": self.state,
            "reservationToken": self.reservation_token,
            "terminalReason": self.terminal_reason,
            "policyHash": self.policy_hash,
            "sourceFactIds": list(self.source_fact_ids),
        }

    @classmethod
    def from_dict(cls, value: object) -> EventOpportunity:
        if not isinstance(value, dict):
            raise ContractViolation("EventOpportunity must be an object")
        return cls(
            schema_version=str(value["schemaVersion"]),
            opportunity_id=str(value["opportunityId"]),
            event_id=value.get("eventId"),
            event_kind=str(value["eventKind"]),
            source_order=value.get("sourceOrder"),
            funnel=FunnelLink.from_dict(value["funnel"]),
            candidate_order=CandidateOrder.from_dict(value["candidateOrder"]),
            stream_epoch=int(value["streamEpoch"]),
            occurrence_id=value.get("occurrenceId"),
            lineage_id=value.get("lineageId"),
            episode_id=str(value["episodeId"]),
            correlation_key=tuple(value.get("correlationKey") or ()),
            tape_channel=str(value["tapeChannel"]),
            created_mono_ms=int(value["createdMonoMs"]),
            expires_mono_ms=int(value["expiresMonoMs"]),
            base_priority=float(value["basePriority"]),
            urgency=str(value["urgency"]),
            penalty_coefficient=float(value["penaltyCoefficient"]),
            material_revision=int(value["materialRevision"]),
            state=str(value["state"]),
            reservation_token=value.get("reservationToken"),
            terminal_reason=value.get("terminalReason"),
            policy_hash=str(value["policyHash"]),
            source_fact_ids=tuple(value.get("sourceFactIds") or ()),
        )


@dataclass(frozen=True, slots=True)
class OpportunityIntent:
    opportunity_id: str
    event_id: str | None
    event_kind: str
    current_identifier: str | None
    source_class: str
    candidate_id: str | None
    detector_observation_id: str | None
    stream_epoch: int
    occurrence_id: str | None
    lineage_id: str | None
    episode_id: str
    correlation_key: tuple[str, ...]
    tape_channel: str | None
    policy_id: str
    created_mono_ms: int
    material_revision: int
    source_fact_ids: tuple[str, ...]
    candidate_order: CandidateOrder
    source_order: dict[str, Any] | None
    relation: str
    beat_id: str
    beat_ids: tuple[str, ...]
    story_id: str
    semantic_identity: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EpisodeBeatRef:
    beat_id: str
    episode_id: str
    story_id: str
    material_revision: int
    candidate_order: CandidateOrder
    tape_channel: str
    policy_id: str


@dataclass(frozen=True, slots=True)
class ArbitrationContext:
    now_ms: int
    stream_epoch: int
    focused_episode_id: str | None
    focused_story_id: str | None
    last_spoken_beat_id: str | None
    last_spoken_episode_id: str | None
    focused_material_order: CandidateOrder
    last_global_spoken_ms: int | None
    last_channel_spoken_ms: dict[str, int]
    last_semantic_spoken_ms: dict[tuple[str, ...], int]
    last_episode_spoken_ms: dict[str, int]
    spoken_semantic_revisions: dict[tuple[str, ...], int]
    valid_successor_targets: tuple[str, ...]
    episode_beats: tuple[EpisodeBeatRef, ...]
    channel_pressure: ChannelPressureView | None
    silence_impulse: bool


@dataclass(frozen=True, slots=True)
class SelectedCandidate:
    source: str
    beat_id: str
    episode_id: str
    opportunity_id: str | None
    relation: str
    score: float
    urgency: str
    tape_channel: str
    channel_pressure: float
    candidate_order: CandidateOrder
    material_revision: int
    policy_id: str


@dataclass(frozen=True, slots=True)
class OpportunityStep:
    reason: str
    opportunity: EventOpportunity | None = None
    superseded_id: str | None = None
    evicted_id: str | None = None


@dataclass(frozen=True, slots=True)
class ArbitrationDecision:
    reason: str
    selected: SelectedCandidate | None = None
    started_impulse: bool = False
    opportunity_consumed: bool = False


@dataclass(frozen=True, slots=True)
class ChannelCounters:
    tape_channel: str
    kick: int = 0
    queued: int = 0
    selected: int = 0
    consumed: int = 0
    expired: int = 0
    superseded: int = 0
    spoken: int = 0
    evicted: int = 0


@dataclass
class _Live:
    opportunity: EventOpportunity
    beat_ids: tuple[str, ...]
    story_id: str
    policy_id: str
    relation: str
    semantic_identity: tuple[str, ...]
    suppressed: set[str] = field(default_factory=set)


@dataclass
class OpportunityQueue:
    """Bounded expiring metadata queue plus one-pass event/successor policy."""

    capacity: int = OPPORTUNITY_CAPACITY
    _live: list[_Live] = field(default_factory=list, init=False, repr=False)
    _counters: dict[str, ChannelCounters] = field(default_factory=dict, init=False, repr=False)
    _policies: dict[str, PolicyProfile] = field(default_factory=dict, init=False, repr=False)
    _catalog_hash: str = field(default="", init=False, repr=False)
    _last_channel: dict[str, str] = field(default_factory=dict, init=False, repr=False)
    _catalog: NarrativeCatalog | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        if isinstance(self.capacity, bool) or not isinstance(self.capacity, int):
            raise ContractViolation("capacity must be a positive integer")
        if self.capacity <= 0:
            raise ContractViolation("capacity must be a positive integer")
        catalog = load_narrative_catalog().require_catalog()
        self._policies = {item.id: item for item in catalog.policies}
        self._catalog = catalog
        self._catalog_hash = catalog.catalog_hash

    def _loaded(self) -> NarrativeCatalog:
        if self._catalog is None:
            raise ContractViolation("catalog is not loaded")
        return self._catalog

    def admit(self, intent: OpportunityIntent) -> OpportunityStep:
        if intent.relation not in RELATIONS:
            raise ContractViolation("unknown event-to-episode relation")
        policy = self._policy(intent.policy_id)
        beat_ids = intent.beat_ids or (intent.beat_id,)
        channel = intent.tape_channel or self._loaded().beat(intent.beat_id).tape_channel
        self._bump(channel, "kick")
        if intent.current_identifier is not None:
            try:
                speakable = can_create_event_opportunity(intent.current_identifier)
            except ContractViolation:
                speakable = False
            if not speakable:
                return OpportunityStep(reason="not_speakable")
        opportunity = EventOpportunity(
            schema_version=SCHEMA_VERSION,
            opportunity_id=intent.opportunity_id,
            event_id=intent.event_id,
            event_kind=intent.event_kind,
            source_order=None if intent.source_order is None else dict(intent.source_order),
            funnel=FunnelLink(
                source_class=intent.source_class,
                candidate_id=intent.candidate_id,
                detector_observation_id=intent.detector_observation_id,
                event_id=intent.event_id,
                material_revision=intent.material_revision,
                opportunity_id=intent.opportunity_id,
                plan_id=None,
                utterance_id=None,
                tape_channel=channel,
            ),
            candidate_order=intent.candidate_order,
            stream_epoch=intent.stream_epoch,
            occurrence_id=intent.occurrence_id,
            lineage_id=intent.lineage_id,
            episode_id=intent.episode_id,
            correlation_key=intent.correlation_key,
            tape_channel=channel,
            created_mono_ms=intent.created_mono_ms,
            expires_mono_ms=intent.created_mono_ms + policy.ttl_ms,
            base_priority=float(policy.base_priority),
            urgency=policy.urgency,
            penalty_coefficient=policy.penalty_coefficient,
            material_revision=intent.material_revision,
            state="pending",
            reservation_token=None,
            terminal_reason=None,
            policy_hash=self._catalog_hash,
            source_fact_ids=intent.source_fact_ids,
        )
        superseded_id = None
        if intent.relation in {"updates", "resolves"}:
            for row in list(self._live):
                same_story = (
                    row.opportunity.episode_id == opportunity.episode_id
                    and row.opportunity.correlation_key == opportunity.correlation_key
                )
                if (
                    same_story
                    and row.opportunity.material_revision <= opportunity.material_revision
                ):
                    superseded_id = row.opportunity.opportunity_id
                    self._terminal(row, "superseded", "superseded_revision")
        evicted_id = self._evict_for_admit()
        if evicted_id is None and len(self._live) >= self.capacity:
            return OpportunityStep(reason="queue_overflow", superseded_id=superseded_id)
        self._live.append(
            _Live(
                opportunity=opportunity,
                beat_ids=tuple(beat_ids),
                story_id=intent.story_id,
                policy_id=intent.policy_id,
                relation=intent.relation,
                semantic_identity=tuple(intent.semantic_identity),
            )
        )
        self._bump(channel, "queued")
        return OpportunityStep(
            reason="queued",
            opportunity=opportunity,
            superseded_id=superseded_id,
            evicted_id=evicted_id,
        )

    def expire_due(self, now_ms: int) -> tuple[OpportunityStep, ...]:
        now = _mono(now_ms, "nowMs")
        steps: list[OpportunityStep] = []
        for row in list(self._live):
            if row.opportunity.state not in {"pending", "reserved"}:
                continue
            if now < row.opportunity.expires_mono_ms:
                continue
            self._terminal(row, "expired", "expired_ttl")
            steps.append(OpportunityStep(reason="expired", opportunity=row.opportunity))
        return tuple(steps)

    def nearest_validity_deadline(self, now_ms: int) -> int | None:
        _mono(now_ms, "nowMs")
        pending = [
            row.opportunity.expires_mono_ms
            for row in self._live
            if row.opportunity.state in {"pending", "reserved"}
        ]
        return min(pending) if pending else None

    def reserve(self, opportunity_id: str, *, now_ms: int) -> OpportunityStep:
        row = self._require_live(opportunity_id)
        if not row.opportunity.is_valid_at(now_ms) or row.opportunity.state != "pending":
            return OpportunityStep(reason="not_reservable", opportunity=row.opportunity)
        token = f"res:{row.opportunity.opportunity_id}"
        row.opportunity = replace(row.opportunity, state="reserved", reservation_token=token)
        return OpportunityStep(reason="reserved", opportunity=row.opportunity)

    def reject_attempt(self, token: str, *, beat_id: str, now_ms: int) -> OpportunityStep:
        _mono(now_ms, "nowMs")
        row = self._by_token(token)
        if row is None:
            return OpportunityStep(reason="not_reserved")
        row.suppressed.add(beat_id)
        row.opportunity = replace(row.opportunity, state="pending", reservation_token=None)
        return OpportunityStep(reason="attempt_released", opportunity=row.opportunity)

    def consume_speech_started(self, token: str, *, now_ms: int) -> OpportunityStep:
        _mono(now_ms, "nowMs")
        row = self._by_token(token)
        if row is None:
            return OpportunityStep(reason="not_reserved")
        self._terminal(row, "consumed", "consumed_playback_accepted")
        return OpportunityStep(reason="consumed", opportunity=row.opportunity)

    def note_spoken(self, opportunity_id: str, *, now_ms: int) -> OpportunityStep:
        _mono(now_ms, "nowMs")
        for row in self._live:
            if row.opportunity.opportunity_id == opportunity_id:
                return OpportunityStep(reason="not_consumed", opportunity=row.opportunity)
        # Terminal rows are removed from `_live`; spoken is a cadence/tape counter.
        self._bump_id(opportunity_id, "spoken")
        return OpportunityStep(reason="spoken")

    def live_ids(self) -> tuple[str, ...]:
        return tuple(row.opportunity.opportunity_id for row in self._live)

    def channel_counters(self, tape_channel: str) -> ChannelCounters:
        return self._counters.get(tape_channel, ChannelCounters(tape_channel=tape_channel))

    def tape_channel_status_counts(self) -> dict[str, dict[str, int]]:
        """Map live channel counters into StatusResponse byTapeChannel shape."""

        raw: dict[str, dict[str, int]] = {}
        for channel, counters in self._counters.items():
            raw[channel] = {
                "kick": int(counters.kick),
                # spoken → accepted (status funnel cohort proxy)
                # consumed → started (PLAYBACK_ACCEPTED / speech-started terminal)
                "accepted": int(counters.spoken),
                "queued": int(counters.queued),
                "selected": int(counters.selected),
                "started": int(counters.consumed),
                "expired": int(counters.expired),
            }
        return project_by_tape_channel_status(raw)

    def arbitrate(self, context: ArbitrationContext) -> ArbitrationDecision:
        self.expire_due(context.now_ms)
        scored = self._collect(context)
        continuation = self._best(
            item
            for item in scored
            if item.source in {"story_successor", "episode_beat"}
            and item.episode_id == context.focused_episode_id
        )
        events = [
            item
            for item in scored
            if item.source == "event_opportunity" or item.source == "episode_beat"
        ]
        if continuation is not None:
            events = [item for item in events if item is not continuation]
        challenger = self._best(events)
        filler = self._best(item for item in scored if item.source == "filler")
        winner, reason = self._choose(continuation, challenger, filler, context)
        if winner is None:
            return ArbitrationDecision(reason=reason, selected=None, started_impulse=False)
        self._bump(winner.tape_channel, "selected")
        return ArbitrationDecision(reason=reason, selected=winner, opportunity_consumed=False)

    def _collect(self, context: ArbitrationContext) -> list[SelectedCandidate]:
        items: list[SelectedCandidate] = []
        for row in self._live:
            if row.opportunity.state != "pending" or not row.opportunity.is_valid_at(
                context.now_ms
            ):
                continue
            if row.opportunity.stream_epoch != context.stream_epoch:
                continue
            beat_id = next((item for item in row.beat_ids if item not in row.suppressed), None)
            if beat_id is None:
                continue
            if row.policy_id == "filler" and not context.silence_impulse:
                continue
            if not self._cadence_ok(row, context):
                continue
            pressure = _pressure(context.channel_pressure, row.opportunity.tape_channel)
            score = row.opportunity.base_priority - (row.opportunity.penalty_coefficient * pressure)
            source = "filler" if row.policy_id == "filler" else "event_opportunity"
            if source != "filler" and score < SELECTION_THRESHOLD:
                continue
            items.append(
                SelectedCandidate(
                    source=source,
                    beat_id=beat_id,
                    episode_id=row.opportunity.episode_id,
                    opportunity_id=row.opportunity.opportunity_id,
                    relation=RELATION_IDS[row.relation],
                    score=score,
                    urgency=row.opportunity.urgency,
                    tape_channel=row.opportunity.tape_channel,
                    channel_pressure=pressure,
                    candidate_order=row.opportunity.candidate_order,
                    material_revision=row.opportunity.material_revision,
                    policy_id=row.policy_id,
                )
            )
        if context.last_spoken_beat_id and context.last_spoken_episode_id:
            items.extend(self._successors(context))
        for ref in context.episode_beats:
            policy = self._policy(ref.policy_id)
            if not self._policy_cadence(policy, context, ref.tape_channel, (), ref.episode_id, 0):
                continue
            pressure = _pressure(context.channel_pressure, ref.tape_channel)
            same = context.focused_story_id == ref.story_id
            score = (
                SUCCESSOR_BASE
                + (SAME_STORY_BONUS if same else 0.0)
                + MATERIAL_REVISION_BONUS
                - (policy.penalty_coefficient * pressure)
            )
            if score < SELECTION_THRESHOLD:
                continue
            items.append(
                SelectedCandidate(
                    source="episode_beat",
                    beat_id=ref.beat_id,
                    episode_id=ref.episode_id,
                    opportunity_id=None,
                    relation=(
                        "continues_focused_episode"
                        if ref.episode_id == context.focused_episode_id
                        else "independent_of_focused_episode"
                    ),
                    score=score,
                    urgency=policy.urgency,
                    tape_channel=ref.tape_channel,
                    channel_pressure=pressure,
                    candidate_order=ref.candidate_order,
                    material_revision=ref.material_revision,
                    policy_id=ref.policy_id,
                )
            )
        return _dedup(items)

    def _successors(self, context: ArbitrationContext) -> list[SelectedCandidate]:
        items: list[SelectedCandidate] = []
        episode_id = context.last_spoken_episode_id
        if episode_id is None or context.last_spoken_beat_id is None:
            return items
        allowed = set(context.valid_successor_targets)
        for edge in self._loaded().edges:
            if edge.from_beat_id != context.last_spoken_beat_id:
                continue
            if edge.to_beat_id not in allowed:
                continue
            beat = self._loaded().beat(edge.to_beat_id)
            policy = beat.policy
            if not self._policy_cadence(policy, context, beat.tape_channel, (), episode_id, 0):
                continue
            pressure = _pressure(context.channel_pressure, beat.tape_channel)
            same = context.focused_story_id in beat.story_routes
            score = (
                SUCCESSOR_BASE
                + (SAME_STORY_BONUS if same else 0.0)
                + float(edge.score_bonus)
                + MATERIAL_REVISION_BONUS
                - (policy.penalty_coefficient * pressure)
            )
            if score < SELECTION_THRESHOLD:
                continue
            items.append(
                SelectedCandidate(
                    source="story_successor",
                    beat_id=edge.to_beat_id,
                    episode_id=episode_id,
                    opportunity_id=None,
                    relation="continues_focused_episode",
                    score=score,
                    urgency=policy.urgency,
                    tape_channel=beat.tape_channel,
                    channel_pressure=pressure,
                    candidate_order=context.focused_material_order,
                    material_revision=1,
                    policy_id=policy.id,
                )
            )
        return items

    def _choose(
        self,
        continuation: SelectedCandidate | None,
        challenger: SelectedCandidate | None,
        filler: SelectedCandidate | None,
        context: ArbitrationContext,
    ) -> tuple[SelectedCandidate | None, str]:
        if continuation is None and challenger is None:
            if context.silence_impulse and filler is not None:
                return filler, "highest_valid_candidate"
            return None, "no_candidate"
        if continuation is None:
            assert challenger is not None
            if (
                challenger.relation
                in {
                    "updates_active_episode",
                    "resolves_active_episode",
                }
                and challenger.episode_id == context.focused_episode_id
            ):
                return challenger, "related_event_update"
            return challenger, "highest_valid_candidate"
        if challenger is None:
            return continuation, "active_story_continuation"
        if URGENCY_RANK[challenger.urgency] > URGENCY_RANK[continuation.urgency]:
            return challenger, "higher_urgency_switch"
        if challenger.score - continuation.score >= SWITCH_MARGIN:
            return challenger, "switch_margin_met"
        return continuation, "active_story_continuation"

    def _cadence_ok(self, row: _Live, context: ArbitrationContext) -> bool:
        return self._policy_cadence(
            self._policy(row.policy_id),
            context,
            row.opportunity.tape_channel,
            row.semantic_identity,
            row.opportunity.episode_id,
            row.opportunity.material_revision,
        )

    def _policy_cadence(
        self,
        policy: PolicyProfile,
        context: ArbitrationContext,
        tape_channel: str,
        semantic: tuple[str, ...],
        episode_id: str,
        material_revision: int,
    ) -> bool:
        now = context.now_ms
        if context.last_global_spoken_ms is not None:
            if now - context.last_global_spoken_ms < GLOBAL_MIN_INTERVAL_MS:
                return False
        scope = CADENCE_SCOPES[policy.id]
        if scope == "silence_impulse":
            return context.silence_impulse
        if scope == "semantic_revision":
            spoken = context.spoken_semantic_revisions.get(semantic)
            return spoken != material_revision
        minimum = policy.cadence_minimum_ms or policy.ttl_ms
        if scope == "semantic":
            last = context.last_semantic_spoken_ms.get(semantic)
        elif scope == "episode":
            last = context.last_episode_spoken_ms.get(episode_id)
        else:
            last = context.last_channel_spoken_ms.get(tape_channel)
        return last is None or now - last >= minimum

    def _policy(self, policy_id: str) -> PolicyProfile:
        try:
            return self._policies[policy_id]
        except KeyError as exc:
            raise ContractViolation(f"unknown policy {policy_id}") from exc

    def _evict_for_admit(self) -> str | None:
        if len(self._live) < self.capacity:
            return None
        pending = [row for row in self._live if row.opportunity.state == "pending"]
        if not pending:
            return None
        pending.sort(
            key=lambda row: (
                *row.opportunity.candidate_order.key(),
                row.opportunity.opportunity_id,
            )
        )
        victim = pending[0]
        evicted_id = victim.opportunity.opportunity_id
        self._terminal(victim, "evicted", "evicted_capacity")
        return evicted_id

    def _terminal(self, row: _Live, state: str, reason: str) -> None:
        row.opportunity = replace(
            row.opportunity, state=state, reservation_token=None, terminal_reason=reason
        )
        if row in self._live:
            self._live.remove(row)
        field = {
            "consumed": "consumed",
            "expired": "expired",
            "superseded": "superseded",
            "evicted": "evicted",
            "invalidated": "expired",
        }[state]
        self._bump(row.opportunity.tape_channel, field)
        self._last_channel[row.opportunity.opportunity_id] = row.opportunity.tape_channel

    def _bump(self, tape_channel: str, field_name: str) -> None:
        current = self._counters.get(tape_channel, ChannelCounters(tape_channel=tape_channel))
        self._counters[tape_channel] = replace(
            current, **{field_name: getattr(current, field_name) + 1}
        )

    def _bump_id(self, opportunity_id: str, field_name: str) -> None:
        channel = self._last_channel.get(opportunity_id)
        if channel is None:
            return
        self._bump(channel, field_name)

    def _require_live(self, opportunity_id: str) -> _Live:
        for row in self._live:
            if row.opportunity.opportunity_id == opportunity_id:
                return row
        raise ContractViolation(f"unknown live opportunity {opportunity_id}")

    def _by_token(self, token: str) -> _Live | None:
        for row in self._live:
            if row.opportunity.reservation_token == token:
                return row
        return None

    def _best(self, items: Iterable[SelectedCandidate]) -> SelectedCandidate | None:
        ranked = list(items)
        if not ranked:
            return None
        ranked.sort(
            key=lambda item: (
                -item.score,
                item.candidate_order.key(),
                item.opportunity_id or item.beat_id,
            )
        )
        return ranked[0]


def _pressure(view: ChannelPressureView | None, tape_channel: str) -> float:
    if view is None:
        return 0.0
    for name, value in view.by_channel:
        if name == tape_channel:
            return float(value)
    return 0.0


def _dedup(items: list[SelectedCandidate]) -> list[SelectedCandidate]:
    best: dict[tuple[str, str, int], SelectedCandidate] = {}
    for item in items:
        key = (item.beat_id, item.episode_id, item.material_revision)
        current = best.get(key)
        if current is None or item.score > current.score:
            best[key] = item
    return list(best.values())
