"""Stateless adapter from accepted V4 events to immutable narrative events."""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any

from irswitch.contracts import (
    ApplyContextBatch,
    ContextBatchPart,
    ContractViolation,
    ExternalOrder,
    FunnelIdentity,
    LineageId,
    NarrativeEvent,
    NarrativeSourceEnvelope,
    NarrativeSourceOrder,
    OccurrenceId,
    SessionRef,
    StreamEpoch,
    derived_delivery_class,
)
from irswitch.events.stream import FrozenAcceptedEvent, thaw_envelope
from irswitch.events.taxonomy import (
    NarrativeAdmissionError,
    narrative_policy_for_event_type,
    narrative_taxonomy_hash,
)

_PHASES = {
    "ENTER": "started",
    "ACTIVE": "started",
    "UPDATE": "updated",
    "COMPACT": "updated",
    "SUSPEND": "ended",
    "RESUME": "updated",
    "EXIT": "ended",
    "RESULT": "result",
}
_LIFECYCLE_POLICY = {
    "STREAM_STARTED": ("started", "stream.lifecycle"),
    "STREAM_ENDED": ("ended", "stream.lifecycle"),
    "SESSION_STARTED": ("started", "session.lifecycle"),
    "SESSION_ENDED": ("ended", "session.lifecycle"),
    "SESSION_RESTARTED": ("impulse", "session.lifecycle"),
}


@dataclass(frozen=True, slots=True)
class NarrativeDedupeResult:
    events: tuple[NarrativeEvent, ...]
    equal_arrivals: tuple[tuple[str, int], ...]


class NarrativeEventDeduplicator:
    """Run-scoped exactly-once admission with explicit equal-arrival evidence."""

    def __init__(self, *, stream_epoch: int) -> None:
        self._stream_epoch = StreamEpoch(stream_epoch)
        self._seen: dict[tuple[str, int], NarrativeEvent] = {}
        self._lock = Lock()

    def admit(self, events: tuple[NarrativeEvent, ...]) -> NarrativeDedupeResult:
        with self._lock:
            return self._admit_locked(events)

    def _admit_locked(self, events: tuple[NarrativeEvent, ...]) -> NarrativeDedupeResult:
        retained: list[NarrativeEvent] = []
        equal_arrivals: list[tuple[str, int]] = []
        next_seen = dict(self._seen)
        for event in events:
            if not isinstance(event, NarrativeEvent):
                raise ContractViolation("narrative deduplicator requires NarrativeEvent values")
            if event.stream_epoch != self._stream_epoch:
                raise ContractViolation("NarrativeEvent stream epoch differs from deduplicator run")
            key = (str(event.event_id), event.material_revision)
            previous = next_seen.get(key)
            if previous is None:
                next_seen[key] = event
                retained.append(event)
            elif previous == event:
                equal_arrivals.append(key)
            else:
                raise ContractViolation(
                    f"duplicate event identity {key!r} carries conflicting content"
                )
        self._seen = next_seen
        return NarrativeDedupeResult(tuple(retained), tuple(equal_arrivals))

    def reset(self, *, stream_epoch: int) -> None:
        """Begin a new narrative run after the owner records its boundary."""

        with self._lock:
            self._stream_epoch = StreamEpoch(stream_epoch)
            self._seen.clear()


def deduplicate_narrative_events(
    events: tuple[NarrativeEvent, ...],
) -> tuple[NarrativeEvent, ...]:
    """Drop byte-equivalent redelivery and reject changed content under one identity."""

    retained: list[NarrativeEvent] = []
    seen: dict[tuple[str, int], NarrativeEvent] = {}
    for event in events:
        key = (str(event.event_id), event.material_revision)
        previous = seen.get(key)
        if previous is None:
            seen[key] = event
            retained.append(event)
        elif previous != event:
            raise ContractViolation(f"duplicate event identity {key!r} carries conflicting content")
    return tuple(retained)


def partition_context_batches(
    *,
    timeline: dict[str, Any],
    fact_view: dict[str, Any],
    events: tuple[NarrativeEvent, ...],
    fanout_stream_sequence: int,
) -> tuple[ContextBatchPart, ...]:
    """Losslessly partition one accepted publication without reordering events."""

    if not events:
        batch = ApplyContextBatch(timeline=timeline, fact_view=fact_view, events=())
        return (
            ContextBatchPart(
                batch=batch,
                external_order=ExternalOrder(fanout_stream_sequence, None, None),
            ),
        )
    previous_ordinal: int | None = None
    saw_external_event = False
    for event in events:
        order = event.source_order
        if order is None:
            if str(event.kind) not in _LIFECYCLE_POLICY or event.source_envelope is not None:
                raise ContractViolation(
                    "only internal lifecycle NarrativeEvents may omit source order"
                )
            if saw_external_event:
                raise ContractViolation(
                    "lifecycle precedence requires lifecycle events before external events"
                )
            continue
        saw_external_event = True
        if int(order.fanout_stream_sequence) != fanout_stream_sequence:
            raise ContractViolation("NarrativeEvent fanout sequence differs from publication")
        if previous_ordinal is not None and order.source_ordinal <= previous_ordinal:
            raise ContractViolation("NarrativeEvent source order must be strictly increasing")
        previous_ordinal = order.source_ordinal
    parts: list[ContextBatchPart] = []
    for offset in range(0, len(events), 64):
        chunk = events[offset : offset + 64]
        source_orders = [event.source_order for event in chunk if event.source_order is not None]
        parts.append(
            ContextBatchPart(
                batch=ApplyContextBatch(
                    timeline=timeline,
                    fact_view=fact_view,
                    events=chunk,
                ),
                external_order=ExternalOrder(
                    fanout_stream_sequence,
                    None if not source_orders else source_orders[0].source_ordinal,
                    None if not source_orders else source_orders[-1].source_ordinal,
                ),
            )
        )
    return tuple(parts)


