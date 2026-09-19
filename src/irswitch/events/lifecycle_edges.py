"""Exact-once stream/session lifecycle triggers.

Projects confirmed StreamTimeline commands plus distinct checkered/hero-finish
edges onto the shared event contract. Does not import StreamTimeline,
NarrativeRuntime, DetectorBank, overlay tape or commentary. Not live-wired.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Literal

from irswitch.contracts.primitives import ContractViolation, Identifier, LineageId, OccurrenceId
from irswitch.contracts.session import SessionRef

SourceClass = Literal["lifecycle"]

LEGACY_STREAM_START = "STREAM_START"
CANONICAL_LIFECYCLE_KINDS = frozenset(
    {
        "STREAM_STARTED",
        "STREAM_ENDED",
        "SESSION_STARTED",
        "SESSION_ENDED",
        "SESSION_RESTARTED",
        "SESSION_CHECKERED",
        "FINISH",
    }
)
_INTERNAL_COMMAND_KINDS = frozenset(
    {
        "STREAM_STARTED",
        "STREAM_ENDED",
        "SESSION_STARTED",
        "SESSION_ENDED",
        "SESSION_RESTARTED",
    }
)
_START_REASONS = frozenset({"normal", "attached_live", "process_recovery", "enabled_mid_stream"})
_END_REASONS = frozenset(
    {
        "completed",
        "forward_transition",
        "rewind_superseded",
        "same_ref_restart",
        "stream_ended",
    }
)
_NARRATIVE = {
    "STREAM_STARTED": ("stream.started", "stream.lifecycle", "started"),
    "STREAM_ENDED": ("stream.ended", "stream.lifecycle", "ended"),
    "SESSION_STARTED": ("session.started", "session.lifecycle", "started"),
    "SESSION_ENDED": ("session.ended", "session.lifecycle", "ended"),
    "SESSION_RESTARTED": ("session.restarted", "session.lifecycle", "impulse"),
    "SESSION_CHECKERED": ("session.checkered", "race.control.flag", "result"),
    "FINISH": ("session.hero_finish", "race.session.finish", "result"),
}
_KIND_RANK = {
    "SESSION_ENDED": 0,
    "SESSION_CHECKERED": 1,
    "FINISH": 2,
    "STREAM_ENDED": 3,
    "STREAM_STARTED": 4,
    "SESSION_STARTED": 5,
    "SESSION_RESTARTED": 6,
}
_SESSION_COMMANDS = frozenset({"SESSION_STARTED", "SESSION_ENDED", "SESSION_RESTARTED"})
IDENTITY_CAPACITY = 256


def _optional_id(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ContractViolation(f"{field} must be an ID or null")
    return str(Identifier(value))


def _is_race_occurrence(occurrence_id: str | None, stage: str | None) -> bool:
    if stage == "race":
        return True
    if occurrence_id is None:
        return False
    return ":race:" in occurrence_id


@dataclass(frozen=True, slots=True)
class LifecycleIdentity:
    kind: str
    stream_epoch: int
    occurrence_id: str | None = None
    hero_id: str | None = None

    def candidate_id(self) -> str:
        parts = ["lifecycle", self.kind, str(self.stream_epoch)]
        if self.occurrence_id is not None:
            parts.append(self.occurrence_id)
        if self.hero_id is not None:
            parts.append(self.hero_id)
        return str(Identifier(":".join(parts)[:128]))


@dataclass(frozen=True, slots=True)
class LifecycleCommand:
    kind: str
    start_reason: str | None = None
    session_ref: SessionRef | None = None
    occurrence_id: str | None = None
    lineage_id: str | None = None
    end_reason: str | None = None

    def __post_init__(self) -> None:
        occurrence = (
            None if self.occurrence_id is None else str(OccurrenceId.parse(self.occurrence_id))
        )
        lineage = None if self.lineage_id is None else str(LineageId.parse(self.lineage_id))
        object.__setattr__(self, "occurrence_id", occurrence)
        object.__setattr__(self, "lineage_id", lineage)
        if self.session_ref is not None and not isinstance(self.session_ref, SessionRef):
            raise ContractViolation("sessionRef must be a SessionRef or null")


@dataclass(frozen=True, slots=True)
class LifecycleSample:
    timeline_revision: int
    observed_mono_ms: int
    source_snapshot_id: str
    broadcast_epoch: int
    stream_epoch: int
    narrative_run_active: bool
    obs_state: str
    session_ref: SessionRef | None
    stage: str | None
    occurrence_id: str | None
    lineage_id: str | None
    previous_occurrence_id: str | None
    previous_lineage_id: str | None
    transition_reasons: tuple[str, ...]
    commands: tuple[LifecycleCommand, ...]
    checkered_active: bool
    hero_finished: bool
    hero_id: str | None
    connected: bool

    def __post_init__(self) -> None:
        if isinstance(self.timeline_revision, bool) or self.timeline_revision < 1:
            raise ContractViolation("timelineRevision must be a positive integer")
        object.__setattr__(self, "source_snapshot_id", str(Identifier(self.source_snapshot_id)))
        if self.obs_state not in {"inactive", "active", "unknown"}:
            raise ContractViolation(f"unknown obsState {self.obs_state!r}")
        if self.stage not in {None, "practice", "qualifying", "race"}:
            raise ContractViolation(f"unknown stage {self.stage!r}")
        occurrence = (
            None if self.occurrence_id is None else str(OccurrenceId.parse(self.occurrence_id))
        )
        lineage = None if self.lineage_id is None else str(LineageId.parse(self.lineage_id))
        previous = (
            None
            if self.previous_occurrence_id is None
            else str(OccurrenceId.parse(self.previous_occurrence_id))
        )
        previous_lineage = (
            None
            if self.previous_lineage_id is None
            else str(LineageId.parse(self.previous_lineage_id))
        )
        present = (
            self.session_ref is not None,
            occurrence is not None,
            lineage is not None,
        )
        if any(present) and not all(present):
            raise ContractViolation(
                "sessionRef, occurrenceId and lineageId must be all coherent or all null"
            )
        if self.session_ref is not None and not isinstance(self.session_ref, SessionRef):
            raise ContractViolation("sessionRef must be a SessionRef or null")
        object.__setattr__(self, "occurrence_id", occurrence)
        object.__setattr__(self, "lineage_id", lineage)
        object.__setattr__(self, "previous_occurrence_id", previous)
        object.__setattr__(self, "previous_lineage_id", previous_lineage)
        object.__setattr__(self, "hero_id", _optional_id(self.hero_id, "heroId"))
        object.__setattr__(self, "transition_reasons", tuple(self.transition_reasons))
        object.__setattr__(self, "commands", tuple(self.commands))


@dataclass(frozen=True, slots=True)
class LifecycleCandidate:
    source_class: SourceClass
    kind: str
    narrative_kind: str
    tape_channel: str
    phase: str
    identity: LifecycleIdentity
    observed_mono_ms: int
    broadcast_epoch: int
    stream_epoch: int
    occurrence_id: str | None
    lineage_id: str | None
    previous_occurrence_id: str | None
    previous_lineage_id: str | None
    correlation_key: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    reason_code: str
    invalidate_speech: bool
    detector_observation_id: None = None


@dataclass(frozen=True, slots=True)
class LifecycleStep:
    accepted: bool
    diagnostic: str | None = None
    candidates: tuple[LifecycleCandidate, ...] = ()


class LifecycleTriggerBank:
    """Process-local lifecycle projector. Replay-deterministic."""

    def __init__(self, identity_capacity: int = IDENTITY_CAPACITY) -> None:
        self._identity_capacity = identity_capacity
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._last_revision: int | None = None
        self._checkered: set[str] = set()
        self._finished: set[tuple[str, str]] = set()

    def observe(self, sample: LifecycleSample) -> LifecycleStep:
        if self._last_revision is not None:
            if int(sample.timeline_revision) < self._last_revision:
                return LifecycleStep(False, "lifecycle_revision_stale")
            if int(sample.timeline_revision) == self._last_revision:
                return LifecycleStep(False, "lifecycle_revision_duplicate")
        self._last_revision = int(sample.timeline_revision)
        if int(sample.stream_epoch) < 1:
            return LifecycleStep(True)

        diagnostic: str | None = None
        built: list[LifecycleCandidate] = []
        closed_race: str | None = None
        for command in sample.commands:
            if command.kind == LEGACY_STREAM_START:
                diagnostic = diagnostic or "legacy_stream_start_rejected"
                continue
            if command.kind == "RESET" or command.kind not in _INTERNAL_COMMAND_KINDS:
                continue
            if command.kind in _SESSION_COMMANDS and command.occurrence_id is None:
                diagnostic = diagnostic or "lifecycle_missing_occurrence"
                continue
            if command.kind == "STREAM_STARTED" and command.start_reason not in _START_REASONS:
                diagnostic = diagnostic or "lifecycle_invalid_start_reason"
                continue
            if command.kind == "SESSION_ENDED" and command.end_reason not in _END_REASONS:
                diagnostic = diagnostic or "lifecycle_missing_end_reason"
                continue
            if command.kind == "SESSION_ENDED" and _is_race_occurrence(command.occurrence_id, None):
                closed_race = command.occurrence_id
            candidate = self._command_candidate(sample, command)
            if candidate is not None:
                built.append(candidate)

        edge_occurrence = self._edge_occurrence(sample, closed_race)
        if sample.connected or closed_race is not None:
            if sample.checkered_active:
                checkered = self._flag_candidate(
                    sample,
                    kind="SESSION_CHECKERED",
                    occurrence_id=edge_occurrence,
                    reason_code="session_checkered",
                    hero_id=None,
                )
                if checkered is not None:
                    built.append(checkered)
            if sample.hero_finished:
                finish = self._flag_candidate(
                    sample,
                    kind="FINISH",
                    occurrence_id=edge_occurrence,
                    reason_code="hero_finished",
                    hero_id=sample.hero_id,
                )
                if finish is not None:
                    built.append(finish)

        built.sort(key=lambda item: _KIND_RANK[item.kind])
        return LifecycleStep(True, diagnostic, tuple(built))

    def _command_candidate(
        self, sample: LifecycleSample, command: LifecycleCommand
    ) -> LifecycleCandidate | None:
        occurrence = command.occurrence_id
        identity = LifecycleIdentity(
            kind=command.kind,
            stream_epoch=int(sample.stream_epoch),
            occurrence_id=occurrence if command.kind in _SESSION_COMMANDS else None,
        )
        if not self._claim(identity):
            return None
        if command.kind == "STREAM_STARTED":
            reason = command.start_reason or "normal"
        elif command.kind == "STREAM_ENDED":
            reason = "broadcast_ended"
        elif command.kind == "SESSION_ENDED":
            reason = command.end_reason or "completed"
        elif command.kind == "SESSION_RESTARTED":
            reason = "session_restarted"
        else:
            reason = "session_started"
        return self._candidate(
            sample,
            identity,
            occurrence_id=occurrence if command.kind in _SESSION_COMMANDS else sample.occurrence_id,
            lineage_id=(
                command.lineage_id if command.kind in _SESSION_COMMANDS else sample.lineage_id
            ),
            reason_code=reason,
            invalidate_speech=command.kind == "STREAM_ENDED",
        )

    def _flag_candidate(
        self,
        sample: LifecycleSample,
        *,
        kind: str,
        occurrence_id: str | None,
        reason_code: str,
        hero_id: str | None,
    ) -> LifecycleCandidate | None:
        if occurrence_id is None or not _is_race_occurrence(occurrence_id, sample.stage):
            return None
        if kind == "FINISH" and hero_id is None:
            return None
        if kind == "SESSION_CHECKERED":
            if occurrence_id in self._checkered:
                return None
            self._checkered.add(occurrence_id)
        else:
            finish_key = (occurrence_id, hero_id or "")
            if finish_key in self._finished:
                return None
            self._finished.add(finish_key)
        identity = LifecycleIdentity(
            kind=kind,
            stream_epoch=int(sample.stream_epoch),
            occurrence_id=occurrence_id,
            hero_id=hero_id if kind == "FINISH" else None,
        )
        if not self._claim(identity):
            return None
        lineage = sample.lineage_id
        if lineage is None and occurrence_id == sample.previous_occurrence_id:
            lineage = sample.previous_lineage_id
        return self._candidate(
            sample,
            identity,
            occurrence_id=occurrence_id,
            lineage_id=lineage,
            reason_code=reason_code,
            invalidate_speech=False,
        )

    @staticmethod
    def _edge_occurrence(sample: LifecycleSample, closed_race: str | None) -> str | None:
        if sample.occurrence_id is not None and _is_race_occurrence(
            sample.occurrence_id, sample.stage
        ):
            return sample.occurrence_id
        if closed_race is not None:
            return closed_race
        if _is_race_occurrence(sample.previous_occurrence_id, None):
            return sample.previous_occurrence_id
        return None

    def _claim(self, identity: LifecycleIdentity) -> bool:
        key = identity.candidate_id()
        if key in self._seen:
            return False
        while len(self._seen) >= self._identity_capacity:
            self._seen.popitem(last=False)
        self._seen[key] = None
        return True

    @staticmethod
    def _candidate(
        sample: LifecycleSample,
        identity: LifecycleIdentity,
        *,
        occurrence_id: str | None,
        lineage_id: str | None,
        reason_code: str,
        invalidate_speech: bool,
    ) -> LifecycleCandidate:
        narrative, channel, phase = _NARRATIVE[identity.kind]
        parts = [identity.kind, f"epoch:{identity.stream_epoch}"]
        if occurrence_id is not None:
            parts.append(occurrence_id)
        if identity.hero_id is not None:
            parts.append(identity.hero_id)
        return LifecycleCandidate(
            source_class="lifecycle",
            kind=identity.kind,
            narrative_kind=narrative,
            tape_channel=channel,
            phase=phase,
            identity=identity,
            observed_mono_ms=int(sample.observed_mono_ms),
            broadcast_epoch=int(sample.broadcast_epoch),
            stream_epoch=int(sample.stream_epoch),
            occurrence_id=occurrence_id,
            lineage_id=lineage_id,
            previous_occurrence_id=sample.previous_occurrence_id,
            previous_lineage_id=sample.previous_lineage_id,
            correlation_key=tuple(parts),
            evidence_refs=(sample.source_snapshot_id, *sample.transition_reasons),
            reason_code=reason_code,
            invalidate_speech=invalidate_speech,
        )
