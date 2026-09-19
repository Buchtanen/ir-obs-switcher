"""F44 composition coordinator: required-capture loss disables only named detectors."""

from __future__ import annotations

from pathlib import Path

from irswitch.commentary.capture_plan import compile_capture_plan
from irswitch.commentary.capture_safety import CaptureSafetyCoordinator
from irswitch.commentary.mailbox import NarrativeMailbox
from irswitch.commentary.tape_queue import CaptureHealthNotice
from irswitch.contracts import NarrativeEvent
from irswitch.contracts.command import NarrativeCommand
from irswitch.events.narrative import partition_context_batches
from irswitch.events.taxonomy import narrative_taxonomy_hash


def _required_plan():
    return compile_capture_plan(
        {
            "commentary.detectors.profile": "calibration",
            "commentary.detector.battle_ahead_v1.enabled": True,
            "commentary.detector.battle_behind_v1.enabled": True,
            "commentary.tape.enabled": True,
            "commentary.tape.channels": ("flow", "detector_tuning"),
            "commentary.tape.detector_tuning.trigger_allowlist": (
                "battle_ahead_v1",
                "battle_behind_v1",
            ),
            "commentary.tape.detector_tuning.capture_input_windows": True,
        },
        preflight_ready=True,
    )


def _timeline() -> dict:
    return {
        "schemaVersion": "timeline-snapshot/2",
        "timelineRevision": 3,
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
        "transitionReasons": ["required_capture_lost"],
    }


