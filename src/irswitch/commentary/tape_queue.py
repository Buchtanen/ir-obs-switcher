"""Bounded NarrativeTape record queue and out-of-queue loss latch.

This is the #240 writer admission primitive. It never performs disk I/O, never
imports DetectorBank or NarrativeRuntime, and is not the V4 overlay HUD tape.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any, Literal

from irswitch.contracts.primitives import (
    ContractViolation,
    Identifier,
    MonotonicMs,
    Sha256Hash,
)

RecordPriority = Literal["sample", "normal", "critical"]
WriterHealth = Literal["ready", "degraded"]
LossReason = Literal[
    "tape_queue_drop",
    "tape_write_failed",
    "tape_flush_timeout",
    "config_transition_lost",
]

QUEUED_RECORD_TYPES = frozenset(
    {
        "context_applied",
        "feature_frame",
        "detector_observation",
        "event_candidate",
        "narrative_event",
        "fact_change",
        "episode_change",
        "opportunity_change",
        "director_decision",
        "llm_attempt",
        "speech_exposure",
        "config_applied",
        "health_change",
        "mailbox_gap",
    }
)
FRAMING_RECORD_TYPES = frozenset({"drop_notice", "manifest_trailer"})
RECORD_PRIORITIES = frozenset({"sample", "normal", "critical"})
LOSS_REASONS = frozenset(
    {
        "tape_queue_drop",
        "tape_write_failed",
        "tape_flush_timeout",
        "config_transition_lost",
    }
)
DEFAULT_CAPACITY = 4096
MAX_LOSS_BUCKETS = 192
MAX_CONFIG_TRANSITIONS = 128


def _nonnegative(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ContractViolation(f"{field} must be a nonnegative int")
    return value


def _positive(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ContractViolation(f"{field} must be a positive int")
    return value


@dataclass(frozen=True, slots=True)
class CaptureHealthNotice:
    recorder_generation: int
    affected_detector_ids: tuple[str, ...]
    first_lost_sequence: int | None = None
    last_lost_sequence: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "recorder_generation",
            _nonnegative(self.recorder_generation, "recorderGeneration"),
        )
        detectors = tuple(sorted({str(Identifier(item)) for item in self.affected_detector_ids}))
        if len(detectors) > 128:
            raise ContractViolation("affected detector ids must contain 0..128 items")
        object.__setattr__(self, "affected_detector_ids", detectors)
        first = self.first_lost_sequence
        last = self.last_lost_sequence
        if (first is None) != (last is None):
            raise ContractViolation("capture health loss endpoints must both be present or null")
        if first is not None and last is not None:
            first = _nonnegative(first, "firstLostSequence")
            last = _nonnegative(last, "lastLostSequence")
            if last < first:
                raise ContractViolation("capture health loss endpoints must be ordered")
            object.__setattr__(self, "first_lost_sequence", first)
            object.__setattr__(self, "last_lost_sequence", last)


@dataclass(frozen=True, slots=True)
class QueuedTapeRecord:
    record_id: str
    record_type: str
    record_priority: str
    recorded_mono_ms: int
    reducer_sequence: int | None = None
    required_capture: bool = False
    detector_ids: tuple[str, ...] = ()
    apply_sequence: int | None = None
    old_effective_hash: str | None = None
    new_effective_hash: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "record_id", str(Identifier(self.record_id)))
        if self.record_type in FRAMING_RECORD_TYPES:
            raise ContractViolation("manifest/trailer and drop_notice bypass the record queue")
        if self.record_type not in QUEUED_RECORD_TYPES:
            raise ContractViolation(f"unknown tape recordType: {self.record_type!r}")
        if self.record_priority not in RECORD_PRIORITIES:
            raise ContractViolation(f"unknown tape recordPriority: {self.record_priority!r}")
        object.__setattr__(self, "recorded_mono_ms", int(MonotonicMs(self.recorded_mono_ms)))
        if self.reducer_sequence is not None:
            object.__setattr__(
                self, "reducer_sequence", _nonnegative(self.reducer_sequence, "reducerSequence")
            )
        if not isinstance(self.required_capture, bool):
            raise ContractViolation("required_capture must be a bool")
        detectors = tuple(str(Identifier(item)) for item in self.detector_ids)
        if len(set(detectors)) != len(detectors):
            raise ContractViolation("detector ids must be unique")
        object.__setattr__(self, "detector_ids", detectors)
        if self.apply_sequence is not None:
            object.__setattr__(
                self, "apply_sequence", _positive(self.apply_sequence, "applySequence")
            )
        if self.old_effective_hash is not None:
            object.__setattr__(self, "old_effective_hash", str(Sha256Hash(self.old_effective_hash)))
        if self.new_effective_hash is not None:
            object.__setattr__(self, "new_effective_hash", str(Sha256Hash(self.new_effective_hash)))


@dataclass(frozen=True, slots=True)
class QueueAdmitResult:
    accepted: bool
    reason: str
    record: QueuedTapeRecord
    evicted: tuple[QueuedTapeRecord, ...] = ()
    health_notice: CaptureHealthNotice | None = None


class CaptureHealthLatch:
    """Out-of-queue idempotent required-capture notice. Survives queue saturation."""

    def __init__(self) -> None:
        self._notice: CaptureHealthNotice | None = None
        self._lock = Lock()

    def snapshot(self) -> CaptureHealthNotice | None:
        with self._lock:
            return self._notice

    def take(self) -> CaptureHealthNotice | None:
        with self._lock:
            notice = self._notice
            self._notice = None
            return notice

    def emit(self, notice: CaptureHealthNotice) -> CaptureHealthNotice:
        if not isinstance(notice, CaptureHealthNotice):
            raise ContractViolation("CaptureHealthLatch accepts only CaptureHealthNotice")
        with self._lock:
            current = self._notice
            if current is None or notice.recorder_generation > current.recorder_generation:
                self._notice = notice
                return notice
            if notice.recorder_generation < current.recorder_generation:
                return current
            merged = CaptureHealthNotice(
                recorder_generation=current.recorder_generation,
                affected_detector_ids=current.affected_detector_ids + notice.affected_detector_ids,
                first_lost_sequence=_merge_first(
                    current.first_lost_sequence, notice.first_lost_sequence
                ),
                last_lost_sequence=_merge_last(
                    current.last_lost_sequence, notice.last_lost_sequence
                ),
            )
            self._notice = merged
            return merged


class TapeLossAccumulator:
    """Registry-bounded out-of-queue loss counts and first/last ranges."""

    def __init__(self) -> None:
        self._buckets: dict[tuple[str, str, str], int] = {}
        self._first_lost_mono_ms: int | None = None
        self._last_lost_mono_ms: int | None = None
        self._first_lost_reducer: int | None = None
        self._last_lost_reducer: int | None = None
        self._config_transitions: dict[int, tuple[str, str]] = {}

    def __bool__(self) -> bool:
        return bool(self._buckets)

    def record(
        self,
        *,
        record_type: str,
        record_priority: str,
        reason: str,
        recorded_mono_ms: int,
        reducer_sequence: int | None = None,
        apply_sequence: int | None = None,
        old_effective_hash: str | None = None,
        new_effective_hash: str | None = None,
    ) -> None:
        if record_type not in QUEUED_RECORD_TYPES and record_type not in FRAMING_RECORD_TYPES:
            raise ContractViolation(f"unknown tape recordType: {record_type!r}")
        if record_priority not in RECORD_PRIORITIES:
            raise ContractViolation(f"unknown tape recordPriority: {record_priority!r}")
        if reason not in LOSS_REASONS:
            raise ContractViolation(f"unknown tape loss reason: {reason!r}")
        key = (record_type, record_priority, reason)
        if key not in self._buckets and len(self._buckets) >= MAX_LOSS_BUCKETS:
            raise ContractViolation("TapeLossAccumulator bucket bound exceeded")
        self._buckets[key] = self._buckets.get(key, 0) + 1
        mono_ms = int(MonotonicMs(recorded_mono_ms))
        self._first_lost_mono_ms = (
            mono_ms if self._first_lost_mono_ms is None else min(self._first_lost_mono_ms, mono_ms)
        )
        self._last_lost_mono_ms = (
            mono_ms if self._last_lost_mono_ms is None else max(self._last_lost_mono_ms, mono_ms)
        )
        if reducer_sequence is not None:
            sequence = _nonnegative(reducer_sequence, "reducerSequence")
            self._first_lost_reducer = (
                sequence
                if self._first_lost_reducer is None
                else min(self._first_lost_reducer, sequence)
            )
            self._last_lost_reducer = (
                sequence
                if self._last_lost_reducer is None
                else max(self._last_lost_reducer, sequence)
            )
        if apply_sequence is not None:
            if old_effective_hash is None or new_effective_hash is None:
                raise ContractViolation("config transition loss requires both effective hashes")
            self._add_transition(apply_sequence, old_effective_hash, new_effective_hash)

    def snapshot(self) -> dict[str, Any] | None:
        if not self._buckets:
            return None
        return {
            "buckets": [
                {
                    "recordType": record_type,
                    "recordPriority": record_priority,
                    "reason": reason,
                    "count": count,
                }
                for (record_type, record_priority, reason), count in sorted(self._buckets.items())
            ],
            "firstLostMonoMs": self._first_lost_mono_ms,
            "lastLostMonoMs": self._last_lost_mono_ms,
            "firstLostReducerSequence": self._first_lost_reducer,
            "lastLostReducerSequence": self._last_lost_reducer,
            "configTransitions": [
                {
                    "applySequence": apply_sequence,
                    "oldEffectiveHash": old_hash,
                    "newEffectiveHash": new_hash,
                }
                for apply_sequence, (old_hash, new_hash) in sorted(self._config_transitions.items())
            ],
        }

    def take(self) -> dict[str, Any] | None:
        payload = self.snapshot()
        self._buckets.clear()
        self._first_lost_mono_ms = None
        self._last_lost_mono_ms = None
        self._first_lost_reducer = None
        self._last_lost_reducer = None
        self._config_transitions.clear()
        return payload

    def import_snapshot(self, loss: dict[str, Any]) -> None:
        for bucket in loss.get("buckets") or ():
            self.record(
                record_type=str(bucket["recordType"]),
                record_priority=str(bucket["recordPriority"]),
                reason=str(bucket["reason"]),
                recorded_mono_ms=int(loss["firstLostMonoMs"]),
                reducer_sequence=loss.get("firstLostReducerSequence"),
            )
            extra = int(bucket["count"]) - 1
            if extra > 0:
                key = (
                    str(bucket["recordType"]),
                    str(bucket["recordPriority"]),
                    str(bucket["reason"]),
                )
                self._buckets[key] = self._buckets.get(key, 0) + extra
        if loss.get("lastLostMonoMs") is not None:
            self._last_lost_mono_ms = (
                int(loss["lastLostMonoMs"])
                if self._last_lost_mono_ms is None
                else max(self._last_lost_mono_ms, int(loss["lastLostMonoMs"]))
            )
        if loss.get("lastLostReducerSequence") is not None:
            last = int(loss["lastLostReducerSequence"])
            self._last_lost_reducer = (
                last if self._last_lost_reducer is None else max(self._last_lost_reducer, last)
            )
        for row in loss.get("configTransitions") or ():
            self._add_transition(
                int(row["applySequence"]),
                str(row["oldEffectiveHash"]),
                str(row["newEffectiveHash"]),
            )

    def _add_transition(self, apply_sequence: int, old_hash: str, new_hash: str) -> None:
        sequence = _positive(apply_sequence, "applySequence")
        row = (str(Sha256Hash(old_hash)), str(Sha256Hash(new_hash)))
        existing = self._config_transitions.get(sequence)
        if existing is not None:
            if existing != row:
                raise ContractViolation("duplicate applySequence carries conflicting hashes")
            return
        if len(self._config_transitions) >= MAX_CONFIG_TRANSITIONS:
            return
        self._config_transitions[sequence] = row


class TapeRecordQueue:
    """Nonblocking bounded record queue with exact sample-then-normal eviction."""

    def __init__(
        self,
        capacity: int = DEFAULT_CAPACITY,
        *,
        recorder_generation: int = 0,
        health_latch: CaptureHealthLatch | None = None,
    ) -> None:
        if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
            raise ContractViolation("tape writer capacity must be a positive int")
        self._capacity = capacity
        self._recorder_generation = _nonnegative(recorder_generation, "recorderGeneration")
        self._items: list[QueuedTapeRecord] = []
        self._loss = TapeLossAccumulator()
        self._health: WriterHealth = "ready"
        self._health_latch = health_latch if health_latch is not None else CaptureHealthLatch()
        self._lock = Lock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)

    @property
    def health(self) -> WriterHealth:
        with self._lock:
            return self._health

    @property
    def health_latch(self) -> CaptureHealthLatch:
        return self._health_latch

    def snapshot(self) -> tuple[QueuedTapeRecord, ...]:
        with self._lock:
            return tuple(self._items)

    def loss_snapshot(self) -> dict[str, Any] | None:
        with self._lock:
            return self._loss.snapshot()

    def dequeue(self) -> QueuedTapeRecord | None:
        with self._lock:
            if not self._items:
                return None
            return self._items.pop(0)

    def mark_degraded(self) -> None:
        with self._lock:
            self._health = "degraded"

    def drain_lost(self, reason: LossReason) -> tuple[QueuedTapeRecord, ...]:
        """Move every queued record into the accumulator. Never blocks."""

        if reason not in LOSS_REASONS:
            raise ContractViolation(f"unknown tape loss reason: {reason!r}")
        with self._lock:
            items = tuple(self._items)
            self._items.clear()
            for item in items:
                self._lose(item, reason)
            return items

    def flush_drop_notice(self, notice_id: str) -> dict[str, Any] | None:
        notice = str(Identifier(notice_id))
        with self._lock:
            loss = self._loss.take()
        if loss is None:
            return None
        return {"schemaVersion": "drop-notice/2", "noticeId": notice, "loss": loss}

    def note_config_transition_lost(
        self,
        *,
        apply_sequence: int,
        old_effective_hash: str,
        new_effective_hash: str,
        recorded_mono_ms: int,
    ) -> None:
        with self._lock:
            self._loss.record(
                record_type="config_applied",
                record_priority="critical",
                reason="config_transition_lost",
                recorded_mono_ms=recorded_mono_ms,
                apply_sequence=apply_sequence,
                old_effective_hash=old_effective_hash,
                new_effective_hash=new_effective_hash,
            )
            self._health = "degraded"

    def admit(self, record: QueuedTapeRecord) -> QueueAdmitResult:
        if not isinstance(record, QueuedTapeRecord):
            raise ContractViolation("TapeRecordQueue accepts only QueuedTapeRecord")
        with self._lock:
            if len(self._items) < self._capacity:
                self._items.append(record)
                return QueueAdmitResult(True, "accepted", record)
            if record.record_priority == "sample":
                notice = self._lose(record, "tape_queue_drop")
                return QueueAdmitResult(False, "tape_queue_drop", record, health_notice=notice)
            victim = self._oldest("sample")
            if victim is None and record.record_priority == "critical":
                victim = self._oldest("normal")
            if victim is None:
                if record.record_priority == "critical":
                    self._health = "degraded"
                notice = self._lose(record, "tape_queue_drop")
                return QueueAdmitResult(False, "tape_queue_drop", record, health_notice=notice)
            self._items.remove(victim)
            notice = self._lose(victim, "tape_queue_drop")
            self._items.append(record)
            return QueueAdmitResult(True, "evicted", record, (victim,), health_notice=notice)

    def _oldest(self, priority: RecordPriority) -> QueuedTapeRecord | None:
        return next((item for item in self._items if item.record_priority == priority), None)

    def _lose(self, record: QueuedTapeRecord, reason: LossReason) -> CaptureHealthNotice | None:
        self._loss.record(
            record_type=record.record_type,
            record_priority=record.record_priority,
            reason=reason,
            recorded_mono_ms=record.recorded_mono_ms,
            reducer_sequence=record.reducer_sequence,
            apply_sequence=record.apply_sequence,
            old_effective_hash=record.old_effective_hash,
            new_effective_hash=record.new_effective_hash,
        )
        if record.record_priority == "critical" and reason != "tape_queue_drop":
            self._health = "degraded"
        if not record.required_capture:
            return None
        return self._health_latch.emit(
            CaptureHealthNotice(
                recorder_generation=self._recorder_generation,
                affected_detector_ids=record.detector_ids,
                first_lost_sequence=record.reducer_sequence,
                last_lost_sequence=record.reducer_sequence,
            )
        )


def _merge_first(current: int | None, incoming: int | None) -> int | None:
    if current is None:
        return incoming
    if incoming is None:
        return current
    return min(current, incoming)


def _merge_last(current: int | None, incoming: int | None) -> int | None:
    if current is None:
        return incoming
    if incoming is None:
        return current
    return max(current, incoming)
