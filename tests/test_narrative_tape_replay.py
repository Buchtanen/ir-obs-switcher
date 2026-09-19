"""F34 NarrativeTape replay: hashes, sidecars, window reconstruction, reports."""

from __future__ import annotations

import copy
import gzip
import importlib.util
import json
from pathlib import Path

import pytest

from irswitch.commentary.tape_replay import (
    LabelVerdict,
    evaluate_tape,
    load_sidecar,
    read_tape_file,
    read_tape_run,
    reconstruct_windows,
    write_sidecar,
)
from irswitch.commentary.tape_writer import TapeFileSession, narrative_tape_filename
from irswitch.contracts.primitives import ContractViolation
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

HASH = "sha256:1111111111111111111111111111111111111111111111111111111111111111"


def _errors(value: object) -> list[str]:
    return _dto_builder.schema_errors(value, SCHEMA, SCHEMA)


def _golden(fixture_id: str) -> dict:
    for row in GOLDENS["valid"]:
        if row["id"] == fixture_id:
            return copy.deepcopy(row["value"])
    raise AssertionError(f"missing valid golden {fixture_id}")


def _envelope(record_id: str, record_type: str, payload: dict, **overrides: object) -> dict:
    record = {
        "schemaVersion": "narrative-tape-record/2",
        "recordId": record_id,
        "recordType": record_type,
        "processInstanceId": "process:1",
        "broadcastEpoch": 4,
        "streamEpoch": 7,
        "reducerSequence": None,
        "recordedMonoMs": 1000,
        "recordedAtUtc": None,
        "purposeChannel": "detector_tuning",
        "recordPriority": "critical",
        "tapeChannel": "race.battle.closing" if record_type == "detector_observation" else None,
        "correlationIds": [],
        "effectiveConfigHash": HASH,
        "configApplySequence": 8,
        "payloadSchemaVersion": payload["schemaVersion"],
        "payload": payload,
    }
    record.update(overrides)
    assert _errors(record) == [], _errors(record)
    return record


def _frame(sequence: int) -> dict:
    payload = _golden("feature-frame-measured-gap")
    payload["frameSequence"] = sequence
    payload["observedMonoMs"] = 1000 + sequence
    payload["values"][0]["observedMonoMs"] = 1000 + sequence
    payload["values"][0]["evidenceRefs"] = [f"frame:{sequence}"]
    return _envelope(
        f"record:frame:{sequence}", "feature_frame", payload, recordedMonoMs=1000 + sequence
    )


def _observation(*, first: int = 200, last: int = 214, complete: bool = True) -> dict:
    payload = _golden("detector-observation-windowed")
    payload["windowFrameRange"] = {
        "firstFrameSequence": first,
        "lastFrameSequence": last,
        "postWindowComplete": complete,
    }
    return _envelope("record:obs:1", "detector_observation", payload, recordedMonoMs=2000)


def _health_unavailable(detector_id: str = "battle_ahead_v1") -> dict:
    record = _golden("tape-health-record")
    record["recordId"] = "record:health:loss"
    record["purposeChannel"] = "flow"
    record["payload"]["status"] = "unavailable"
    record["payload"]["affectedDetectorIds"] = [detector_id]
    record["payload"]["firstLostSequence"] = 209
    record["payload"]["lastLostSequence"] = 209
    record["reducerSequence"] = 10
    assert _errors(record) == [], _errors(record)
    return record


def _write_file(path: Path, *records: dict, manifest: dict | None = None) -> dict:
    session = TapeFileSession(path)
    session.open(manifest or _golden("tape-manifest-framing"))
    for record in records:
        assert session.append(record) is True
    trailer = session.close(reason="shutdown", recorded_mono_ms=9000, record_id="record:trailer")
    assert trailer is not None
    return trailer


