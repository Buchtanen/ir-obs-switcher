"""Immutable DTOs at the accepted-event to narrative-runtime boundary."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, ClassVar, Literal, Self

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
    Sha256Hash,
    SourceSequence,
    StreamEpoch,
    canonical_json,
    validate_occurrence_lineage,
)
from .session import SessionRef

NarrativePhase = Literal["started", "updated", "ended", "result", "impulse"]
DeliveryClass = Literal["ordinary", "protected"]
FunnelSourceClass = Literal["detector", "direct", "lifecycle", "silence", "successor"]

_NARRATIVE_PHASES = frozenset({"started", "updated", "ended", "result", "impulse"})
_FUNNEL_SOURCE_CLASSES = frozenset({"detector", "direct", "lifecycle", "silence", "successor"})
_PROTECTED_KINDS = frozenset(
    {"STREAM_STARTED", "STREAM_ENDED", "SESSION_STARTED", "SESSION_ENDED", "SESSION_RESTARTED"}
)


def _exact_object(value: object, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ContractViolation(f"{label} must be a JSON object")
    actual = frozenset(value)
    if actual != fields:
        raise ContractViolation(
            f"invalid {label} fields; missing={sorted(fields - actual)}, "
            f"unknown={sorted(actual - fields)}"
        )
    return value


def _bounded_int(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractViolation(f"{field} must be an integer")
    if not minimum <= value <= MAX_SIGNED_INT64:
        raise ContractViolation(f"{field} must be in {minimum}..{MAX_SIGNED_INT64}")
    return value


def _unique_ids(value: object, field: str, minimum: int, maximum: int) -> tuple[Identifier, ...]:
    if not isinstance(value, (list, tuple)):
        raise ContractViolation(f"{field} must be an array")
    values = tuple(Identifier(item) for item in value)
    if not minimum <= len(values) <= maximum:
        raise ContractViolation(f"{field} must contain {minimum}..{maximum} IDs")
    if len(set(values)) != len(values):
        raise ContractViolation(f"{field} must contain unique IDs")
    return values


@dataclass(frozen=True, slots=True, init=False)
class NarrativeSourceEnvelope:
    session_id: Identifier
    event_id: Identifier
    sequence: SourceSequence
    event_type: Identifier

    _FIELDS: ClassVar[frozenset[str]] = frozenset({"sessionId", "eventId", "sequence", "eventType"})

    def __init__(self, session_id: str, event_id: str, sequence: int, event_type: str) -> None:
        object.__setattr__(self, "session_id", Identifier(session_id))
        object.__setattr__(self, "event_id", Identifier(event_id))
        object.__setattr__(self, "sequence", SourceSequence(sequence))
        object.__setattr__(self, "event_type", Identifier(event_type))

    def to_dict(self) -> dict[str, Any]:
        return {
            "sessionId": str(self.session_id),
            "eventId": str(self.event_id),
            "sequence": int(self.sequence),
            "eventType": str(self.event_type),
        }

    @classmethod
    def from_dict(cls, value: object) -> Self:
        data = _exact_object(value, cls._FIELDS, "NarrativeEvent sourceEnvelope")
        return cls(data["sessionId"], data["eventId"], data["sequence"], data["eventType"])


@dataclass(frozen=True, slots=True, init=False)
class NarrativeSourceOrder:
    fanout_stream_sequence: SourceSequence
    source_ordinal: int

    _FIELDS: ClassVar[frozenset[str]] = frozenset({"fanoutStreamSequence", "sourceOrdinal"})

    def __init__(self, fanout_stream_sequence: int, source_ordinal: int) -> None:
        object.__setattr__(self, "fanout_stream_sequence", SourceSequence(fanout_stream_sequence))
        object.__setattr__(self, "source_ordinal", _bounded_int(source_ordinal, "sourceOrdinal"))

    def to_dict(self) -> dict[str, int]:
        return {
            "fanoutStreamSequence": int(self.fanout_stream_sequence),
            "sourceOrdinal": self.source_ordinal,
        }

    @classmethod
    def from_dict(cls, value: object) -> Self:
        data = _exact_object(value, cls._FIELDS, "NarrativeEvent sourceOrder")
        return cls(data["fanoutStreamSequence"], data["sourceOrdinal"])


@dataclass(frozen=True, slots=True, init=False)
class FunnelIdentity:
    source_class: FunnelSourceClass
    candidate_id: Identifier | None
    detector_observation_id: Identifier | None
    event_id: Identifier | None
    material_revision: int | None
    opportunity_id: Identifier | None
    plan_id: Identifier | None
    utterance_id: Identifier | None
    tape_channel: Identifier

    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "sourceClass",
            "candidateId",
            "detectorObservationId",
            "eventId",
            "materialRevision",
            "opportunityId",
            "planId",
            "utteranceId",
            "tapeChannel",
        }
    )

    def __init__(
        self,
        *,
        source_class: FunnelSourceClass | str,
        candidate_id: str | None,
        detector_observation_id: str | None,
        event_id: str | None,
        material_revision: int | None,
        opportunity_id: str | None,
        plan_id: str | None,
        utterance_id: str | None,
        tape_channel: str,
    ) -> None:
        if source_class not in _FUNNEL_SOURCE_CLASSES:
            raise ContractViolation(f"invalid funnel sourceClass: {source_class!r}")
        object.__setattr__(self, "source_class", source_class)
        for field, value in (
            ("candidate_id", candidate_id),
            ("detector_observation_id", detector_observation_id),
            ("event_id", event_id),
            ("opportunity_id", opportunity_id),
            ("plan_id", plan_id),
            ("utterance_id", utterance_id),
        ):
            object.__setattr__(self, field, None if value is None else Identifier(value))
        object.__setattr__(
            self,
            "material_revision",
            (
                None
                if material_revision is None
                else _bounded_int(material_revision, "funnel materialRevision")
            ),
        )
        object.__setattr__(self, "tape_channel", Identifier(tape_channel))

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
    def from_dict(cls, value: object) -> Self:
        data = _exact_object(value, cls._FIELDS, "FunnelIdentity")
        return cls(
            source_class=data["sourceClass"],
            candidate_id=data["candidateId"],
            detector_observation_id=data["detectorObservationId"],
            event_id=data["eventId"],
            material_revision=data["materialRevision"],
            opportunity_id=data["opportunityId"],
            plan_id=data["planId"],
            utterance_id=data["utteranceId"],
            tape_channel=data["tapeChannel"],
        )


def derived_delivery_class(kind: str, phase: str) -> DeliveryClass:
    return "protected" if phase in {"ended", "result"} or kind in _PROTECTED_KINDS else "ordinary"


@dataclass(frozen=True, slots=True, init=False)
class NarrativeEvent:
    event_id: Identifier
    kind: Identifier
    phase: NarrativePhase
    delivery_class: DeliveryClass
    source_envelope: NarrativeSourceEnvelope | None
    source_order: NarrativeSourceOrder | None
    occurred_mono_ms: MonotonicMs
    broadcast_epoch: BroadcastEpoch
    stream_epoch: StreamEpoch
    session_ref: SessionRef | None
    occurrence_id: OccurrenceId | None
    lineage_id: LineageId | None
    correlation_key: tuple[Identifier, ...]
    fact_ids: tuple[Identifier, ...]
    fact_view_revision: int
    material_revision: int
    confidence: Confidence
    tape_channel: Identifier
    funnel: FunnelIdentity
    taxonomy_hash: Sha256Hash
    _payload_json: str

    SCHEMA_VERSION: ClassVar[SchemaVersion] = SchemaVersion("narrative-event/2")
    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "schemaVersion",
            "eventId",
            "kind",
            "phase",
            "deliveryClass",
            "sourceEnvelope",
            "sourceOrder",
            "occurredMonoMs",
            "broadcastEpoch",
            "streamEpoch",
            "sessionRef",
            "occurrenceId",
            "lineageId",
            "correlationKey",
            "factIds",
            "factViewRevision",
            "materialRevision",
            "confidence",
            "tapeChannel",
            "funnel",
            "taxonomyHash",
            "payload",
        }
    )

    def __init__(
        self,
        *,
        event_id: str,
        kind: str,
        phase: NarrativePhase | str,
        delivery_class: DeliveryClass | str,
        source_envelope: NarrativeSourceEnvelope | None,
        source_order: NarrativeSourceOrder | None,
        occurred_mono_ms: int,
        broadcast_epoch: int,
        stream_epoch: int,
        session_ref: SessionRef | None,
        occurrence_id: OccurrenceId | None,
        lineage_id: LineageId | None,
        correlation_key: tuple[str, ...] | list[str],
        fact_ids: tuple[str, ...] | list[str],
        fact_view_revision: int,
        material_revision: int,
        confidence: float,
        tape_channel: str,
        funnel: FunnelIdentity,
        taxonomy_hash: str,
        payload: dict[str, Any],
    ) -> None:
        event = Identifier(event_id)
        event_kind = Identifier(kind)
        if phase not in _NARRATIVE_PHASES:
            raise ContractViolation(f"invalid NarrativeEvent phase: {phase!r}")
        expected_delivery = derived_delivery_class(event_kind, phase)
        if delivery_class != expected_delivery:
            raise ContractViolation(
                f"deliveryClass must be derived as {expected_delivery!r} for {kind}/{phase}"
            )
        if source_envelope is not None and not isinstance(source_envelope, NarrativeSourceEnvelope):
            raise ContractViolation("sourceEnvelope must be NarrativeSourceEnvelope or null")
        if source_order is not None and not isinstance(source_order, NarrativeSourceOrder):
            raise ContractViolation("sourceOrder must be NarrativeSourceOrder or null")
        if session_ref is not None and not isinstance(session_ref, SessionRef):
            raise ContractViolation("sessionRef must be SessionRef or null")
        if occurrence_id is not None and not isinstance(occurrence_id, OccurrenceId):
            raise ContractViolation("occurrenceId must be OccurrenceId or null")
        if lineage_id is not None and not isinstance(lineage_id, LineageId):
            raise ContractViolation("lineageId must be LineageId or null")
        occurrence, lineage = validate_occurrence_lineage(
            occurrence_id, lineage_id, allow_stream_scope=session_ref is None
        )
        if (session_ref is None) != (occurrence is None):
            raise ContractViolation(
                "sessionRef and occurrence identity must be jointly present or null"
            )
        if not isinstance(funnel, FunnelIdentity):
            raise ContractViolation("funnel must be FunnelIdentity")
        if event_kind in _PROTECTED_KINDS:
            if source_envelope is not None or source_order is not None:
                raise ContractViolation("lifecycle NarrativeEvent must have null V4 provenance")
            if funnel.source_class != "lifecycle":
                raise ContractViolation("lifecycle NarrativeEvent requires lifecycle funnel")
        elif funnel.source_class == "lifecycle":
            raise ContractViolation("non-lifecycle NarrativeEvent cannot use lifecycle funnel")
        channel = Identifier(tape_channel)
        material = _bounded_int(material_revision, "materialRevision")
        if funnel.event_id != event or funnel.material_revision != material:
            raise ContractViolation("funnel event/material identity must match NarrativeEvent")
        if funnel.tape_channel != channel:
            raise ContractViolation("funnel tapeChannel must match NarrativeEvent")
        if not isinstance(payload, dict) or any(not isinstance(key, str) for key in payload):
            raise ContractViolation("payload must be a JSON object")
        if len(payload) > 32:
            raise ContractViolation("payload must contain at most 32 fields")
        payload_json = canonical_json(payload)

        object.__setattr__(self, "event_id", event)
        object.__setattr__(self, "kind", event_kind)
        object.__setattr__(self, "phase", phase)
        object.__setattr__(self, "delivery_class", delivery_class)
        object.__setattr__(self, "source_envelope", source_envelope)
        object.__setattr__(self, "source_order", source_order)
        object.__setattr__(self, "occurred_mono_ms", MonotonicMs(occurred_mono_ms))
        object.__setattr__(self, "broadcast_epoch", BroadcastEpoch(broadcast_epoch))
        object.__setattr__(self, "stream_epoch", StreamEpoch(stream_epoch))
        object.__setattr__(self, "session_ref", session_ref)
        object.__setattr__(self, "occurrence_id", occurrence)
        object.__setattr__(self, "lineage_id", lineage)
        object.__setattr__(
            self, "correlation_key", _unique_ids(correlation_key, "correlationKey", 0, 8)
        )
        object.__setattr__(self, "fact_ids", _unique_ids(fact_ids, "factIds", 1, 32))
        object.__setattr__(
            self,
            "fact_view_revision",
            _bounded_int(fact_view_revision, "factViewRevision"),
        )
        object.__setattr__(self, "material_revision", material)
        object.__setattr__(self, "confidence", Confidence(confidence))
        object.__setattr__(self, "tape_channel", channel)
        object.__setattr__(self, "funnel", funnel)
        object.__setattr__(self, "taxonomy_hash", Sha256Hash(taxonomy_hash))
        object.__setattr__(self, "_payload_json", payload_json)

    @property
    def payload(self) -> dict[str, Any]:
        value = json.loads(self._payload_json)
        assert isinstance(value, dict)
        return value

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": str(self.SCHEMA_VERSION),
            "eventId": str(self.event_id),
            "kind": str(self.kind),
            "phase": self.phase,
            "deliveryClass": self.delivery_class,
            "sourceEnvelope": (
                None if self.source_envelope is None else self.source_envelope.to_dict()
            ),
            "sourceOrder": None if self.source_order is None else self.source_order.to_dict(),
            "occurredMonoMs": int(self.occurred_mono_ms),
            "broadcastEpoch": int(self.broadcast_epoch),
            "streamEpoch": int(self.stream_epoch),
            "sessionRef": None if self.session_ref is None else self.session_ref.to_dict(),
            "occurrenceId": None if self.occurrence_id is None else str(self.occurrence_id),
            "lineageId": None if self.lineage_id is None else str(self.lineage_id),
            "correlationKey": [str(item) for item in self.correlation_key],
            "factIds": [str(item) for item in self.fact_ids],
            "factViewRevision": self.fact_view_revision,
            "materialRevision": self.material_revision,
            "confidence": float(self.confidence),
            "tapeChannel": str(self.tape_channel),
            "funnel": self.funnel.to_dict(),
            "taxonomyHash": str(self.taxonomy_hash),
            "payload": self.payload,
        }

    @classmethod
    def from_dict(cls, value: object) -> Self:
        data = _exact_object(value, cls._FIELDS, "NarrativeEvent")
        if data["schemaVersion"] != cls.SCHEMA_VERSION:
            raise ContractViolation("NarrativeEvent schemaVersion must be narrative-event/2")
        return cls(
            event_id=data["eventId"],
            kind=data["kind"],
            phase=data["phase"],
            delivery_class=data["deliveryClass"],
            source_envelope=(
                None
                if data["sourceEnvelope"] is None
                else NarrativeSourceEnvelope.from_dict(data["sourceEnvelope"])
            ),
            source_order=(
                None
                if data["sourceOrder"] is None
                else NarrativeSourceOrder.from_dict(data["sourceOrder"])
            ),
            occurred_mono_ms=data["occurredMonoMs"],
            broadcast_epoch=data["broadcastEpoch"],
            stream_epoch=data["streamEpoch"],
            session_ref=(
                None if data["sessionRef"] is None else SessionRef.from_dict(data["sessionRef"])
            ),
            occurrence_id=(
                None if data["occurrenceId"] is None else OccurrenceId.parse(data["occurrenceId"])
            ),
            lineage_id=None if data["lineageId"] is None else LineageId.parse(data["lineageId"]),
            correlation_key=data["correlationKey"],
            fact_ids=data["factIds"],
            fact_view_revision=data["factViewRevision"],
            material_revision=data["materialRevision"],
            confidence=data["confidence"],
            tape_channel=data["tapeChannel"],
            funnel=FunnelIdentity.from_dict(data["funnel"]),
            taxonomy_hash=data["taxonomyHash"],
            payload=data["payload"],
        )
