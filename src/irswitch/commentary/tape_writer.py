"""One NDJSON NarrativeTape file: manifest, body records, trailer.

This is the #240 file-session primitive. It does not import DetectorBank,
NarrativeRuntime, or the V4 overlay HUD tape. Disk failures are fail-soft.
"""

from __future__ import annotations

import asyncio
import copy
import gzip
import hashlib
from collections.abc import Callable
from pathlib import Path
from threading import Lock
from typing import Any, BinaryIO, Literal

from irswitch.commentary.tape_queue import (
    CaptureHealthLatch,
    QueueAdmitResult,
    QueuedTapeRecord,
    TapeLossAccumulator,
    TapeRecordQueue,
)
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

    @property
    def byte_size(self) -> int:
        with self._lock:
            return len(self._pre_trailer)

    @property
    def file_hash(self) -> str | None:
        with self._lock:
            if self._trailer is None:
                return None
            return str(self._trailer["payload"]["fileHash"])

    def import_loss(self, loss: dict[str, Any]) -> None:
        with self._lock:
            self._loss.import_snapshot(loss)

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


def queued_from_record(
    record: dict[str, Any],
    *,
    required_capture: bool = False,
    detector_ids: tuple[str, ...] = (),
) -> QueuedTapeRecord:
    raw_payload = record.get("payload")
    payload: dict[str, Any] = raw_payload if isinstance(raw_payload, dict) else {}
    apply_sequence = None
    old_hash = None
    new_hash = None
    if record.get("recordType") == "config_applied":
        apply_sequence = payload.get("applySequence")
        old_hash = payload.get("oldEffectiveHash")
        new_hash = payload.get("newEffectiveHash")
    return QueuedTapeRecord(
        record_id=str(record["recordId"]),
        record_type=str(record["recordType"]),
        record_priority=str(record["recordPriority"]),
        recorded_mono_ms=int(record["recordedMonoMs"]),
        reducer_sequence=record.get("reducerSequence"),
        required_capture=required_capture,
        detector_ids=detector_ids,
        apply_sequence=apply_sequence,
        old_effective_hash=old_hash,
        new_effective_hash=new_hash,
    )