def _fact_view() -> dict:
    return {
        "schemaVersion": "fact-view/2",
        "viewRevision": 9,
        "createdMonoMs": 1000,
        "broadcastEpoch": 4,
        "streamEpoch": 1,
        "occurrenceId": "1:race:0",
        "lineageId": "1:race:0",
        "historyComplete": True,
        "facts": [
            {
                "schemaVersion": "atomic-fact/2",
                "factId": "fact:battle:0",
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
        ],
        "compactedSummaryRefs": [],
    }


def _event() -> NarrativeEvent:
    return NarrativeEvent.from_dict(
        {
            "schemaVersion": "narrative-event/2",
            "eventId": "event:hunting:0",
            "kind": "battle.pursuit",
            "phase": "started",
            "deliveryClass": "ordinary",
            "sourceEnvelope": {
                "sessionId": "session:42",
                "eventId": "event:hunting:0",
                "sequence": 1,
                "eventType": "HUNTING",
            },
            "sourceOrder": {"fanoutStreamSequence": 11, "sourceOrdinal": 0},
            "occurredMonoMs": 1000,
            "broadcastEpoch": 4,
            "streamEpoch": 1,
            "sessionRef": {"subSessionId": "42", "sessionNum": 2},
            "occurrenceId": "1:race:0",
            "lineageId": "1:race:0",
            "correlationKey": ["car:12", "car:34"],
            "factIds": ["fact:battle:0"],
            "factViewRevision": 9,
            "materialRevision": 0,
            "confidence": 0.8,
            "tapeChannel": "race.battle.closing",
            "funnel": {
                "sourceClass": "direct",
                "candidateId": "candidate:hunting:0",
                "detectorObservationId": None,
                "eventId": "event:hunting:0",
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


def _context(command_id: str) -> NarrativeCommand:
    part = partition_context_batches(
        timeline=_timeline(),
        fact_view=_fact_view(),
        events=(_event(),),
        fanout_stream_sequence=11,
    )[0]
    return NarrativeCommand.context_batch(command_id, 2000, part)


class _Bank:
    def __init__(self) -> None:
        self.disabled: list[tuple[tuple[str, ...], str]] = []

    def disable_for_run(self, detector_ids: tuple[str, ...], reason: str) -> tuple[str, ...]:
        self.disabled.append((detector_ids, reason))
        return detector_ids


class _Closer:
    def __init__(self) -> None:
        self.closed: list[tuple[str, ...]] = []

    def close_required_capture_lost(self, detector_ids: tuple[str, ...]) -> None:
        self.closed.append(detector_ids)


def _coordinator(
    mailbox: NarrativeMailbox | None = None,
) -> tuple[CaptureSafetyCoordinator, _Bank, _Closer, NarrativeMailbox]:
    bank = _Bank()
    closer = _Closer()
    box = mailbox or NarrativeMailbox()
    coordinator = CaptureSafetyCoordinator(
        plan=_required_plan(),
        recorder_generation=4,
        detector_control=bank,
        truth_closer=closer,
        mailbox=box,
    )
    return coordinator, bank, closer, box


def test_required_loss_disables_only_named_experimental_detectors() -> None:
    coordinator, bank, closer, mailbox = _coordinator()
    notice = CaptureHealthNotice(
        recorder_generation=4,
        affected_detector_ids=("battle_ahead_v1", "direct_flag_v1"),
        first_lost_sequence=10,
        last_lost_sequence=12,
    )

    effect = coordinator.apply_notice(
        notice, command_id="tape:health:1", enqueued_mono_ms=2000, context=_context("ctx:1")
    )

    assert effect.applied is True
    assert effect.disabled_detector_ids == ("battle_ahead_v1",)
    assert bank.disabled == [(("battle_ahead_v1",), "required_capture_lost")]
    assert closer.closed == [("battle_ahead_v1",)]
    assert coordinator.disabled_for_run == ("battle_ahead_v1",)
    first = mailbox.dequeue()
    second = mailbox.dequeue()
    assert first is not None and first.kind == "TAPE_HEALTH_CHANGED"
    assert first.payload["status"] == "unavailable"
    assert first.payload["affectedDetectorIds"] == ["battle_ahead_v1", "direct_flag_v1"]
    assert second is not None and second.kind == "APPLY_CONTEXT_BATCH"
    assert mailbox.dequeue() is None


def test_duplicate_and_stale_notices_are_noop_and_repair_cannot_reenable() -> None:
    coordinator, bank, closer, _mailbox = _coordinator()
    notice = CaptureHealthNotice(
        recorder_generation=4,
        affected_detector_ids=("battle_ahead_v1",),
        first_lost_sequence=1,
        last_lost_sequence=1,
    )
    first = coordinator.apply_notice(
        notice, command_id="tape:health:1", enqueued_mono_ms=2000, context=_context("ctx:1")
    )
    duplicate = coordinator.apply_notice(
        notice, command_id="tape:health:2", enqueued_mono_ms=2100, context=_context("ctx:2")
    )
    stale = coordinator.apply_notice(
        CaptureHealthNotice(3, ("battle_ahead_v1",), 1, 1),
        command_id="tape:health:3",
        enqueued_mono_ms=2200,
        context=_context("ctx:3"),
    )
    coordinator.note_recorder_ready()

    assert first.applied is True
    assert duplicate.applied is False
    assert duplicate.reason == "duplicate"
    assert stale.applied is False
    assert stale.reason == "stale_generation"
    assert bank.disabled == [(("battle_ahead_v1",), "required_capture_lost")]
    assert closer.closed == [("battle_ahead_v1",)]
    assert coordinator.disabled_for_run == ("battle_ahead_v1",)


def test_next_stream_plus_preflight_can_admit_the_detector_again() -> None:
    coordinator, _bank, _closer, mailbox = _coordinator()
    coordinator.apply_notice(
        CaptureHealthNotice(4, ("battle_ahead_v1",), 1, 1),
        command_id="tape:health:1",
        enqueued_mono_ms=2000,
        context=_context("ctx:1"),
    )
    coordinator.begin_stream(_required_plan(), recorder_generation=5)
    effect = coordinator.apply_notice(
        CaptureHealthNotice(5, ("battle_ahead_v1",), 8, 8),
        command_id="tape:health:2",
        enqueued_mono_ms=3000,
        context=_context("ctx:2"),
    )

    assert coordinator.disabled_for_run == ("battle_ahead_v1",)
    assert effect.applied is True
    assert mailbox.dequeue() is not None
    assert mailbox.dequeue() is not None
    assert mailbox.dequeue() is not None
    assert mailbox.dequeue() is not None


def test_coordinator_does_not_import_runtime_or_detector_bank() -> None:
    source = Path(__file__).resolve().parents[1] / "src/irswitch/commentary/capture_safety.py"
    imports = [
        line
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.startswith("from ") or line.startswith("import ")
    ]
    joined = "\n".join(imports)
    assert "NarrativeRuntime" not in joined
    assert "DetectorBank" not in joined
    assert "overlay.tape" not in joined
