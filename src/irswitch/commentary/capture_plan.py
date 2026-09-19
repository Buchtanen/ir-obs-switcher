"""Immutable per-stream CapturePlan compiled from catalog tuning + tape config.

TapePolicyCompiler never imports DetectorBank, NarrativeRuntime, or the V4
overlay tape. Config admission (#238) still owns INI parsing; this module owns
the effective capture policy for every catalog detector.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal, cast

from irswitch.contracts.config import CommentaryConfigSnapshot
from irswitch.contracts.primitives import (
    ContractViolation,
    Identifier,
    Sha256Hash,
    canonical_sha256,
)
from irswitch.contracts.resources import packaged_schema_bytes

TuningPolicy = Literal["none", "optional", "required"]
PurposeChannel = Literal["flow", "llm_eval", "detector_tuning"]
PreWindow = Literal["none", "complete_trend_window"]
EvidenceCompleteness = Literal["not_applicable", "optional_may_gap", "required"]
CaptureDiagnosticReason = Literal[
    "required_not_experimental",
    "required_requires_calibration",
    "required_requires_detector_tuning",
    "required_requires_allowlist",
    "required_requires_input_windows",
    "required_requires_preflight",
    "purpose_channel_is_not_tape_channel",
    "tape_channel_is_not_purpose_channel",
    "unknown_purpose_channel",
    "unknown_tape_channel",
]

PURPOSE_CHANNELS = frozenset({"flow", "llm_eval", "detector_tuning"})
TUNING_POLICIES = frozenset({"none", "optional", "required"})
REQUIRED_FIELDS = (
    "coverage",
    "effectiveParameters",
    "featureQuality",
    "nearThresholdNegatives",
    "predicateTrace",
    "transitionReason",
)
REQUIRED_RECORD_KINDS = ("detector_observation", "feature_frame")


def _packaged_json(name: str) -> dict[str, Any]:
    return cast(dict[str, Any], json.loads(packaged_schema_bytes(name)))


@lru_cache(maxsize=1)
def _default_config() -> dict[str, Any]:
    return dict(_packaged_json("config-contract.json")["defaultConfig"])


@lru_cache(maxsize=1)
def _packaged_catalog() -> dict[str, Any]:
    return _packaged_json("detector-catalog.json")


@lru_cache(maxsize=1)
def _registry_tape_channels() -> frozenset[str]:
    return frozenset(_packaged_json("freeze-registry.json")["tapeChannels"])


def _as_tuple(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value)
    raise ContractViolation("set value must be a string sequence")


def _bool(value: object, field: str) -> bool:
    if not isinstance(value, bool):
        raise ContractViolation(f"{field} must be a bool")
    return value


def _policy(value: object, detector_id: str) -> TuningPolicy:
    if value not in TUNING_POLICIES:
        raise ContractViolation(f"detector {detector_id} has unknown tuning.policy")
    return cast(TuningPolicy, value)


@dataclass(frozen=True, slots=True)
class CaptureWindow:
    pre_window: PreWindow
    post_window_s: float


@dataclass(frozen=True, slots=True)
class CapturePlanDiagnostic:
    reason: CaptureDiagnosticReason
    message: str
    detector_id: str | None = None


@dataclass(frozen=True, slots=True)
class DetectorCapturePlan:
    detector_id: str
    detector_version: int
    experimental: bool
    enabled: bool
    catalog_policy: TuningPolicy
    effective_policy: TuningPolicy
    tape_channel: str
    purpose_channels: tuple[PurposeChannel, ...]
    capture_active: bool
    forces_feature_windows: bool
    required_fields: tuple[str, ...]
    required_record_kinds: tuple[str, ...]
    parameters: MappingProxyType[str, object]
    parameter_snapshot_id: str | None
    detector_config_hash: Sha256Hash
    window: CaptureWindow
    evidence_completeness: EvidenceCompleteness


@dataclass(frozen=True, slots=True)
class StreamCapturePlan:
    profile: Literal["production", "calibration"]
    tape_enabled: bool
    purpose_channels: tuple[PurposeChannel, ...]
    tape_channel_allowlist: tuple[str, ...]
    detail: str
    preflight_ready: bool
    valid: bool
    plan_hash: Sha256Hash
    detectors: tuple[DetectorCapturePlan, ...]
    diagnostics: tuple[CapturePlanDiagnostic, ...]

    def entry(self, detector_id: str) -> DetectorCapturePlan:
        for item in self.detectors:
            if item.detector_id == detector_id:
                return item
        raise ContractViolation(f"unknown capture-plan detector {detector_id}")

    def parameter_snapshots(self) -> tuple[dict[str, object], ...]:
        rows: list[dict[str, object]] = []
        for item in self.detectors:
            if item.parameter_snapshot_id is None:
                continue
            rows.append(
                {
                    "parameterSnapshotId": item.parameter_snapshot_id,
                    "detectorId": item.detector_id,
                    "detectorVersion": str(item.detector_version),
                    "detectorConfigHash": str(item.detector_config_hash),
                    "parameters": dict(item.parameters),
                }
            )
        return tuple(rows)

    def startup_status(self) -> tuple[dict[str, object], ...]:
        return tuple(
            {
                "detectorId": item.detector_id,
                "enabled": item.enabled,
                "experimental": item.experimental,
                "effectivePolicy": item.effective_policy,
                "captureActive": item.capture_active,
                "tapeChannel": item.tape_channel,
                "evidenceCompleteness": item.evidence_completeness,
            }
            for item in self.detectors
        )

    def runtime_status(
        self, *, disabled_for_run: Sequence[str] = ()
    ) -> tuple[dict[str, object], ...]:
        disabled = frozenset(disabled_for_run)
        return tuple(
            {
                **row,
                "disabledForRun": row["detectorId"] in disabled,
            }
            for row in self.startup_status()
        )


def _resolved_values(
    values: Mapping[str, object] | CommentaryConfigSnapshot | None,
) -> dict[str, object]:
    merged: dict[str, object] = dict(_default_config())
    supplied: Mapping[str, object]
    if values is None:
        supplied = {}
    elif isinstance(values, CommentaryConfigSnapshot):
        supplied = values.values
    else:
        supplied = values
    for key, value in supplied.items():
        merged[str(key)] = tuple(value) if isinstance(value, list) else value
    return merged


def _parameters(detector: Mapping[str, Any], values: Mapping[str, object]) -> dict[str, object]:
    parameters = {item["id"]: item["default"] for item in detector.get("parameters", ())}
    prefix = f"commentary.detector.{detector['id']}."
    for key, value in values.items():
        if key.startswith(prefix) and key != f"{prefix}enabled":
            parameters[key.removeprefix(prefix)] = value
    return {str(key): parameters[key] for key in sorted(parameters)}


def _catalog_windows(catalog: Mapping[str, Any]) -> CaptureWindow:
    capture = catalog.get("capturePlan") or {}
    pre = capture.get("preWindow", "complete_trend_window")
    post = capture.get("postWindowSeconds", 5.0)
    if (
        pre != "complete_trend_window"
        or not isinstance(post, (int, float))
        or isinstance(post, bool)
    ):
        raise ContractViolation("catalog capturePlan windows are invalid")
    return CaptureWindow(pre_window="complete_trend_window", post_window_s=float(post))


def _required_fields(catalog: Mapping[str, Any]) -> tuple[str, ...]:
    capture = catalog.get("capturePlan") or {}
    fields = tuple(sorted(str(item) for item in capture.get("requiredFields", REQUIRED_FIELDS)))
    return fields or REQUIRED_FIELDS


def _flow_selected(
    tape_channel: str,
    tape_enabled: bool,
    purpose_channels: tuple[str, ...],
    allowlist: tuple[str, ...],
) -> bool:
    if not tape_enabled or "flow" not in purpose_channels:
        return False
    return "*" in allowlist or tape_channel in allowlist


def _channel_diagnostics(
    purpose_channels: tuple[str, ...],
    allowlist: tuple[str, ...],
    registry_channels: frozenset[str],
) -> list[CapturePlanDiagnostic]:
    diagnostics: list[CapturePlanDiagnostic] = []
    for channel in purpose_channels:
        if channel not in PURPOSE_CHANNELS:
            reason: CaptureDiagnosticReason
            if channel in registry_channels:
                reason = "purpose_channel_is_not_tape_channel"
                message = f"purpose channel {channel} is a tape_channel, not a capture purpose"
            else:
                reason = "unknown_purpose_channel"
                message = f"unknown purpose channel {channel}"
            diagnostics.append(CapturePlanDiagnostic(reason, message))
    for channel in allowlist:
        if channel == "*":
            continue
        if channel in PURPOSE_CHANNELS:
            diagnostics.append(
                CapturePlanDiagnostic(
                    "tape_channel_is_not_purpose_channel",
                    f"tape_channel allowlist member {channel} is a purpose channel",
                )
            )
        elif channel not in registry_channels:
            diagnostics.append(
                CapturePlanDiagnostic("unknown_tape_channel", f"unknown tape_channel {channel}")
            )
    return diagnostics


def _required_diagnostics(
    detector_id: str,
    *,
    experimental: bool,
    enabled: bool,
    profile: str,
    tape_enabled: bool,
    purpose_channels: tuple[str, ...],
    allowlist: tuple[str, ...],
    capture_windows: bool,
    preflight_ready: bool,
) -> list[CapturePlanDiagnostic]:
    if not experimental:
        return [
            CapturePlanDiagnostic(
                "required_not_experimental",
                f"required tuning detector {detector_id} cannot be released",
                detector_id,
            )
        ]
    if not enabled:
        return []
    if profile != "calibration":
        return [
            CapturePlanDiagnostic(
                "required_requires_calibration",
                f"required tuning detector {detector_id} requires calibration profile",
                detector_id,
            )
        ]
    if not tape_enabled or "detector_tuning" not in purpose_channels:
        return [
            CapturePlanDiagnostic(
                "required_requires_detector_tuning",
                f"required tuning detector {detector_id} requires detector_tuning tape",
                detector_id,
            )
        ]
    if detector_id not in allowlist:
        return [
            CapturePlanDiagnostic(
                "required_requires_allowlist",
                f"required tuning detector {detector_id} must be allowlisted",
                detector_id,
            )
        ]
    if not capture_windows:
        return [
            CapturePlanDiagnostic(
                "required_requires_input_windows",
                f"required tuning detector {detector_id} requires input-window capture",
                detector_id,
            )
        ]
    if not preflight_ready:
        return [
            CapturePlanDiagnostic(
                "required_requires_preflight",
                f"required tuning detector {detector_id} requires writable recorder preflight",
                detector_id,
            )
        ]
    return []


def compile_capture_plan(
    values: Mapping[str, object] | CommentaryConfigSnapshot | None = None,
    *,
    catalog: Mapping[str, Any] | None = None,
    tape_channels: frozenset[str] | None = None,
    preflight_ready: bool = False,
) -> StreamCapturePlan:
    """Combine global tape config with each trigger's tuning declaration."""

    resolved = _resolved_values(values)
    catalog_data = dict(catalog) if catalog is not None else _packaged_catalog()
    registry_channels = tape_channels if tape_channels is not None else _registry_tape_channels()
    profile = str(resolved["commentary.detectors.profile"])
    if profile not in {"production", "calibration"}:
        raise ContractViolation("commentary.detectors.profile must be production or calibration")
    tape_enabled = _bool(resolved["commentary.tape.enabled"], "commentary.tape.enabled")
    purpose_channels = _as_tuple(resolved["commentary.tape.channels"])
    trigger_allowlist = _as_tuple(resolved["commentary.tape.detector_tuning.trigger_allowlist"])
    flow_allowlist = _as_tuple(resolved["commentary.tape.flow.tape_channel_allowlist"])
    capture_windows = _bool(
        resolved["commentary.tape.detector_tuning.capture_input_windows"],
        "commentary.tape.detector_tuning.capture_input_windows",
    )
    detail = str(resolved["commentary.tape.detail"])
    catalog_window = _catalog_windows(catalog_data)
    required_fields = _required_fields(catalog_data)

    diagnostics = _channel_diagnostics(purpose_channels, flow_allowlist, registry_channels)
    normalized_purposes = tuple(
        cast(PurposeChannel, channel) for channel in purpose_channels if channel in PURPOSE_CHANNELS
    )
    detectors: list[DetectorCapturePlan] = []
    for detector in catalog_data["definitions"]:
        detector_id = Identifier(str(detector["id"]))
        policy = _policy(detector["tuningPolicy"], detector_id)
        experimental = _bool(detector["experimental"], f"{detector_id}.experimental")
        enabled = bool(resolved.get(f"commentary.detector.{detector_id}.enabled", False))
        tape_channel = Identifier(str(detector["output"]["tapeChannel"]))
        parameters = _parameters(detector, resolved)
        config_hash = canonical_sha256(
            {
                "detectorId": detector_id,
                "detectorVersion": str(detector["version"]),
                "parameters": parameters,
            }
        )
        detector_diagnostics: list[CapturePlanDiagnostic] = []
        if policy == "required":
            detector_diagnostics = _required_diagnostics(
                detector_id,
                experimental=experimental,
                enabled=enabled,
                profile=profile,
                tape_enabled=tape_enabled,
                purpose_channels=purpose_channels,
                allowlist=trigger_allowlist,
                capture_windows=capture_windows,
                preflight_ready=preflight_ready,
            )
        diagnostics.extend(detector_diagnostics)
        tuning_selected = (
            tape_enabled
            and "detector_tuning" in purpose_channels
            and detector_id in trigger_allowlist
            and capture_windows
        )
        capture_active = False
        forces_windows = False
        evidence: EvidenceCompleteness = "not_applicable"
        window = CaptureWindow(pre_window="none", post_window_s=0.0)
        fields: tuple[str, ...] = ()
        kinds: tuple[str, ...] = ()
        snapshot_id: str | None = None
        if policy == "none":
            capture_active = False
        elif policy == "optional" and enabled and tuning_selected:
            capture_active = True
            evidence = "optional_may_gap"
            window = catalog_window
            snapshot_id = f"params:{detector_id}:{detector['version']}"
        elif policy == "required" and enabled and not detector_diagnostics:
            capture_active = True
            forces_windows = True
            evidence = "required"
            window = catalog_window
            fields = required_fields
            kinds = REQUIRED_RECORD_KINDS
            snapshot_id = f"params:{detector_id}:{detector['version']}"
        purposes: list[PurposeChannel] = []
        if capture_active:
            purposes.append("detector_tuning")
        if _flow_selected(tape_channel, tape_enabled, purpose_channels, flow_allowlist):
            purposes.append("flow")
        detectors.append(
            DetectorCapturePlan(
                detector_id=detector_id,
                detector_version=int(detector["version"]),
                experimental=experimental,
                enabled=enabled,
                catalog_policy=policy,
                effective_policy=policy,
                tape_channel=tape_channel,
                purpose_channels=tuple(sorted(purposes)),
                capture_active=capture_active,
                forces_feature_windows=forces_windows,
                required_fields=fields,
                required_record_kinds=kinds,
                parameters=MappingProxyType(parameters),
                parameter_snapshot_id=snapshot_id,
                detector_config_hash=config_hash,
                window=window,
                evidence_completeness=evidence,
            )
        )

    detectors.sort(key=lambda item: item.detector_id)
    projection = {
        "profile": profile,
        "tapeEnabled": tape_enabled,
        "purposeChannels": list(normalized_purposes),
        "tapeChannelAllowlist": list(flow_allowlist),
        "detail": detail,
        "preflightReady": preflight_ready,
        "detectors": [
            {
                "detectorId": item.detector_id,
                "effectivePolicy": item.effective_policy,
                "enabled": item.enabled,
                "captureActive": item.capture_active,
                "tapeChannel": item.tape_channel,
                "purposeChannels": list(item.purpose_channels),
                "parameterSnapshotId": item.parameter_snapshot_id,
            }
            for item in detectors
        ],
        "diagnostics": [
            {"reason": item.reason, "detectorId": item.detector_id, "message": item.message}
            for item in diagnostics
        ],
    }
    return StreamCapturePlan(
        profile=cast(Literal["production", "calibration"], profile),
        tape_enabled=tape_enabled,
        purpose_channels=normalized_purposes,
        tape_channel_allowlist=flow_allowlist,
        detail=detail,
        preflight_ready=preflight_ready,
        valid=not diagnostics,
        plan_hash=canonical_sha256(projection),
        detectors=tuple(detectors),
        diagnostics=tuple(diagnostics),
    )


