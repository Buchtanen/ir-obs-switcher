"""#284 reducer-state tape replay equivalence helpers.

Library-only: capture a deterministic reducer trace from a command list and
replay it on a fresh NarrativeRuntime (optional ``runtime_factory`` for
StoryDirector seed so director decisions stay reproducible). Also reads/writes a
NarrativeTape-shaped command journal (NDJSON) including recorded realization
completions so file→command reconstruction can feed the harness.
Not exported from ``events/__init__.py``. Race wiring and master cutover remain
deferred.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from irswitch.commentary.mailbox import NarrativeMailbox
from irswitch.contracts.command import NarrativeCommand
from irswitch.contracts.context import ApplyContextBatch, ContextBatchPart, ExternalOrder
from irswitch.contracts.narrative import NarrativeEvent
from irswitch.contracts.primitives import ContractViolation
from irswitch.events.narrative_runtime import NarrativeRuntime, ReduceResult, RuntimeStatus

MailboxFactory = Callable[[], NarrativeMailbox]
RuntimeFactory = Callable[[], NarrativeRuntime]

COMMAND_JOURNAL_SCHEMA = "narrative-command-journal/1"


@dataclass(frozen=True, slots=True)
class ReducerTraceStep:
    reducer_sequence: int
    command_id: str
    command_kind: str
    disposition: str
    lane_before: str
    lane_after: str
    runtime_state: str
    history_complete: bool
    planning_cycle_id: int
    plans_dispatched: int
    effects: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReducerTrace:
    """Captured reducer outcomes plus the commands that produced them."""

    commands: tuple[NarrativeCommand, ...]
    steps: tuple[ReducerTraceStep, ...]
    final_status: RuntimeStatus

    def to_tape_rows(self) -> list[dict[str, object]]:
        """Tape-shaped projection keyed by assigned ``reducerSequence``."""

        return [
            {
                "reducerSequence": step.reducer_sequence,
                "commandId": step.command_id,
                "commandKind": step.command_kind,
                "disposition": step.disposition,
                "laneBefore": step.lane_before,
                "laneAfter": step.lane_after,
                "runtimeState": step.runtime_state,
                "historyComplete": step.history_complete,
                "planningCycleId": step.planning_cycle_id,
                "plansDispatched": step.plans_dispatched,
                "effects": list(step.effects),
            }
            for step in self.steps
        ]


def _step_from_result(result: ReduceResult) -> ReducerTraceStep:
    return ReducerTraceStep(
        reducer_sequence=int(result.reducer_sequence),
        command_id=str(result.command_id),
        command_kind=str(result.kind),
        disposition=str(result.disposition),
        lane_before=str(result.lane_before),
        lane_after=str(result.lane_after),
        runtime_state=str(result.runtime_state),
        history_complete=bool(result.history_complete),
        planning_cycle_id=int(result.planning_cycle_id),
        plans_dispatched=int(result.plans_dispatched),
        effects=tuple(result.effects),
    )


def _run_commands(
    commands: Sequence[NarrativeCommand],
    *,
    mailbox_factory: MailboxFactory | None = None,
    runtime_factory: RuntimeFactory | None = None,
) -> ReducerTrace:
    if runtime_factory is not None:
        runtime = runtime_factory()
    else:
        factory = mailbox_factory or NarrativeMailbox
        runtime = NarrativeRuntime(mailbox=factory())
    runtime.enable()
    for command in commands:
        admitted = runtime.admit(command)
        if not admitted.accepted:
            raise RuntimeError(
                f"command {command.command_id!r} rejected during reducer replay "
                f"({admitted.reason})"
            )
    steps = tuple(_step_from_result(result) for result in runtime.drain())
    return ReducerTrace(commands=tuple(commands), steps=steps, final_status=runtime.status())


def capture_reducer_trace(
    commands: Sequence[NarrativeCommand],
    *,
    mailbox_factory: MailboxFactory | None = None,
    runtime_factory: RuntimeFactory | None = None,
) -> ReducerTrace:
    """Admit+drain ``commands`` and return the deterministic reducer trace.

    Optional ``runtime_factory`` builds a pre-seeded ``NarrativeRuntime`` (e.g.
    StoryDirector + seed) so director decisions stay reproducible under replay.
    """

    return _run_commands(
        commands,
        mailbox_factory=mailbox_factory,
        runtime_factory=runtime_factory,
    )


def replay_reducer_trace(
    trace: ReducerTrace,
    *,
    mailbox_factory: MailboxFactory | None = None,
    runtime_factory: RuntimeFactory | None = None,
) -> ReducerTrace:
    """Re-run the captured command list on a fresh runtime."""

    return _run_commands(
        trace.commands,
        mailbox_factory=mailbox_factory,
        runtime_factory=runtime_factory,
    )


_STATUS_FINGERPRINT_VOLATILE = frozenset(
    {
        # Monotonic clocks differ across live capture vs later journal replay.
        "loop_last_reduce_mono_ms",
        "speech_dispatched_at_mono_ms",
        "speech_accepted_at_mono_ms",
    }
)


def _status_fingerprint(status: RuntimeStatus) -> dict[str, object]:
    payload = asdict(status)
    for key in _STATUS_FINGERPRINT_VOLATILE:
        payload.pop(key, None)
    # component_health is a plain dict already; keep deterministic key order.
    health = payload.get("component_health")
    if isinstance(health, dict):
        payload["component_health"] = dict(sorted((str(k), str(v)) for k, v in health.items()))
    return payload


def traces_equivalent(left: ReducerTrace, right: ReducerTrace) -> bool:
    """True when step fingerprints and final status fingerprints match."""

    if left.steps != right.steps:
        return False
    return _status_fingerprint(left.final_status) == _status_fingerprint(right.final_status)


def command_from_dict(payload: dict[str, Any]) -> NarrativeCommand:
    """Rebuild a ``NarrativeCommand`` from ``NarrativeCommand.to_dict()`` JSON.

    Supports the journal slice kinds: ``APPLY_CONTEXT_BATCH``, ordinary
    deadlines, ``REALIZATION_SUCCEEDED`` / ``REALIZATION_FAILED`` (recorded
    Qwen/authored completions), and ``SHUTDOWN``. Other kinds raise
    ``ContractViolation``.
    """

    if not isinstance(payload, dict):
        raise ContractViolation("command journal payload must be an object")
    kind = payload.get("kind")
    command_id = payload.get("commandId")
    enqueued = payload.get("enqueuedMonoMs")
    if not isinstance(kind, str) or not isinstance(command_id, str):
        raise ContractViolation("command journal requires string kind and commandId")
    if isinstance(enqueued, bool) or not isinstance(enqueued, int):
        raise ContractViolation("command journal enqueuedMonoMs must be an integer")

    if kind == "APPLY_CONTEXT_BATCH":
        body = payload.get("payload")
        external = payload.get("externalOrder")
        if not isinstance(body, dict) or not isinstance(external, dict):
            raise ContractViolation("APPLY_CONTEXT_BATCH journal row needs payload+externalOrder")
        events_raw = body.get("events")
        if not isinstance(events_raw, list):
            raise ContractViolation("APPLY_CONTEXT_BATCH payload.events must be an array")
        events = tuple(NarrativeEvent.from_dict(item) for item in events_raw)
        batch = ApplyContextBatch(
            timeline=body["timeline"],
            fact_view=body["factView"],
            events=events,
        )
        order = ExternalOrder(
            external["fanoutStreamSequence"],
            external.get("firstSourceOrdinal"),
            external.get("lastSourceOrdinal"),
        )
        return NarrativeCommand.context_batch(command_id, enqueued, ContextBatchPart(batch, order))

    if kind in {"LONG_SILENCE_ELAPSED", "VALIDITY_DEADLINE_ELAPSED"}:
        token = payload.get("token")
        if not isinstance(token, dict):
            raise ContractViolation(f"{kind} journal row requires token object")
        generation = token.get("generation")
        deadline_mono_ms = token.get("deadlineMonoMs")
        if isinstance(generation, bool) or not isinstance(generation, int):
            raise ContractViolation(f"{kind} token.generation must be an integer")
        if isinstance(deadline_mono_ms, bool) or not isinstance(deadline_mono_ms, int):
            raise ContractViolation(f"{kind} token.deadlineMonoMs must be an integer")
        return NarrativeCommand.deadline(
            command_id,
            kind,  # type: ignore[arg-type]
            enqueued,
            generation=generation,
            deadline_mono_ms=deadline_mono_ms,
        )

    if kind in {"REALIZATION_SUCCEEDED", "REALIZATION_FAILED"}:
        token = payload.get("token")
        body = payload.get("payload")
        if not isinstance(token, dict) or not isinstance(body, dict):
            raise ContractViolation(f"{kind} journal row requires token and payload objects")
        request_id = token.get("requestId")
        request_ordinal = token.get("requestOrdinal")
        dispatch_generation = token.get("dispatchGeneration")
        if not isinstance(request_id, str):
            raise ContractViolation(f"{kind} token.requestId must be a string")
        if isinstance(request_ordinal, bool) or not isinstance(request_ordinal, int):
            raise ContractViolation(f"{kind} token.requestOrdinal must be an integer")
        if isinstance(dispatch_generation, bool) or not isinstance(dispatch_generation, int):
            raise ContractViolation(f"{kind} token.dispatchGeneration must be an integer")
        return NarrativeCommand.realization_result(
            command_id,
            kind,  # type: ignore[arg-type]
            enqueued,
            request_id=request_id,
            request_ordinal=request_ordinal,
            dispatch_generation=dispatch_generation,
            result=body,
        )

    if kind == "SHUTDOWN":
        body = payload.get("payload")
        if not isinstance(body, dict) or not isinstance(body.get("reason"), str):
            raise ContractViolation("SHUTDOWN journal row requires payload.reason string")
        return NarrativeCommand.shutdown(command_id, enqueued, body["reason"])

    raise ContractViolation(f"unsupported command journal kind: {kind}")


def append_command_journal_row(
    path: Path | str,
    *,
    reducer_sequence: int,
    command: NarrativeCommand,
) -> None:
    """Append one tape-shaped NDJSON row for a live reduce (fail-soft caller)."""

    if (
        isinstance(reducer_sequence, bool)
        or not isinstance(reducer_sequence, int)
        or reducer_sequence < 1
    ):
        raise ContractViolation("reducer_sequence must be a positive int")
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "schemaVersion": COMMAND_JOURNAL_SCHEMA,
        "reducerSequence": int(reducer_sequence),
        "command": command.to_dict(),
    }
    with target.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, separators=(",", ":"), ensure_ascii=True) + "\n")


def write_command_journal(path: Path | str, trace: ReducerTrace) -> Path:
    """Write tape-shaped NDJSON rows: reducerSequence + full command dict."""

    target = Path(path)
    if len(trace.commands) != len(trace.steps):
        raise ContractViolation("reducer trace commands/steps length mismatch")
    lines: list[str] = []
    for command, step in zip(trace.commands, trace.steps, strict=True):
        row = {
            "schemaVersion": COMMAND_JOURNAL_SCHEMA,
            "reducerSequence": int(step.reducer_sequence),
            "command": command.to_dict(),
        }
        lines.append(json.dumps(row, separators=(",", ":"), ensure_ascii=True))
    target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return target


def read_commands_from_journal(path: Path | str) -> tuple[NarrativeCommand, ...]:
    """Load commands from a journal file ordered by ``reducerSequence``."""

    target = Path(path)
    rows: list[tuple[int, NarrativeCommand]] = []
    for line_no, raw in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ContractViolation(f"command journal line {line_no} is not JSON") from exc
        if not isinstance(row, dict):
            raise ContractViolation(f"command journal line {line_no} must be an object")
        if row.get("schemaVersion") != COMMAND_JOURNAL_SCHEMA:
            raise ContractViolation(
                f"command journal line {line_no} schemaVersion must be {COMMAND_JOURNAL_SCHEMA}"
            )
        sequence = row.get("reducerSequence")
        command_payload = row.get("command")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or sequence < 1:
            raise ContractViolation(
                f"command journal line {line_no} reducerSequence must be a positive int"
            )
        if not isinstance(command_payload, dict):
            raise ContractViolation(f"command journal line {line_no} command must be an object")
        rows.append((sequence, command_from_dict(command_payload)))
    rows.sort(key=lambda item: item[0])
    return tuple(command for _, command in rows)


def replay_command_journal(
    path: Path | str,
    *,
    mailbox_factory: MailboxFactory | None = None,
    runtime_factory: RuntimeFactory | None = None,
) -> ReducerTrace:
    """Read a command journal file and capture a fresh reducer trace."""

    return capture_reducer_trace(
        read_commands_from_journal(path),
        mailbox_factory=mailbox_factory,
        runtime_factory=runtime_factory,
    )
