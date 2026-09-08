"""NDJSON TapeFileSession identity, hashing and fail-soft close."""

from __future__ import annotations

import asyncio
import contextlib
import copy
import gzip
import hashlib
import importlib.util
import json
import threading
from pathlib import Path

import pytest

from irswitch.commentary.tape_queue import CaptureHealthLatch
from irswitch.commentary.tape_safety import tape_health_command
from irswitch.commentary.tape_writer import (
    NarrativeTapeWriter,
    TapeFileSession,
    narrative_tape_filename,
)
from irswitch.contracts.primitives import ContractViolation, canonical_sha256
from irswitch.contracts.resources import packaged_schema_bytes

ROOT = Path(__file__).resolve().parents[1]
FROZEN_MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
SCHEMA = json.loads(packaged_schema_bytes("dto-contracts.schema.json"))
GOLDENS = json.loads((FROZEN_MACHINE / "dto-schema-goldens.json").read_text(encoding="utf-8"))

_BUILDER = importlib.util.spec_from_file_location(
    "v2_build_dto_schemas", FROZEN_MACHINE / "build_dto_schemas.py"
)
assert _BUILDER is not None and _BUILDER.loader is not None
_dto_builder = importlib.util.module_from_spec(_BUILDER)
_BUILDER.loader.exec_module(_dto_builder)


def _errors(value: object) -> list[str]:
    return _dto_builder.schema_errors(value, SCHEMA, SCHEMA)


def _golden(fixture_id: str) -> dict:
    for row in GOLDENS["valid"]:
        if row["id"] == fixture_id:
            return copy.deepcopy(row["value"])
    raise AssertionError(f"missing valid golden {fixture_id}")


def _lines(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_bytes().splitlines()]


def _file_hash(path: Path, *, exclude_trailer: bool = True) -> str:
    raw = path.read_bytes()
    if exclude_trailer:
        raw = raw[: raw.rfind(b"\n", 0, len(raw) - 1) + 1]
    digest = hashlib.sha256(raw).hexdigest()
    return f"sha256:{digest}"


def test_filename_is_windows_safe_and_epoch_scoped() -> None:
    assert narrative_tape_filename("process:1", 7, 0) == "narrative-process_1-s7-f0000.ndjson"
    assert narrative_tape_filename("process:1", None, 2) == "narrative-process_1-snone-f0002.ndjson"


def test_session_writes_manifest_record_and_complete_trailer(tmp_path: Path) -> None:
    manifest = _golden("tape-manifest-framing")
    record = _golden("tape-health-record")
    path = tmp_path / narrative_tape_filename("process:1", 7, 0)
    session = TapeFileSession(path)

    assert session.open(manifest) is True
    assert session.append(record) is True
    trailer = session.close(reason="shutdown", recorded_mono_ms=2000, record_id="record:trailer:1")

    assert trailer is not None
    rows = _lines(path)
    assert len(rows) == 3
    assert rows[0]["recordType"] == "manifest"
    assert rows[1]["recordId"] == "record:1"
    assert rows[2]["recordType"] == "manifest_trailer"
    assert _errors(rows[0]) == []
    assert _errors(rows[1]) == []
    assert _errors(rows[2]) == []
    assert rows[2]["payload"]["complete"] is True
    assert rows[2]["payload"]["lossAccumulator"] is None
    assert rows[2]["payload"]["closeReason"] == "shutdown"
    assert rows[2]["payload"]["lastReducerSequence"] == 9
    assert rows[2]["payload"]["finalRecordHash"] == canonical_sha256(record)
    assert rows[2]["payload"]["fileHash"] == _file_hash(path)
    assert rows[2]["payload"]["fileHash"] != canonical_sha256(rows[2])
    assert b"\r\n" not in path.read_bytes()


def test_session_rejects_a_second_stream_epoch(tmp_path: Path) -> None:
    session = TapeFileSession(tmp_path / "one.ndjson")
    assert session.open(_golden("tape-manifest-framing")) is True
    foreign = _golden("tape-health-record")
    foreign["streamEpoch"] = 8
    with pytest.raises(ContractViolation, match="streamEpoch"):
        session.append(foreign)
    assert session.append(_golden("tape-health-record")) is True


