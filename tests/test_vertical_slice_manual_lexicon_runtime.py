"""#278 Slice 10 — offline F12/F29 manual-disabled + lexicon drivers.

Consumes frozen machine rows and proves manual speak while automatic
commentary stays inert (busy on second request, race truth without barge-in),
plus offline SemanticVerifier lexicon hard-fail without live reads. Does not
rewrite ``docs/v2.0.0/machine/*`` hashes and does not claim live §24.9 GO.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from test_narrative_context_batch import _context_command
from test_semantic_verifier import _intent

from irswitch.events.narrative_runtime import NarrativeRuntime
from irswitch.events.semantic_verifier import SemanticVerifier

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
FIXTURES_PATH = MACHINE / "vertical-slice-fixtures.json"
BUILDER_PATH = MACHINE / "build_vertical_slice_fixtures.py"

SLICE10_IDS = ("F12", "F29")


def _load_builder() -> Any:
    module_name = "irswitch_vertical_slice_manual_lexicon_builder_under_test"
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


@pytest.mark.parametrize("fixture_id", SLICE10_IDS)
def test_slice10_machine_projection_and_calculations(
    fixtures_by_id: dict[str, dict[str, Any]], fixture_id: str
) -> None:
    row = fixtures_by_id[fixture_id]
    assert builder.execute_model(row) == row["expectations"]
    for calculation in row.get("calculations") or ():
        assert builder.evaluate(calculation) == calculation["expected"]


@pytest.mark.asyncio
async def test_f12_manual_speak_while_automatic_commentary_disabled(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F12: manual 202 while auto commentary inert; second busy; race no barge-in."""

    expected = set(fixtures_by_id["F12"]["expectations"])
    observed: set[str] = set()

    runtime = NarrativeRuntime()
    # Automatic commentary stays inert: try_manual_speak may arm transport, but
    # never opens a planning cycle / narrative planning state.
    first = await runtime.try_manual_speak(
        "Manual line while auto is off.",
        request_id="manual:f12:1",
        now_ms=1_000,
        admission_ordinal=1,
    )
    assert first.kind == "accepted"
    status = runtime.status()
    assert status.planning_cycle_id == 0
    assert status.plans_dispatched_in_cycle == 0
    assert status.narrative_run_active is False
    assert status.speech_source_kind == "manual"
    assert not any(code.startswith("planning_cycle_opened:") for code in status.reason_codes)
    observed.add("manual_202_after_dispatch")
    observed.add("no_narrative_state")

    second = await runtime.try_manual_speak(
        "Second manual while busy.",
        request_id="manual:f12:2",
        now_ms=1_001,
        admission_ordinal=2,
    )
    assert second.kind == "speech_busy"
    observed.add("second_busy")

    admitted = runtime.admit(_context_command("race:f12"))
    assert admitted.accepted is True
    reduced = runtime.reduce_next()
    assert reduced is not None
    assert "truth_updated_without_barge_in" in reduced.effects
    after = runtime.status()
    assert after.speech_source_kind == "manual"
    assert after.lane == "committed"
    observed.add("race_truth_no_interrupt")

    assert observed == expected


def test_f29_offline_lexicon_hard_fails_without_live_reads(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F29: complete lexicon parses; invalid bindings 400-class; reverse actors."""

    expected = set(fixtures_by_id["F29"]["expectations"])
    observed: set[str] = set()

    verifier = SemanticVerifier()
    complete = verifier.verify(_intent())
    assert complete.outcome == "succeeded"
    assert complete.result is not None
    assert complete.result.accepted is True
    assert complete.result.used_live_view is False
    assert complete.result.used_roster is False
    assert complete.result.used_config is False
    observed.add("only_complete_parses")

    missing = verifier.verify(
        _intent(
            actor_bindings=(("hero", ("Alex", "the driver")),),
            required_actors=frozenset({"hero", "car:22"}),
        )
    )
    unused = verifier.verify(
        _intent(
            actor_bindings=(
                ("hero", ("Alex",)),
                ("car:22", ("Morgan",)),
                ("car:9", ("Taylor",)),
            )
        )
    )
    colliding = verifier.verify(
        _intent(
            actor_bindings=(
                ("hero", ("Alex", "he")),
                ("car:22", ("Morgan", "HE")),
            )
        )
    )
    for step in (missing, unused, colliding):
        assert step.outcome == "failed"
        assert step.reason == "realization_input_invalid"
        assert step.result is None
        assert step.used_live_view is False
        assert step.used_roster is False
        assert step.used_config is False
    observed.add("invalid_400_no_live_reads")

    reversed_actors = verifier.verify(_intent(text="Morgan is closing on Alex."))
    assert reversed_actors.result is not None
    assert reversed_actors.result.accepted is False
    assert "actor_reversed" in reversed_actors.result.reasons
    assert reversed_actors.result.used_live_view is False
    assert reversed_actors.result.used_roster is False
    observed.add("reversal_actor_reversed")

    assert observed == expected
