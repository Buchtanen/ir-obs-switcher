"""Offline NarrativeTape reader, immutable label sidecars and evaluation reports.

Consumes #239/#240 NDJSON without live iRacing, TTS, LLM, DetectorBank or
NarrativeRuntime. Ground-truth labels never write back into the source tape.
"""

from __future__ import annotations

import gzip
import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from irswitch.contracts.primitives import ContractViolation, Identifier, Sha256Hash, canonical_json

SCHEMA_RECORD = "narrative-tape-record/2"
SCHEMA_MANIFEST = "narrative-tape-manifest/2"
SCHEMA_SIDECAR = "narrative-label-sidecar/2"
KNOWN_RECORD_TYPES = frozenset(
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
        "drop_notice",
        "manifest_trailer",
    }
)


class LabelVerdict(StrEnum):
    TRUE_POSITIVE = "true_positive"
    FALSE_POSITIVE = "false_positive"
    FALSE_NEGATIVE = "false_negative"
    TRUE_NEGATIVE = "true_negative"
    UPSTREAM_FACT_ERROR = "upstream_fact_error"
    REALIZATION_ERROR = "realization_error"


@dataclass(frozen=True, slots=True)
class GroundTruthLabel:
    label_id: str
    target_record_id: str
    verdict: LabelVerdict
    note: str = ""
    target_frame_sequence: int | None = None


@dataclass(frozen=True, slots=True)
class GroundTruthSidecar:
    tape_file_hash: str
    process_instance_id: str | None
    stream_epoch: int | None
    labels: tuple[GroundTruthLabel, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schemaVersion": SCHEMA_SIDECAR,
            "tapeFileHash": self.tape_file_hash,
            "processInstanceId": self.process_instance_id,
            "streamEpoch": self.stream_epoch,
            "labels": [
                {
                    "labelId": item.label_id,
                    "targetRecordId": item.target_record_id,
                    "verdict": str(item.verdict),
                    "note": item.note,
                    "targetFrameSequence": item.target_frame_sequence,
                }
                for item in self.labels
            ],
        }


@dataclass(frozen=True, slots=True)
class TapeFileView:
    path: Path
    manifest: dict[str, Any]
    body: tuple[dict[str, Any], ...]
    trailer: dict[str, Any] | None
    file_hash: str | None
    catalog_hash: str
    effective_config_hash: str
    complete: bool
    compatible: bool
    diagnostics: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class TapeRunView:
    files: tuple[TapeFileView, ...]
    complete: bool
    compatible: bool
    catalog_hash: str
    effective_config_hash: str
    parameter_snapshots: tuple[dict[str, Any], ...]
    diagnostics: tuple[str, ...]

    @property
    def file_count(self) -> int:
        return len(self.files)

    def records(self) -> tuple[dict[str, Any], ...]:
        return tuple(record for view in self.files for record in view.body)

    def ordered_actor_records(self) -> tuple[dict[str, Any], ...]:
        """Actor records in reducerSequence order. Wall clock is not authority."""

        records = [record for record in self.records() if record.get("reducerSequence") is not None]
        return tuple(
            sorted(
                records,
                key=lambda record: (int(record["reducerSequence"]), int(record["recordedMonoMs"])),
            )
        )


@dataclass(frozen=True, slots=True)
class DetectorWindowReplay:
    detector_id: str
    parameter_snapshot_id: str | None
    first_frame_sequence: int
    last_frame_sequence: int
    frame_sequences: tuple[int, ...]
    missing_frame_sequences: tuple[int, ...]
    complete: bool
    capture_loss: bool
    interpolated: bool = False


@dataclass(frozen=True, slots=True)
class DetectorMetrics:
    windows: int
    complete_windows: int
    incomplete_windows: int
    required_capture_losses: int


@dataclass(frozen=True, slots=True)
class RealizationMetrics:
    fact_errors: int
    realization_errors: int


@dataclass(frozen=True, slots=True)
class EvaluationReport:
    compatible: bool
    complete: bool
    catalog_hash: str
    effective_config_hash: str
    detector: DetectorMetrics
    realization: RealizationMetrics
    incomplete_windows: tuple[str, ...]
    report_hash: Sha256Hash


