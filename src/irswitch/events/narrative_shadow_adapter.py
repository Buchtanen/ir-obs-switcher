"""Best-effort FrozenAcceptedEventBatch → AdaptedPublication for #284 shadow.

Builds synthetic timeline/fact_view identities consistent with adapted
NarrativeEvents so shadow fanout cutover can admit+reduce without the live
FeatureEngine/FactView owners. Skips batches with no commentary-audience
events that adapt successfully.

Observation-only for the default-on shadow path — not authoritative fact
ownership. Not exported from ``events/__init__.py``.
"""

from __future__ import annotations

import logging
from typing import Any

from irswitch.contracts.primitives import ContractViolation, LineageId, OccurrenceId
from irswitch.contracts.session import SessionRef
from irswitch.events.narrative import NarrativeAdmissionError, adapt_accepted_event
from irswitch.events.narrative_shadow_consumer import AdaptedPublication
from irswitch.events.stream import FrozenAcceptedEventBatch

logger = logging.getLogger(__name__)

_BROADCAST_EPOCH = 4
_STREAM_EPOCH = 1
_FACT_VIEW_REVISION = 9
_OCCURRENCE = "1:race:0"
_LINEAGE = "1:race:0"


def adapt_batch_for_shadow(batch: FrozenAcceptedEventBatch) -> AdaptedPublication | None:
    """Adapt commentary-audience accepted events into one shadow publication.

    Returns ``None`` when nothing can be admitted (no commentary events or all
    adaptations fail closed). Never raises into the consumer loop.
    """

    if not isinstance(batch, FrozenAcceptedEventBatch):
        return None
    adapted_events = []
    facts: list[dict[str, Any]] = []
    for index, accepted in enumerate(batch.events):
        if "commentary" not in accepted.audiences:
            continue
        fact_id = f"fact:shadow:{batch.stream_sequence}:{accepted.source_ordinal}:{index}"
        try:
            event = adapt_accepted_event(
                accepted,
                fanout_stream_sequence=int(batch.stream_sequence),
                broadcast_epoch=_BROADCAST_EPOCH,
                stream_epoch=_STREAM_EPOCH,
                session_ref=SessionRef("42", 2),
                occurrence_id=OccurrenceId.parse(_OCCURRENCE),
                lineage_id=LineageId.parse(_LINEAGE),
                fact_ids=(fact_id,),
                fact_view_revision=_FACT_VIEW_REVISION,
                material_revision=0,
                correlation_key=("shadow", str(accepted.event_id)),
                semantic_payload={},
            )
        except (NarrativeAdmissionError, ContractViolation, ValueError, TypeError) as exc:
            logger.debug(
                "shadow adapter skipped event %s: %s",
                accepted.event_id,
                exc,
            )
            continue
        adapted_events.append(event)
        facts.append(_shadow_fact(fact_id, observed_mono_ms=int(batch.accepted_monotonic_ms)))
    if not adapted_events:
        return None
    return AdaptedPublication(
        timeline=_shadow_timeline(observed_mono_ms=int(batch.accepted_monotonic_ms)),
        fact_view=_shadow_fact_view(
            facts,
            observed_mono_ms=int(batch.accepted_monotonic_ms),
        ),
        events=tuple(adapted_events),
        fanout_stream_sequence=int(batch.stream_sequence),
        command_id_prefix=f"shadow:{batch.stream_sequence}",
        enqueued_mono_ms=int(batch.accepted_monotonic_ms),
    )


def _shadow_timeline(*, observed_mono_ms: int) -> dict[str, Any]:
    return {
        "schemaVersion": "timeline-snapshot/2",
        "timelineRevision": 3,
        "observedMonoMs": observed_mono_ms,
        "broadcastEpoch": _BROADCAST_EPOCH,
        "streamEpoch": _STREAM_EPOCH,
        "narrativeRunActive": True,
        "obsState": "active",
        "sessionRef": {"subSessionId": "42", "sessionNum": 2},
        "stage": "race",
        "sessionPlanRevision": 1,
        "occurrenceId": _OCCURRENCE,
        "lineageId": _LINEAGE,
        "historyComplete": True,
        "transitionReasons": [],
    }


def _shadow_fact_view(facts: list[dict[str, Any]], *, observed_mono_ms: int) -> dict[str, Any]:
    return {
        "schemaVersion": "fact-view/2",
        "viewRevision": _FACT_VIEW_REVISION,
        "createdMonoMs": observed_mono_ms,
        "broadcastEpoch": _BROADCAST_EPOCH,
        "streamEpoch": _STREAM_EPOCH,
        "occurrenceId": _OCCURRENCE,
        "lineageId": _LINEAGE,
        "historyComplete": True,
        "facts": facts,
        "compactedSummaryRefs": [],
    }


def _shadow_fact(fact_id: str, *, observed_mono_ms: int) -> dict[str, Any]:
    return {
        "schemaVersion": "atomic-fact/2",
        "factId": fact_id,
        "predicate": "shadow.observation",
        "subjectId": "shadow:subject",
        "objectId": None,
        "attributes": {},
        "polarity": "positive",
        "validFromMonoMs": max(0, observed_mono_ms - 100),
        "validUntilMonoMs": observed_mono_ms + 500,
        "observedAtMonoMs": observed_mono_ms,
        "broadcastEpoch": _BROADCAST_EPOCH,
        "streamEpoch": _STREAM_EPOCH,
        "occurrenceId": _OCCURRENCE,
        "lineageId": _LINEAGE,
        "evidenceRefs": ["shadow:adapter"],
        "confidence": 0.5,
        "scope": "occurrence",
        "status": "active",
        "revision": 0,
    }
