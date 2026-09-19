"""Immutable session-plan and occurrence DTOs from the frozen v2 contract."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar, Literal, Self

from .primitives import (
    MAX_SIGNED_INT64,
    BroadcastEpoch,
    ContractViolation,
    LineageId,
    MonotonicMs,
    OccurrenceId,
    ScalarType,
    SchemaVersion,
    Stage,
    validate_occurrence_lineage,
    validate_scalar,
)

_STAGE_RANK = {Stage.PRACTICE: 0, Stage.QUALIFYING: 1, Stage.RACE: 2}

OccurrenceStatus = Literal["active", "completed", "restarted", "superseded", "abandoned"]
SessionEndReason = Literal[
    "completed",
    "forward_transition",
    "rewind_superseded",
    "same_ref_restart",
    "stream_ended",
]
_OCCURRENCE_STATUSES = frozenset({"active", "completed", "restarted", "superseded", "abandoned"})
_STATUS_REASONS: dict[str, frozenset[str]] = {
    "completed": frozenset({"completed", "forward_transition"}),
    "restarted": frozenset({"same_ref_restart"}),
    "superseded": frozenset({"rewind_superseded"}),
    "abandoned": frozenset({"stream_ended"}),
}


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
class SessionOccurrence:
    """One retained run of one SessionRef. Encoded identity excludes the ref."""

    occurrence_id: OccurrenceId
    broadcast_epoch: BroadcastEpoch
    session_ref: SessionRef
    parent_id: OccurrenceId | None
    lineage_id: LineageId
    started_at_mono_ms: MonotonicMs
    ended_at_mono_ms: MonotonicMs | None
    end_reason: SessionEndReason | None
    status: OccurrenceStatus

    _FIELDS: ClassVar[frozenset[str]] = frozenset(
        {
            "occurrenceId",
            "broadcastEpoch",
            "sessionRef",
            "parentId",
            "lineageId",
            "startedAtMonoMs",
            "endedAtMonoMs",
            "endReason",
            "status",
        }
    )

    def __post_init__(self) -> None:
        if not isinstance(self.occurrence_id, OccurrenceId):
            raise ContractViolation("occurrenceId must be an OccurrenceId")
        object.__setattr__(
            self, "broadcast_epoch", BroadcastEpoch(self.broadcast_epoch).require_active()
        )
        if not isinstance(self.session_ref, SessionRef):
            raise ContractViolation("sessionRef must be a SessionRef")
        if self.parent_id is not None and not isinstance(self.parent_id, OccurrenceId):
            raise ContractViolation("parentId must be an OccurrenceId or null")
        if not isinstance(self.lineage_id, LineageId):
            raise ContractViolation("lineageId must be a LineageId")
        object.__setattr__(self, "started_at_mono_ms", MonotonicMs(self.started_at_mono_ms))
        if self.ended_at_mono_ms is not None:
            object.__setattr__(self, "ended_at_mono_ms", MonotonicMs(self.ended_at_mono_ms))
        if self.status not in _OCCURRENCE_STATUSES:
            raise ContractViolation(f"invalid occurrence status: {self.status!r}")
        validate_occurrence_lineage(self.occurrence_id, self.lineage_id)
        self._validate_parent()
        self._validate_terminal()

    def _validate_parent(self) -> None:
        occurrences = self.lineage_id.occurrences
        if self.parent_id is None:
            if occurrences != (self.occurrence_id,):
                raise ContractViolation("root occurrence lineage must be exactly itself")
            return
        if self.parent_id.stream_epoch != self.occurrence_id.stream_epoch:
            raise ContractViolation("parentId must share streamEpoch")
        if _STAGE_RANK[self.parent_id.stage] >= _STAGE_RANK[self.occurrence_id.stage]:
            raise ContractViolation("parentId must be an earlier canonical stage")
        if len(occurrences) < 2 or occurrences[-2] != self.parent_id:
            raise ContractViolation("parentId must be the immediate lineage ancestor")

    def _validate_terminal(self) -> None:
        if self.status == "active":
            if self.ended_at_mono_ms is not None or self.end_reason is not None:
                raise ContractViolation("active occurrence cannot carry an end")
            return
        if self.ended_at_mono_ms is None or self.end_reason is None:
            raise ContractViolation("closed occurrence requires endedAtMonoMs and endReason")
        allowed = _STATUS_REASONS[self.status]
        if self.end_reason not in allowed:
            raise ContractViolation(
                f"endReason {self.end_reason!r} is not valid for status {self.status!r}"
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "occurrenceId": str(self.occurrence_id),
            "broadcastEpoch": int(self.broadcast_epoch),
            "sessionRef": self.session_ref.to_dict(),
            "parentId": None if self.parent_id is None else str(self.parent_id),
            "lineageId": str(self.lineage_id),
            "startedAtMonoMs": int(self.started_at_mono_ms),
            "endedAtMonoMs": (
                None if self.ended_at_mono_ms is None else int(self.ended_at_mono_ms)
            ),
            "endReason": self.end_reason,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, value: object) -> Self:
        data = _exact_object(value, cls._FIELDS, "SessionOccurrence")
        return cls(
            occurrence_id=OccurrenceId.parse(data["occurrenceId"]),
            broadcast_epoch=data["broadcastEpoch"],
            session_ref=SessionRef.from_dict(data["sessionRef"]),
            parent_id=(None if data["parentId"] is None else OccurrenceId.parse(data["parentId"])),
            lineage_id=LineageId.parse(data["lineageId"]),
            started_at_mono_ms=data["startedAtMonoMs"],
            ended_at_mono_ms=data["endedAtMonoMs"],
            end_reason=data["endReason"],
            status=data["status"],
        )


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