def _read_bytes(path: Path) -> bytes:
    name = path.name
    if name.endswith(".ndjson.gz"):
        with gzip.open(path, "rb") as handle:
            return handle.read()
    if not name.endswith(".ndjson"):
        raise ContractViolation("narrative tape must be .ndjson or .ndjson.gz")
    return path.read_bytes()


def _parse_lines(raw: bytes) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in raw.splitlines():
        if not line:
            continue
        try:
            parsed = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise ContractViolation("tape line is not UTF-8 JSON") from error
        if not isinstance(parsed, dict):
            raise ContractViolation("tape line must be an object")
        rows.append(parsed)
    return rows


def _pre_trailer_bytes(raw: bytes) -> bytes:
    if not raw.endswith(b"\n"):
        return raw
    previous = raw.rfind(b"\n", 0, len(raw) - 1)
    if previous < 0:
        return raw
    return raw[: previous + 1]


def _file_hash(raw: bytes) -> str:
    return f"sha256:{hashlib.sha256(_pre_trailer_bytes(raw)).hexdigest()}"


def _diagnostics_for(
    manifest: Mapping[str, Any],
    *,
    expected_catalog_hash: str | None,
    expected_config_hash: str | None,
) -> list[str]:
    notes: list[str] = []
    if expected_catalog_hash is not None and manifest.get("catalogHash") != expected_catalog_hash:
        notes.append("catalog_hash_mismatch")
    if (
        expected_config_hash is not None
        and manifest.get("effectiveConfigHash") != expected_config_hash
    ):
        notes.append("config_hash_mismatch")
    return notes


def read_tape_file(
    path: Path | str,
    *,
    expected_catalog_hash: str | None = None,
    expected_config_hash: str | None = None,
) -> TapeFileView:
    """Read one versioned NDJSON file. Hash mismatch is explicit, not a crash."""

    source = Path(path)
    raw = _read_bytes(source)
    rows = _parse_lines(raw)
    if not rows or rows[0].get("recordType") != "manifest":
        raise ContractViolation("tape file must start with a manifest")
    if rows[0].get("schemaVersion") != SCHEMA_MANIFEST:
        raise ContractViolation("incompatible tape manifest schemaVersion")
    manifest = rows[0]
    trailer = rows[-1] if rows[-1].get("recordType") == "manifest_trailer" else None
    body = tuple(rows[1:-1] if trailer is not None else rows[1:])
    diagnostics = _diagnostics_for(
        manifest,
        expected_catalog_hash=expected_catalog_hash,
        expected_config_hash=expected_config_hash,
    )
    computed = _file_hash(raw)
    stored = None if trailer is None else trailer.get("payload", {}).get("fileHash")
    if trailer is None:
        diagnostics.append("missing_trailer")
    elif stored != computed:
        diagnostics.append("file_hash_mismatch")
    if trailer is not None and trailer.get("payload", {}).get("complete") is not True:
        diagnostics.append("trailer_incomplete")
    if trailer is not None and trailer.get("payload", {}).get("lossAccumulator"):
        diagnostics.append("drop_affected")
    for record in body:
        if record.get("schemaVersion") != SCHEMA_RECORD:
            diagnostics.append("incompatible_record_schema")
        if record.get("recordType") not in KNOWN_RECORD_TYPES:
            diagnostics.append("unknown_record_type")
    complete = (
        trailer is not None
        and trailer.get("payload", {}).get("complete") is True
        and stored == computed
        and "drop_affected" not in diagnostics
    )
    return TapeFileView(
        path=source,
        manifest=manifest,
        body=body,
        trailer=trailer,
        file_hash=computed if trailer is not None else None,
        catalog_hash=str(manifest["catalogHash"]),
        effective_config_hash=str(manifest["effectiveConfigHash"]),
        complete=complete,
        compatible="catalog_hash_mismatch" not in diagnostics
        and "config_hash_mismatch" not in diagnostics
        and "incompatible_record_schema" not in diagnostics
        and "unknown_record_type" not in diagnostics,
        diagnostics=tuple(dict.fromkeys(diagnostics)),
    )