def test_reenable_opens_a_new_file_for_the_same_broadcast(tmp_path: Path) -> None:
    first_manifest = _golden("tape-manifest-framing")
    second_manifest = _golden("tape-manifest-framing")
    second_manifest["streamEpoch"] = 8
    second_manifest["fileOrdinal"] = 0
    second_manifest["historyComplete"] = False
    first = _golden("tape-health-record")
    second = _golden("tape-health-record")
    second["streamEpoch"] = 8
    second["recordId"] = "record:2"
    first_path = tmp_path / narrative_tape_filename("process:1", 7, 0)
    second_path = tmp_path / narrative_tape_filename("process:1", 8, 0)

    closed = TapeFileSession(first_path)
    closed.open(first_manifest)
    closed.append(first)
    closed.close(reason="commentary_disabled", recorded_mono_ms=3000, record_id="record:trailer:7")

    reopened = TapeFileSession(second_path)
    reopened.open(second_manifest)
    reopened.append(second)
    reopened.close(reason="shutdown", recorded_mono_ms=4000, record_id="record:trailer:8")

    assert first_path != second_path
    assert _lines(first_path)[0]["streamEpoch"] == 7
    assert _lines(second_path)[0]["streamEpoch"] == 8
    assert _lines(first_path)[0]["broadcastEpoch"] == 4
    assert _lines(second_path)[0]["broadcastEpoch"] == 4
    assert _lines(first_path)[-1]["payload"]["closeReason"] == "commentary_disabled"
    assert _file_hash(first_path) != _file_hash(second_path)


def test_empty_body_has_null_final_hash_and_is_complete(tmp_path: Path) -> None:
    path = tmp_path / "empty.ndjson"
    session = TapeFileSession(path)
    session.open(_golden("tape-manifest-framing"))
    trailer = session.close(
        reason="recording_disabled", recorded_mono_ms=1100, record_id="record:t"
    )

    assert trailer["payload"]["finalRecordHash"] is None
    assert trailer["payload"]["complete"] is True
    assert trailer["payload"]["lastReducerSequence"] is None
    assert trailer["payload"]["recordCounts"] == []
    assert _errors(trailer) == []
    assert len(_lines(path)) == 2


def test_pending_loss_is_written_as_drop_notice_and_keeps_file_incomplete(
    tmp_path: Path,
) -> None:
    path = tmp_path / "loss.ndjson"
    session = TapeFileSession(path)
    session.open(_golden("tape-manifest-framing"))
    session.note_queue_loss(
        record_type="feature_frame",
        record_priority="sample",
        recorded_mono_ms=1000,
    )
    trailer = session.close(reason="shutdown", recorded_mono_ms=1900, record_id="record:trailer:1")

    rows = _lines(path)
    assert [row["recordType"] for row in rows] == ["manifest", "drop_notice", "manifest_trailer"]
    assert rows[1]["recordPriority"] == "critical"
    assert rows[1]["reducerSequence"] is None
    assert _errors(rows[1]) == []
    assert rows[2]["payload"]["complete"] is False
    assert rows[2]["payload"]["lossAccumulator"]["buckets"][0]["reason"] == "tape_queue_drop"
    assert rows[2]["payload"]["fileHash"] == _file_hash(path)
    assert "drop_notice" in {row["recordType"] for row in rows[2]["payload"]["recordCounts"]}
    assert trailer["payload"]["complete"] is False


def test_write_failure_is_fail_soft_and_observable(tmp_path: Path) -> None:
    written: list[bytes] = []

    def sink(data: bytes) -> None:
        written.append(data)
        if len(written) > 1:
            raise OSError("disk full")

    session = TapeFileSession(tmp_path / "fail.ndjson", sink=sink)
    assert session.open(_golden("tape-manifest-framing")) is True
    assert session.append(_golden("tape-health-record")) is False
    assert session.health == "degraded"
    trailer = session.close(reason="write_failed", recorded_mono_ms=2100, record_id="record:t")
    assert trailer is not None
    assert session.health == "degraded"
    assert trailer["payload"]["complete"] is False
    assert trailer["payload"]["closeReason"] == "write_failed"
    reasons = {row["reason"] for row in trailer["payload"]["dropCounts"]}
    assert "tape_write_failed" in reasons


def test_framing_records_cannot_be_appended(tmp_path: Path) -> None:
    session = TapeFileSession(tmp_path / "frame.ndjson")
    session.open(_golden("tape-manifest-framing"))
    with pytest.raises(ContractViolation, match="bypass"):
        session.append(_golden("tape-trailer-record"))
    with pytest.raises(ContractViolation, match="bypass"):
        session.append(_golden("tape-manifest-framing"))


def _health(record_id: str, *, mono_ms: int = 1200, stream_epoch: int = 7) -> dict:
    record = _golden("tape-health-record")
    record["recordId"] = record_id
    record["recordedMonoMs"] = mono_ms
    record["streamEpoch"] = stream_epoch
    return record


