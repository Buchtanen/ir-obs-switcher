"""Lineage-aware EpisodeRegistry. World lifecycle, not speech lifecycle.

Does not import the narrative actor, overlay tape or commentary. Not live-wired.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Literal

from irswitch.contracts.catalog_loader import load_narrative_catalog
from irswitch.contracts.primitives import (
    ContractViolation,
    Identifier,
    LineageId,
    MonotonicMs,
    OccurrenceId,
    SchemaVersion,
    validate_occurrence_lineage,
)

ACTIVE_CAP = 64
RESOLVED_CAP = 256
SCHEMA_VERSION = "episode/2"
EpisodeState = Literal["candidate", "active", "suspended", "resolved", "invalidated"]
EpisodeScope = Literal["stream", "occurrence"]
PinKind = Literal["reserved", "building", "committed", "speaking"]

CURRENT_STATES = frozenset({"candidate", "active", "suspended"})
TERMINAL_STATES = frozenset({"resolved", "invalidated"})
TERMINAL_REASONS = frozenset(
    {
        "outcome_observed",
        "natural_exit",
        "target_changed",
        "composite_exited",
        "occurrence_ended",
        "occurrence_superseded",
        "stream_ended",
        "commentary_disabled",
        "evidence_invalidated",
        "capacity_evicted",
    }
)
PIN_KINDS = frozenset({"reserved", "building", "committed", "speaking"})
EXCLUSIVE_GROUPS = {
    "battle_ahead": "battle",
    "battle_behind": "battle",
    "battle_two_front": "battle",
}
STREAM_ONLY = frozenset({"stream_lifecycle"})


def _story_ids() -> frozenset[str]:
    return frozenset(item.id for item in load_narrative_catalog().require_catalog().stories)


def _id(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ContractViolation(f"{field} must be an ID")
    return str(Identifier(value))


def _optional_id(value: object, field: str) -> str | None:
    if value is None:
        return None
    return _id(value, field)


def _ids(
    values: tuple[str, ...], field: str, *, minimum: int = 0, maximum: int = 8
) -> tuple[str, ...]:
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


@dataclass(frozen=True, slots=True)
class MaterialOrder:
    reducer_sequence: int
    source_ordinal: int

    def __post_init__(self) -> None:
        if not isinstance(self.reducer_sequence, int) or isinstance(self.reducer_sequence, bool):
            raise ContractViolation("materialOrder.reducerSequence must be an integer")
        if not isinstance(self.source_ordinal, int) or isinstance(self.source_ordinal, bool):
            raise ContractViolation("materialOrder.sourceOrdinal must be an integer")
        if self.reducer_sequence < 0 or self.source_ordinal < 0:
            raise ContractViolation("materialOrder fields must be nonnegative")

    def key(self) -> tuple[int, int]:
        return (self.reducer_sequence, self.source_ordinal)


@dataclass(frozen=True, slots=True)
class Episode:
    schema_version: str
    episode_id: str
    definition_id: str
    scope: EpisodeScope
    occurrence_id: str | None
    lineage_id: str | None
    semantic_identity: tuple[str, ...]
    correlation_ids: tuple[str, ...]
    state: EpisodeState
    opened_mono_ms: int
    updated_mono_ms: int
    resolved_mono_ms: int | None
    resolution_reason: str | None
    fact_ids: tuple[str, ...]
    material_revision: int
    spoken_beat_ids: tuple[str, ...]
    material_order: MaterialOrder
    next_eligible_mono_ms: int
    last_spoken_beat_id: str | None
    continuation_priority: int
    history_complete: bool

    def __post_init__(self) -> None:
        SchemaVersion(self.schema_version)
        if self.schema_version != SCHEMA_VERSION:
            raise ContractViolation("episode schemaVersion must be episode/2")
        if self.state in TERMINAL_STATES:
            if self.resolved_mono_ms is None or self.resolution_reason is None:
                raise ContractViolation("terminal episode requires resolved time and reason")
            if self.resolution_reason not in TERMINAL_REASONS:
                raise ContractViolation("unknown episode terminal reason")
        elif self.resolved_mono_ms is not None or self.resolution_reason is not None:
            raise ContractViolation("live episode cannot carry a resolution")
        if self.opened_mono_ms > self.updated_mono_ms:
            raise ContractViolation("openedMonoMs must be <= updatedMonoMs")
        if self.resolved_mono_ms is not None and self.updated_mono_ms > self.resolved_mono_ms:
            raise ContractViolation("updatedMonoMs must be <= resolvedMonoMs")


@dataclass(frozen=True, slots=True)
class EpisodeIntent:
    definition_id: str
    scope: EpisodeScope
    occurrence_id: str | None
    lineage_id: str | None
    semantic_identity: tuple[str, ...]
    correlation_ids: tuple[str, ...]
    fact_ids: tuple[str, ...]
    material_order: MaterialOrder
    now_ms: int
    continuation_priority: int
    source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EpisodeTransition:
    episode: Episode
    previous_state: str | None
    reason: str
    source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EpisodeStep:
    episode: Episode | None
    transitions: tuple[EpisodeTransition, ...] = ()
    decision: str | None = None
    affected: tuple[Episode, ...] = ()


def _semantic_key(intent: EpisodeIntent) -> tuple[object, ...]:
    return (intent.definition_id, intent.occurrence_id, tuple(sorted(intent.semantic_identity)))


def _episode_id(intent: EpisodeIntent, ordinal: int) -> str:
    definition = intent.definition_id.replace("_", "-")
    scope = "stream" if intent.scope == "stream" else str(intent.occurrence_id).replace(":", ".")
    correlation = (
        ".".join(item.replace(":", ".") for item in sorted(intent.correlation_ids)) or "none"
    )
    return _id(f"{definition}:{scope}:{correlation}:{ordinal}", "episodeId")


@dataclass
class EpisodeRegistry:
    """Bounded live/resolved episode store. Eviction never mutates FactLedger."""

    active_capacity: int = ACTIVE_CAP
    resolved_capacity: int = RESOLVED_CAP
    history_complete: bool = True
    _current: dict[str, Episode] = field(default_factory=dict)
    _resolved: dict[str, Episode] = field(default_factory=dict)
    _keys: dict[tuple[object, ...], str] = field(default_factory=dict)
    _ordinals: dict[tuple[object, ...], int] = field(default_factory=dict)
    _pins: dict[str, set[str]] = field(default_factory=dict)
    _stories: frozenset[str] | None = None

    def current(self) -> tuple[Episode, ...]:
        return tuple(sorted(self._current.values(), key=lambda item: item.episode_id))

    def get(self, episode_id: str) -> Episode | None:
        return self._current.get(episode_id) or self._resolved.get(episode_id)

    def pin(self, episode_id: str, kind: PinKind) -> None:
        if kind not in PIN_KINDS:
            raise ContractViolation("unknown episode pin kind")
        if episode_id not in self._current:
            raise ContractViolation("cannot pin a missing current episode")
        self._pins.setdefault(episode_id, set()).add(kind)

    def unpin(self, episode_id: str, kind: PinKind) -> None:
        pins = self._pins.get(episode_id)
        if pins is None:
            return
        pins.discard(kind)
        if not pins:
            self._pins.pop(episode_id, None)

    def open(self, intent: EpisodeIntent) -> EpisodeStep:
        self._validate_intent(intent)
        transitions: list[EpisodeTransition] = []
        key = _semantic_key(intent)
        existing_id = self._keys.get(key)
        if existing_id is not None and existing_id in self._current:
            return self._revise(existing_id, intent)

        transitions.extend(self._suspend_conflicts(intent))
        rejected = self._ensure_current_capacity(intent, transitions)
        if rejected is not None:
            return rejected

        self._ordinals[key] = self._ordinals.get(key, 0) + 1
        episode = Episode(
            schema_version=SCHEMA_VERSION,
            episode_id=_episode_id(intent, self._ordinals[key]),
            definition_id=intent.definition_id,
            scope=intent.scope,
            occurrence_id=intent.occurrence_id,
            lineage_id=intent.lineage_id,
            semantic_identity=_ids(intent.semantic_identity, "semanticIdentity", minimum=1),
            correlation_ids=_ids(intent.correlation_ids, "correlationIds"),
            state="candidate",
            opened_mono_ms=_mono(intent.now_ms, "openedMonoMs"),
            updated_mono_ms=_mono(intent.now_ms, "updatedMonoMs"),
            resolved_mono_ms=None,
            resolution_reason=None,
            fact_ids=_ids(intent.fact_ids, "factIds", maximum=64),
            material_revision=1,
            spoken_beat_ids=(),
            material_order=intent.material_order,
            next_eligible_mono_ms=_mono(intent.now_ms, "nextEligibleMonoMs"),
            last_spoken_beat_id=None,
            continuation_priority=intent.continuation_priority,
            history_complete=True,
        )
        self._current[episode.episode_id] = episode
        self._keys[key] = episode.episode_id
        transitions.append(
            EpisodeTransition(
                episode=episode,
                previous_state=None,
                reason="opened",
                source_refs=intent.source_refs,
            )
        )
        return EpisodeStep(episode=episode, transitions=tuple(transitions))

    def activate(
        self, episode_id: str, *, now_ms: int, source_refs: tuple[str, ...]
    ) -> EpisodeStep:
        return self._move(episode_id, "active", now_ms, "activated", source_refs)

    def suspend(
        self,
        episode_id: str,
        *,
        now_ms: int,
        reason: str,
        source_refs: tuple[str, ...],
    ) -> EpisodeStep:
        return self._move(episode_id, "suspended", now_ms, reason, source_refs)

    def resolve(self, episode_id: str, *, now_ms: int, reason: str) -> EpisodeStep:
        return self._terminal(episode_id, "resolved", now_ms, reason)

    def invalidate(self, episode_id: str, *, now_ms: int, reason: str) -> EpisodeStep:
        return self._terminal(episode_id, "invalidated", now_ms, reason)

    def mark_spoken(
        self,
        episode_id: str,
        beat_id: str,
        *,
        now_ms: int,
        source_refs: tuple[str, ...],
    ) -> EpisodeStep:
        episode = self._require_current(episode_id)
        spoken = tuple(dict.fromkeys((*episode.spoken_beat_ids, _id(beat_id, "beatId"))))
        updated = replace(
            episode,
            spoken_beat_ids=spoken,
            last_spoken_beat_id=_id(beat_id, "beatId"),
            updated_mono_ms=_mono(now_ms, "updatedMonoMs"),
        )
        self._current[episode_id] = updated
        transition = EpisodeTransition(
            episode=updated,
            previous_state=episode.state,
            reason="spoken_beat",
            source_refs=source_refs,
        )
        return EpisodeStep(episode=updated, transitions=(transition,))

    def reset_occurrences(
        self, occurrence_ids: set[str], *, now_ms: int, reason: str
    ) -> EpisodeStep:
        if reason not in TERMINAL_REASONS:
            raise ContractViolation("unknown episode terminal reason")
        transitions: list[EpisodeTransition] = []
        affected: list[Episode] = []
        for episode in list(self._current.values()):
            if episode.occurrence_id in occurrence_ids:
                step = self._terminal(episode.episode_id, "invalidated", now_ms, reason)
                transitions.extend(step.transitions)
                affected.extend(step.affected)
        return EpisodeStep(episode=None, transitions=tuple(transitions), affected=tuple(affected))

    def _validate_intent(self, intent: EpisodeIntent) -> None:
        stories = self._stories if self._stories is not None else _story_ids()
        self._stories = stories
        if intent.definition_id not in stories:
            raise ContractViolation(f"unknown story {intent.definition_id}")
        stream_scope = intent.scope == "stream"
        if stream_scope and intent.definition_id not in STREAM_ONLY | {"filler_single"}:
            raise ContractViolation("story is not stream-scoped")
        if not stream_scope and intent.definition_id in STREAM_ONLY:
            raise ContractViolation("stream_lifecycle requires stream scope")
        occurrence = (
            None if intent.occurrence_id is None else OccurrenceId.parse(intent.occurrence_id)
        )
        lineage = None if intent.lineage_id is None else LineageId.parse(intent.lineage_id)
        validate_occurrence_lineage(occurrence, lineage, allow_stream_scope=stream_scope)
        _ids(intent.semantic_identity, "semanticIdentity", minimum=1)
        _ids(intent.correlation_ids, "correlationIds")
        _ids(intent.fact_ids, "factIds", maximum=64)
        _mono(intent.now_ms, "nowMs")
        if not intent.source_refs:
            raise ContractViolation("episode transition requires source refs")
        if not isinstance(intent.continuation_priority, int) or isinstance(
            intent.continuation_priority, bool
        ):
            raise ContractViolation("continuationPriority must be an integer")

    def _revise(self, episode_id: str, intent: EpisodeIntent) -> EpisodeStep:
        episode = self._require_current(episode_id)
        facts = tuple(dict.fromkeys((*episode.fact_ids, *intent.fact_ids)))[:64]
        updated = replace(
            episode,
            fact_ids=_ids(facts, "factIds", maximum=64),
            material_revision=episode.material_revision + 1,
            material_order=intent.material_order,
            updated_mono_ms=_mono(intent.now_ms, "updatedMonoMs"),
            continuation_priority=intent.continuation_priority,
        )
        self._current[episode_id] = updated
        transition = EpisodeTransition(
            episode=updated,
            previous_state=episode.state,
            reason="material_revision",
            source_refs=intent.source_refs,
        )
        return EpisodeStep(episode=updated, transitions=(transition,))

    def _suspend_conflicts(self, intent: EpisodeIntent) -> list[EpisodeTransition]:
        group = EXCLUSIVE_GROUPS.get(intent.definition_id)
        if group is None:
            return []
        overlap = set(intent.correlation_ids)
        transitions: list[EpisodeTransition] = []
        for episode in list(self._current.values()):
            if EXCLUSIVE_GROUPS.get(episode.definition_id) != group:
                continue
            if episode.episode_id == self._keys.get(_semantic_key(intent)):
                continue
            if not overlap.intersection(episode.correlation_ids):
                continue
            step = self._move(
                episode.episode_id,
                "suspended",
                intent.now_ms,
                "target_changed",
                intent.source_refs,
            )
            transitions.extend(step.transitions)
        return transitions

    def _ensure_current_capacity(
        self, intent: EpisodeIntent, transitions: list[EpisodeTransition]
    ) -> EpisodeStep | None:
        while len(self._current) >= self.active_capacity:
            victim = self._eviction_victim()
            if victim is None:
                return EpisodeStep(episode=None, decision="episode_capacity_rejected")
            step = self._terminal(
                victim.episode_id, "invalidated", intent.now_ms, "capacity_evicted"
            )
            transitions.extend(step.transitions)
        return None

    def _eviction_victim(self) -> Episode | None:
        unpinned = [item for item in self._current.values() if item.episode_id not in self._pins]
        suspended = [item for item in unpinned if item.state == "suspended"]
        if suspended:
            return min(
                suspended,
                key=lambda item: (item.opened_mono_ms, *item.material_order.key(), item.episode_id),
            )
        candidates = [item for item in unpinned if item.state == "candidate"]
        if candidates:
            return min(
                candidates,
                key=lambda item: (item.opened_mono_ms, *item.material_order.key(), item.episode_id),
            )
        active = [item for item in unpinned if item.state == "active"]
        if active:
            return min(
                active,
                key=lambda item: (
                    item.continuation_priority,
                    *item.material_order.key(),
                    item.episode_id,
                ),
            )
        return None

    def _move(
        self,
        episode_id: str,
        state: EpisodeState,
        now_ms: int,
        reason: str,
        source_refs: tuple[str, ...],
    ) -> EpisodeStep:
        episode = self._require_current(episode_id)
        if state in TERMINAL_STATES:
            raise ContractViolation("use terminal helpers for resolved/invalidated")
        if not source_refs:
            raise ContractViolation("episode transition requires source refs")
        updated = replace(episode, state=state, updated_mono_ms=_mono(now_ms, "updatedMonoMs"))
        self._current[episode_id] = updated
        transition = EpisodeTransition(
            episode=updated,
            previous_state=episode.state,
            reason=reason,
            source_refs=source_refs,
        )
        return EpisodeStep(episode=updated, transitions=(transition,))

    def _terminal(
        self, episode_id: str, state: EpisodeState, now_ms: int, reason: str
    ) -> EpisodeStep:
        episode = self._require_current(episode_id)
        if reason not in TERMINAL_REASONS:
            raise ContractViolation("unknown episode terminal reason")
        resolved_ms = _mono(now_ms, "resolvedMonoMs")
        updated = replace(
            episode,
            state=state,
            updated_mono_ms=resolved_ms,
            resolved_mono_ms=resolved_ms,
            resolution_reason=reason,
        )
        self._current.pop(episode_id, None)
        self._pins.pop(episode_id, None)
        key = next((item for item, value in self._keys.items() if value == episode_id), None)
        if key is not None:
            self._keys.pop(key, None)
        if state == "resolved":
            self._resolved[episode_id] = updated
            self._trim_resolved()
        else:
            self._resolved[episode_id] = updated
            self._trim_resolved()
        transition = EpisodeTransition(
            episode=updated,
            previous_state=episode.state,
            reason=reason,
            source_refs=(episode.episode_id,),
        )
        return EpisodeStep(episode=updated, transitions=(transition,), affected=(updated,))

    def _trim_resolved(self) -> None:
        while len(self._resolved) > self.resolved_capacity:
            oldest = min(
                self._resolved.values(),
                key=lambda item: (item.resolved_mono_ms or 0, item.episode_id),
            )
            self._resolved.pop(oldest.episode_id, None)
            self.history_complete = False

    def _require_current(self, episode_id: str) -> Episode:
        episode = self._current.get(episode_id)
        if episode is None:
            raise ContractViolation(f"unknown current episode {episode_id}")
        return episode
