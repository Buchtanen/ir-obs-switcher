"""#278 Slice 13 — offline F14/F35 playback-race + planning-replace drivers.

Consumes frozen machine rows and proves NarrativeRuntime playback/reset
ordering locks (stale accept after reset stays unconsumed, accept-then-reset
interrupts an exposed utterance, reducer sequence is authoritative) plus
event-replacement planning locks (replace without suppression, close cycle N,
open N+1 attempt 1, one alternative, lower/pure fact does not replace,
accepted events only). Does not rewrite ``docs/v2.0.0/machine/*`` hashes and
does not claim live §24.9 GO.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from test_narrative_runtime import (
    _context_with_timeline,
    _drive_to,
    _event_impulse,
    _pure_fact,
    _timeline_run,
    _tts_callback,
)

from irswitch.events.narrative_runtime import NarrativeRuntime

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
FIXTURES_PATH = MACHINE / "vertical-slice-fixtures.json"
BUILDER_PATH = MACHINE / "build_vertical_slice_fixtures.py"

SLICE13_IDS = ("F14", "F35")


def _load_builder() -> Any:
    module_name = "irswitch_vertical_slice_playback_replace_builder_under_test"
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


def _reset_context(command_id: str, *, revision: int, fanout: int) -> Any:
    return _context_with_timeline(
        command_id,
        _timeline_run(
            revision=revision,
            stream_epoch=1,
            narrative_run_active=True,
            transition_reasons=["session_restarted"],
        ),
        fanout=fanout,
    )


@pytest.fixture(scope="module")
def fixtures_by_id() -> dict[str, dict[str, Any]]:
    bundle = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    return {row["id"]: row for row in bundle["fixtures"]}


@pytest.mark.parametrize("fixture_id", SLICE13_IDS)
def test_slice13_machine_projection_and_calculations(
    fixtures_by_id: dict[str, dict[str, Any]], fixture_id: str
) -> None:
    row = fixtures_by_id[fixture_id]
    assert builder.execute_model(row) == row["expectations"]
    for calculation in row.get("calculations") or ():
        assert builder.evaluate(calculation) == calculation["expected"]


def test_f14_playback_acknowledgement_races_reset(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F14: reset/accept order is reducer-authoritative; stale accept is inert."""

    expected = set(fixtures_by_id["F14"]["expectations"])
    observed: set[str] = set()

    # Order 1: reset then accept — opportunity stays unconsumed; accept is stale.
    reset_first = _drive_to("speaking")
    utterance = reset_first.current_utterance_token()
    assert utterance is not None
    assert reset_first.admit(_reset_context("f14:reset-first", revision=400, fanout=400)).accepted
    reset_result = reset_first.reduce_next()
    assert reset_result is not None
    assert reset_result.disposition == "handled"
    assert "speech_cancel_requested" in reset_result.effects
    reset_seq = reset_result.reducer_sequence
    assert reset_first.admit(
        _tts_callback("PLAYBACK_ACCEPTED", utterance, command_id="f14:stale-accept")
    ).accepted
    stale = reset_first.reduce_next()
    assert stale is not None
    assert stale.disposition == "ignored_stale_or_inapplicable"
    assert "stale_playback_token" in stale.effects
    assert stale.reducer_sequence == reset_seq + 1
    observed.add("first_unconsumed_stale_accept")

    # Order 2: accept already consumed/exposed via drive, then reset interrupts.
    accept_first = _drive_to("speaking")
    assert accept_first.status().lane == "speaking"
    assert accept_first.admit(_reset_context("f14:reset-second", revision=401, fanout=401)).accepted
    interrupt = accept_first.reduce_next()
    assert interrupt is not None
    assert interrupt.disposition == "handled"
    assert "speech_cancel_requested" in interrupt.effects
    assert accept_first.status().lane == "stopping"
    observed.add("second_consumed_exposed_interrupt")

    # Reducer sequence alone distinguishes the two OS-time-equal orderings.
    assert reset_seq < stale.reducer_sequence
    assert interrupt.reducer_sequence >= 1
    assert "stale_playback_token" in stale.effects
    assert "stale_playback_token" not in interrupt.effects
    observed.add("reducer_sequence_authority")

    assert observed == expected


def test_f35_real_event_replaces_into_new_planning_cycle(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F35: accepted event replaces building cycle; pure/lower fact does not."""

    expected = set(fixtures_by_id["F35"]["expectations"])
    observed: set[str] = set()

    runtime = NarrativeRuntime()
    runtime.enable()

    assert runtime.admit(_event_impulse("f35:cycle70", revision=70, fanout=70)).accepted
    first = runtime.reduce_next()
    assert first is not None
    assert first.disposition == "handled"
    assert first.planning_cycle_id == 1
    assert first.plans_dispatched == 1
    assert "planning_cycle_opened:event_impulse" in first.effects
    assert runtime.status().lane == "building"

    assert runtime.admit(_event_impulse("f35:cycle71", revision=71, fanout=71)).accepted
    second = runtime.reduce_next()
    assert second is not None
    assert second.disposition == "handled"
    assert "replaced_precommit" in second.effects
    assert "planning_cycle_opened:event_replacement" in second.effects
    assert second.planning_cycle_id == 2
    assert second.plans_dispatched == 1
    assert runtime.status().planning_cycle_id == 2
    assert runtime.status().plans_dispatched_in_cycle == 1
    observed.add("replace_without_suppression")
    observed.add("close70")
    observed.add("new_cycle71_attempt1")
    observed.add("one_alternative")
    observed.add("accepted_event_only")

    cycle_before = runtime.status().planning_cycle_id
    assert runtime.admit(_pure_fact("f35:lower", revision=72, fanout=72)).accepted
    lower = runtime.reduce_next()
    assert lower is not None
    assert lower.disposition == "handled"
    assert "director_skipped_pure_fact" in lower.effects
    assert "planning_cycle_opened:event_replacement" not in lower.effects
    assert runtime.status().planning_cycle_id == cycle_before == 2
    observed.add("lower_event_no_replace")

    assert observed == expected