@dataclass(frozen=True, slots=True)
class CapturePreflight:
    ready: bool
    reason: str | None = None


def probe_writable_capture(
    output_dir: Path | str,
    *,
    working_directory: Path | None = None,
) -> CapturePreflight:
    """Fail-soft writable-path probe. Never raises into the race loop."""

    if not isinstance(output_dir, (Path, str)) or str(output_dir).strip() == "":
        raise ContractViolation("capture output_dir is required")
    workdir = (working_directory or Path.cwd()).resolve(strict=False)
    try:
        path = Path(output_dir).expanduser()
        resolved = (workdir / path if not path.is_absolute() else path).resolve(strict=False)
        if resolved == Path(resolved.anchor).resolve(strict=False):
            return CapturePreflight(False, "unsafe_root_path")
        existing = resolved
        while not existing.exists() and existing != existing.parent:
            existing = existing.parent
        if not existing.is_dir() or not os.access(existing, os.W_OK):
            return CapturePreflight(False, "destination_parent_not_writable")
        if resolved.exists() and not resolved.is_dir():
            return CapturePreflight(False, "output_dir_is_not_a_directory")
        probe_dir = resolved if resolved.exists() else existing
        probe = probe_dir / ".narrative-capture-preflight"
        probe.write_bytes(b"ok")
        probe.unlink()
    except OSError:
        return CapturePreflight(False, "writable_probe_failed")
    return CapturePreflight(True, None)


