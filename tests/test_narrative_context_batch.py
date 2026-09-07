from __future__ import annotations

import copy

import pytest

from irswitch.contracts import (
    ApplyContextBatch,
    ContextRevision,
    ContractViolation,
    ExternalOrder,
    NarrativeEvent,
)
from irswitch.events.narrative import (
    deduplicate_narrative_events,
    partition_context_batches,
)
from irswitch.events.taxonomy import narrative_taxonomy_hash


def _timeline(*, revision: int = 3, transition_reasons: list[str] | None = None) -> dict:
    return {
        "schemaVersion": "timeline-snapshot/2",
        "timelineRevision": revision,
        "observedMonoMs": 1000,
        "broadcastEpoch": 4,
        "streamEpoch": 1,
        "narrativeRunActive": True,
        "obsState": "active",
        "sessionRef": {"subSessionId": "42", "sessionNum": 2},
        "stage": "race",
        "sessionPlanRevision": 1,
        "occurrenceId": "1:race:0",
        "lineageId": "1:race:0",
        "historyComplete": True,
        "transitionReasons": transition_reasons or [],
    }


def _fact(fact_id: str) -> dict:
    return {
        "schemaVersion": "atomic-fact/2",
        "factId": fact_id,
        "predicate": "battle.closing",
        "subjectId": "car:12",
        "objectId": "car:34",
        "attributes": {"gapSeconds": 0.42},
        "polarity": "positive",
        "validFromMonoMs": 900,
        "validUntilMonoMs": 1500,
        "observedAtMonoMs": 1000,
        "broadcastEpoch": 4,
        "streamEpoch": 1,
        "occurrenceId": "1:race:0",
        "lineageId": "1:race:0",
        "evidenceRefs": ["telemetry:1"],
        "confidence": 0.8,
        "scope": "occurrence",
        "status": "active",
        "revision": 0,
    }


def _fact_view(count: int, *, revision: int = 9) -> dict:
    return {
        "schemaVersion": "fact-view/2",
        "viewRevision": revision,
        "createdMonoMs": 1000,
        "broadcastEpoch": 4,
        "streamEpoch": 1,
        "occurrenceId": "1:race:0",
        "lineageId": "1:race:0",
        "historyComplete": True,
        "facts": [_fact(f"fact:battle:{index}") for index in range(count)],
        "compactedSummaryRefs": [],
    }


def _event(index: int, *, fanout: int = 11, fact_revision: int = 9) -> NarrativeEvent:
    event_id = f"event:hunting:{index}"
    fact_id = f"fact:battle:{index}"
    return NarrativeEvent.from_dict(
        {
            "schemaVersion": "narrative-event/2",
            "eventId": event_id,
            "kind": "battle.pursuit",
            "phase": "started",
            "deliveryClass": "ordinary",
            "sourceEnvelope": {
                "sessionId": "session:42",
                "eventId": event_id,
                "sequence": index + 1,
                "eventType": "HUNTING",
            },
            "sourceOrder": {
                "fanoutStreamSequence": fanout,
                "sourceOrdinal": index,
            },
            "occurredMonoMs": 1000 + index,
            "broadcastEpoch": 4,
            "streamEpoch": 1,
            "sessionRef": {"subSessionId": "42", "sessionNum": 2},
            "occurrenceId": "1:race:0",
            "lineageId": "1:race:0",
            "correlationKey": ["car:12", "car:34"],
            "factIds": [fact_id],
            "factViewRevision": fact_revision,
            "materialRevision": 0,
            "confidence": 0.8,
            "tapeChannel": "race.battle.closing",
            "funnel": {
                "sourceClass": "direct",
                "candidateId": f"candidate:hunting:{index}",
                "detectorObservationId": None,
                "eventId": event_id,
                "materialRevision": 0,
                "opportunityId": None,
                "planId": None,
                "utteranceId": None,
                "tapeChannel": "race.battle.closing",
            },
            "taxonomyHash": narrative_taxonomy_hash(),
            "payload": {"gapSeconds": 0.42},
        }
    )


def test_context_batch_round_trip_is_immutable_and_coherent() -> None:
    timeline = _timeline()
    facts = _fact_view(1)
    original_timeline = copy.deepcopy(timeline)
    original_facts = copy.deepcopy(facts)

    batch = ApplyContextBatch(timeline=timeline, fact_view=facts, events=(_event(0),))

    assert batch.context_revision == ContextRevision(3, 9)
    assert batch.to_dict() == {
        "timeline": original_timeline,
        "factView": original_facts,
        "events": [_event(0).to_dict()],
    }
    timeline["timelineRevision"] = 99
    facts["facts"].clear()
    assert batch.timeline["timelineRevision"] == 3
    assert len(batch.fact_view["facts"]) == 1


def test_context_batch_rejects_wrong_view_revision_or_fact_identity() -> None:
    with pytest.raises(ContractViolation, match="factViewRevision"):
        ApplyContextBatch(
            timeline=_timeline(),
            fact_view=_fact_view(1),
            events=(_event(0, fact_revision=8),),
        )

    facts = _fact_view(1)
    facts["facts"][0]["streamEpoch"] = 2
    with pytest.raises(ContractViolation, match="fact identity"):
        ApplyContextBatch(timeline=_timeline(), fact_view=facts, events=(_event(0),))


def test_partition_is_lossless_ordered_and_bounded_to_64_events() -> None:
    events = tuple(_event(index) for index in range(65))

    parts = partition_context_batches(
        timeline=_timeline(),
        fact_view=_fact_view(65),
        events=events,
        fanout_stream_sequence=11,
    )

    assert [len(part.batch.events) for part in parts] == [64, 1]
    assert [part.external_order for part in parts] == [
        ExternalOrder(11, 0, 63),
        ExternalOrder(11, 64, 64),
    ]
    assert tuple(event for part in parts for event in part.batch.events) == events
    assert all(part.context_revision == ContextRevision(3, 9) for part in parts)
    assert all(part.planning_impulse for part in parts)


def test_partition_rejects_reordering_or_mixed_publications() -> None:
    with pytest.raises(ContractViolation, match="source order"):
        partition_context_batches(
            timeline=_timeline(),
            fact_view=_fact_view(2),
            events=(_event(1), _event(0)),
            fanout_stream_sequence=11,
        )
    with pytest.raises(ContractViolation, match="fanout"):
        partition_context_batches(
            timeline=_timeline(),
            fact_view=_fact_view(2),
            events=(_event(0), _event(1, fanout=12)),
            fanout_stream_sequence=11,
        )


def test_pure_projection_batch_has_null_ordinal_range_and_no_impulse() -> None:
    parts = partition_context_batches(
        timeline=_timeline(transition_reasons=["session_started"]),
        fact_view=_fact_view(0),
        events=(),
        fanout_stream_sequence=12,
    )

    assert len(parts) == 1
    assert parts[0].external_order == ExternalOrder(12, None, None)
    assert parts[0].protected
    assert not parts[0].planning_impulse


def test_duplicate_delivery_is_exactly_once_and_conflicts_fail_closed() -> None:
    event = _event(0)
    assert deduplicate_narrative_events((event, event)) == (event,)

    changed = event.to_dict()
    changed["payload"] = {"gapSeconds": 0.3}
    with pytest.raises(ContractViolation, match="duplicate event identity"):
        deduplicate_narrative_events((event, NarrativeEvent.from_dict(changed)))
