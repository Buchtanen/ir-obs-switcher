"""Deterministic StreamTimeline reducer. Sole streamEpoch owner in logic/.

Consumes debounced BroadcastClock epochs plus iRSDK session observations.
Does not import NarrativeRuntime, DetectorBank, mailbox or overlay tape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from irswitch.contracts.primitives import (
    LineageId,
    OccurrenceId,
    Stage,
    StreamEpoch,
)
from irswitch.contracts.session import (
    SessionPlan,
    SessionPlanEntry,
    SessionRef,
    UnsupportedSessionEntry,
)
from irswitch.logic.broadcast_clock import BroadcastClock, BroadcastClockSnapshot

ObsState = Literal["inactive", "active", "unknown"]
Availability = Literal["complete", "partial", "unavailable"]

REWIND_DROP_S = 5.0
REWIND_CONFIRM_MS = 100

TRANSITION_REASON_ORDER = (
    "session_ended",
    "session_superseded",
    "session_suspended",
    "narrative_disabled",
    "broadcast_ended",
    "broadcast_unknown",
    "broadcast_started",
    "attached_live",
    "process_recovery",
    "narrative_enabled",
    "broadcast_resumed",
    "session_started",
    "session_restarted",
    "session_resumed",
)

_STAGE_RANK = {Stage.PRACTICE: 0, Stage.QUALIFYING: 1, Stage.RACE: 2}
_START_REASON_TO_TRANSITION = {
    "normal": "broadcast_started",
    "attached_live": "attached_live",
    "process_recovery": "process_recovery",
    "enabled_mid_stream": "narrative_enabled",
}


def _stage_from_iracing(session_type: str) -> Stage | None:
    label = session_type.strip().lower()
    if not label:
        return None
    if "practice" in label or label == "practise":
        return Stage.PRACTICE
    if "qualify" in label:
        return Stage.QUALIFYING
    if "race" in label:
        return Stage.RACE
    return None


@dataclass(frozen=True, slots=True)
class SessionInfoRow:
    session_num: int
    session_type: str


@dataclass(frozen=True, slots=True)
class SessionObservation:
    connected: bool
    availability: Availability
    sub_session_id: str | None
    session_num: int | None
    session_time_s: float | None
    rows: tuple[SessionInfoRow, ...]
    track_id: int | None = None


@dataclass(frozen=True, slots=True)
class BroadcastObservation:
    epoch: int
    state: ObsState


@dataclass(frozen=True, slots=True)
class TimelineTick:
    now_ms: int
    broadcast: BroadcastObservation
    session: SessionObservation
    commentary_enabled: bool


@dataclass(frozen=True, slots=True)
class TimelineCommand:
    kind: str
    start_reason: str | None = None
    session_ref: SessionRef | None = None
    occurrence_id: str | None = None
    lineage_id: str | None = None


@dataclass(frozen=True, slots=True)
class TimelineStep:
    snapshot: dict[str, object]
    plan: SessionPlan | None
    commands: tuple[TimelineCommand, ...]
    diagnostics: tuple[str, ...] = ()


def observe_broadcast_clock(
    clock: BroadcastClock,
    *,
    now_s: float,
    streaming: bool | None,
    output_duration_seconds: float | None = None,
    broadcast_id: str | None = None,
) -> BroadcastObservation:
    """Map one BroadcastClock sample. Missing transport is unknown, not ended."""

    if streaming is None:
        snap: BroadcastClockSnapshot = clock.snapshot(now_s)
        return BroadcastObservation(epoch=snap.epoch, state="unknown")
    snap = clock.update(
        now=now_s,
        streaming=streaming,
        output_duration_seconds=output_duration_seconds,
        broadcast_id=broadcast_id,
    )
    return BroadcastObservation(epoch=snap.epoch, state="active" if snap.active else "inactive")


def compile_session_plan(
    *,
    sub_session_id: str | None,
    rows: tuple[SessionInfoRow, ...],
    captured_mono_ms: int,
    plan_revision: int,
) -> SessionPlan:
    """Compile one complete SessionInfo snapshot. Partial/unavailable callers skip this."""

    supported: list[SessionPlanEntry] = []
    unsupported: list[UnsupportedSessionEntry] = []
    identity_ok = True
    for row in rows:
        stage = _stage_from_iracing(row.session_type)
        if stage is None:
            unsupported.append(UnsupportedSessionEntry(row.session_num, row.session_type))
            continue
        if sub_session_id is None:
            identity_ok = False
            continue
        try:
            supported.append(SessionPlanEntry(SessionRef(sub_session_id, row.session_num), stage))
        except Exception:
            identity_ok = False

    if not identity_ok or not supported:
        return SessionPlan.conflict(
            plan_revision=plan_revision,
            captured_mono_ms=captured_mono_ms,
            sub_session_id=sub_session_id,
            unsupported_entries=tuple(unsupported),
        )
    ranks = [_STAGE_RANK[entry.stage] for entry in supported]
    nums = [entry.session_ref.session_num for entry in supported]
    if ranks != sorted(set(ranks)) or nums != sorted(set(nums)):
        return SessionPlan.conflict(
            plan_revision=plan_revision,
            captured_mono_ms=captured_mono_ms,
            sub_session_id=sub_session_id,
            unsupported_entries=tuple(unsupported),
        )
    ordered = tuple(
        sorted(
            supported, key=lambda entry: (_STAGE_RANK[entry.stage], entry.session_ref.session_num)
        )
    )
    if sub_session_id is None:
        return SessionPlan.conflict(
            plan_revision=plan_revision,
            captured_mono_ms=captured_mono_ms,
            sub_session_id=None,
            unsupported_entries=tuple(unsupported),
        )
    try:
        return SessionPlan.valid_plan(
            plan_revision=plan_revision,
            captured_mono_ms=captured_mono_ms,
            sub_session_id=sub_session_id,
            entries=ordered,
            unsupported_entries=tuple(unsupported),
        )
    except Exception:
        return SessionPlan.conflict(
            plan_revision=plan_revision,
            captured_mono_ms=captured_mono_ms,
            sub_session_id=sub_session_id,
            unsupported_entries=tuple(unsupported),
        )


def _order_reasons(reasons: list[str]) -> list[str]:
    unique = list(dict.fromkeys(reasons))
    rank = {name: index for index, name in enumerate(TRANSITION_REASON_ORDER)}
    return sorted(unique, key=lambda name: rank[name])


def _current_stage(session: SessionObservation) -> Stage | None:
    if session.session_num is None:
        return None
    for row in session.rows:
        if row.session_num == session.session_num:
            return _stage_from_iracing(row.session_type)
    if session.sub_session_id is None:
        return None
    return None


def _coherent_ref(session: SessionObservation, stage: Stage | None) -> SessionRef | None:
    if (
        not session.connected
        or session.sub_session_id is None
        or session.session_num is None
        or stage is None
    ):
        return None
    try:
        return SessionRef(session.sub_session_id, session.session_num)
    except Exception:
        return None


@dataclass
class StreamTimeline:
    """Process-local timeline reducer. Replay-deterministic for the same ticks."""

    process_recovery: bool = False
    _timeline_revision: int = 0
    _broadcast_epoch: int = 0
    _stream_epoch: int = 0
    _narrative_run_active: bool = False
    _obs_state: ObsState = "inactive"
    _history_complete: bool = False
    _had_run_in_broadcast: set[int] = field(default_factory=set)
    _plan: SessionPlan | None = None
    _prefix: tuple[SessionPlanEntry, ...] | None = None
    _latched_conflict: bool = False
    _session_ref: SessionRef | None = None
    _stage: Stage | None = None
    _occurrence: OccurrenceId | None = None
    _lineage: LineageId | None = None
    _retained_ref: SessionRef | None = None
    _retained_stage: Stage | None = None
    _retained_occurrence: OccurrenceId | None = None
    _retained_lineage: LineageId | None = None
    _last_session_time: float | None = None
    _rewind_since_ms: int | None = None
    _connected: bool = False
    _suspended: bool = False
    _ordinals: dict[Stage, int] = field(default_factory=dict)
    _active: dict[Stage, OccurrenceId] = field(default_factory=dict)
    _quarantined_ref: SessionRef | None = None
    _ever_allocated: bool = False
    _seen_obs: bool = False

    def observe(self, tick: TimelineTick) -> TimelineStep:
        reasons: list[str] = []
        commands: list[TimelineCommand] = []
        diagnostics: list[str] = []
        prev_state: ObsState | None = self._obs_state if self._seen_obs else None
        prev_run = self._narrative_run_active
        broadcast = tick.broadcast
        session = tick.session

        if not tick.commentary_enabled and self._narrative_run_active:
            reasons.append("narrative_disabled")
            self._close_run(retain_session=False)

        self._broadcast_epoch = broadcast.epoch
        if broadcast.state == "unknown":
            if prev_state == "active" and (prev_run or self._narrative_run_active):
                reasons.append("broadcast_unknown")
            self._obs_state = "unknown"
        elif broadcast.state == "inactive":
            if self._narrative_run_active:
                reasons.append("broadcast_ended")
                commands.append(TimelineCommand(kind="STREAM_ENDED"))
                self._close_run(retain_session=False)
            self._obs_state = "inactive"
        else:
            if prev_state == "unknown" and self._narrative_run_active and tick.commentary_enabled:
                reasons.append("broadcast_resumed")
            self._obs_state = "active"

        if (
            tick.commentary_enabled
            and self._obs_state == "active"
            and not self._narrative_run_active
        ):
            start_reason = self._allocate_start_reason(prev_state=prev_state)
            self._open_run(start_reason)
            reasons.append(_START_REASON_TO_TRANSITION[start_reason])
            commands.append(TimelineCommand(kind="STREAM_STARTED", start_reason=start_reason))
        self._seen_obs = True

        if self._narrative_run_active:
            self._apply_session(tick, session, reasons, commands, diagnostics)
            if not self._quarantined_ref:
                self._apply_plan(tick, session, reasons, commands, diagnostics)
        else:
            self._clear_current_session()
            self._rewind_since_ms = None

        reasons = _order_reasons(reasons)
        commands = self._order_commands(commands, reasons)
        self._timeline_revision += 1
        snapshot = self._snapshot(tick.now_ms, reasons)
        return TimelineStep(
            snapshot=snapshot,
            plan=self._plan,
            commands=tuple(commands),
            diagnostics=tuple(dict.fromkeys(diagnostics)),
        )

    def _allocate_start_reason(self, *, prev_state: ObsState | None) -> str:
        if self.process_recovery and not self._ever_allocated:
            return "process_recovery"
        if self._broadcast_epoch in self._had_run_in_broadcast:
            return "enabled_mid_stream"
        if prev_state in {"inactive", "unknown"}:
            return "normal"
        return "attached_live"

    def _open_run(self, start_reason: str) -> None:
        self._stream_epoch += 1
        self._narrative_run_active = True
        self._ever_allocated = True
        self._had_run_in_broadcast.add(self._broadcast_epoch)
        self._history_complete = start_reason == "normal"
        self._latched_conflict = False
        self._prefix = None
        self._plan = None
        self._ordinals = {}
        self._active = {}
        self._quarantined_ref = None
        self._clear_current_session()
        self._retained_ref = None
        self._retained_stage = None
        self._retained_occurrence = None
        self._retained_lineage = None
        self._last_session_time = None
        self._rewind_since_ms = None
        self._suspended = False

    def _close_run(self, *, retain_session: bool) -> None:
        self._narrative_run_active = False
        if not retain_session:
            self._clear_current_session()
        self._rewind_since_ms = None

    def _clear_current_session(self) -> None:
        self._session_ref = None
        self._stage = None
        self._occurrence = None
        self._lineage = None

    def _apply_plan(
        self,
        tick: TimelineTick,
        session: SessionObservation,
        reasons: list[str],
        commands: list[TimelineCommand],
        diagnostics: list[str],
    ) -> None:
        if session.availability != "complete" or not session.connected:
            return
        next_revision = 1 if self._plan is None else self._plan.plan_revision
        candidate = compile_session_plan(
            sub_session_id=session.sub_session_id,
            rows=session.rows,
            captured_mono_ms=tick.now_ms,
            plan_revision=next_revision,
        )
        if self._latched_conflict:
            return
        if not candidate.valid:
            if self._prefix is None and self._plan is None:
                self._plan = candidate
                self._latched_conflict = True
                self._clear_identity(reasons, commands, diagnostics, "session_plan_conflict")
                return
            self._publish_conflict(tick, session, commands, diagnostics)
            return
        entries = candidate.entries
        if self._prefix is None:
            self._prefix = entries
            self._plan = candidate
            return
        if entries == self._prefix:
            return
        if self._is_legal_append(self._prefix, entries) and self._plan is not None:
            self._prefix = entries
            self._plan = SessionPlan.valid_plan(
                plan_revision=self._plan.plan_revision + 1,
                captured_mono_ms=tick.now_ms,
                sub_session_id=candidate.sub_session_id or session.sub_session_id or "sub:0",
                entries=entries,
                unsupported_entries=candidate.unsupported_entries,
            )
            return
        self._publish_conflict(tick, session, commands, diagnostics)

    def _is_legal_append(
        self, prefix: tuple[SessionPlanEntry, ...], entries: tuple[SessionPlanEntry, ...]
    ) -> bool:
        if len(entries) <= len(prefix) or entries[: len(prefix)] != prefix:
            return False
        last = prefix[-1]
        for extra in entries[len(prefix) :]:
            if extra.session_ref.session_num <= last.session_ref.session_num:
                return False
            if _STAGE_RANK[extra.stage] <= _STAGE_RANK[last.stage]:
                return False
            last = extra
        return True

    def _publish_conflict(
        self,
        tick: TimelineTick,
        session: SessionObservation,
        commands: list[TimelineCommand],
        diagnostics: list[str],
    ) -> None:
        revision = 1 if self._plan is None else self._plan.plan_revision + 1
        self._plan = SessionPlan.conflict(
            plan_revision=revision,
            captured_mono_ms=tick.now_ms,
            sub_session_id=session.sub_session_id,
            unsupported_entries=(),
        )
        self._latched_conflict = True
        self._clear_identity([], commands, diagnostics, "session_plan_conflict")

    def _clear_identity(
        self,
        reasons: list[str],
        commands: list[TimelineCommand],
        diagnostics: list[str],
        diagnostic: str,
    ) -> None:
        if self._session_ref is not None:
            self._retain_current()
            self._clear_current_session()
        diagnostics.append(diagnostic)
        commands.append(TimelineCommand(kind="RESET"))

    def _retain_current(self) -> None:
        self._retained_ref = self._session_ref
        self._retained_stage = self._stage
        self._retained_occurrence = self._occurrence
        self._retained_lineage = self._lineage

    def _apply_session(
        self,
        tick: TimelineTick,
        session: SessionObservation,
        reasons: list[str],
        commands: list[TimelineCommand],
        diagnostics: list[str],
    ) -> None:
        if self._latched_conflict:
            self._clear_current_session()
            if session.availability != "complete" or not session.connected:
                reasons.append("session_suspended")
            return
        if not session.connected:
            if self._session_ref is not None:
                self._retain_current()
                self._clear_current_session()
                self._suspended = True
                reasons.append("session_suspended")
            self._connected = False
            self._rewind_since_ms = None
            return
        if session.availability != "complete":
            if self._session_ref is not None or self._retained_ref is not None:
                if self._session_ref is not None:
                    self._retain_current()
                self._clear_current_session()
                self._suspended = True
                reasons.append("session_suspended")
            self._rewind_since_ms = None
            return

        stage = _current_stage(session)
        ref = _coherent_ref(session, stage)
        if ref is None or stage is None:
            if self._session_ref is not None:
                self._retain_current()
                self._clear_current_session()
            self._rewind_since_ms = None
            self._connected = True
            return

        if self._quarantined_ref == ref:
            diagnostics.append("session_identity_conflict")
            self._connected = True
            return

        if self._suspended and self._retained_ref == ref and self._retained_occurrence is not None:
            self._session_ref = self._retained_ref
            self._stage = self._retained_stage
            self._occurrence = self._retained_occurrence
            self._lineage = self._retained_lineage
            self._suspended = False
            self._connected = True
            self._last_session_time = session.session_time_s
            reasons.append("session_resumed")
            return

        if self._session_ref is None:
            self._start_occurrence(ref, stage, reasons, commands)
            self._last_session_time = session.session_time_s
            self._connected = True
            self._suspended = False
            return

        if self._session_ref is not None and ref != self._session_ref:
            backward = _STAGE_RANK[stage] < _STAGE_RANK[self._stage] if self._stage else False
            self._end_occurrence(reasons, commands, superseded=backward)
            self._start_occurrence(ref, stage, reasons, commands)
            self._last_session_time = session.session_time_s
            self._rewind_since_ms = None
            self._connected = True
            return

        if self._session_ref == ref and self._stage is not None and stage != self._stage:
            diagnostics.append("session_identity_conflict")
            self._quarantined_ref = ref
            commands.append(TimelineCommand(kind="RESET"))
            self._connected = True
            return

        self._connected = True
        self._maybe_rewind(tick, session, reasons, commands)

    def _maybe_rewind(
        self,
        tick: TimelineTick,
        session: SessionObservation,
        reasons: list[str],
        commands: list[TimelineCommand],
    ) -> None:
        current = session.session_time_s
        if current is None or self._last_session_time is None or self._session_ref is None:
            self._rewind_since_ms = None
            if current is not None:
                self._last_session_time = current
            return
        if self._last_session_time - current > REWIND_DROP_S:
            if self._rewind_since_ms is None:
                self._rewind_since_ms = tick.now_ms
                return
            if tick.now_ms - self._rewind_since_ms < REWIND_CONFIRM_MS:
                return
            assert self._stage is not None
            self._restart_occurrence(self._session_ref, self._stage, reasons, commands)
            self._last_session_time = current
            self._rewind_since_ms = None
            return
        self._rewind_since_ms = None
        self._last_session_time = max(self._last_session_time, current)

    def _start_occurrence(
        self,
        ref: SessionRef,
        stage: Stage,
        reasons: list[str],
        commands: list[TimelineCommand],
    ) -> None:
        occurrence, lineage = self._allocate(stage)
        self._session_ref = ref
        self._stage = stage
        self._occurrence = occurrence
        self._lineage = lineage
        self._suspended = False
        reasons.append("session_started")
        commands.append(
            TimelineCommand(
                kind="SESSION_STARTED",
                session_ref=ref,
                occurrence_id=str(occurrence),
                lineage_id=str(lineage),
            )
        )

    def _end_occurrence(
        self, reasons: list[str], commands: list[TimelineCommand], *, superseded: bool
    ) -> None:
        if self._occurrence is None or self._session_ref is None:
            return
        reasons.append("session_ended")
        commands.append(
            TimelineCommand(
                kind="SESSION_ENDED",
                session_ref=self._session_ref,
                occurrence_id=str(self._occurrence),
                lineage_id=None if self._lineage is None else str(self._lineage),
            )
        )
        if superseded:
            reasons.append("session_superseded")
            dropped = [
                stage
                for stage in self._active
                if _STAGE_RANK[stage] >= _STAGE_RANK[self._stage or stage]
            ]
            for stage in dropped:
                self._active.pop(stage, None)
        else:
            if self._stage is not None:
                self._active[self._stage] = self._occurrence

    def _restart_occurrence(
        self,
        ref: SessionRef,
        stage: Stage,
        reasons: list[str],
        commands: list[TimelineCommand],
    ) -> None:
        occurrence, lineage = self._allocate(stage)
        self._session_ref = ref
        self._stage = stage
        self._occurrence = occurrence
        self._lineage = lineage
        reasons.append("session_restarted")
        commands.append(
            TimelineCommand(
                kind="SESSION_RESTARTED",
                session_ref=ref,
                occurrence_id=str(occurrence),
                lineage_id=str(lineage),
            )
        )

    def _allocate(self, stage: Stage) -> tuple[OccurrenceId, LineageId]:
        ordinal = self._ordinals.get(stage, 0)
        self._ordinals[stage] = ordinal + 1
        occurrence = OccurrenceId(StreamEpoch(self._stream_epoch), stage, ordinal)
        kept = {
            item_stage: item
            for item_stage, item in self._active.items()
            if _STAGE_RANK[item_stage] < _STAGE_RANK[stage]
        }
        kept[stage] = occurrence
        self._active = kept
        lineage = LineageId(
            tuple(
                kept[item]
                for item in (Stage.PRACTICE, Stage.QUALIFYING, Stage.RACE)
                if item in kept
            )
        )
        return occurrence, lineage

    def _order_commands(
        self, commands: list[TimelineCommand], reasons: list[str]
    ) -> list[TimelineCommand]:
        kind_rank = {
            "SESSION_ENDED": 0,
            "RESET": 1,
            "STREAM_ENDED": 2,
            "STREAM_STARTED": 3,
            "SESSION_STARTED": 4,
            "SESSION_RESTARTED": 5,
        }
        return sorted(commands, key=lambda item: kind_rank.get(item.kind, 9))

    def _snapshot(self, now_ms: int, reasons: list[str]) -> dict[str, object]:
        session_ref = self._session_ref
        stage = self._stage
        occurrence = self._occurrence
        lineage = self._lineage
        coherent = (
            session_ref is not None
            and stage is not None
            and occurrence is not None
            and lineage is not None
            and self._narrative_run_active
        )
        return {
            "schemaVersion": "timeline-snapshot/2",
            "timelineRevision": self._timeline_revision,
            "observedMonoMs": now_ms,
            "broadcastEpoch": self._broadcast_epoch,
            "streamEpoch": self._stream_epoch,
            "narrativeRunActive": self._narrative_run_active,
            "obsState": self._obs_state,
            "sessionRef": session_ref.to_dict() if coherent and session_ref is not None else None,
            "stage": stage.value if coherent and stage is not None else None,
            "sessionPlanRevision": None if self._plan is None else self._plan.plan_revision,
            "occurrenceId": str(occurrence) if coherent and occurrence is not None else None,
            "lineageId": str(lineage) if coherent and lineage is not None else None,
            "historyComplete": self._history_complete if self._narrative_run_active else False,
            "transitionReasons": reasons,
        }
