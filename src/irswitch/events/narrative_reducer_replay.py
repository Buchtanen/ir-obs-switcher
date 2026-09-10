"""#284 reducer-state tape replay equivalence helpers.

Library-only: capture a deterministic reducer trace from a command list and
replay it on a fresh NarrativeRuntime. Not exported from ``events/__init__.py``.
Race wiring and master cutover remain deferred.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass

from irswitch.commentary.mailbox import NarrativeMailbox
from irswitch.contracts.command import NarrativeCommand
from irswitch.events.narrative_runtime import NarrativeRuntime, ReduceResult, RuntimeStatus

MailboxFactory = Callable[[], NarrativeMailbox]


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
) -> ReducerTrace:
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
) -> ReducerTrace:
    """Admit+drain ``commands`` and return the deterministic reducer trace."""

    return _run_commands(commands, mailbox_factory=mailbox_factory)


def replay_reducer_trace(
    trace: ReducerTrace,
    *,
    mailbox_factory: MailboxFactory | None = None,
) -> ReducerTrace:
    """Re-run the captured command list on a fresh runtime."""

    return _run_commands(trace.commands, mailbox_factory=mailbox_factory)


def _status_fingerprint(status: RuntimeStatus) -> dict[str, object]:
    payload = asdict(status)
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
