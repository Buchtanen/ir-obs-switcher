"""Stateless adapter from accepted V4 events to immutable narrative events."""

from __future__ import annotations

from typing import Any

from irswitch.contracts import (
    FunnelIdentity,
    LineageId,
    NarrativeEvent,
    NarrativeSourceEnvelope,
    NarrativeSourceOrder,
    OccurrenceId,
    SessionRef,
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


__all__ = ["NarrativeAdmissionError", "adapt_accepted_event"]
