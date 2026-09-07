"""Immutable coherent context payloads shared with NarrativeCommand."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .narrative import NarrativeEvent
from .primitives import MAX_SIGNED_INT64, ContractViolation, SourceSequence, canonical_json

_TIMELINE_FIELDS = frozenset(
    {
        "schemaVersion",
        "timelineRevision",
        "observedMonoMs",
        "broadcastEpoch",
        "streamEpoch",
        "narrativeRunActive",
        "obsState",
        "sessionRef",
        "stage",
        "sessionPlanRevision",
        "occurrenceId",
        "lineageId",
        "historyComplete",
        "transitionReasons",
    }
)
_FACT_VIEW_FIELDS = frozenset(
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


def _bounded_int(value: object, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractViolation(f"{field} must be an integer")
    if not minimum <= value <= MAX_SIGNED_INT64:
        raise ContractViolation(f"{field} must be in {minimum}..{MAX_SIGNED_INT64}")
    return value


def _snapshot(value: object, fields: frozenset[str], label: str) -> tuple[dict[str, Any], str]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ContractViolation(f"{label} must be a JSON object")
    actual = frozenset(value)
    if actual != fields:
        raise ContractViolation(
            f"invalid {label} fields; missing={sorted(fields - actual)}, "
            f"unknown={sorted(actual - fields)}"
        )
    encoded = canonical_json(value)
    decoded = json.loads(encoded)
    assert isinstance(decoded, dict)
    return decoded, encoded


@dataclass(frozen=True, slots=True, init=False)
class ContextRevision:
    timeline_revision: int
    fact_view_revision: int

    def __init__(self, timeline_revision: int, fact_view_revision: int) -> None:
        object.__setattr__(
            self,
            "timeline_revision",
            _bounded_int(timeline_revision, "timelineRevision"),
        )
        object.__setattr__(
            self,
            "fact_view_revision",
            _bounded_int(fact_view_revision, "factViewRevision"),
        )

    def to_dict(self) -> dict[str, int]:
        return {
            "timelineRevision": self.timeline_revision,
            "factViewRevision": self.fact_view_revision,
        }


@dataclass(frozen=True, slots=True, init=False)
class ExternalOrder:
    fanout_stream_sequence: SourceSequence
    first_source_ordinal: int | None
    last_source_ordinal: int | None

    def __init__(
        self,
        fanout_stream_sequence: int,
        first_source_ordinal: int | None,
        last_source_ordinal: int | None,
    ) -> None:
        sequence = SourceSequence(fanout_stream_sequence)
        if (first_source_ordinal is None) != (last_source_ordinal is None):
            raise ContractViolation(
                "source ordinal range endpoints must be jointly present or null"
            )
        first: int | None
        last: int | None
        if first_source_ordinal is not None and last_source_ordinal is not None:
            first = _bounded_int(first_source_ordinal, "firstSourceOrdinal")
            last = _bounded_int(last_source_ordinal, "lastSourceOrdinal")
            if last < first:
                raise ContractViolation("source ordinal range must be ordered")
        else:
            first = last = None
        object.__setattr__(self, "fanout_stream_sequence", sequence)
        object.__setattr__(self, "first_source_ordinal", first)
        object.__setattr__(self, "last_source_ordinal", last)

    def to_dict(self) -> dict[str, int | None]:
        return {
            "fanoutStreamSequence": int(self.fanout_stream_sequence),
            "firstSourceOrdinal": self.first_source_ordinal,
            "lastSourceOrdinal": self.last_source_ordinal,
        }


@dataclass(frozen=True, slots=True, init=False)
class ApplyContextBatch:
    """Frozen truth projection plus accepted events; owns no truth mutation."""

    _timeline_json: str
    _fact_view_json: str
    events: tuple[NarrativeEvent, ...]
    context_revision: ContextRevision
    has_timeline_transition: bool

    def __init__(
        self,
        *,
        timeline: dict[str, Any],
        fact_view: dict[str, Any],
        events: tuple[NarrativeEvent, ...],
    ) -> None:
        timeline_value, timeline_json = _snapshot(timeline, _TIMELINE_FIELDS, "TimelineSnapshot")
        fact_view_value, fact_view_json = _snapshot(fact_view, _FACT_VIEW_FIELDS, "FactView")
        if timeline_value.get("schemaVersion") != "timeline-snapshot/2":
            raise ContractViolation("TimelineSnapshot schemaVersion must be timeline-snapshot/2")
        if fact_view_value.get("schemaVersion") != "fact-view/2":
            raise ContractViolation("FactView schemaVersion must be fact-view/2")
        timeline_revision = _bounded_int(timeline_value.get("timelineRevision"), "timelineRevision")
        fact_view_revision = _bounded_int(fact_view_value.get("viewRevision"), "viewRevision")
        event_values = tuple(events)
        if len(event_values) > 64:
            raise ContractViolation("APPLY_CONTEXT_BATCH may contain at most 64 events")
        if any(not isinstance(event, NarrativeEvent) for event in event_values):
            raise ContractViolation("events must contain NarrativeEvent values")
        self._validate_projection_identity(timeline_value, fact_view_value)
        self._validate_events(event_values, fact_view_value, fact_view_revision)
        reasons = timeline_value.get("transitionReasons")
        if not isinstance(reasons, list) or any(not isinstance(reason, str) for reason in reasons):
            raise ContractViolation(
                "TimelineSnapshot transitionReasons must be an array of strings"
            )
        if len(reasons) > 8 or len(set(reasons)) != len(reasons):
            raise ContractViolation("TimelineSnapshot transitionReasons must be 0..8 unique values")
        object.__setattr__(self, "_timeline_json", timeline_json)
        object.__setattr__(self, "_fact_view_json", fact_view_json)
        object.__setattr__(self, "events", event_values)
        object.__setattr__(
            self, "context_revision", ContextRevision(timeline_revision, fact_view_revision)
        )
        object.__setattr__(self, "has_timeline_transition", bool(reasons))

    @staticmethod
    def _validate_projection_identity(timeline: dict[str, Any], fact_view: dict[str, Any]) -> None:
        for field in ("broadcastEpoch", "streamEpoch", "occurrenceId", "lineageId"):
            if timeline.get(field) != fact_view.get(field):
                raise ContractViolation(f"TimelineSnapshot and FactView disagree on {field}")

    @staticmethod
    def _validate_events(
        events: tuple[NarrativeEvent, ...], fact_view: dict[str, Any], revision: int
    ) -> None:
        facts = fact_view.get("facts")
        if not isinstance(facts, list):
            raise ContractViolation("FactView facts must be an array")
        indexed: dict[str, dict[str, Any]] = {}
        for fact in facts:
            if not isinstance(fact, dict) or not isinstance(fact.get("factId"), str):
                raise ContractViolation("FactView contains an invalid fact identity")
            fact_id = fact["factId"]
            if fact_id in indexed:
                raise ContractViolation("FactView fact identities must be unique")
            indexed[fact_id] = fact
        for event in events:
            if event.fact_view_revision != revision:
                raise ContractViolation("NarrativeEvent factViewRevision must match FactView")
            for fact_id in event.fact_ids:
                fact = indexed.get(str(fact_id))
                if fact is None:
                    raise ContractViolation(f"NarrativeEvent factId {fact_id!s} is absent")
                expected = (
                    int(event.broadcast_epoch),
                    int(event.stream_epoch),
                    None if event.occurrence_id is None else str(event.occurrence_id),
                    None if event.lineage_id is None else str(event.lineage_id),
                )
                actual = tuple(
                    fact.get(field)
                    for field in ("broadcastEpoch", "streamEpoch", "occurrenceId", "lineageId")
                )
                if actual != expected:
                    raise ContractViolation(
                        f"NarrativeEvent fact identity does not match {fact_id!s}"
                    )

    @property
    def timeline(self) -> dict[str, Any]:
        value = json.loads(self._timeline_json)
        assert isinstance(value, dict)
        return value

    @property
    def fact_view(self) -> dict[str, Any]:
        value = json.loads(self._fact_view_json)
        assert isinstance(value, dict)
        return value

    @property
    def protected(self) -> bool:
        return self.has_timeline_transition or any(
            event.delivery_class == "protected" for event in self.events
        )

    @property
    def planning_impulse(self) -> bool:
        return bool(self.events)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timeline": self.timeline,
            "factView": self.fact_view,
            "events": [event.to_dict() for event in self.events],
        }


@dataclass(frozen=True, slots=True)
class ContextBatchPart:
    batch: ApplyContextBatch
    external_order: ExternalOrder

    @property
    def context_revision(self) -> ContextRevision:
        return self.batch.context_revision

    @property
    def protected(self) -> bool:
        return self.batch.protected

    @property
    def planning_impulse(self) -> bool:
        return self.batch.planning_impulse