def adapt_lifecycle_event(
    kind: str,
    *,
    event_id: str,
    occurred_mono_ms: int,
    broadcast_epoch: int,
    stream_epoch: int,
    session_ref: SessionRef | None,
    occurrence_id: OccurrenceId | None,
    lineage_id: LineageId | None,
    fact_ids: tuple[str, ...],
    fact_view_revision: int,
    material_revision: int,
    correlation_key: tuple[str, ...],
    payload: dict[str, Any],
) -> NarrativeEvent:
    """Create one of the five internal lifecycle events without a V4 envelope."""

    try:
        phase, tape_channel = _LIFECYCLE_POLICY[kind]
    except KeyError as exc:
        raise ContractViolation(f"unknown lifecycle kind: {kind!r}") from exc
    funnel = FunnelIdentity(
        source_class="lifecycle",
        candidate_id=None,
        detector_observation_id=None,
        event_id=event_id,
        material_revision=material_revision,
        opportunity_id=None,
        plan_id=None,
        utterance_id=None,
        tape_channel=tape_channel,
    )
    return NarrativeEvent(
        event_id=event_id,
        kind=kind,
        phase=phase,
        delivery_class=derived_delivery_class(kind, phase),
        source_envelope=None,
        source_order=None,
        occurred_mono_ms=occurred_mono_ms,
        broadcast_epoch=broadcast_epoch,
        stream_epoch=stream_epoch,
        session_ref=session_ref,
        occurrence_id=occurrence_id,
        lineage_id=lineage_id,
        correlation_key=correlation_key,
        fact_ids=fact_ids,
        fact_view_revision=fact_view_revision,
        material_revision=material_revision,
        confidence=1.0,
        tape_channel=tape_channel,
        funnel=funnel,
        taxonomy_hash=narrative_taxonomy_hash(),
        payload=payload,
    )


def adapt_accepted_event(
    accepted: FrozenAcceptedEvent,
    *,
    fanout_stream_sequence: int,
    broadcast_epoch: int,
    stream_epoch: int,
    session_ref: SessionRef | None,
    occurrence_id: OccurrenceId | None,
    lineage_id: LineageId | None,
    fact_ids: tuple[str, ...],
    fact_view_revision: int,
    material_revision: int,
    correlation_key: tuple[str, ...],
    semantic_payload: dict[str, Any],
    candidate_id: str | None = None,
    detector_observation_id: str | None = None,
) -> NarrativeEvent:
    """Adapt one immutable accepted value without mutating the V4 envelope wire."""

    if not isinstance(accepted, FrozenAcceptedEvent):
        raise NarrativeAdmissionError("adapter requires a FrozenAcceptedEvent")
    if "commentary" not in accepted.audiences:
        raise NarrativeAdmissionError("accepted event has no commentary audience")
    envelope = thaw_envelope(accepted.envelope)
    policy = narrative_policy_for_event_type(envelope.event_type)
    try:
        phase = _PHASES[envelope.phase]
    except KeyError as exc:
        raise NarrativeAdmissionError(f"unmapped V4 phase: {envelope.phase!r}") from exc
    source_envelope = NarrativeSourceEnvelope(
        envelope.session_id, envelope.event_id, envelope.sequence, envelope.event_type
    )
    source_order = NarrativeSourceOrder(fanout_stream_sequence, accepted.source_ordinal)
    funnel = FunnelIdentity(
        source_class="detector" if detector_observation_id is not None else "direct",
        candidate_id=candidate_id,
        detector_observation_id=detector_observation_id,
        event_id=envelope.event_id,
        material_revision=material_revision,
        opportunity_id=None,
        plan_id=None,
        utterance_id=None,
        tape_channel=policy.tape_channel,
    )
    return NarrativeEvent(
        event_id=envelope.event_id,
        kind=policy.narrative_kind,
        phase=phase,
        delivery_class=derived_delivery_class(policy.narrative_kind, phase),
        source_envelope=source_envelope,
        source_order=source_order,
        occurred_mono_ms=envelope.monotonic_ms,
        broadcast_epoch=broadcast_epoch,
        stream_epoch=stream_epoch,
        session_ref=session_ref,
        occurrence_id=occurrence_id,
        lineage_id=lineage_id,
        correlation_key=correlation_key,
        fact_ids=fact_ids,
        fact_view_revision=fact_view_revision,
        material_revision=material_revision,
        confidence=envelope.confidence,
        tape_channel=policy.tape_channel,
        funnel=funnel,
        taxonomy_hash=narrative_taxonomy_hash(),
        payload=semantic_payload,
    )


__all__ = [
    "NarrativeAdmissionError",
    "NarrativeDedupeResult",
    "NarrativeEventDeduplicator",
    "adapt_accepted_event",
    "adapt_lifecycle_event",
    "deduplicate_narrative_events",
    "partition_context_batches",
]