def test_reader_validates_versioned_file_and_hashes(tmp_path: Path) -> None:
    path = tmp_path / narrative_tape_filename("process:1", 7, 0)
    _write_file(path, _golden("tape-health-record"))

    view = read_tape_file(path, expected_catalog_hash=HASH, expected_config_hash=HASH)

    assert view.complete is True
    assert view.compatible is True
    assert view.file_hash == view.trailer["payload"]["fileHash"]
    assert view.catalog_hash == HASH
    assert view.effective_config_hash == HASH
    assert [item["recordType"] for item in view.body] == ["health_change"]


def test_incompatible_catalog_hash_is_explicit_not_a_crash(tmp_path: Path) -> None:
    path = tmp_path / "mismatch.ndjson"
    _write_file(path, _golden("tape-health-record"))
    other = "sha256:2222222222222222222222222222222222222222222222222222222222222222"

    view = read_tape_file(path, expected_catalog_hash=other)

    assert view.compatible is False
    assert view.complete is True
    assert "catalog_hash_mismatch" in view.diagnostics


def test_sidecar_never_mutates_source_tape(tmp_path: Path) -> None:
    tape = tmp_path / "source.ndjson"
    trailer = _write_file(tape, _golden("tape-health-record"))
    before = tape.read_bytes()
    sidecar_path = tmp_path / "source.labels.json"

    written = write_sidecar(
        sidecar_path,
        tape_file_hash=trailer["payload"]["fileHash"],
        process_instance_id="process:1",
        stream_epoch=7,
        labels=(
            {
                "labelId": "label:1",
                "targetRecordId": "record:1",
                "verdict": "upstream_fact_error",
                "note": "gap sign flipped",
            },
        ),
    )
    loaded = load_sidecar(sidecar_path, expected_file_hash=trailer["payload"]["fileHash"])

    assert tape.read_bytes() == before
    assert written.tape_file_hash == trailer["payload"]["fileHash"]
    assert loaded.labels[0].verdict is LabelVerdict.UPSTREAM_FACT_ERROR
    with pytest.raises(ContractViolation, match="sidecar"):
        write_sidecar(tape, tape_file_hash=trailer["payload"]["fileHash"], labels=())
    with pytest.raises(ContractViolation, match="fileHash"):
        load_sidecar(sidecar_path, expected_file_hash=HASH)


def test_f34_reconstructs_window_across_rotation_without_current_config(tmp_path: Path) -> None:
    first_manifest = _golden("tape-manifest-framing")
    first_path = tmp_path / narrative_tape_filename("process:1", 7, 0)
    first_trailer = _write_file(
        first_path,
        *(_frame(sequence) for sequence in range(200, 208)),
        manifest=first_manifest,
    )
    second_manifest = _golden("tape-continuation-manifest")
    second_manifest["previousFileHash"] = first_trailer["payload"]["fileHash"]
    second_path = tmp_path / narrative_tape_filename("process:1", 7, 1)
    _write_file(
        second_path,
        *(_frame(sequence) for sequence in range(208, 215)),
        _observation(),
        manifest=second_manifest,
    )

    run = read_tape_run((first_path, second_path), expected_catalog_hash=HASH)
    windows = reconstruct_windows(run)

    assert run.complete is True
    assert run.file_count == 2
    assert run.parameter_snapshots[0]["parameterSnapshotId"] == "params:battle-ahead:1"
    assert windows[0].detector_id == "battle_ahead_v1"
    assert windows[0].parameter_snapshot_id == "params:battle-ahead:1"
    assert windows[0].frame_sequences == tuple(range(200, 215))
    assert windows[0].complete is True
    assert windows[0].capture_loss is False
    assert windows[0].interpolated is False


def test_required_missing_frame_is_incomplete_without_interpolation(tmp_path: Path) -> None:
    path = tmp_path / "required-gap.ndjson"
    frames = [_frame(sequence) for sequence in range(200, 215) if sequence != 209]
    session = TapeFileSession(path)
    session.open(_golden("tape-manifest-framing"))
    for record in frames:
        assert session.append(record) is True
    session.note_queue_loss(
        record_type="feature_frame",
        record_priority="critical",
        recorded_mono_ms=1209,
    )
    assert session.append(_observation()) is True
    assert session.append(_health_unavailable()) is True
    session.close(reason="shutdown", recorded_mono_ms=9000, record_id="record:trailer")

    run = read_tape_run((path,))
    window = reconstruct_windows(run)[0]
    report = evaluate_tape(run)

    assert window.complete is False
    assert window.missing_frame_sequences == (209,)
    assert window.interpolated is False
    assert window.capture_loss is True
    assert report.complete is False
    assert report.detector.required_capture_losses == 1
    assert 209 not in window.frame_sequences


