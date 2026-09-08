"""One NDJSON NarrativeTape file: manifest, body records, trailer.

This is the #240 file-session primitive. It does not import DetectorBank,
NarrativeRuntime, or the V4 overlay HUD tape. Disk failures are fail-soft.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path
from threading import Lock
from typing import Any, BinaryIO, Literal

from irswitch.commentary.tape_queue import TapeLossAccumulator
from irswitch.contracts.primitives import (
    ContractViolation,
    Identifier,
    MonotonicMs,
    canonical_json,
)

WriterHealth = Literal["ready", "degraded"]
CloseReason = Literal[
    "rotation_size",
    "rotation_duration",
    "broadcast_ended",
    "commentary_disabled",
    "recording_disabled",
    "shutdown",
    "write_failed",
    "flush_timeout",
]

CLOSE_REASONS = frozenset(
    {
        "rotation_size",
        "rotation_duration",
        "broadcast_ended",
        "commentary_disabled",
        "recording_disabled",
        "shutdown",
        "write_failed",
        "flush_timeout",
    }
)
FRAMING_TYPES = frozenset({"manifest", "manifest_trailer"})
Sink = Callable[[bytes], None]


def narrative_tape_filename(
    process_instance_id: str, stream_epoch: int | None, file_ordinal: int
) -> str:
    """Windows-safe NDJSON name scoped to one process/stream/ordinal."""

    safe = str(Identifier(process_instance_id)).replace(":", "_")
    if stream_epoch is not None:
        if isinstance(stream_epoch, bool) or not isinstance(stream_epoch, int) or stream_epoch < 0:
            raise ContractViolation("streamEpoch must be a nonnegative int")
    if isinstance(file_ordinal, bool) or not isinstance(file_ordinal, int) or file_ordinal < 0:
        raise ContractViolation("fileOrdinal must be a nonnegative int")
    epoch = "none" if stream_epoch is None else str(stream_epoch)
    return f"narrative-{safe}-s{epoch}-f{file_ordinal:04d}.ndjson"


def _bytes_sha256(data: bytes) -> str:
    return f"sha256:{hashlib.sha256(data).hexdigest()}"


def _json_sha256(value: object) -> str:
    digest = hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


class TapeFileSession:
    """One file identity: `(processInstanceId, streamEpoch-or-null, fileOrdinal)`."""

    def __init__(self, path: Path, *, sink: Sink | None = None) -> None:
        self._path = Path(path)
        self._sink = sink
        self._fh: BinaryIO | None = None
        self._manifest: dict[str, Any] | None = None
        self._pre_trailer = bytearray()
        self._body: list[dict[str, Any]] = []
        self._loss = TapeLossAccumulator()
        self._trailer_loss: dict[str, Any] | None = None
        self._health: WriterHealth = "ready"
        self._trailer: dict[str, Any] | None = None
        self._closed = False
        self._lock = Lock()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def health(self) -> WriterHealth:
        with self._lock:
            return self._health

    def note_queue_loss(
        self,
        *,
        record_type: str,
        record_priority: str,
        recorded_mono_ms: int,
        reducer_sequence: int | None = None,
    ) -> None:
        with self._lock:
            self._loss.record(
                record_type=record_type,
                record_priority=record_priority,
                reason="tape_queue_drop",
                recorded_mono_ms=recorded_mono_ms,
                reducer_sequence=reducer_sequence,
            )

    def open(self, manifest: dict[str, Any]) -> bool:
        if not isinstance(manifest, dict):
            raise ContractViolation("tape manifest must be an object")
        if manifest.get("recordType") != "manifest":
            raise ContractViolation("tape file must start with a manifest")
        with self._lock:
            if self._manifest is not None or self._closed:
                raise ContractViolation("TapeFileSession is already open or closed")
            if not self._emit(manifest, body=False):
                self._health = "degraded"
                return False
            self._manifest = copy_manifest(manifest)
            return True

    def append(self, record: dict[str, Any]) -> bool:
        if not isinstance(record, dict):
            raise ContractViolation("tape record must be an object")
        record_type = record.get("recordType")
        if record_type in FRAMING_TYPES:
            raise ContractViolation("manifest/trailer bypass the record body")
        with self._lock:
            self._require_open()
            self._check_identity(record)
            if not self._emit(record, body=True):
                self._lose_write(record)
                return False
            return True

    def close(
        self,
        *,
        reason: str,
        recorded_mono_ms: int,
        record_id: str,
    ) -> dict[str, Any] | None:
        if reason not in CLOSE_REASONS:
            raise ContractViolation(f"unknown tape closeReason: {reason!r}")
        with self._lock:
            if self._trailer is not None:
                return self._trailer
            if self._manifest is None:
                return None
            self._flush_drop_notice(int(MonotonicMs(recorded_mono_ms)))
            if self._trailer_loss is None:
                self._trailer_loss = self._loss.take()
            trailer = self._build_trailer(
                reason=reason,
                recorded_mono_ms=int(MonotonicMs(recorded_mono_ms)),
                record_id=str(Identifier(record_id)),
            )
            self._emit(trailer, body=False)
            self._trailer = trailer
            self._closed = True
            self._close_handle()
            return trailer

    def _flush_drop_notice(self, recorded_mono_ms: int) -> None:
        loss = self._loss.snapshot()
        if loss is None:
            return
        notice = self._drop_notice(loss, recorded_mono_ms)
        if self._emit(notice, body=True):
            self._loss.take()
            self._trailer_loss = loss
            return
        self._lose_write(notice)
        self._trailer_loss = self._loss.take()

    def _drop_notice(self, loss: dict[str, Any], recorded_mono_ms: int) -> dict[str, Any]:
        manifest = self._manifest
        assert manifest is not None
        ordinal = manifest["fileOrdinal"]
        return {
            "schemaVersion": "narrative-tape-record/2",
            "recordId": f"record:drop:{ordinal}:{recorded_mono_ms}",
            "recordType": "drop_notice",
            "processInstanceId": manifest["processInstanceId"],
            "broadcastEpoch": manifest["broadcastEpoch"],
            "streamEpoch": manifest["streamEpoch"],
            "reducerSequence": None,
            "recordedMonoMs": recorded_mono_ms,
            "recordedAtUtc": None,
            "purposeChannel": manifest["enabledPurposeChannels"][0],
            "recordPriority": "critical",
            "tapeChannel": None,
            "correlationIds": [],
            "effectiveConfigHash": manifest["effectiveConfigHash"],
            "configApplySequence": manifest["configApplySequence"],
            "payloadSchemaVersion": "drop-notice/2",
            "payload": {
                "schemaVersion": "drop-notice/2",
                "noticeId": f"notice:{ordinal}:{recorded_mono_ms}",
                "loss": loss,
            },
        }

    def _build_trailer(
        self, *, reason: str, recorded_mono_ms: int, record_id: str
    ) -> dict[str, Any]:
        manifest = self._manifest
        assert manifest is not None
        record_counts = _count_rows(self._body, "recordType", "recordType")
        purpose_counts = _count_rows(self._body, "purposeChannel", "purposeChannel")
        channel_counts = _count_rows(
            [row for row in self._body if row.get("tapeChannel")],
            "tapeChannel",
            "tapeChannel",
        )
        drop_counts = _drop_counts(self._trailer_loss)
        last_reducer = _last_reducer(self._body)
        final_record = self._body[-1] if self._body else None
        return {
            "schemaVersion": "narrative-tape-record/2",
            "recordId": record_id,
            "recordType": "manifest_trailer",
            "processInstanceId": manifest["processInstanceId"],
            "broadcastEpoch": manifest["broadcastEpoch"],
            "streamEpoch": manifest["streamEpoch"],
            "reducerSequence": None,
            "recordedMonoMs": recorded_mono_ms,
            "recordedAtUtc": None,
            "purposeChannel": manifest["enabledPurposeChannels"][0],
            "recordPriority": "critical",
            "tapeChannel": None,
            "correlationIds": [],
            "effectiveConfigHash": manifest["effectiveConfigHash"],
            "configApplySequence": manifest["configApplySequence"],
            "payloadSchemaVersion": "manifest-trailer/2",
            "payload": {
                "schemaVersion": "manifest-trailer/2",
                "finalRecordHash": None if final_record is None else _json_sha256(final_record),
                "fileHash": _bytes_sha256(bytes(self._pre_trailer)),
                "recordCounts": record_counts,
                "purposeCounts": purpose_counts,
                "tapeChannelCounts": channel_counts,
                "dropCounts": drop_counts,
                "lossAccumulator": self._trailer_loss,
                "lastReducerSequence": last_reducer,
                "closeReason": reason,
                "complete": self._trailer_loss is None,
            },
        }

    def _emit(self, value: dict[str, Any], *, body: bool) -> bool:
        data = (canonical_json(value) + "\n").encode("utf-8")
        try:
            if self._sink is not None:
                self._sink(data)
            else:
                if self._fh is None:
                    self._path.parent.mkdir(parents=True, exist_ok=True)
                    self._fh = self._path.open("wb")
                self._fh.write(data)
                self._fh.flush()
        except OSError:
            self._health = "degraded"
            return False
        if body:
            self._pre_trailer.extend(data)
            self._body.append(value)
        elif self._manifest is None:
            self._pre_trailer.extend(data)
        return True

    def _check_identity(self, record: dict[str, Any]) -> None:
        manifest = self._manifest
        assert manifest is not None
        if record.get("processInstanceId") != manifest["processInstanceId"]:
            raise ContractViolation("tape record processInstanceId must match the open file")
        if record.get("streamEpoch") != manifest["streamEpoch"]:
            raise ContractViolation("tape record streamEpoch must match the open file")

    def _require_open(self) -> None:
        if self._manifest is None or self._closed:
            raise ContractViolation("TapeFileSession is not open")

    def _lose_write(self, record: dict[str, Any]) -> None:
        self._health = "degraded"
        self._loss.record(
            record_type=str(record.get("recordType") or "health_change"),
            record_priority=str(record.get("recordPriority") or "critical"),
            reason="tape_write_failed",
            recorded_mono_ms=int(record.get("recordedMonoMs") or 0),
            reducer_sequence=record.get("reducerSequence"),
        )

    def _close_handle(self) -> None:
        handle = self._fh
        self._fh = None
        if handle is not None:
            try:
                handle.close()
            except OSError:
                self._health = "degraded"


def copy_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        key: (list(value) if isinstance(value, list) else value) for key, value in manifest.items()
    }


def _count_rows(rows: list[dict[str, Any]], field: str, name: str) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in rows:
        key = row.get(field)
        if not isinstance(key, str):
            continue
        counts[key] = counts.get(key, 0) + 1
    return [{name: key, "count": count} for key, count in sorted(counts.items())]


def _drop_counts(loss: dict[str, Any] | None) -> list[dict[str, Any]]:
    if loss is None:
        return []
    counts: dict[str, int] = {}
    for bucket in loss.get("buckets") or ():
        reason = bucket["reason"]
        counts[reason] = counts.get(reason, 0) + int(bucket["count"])
    return [{"reason": reason, "count": count} for reason, count in sorted(counts.items())]


def _last_reducer(rows: list[dict[str, Any]]) -> int | None:
    sequences = [
        row["reducerSequence"]
        for row in rows
        if isinstance(row.get("reducerSequence"), int)
        and not isinstance(row["reducerSequence"], bool)
    ]
    return max(sequences) if sequences else None
