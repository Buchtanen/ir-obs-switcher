"""F27 tape-queue eviction, loss accounting and required-capture latch."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from irswitch.commentary.tape_queue import (
    CaptureHealthLatch,
    CaptureHealthNotice,
    QueuedTapeRecord,
    TapeRecordQueue,
)
from irswitch.contracts.primitives import ContractViolation
from irswitch.contracts.resources import packaged_schema_bytes

ROOT = Path(__file__).resolve().parents[1]
FROZEN_MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
SCHEMA = json.loads(packaged_schema_bytes("dto-contracts.schema.json"))
HASH_A = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
HASH_B = "sha256:bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"

_BUILDER = importlib.util.spec_from_file_location(
    "v2_build_dto_schemas", FROZEN_MACHINE / "build_dto_schemas.py"
)
assert _BUILDER is not None and _BUILDER.loader is not None
_dto_builder = importlib.util.module_from_spec(_BUILDER)
_BUILDER.loader.exec_module(_dto_builder)


def _errors(value: object) -> list[str]:
    return _dto_builder.schema_errors(value, SCHEMA, SCHEMA)


def _record(
    record_id: str,
    record_type: str,
    priority: str,
    *,
    mono_ms: int = 1000,
    reducer_sequence: int | None = None,
    required_capture: bool = False,
    detector_ids: tuple[str, ...] = (),
    apply_sequence: int | None = None,
    old_effective_hash: str | None = None,
    new_effective_hash: str | None = None,
) -> QueuedTapeRecord:
    return QueuedTapeRecord(
        record_id=record_id,
        record_type=record_type,
        record_priority=priority,
        recorded_mono_ms=mono_ms,
        reducer_sequence=reducer_sequence,
        required_capture=required_capture,
        detector_ids=detector_ids,
        apply_sequence=apply_sequence,
        old_effective_hash=old_effective_hash,
        new_effective_hash=new_effective_hash,
    )


def _fill(queue: TapeRecordQueue, *records: QueuedTapeRecord) -> None:
    for record in records:
        result = queue.admit(record)
        assert result.accepted, (record.record_id, result.reason)


def test_admit_is_fifo_within_the_same_priority() -> None:
    queue = TapeRecordQueue(capacity=4)
    _fill(
        queue,
        _record("sample:1", "feature_frame", "sample", mono_ms=1000),
        _record("sample:2", "feature_frame", "sample", mono_ms=1100),
        _record("normal:1", "fact_change", "normal", mono_ms=1200, reducer_sequence=1),
        _record("normal:2", "fact_change", "normal", mono_ms=1300, reducer_sequence=2),
    )

    assert [item.record_id for item in queue.snapshot()] == [
        "sample:1",
        "sample:2",
        "normal:1",
        "normal:2",
    ]
    assert queue.dequeue().record_id == "sample:1"
    assert queue.dequeue().record_id == "sample:2"


def test_incoming_sample_at_capacity_is_dropped() -> None:
    queue = TapeRecordQueue(capacity=2)
    _fill(
        queue,
        _record("normal:1", "fact_change", "normal", reducer_sequence=1),
        _record("normal:2", "fact_change", "normal", reducer_sequence=2),
    )

    result = queue.admit(_record("sample:new", "feature_frame", "sample", mono_ms=1500))

    assert result.accepted is False
    assert result.reason == "tape_queue_drop"
    assert [item.record_id for item in queue.snapshot()] == ["normal:1", "normal:2"]
    loss = queue.loss_snapshot()
    assert loss is not None
    assert loss["buckets"] == [
        {
            "recordType": "feature_frame",
            "recordPriority": "sample",
            "reason": "tape_queue_drop",
            "count": 1,
        }
    ]
    assert loss["firstLostMonoMs"] == 1500
    assert loss["lastLostMonoMs"] == 1500
    assert loss["firstLostReducerSequence"] is None
    assert loss["lastLostReducerSequence"] is None
    assert queue.health == "ready"


def test_normal_evicts_oldest_sample_then_drops_without_samples() -> None:
    queue = TapeRecordQueue(capacity=2)
    _fill(
        queue,
        _record("sample:old", "feature_frame", "sample", mono_ms=1000),
        _record("normal:1", "fact_change", "normal", mono_ms=1200, reducer_sequence=3),
    )

    evicted = queue.admit(
        _record("normal:2", "narrative_event", "normal", mono_ms=1300, reducer_sequence=4)
    )
    assert evicted.accepted is True
    assert evicted.reason == "evicted"
    assert [item.record_id for item in evicted.evicted] == ["sample:old"]
    assert [item.record_id for item in queue.snapshot()] == ["normal:1", "normal:2"]

    dropped = queue.admit(
        _record("normal:3", "fact_change", "normal", mono_ms=1400, reducer_sequence=5)
    )
    assert dropped.accepted is False
    assert dropped.reason == "tape_queue_drop"

    queue.dequeue()
    accepted = queue.admit(
        _record("normal:4", "fact_change", "normal", mono_ms=1500, reducer_sequence=6)
    )
    assert accepted.accepted is True
    assert [item.record_id for item in queue.snapshot()] == ["normal:2", "normal:4"]
    assert sum(bucket["count"] for bucket in queue.loss_snapshot()["buckets"]) == 2


def test_critical_evicts_sample_then_oldest_normal_in_order() -> None:
    queue = TapeRecordQueue(capacity=4)
    _fill(
        queue,
        _record("sample:1", "feature_frame", "sample", mono_ms=1000),
        _record("normal:old", "fact_change", "normal", mono_ms=1100, reducer_sequence=1),
        _record("sample:2", "feature_frame", "sample", mono_ms=1200),
        _record("normal:new", "director_decision", "normal", mono_ms=1300, reducer_sequence=2),
    )

    first = queue.admit(
        _record("speech:1", "speech_exposure", "critical", mono_ms=1400, reducer_sequence=3)
    )
    second = queue.admit(
        _record("speech:2", "speech_exposure", "critical", mono_ms=1500, reducer_sequence=4)
    )
    third = queue.admit(
        _record("gap:1", "mailbox_gap", "critical", mono_ms=1600, reducer_sequence=5)
    )

    assert first.reason == "evicted"
    assert [item.record_id for item in first.evicted] == ["sample:1"]
    assert second.reason == "evicted"
    assert [item.record_id for item in second.evicted] == ["sample:2"]
    assert third.reason == "evicted"
    assert [item.record_id for item in third.evicted] == ["normal:old"]
    assert [item.record_id for item in queue.snapshot()] == [
        "normal:new",
        "speech:1",
        "speech:2",
        "gap:1",
    ]


def test_all_critical_overflow_never_blocks_and_degrades_health() -> None:
    queue = TapeRecordQueue(capacity=2)
    _fill(
        queue,
        _record("speech:1", "speech_exposure", "critical", mono_ms=1000, reducer_sequence=8),
        _record("speech:2", "speech_exposure", "critical", mono_ms=1100, reducer_sequence=9),
    )

    overflow = queue.admit(
        _record("speech:3", "speech_exposure", "critical", mono_ms=1800, reducer_sequence=12)
    )

    assert overflow.accepted is False
    assert overflow.reason == "tape_queue_drop"
    assert overflow.evicted == ()
    assert [item.record_id for item in queue.snapshot()] == ["speech:1", "speech:2"]
    assert queue.health == "degraded"
    loss = queue.loss_snapshot()
    assert loss["firstLostReducerSequence"] == 12
    assert loss["lastLostReducerSequence"] == 12
    assert loss["buckets"] == [
        {
            "recordType": "speech_exposure",
            "recordPriority": "critical",
            "reason": "tape_queue_drop",
            "count": 1,
        }
    ]


def test_f27_sample_then_normal_eviction_then_required_capture_notice() -> None:
    latch = CaptureHealthLatch()
    queue = TapeRecordQueue(capacity=3, recorder_generation=4, health_latch=latch)
    _fill(
        queue,
        _record("sample:1", "feature_frame", "sample", mono_ms=1000),
        _record("normal:1", "fact_change", "normal", mono_ms=1100, reducer_sequence=20),
        _record("normal:2", "director_decision", "normal", mono_ms=1200, reducer_sequence=21),
    )

    normal = queue.admit(
        _record("normal:3", "narrative_event", "normal", mono_ms=1300, reducer_sequence=22)
    )
    first_critical = queue.admit(
        _record("speech:1", "speech_exposure", "critical", mono_ms=1400, reducer_sequence=23)
    )
    second_critical = queue.admit(
        _record("speech:2", "speech_exposure", "critical", mono_ms=1410, reducer_sequence=24)
    )
    third_critical = queue.admit(
        _record("speech:3", "speech_exposure", "critical", mono_ms=1420, reducer_sequence=25)
    )
    late_normal = queue.admit(
        _record("normal:late", "fact_change", "normal", mono_ms=1450, reducer_sequence=26)
    )
    speech = queue.admit(
        _record(
            "speech:terminal",
            "speech_exposure",
            "critical",
            mono_ms=1480,
            reducer_sequence=27,
        )
    )
    required = queue.admit(
        _record(
            "window:required",
            "feature_frame",
            "critical",
            mono_ms=1500,
            required_capture=True,
            detector_ids=("closing",),
        )
    )

    assert [item.record_id for item in normal.evicted] == ["sample:1"]
    assert [item.record_id for item in first_critical.evicted] == ["normal:1"]
    assert [item.record_id for item in second_critical.evicted] == ["normal:2"]
    assert [item.record_id for item in third_critical.evicted] == ["normal:3"]
    assert late_normal.accepted is False
    assert speech.accepted is False
    assert required.accepted is False
    assert required.reason == "tape_queue_drop"
    assert queue.health == "degraded"
    assert [item.record_id for item in queue.snapshot()] == [
        "speech:1",
        "speech:2",
        "speech:3",
    ]

    notice = latch.snapshot()
    assert notice == CaptureHealthNotice(
        recorder_generation=4,
        affected_detector_ids=("closing",),
        first_lost_sequence=None,
        last_lost_sequence=None,
    )
    assert required.health_notice == notice

    flushed = queue.flush_drop_notice("notice:f27")
    assert _errors(flushed) == []
    assert flushed["schemaVersion"] == "drop-notice/2"
    assert flushed["noticeId"] == "notice:f27"
    assert flushed["loss"]["firstLostMonoMs"] == 1000
    assert flushed["loss"]["lastLostMonoMs"] == 1500
    assert flushed["loss"]["firstLostReducerSequence"] == 20
    assert flushed["loss"]["lastLostReducerSequence"] == 27
    assert {
        (bucket["recordType"], bucket["recordPriority"], bucket["reason"]): bucket["count"]
        for bucket in flushed["loss"]["buckets"]
    } == {
        ("director_decision", "normal", "tape_queue_drop"): 1,
        ("fact_change", "normal", "tape_queue_drop"): 2,
        ("feature_frame", "critical", "tape_queue_drop"): 1,
        ("feature_frame", "sample", "tape_queue_drop"): 1,
        ("narrative_event", "normal", "tape_queue_drop"): 1,
        ("speech_exposure", "critical", "tape_queue_drop"): 1,
    }
    assert queue.loss_snapshot() is None


def test_required_capture_loss_merges_idempotent_latch() -> None:
    latch = CaptureHealthLatch()
    queue = TapeRecordQueue(capacity=1, recorder_generation=2, health_latch=latch)
    _fill(
        queue,
        _record("critical:held", "mailbox_gap", "critical", reducer_sequence=1),
    )

    first = queue.admit(
        _record(
            "window:1",
            "detector_observation",
            "critical",
            mono_ms=2000,
            reducer_sequence=30,
            required_capture=True,
            detector_ids=("under_pressure",),
        )
    )
    second = queue.admit(
        _record(
            "window:2",
            "detector_observation",
            "critical",
            mono_ms=2100,
            reducer_sequence=34,
            required_capture=True,
            detector_ids=("closing", "under_pressure"),
        )
    )
    older = latch.emit(
        CaptureHealthNotice(
            recorder_generation=1,
            affected_detector_ids=("stale",),
            first_lost_sequence=1,
            last_lost_sequence=2,
        )
    )

    assert first.accepted is False
    assert second.accepted is False
    assert older == latch.snapshot()
    assert latch.snapshot() == CaptureHealthNotice(
        recorder_generation=2,
        affected_detector_ids=("closing", "under_pressure"),
        first_lost_sequence=30,
        last_lost_sequence=34,
    )
    taken = latch.take()
    assert taken is not None
    assert latch.snapshot() is None


def test_config_barrier_loss_bypasses_queue_and_is_reportable() -> None:
    queue = TapeRecordQueue(capacity=1)
    _fill(queue, _record("critical:held", "health_change", "critical", reducer_sequence=7))

    queue.note_config_transition_lost(
        apply_sequence=9,
        old_effective_hash=HASH_A,
        new_effective_hash=HASH_B,
        recorded_mono_ms=1800,
    )

    assert len(queue) == 1
    assert queue.health == "degraded"
    loss = queue.loss_snapshot()
    assert loss["configTransitions"] == [
        {
            "applySequence": 9,
            "oldEffectiveHash": HASH_A,
            "newEffectiveHash": HASH_B,
        }
    ]
    assert loss["buckets"] == [
        {
            "recordType": "config_applied",
            "recordPriority": "critical",
            "reason": "config_transition_lost",
            "count": 1,
        }
    ]
    assert _errors(queue.flush_drop_notice("notice:config")) == []


def test_framing_records_never_enter_the_queue() -> None:
    queue = TapeRecordQueue(capacity=2)
    for record_type in ("drop_notice", "manifest_trailer"):
        with pytest.raises(ContractViolation, match="bypass"):
            queue.admit(_record(f"{record_type}:1", record_type, "critical"))
    assert len(queue) == 0


def test_queue_rejects_unknown_type_and_priority() -> None:
    queue = TapeRecordQueue(capacity=2)
    with pytest.raises(ContractViolation, match="recordType"):
        queue.admit(_record("bad:type", "overlay_hud", "sample"))
    with pytest.raises(ContractViolation, match="recordPriority"):
        queue.admit(_record("bad:priority", "feature_frame", "high"))
