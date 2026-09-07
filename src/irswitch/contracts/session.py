"""Immutable session-plan DTOs from the frozen v2 schema contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Self

from .primitives import (
    MAX_SIGNED_INT64,
    ContractViolation,
    MonotonicMs,
    ScalarType,
    SchemaVersion,
    Stage,
    validate_scalar,
)

_STAGE_RANK = {Stage.PRACTICE: 0, Stage.QUALIFYING: 1, Stage.RACE: 2}


def _nonnegative_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractViolation(f"{field} must be a nonnegative integer")
    if not 0 <= value <= MAX_SIGNED_INT64:
        raise ContractViolation(f"{field} must fit a nonnegative signed 64-bit integer")
    return value


def _exact_object(value: object, fields: frozenset[str], label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ContractViolation(f"{label} must be a JSON object")
    actual = frozenset(value)
    if actual != fields:
        missing = sorted(fields - actual)
        unknown = sorted(actual - fields)
        raise ContractViolation(f"invalid {label} fields; missing={missing}, unknown={unknown}")
    return value


@dataclass(frozen=True, slots=True)
class SessionRef:
    sub_session_id: str
    session_num: int

    _FIELDS: ClassVar[frozenset[str]] = frozenset({"subSessionId", "sessionNum"})

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "sub_session_id", validate_scalar(ScalarType.ID, self.sub_session_id)
        )
        object.__setattr__(self, "session_num", _nonnegative_int(self.session_num, "sessionNum"))

    def to_dict(self) -> dict[str, Any]:
        return {"subSessionId": self.sub_session_id, "sessionNum": self.session_num}

    @classmethod
    def from_dict(cls, value: object) -> Self:
        data = _exact_object(value, cls._FIELDS, "SessionRef")
        return cls(data["subSessionId"], data["sessionNum"])


@dataclass(frozen=True, slots=True)
class SessionPlanEntry:
    session_ref: SessionRef
    stage: Stage

    _FIELDS: ClassVar[frozenset[str]] = frozenset({"sessionRef", "stage"})

    def __post_init__(self) -> None:
        if not isinstance(self.session_ref, SessionRef):
            raise ContractViolation("session plan entry requires a SessionRef")
        try:
            stage = Stage(self.stage)
        except (TypeError, ValueError) as exc:
            raise ContractViolation(f"invalid session plan stage: {self.stage!r}") from exc
        object.__setattr__(self, "stage", stage)

    def to_dict(self) -> dict[str, Any]:
        return {"sessionRef": self.session_ref.to_dict(), "stage": self.stage.value}

    @classmethod
    def from_dict(cls, value: object) -> Self:
        data = _exact_object(value, cls._FIELDS, "SessionPlan entry")
        return cls(SessionRef.from_dict(data["sessionRef"]), data["stage"])


@dataclass(frozen=True, slots=True)
class UnsupportedSessionEntry:
    session_num: int
    external_type: str

    _FIELDS: ClassVar[frozenset[str]] = frozenset({"sessionNum", "externalType"})

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_num", _nonnegative_int(self.session_num, "sessionNum"))
        if not isinstance(self.external_type, str):
            raise ContractViolation("externalType must be a string")

    def to_dict(self) -> dict[str, Any]:
        return {"sessionNum": self.session_num, "externalType": self.external_type}

    @classmethod
    def from_dict(cls, value: object) -> Self:
        data = _exact_object(value, cls._FIELDS, "unsupported session entry")
        return cls(data["sessionNum"], data["externalType"])


@dataclass(frozen=True, slots=True)
class SessionPlan:
    """Serializable bounded plan; prefix evolution belongs to StreamTimeline."""

    plan_revision: int
    captured_mono_ms: MonotonicMs
    sub_session_id: str | None
    valid: bool
    reason: str | None
    entries: tuple[SessionPlanEntry, ...]
    unsupported_entries: tuple[UnsupportedSessionEntry, ...]
    unsupported_overflow_count: int

    SCHEMA_VERSION: ClassVar[SchemaVersion] = SchemaVersion("session-plan/2")
    CONFLICT_REASON: ClassVar[str] = "session_plan_conflict"
    MAX_SUPPORTED_ENTRIES: ClassVar[int] = 3
    MAX_UNSUPPORTED_ENTRIES: ClassVar[int] = 16
    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "schemaVersion",
            "planRevision",
            "capturedMonoMs",
            "subSessionId",
            "valid",
            "reason",
            "entries",
            "unsupportedEntries",
            "unsupportedOverflowCount",
        }
    )

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "plan_revision", _nonnegative_int(self.plan_revision, "planRevision")
        )
        object.__setattr__(self, "captured_mono_ms", MonotonicMs(self.captured_mono_ms))
        if self.sub_session_id is not None:
            object.__setattr__(
                self,
                "sub_session_id",
                validate_scalar(ScalarType.ID, self.sub_session_id),
            )
        if not isinstance(self.valid, bool):
            raise ContractViolation("valid must be a JSON boolean")
        if self.reason is not None and not isinstance(self.reason, str):
            raise ContractViolation("reason must be a string or null")
        entries = tuple(self.entries)
        unsupported = tuple(self.unsupported_entries)
        if any(not isinstance(entry, SessionPlanEntry) for entry in entries):
            raise ContractViolation("entries must contain SessionPlanEntry values")
        if any(not isinstance(entry, UnsupportedSessionEntry) for entry in unsupported):
            raise ContractViolation(
                "unsupportedEntries must contain UnsupportedSessionEntry values"
            )
        if len(entries) > self.MAX_SUPPORTED_ENTRIES:
            raise ContractViolation("entries exceeds the three-stage bound")
        if len(unsupported) > self.MAX_UNSUPPORTED_ENTRIES:
            raise ContractViolation("unsupportedEntries exceeds the audit bound")
        overflow = _nonnegative_int(self.unsupported_overflow_count, "unsupportedOverflowCount")
        object.__setattr__(self, "entries", entries)
        object.__setattr__(self, "unsupported_entries", unsupported)
        object.__setattr__(self, "unsupported_overflow_count", overflow)
        if self.valid:
            self._validate_valid_shape()
        elif self.reason != self.CONFLICT_REASON or entries:
            raise ContractViolation(
                "invalid SessionPlan requires session_plan_conflict and empty entries"
            )

    def _validate_valid_shape(self) -> None:
        if self.sub_session_id is None or self.reason is not None or not self.entries:
            raise ContractViolation(
                "valid SessionPlan requires subSessionId, null reason and one to three entries"
            )
        session_nums = [entry.session_ref.session_num for entry in self.entries]
        stage_ranks = [_STAGE_RANK[entry.stage] for entry in self.entries]
        if any(entry.session_ref.sub_session_id != self.sub_session_id for entry in self.entries):
            raise ContractViolation("every SessionRef must match SessionPlan subSessionId")
        if session_nums != sorted(set(session_nums)):
            raise ContractViolation("sessionNum values must be unique and strictly increasing")
        if stage_ranks != sorted(set(stage_ranks)):
            raise ContractViolation("stages must be unique and in canonical order")

    @staticmethod
    def _bound_unsupported(
        values: tuple[UnsupportedSessionEntry, ...],
    ) -> tuple[tuple[UnsupportedSessionEntry, ...], int]:
        if any(not isinstance(entry, UnsupportedSessionEntry) for entry in values):
            raise ContractViolation(
                "unsupportedEntries must contain UnsupportedSessionEntry values"
            )
        return values[: SessionPlan.MAX_UNSUPPORTED_ENTRIES], max(
            0, len(values) - SessionPlan.MAX_UNSUPPORTED_ENTRIES
        )

    @classmethod
    def valid_plan(
        cls,
        *,
        plan_revision: int,
        captured_mono_ms: MonotonicMs | int,
        sub_session_id: str,
        entries: tuple[SessionPlanEntry, ...],
        unsupported_entries: tuple[UnsupportedSessionEntry, ...] = (),
    ) -> Self:
        retained, overflow = cls._bound_unsupported(tuple(unsupported_entries))
        return cls(
            plan_revision=plan_revision,
            captured_mono_ms=MonotonicMs(captured_mono_ms),
            sub_session_id=sub_session_id,
            valid=True,
            reason=None,
            entries=tuple(entries),
            unsupported_entries=retained,
            unsupported_overflow_count=overflow,
        )

    @classmethod
    def conflict(
        cls,
        *,
        plan_revision: int,
        captured_mono_ms: MonotonicMs | int,
        sub_session_id: str | None,
        unsupported_entries: tuple[UnsupportedSessionEntry, ...] = (),
    ) -> Self:
        retained, overflow = cls._bound_unsupported(tuple(unsupported_entries))
        return cls(
            plan_revision=plan_revision,
            captured_mono_ms=MonotonicMs(captured_mono_ms),
            sub_session_id=sub_session_id,
            valid=False,
            reason=cls.CONFLICT_REASON,
            entries=(),
            unsupported_entries=retained,
            unsupported_overflow_count=overflow,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schemaVersion": str(self.SCHEMA_VERSION),
            "planRevision": self.plan_revision,
            "capturedMonoMs": int(self.captured_mono_ms),
            "subSessionId": self.sub_session_id,
            "valid": self.valid,
            "reason": self.reason,
            "entries": [entry.to_dict() for entry in self.entries],
            "unsupportedEntries": [entry.to_dict() for entry in self.unsupported_entries],
            "unsupportedOverflowCount": self.unsupported_overflow_count,
        }

    @classmethod
    def from_dict(cls, value: object) -> Self:
        data = _exact_object(value, cls._FIELDS, "SessionPlan")
        if SchemaVersion(data["schemaVersion"]) != cls.SCHEMA_VERSION:
            raise ContractViolation("SessionPlan requires schemaVersion session-plan/2")
        raw_entries = data["entries"]
        raw_unsupported = data["unsupportedEntries"]
        if not isinstance(raw_entries, list) or not isinstance(raw_unsupported, list):
            raise ContractViolation("SessionPlan entries must be JSON arrays")
        return cls(
            plan_revision=data["planRevision"],
            captured_mono_ms=MonotonicMs(data["capturedMonoMs"]),
            sub_session_id=data["subSessionId"],
            valid=data["valid"],
            reason=data["reason"],
            entries=tuple(SessionPlanEntry.from_dict(entry) for entry in raw_entries),
            unsupported_entries=tuple(
                UnsupportedSessionEntry.from_dict(entry) for entry in raw_unsupported
            ),
            unsupported_overflow_count=data["unsupportedOverflowCount"],
        )
