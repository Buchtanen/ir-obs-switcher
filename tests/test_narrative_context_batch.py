from __future__ import annotations

import copy

import pytest

from irswitch.commentary.mailbox import NarrativeMailbox
from irswitch.contracts import (
    COMMAND_KINDS,
    ApplyContextBatch,
    ContextRevision,
    ContractViolation,
    ExternalOrder,
    NarrativeCommand,
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


def _context_command(command_id: str, *, transition: bool = False) -> NarrativeCommand:
    part = partition_context_batches(
        timeline=_timeline(transition_reasons=["session_started"] if transition else []),
        fact_view=_fact_view(1),
        events=(_event(0),),
        fanout_stream_sequence=11,
    )[0]
    return NarrativeCommand.context_batch(command_id, 2000, part)


def test_mailbox_assigns_one_total_order_across_ordinary_and_protected() -> None:
    mailbox = NarrativeMailbox()
    timer = NarrativeCommand.deadline(
        "timer:1", "LONG_SILENCE_ELAPSED", 2000, generation=1, deadline_mono_ms=2000
    )
    health = NarrativeCommand.component_health(
        "health:1",
        2000,
        component="llm",
        generation=1,
        status="unavailable",
        reason="preflight_failed",
    )

    assert mailbox.admit(timer).command.mailbox_sequence == 1
    assert mailbox.admit(health).command.mailbox_sequence == 2
    assert mailbox.dequeue().command_id == "timer:1"
    assert mailbox.dequeue().command_id == "health:1"


def test_mailbox_coalesces_only_same_deadline_generation_in_place() -> None:
    mailbox = NarrativeMailbox()
    first = NarrativeCommand.deadline(
        "timer:1", "LONG_SILENCE_ELAPSED", 2000, generation=7, deadline_mono_ms=2100
    )
    refreshed = NarrativeCommand.deadline(
        "timer:2", "LONG_SILENCE_ELAPSED", 2050, generation=7, deadline_mono_ms=2100
    )
    different = NarrativeCommand.deadline(
        "timer:3", "LONG_SILENCE_ELAPSED", 2051, generation=8, deadline_mono_ms=2200
    )

    original = mailbox.admit(first).command
    coalesced = mailbox.admit(refreshed)
    admitted = mailbox.admit(different)

    assert coalesced.reason == "coalesced"
    assert coalesced.command.mailbox_sequence == original.mailbox_sequence
    assert admitted.command.mailbox_sequence > original.mailbox_sequence
    assert len(mailbox) == 2


def test_full_ordinary_partition_rejects_manual_without_eviction() -> None:
    mailbox = NarrativeMailbox()
    for index in range(56):
        assert mailbox.admit(_context_command(f"context:{index}")).accepted

    result = mailbox.admit(
        NarrativeCommand.manual_speak("manual:1", 3000, text="Hello", admission_ordinal=1)
    )

    assert not result.accepted
    assert result.reason == "mailbox_overloaded"
    assert len(mailbox) == 56


def test_context_pressure_evicts_silence_before_context() -> None:
    mailbox = NarrativeMailbox()
    silence = NarrativeCommand.deadline(
        "timer:silence", "LONG_SILENCE_ELAPSED", 2000, generation=1, deadline_mono_ms=2000
    )
    mailbox.admit(silence)
    for index in range(55):
        mailbox.admit(_context_command(f"context:{index}"))

    result = mailbox.admit(_context_command("context:new"))

    assert result.accepted
    assert result.reason == "mailbox_evicted_update"
    assert result.evicted_command_ids == ("timer:silence",)
    assert all(item.command_id != "timer:silence" for item in mailbox.snapshot())
    assert mailbox.recovery is None


def test_lost_context_creates_visible_recovery_with_latest_projection() -> None:
    mailbox = NarrativeMailbox()
    for index in range(56):
        mailbox.admit(_context_command(f"context:{index}"))

    result = mailbox.admit(_context_command("context:new"))

    assert result.accepted
    assert result.reason == "mailbox_recovery"
    assert result.evicted_command_ids == ("context:0",)
    assert mailbox.recovery is not None
    assert mailbox.recovery.kind == "MAILBOX_RECOVERY"
    assert mailbox.recovery.payload["historyComplete"] is False
    assert mailbox.recovery.context_revision == ContextRevision(3, 9)
    assert mailbox.recovery.payload["safetyEffects"][0]["kind"] == "MAILBOX_RECOVERY"
    assert len(mailbox) == 56


def test_protected_saturation_refreshes_one_emergency_recovery_in_place() -> None:
    mailbox = NarrativeMailbox()
    for index in range(56):
        mailbox.admit(_context_command(f"context:{index}"))
    for index in range(7):
        mailbox.admit(
            NarrativeCommand.component_health(
                f"health:{index}",
                2100 + index,
                component="llm",
                generation=index,
                status="unavailable",
                reason="preflight_failed",
            )
        )

    first = mailbox.admit(
        NarrativeCommand.component_health(
            "health:overflow:1",
            2200,
            component="tts",
            generation=10,
            status="unavailable",
            reason="preflight_failed",
        )
    )
    recovery_sequence = first.command.mailbox_sequence
    second = mailbox.admit(
        NarrativeCommand.component_health(
            "health:overflow:2",
            2201,
            component="tts",
            generation=11,
            status="unavailable",
            reason="preflight_failed",
        )
    )

    assert first.reason == second.reason == "mailbox_recovery"
    assert second.command.mailbox_sequence == recovery_sequence
    assert len(second.command.payload["safetyEffects"]) == 2
    assert len(mailbox) == 64


def test_shutdown_owns_emergency_cell_and_closes_ingress() -> None:
    mailbox = NarrativeMailbox()
    for index in range(56):
        mailbox.admit(_context_command(f"context:{index}"))
    for index in range(7):
        mailbox.admit(
            NarrativeCommand.component_health(
                f"health:{index}",
                2100 + index,
                component="llm",
                generation=index,
                status="unavailable",
                reason="preflight_failed",
            )
        )
    mailbox.admit(
        NarrativeCommand.component_health(
            "health:overflow",
            2200,
            component="tts",
            generation=10,
            status="unavailable",
            reason="preflight_failed",
        )
    )

    shutdown = mailbox.admit(NarrativeCommand.shutdown("shutdown:1", 2300, "application_exit"))
    rejected = mailbox.admit(_context_command("context:late"))

    assert shutdown.accepted
    assert shutdown.command.kind == "SHUTDOWN"
    assert mailbox.recovery is None
    assert mailbox.shutdown_recovery is not None
    assert not rejected.accepted
    assert rejected.reason == "ingress_closed"


def test_command_factories_reject_noncanonical_manual_and_invalid_tape_health() -> None:
    with pytest.raises(ContractViolation, match="config payload"):
        NarrativeCommand._new(
            command_id="config:malformed",
            kind="CONFIG_UPDATE",
            enqueued_mono_ms=3000,
            token=None,
            payload={},
        )
    with pytest.raises(ContractViolation, match="admissionOrdinal"):
        NarrativeCommand.manual_speak("manual:zero", 3000, text="Hello", admission_ordinal=0)
    with pytest.raises(ContractViolation, match="normalized"):
        NarrativeCommand.manual_speak("manual:space", 3000, text=" Hello ", admission_ordinal=1)
    with pytest.raises(ContractViolation, match="loss endpoints"):
        NarrativeCommand.tape_health(
            "tape:bad",
            3000,
            recorder_generation=1,
            status="degraded",
            affected_detector_ids=(),
            first_lost_sequence=1,
            last_lost_sequence=None,
        )


def test_tape_health_has_exact_conditional_protection_and_coalescing() -> None:
    mailbox = NarrativeMailbox()
    ordinary = NarrativeCommand.tape_health(
        "tape:1",
        3000,
        recorder_generation=4,
        status="degraded",
        affected_detector_ids=("battle", "incident"),
        first_lost_sequence=10,
        last_lost_sequence=12,
    )
    refreshed = NarrativeCommand.tape_health(
        "tape:2",
        3001,
        recorder_generation=4,
        status="degraded",
        affected_detector_ids=("battle", "incident"),
        first_lost_sequence=10,
        last_lost_sequence=13,
    )
    protected = NarrativeCommand.tape_health(
        "tape:3",
        3002,
        recorder_generation=4,
        status="unavailable",
        affected_detector_ids=("battle",),
        first_lost_sequence=14,
        last_lost_sequence=14,
    )

    first = mailbox.admit(ordinary)
    second = mailbox.admit(refreshed)

    assert not ordinary.protected
    assert protected.protected
    assert second.reason == "coalesced"
    assert second.command.mailbox_sequence == first.command.mailbox_sequence


def test_atomic_control_context_bundle_is_consecutive_or_one_recovery() -> None:
    mailbox = NarrativeMailbox()
    config = NarrativeCommand.config_update(
        "config:1", 3100, valid=False, ledger=None, diagnostics=()
    )
    context = _context_command("context:bundle", transition=True)

    admitted = mailbox.admit_bundle(config, context)

    assert admitted.accepted
    assert admitted.reason == "accepted"
    assert tuple(item.mailbox_sequence for item in admitted.commands) == (1, 2)

    saturated = NarrativeMailbox()
    saturated.admit(_context_command("context:initial"))
    for index in range(6):
        saturated.admit(
            NarrativeCommand.component_health(
                f"health:{index}",
                3200 + index,
                component="llm",
                generation=index,
                status="unavailable",
                reason="preflight_failed",
            )
        )
    recovery = saturated.admit_bundle(config, context)

    assert recovery.accepted
    assert recovery.reason == "mailbox_recovery"
    assert recovery.commands == (recovery.recovery,)
    assert recovery.recovery is not None
    assert len(recovery.recovery.payload["safetyEffects"]) == 2
    assert all(
        item.command_id not in {"config:1", "context:bundle"} for item in saturated.snapshot()
    )


def test_rejected_context_never_becomes_recovery_projection() -> None:
    mailbox = NarrativeMailbox()
    initial = _context_command("context:initial")
    mailbox.admit(initial)
    for index in range(7):
        mailbox.admit(
            NarrativeCommand.component_health(
                f"health:{index}",
                3300 + index,
                component="llm",
                generation=index,
                status="unavailable",
                reason="preflight_failed",
            )
        )

    conflicting = _context_command("context:initial", transition=True)
    with pytest.raises(ContractViolation, match="duplicate commandId"):
        mailbox.admit(conflicting)
    recovery = mailbox.admit(
        NarrativeCommand.component_health(
            "health:overflow",
            3400,
            component="tts",
            generation=99,
            status="unavailable",
            reason="preflight_failed",
        )
    ).command

    assert recovery.payload["latestTimeline"] == initial.payload["timeline"]


def test_shutdown_is_idempotent_and_recovery_metadata_is_deeply_isolated() -> None:
    mailbox = NarrativeMailbox()
    for index in range(56):
        mailbox.admit(_context_command(f"context:{index}"))
    mailbox.admit(_context_command("context:new"))

    first = mailbox.admit(NarrativeCommand.shutdown("shutdown:1", 3500, "application_exit"))
    second = mailbox.admit(NarrativeCommand.shutdown("shutdown:1", 3500, "application_exit"))
    recovery = mailbox.shutdown_recovery
    assert recovery is not None
    recovery["safetyEffects"][0]["identity"] = "mutated"

    assert second.accepted
    assert second.reason == "duplicate"
    assert second.command == first.command
    assert mailbox.shutdown_recovery["safetyEffects"][0]["identity"] != "mutated"


def test_all_seventeen_command_kinds_have_validated_factories() -> None:
    result_base = {
        "schemaVersion": "realization-result/2",
        "resultId": "result:1",
        "requestId": "request:1",
        "requestOrdinal": 1,
        "dispatchGeneration": 1,
        "backend": "authored",
        "outcome": "succeeded",
        "text": "Clear sentence.",
        "textHash": "sha256:" + "1" * 64,
        "failureReason": None,
        "modelReported": None,
        "transportStartedMonoMs": 1,
        "responseStartedMonoMs": 1,
        "firstContentMonoMs": 1,
        "completedMonoMs": 2,
        "promptTokens": None,
        "completionTokens": None,
        "totalTokens": None,
        "usageSource": "unavailable",
        "finishReason": None,
        "resultHash": "sha256:" + "2" * 64,
    }
    failed_result = {
        **result_base,
        "resultId": "result:2",
        "outcome": "failed",
        "text": None,
        "textHash": None,
        "failureReason": "realization_transport",
    }

    def callback(callback_kind: str, callback_id: str) -> dict[str, object]:
        detail = {
            "playback_accepted": None,
            "completed": None,
            "interrupted": "backend_cancelled",
            "failed": "backend_audio_error",
        }[callback_kind]
        return {
            "schemaVersion": "tts-callback/2",
            "callbackId": callback_id,
            "kind": callback_kind,
            "utteranceId": "utterance:1",
            "utteranceOrdinal": 1,
            "backend": "sapi",
            "backendGeneration": 1,
            "dispatchGeneration": 1,
            "workerSequence": 1,
            "observedMonoMs": 10,
            "detailCode": detail,
        }

    context = _context_command("context:all", transition=True)
    commands = [
        context,
        NarrativeCommand.config_update("config:all", 1, valid=False, ledger=None, diagnostics=()),
        NarrativeCommand.deadline(
            "silence:all", "LONG_SILENCE_ELAPSED", 1, generation=1, deadline_mono_ms=2
        ),
        NarrativeCommand.deadline(
            "validity:all",
            "VALIDITY_DEADLINE_ELAPSED",
            1,
            generation=1,
            deadline_mono_ms=2,
        ),
        NarrativeCommand.realization_result(
            "realization:ok",
            "REALIZATION_SUCCEEDED",
            1,
            request_id="request:1",
            request_ordinal=1,
            dispatch_generation=1,
            result=result_base,
        ),
        NarrativeCommand.realization_result(
            "realization:failed",
            "REALIZATION_FAILED",
            1,
            request_id="request:1",
            request_ordinal=1,
            dispatch_generation=1,
            result=failed_result,
        ),
        NarrativeCommand.realization_deadline(
            "realization:deadline",
            1,
            request_id="request:1",
            request_ordinal=1,
            dispatch_generation=1,
            deadline_mono_ms=2,
        ),
    ]
    for command_kind, callback_kind in (
        ("PLAYBACK_ACCEPTED", "playback_accepted"),
        ("SPEECH_COMPLETED", "completed"),
        ("SPEECH_INTERRUPTED", "interrupted"),
        ("SPEECH_FAILED", "failed"),
    ):
        commands.append(
            NarrativeCommand.tts_callback(
                f"tts:{callback_kind}",
                command_kind,
                1,
                utterance_id="utterance:1",
                utterance_ordinal=1,
                backend_generation=1,
                dispatch_generation=1,
                callback=callback(callback_kind, f"callback:{callback_kind}"),
            )
        )
    commands.extend(
        (
            NarrativeCommand.speech_deadline(
                "speech:deadline",
                1,
                utterance_id="utterance:1",
                utterance_ordinal=1,
                backend_generation=1,
                dispatch_generation=1,
                stage="playback",
                deadline_mono_ms=2,
            ),
            NarrativeCommand.manual_speak(
                "manual:all", 1, text="Manual sentence.", admission_ordinal=1
            ),
            NarrativeCommand.tape_health(
                "tape:all",
                1,
                recorder_generation=1,
                status="unavailable",
                affected_detector_ids=("battle",),
                first_lost_sequence=1,
                last_lost_sequence=1,
            ),
            NarrativeCommand.component_health(
                "health:all",
                1,
                component="llm",
                generation=1,
                status="unavailable",
                reason="preflight_failed",
            ),
            NarrativeCommand.recovery(
                "recovery:all",
                1,
                latest_context=context.context_part,
                loss_first_sequence=1,
                loss_last_sequence=1,
                safety_effects=(context.safety_effect(),),
            ),
            NarrativeCommand.shutdown("shutdown:all", 1, "application_exit"),
        )
    )

    assert {command.kind for command in commands} == COMMAND_KINDS


def test_recovery_safety_effect_overflow_is_explicitly_digest_compacted() -> None:
    mailbox = NarrativeMailbox()
    mailbox.admit(_context_command("context:initial"))
    for index in range(7):
        mailbox.admit(
            NarrativeCommand.component_health(
                f"health:reserved:{index}",
                4000 + index,
                component="llm",
                generation=index,
                status="unavailable",
                reason="preflight_failed",
            )
        )
    for index in range(65):
        result = mailbox.admit(
            NarrativeCommand.component_health(
                f"health:lost:{index}",
                4100 + index,
                component="tts",
                generation=100 + index,
                status="unavailable",
                reason="preflight_failed",
            )
        )
        assert result.accepted

    effects = mailbox.recovery.payload["safetyEffects"]
    assert len(effects) == 64
    assert effects[0]["kind"] == "MAILBOX_RECOVERY"
    assert effects[0]["identity"] == "safety-effects:compacted"


def test_context_pressure_accepts_maximum_length_command_identity() -> None:
    mailbox = NarrativeMailbox()
    oldest_id = "c" * 128
    mailbox.admit(_context_command(oldest_id))
    for index in range(55):
        mailbox.admit(_context_command(f"context:{index}"))

    result = mailbox.admit(_context_command("context:new"))

    assert result.accepted
    assert result.reason == "mailbox_recovery"
    assert result.command.payload["safetyEffects"][0]["identity"] == oldest_id


def test_recovery_command_requires_projection_order_and_revision() -> None:
    with pytest.raises(ContractViolation, match="requires externalOrder/contextRevision"):
        NarrativeCommand._new(
            command_id="recovery:malformed",
            kind="MAILBOX_RECOVERY",
            enqueued_mono_ms=1,
            token=None,
            payload={
                "latestTimeline": _timeline(),
                "latestFactView": _fact_view(1),
                "lossFirstMailboxSequence": 1,
                "lossLastMailboxSequence": 1,
                "historyComplete": False,
                "safetyEffects": [
                    {
                        "kind": "MAILBOX_RECOVERY",
                        "identity": "lost:1",
                        "payloadHash": "sha256:" + "1" * 64,
                    }
                ],
            },
        )


def test_precontext_protected_saturation_fails_soft_with_explicit_reason() -> None:
    mailbox = NarrativeMailbox()
    for index in range(7):
        assert mailbox.admit(
            NarrativeCommand.component_health(
                f"health:{index}",
                5000 + index,
                component="llm",
                generation=index,
                status="unavailable",
                reason="preflight_failed",
            )
        ).accepted

    overflow = mailbox.admit(
        NarrativeCommand.component_health(
            "health:overflow",
            5010,
            component="tts",
            generation=10,
            status="unavailable",
            reason="preflight_failed",
        )
    )

    assert not overflow.accepted
    assert overflow.reason == "recovery_context_unavailable"
    assert len(mailbox) == 7
