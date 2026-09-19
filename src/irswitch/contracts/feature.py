"""Immutable FeatureFrame DTOs and the frozen 21-ID feature registry."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, ClassVar, Self

from .primitives import (
    MAX_SIGNED_INT64,
    ContractViolation,
    FactQuality,
    Identifier,
    LineageId,
    OccurrenceId,
    ScalarType,
    SchemaVersion,
    validate_occurrence_lineage,
)
from .resources import packaged_schema_bytes
from .session import SessionRef

FIRST_SLICE_FEATURE_ID = "gap.relation.seconds.estimated_v1"

_FEATURE_VALUE_TYPES = (bool, int, float, str)
_COMPATIBLE_PARAMETER_UNITS = {
    "gap_seconds": ScalarType.SECONDS.value,
}
_SECONDS_PARAMETER_SUFFIXES = ("_s",)
_ALLOWED_PARAMETER_UNITS = frozenset(item.value for item in ScalarType) | frozenset(
    _COMPATIBLE_PARAMETER_UNITS
)


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractViolation(f"{field} must be a nonnegative integer")
    if not 0 <= value <= MAX_SIGNED_INT64:
        raise ContractViolation(f"{field} must fit a nonnegative signed 64-bit integer")
    return value


def _positive_int(value: object, field: str) -> int:
    number = _nonnegative_int(value, field)
    if number < 1:
        raise ContractViolation(f"{field} must be a positive integer")
    return number


def _exact_object(value: object, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ContractViolation(f"{label} must be a JSON object")
    actual = frozenset(value)
    if actual != fields:
        missing = sorted(fields - actual)
        unknown = sorted(actual - fields)
        raise ContractViolation(f"invalid {label} fields; missing={missing}, unknown={unknown}")
    return value


def _optional_id(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ContractViolation(f"{field} must be an ID or null")
    return str(Identifier(value))


def _id_tuple(value: object, field: str, minimum: int, maximum: int) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)) or not minimum <= len(value) <= maximum:
        raise ContractViolation(f"{field} must contain {minimum}..{maximum} unique IDs")
    items = tuple(str(Identifier(item)) for item in value)
    if len(set(items)) != len(items):
        raise ContractViolation(f"{field} must be unique")
    return items


def _coerce_occurrence(value: OccurrenceId | str | None) -> OccurrenceId | None:
    if value is None or isinstance(value, OccurrenceId):
        return value
    return OccurrenceId.parse(value)


def _coerce_lineage(value: LineageId | str | None) -> LineageId | None:
    if value is None or isinstance(value, LineageId):
        return value
    return LineageId.parse(value)


def _canonical_parameter_unit(unit: str) -> str:
    return _COMPATIBLE_PARAMETER_UNITS.get(unit, unit)


@dataclass(frozen=True, slots=True)
class FeatureDefinition:
    feature_id: str
    unit: str
    algorithm_id: str
    definition: str
    unknown_when: str


@dataclass(frozen=True, slots=True)
class FeatureRegistry:
    features: tuple[FeatureDefinition, ...]

    def require(self, feature_id: str) -> FeatureDefinition:
        for spec in self.features:
            if spec.feature_id == feature_id:
                return spec
        raise ContractViolation(f"unregistered feature: {feature_id!r}")


@lru_cache(maxsize=1)
def load_feature_registry() -> FeatureRegistry:
    raw = json.loads(packaged_schema_bytes("freeze-registry.json"))
    features = tuple(
        FeatureDefinition(
            feature_id=str(Identifier(row["id"])),
            unit=str(row["scalarType"]),
            algorithm_id=str(Identifier(row["id"])),
            definition=str(row["definition"]),
            unknown_when=str(row["unknownWhen"]),
        )
        for row in raw["features"]
    )
    if len(features) != 21:
        raise ContractViolation("feature registry must contain exactly 21 IDs")
    ids = [item.feature_id for item in features]
    if len(set(ids)) != len(ids):
        raise ContractViolation("feature registry IDs must be unique")
    return FeatureRegistry(features)


def validate_detector_feature_units() -> None:
    """Reject catalog feature IDs or parameter units that the registry does not own."""

    registry = load_feature_registry()
    known_units = {spec.feature_id: spec.unit for spec in registry.features}
    catalog = json.loads(packaged_schema_bytes("detector-catalog.json"))
    for detector in catalog.get("definitions") or []:
        detector_id = detector.get("id", "<unknown>")
        for feature_id in detector.get("features") or []:
            if feature_id not in known_units:
                raise ContractViolation(
                    f"unregistered feature {feature_id!r} on detector {detector_id!r}"
                )
        seconds_features = {
            feature_id
            for feature_id, unit in known_units.items()
            if feature_id in set(detector.get("features") or [])
            and unit == ScalarType.SECONDS.value
        }
        for parameter in detector.get("parameters") or []:
            param_id = str(parameter.get("id", ""))
            unit = str(parameter.get("unit", ""))
            if unit not in _ALLOWED_PARAMETER_UNITS:
                raise ContractViolation(
                    f"detector {detector_id!r} parameter {param_id!r} has unknown unit {unit!r}"
                )
            canonical = _canonical_parameter_unit(unit)
            if param_id.endswith(_SECONDS_PARAMETER_SUFFIXES) and canonical not in {
                ScalarType.SECONDS.value,
                ScalarType.SECONDS_PER_SECOND.value,
            }:
                raise ContractViolation(
                    f"detector {detector_id!r} parameter {param_id!r} unit {unit!r} is not seconds"
                )
            if unit == "gap_seconds" and not seconds_features:
                raise ContractViolation(
                    f"detector {detector_id!r} uses gap_seconds without a seconds feature"
                )


@dataclass(frozen=True, slots=True)
class FeatureValue:
    feature_id: str
    value: bool | int | float | str
    unit: str
    quality: FactQuality
    observed_mono_ms: int
    valid_until_mono_ms: int | None
    evidence_refs: tuple[str, ...]

    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "featureId",
            "value",
            "unit",
            "quality",
            "observedMonoMs",
            "validUntilMonoMs",
            "evidenceRefs",
        }
    )

    def __post_init__(self) -> None:
        object.__setattr__(self, "feature_id", str(Identifier(self.feature_id)))
        spec = load_feature_registry().require(self.feature_id)
        if self.value is None or isinstance(self.value, (list, dict)):
            raise ContractViolation("FeatureValue.value must be boolean, number, or string")
        if not isinstance(self.value, _FEATURE_VALUE_TYPES):
            raise ContractViolation("FeatureValue.value must be boolean, number, or string")
        if isinstance(self.value, bool):
            pass
        elif isinstance(self.value, float) and self.value != self.value:
            raise ContractViolation("FeatureValue.value must be finite")
        object.__setattr__(self, "unit", str(self.unit))
        if self.unit != spec.unit:
            raise ContractViolation(
                f"feature {self.feature_id} requires unit {spec.unit}, got {self.unit!r}"
            )
        object.__setattr__(self, "quality", FactQuality(self.quality))
        object.__setattr__(
            self, "observed_mono_ms", _nonnegative_int(self.observed_mono_ms, "observedMonoMs")
        )
        if self.valid_until_mono_ms is not None:
            object.__setattr__(
                self,
                "valid_until_mono_ms",
                _nonnegative_int(self.valid_until_mono_ms, "validUntilMonoMs"),
            )
            if int(self.valid_until_mono_ms) < int(self.observed_mono_ms):
                raise ContractViolation("validUntilMonoMs must be >= observedMonoMs")
        object.__setattr__(
            self, "evidence_refs", _id_tuple(self.evidence_refs, "evidenceRefs", 1, 16)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "featureId": self.feature_id,
            "value": self.value,
            "unit": self.unit,
            "quality": self.quality.value,
            "observedMonoMs": int(self.observed_mono_ms),
            "validUntilMonoMs": (
                None if self.valid_until_mono_ms is None else int(self.valid_until_mono_ms)
            ),
            "evidenceRefs": list(self.evidence_refs),
        }

    @classmethod
    def from_dict(cls, value: object) -> Self:
        data = _exact_object(value, cls._FIELDS, "FeatureValue")
        return cls(
            feature_id=data["featureId"],
            value=data["value"],
            unit=data["unit"],
            quality=data["quality"],
            observed_mono_ms=data["observedMonoMs"],
            valid_until_mono_ms=data["validUntilMonoMs"],
            evidence_refs=tuple(data["evidenceRefs"]),
        )


@dataclass(frozen=True, slots=True)
class FeatureFrame:
    frame_sequence: int
    observed_mono_ms: int
    source_snapshot_id: str
    broadcast_epoch: int
    stream_epoch: int
    session_ref: SessionRef | None
    occurrence_id: OccurrenceId | str | None
    lineage_id: LineageId | str | None
    correlation_key: tuple[str, ...]
    values: tuple[FeatureValue, ...]

    SCHEMA_VERSION: ClassVar[SchemaVersion] = SchemaVersion("feature-frame/2")
    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "schemaVersion",
            "frameSequence",
            "observedMonoMs",
            "sourceSnapshotId",
            "broadcastEpoch",
            "streamEpoch",
            "sessionRef",
            "occurrenceId",
            "lineageId",
            "correlationKey",
            "values",
        }
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "frame_sequence", _positive_int(self.frame_sequence, "frameSequence")
        )
        object.__setattr__(
            self, "observed_mono_ms", _nonnegative_int(self.observed_mono_ms, "observedMonoMs")
        )
        object.__setattr__(self, "source_snapshot_id", str(Identifier(self.source_snapshot_id)))
        object.__setattr__(
            self, "broadcast_epoch", _nonnegative_int(self.broadcast_epoch, "broadcastEpoch")
        )
        object.__setattr__(self, "stream_epoch", _nonnegative_int(self.stream_epoch, "streamEpoch"))
        session_ref = self.session_ref
        if session_ref is not None and not isinstance(session_ref, SessionRef):
            raise ContractViolation("sessionRef must be a SessionRef or null")
        occurrence = _coerce_occurrence(self.occurrence_id)
        lineage = _coerce_lineage(self.lineage_id)
        present = (session_ref is not None, occurrence is not None, lineage is not None)
        if any(present) and not all(present):
            raise ContractViolation(
                "sessionRef, occurrenceId and lineageId must be all coherent or all null"
            )
        if all(present):
            occurrence, lineage = validate_occurrence_lineage(occurrence, lineage)
        object.__setattr__(self, "occurrence_id", occurrence)
        object.__setattr__(self, "lineage_id", lineage)
        object.__setattr__(
            self, "correlation_key", _id_tuple(self.correlation_key, "correlationKey", 1, 8)
        )
        values = tuple(self.values)
        if any(not isinstance(item, FeatureValue) for item in values):
            raise ContractViolation("FeatureFrame values must contain FeatureValue items")
        if len(values) > 64:
            raise ContractViolation("FeatureFrame values exceeds the 64-field bound")
        ids = [item.feature_id for item in values]
        if len(set(ids)) != len(ids):
            raise ContractViolation("FeatureFrame feature identities must be unique")
        if ids != sorted(ids):
            raise ContractViolation("FeatureFrame values must be sorted by featureId")
        object.__setattr__(self, "values", values)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": str(self.SCHEMA_VERSION),
            "frameSequence": int(self.frame_sequence),
            "observedMonoMs": int(self.observed_mono_ms),
            "sourceSnapshotId": self.source_snapshot_id,
            "broadcastEpoch": int(self.broadcast_epoch),
            "streamEpoch": int(self.stream_epoch),
            "sessionRef": None if self.session_ref is None else self.session_ref.to_dict(),
            "occurrenceId": None if self.occurrence_id is None else str(self.occurrence_id),
            "lineageId": None if self.lineage_id is None else str(self.lineage_id),
            "correlationKey": list(self.correlation_key),
            "values": [item.to_dict() for item in self.values],
        }

    @classmethod
    def from_dict(cls, value: object) -> Self:
        data = _exact_object(value, cls._FIELDS, "FeatureFrame")
        if SchemaVersion(data["schemaVersion"]) != cls.SCHEMA_VERSION:
            raise ContractViolation("FeatureFrame requires schemaVersion feature-frame/2")
        session = data["sessionRef"]
        return cls(
            frame_sequence=data["frameSequence"],
            observed_mono_ms=data["observedMonoMs"],
            source_snapshot_id=data["sourceSnapshotId"],
            broadcast_epoch=data["broadcastEpoch"],
            stream_epoch=data["streamEpoch"],
            session_ref=None if session is None else SessionRef.from_dict(session),
            occurrence_id=data["occurrenceId"],
            lineage_id=data["lineageId"],
            correlation_key=tuple(data["correlationKey"]),
            values=tuple(FeatureValue.from_dict(item) for item in data["values"]),
        )
