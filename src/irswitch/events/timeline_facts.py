"""Compile StreamTimeline commands into typed AtomicFacts.

Consumes immutable timeline snapshot/command/occurrence projections only.
Does not import StreamTimeline, NarrativeRuntime, DetectorBank or overlay tape.
"""

from __future__ import annotations

from typing import Any, Protocol

from irswitch.contracts.fact import AtomicFact
from irswitch.contracts.primitives import ContractViolation, Stage
from irswitch.contracts.session import SessionOccurrence, SessionPlan

_STREAM_START_REASONS = frozenset(
    {"normal", "attached_live", "process_recovery", "enabled_mid_stream"}
)
_ATTACHED_STREAM = frozenset({"attached_live", "process_recovery", "enabled_mid_stream"})
_STAGE_RANK = {Stage.PRACTICE: 0, Stage.QUALIFYING: 1, Stage.RACE: 2}


class TimelineFactCommand(Protocol):
    kind: str
    start_reason: str | None
    occurrence_id: str | None
    lineage_id: str | None


def compile_timeline_facts(
    *,
    snapshot: dict[str, Any],
    commands: tuple[TimelineFactCommand, ...],
    occurrences: tuple[SessionOccurrence, ...],
    plan: SessionPlan | None = None,
) -> tuple[AtomicFact, ...]:
    """Map one TimelineStep into registry timeline facts, preserving command order."""

    now_ms = _require_int(snapshot.get("observedMonoMs"), "observedMonoMs")
    broadcast_epoch = _require_int(snapshot.get("broadcastEpoch"), "broadcastEpoch")
    stream_epoch = _require_int(snapshot.get("streamEpoch"), "streamEpoch")
    if broadcast_epoch < 1 or stream_epoch < 1:
        return ()
    records = {str(item.occurrence_id): item for item in occurrences}
    stream_start = next(
        (item.start_reason for item in commands if item.kind == "STREAM_STARTED"), None
    )
    facts: list[AtomicFact] = []
    for command in commands:
        if command.kind == "STREAM_STARTED":
            facts.append(
                _stream_started(
                    now_ms=now_ms,
                    broadcast_epoch=broadcast_epoch,
                    stream_epoch=stream_epoch,
                    start_reason=command.start_reason,
                )
            )
            continue
        if command.kind == "SESSION_STARTED":
            facts.append(
                _session_started(
                    now_ms=now_ms,
                    broadcast_epoch=broadcast_epoch,
                    stream_epoch=stream_epoch,
                    command=command,
                    records=records,
                    stream_start=stream_start,
                    commands=commands,
                )
            )
            continue
        if command.kind == "SESSION_RESTARTED":
            facts.append(
                _session_restarted(
                    now_ms=now_ms,
                    broadcast_epoch=broadcast_epoch,
                    stream_epoch=stream_epoch,
                    command=command,
                    records=records,
                )
            )
            continue
        if command.kind == "SESSION_ENDED":
            facts.append(
                _session_ended(
                    now_ms=now_ms,
                    broadcast_epoch=broadcast_epoch,
                    stream_epoch=stream_epoch,
                    command=command,
                    records=records,
                )
            )
    next_stage = _next_present_stage(
        snapshot=snapshot,
        plan=plan,
        now_ms=now_ms,
        broadcast_epoch=broadcast_epoch,
        stream_epoch=stream_epoch,
    )
    if next_stage is not None:
        facts.append(next_stage)
    return tuple(facts)


def _stream_started(
    *,
    now_ms: int,
    broadcast_epoch: int,
    stream_epoch: int,
    start_reason: str | None,
) -> AtomicFact:
    if start_reason not in _STREAM_START_REASONS:
        raise ContractViolation(f"invalid stream startReason: {start_reason!r}")
    return _fact(
        fact_id=f"fact:timeline:stream.started:{stream_epoch}",
        predicate="stream.started",
        attributes={"startReason": start_reason},
        scope="stream",
        now_ms=now_ms,
        broadcast_epoch=broadcast_epoch,
        stream_epoch=stream_epoch,
        occurrence_id=None,
        lineage_id=None,
        evidence=f"timeline:stream_started:{stream_epoch}",
    )


def _session_started(
    *,
    now_ms: int,
    broadcast_epoch: int,
    stream_epoch: int,
    command: TimelineFactCommand,
    records: dict[str, SessionOccurrence],
    stream_start: str | None,
    commands: tuple[TimelineFactCommand, ...],
) -> AtomicFact:
    record = _require_record(command, records)
    start_reason = "normal_transition"
    if stream_start in _ATTACHED_STREAM:
        start_reason = "attached_mid_session"
    elif any(
        item.kind == "SESSION_ENDED"
        and records.get(str(item.occurrence_id) or "") is not None
        and records[str(item.occurrence_id)].end_reason == "rewind_superseded"
        for item in commands
    ):
        start_reason = "rewind_branch"
    return _fact(
        fact_id=f"fact:timeline:session.started:{record.occurrence_id}",
        predicate="session.started",
        attributes={"stage": record.occurrence_id.stage.value, "startReason": start_reason},
        scope="occurrence",
        now_ms=now_ms,
        broadcast_epoch=broadcast_epoch,
        stream_epoch=stream_epoch,
        occurrence_id=str(record.occurrence_id),
        lineage_id=str(record.lineage_id),
        evidence=f"timeline:session_started:{record.occurrence_id}",
    )