def _writer(tmp_path: Path, **overrides: object) -> NarrativeTapeWriter:
    settings = {
        "output_dir": tmp_path,
        "manifest": _golden("tape-manifest-framing"),
        "capacity": 8,
        "rotate_bytes": 1024 * 1024,
        "keep_files": 8,
        "compress_rotated": True,
        "flush_interval_ms": 50,
        "shutdown_flush_timeout_s": 1.0,
        "recorder_generation": 4,
    }
    settings.update(overrides)
    return NarrativeTapeWriter(**settings)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_submit_never_performs_disk_io(tmp_path: Path) -> None:
    writer = _writer(tmp_path)
    result = writer.submit(_health("record:1"))

    assert result.accepted is True
    assert list(tmp_path.glob("narrative-*")) == []

    await writer.aclose("shutdown")
    files = list(tmp_path.glob("narrative-*.ndjson"))
    assert len(files) == 1
    assert _lines(files[0])[1]["recordId"] == "record:1"


@pytest.mark.asyncio
async def test_owned_task_writes_and_aclose_joins(tmp_path: Path) -> None:
    writer = _writer(tmp_path, flush_interval_ms=20)
    writer.submit(_health("record:1"))
    task = writer.start()
    assert task.get_name() == "narrative_tape_writer"
    await asyncio.sleep(0.05)
    await writer.aclose("shutdown")
    assert task.done()
    path = tmp_path / narrative_tape_filename("process:1", 7, 0)
    assert path.is_file()
    assert _lines(path)[-1]["payload"]["closeReason"] == "shutdown"


@pytest.mark.asyncio
async def test_rotation_gzips_and_chains_previous_file_hash(tmp_path: Path) -> None:
    writer = _writer(tmp_path, rotate_bytes=1, keep_files=8)
    writer.submit(_health("record:1", mono_ms=1200))
    await writer.aclose("shutdown")

    first = tmp_path / "narrative-process_1-s7-f0000.ndjson.gz"
    second = tmp_path / "narrative-process_1-s7-f0001.ndjson"
    assert first.is_file()
    assert second.is_file()
    assert not (tmp_path / "narrative-process_1-s7-f0000.ndjson").exists()
    rotated = [json.loads(line) for line in gzip.open(first, "rt", encoding="utf-8")]
    assert rotated[-1]["payload"]["closeReason"] == "rotation_size"
    assert _lines(second)[0]["previousFileHash"] == rotated[-1]["payload"]["fileHash"]
    assert _lines(second)[0]["fileOrdinal"] == 1
    assert _lines(second)[0]["streamEpoch"] == 7


@pytest.mark.asyncio
async def test_retention_deletes_oldest_archives(tmp_path: Path) -> None:
    writer = _writer(tmp_path, rotate_bytes=1, keep_files=2)
    writer.submit(_health("record:1", mono_ms=1200))
    writer.submit(_health("record:2", mono_ms=1300))
    writer.submit(_health("record:3", mono_ms=1400))
    await writer.aclose("shutdown")

    names = sorted(path.name for path in tmp_path.glob("narrative-*"))
    assert "narrative-process_1-s7-f0000.ndjson.gz" not in names
    assert len(names) == 2


@pytest.mark.asyncio
async def test_shutdown_timeout_is_fail_soft(tmp_path: Path) -> None:
    blocked = threading.Event()
    writes = 0

    def sink(data: bytes) -> None:
        nonlocal writes
        writes += 1
        if writes > 1:
            blocked.wait(0.4)

    writer = _writer(tmp_path, shutdown_flush_timeout_s=0.05, sink=sink)
    writer.submit(_health("record:1"))
    writer.submit(_health("record:2"))
    task = writer.start()
    await writer.aclose("shutdown")
    blocked.set()
    if not task.done():
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=0.5)
    assert writer.health == "degraded"
    loss = writer._queue.loss_snapshot()
    assert loss is not None
    assert any(bucket["reason"] == "tape_flush_timeout" for bucket in loss["buckets"])


def test_composition_builds_tape_health_without_runtime_import() -> None:
    source = Path(__file__).resolve().parents[1] / "src/irswitch/commentary/tape_writer.py"
    imports = [
        line
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.startswith("from ") or line.startswith("import ")
    ]
    joined = "\n".join(imports)
    assert "NarrativeRuntime" not in joined
    assert "DetectorBank" not in joined
    assert "overlay.tape" not in joined

    latch = CaptureHealthLatch()
    writer = NarrativeTapeWriter(
        Path("/tmp/unused-tape"),
        _golden("tape-manifest-framing"),
        capacity=1,
        recorder_generation=4,
        health_latch=latch,
    )
    writer.submit(_health("record:held"))
    lost = writer.submit(
        _health("record:required"),
        required_capture=True,
        detector_ids=("closing",),
    )
    assert lost.accepted is False
    notice = latch.snapshot()
    assert notice is not None
    command = tape_health_command(notice, "tape:health:1", 2000)
    assert command.kind == "TAPE_HEALTH_CHANGED"
    assert command.payload["status"] == "unavailable"
    assert command.payload["affectedDetectorIds"] == ["closing"]
    assert command.protected is True