def read_tape_run(
    paths: Sequence[Path | str],
    *,
    expected_catalog_hash: str | None = None,
    expected_config_hash: str | None = None,
) -> TapeRunView:
    """Read rotated files for one process/stream without consulting live config."""

    views = tuple(
        read_tape_file(
            path,
            expected_catalog_hash=expected_catalog_hash,
            expected_config_hash=expected_config_hash,
        )
        for path in paths
    )
    ordered = tuple(sorted(views, key=lambda item: int(item.manifest["fileOrdinal"])))
    diagnostics = [note for view in ordered for note in view.diagnostics]
    if not ordered:
        raise ContractViolation("tape run requires at least one file")
    identity = (
        ordered[0].manifest["processInstanceId"],
        ordered[0].manifest.get("streamEpoch"),
    )
    snapshots = tuple(ordered[0].manifest.get("detectorParameterSnapshots") or ())
    previous: str | None = None
    for view in ordered:
        if (view.manifest["processInstanceId"], view.manifest.get("streamEpoch")) != identity:
            diagnostics.append("run_identity_mismatch")
        if list(view.manifest.get("detectorParameterSnapshots") or ()) != list(snapshots):
            diagnostics.append("parameter_snapshot_drift")
        chained = view.manifest.get("previousFileHash")
        if previous is None and chained not in {None, previous}:
            diagnostics.append("rotation_chain_broken")
        if previous is not None and chained != previous:
            diagnostics.append("rotation_chain_broken")
        previous = view.file_hash
    return TapeRunView(
        files=ordered,
        complete=all(view.complete for view in ordered)
        and "rotation_chain_broken" not in diagnostics,
        compatible=all(view.compatible for view in ordered)
        and "run_identity_mismatch" not in diagnostics,
        catalog_hash=ordered[0].catalog_hash,
        effective_config_hash=ordered[0].effective_config_hash,
        parameter_snapshots=snapshots,
        diagnostics=tuple(dict.fromkeys(diagnostics)),
    )


def _labels(raw: Iterable[Mapping[str, object]]) -> tuple[GroundTruthLabel, ...]:
    labels: list[GroundTruthLabel] = []
    for item in raw:
        frame = item.get("targetFrameSequence")
        labels.append(
            GroundTruthLabel(
                label_id=str(Identifier(str(item["labelId"]))),
                target_record_id=str(Identifier(str(item["targetRecordId"]))),
                verdict=LabelVerdict(str(item["verdict"])),
                note=str(item.get("note") or ""),
                target_frame_sequence=int(frame) if isinstance(frame, int) else None,
            )
        )
    return tuple(labels)


def write_sidecar(
    path: Path | str,
    *,
    tape_file_hash: str,
    labels: Sequence[Mapping[str, object]] = (),
    process_instance_id: str | None = None,
    stream_epoch: int | None = None,
) -> GroundTruthSidecar:
    """Write labels beside the tape. Refuses any NarrativeTape path."""

    destination = Path(path)
    name = destination.name
    if name.endswith(".ndjson") or name.endswith(".ndjson.gz"):
        raise ContractViolation("sidecar must not be written into a narrative tape file")
    sidecar = GroundTruthSidecar(
        tape_file_hash=str(Sha256Hash(tape_file_hash)),
        process_instance_id=process_instance_id,
        stream_epoch=stream_epoch,
        labels=_labels(labels),
    )
    destination.write_text(canonical_json(sidecar.to_dict()) + "\n", encoding="utf-8")
    return sidecar


def load_sidecar(
    path: Path | str,
    *,
    expected_file_hash: str | None = None,
) -> GroundTruthSidecar:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schemaVersion") != SCHEMA_SIDECAR:
        raise ContractViolation("sidecar schemaVersion must be narrative-label-sidecar/2")
    tape_hash = str(Sha256Hash(payload["tapeFileHash"]))
    if expected_file_hash is not None and tape_hash != expected_file_hash:
        raise ContractViolation("sidecar fileHash does not bind the source tape")
    return GroundTruthSidecar(
        tape_file_hash=tape_hash,
        process_instance_id=payload.get("processInstanceId"),
        stream_epoch=payload.get("streamEpoch"),
        labels=_labels(payload.get("labels") or ()),
    )