@dataclass(frozen=True, slots=True)
class WindowFrameRange:
    first_frame_sequence: int
    last_frame_sequence: int
    post_window_complete: bool

    def __post_init__(self) -> None:
        first = self.first_frame_sequence
        last = self.last_frame_sequence
        if isinstance(first, bool) or isinstance(last, bool):
            raise ContractViolation("window frame sequences must be positive ints")
        if not isinstance(first, int) or not isinstance(last, int) or first < 1 or last < first:
            raise ContractViolation("windowFrameRange endpoints must be positive and ordered")
        if not isinstance(self.post_window_complete, bool):
            raise ContractViolation("postWindowComplete must be a bool")

    def expected_sequences(self) -> tuple[int, ...]:
        return tuple(range(self.first_frame_sequence, self.last_frame_sequence + 1))


@dataclass(frozen=True, slots=True)
class CaptureCompleteness:
    detector_id: str
    complete: bool
    capture_loss: bool
    missing_frame_sequences: tuple[int, ...]
    parameter_snapshot_mismatch: bool
    post_window_incomplete: bool


def evaluate_capture_completeness(
    entry: DetectorCapturePlan,
    *,
    parameter_snapshot_id: str | None,
    window: WindowFrameRange | None,
    present_frame_sequences: Sequence[int],
) -> CaptureCompleteness:
    """Compare a declared FeatureFrame range to the frames actually retained."""

    if not entry.capture_active or entry.effective_policy == "none":
        return CaptureCompleteness(
            detector_id=entry.detector_id,
            complete=True,
            capture_loss=False,
            missing_frame_sequences=(),
            parameter_snapshot_mismatch=False,
            post_window_incomplete=False,
        )
    present = {int(item) for item in present_frame_sequences}
    expected = window.expected_sequences() if window is not None else ()
    missing = tuple(item for item in expected if item not in present)
    snapshot_mismatch = (
        entry.parameter_snapshot_id is not None
        and parameter_snapshot_id != entry.parameter_snapshot_id
    )
    post_incomplete = window is None or not window.post_window_complete
    incomplete = bool(missing) or snapshot_mismatch or post_incomplete
    capture_loss = incomplete and entry.effective_policy == "required"
    return CaptureCompleteness(
        detector_id=entry.detector_id,
        complete=not incomplete,
        capture_loss=capture_loss,
        missing_frame_sequences=missing,
        parameter_snapshot_mismatch=snapshot_mismatch,
        post_window_incomplete=post_incomplete,
    )
