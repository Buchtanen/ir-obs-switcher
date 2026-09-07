from __future__ import annotations

import copy

import pytest

from irswitch.contracts import (
    ContractViolation,
    FunnelIdentity,
    LineageId,
    NarrativeEvent,
    NarrativeSourceEnvelope,
    NarrativeSourceOrder,
    OccurrenceId,
    SessionRef,
)
from irswitch.events.envelope import make_envelope
from irswitch.events.narrative import NarrativeAdmissionError, adapt_accepted_event
from irswitch.events.stream import freeze_accepted_event
from irswitch.events.taxonomy import (
    narrative_policy_for_event_type,
    narrative_taxonomy_hash,
    validate_narrative_taxonomy,
)


def _event_dict() -> dict[str, object]:
    return {
        "schemaVersion": "narrative-event/2",
        "eventId": "session:42:HUNTING:7",
        "kind": "battle.pursuit",
        "phase": "started",
        "deliveryClass": "ordinary",
        "sourceEnvelope": {
            "sessionId": "session:42",
            "eventId": "session:42:HUNTING:7",
            "sequence": 7,
            "eventType": "HUNTING",
        },
        "sourceOrder": {"fanoutStreamSequence": 11, "sourceOrdinal": 2},
        "occurredMonoMs": 1234,
        "broadcastEpoch": 4,
        "streamEpoch": 1,
        "sessionRef": {"subSessionId": "42", "sessionNum": 2},
        "occurrenceId": "1:race:0",
        "lineageId": "1:race:0",
        "correlationKey": ["car:12", "car:34"],
        "factIds": ["fact:battle:1"],
        "factViewRevision": 9,
        "materialRevision": 0,
        "confidence": 0.8,
        "tapeChannel": "race.battle.closing",
        "funnel": {
            "sourceClass": "direct",
            "candidateId": "candidate:hunting:1",
            "detectorObservationId": None,
            "eventId": "session:42:HUNTING:7",
            "materialRevision": 0,
            "opportunityId": None,
            "planId": None,
            "utteranceId": None,
            "tapeChannel": "race.battle.closing",
        },
        "taxonomyHash": narrative_taxonomy_hash(),
        "payload": {"gapSeconds": 0.42, "targetCarId": "car:34"},
    }


def test_narrative_event_round_trip_is_exact_and_deterministic() -> None:
    source = _event_dict()

    event = NarrativeEvent.from_dict(source)

    assert event.to_dict() == source
    assert NarrativeEvent.from_dict(event.to_dict()) == event
    assert isinstance(event.source_envelope, NarrativeSourceEnvelope)
    assert isinstance(event.source_order, NarrativeSourceOrder)
    assert isinstance(event.funnel, FunnelIdentity)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("factIds", []),
        ("factIds", ["fact:1", "fact:1"]),
        ("correlationKey", ["car:1", "car:1"]),
        ("taxonomyHash", "CAB0"),
        ("payload", {str(index): index for index in range(33)}),
    ],
)
def test_narrative_event_rejects_invalid_closed_contract_values(field: str, value: object) -> None:
    source = _event_dict()
    source[field] = value

    with pytest.raises(ContractViolation):
        NarrativeEvent.from_dict(source)


def test_narrative_event_derives_delivery_class_and_checks_funnel_identity() -> None:
    source = _event_dict()
    source["phase"] = "ended"

    with pytest.raises(ContractViolation, match="deliveryClass"):
        NarrativeEvent.from_dict(source)

    source = _event_dict()
    funnel = dict(source["funnel"])  # type: ignore[arg-type]
    funnel["tapeChannel"] = "race.position.pass"
    source["funnel"] = funnel
    with pytest.raises(ContractViolation, match="funnel"):
        NarrativeEvent.from_dict(source)