def test_optional_missing_frame_is_incomplete_without_capture_loss(tmp_path: Path) -> None:
    path = tmp_path / "optional-gap.ndjson"
    frames = [_frame(sequence) for sequence in range(200, 215) if sequence != 209]
    session = TapeFileSession(path)
    session.open(_golden("tape-manifest-framing"))
    for record in frames:
        assert session.append(record) is True
    session.note_queue_loss(
        record_type="feature_frame",
        record_priority="sample",
        recorded_mono_ms=1209,
    )
    assert session.append(_observation()) is True
    session.close(reason="shutdown", recorded_mono_ms=9000, record_id="record:trailer")

    window = reconstruct_windows(read_tape_run((path,)))[0]

    assert window.complete is False
    assert window.missing_frame_sequences == (209,)
    assert window.capture_loss is False
    assert window.interpolated is False


def test_report_separates_fact_errors_from_realization_errors(tmp_path: Path) -> None:
    tape = tmp_path / "eval.ndjson"
    trailer = _write_file(tape, _golden("tape-health-record"))
    sidecar_path = tmp_path / "eval.labels.json"
    write_sidecar(
        sidecar_path,
        tape_file_hash=trailer["payload"]["fileHash"],
        labels=(
            {
                "labelId": "label:fact",
                "targetRecordId": "record:1",
                "verdict": "upstream_fact_error",
            },
            {
                "labelId": "label:realizer",
                "targetRecordId": "record:1",
                "verdict": "realization_error",
            },
        ),
    )
    run = read_tape_run((tape,), expected_catalog_hash=HASH, expected_config_hash=HASH)
    sidecar = load_sidecar(sidecar_path, expected_file_hash=run.files[0].file_hash)
    first = evaluate_tape(run, sidecar)
    second = evaluate_tape(run, sidecar)

    assert first.realization.fact_errors == 1
    assert first.realization.realization_errors == 1
    assert first.report_hash == second.report_hash
    assert first.catalog_hash == HASH
    assert first.effective_config_hash == HASH


def test_actor_replay_orders_by_reducer_sequence_not_clock(tmp_path: Path) -> None:
    later = _golden("tape-health-record")
    later["recordId"] = "record:later"
    later["reducerSequence"] = 11
    later["recordedMonoMs"] = 1000
    earlier = _golden("tape-health-record")
    earlier["recordId"] = "record:earlier"
    earlier["reducerSequence"] = 9
    earlier["recordedMonoMs"] = 5000
    path = tmp_path / "order.ndjson"
    _write_file(path, later, earlier)

    ordered = read_tape_run((path,)).ordered_actor_records()

    assert [item["recordId"] for item in ordered] == ["record:earlier", "record:later"]


def test_gzip_continuation_is_readable(tmp_path: Path) -> None:
    raw = tmp_path / "rotated.ndjson"
    _write_file(raw, _golden("tape-health-record"))
    gz = tmp_path / "rotated.ndjson.gz"
    gz.write_bytes(gzip.compress(raw.read_bytes()))

    view = read_tape_file(gz)
    assert view.body[0]["recordType"] == "health_change"
    assert view.complete is True


def test_replay_module_does_not_import_runtime_or_overlay_tape() -> None:
    source = ROOT / "src/irswitch/commentary/tape_replay.py"
    imports = [
        line
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.startswith("from ") or line.startswith("import ")
    ]
    joined = "\n".join(imports)
    assert "NarrativeRuntime" not in joined
    assert "DetectorBank" not in joined
    assert "overlay.tape" not in joined
    assert "overlay.replay" not in joined