def _capture_unavailable(run: TapeRunView) -> frozenset[str]:
    detectors: set[str] = set()
    for record in run.records():
        if record.get("recordType") != "health_change":
            continue
        payload = record.get("payload") or {}
        if payload.get("status") == "unavailable":
            detectors.update(str(item) for item in payload.get("affectedDetectorIds") or ())
    return frozenset(detectors)


def reconstruct_windows(run: TapeRunView) -> tuple[DetectorWindowReplay, ...]:
    """Rebuild inclusive FeatureFrame ranges across rotated files. Never interpolate."""

    frames: dict[int, dict[str, Any]] = {}
    for record in run.records():
        if record.get("recordType") != "feature_frame":
            continue
        sequence = int(record["payload"]["frameSequence"])
        frames.setdefault(sequence, record["payload"])
    unavailable = _capture_unavailable(run)
    windows: list[DetectorWindowReplay] = []
    for record in run.records():
        if record.get("recordType") != "detector_observation":
            continue
        payload = record["payload"]
        window = payload.get("windowFrameRange")
        if not isinstance(window, dict):
            continue
        first = int(window["firstFrameSequence"])
        last = int(window["lastFrameSequence"])
        expected = tuple(range(first, last + 1))
        present = tuple(item for item in expected if item in frames)
        missing = tuple(item for item in expected if item not in frames)
        complete = not missing and bool(window.get("postWindowComplete"))
        detector_id = str(payload["detectorId"])
        windows.append(
            DetectorWindowReplay(
                detector_id=detector_id,
                parameter_snapshot_id=payload.get("parameterSnapshotId"),
                first_frame_sequence=first,
                last_frame_sequence=last,
                frame_sequences=present,
                missing_frame_sequences=missing,
                complete=complete,
                capture_loss=bool(missing) and detector_id in unavailable,
                interpolated=False,
            )
        )
    return tuple(windows)


def evaluate_tape(
    run: TapeRunView,
    sidecar: GroundTruthSidecar | None = None,
) -> EvaluationReport:
    """Deterministic detector/LLM report. Fact errors stay separate from realization."""

    windows = reconstruct_windows(run)
    labels = () if sidecar is None else sidecar.labels
    detector = DetectorMetrics(
        windows=len(windows),
        complete_windows=sum(1 for item in windows if item.complete),
        incomplete_windows=sum(1 for item in windows if not item.complete),
        required_capture_losses=sum(1 for item in windows if item.capture_loss),
    )
    realization = RealizationMetrics(
        fact_errors=sum(1 for item in labels if item.verdict is LabelVerdict.UPSTREAM_FACT_ERROR),
        realization_errors=sum(
            1 for item in labels if item.verdict is LabelVerdict.REALIZATION_ERROR
        ),
    )
    projection = {
        "compatible": run.compatible,
        "complete": run.complete and detector.incomplete_windows == 0,
        "catalogHash": run.catalog_hash,
        "effectiveConfigHash": run.effective_config_hash,
        "detector": {
            "windows": detector.windows,
            "completeWindows": detector.complete_windows,
            "incompleteWindows": detector.incomplete_windows,
            "requiredCaptureLosses": detector.required_capture_losses,
        },
        "realization": {
            "factErrors": realization.fact_errors,
            "realizationErrors": realization.realization_errors,
        },
        "incompleteWindows": [
            f"{item.detector_id}:{item.first_frame_sequence}-{item.last_frame_sequence}"
            for item in windows
            if not item.complete
        ],
    }
    incomplete = tuple(
        f"{item.detector_id}:{item.first_frame_sequence}-{item.last_frame_sequence}"
        for item in windows
        if not item.complete
    )
    return EvaluationReport(
        compatible=run.compatible,
        complete=bool(projection["complete"]),
        catalog_hash=run.catalog_hash,
        effective_config_hash=run.effective_config_hash,
        detector=detector,
        realization=realization,
        incomplete_windows=incomplete,
        report_hash=Sha256Hash(
            f"sha256:{hashlib.sha256(canonical_json(projection).encode('utf-8')).hexdigest()}"
        ),
    )
