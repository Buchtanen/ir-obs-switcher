"""Resolved-episode retention. World outcomes only; no prepared-speech queue.

Does not import the narrative actor, overlay tape or commentary. Not live-wired.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from irswitch.contracts.catalog_loader import CatalogLoadResult, load_narrative_catalog
from irswitch.contracts.primitives import ContractViolation, Identifier, MonotonicMs
from irswitch.events.episode_registry import RESOLVED_CAP, Episode

SCHEMA_VERSION = "episode-retention/2"
SELF_CONTAINED = frozenset({"critical", "result"})
OUTCOME_FAMILIES = frozenset({"critical", "result", "live_story", "transient", "context", "filler"})
RETAIN_REASONS = frozenset({"retained", "expired_ttl", "superseded_revision", "skipped"})
OutcomeFamily = Literal["critical", "result", "live_story", "transient", "context", "filler"]


def _id(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ContractViolation(f"{field} must be an ID")
    return str(Identifier(value))


def _mono(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractViolation(f"{field} must be monotonic milliseconds")
    return int(MonotonicMs(value))


@dataclass(frozen=True, slots=True)
class RetentionIntent:
    episode: Episode
    beat_id: str
    now_ms: int
    source_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RetentionRecord:
    schema_version: str
    episode_id: str
    definition_id: str
    beat_id: str
    outcome_family: str
    resolution_salience: int
    speakable_until_ms: int
    resolved_mono_ms: int
    material_revision: int
    semantic_identity: tuple[str, ...]
    occurrence_id: str | None
    fact_ids: tuple[str, ...]
    self_contained: bool

    def identity_key(self) -> tuple[object, ...]:
        return (self.occurrence_id, self.definition_id, self.semantic_identity)


@dataclass(frozen=True, slots=True)
class RetentionDecision:
    record: RetentionRecord
    reason: str
    source_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.reason not in RETAIN_REASONS:
            raise ContractViolation("unknown retention reason")
        if not self.source_refs:
            raise ContractViolation("retention decision requires source refs")


@dataclass(frozen=True, slots=True)
class RetentionStep:
    retained: RetentionRecord | None = None
    selected: tuple[RetentionRecord, ...] = ()
    decisions: tuple[RetentionDecision, ...] = ()


@dataclass
class EpisodeRetention:
    """Bounded resolved-outcome store. Does not queue prepared speech."""

    resolved_capacity: int = RESOLVED_CAP
    _live: dict[str, RetentionRecord] = field(default_factory=dict)
    _catalog: CatalogLoadResult | None = None

    def live(self) -> tuple[RetentionRecord, ...]:
        return tuple(sorted(self._live.values(), key=lambda item: item.episode_id))

    def retain(self, intent: RetentionIntent) -> RetentionStep:
        record = self._record(intent)
        decisions: list[RetentionDecision] = []
        for existing in list(self._live.values()):
            if existing.identity_key() != record.identity_key():
                continue
            if existing.episode_id == record.episode_id:
                continue
            newer = (
                record.resolved_mono_ms,
                record.material_revision,
                record.episode_id,
            ) > (
                existing.resolved_mono_ms,
                existing.material_revision,
                existing.episode_id,
            )
            if not newer:
                continue
            if existing.outcome_family not in SELF_CONTAINED:
                self._live.pop(existing.episode_id, None)
                decisions.append(
                    RetentionDecision(
                        record=existing,
                        reason="superseded_revision",
                        source_refs=intent.source_refs,
                    )
                )
        self._live[record.episode_id] = record
        self._trim()
        decisions.append(
            RetentionDecision(record=record, reason="retained", source_refs=intent.source_refs)
        )
        return RetentionStep(retained=record, decisions=tuple(decisions))

    def on_speech_complete(self, *, now_ms: int, source_refs: tuple[str, ...]) -> RetentionStep:
        if not source_refs:
            raise ContractViolation("retention decision requires source refs")
        now = _mono(now_ms, "nowMs")
        decisions: list[RetentionDecision] = []
        selected: list[RetentionRecord] = []
        for record in list(self._live.values()):
            if now >= record.speakable_until_ms:
                self._live.pop(record.episode_id, None)
                decisions.append(
                    RetentionDecision(record=record, reason="expired_ttl", source_refs=source_refs)
                )
                continue
            if not record.self_contained:
                self._live.pop(record.episode_id, None)
                decisions.append(
                    RetentionDecision(record=record, reason="skipped", source_refs=source_refs)
                )
                continue
            selected.append(record)
        selected.sort(
            key=lambda item: (
                -item.resolution_salience,
                item.speakable_until_ms,
                item.episode_id,
            )
        )
        return RetentionStep(selected=tuple(selected), decisions=tuple(decisions))

    def _record(self, intent: RetentionIntent) -> RetentionRecord:
        episode = intent.episode
        if episode.state != "resolved":
            raise ContractViolation("retention requires a resolved episode")
        if episode.resolved_mono_ms is None:
            raise ContractViolation("retention requires a resolved episode")
        if not intent.source_refs:
            raise ContractViolation("retention decision requires source refs")
        _mono(intent.now_ms, "nowMs")
        catalog = self._catalog if self._catalog is not None else load_narrative_catalog()
        self._catalog = catalog
        loaded = catalog.require_catalog()
        beat = loaded.beat(_id(intent.beat_id, "beatId"))
        family = beat.policy.id
        if family not in OUTCOME_FAMILIES:
            raise ContractViolation(f"unknown outcome family {family}")
        resolved_ms = _mono(episode.resolved_mono_ms, "resolvedMonoMs")
        return RetentionRecord(
            schema_version=SCHEMA_VERSION,
            episode_id=episode.episode_id,
            definition_id=episode.definition_id,
            beat_id=beat.id,
            outcome_family=family,
            resolution_salience=beat.policy.base_priority,
            speakable_until_ms=resolved_ms + beat.policy.ttl_ms,
            resolved_mono_ms=resolved_ms,
            material_revision=episode.material_revision,
            semantic_identity=episode.semantic_identity,
            occurrence_id=episode.occurrence_id,
            fact_ids=episode.fact_ids,
            self_contained=family in SELF_CONTAINED,
        )

    def _trim(self) -> None:
        while len(self._live) > self.resolved_capacity:
            oldest = min(
                self._live.values(),
                key=lambda item: (item.resolved_mono_ms, item.episode_id),
            )
            self._live.pop(oldest.episode_id, None)