def test_narrative_taxonomy_resolves_one_channel_and_rejects_non_narrative_ids() -> None:
    validate_narrative_taxonomy()

    hunting = narrative_policy_for_event_type("HUNTING")
    assert hunting.narrative_kind == "battle.pursuit"
    assert hunting.tape_channel == "race.battle.closing"
    assert narrative_taxonomy_hash() == (
        "sha256:7420930a571471ea89b409418bfdb6678522af648d251619fa4802b5dced7d52"
    )

    with pytest.raises(NarrativeAdmissionError, match="visual_only"):
        narrative_policy_for_event_type("CPU_TEMP_HIGH")
    with pytest.raises(NarrativeAdmissionError, match="compatibility_alias"):
        narrative_policy_for_event_type("BATTLE_LOST")
    with pytest.raises(NarrativeAdmissionError, match="unregistered"):
        narrative_policy_for_event_type("NOT_A_REAL_EVENT")


def test_adapter_preserves_v4_envelope_and_assigns_external_order() -> None:
    envelope = make_envelope(
        event_type="HUNTING",
        phase="ENTER",
        session_id="session:42",
        event_id="session:42:HUNTING:7",
        sequence=7,
        monotonic_ms=1234,
        confidence=0.8,
        correlation_id="battle:12:34",
        metrics={"gapSeconds": 0.42},
    )
    original = copy.deepcopy(envelope.to_dict())
    accepted = freeze_accepted_event(
        envelope,
        audiences=("overlay", "commentary"),
        source="event-manager",
        source_ordinal=2,
    )

    event = adapt_accepted_event(
        accepted,
        fanout_stream_sequence=11,
        broadcast_epoch=4,
        stream_epoch=1,
        session_ref=SessionRef("42", 2),
        occurrence_id=OccurrenceId.parse("1:race:0"),
        lineage_id=LineageId.parse("1:race:0"),
        fact_ids=("fact:battle:1",),
        fact_view_revision=9,
        material_revision=0,
        correlation_key=("car:12", "car:34"),
        semantic_payload={"gapSeconds": 0.42, "targetCarId": "car:34"},
        candidate_id="candidate:hunting:1",
    )

    assert envelope.to_dict() == original
    assert event.kind == "battle.pursuit"
    assert event.phase == "started"
    assert event.source_order == NarrativeSourceOrder(11, 2)
    assert event.source_envelope == NarrativeSourceEnvelope(
        "session:42", "session:42:HUNTING:7", 7, "HUNTING"
    )
    assert event.tape_channel == "race.battle.closing"


def test_adapter_never_admits_visual_only_or_unproven_events() -> None:
    envelope = make_envelope(
        event_type="CPU_TEMP_HIGH",
        session_id="session:42",
        event_id="session:42:CPU_TEMP_HIGH:8",
        sequence=8,
        correlation_id="thermal:cpu",
    )
    accepted = freeze_accepted_event(
        envelope,
        audiences=("overlay", "commentary"),
        source="event-manager",
        source_ordinal=0,
    )

    with pytest.raises(NarrativeAdmissionError, match="visual_only"):
        adapt_accepted_event(
            accepted,
            fanout_stream_sequence=12,
            broadcast_epoch=4,
            stream_epoch=1,
            session_ref=None,
            occurrence_id=None,
            lineage_id=None,
            fact_ids=("fact:thermal:1",),
            fact_view_revision=10,
            material_revision=0,
            correlation_key=("cpu",),
            semantic_payload={},
        )

    hunting = make_envelope(
        event_type="HUNTING",
        session_id="session:42",
        event_id="session:42:HUNTING:9",
        sequence=9,
        correlation_id="battle:12:34",
    )
    accepted_hunting = freeze_accepted_event(
        hunting,
        audiences=("commentary",),
        source="event-manager",
        source_ordinal=1,
    )
    with pytest.raises(ContractViolation, match="factIds"):
        adapt_accepted_event(
            accepted_hunting,
            fanout_stream_sequence=12,
            broadcast_epoch=4,
            stream_epoch=1,
            session_ref=SessionRef("42", 2),
            occurrence_id=OccurrenceId.parse("1:race:0"),
            lineage_id=LineageId.parse("1:race:0"),
            fact_ids=(),
            fact_view_revision=10,
            material_revision=0,
            correlation_key=("car:12", "car:34"),
            semantic_payload={},
        )
