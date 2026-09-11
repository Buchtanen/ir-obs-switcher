"""#278 Slice 23 — offline F19 refreshed recovery-barrier runtime drivers.

Consumes frozen machine rows and proves NarrativeMailbox + NarrativeRuntime
ownership of in-place recovery refresh: jump to revision 110, expanded loss
range, no invented opportunities, stale queued revisions 105-109, apply 111,
and reducer replay equivalence. Does not rewrite ``docs/v2.0.0/machine/*``
hashes and does not claim live §24.9 GO.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from test_narrative_runtime import _pure_fact

from irswitch.commentary.mailbox import NarrativeMailbox
from irswitch.contracts.command import NarrativeCommand
from irswitch.events.narrative_reducer_replay import (
    capture_reducer_trace,
    replay_reducer_trace,
    traces_equivalent,
)
from irswitch.events.narrative_runtime import NarrativeRuntime

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
FIXTURES_PATH = MACHINE / "vertical-slice-fixtures.json"
BUILDER_PATH = MACHINE / "build_vertical_slice_fixtures.py"

SLICE23_IDS = ("F19",)


def _load_builder() -> Any:
    module_name = "irswitch_vertical_slice_recovery_barrier_builder_under_test"
    if module_name in sys.modules:
        return sys.modules[module_name]
    machine_path = str(MACHINE)
    if machine_path not in sys.path:
        sys.path.insert(0, machine_path)
    spec = importlib.util.spec_from_file_location(module_name, BUILDER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


builder = _load_builder()


@pytest.fixture(scope="module")
def fixtures_by_id() -> dict[str, dict[str, Any]]:
    bundle = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    return {row["id"]: row for row in bundle["fixtures"]}


@pytest.mark.parametrize("fixture_id", SLICE23_IDS)
def test_slice23_machine_projection_and_calculations(
    fixtures_by_id: dict[str, dict[str, Any]], fixture_id: str
) -> None:
    row = fixtures_by_id[fixture_id]
    assert builder.execute_model(row) == row["expectations"]
    for calculation in row.get("calculations") or ():
        assert builder.evaluate(calculation) == calculation["expected"]


def _health(command_id: str, mono_ms: int, *, generation: int) -> NarrativeCommand:
    return NarrativeCommand.component_health(
        command_id,
        mono_ms,
        component="llm",
        generation=generation,
        status="unavailable",
        reason="preflight_failed",
    )


def test_f19_refreshed_recovery_barrier_jumps_over_stale_queued_context(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F19: refreshed recovery barrier jumps to 110; older queued contexts are stale."""

    expected = set(fixtures_by_id["F19"]["expectations"])
    observed: set[str] = set()

    runtime = NarrativeRuntime()
    runtime.enable()
    assert runtime.admit(_pure_fact("seed", revision=1, fanout=1)).accepted
    assert runtime.reduce_next() is not None

    # Barrier covering lost revisions 101-104 (mailbox sequences in the loss range).
    barrier_seed = _pure_fact("barrier:seed", revision=40, fanout=40)
    barrier = NarrativeCommand.recovery(
        "recovery:barrier",
        2000,
        latest_context=barrier_seed.context_part,
        loss_first_sequence=101,
        loss_last_sequence=104,
        safety_effects=(barrier_seed.safety_effect(),),
    )
    assert runtime.admit(barrier).accepted
    barrier_sequence = runtime._mailbox.recovery.mailbox_sequence
    assert barrier_sequence is not None

    # Revisions 105-109 remain physically behind the barrier (later mailbox sequences).
    for revision in range(105, 110):
        admitted = runtime.admit(
            _pure_fact(f"queued:{revision}", revision=revision, fanout=revision)
        )
        assert admitted.accepted
        assert admitted.command.mailbox_sequence > barrier_sequence

    # Refresh the same barrier in place to coherent revision 110 with expanded loss.
    assert runtime.admit(_pure_fact("latest:110", revision=110, fanout=110)).accepted
    for index in range(NarrativeMailbox.PROTECTED_CELLS):
        assert runtime.admit(_health(f"health:{index}", 3000 + index, generation=index)).accepted
    overflow = runtime.admit(_health("health:overflow", 4000, generation=99))
    assert overflow.accepted
    assert overflow.reason == "mailbox_recovery"
    refreshed = runtime._mailbox.recovery
    assert refreshed is not None
    assert refreshed.mailbox_sequence == barrier_sequence
    assert refreshed.context_revision.timeline_revision == 110
    assert refreshed.payload["lossFirstMailboxSequence"] <= 101
    assert refreshed.payload["lossLastMailboxSequence"] >= 104
    assert (
        refreshed.payload["lossLastMailboxSequence"] > refreshed.payload["lossFirstMailboxSequence"]
    )
    observed.add("full_loss_range")

    # Reducing the barrier jumps to 110 without inventing lost opportunities.
    recovery_result = runtime.reduce_next()
    assert recovery_result is not None
    assert recovery_result.kind == "MAILBOX_RECOVERY"
    assert recovery_result.disposition == "handled"
    assert "recovery_applied" in recovery_result.effects
    assert "history_incomplete" in recovery_result.effects
    assert runtime.status().timeline_revision == 110
    assert runtime.status().history_complete is False
    assert runtime.status().last_recovery_loss_first <= 101
    assert runtime.status().last_recovery_loss_last >= 104
    assert not any(
        effect.startswith("opportunity") or effect.startswith("director_selected")
        for effect in recovery_result.effects
    )
    observed.add("jump_110")
    observed.add("no_invented_opportunities")

    # Subsequently dequeued 105-109 (and the equal-110 refresh carrier) are stale no-ops.
    stale_revisions: list[int] = []
    while True:
        item = runtime.reduce_next()
        if item is None:
            break
        if item.kind != "APPLY_CONTEXT_BATCH":
            continue
        assert item.disposition == "ignored_stale_or_inapplicable"
        assert "stale_context_after_recovery" in item.effects
        assert runtime.status().timeline_revision == 110
        assert runtime.status().history_complete is False
        assert not any(
            effect.startswith("opportunity") or effect.startswith("director_selected")
            for effect in item.effects
        )
        # Track which queued revisions we observed via command id prefix.
        if item.command_id.startswith("queued:"):
            stale_revisions.append(int(item.command_id.split(":")[1]))
    assert stale_revisions == [105, 106, 107, 108, 109]
    observed.add("stale_105_109")

    # Revision 111 arrives after the barrier and applies normally; history stays incomplete.
    assert runtime.admit(_pure_fact("queued:111", revision=111, fanout=111)).accepted
    applied = runtime.reduce_next()
    assert applied is not None
    assert applied.kind == "APPLY_CONTEXT_BATCH"
    assert applied.disposition == "handled"
    assert "context_applied" in applied.effects
    assert runtime.status().timeline_revision == 111
    assert runtime.status().history_complete is False
    observed.add("apply_111")

    # Tape/reducer replay over the same command sequence produces the same state.
    def scenario_commands() -> list[NarrativeCommand]:
        commands: list[NarrativeCommand] = [_pure_fact("seed", revision=1, fanout=1)]
        seed = _pure_fact("barrier:seed", revision=40, fanout=40)
        commands.append(
            NarrativeCommand.recovery(
                "recovery:barrier",
                2000,
                latest_context=seed.context_part,
                loss_first_sequence=101,
                loss_last_sequence=104,
                safety_effects=(seed.safety_effect(),),
            )
        )
        for revision in range(105, 110):
            commands.append(_pure_fact(f"queued:{revision}", revision=revision, fanout=revision))
        commands.append(_pure_fact("latest:110", revision=110, fanout=110))
        for index in range(NarrativeMailbox.PROTECTED_CELLS):
            commands.append(_health(f"health:{index}", 3000 + index, generation=index))
        commands.append(_health("health:overflow", 4000, generation=99))
        commands.append(_pure_fact("queued:111", revision=111, fanout=111))
        return commands

    recorded = capture_reducer_trace(scenario_commands())
    replayed = replay_reducer_trace(recorded)
    assert traces_equivalent(recorded, replayed)
    observed.add("replay_equal")

    assert observed == expected
