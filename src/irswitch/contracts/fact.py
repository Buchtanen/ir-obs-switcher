"""Immutable AtomicFact and FactView DTOs from the frozen v2 contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from typing import Any, ClassVar, Self

from .primitives import (
    MAX_SIGNED_INT64,
    BroadcastEpoch,
    Confidence,
    ContractViolation,
    Identifier,
    LineageId,
    MonotonicMs,
    OccurrenceId,
    SchemaVersion,
    StreamEpoch,
    validate_occurrence_lineage,
    validate_scalar,
)
from .resources import packaged_schema_bytes


class FactScope(StrEnum):
    OCCURRENCE = "occurrence"
    DOWNSTREAM = "downstream"
    STREAM = "stream"
    REVALIDATE = "revalidate"
    HISTORICAL_ONLY = "historical_only"


class FactStatus(StrEnum):
    PROVISIONAL = "provisional"
    ACTIVE = "active"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"
    HISTORICAL = "historical"
    REJECTED = "rejected"
    UNKNOWN = "unknown"


_ACTIVE_CLAIM_STATUSES = frozenset({FactStatus.PROVISIONAL, FactStatus.ACTIVE})


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractViolation(f"{field} must be a nonnegative integer")
    if not 0 <= value <= MAX_SIGNED_INT64:
        raise ContractViolation(f"{field} must fit a nonnegative signed 64-bit integer")
    return value


def _exact_object(value: object, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ContractViolation(f"{label} must be a JSON object")
    actual = frozenset(value)
    if actual != fields:
        missing = sorted(fields - actual)
        unknown = sorted(actual - fields)
        raise ContractViolation(f"invalid {label} fields; missing={missing}, unknown={unknown}")
    return value


def _optional_id(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ContractViolation(f"{field} must be an ID or null")
    return str(Identifier(value))


@dataclass(frozen=True, slots=True)
class FactPredicateSpec:
    predicate: str
    scope: FactScope
    attributes: tuple[tuple[str, str, bool], ...]
    minimum_attribute_count: int

    def attribute_ids(self) -> frozenset[str]:
        return frozenset(item[0] for item in self.attributes)

    def required_ids(self) -> frozenset[str]:
        return frozenset(item[0] for item in self.attributes if item[2])


@dataclass(frozen=True, slots=True)
class FactRegistry:
    predicates: dict[str, FactPredicateSpec]
    enums: dict[str, frozenset[str]]

    def require(self, predicate: str) -> FactPredicateSpec:
        try:
            return self.predicates[predicate]
        except KeyError as exc:
            raise ContractViolation(f"unregistered fact predicate: {predicate!r}") from exc


@lru_cache(maxsize=1)
def load_fact_registry() -> FactRegistry:
    raw = json.loads(packaged_schema_bytes("freeze-registry.json"))
    predicates = {
        row["id"]: FactPredicateSpec(
            predicate=row["id"],
            scope=FactScope(row["scope"]),
            attributes=tuple(
                (item["id"], item["scalarType"], bool(item["required"]))
                for item in row["attributes"]
            ),
            minimum_attribute_count=int(row["minimumAttributeCount"]),
        )
        for row in raw["factPredicates"]
    }
    enums = {name: frozenset(values) for name, values in raw["enums"].items()}
    return FactRegistry(predicates, enums)


def validate_fact_attribute(scalar_type: str, value: object) -> object:
    """Validate one registry attribute. None is unknown, never coerced to zero/false."""

    if value is None:
        raise ContractViolation(f"{scalar_type} has no active value")
    registry = load_fact_registry()
    if scalar_type in registry.enums:
        if not isinstance(value, str) or value not in registry.enums[scalar_type]:
            raise ContractViolation(f"invalid {scalar_type}: {value!r}")
        return value
    return validate_scalar(scalar_type, value)


def semantic_key(fact: AtomicFact) -> tuple[object, ...]:
    """Identity used for supersession. Stream facts are occurrence-null."""

    return (
        int(fact.stream_epoch),
        fact.predicate,
        fact.subject_id,
        fact.object_id,
        None if fact.scope is FactScope.STREAM else str(fact.occurrence_id),
    )


@dataclass(frozen=True, slots=True)
class AtomicFact:
    fact_id: Identifier
    predicate: str
    subject_id: str | None
    object_id: str | None
    attributes: tuple[tuple[str, object], ...]
    polarity: str
    valid_from_mono_ms: MonotonicMs
    valid_until_mono_ms: MonotonicMs | None
    observed_at_mono_ms: MonotonicMs
    broadcast_epoch: BroadcastEpoch
    stream_epoch: StreamEpoch
    occurrence_id: OccurrenceId | None
    lineage_id: LineageId | None
    evidence_refs: tuple[Identifier, ...]
    confidence: Confidence
    scope: FactScope
    status: FactStatus
    revision: int

    SCHEMA_VERSION: ClassVar[SchemaVersion] = SchemaVersion("atomic-fact/2")
    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "schemaVersion",
            "factId",
            "predicate",
            "subjectId",
            "objectId",
            "attributes",
            "polarity",
            "validFromMonoMs",
            "validUntilMonoMs",
            "observedAtMonoMs",
            "broadcastEpoch",
            "streamEpoch",
            "occurrenceId",
            "lineageId",
            "evidenceRefs",
            "confidence",
            "scope",
            "status",
            "revision",
        }
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "fact_id", Identifier(self.fact_id))
        object.__setattr__(self, "predicate", str(Identifier(self.predicate)))
        object.__setattr__(self, "subject_id", _optional_id(self.subject_id, "subjectId"))
        object.__setattr__(self, "object_id", _optional_id(self.object_id, "objectId"))
        if self.polarity not in {"positive", "negative"}:
            raise ContractViolation("polarity must be positive or negative")
        object.__setattr__(self, "valid_from_mono_ms", MonotonicMs(self.valid_from_mono_ms))
        if self.valid_until_mono_ms is not None:
            object.__setattr__(self, "valid_until_mono_ms", MonotonicMs(self.valid_until_mono_ms))
            if int(self.valid_until_mono_ms) < int(self.valid_from_mono_ms):
                raise ContractViolation("validUntilMonoMs must be >= validFromMonoMs")
        object.__setattr__(self, "observed_at_mono_ms", MonotonicMs(self.observed_at_mono_ms))
        object.__setattr__(
            self, "broadcast_epoch", BroadcastEpoch(self.broadcast_epoch).require_active()
        )
        object.__setattr__(self, "stream_epoch", StreamEpoch(self.stream_epoch).require_active())
        object.__setattr__(self, "scope", FactScope(self.scope))
        object.__setattr__(self, "status", FactStatus(self.status))
        object.__setattr__(self, "revision", _nonnegative_int(self.revision, "revision"))
        object.__setattr__(self, "confidence", Confidence(self.confidence))
        object.__setattr__(self, "occurrence_id", self._coerce_occurrence(self.occurrence_id))
        object.__setattr__(self, "lineage_id", self._coerce_lineage(self.lineage_id))
        self._validate_identity()
        object.__setattr__(self, "evidence_refs", self._validate_evidence(self.evidence_refs))
        object.__setattr__(self, "attributes", self._validate_attributes(self.attributes))

    @staticmethod
    def _coerce_occurrence(value: OccurrenceId | str | None) -> OccurrenceId | None:
        if value is None or isinstance(value, OccurrenceId):
            return value
        return OccurrenceId.parse(value)

    @staticmethod
    def _coerce_lineage(value: LineageId | str | None) -> LineageId | None:
        if value is None or isinstance(value, LineageId):
            return value
        return LineageId.parse(value)

    def _validate_identity(self) -> None:
        allow_stream = self.scope is FactScope.STREAM
        occurrence, lineage = validate_occurrence_lineage(
            self.occurrence_id, self.lineage_id, allow_stream_scope=allow_stream
        )
        object.__setattr__(self, "occurrence_id", occurrence)
        object.__setattr__(self, "lineage_id", lineage)
        spec = load_fact_registry().require(self.predicate)
        if self.scope is not spec.scope:
            raise ContractViolation(f"predicate {self.predicate} requires scope {spec.scope.value}")

    def _validate_evidence(self, value: object) -> tuple[Identifier, ...]:
        if not isinstance(value, (tuple, list)) or not 1 <= len(value) <= 16:
            raise ContractViolation("evidenceRefs must contain 1..16 unique IDs")
        refs = tuple(Identifier(item) for item in value)
        if len(set(refs)) != len(refs):
            raise ContractViolation("evidenceRefs must be unique")
        return refs

    def _validate_attributes(self, value: object) -> tuple[tuple[str, object], ...]:
        if isinstance(value, dict):
            items = tuple(sorted(value.items(), key=lambda item: item[0]))
        elif isinstance(value, (tuple, list)):
            items = tuple(value)
        else:
            raise ContractViolation("attributes must be a JSON object")
        if len(items) > 32:
            raise ContractViolation("attributes exceeds the 32-field bound")
        names = [name for name, _ in items]
        if any(not isinstance(name, str) for name in names) or len(set(names)) != len(names):
            raise ContractViolation("attribute names must be unique strings")
        spec = load_fact_registry().require(self.predicate)
        provided = set(names)
        unknown = provided - spec.attribute_ids()
        if unknown:
            raise ContractViolation(f"unknown attributes for {self.predicate}: {sorted(unknown)}")
        if self.status in _ACTIVE_CLAIM_STATUSES:
            missing = spec.required_ids() - provided
            if missing or len(provided) < spec.minimum_attribute_count:
                raise ContractViolation(f"missing required attributes for {self.predicate}")
            validated: list[tuple[str, object]] = []
            types = {name: scalar for name, scalar, _required in spec.attributes}
            for name, raw in items:
                validated.append((name, validate_fact_attribute(types[name], raw)))
            return tuple(validated)
        return items

    def is_current(self, now_ms: int) -> bool:
        if self.status not in _ACTIVE_CLAIM_STATUSES:
            return False
        if now_ms < int(self.valid_from_mono_ms):
            return False
        if self.valid_until_mono_ms is None:
            return True
        return now_ms < int(self.valid_until_mono_ms)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": str(self.SCHEMA_VERSION),
            "factId": str(self.fact_id),
            "predicate": self.predicate,
            "subjectId": self.subject_id,
            "objectId": self.object_id,
            "attributes": dict(self.attributes),
            "polarity": self.polarity,
            "validFromMonoMs": int(self.valid_from_mono_ms),
            "validUntilMonoMs": (
                None if self.valid_until_mono_ms is None else int(self.valid_until_mono_ms)
            ),
            "observedAtMonoMs": int(self.observed_at_mono_ms),
            "broadcastEpoch": int(self.broadcast_epoch),
            "streamEpoch": int(self.stream_epoch),
            "occurrenceId": None if self.occurrence_id is None else str(self.occurrence_id),
            "lineageId": None if self.lineage_id is None else str(self.lineage_id),
            "evidenceRefs": [str(item) for item in self.evidence_refs],
            "confidence": float(self.confidence),
            "scope": self.scope.value,
            "status": self.status.value,
            "revision": self.revision,
        }

    @classmethod
    def from_dict(cls, value: object) -> Self:
        data = _exact_object(value, cls._FIELDS, "AtomicFact")
        if SchemaVersion(data["schemaVersion"]) != cls.SCHEMA_VERSION:
            raise ContractViolation("AtomicFact requires schemaVersion atomic-fact/2")
        occurrence = data["occurrenceId"]
        lineage = data["lineageId"]
        return cls(
            fact_id=data["factId"],
            predicate=data["predicate"],
            subject_id=data["subjectId"],
            object_id=data["objectId"],
            attributes=data["attributes"],
            polarity=data["polarity"],
            valid_from_mono_ms=data["validFromMonoMs"],
            valid_until_mono_ms=data["validUntilMonoMs"],
            observed_at_mono_ms=data["observedAtMonoMs"],
            broadcast_epoch=data["broadcastEpoch"],
            stream_epoch=data["streamEpoch"],
            occurrence_id=None if occurrence is None else OccurrenceId.parse(occurrence),
            lineage_id=None if lineage is None else LineageId.parse(lineage),
            evidence_refs=tuple(data["evidenceRefs"]),
            confidence=data["confidence"],
            scope=data["scope"],
            status=data["status"],
            revision=data["revision"],
        )


@dataclass(frozen=True, slots=True)
class FactView:
    view_revision: int
    created_mono_ms: MonotonicMs
    broadcast_epoch: int
    stream_epoch: int
    occurrence_id: OccurrenceId | None
    lineage_id: LineageId | None
    history_complete: bool
    facts: tuple[AtomicFact, ...]
    compacted_summary_refs: tuple[Identifier, ...]

    SCHEMA_VERSION: ClassVar[SchemaVersion] = SchemaVersion("fact-view/2")
    MAX_FACTS: ClassVar[int] = 1024
    MAX_SUMMARY_REFS: ClassVar[int] = 64
    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "schemaVersion",
            "viewRevision",
            "createdMonoMs",
            "broadcastEpoch",
            "streamEpoch",
            "occurrenceId",
            "lineageId",
            "historyComplete",
            "facts",
            "compactedSummaryRefs",
        }
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "view_revision", _nonnegative_int(self.view_revision, "viewRevision")
        )
        object.__setattr__(self, "created_mono_ms", MonotonicMs(self.created_mono_ms))
        object.__setattr__(
            self, "broadcast_epoch", _nonnegative_int(self.broadcast_epoch, "broadcastEpoch")
        )
        object.__setattr__(self, "stream_epoch", _nonnegative_int(self.stream_epoch, "streamEpoch"))
        if not isinstance(self.history_complete, bool):
            raise ContractViolation("historyComplete must be a JSON boolean")
        validate_occurrence_lineage(self.occurrence_id, self.lineage_id, allow_stream_scope=True)
        facts = tuple(self.facts)
        refs = tuple(Identifier(item) for item in self.compacted_summary_refs)
        if any(not isinstance(fact, AtomicFact) for fact in facts):
            raise ContractViolation("FactView facts must contain AtomicFact values")
        if len(facts) > self.MAX_FACTS:
            raise ContractViolation("FactView facts exceeds the 1024 bound")
        ids = [str(fact.fact_id) for fact in facts]
        if len(set(ids)) != len(ids):
            raise ContractViolation("FactView fact identities must be unique")
        if facts != tuple(sorted(facts, key=lambda fact: str(fact.fact_id))):
            raise ContractViolation("FactView facts must be sorted by factId")
        if any(int(fact.observed_at_mono_ms) > int(self.created_mono_ms) for fact in facts):
            raise ContractViolation("observedAtMonoMs cannot be later than FactView createdMonoMs")
        if len(refs) > self.MAX_SUMMARY_REFS or len(set(refs)) != len(refs):
            raise ContractViolation("compactedSummaryRefs must be 0..64 unique IDs")
        object.__setattr__(self, "facts", facts)
        object.__setattr__(self, "compacted_summary_refs", refs)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": str(self.SCHEMA_VERSION),
            "viewRevision": self.view_revision,
            "createdMonoMs": int(self.created_mono_ms),
            "broadcastEpoch": self.broadcast_epoch,
            "streamEpoch": self.stream_epoch,
            "occurrenceId": None if self.occurrence_id is None else str(self.occurrence_id),
            "lineageId": None if self.lineage_id is None else str(self.lineage_id),
            "historyComplete": self.history_complete,
            "facts": [fact.to_dict() for fact in self.facts],
            "compactedSummaryRefs": [str(item) for item in self.compacted_summary_refs],
        }

    @classmethod
    def from_dict(cls, value: object) -> Self:
        data = _exact_object(value, cls._FIELDS, "FactView")
        if SchemaVersion(data["schemaVersion"]) != cls.SCHEMA_VERSION:
            raise ContractViolation("FactView requires schemaVersion fact-view/2")
        raw_facts = data["facts"]
        raw_refs = data["compactedSummaryRefs"]
        if not isinstance(raw_facts, list) or not isinstance(raw_refs, list):
            raise ContractViolation("FactView facts and compactedSummaryRefs must be arrays")
        occurrence = data["occurrenceId"]
        lineage = data["lineageId"]
        return cls(
            view_revision=data["viewRevision"],
            created_mono_ms=data["createdMonoMs"],
            broadcast_epoch=data["broadcastEpoch"],
            stream_epoch=data["streamEpoch"],
            occurrence_id=None if occurrence is None else OccurrenceId.parse(occurrence),
            lineage_id=None if lineage is None else LineageId.parse(lineage),
            history_complete=data["historyComplete"],
            facts=tuple(AtomicFact.from_dict(item) for item in raw_facts),
            compacted_summary_refs=tuple(raw_refs),
        )