class NarrativeTapeWriter:
    """Owned cancellable writer: nonblocking submit, disk I/O only in run()."""

    def __init__(
        self,
        output_dir: Path,
        manifest: dict[str, Any],
        *,
        capacity: int = 4096,
        rotate_bytes: int = 64 * 1024 * 1024,
        keep_files: int = 8,
        compress_rotated: bool = True,
        flush_interval_ms: int = 500,
        shutdown_flush_timeout_s: float = 2.0,
        recorder_generation: int = 0,
        health_latch: CaptureHealthLatch | None = None,
        sink: Sink | None = None,
    ) -> None:
        if rotate_bytes < 1 or keep_files < 1:
            raise ContractViolation("rotate_bytes and keep_files must be positive")
        self._output_dir = Path(output_dir)
        self._manifest = copy.deepcopy(manifest)
        self._rotate_bytes = rotate_bytes
        self._keep_files = keep_files
        self._compress_rotated = compress_rotated
        self._flush_interval_s = flush_interval_ms / 1000.0
        self._shutdown_s = float(shutdown_flush_timeout_s)
        self._queue = TapeRecordQueue(
            capacity, recorder_generation=recorder_generation, health_latch=health_latch
        )
        self._envelopes: dict[str, dict[str, Any]] = {}
        self._sink = sink
        self._session: TapeFileSession | None = None
        self._task: asyncio.Task[None] | None = None
        self._wake: asyncio.Event | None = None
        self._stop = False
        self._close_reason: str = "shutdown"
        self._last_mono_ms = 0
        self._lock = Lock()

    @property
    def task(self) -> asyncio.Task[None] | None:
        return self._task

    @property
    def health_latch(self) -> CaptureHealthLatch:
        return self._queue.health_latch

    @property
    def health(self) -> WriterHealth:
        session = self._session
        if session is not None and session.health == "degraded":
            return "degraded"
        return self._queue.health

    def submit(
        self,
        record: dict[str, Any],
        *,
        required_capture: bool = False,
        detector_ids: tuple[str, ...] = (),
    ) -> QueueAdmitResult:
        queued = queued_from_record(
            record, required_capture=required_capture, detector_ids=detector_ids
        )
        result = self._queue.admit(queued)
        with self._lock:
            self._last_mono_ms = max(self._last_mono_ms, queued.recorded_mono_ms)
            if result.accepted:
                self._envelopes[queued.record_id] = record
            for evicted in result.evicted:
                self._envelopes.pop(evicted.record_id, None)
            if not result.accepted:
                self._envelopes.pop(queued.record_id, None)
        self._signal()
        return result

    def start(self) -> asyncio.Task[None]:
        if self._task is not None and not self._task.done():
            raise ContractViolation("narrative tape writer task is already running")
        self._stop = False
        self._task = asyncio.create_task(self.run(), name="narrative_tape_writer")
        return self._task

    async def run(self) -> None:
        self._wake = asyncio.Event()
        try:
            await asyncio.to_thread(self._ensure_session)
            while not self._stop:
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=self._flush_interval_s)
                except TimeoutError:
                    pass
                if self._wake is not None:
                    self._wake.clear()
                await asyncio.to_thread(self._pump)
            await asyncio.to_thread(self._pump)
            await asyncio.to_thread(self._finish, self._close_reason)
        except asyncio.CancelledError:
            self._queue.drain_lost("tape_flush_timeout")
            self._queue.mark_degraded()
            raise

    async def aclose(self, reason: str = "shutdown") -> None:
        if reason not in CLOSE_REASONS:
            raise ContractViolation(f"unknown tape closeReason: {reason!r}")
        self._close_reason = reason
        self._stop = True
        self._signal()
        task = self._task
        if task is None:
            self._ensure_session()
            self._pump()
            self._finish(reason)
            return
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=self._shutdown_s)
        except TimeoutError:
            self._queue.drain_lost("tape_flush_timeout")
            self._queue.mark_degraded()
            self._session = None
            task.cancel()
        except asyncio.CancelledError:
            self._queue.drain_lost("tape_flush_timeout")
            self._queue.mark_degraded()
            self._session = None
        except Exception:
            self._queue.drain_lost("tape_write_failed")
            self._queue.mark_degraded()
            self._finish("write_failed")

    def _signal(self) -> None:
        wake = self._wake
        if wake is not None:
            wake.set()

    def _ensure_session(self) -> None:
        if self._session is not None:
            return
        path = self._output_dir / narrative_tape_filename(
            str(self._manifest["processInstanceId"]),
            self._manifest.get("streamEpoch"),
            int(self._manifest["fileOrdinal"]),
        )
        session = TapeFileSession(path, sink=self._sink)
        if not session.open(self._manifest):
            return
        self._session = session

    def _pump(self) -> None:
        self._ensure_session()
        while True:
            item = self._queue.dequeue()
            if item is None:
                break
            with self._lock:
                envelope = self._envelopes.pop(item.record_id, None)
            if envelope is None:
                continue
            session = self._session
            if session is None or not session.append(envelope):
                continue
            if session.byte_size >= self._rotate_bytes:
                self._rotate()

    def _rotate(self) -> None:
        self._finish("rotation_size")
        self._manifest["fileOrdinal"] = int(self._manifest["fileOrdinal"]) + 1
        self._ensure_session()

    def _finish(self, reason: str) -> None:
        session = self._session
        if session is None:
            return
        loss = self._queue.loss_snapshot()
        if loss is not None:
            session.import_loss(loss)
            self._queue.flush_drop_notice(f"notice:import:{self._manifest['fileOrdinal']}")
        trailer = session.close(
            reason=reason,
            recorded_mono_ms=self._last_mono_ms or 0,
            record_id=f"record:trailer:{self._manifest['fileOrdinal']}:{reason}",
        )
        if trailer is not None:
            self._manifest["previousFileHash"] = trailer["payload"]["fileHash"]
        if reason == "rotation_size" and self._compress_rotated:
            self._compress(session.path)
        self._retain()
        self._session = None

    def _compress(self, path: Path) -> None:
        if not path.is_file():
            return
        gz_path = Path(str(path) + ".gz")
        try:
            with path.open("rb") as src, gzip.open(gz_path, "wb") as dst:
                dst.write(src.read())
            path.unlink()
        except OSError:
            return

    def _retain(self) -> None:
        files = sorted(
            list(self._output_dir.glob("narrative-*.ndjson"))
            + list(self._output_dir.glob("narrative-*.ndjson.gz"))
        )
        extra = len(files) - self._keep_files
        current = None if self._session is None else self._session.path
        for path in files:
            if extra <= 0:
                break
            if current is not None and path.resolve() == current.resolve():
                continue
            try:
                path.unlink()
                extra -= 1
            except OSError:
                continue
