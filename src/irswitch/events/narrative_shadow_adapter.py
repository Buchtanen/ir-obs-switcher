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
from typing import TYPE_CHECKING, Any

from irswitch.contracts.primitives import ContractViolation, LineageId, OccurrenceId
from irswitch.contracts.session import SessionRef
from irswitch.events.narrative import NarrativeAdmissionError, adapt_accepted_event
from irswitch.events.narrative_shadow_consumer import AdaptedPublication
from irswitch.events.stream import FrozenAcceptedEventBatch

if TYPE_CHECKING:
    from irswitch.events.stream import SessionReset

logger = logging.getLogger(__name__)

_BROADCAST_EPOCH = 4
_STREAM_EPOCH = 1
_OCCURRENCE = "1:race:0"
_LINEAGE = "1:race:0"


def adapt_batch_for_shadow(
    batch: FrozenAcceptedEventBatch,
    *,
    narrative_run_active: bool = False,
) -> AdaptedPublication | None:
    """Adapt commentary-audience accepted events into one shadow publication.

    ``narrative_run_active`` must follow the commentary kill-switch
    (``commentary.enabled``). Default ``False`` so callers cannot silently
    invent an active narrative run.

    Timeline/fact revisions follow ``batch.stream_sequence`` so later live
    batches can clear a recovery barrier floor (Slice 2 / #349). Fixed
    synthetic revisions must not permanently lose to recovery.

    Returns ``None`` when nothing can be admitted (no commentary events or all
    adaptations fail closed). Never raises into the consumer loop.
    """

    if not isinstance(batch, FrozenAcceptedEventBatch):
        return None
    revision = max(1, int(batch.stream_sequence))
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
                fact_view_revision=revision,
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
        timeline=_shadow_timeline(
            observed_mono_ms=int(batch.accepted_monotonic_ms),
            narrative_run_active=bool(narrative_run_active),
            timeline_revision=revision,
        ),
        fact_view=_shadow_fact_view(
            facts,
            observed_mono_ms=int(batch.accepted_monotonic_ms),
            view_revision=revision,
        ),
        events=tuple(adapted_events),
        fanout_stream_sequence=int(batch.stream_sequence),
        command_id_prefix=f"shadow:{batch.stream_sequence}",
        enqueued_mono_ms=int(batch.accepted_monotonic_ms),
    )


def adapt_session_reset_for_shadow(
    reset: SessionReset,
    *,
    observed_mono_ms: int | None = None,
) -> AdaptedPublication:
    """Empty shadow publication for SessionReset mailbox cutover (#349 Slice 2).

    Revisions follow ``reset.stream_sequence`` so post-recovery context is not
    permanently stale. ``narrativeRunActive`` is False — reset clears the run.
    """

    from irswitch.events.stream import SessionReset

    if not isinstance(reset, SessionReset):
        raise TypeError("adapt_session_reset_for_shadow requires SessionReset")
    revision = max(1, int(reset.stream_sequence))
    mono = int(observed_mono_ms) if observed_mono_ms is not None else revision * 1000
    return AdaptedPublication(
        timeline=_shadow_timeline(
            observed_mono_ms=mono,
            narrative_run_active=False,
            timeline_revision=revision,
        ),
        fact_view=_shadow_fact_view([], observed_mono_ms=mono, view_revision=revision),
        events=(),
        fanout_stream_sequence=revision,
        command_id_prefix=f"shadow-reset:{revision}",
        enqueued_mono_ms=mono,
    )


def _shadow_timeline(
    *,
    observed_mono_ms: int,
    narrative_run_active: bool = False,
    timeline_revision: int = 1,
) -> dict[str, Any]:
    return {
        "schemaVersion": "timeline-snapshot/2",
        "timelineRevision": int(timeline_revision),
        "observedMonoMs": observed_mono_ms,
        "broadcastEpoch": _BROADCAST_EPOCH,
        "streamEpoch": _STREAM_EPOCH,
        "narrativeRunActive": bool(narrative_run_active),
        "obsState": "active",
        "sessionRef": {"subSessionId": "42", "sessionNum": 2},
        "stage": "race",
        "sessionPlanRevision": 1,
        "occurrenceId": _OCCURRENCE,
        "lineageId": _LINEAGE,
        "historyComplete": True,
        "transitionReasons": [],
    }


def _shadow_fact_view(
    facts: list[dict[str, Any]],
    *,
    observed_mono_ms: int,
    view_revision: int = 1,
) -> dict[str, Any]:
    return {
        "schemaVersion": "fact-view/2",
        "viewRevision": int(view_revision),
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