def _session_restarted(
    *,
    now_ms: int,
    broadcast_epoch: int,
    stream_epoch: int,
    command: TimelineFactCommand,
    records: dict[str, SessionOccurrence],
) -> AtomicFact:
    record = _require_record(command, records)
    predecessor = f"{int(record.occurrence_id.stream_epoch)}:{record.occurrence_id.stage.value}:{record.occurrence_id.ordinal - 1}"
    if record.occurrence_id.ordinal < 1:
        raise ContractViolation("session.restarted requires a predecessor occurrence")
    return _fact(
        fact_id=f"fact:timeline:session.restarted:{record.occurrence_id}",
        predicate="session.restarted",
        attributes={
            "stage": record.occurrence_id.stage.value,
            "predecessorOccurrenceId": predecessor,
        },
        scope="occurrence",
        now_ms=now_ms,
        broadcast_epoch=broadcast_epoch,
        stream_epoch=stream_epoch,
        occurrence_id=str(record.occurrence_id),
        lineage_id=str(record.lineage_id),
        evidence=f"timeline:session_restarted:{record.occurrence_id}",
    )


def _session_ended(
    *,
    now_ms: int,
    broadcast_epoch: int,
    stream_epoch: int,
    command: TimelineFactCommand,
    records: dict[str, SessionOccurrence],
) -> AtomicFact:
    record = _require_record(command, records)
    if record.end_reason is None:
        raise ContractViolation("session.ended requires a closed occurrence")
    return _fact(
        fact_id=f"fact:timeline:session.ended:{record.occurrence_id}",
        predicate="session.ended",
        attributes={"stage": record.occurrence_id.stage.value, "reason": record.end_reason},
        scope="historical_only",
        now_ms=now_ms,
        broadcast_epoch=broadcast_epoch,
        stream_epoch=stream_epoch,
        occurrence_id=str(record.occurrence_id),
        lineage_id=str(record.lineage_id),
        evidence=f"timeline:session_ended:{record.occurrence_id}",
    )


def _next_present_stage(
    *,
    snapshot: dict[str, Any],
    plan: SessionPlan | None,
    now_ms: int,
    broadcast_epoch: int,
    stream_epoch: int,
) -> AtomicFact | None:
    if plan is None or not plan.valid or plan.sub_session_id is None:
        return None
    current = snapshot.get("stage")
    occurrence_id = snapshot.get("occurrenceId")
    lineage_id = snapshot.get("lineageId")
    if (
        not isinstance(current, str)
        or not isinstance(occurrence_id, str)
        or not isinstance(lineage_id, str)
    ):
        return None
    try:
        current_rank = _STAGE_RANK[Stage(current)]
    except (KeyError, ValueError):
        return None
    nxt = next((entry for entry in plan.entries if _STAGE_RANK[entry.stage] > current_rank), None)
    if nxt is None:
        return None
    return _fact(
        fact_id=f"fact:timeline:session.next_present_stage:{occurrence_id}",
        predicate="session.next_present_stage",
        attributes={
            "stage": nxt.stage.value,
            "sourceSubSessionId": plan.sub_session_id,
            "sourceSessionNum": nxt.session_ref.session_num,
        },
        scope="occurrence",
        now_ms=now_ms,
        broadcast_epoch=broadcast_epoch,
        stream_epoch=stream_epoch,
        occurrence_id=occurrence_id,
        lineage_id=lineage_id,
        evidence=f"timeline:session_plan:{plan.plan_revision}",
    )


def _require_record(
    command: TimelineFactCommand, records: dict[str, SessionOccurrence]
) -> SessionOccurrence:
    key = command.occurrence_id
    if not isinstance(key, str) or key not in records:
        raise ContractViolation(f"{command.kind} is missing its SessionOccurrence")
    return records[key]


def _require_int(value: object, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ContractViolation(f"{field} must be an integer")
    return value


def _fact(
    *,
    fact_id: str,
    predicate: str,
    attributes: dict[str, object],
    scope: str,
    now_ms: int,
    broadcast_epoch: int,
    stream_epoch: int,
    occurrence_id: str | None,
    lineage_id: str | None,
    evidence: str,
) -> AtomicFact:
    return AtomicFact.from_dict(
        {
            "schemaVersion": "atomic-fact/2",
            "factId": fact_id,
            "predicate": predicate,
            "subjectId": None,
            "objectId": None,
            "attributes": attributes,
            "polarity": "positive",
            "validFromMonoMs": now_ms,
            "validUntilMonoMs": None,
            "observedAtMonoMs": now_ms,
            "broadcastEpoch": broadcast_epoch,
            "streamEpoch": stream_epoch,
            "occurrenceId": occurrence_id,
            "lineageId": lineage_id,
            "evidenceRefs": [evidence],
            "confidence": 1.0,
            "scope": scope,
            "status": "active",
            "revision": 0,
        }
    )
