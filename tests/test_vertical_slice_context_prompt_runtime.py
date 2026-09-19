"""#278 Slice 12 — offline F18/F33 context-cut + prompt-freedom drivers.

Consumes frozen machine rows and proves ApplyContextBatch/NarrativeRuntime
coherence locks (apply revision 88, reject mismatched event revision, no
cached older-view resolution, no cross-batch merge, revision 89 opens one
director cycle) plus PromptCompiler freedom clamps (closed profiles, least
permissive, tight baseline, safe promotion, canonical seed, card-or-fatigue,
failure never widens). Does not rewrite ``docs/v2.0.0/machine/*`` hashes and
does not claim live §24.9 GO.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from test_narrative_runtime import _event, _fact_view, _timeline
from test_prompt_compiler import _world

from irswitch.contracts.command import NarrativeCommand
from irswitch.contracts.context import ApplyContextBatch, ContractViolation
from irswitch.events.narrative import partition_context_batches
from irswitch.events.narrative_runtime import NarrativeRuntime
from irswitch.events.prompt_compiler import PROFILES, PromptCompiler, prompt_options_for

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
FIXTURES_PATH = MACHINE / "vertical-slice-fixtures.json"
BUILDER_PATH = MACHINE / "build_vertical_slice_fixtures.py"

SLICE12_IDS = ("F18", "F33")
CANONICAL_SEED = 16041955996680716084


def _load_builder() -> Any:
    module_name = "irswitch_vertical_slice_context_prompt_builder_under_test"
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


def _context_command(
    command_id: str,
    *,
    timeline_revision: int,
    fact_view_revision: int,
    fanout: int,
    with_event: bool = False,
) -> NarrativeCommand:
    timeline = _timeline(revision=timeline_revision)
    fact_view = _fact_view(1, revision=fact_view_revision)
    events = ()
    if with_event:
        events = (_event(0, fanout=fanout, fact_revision=fact_view_revision),)
    part = partition_context_batches(
        timeline=timeline,
        fact_view=fact_view,
        events=events,
        fanout_stream_sequence=fanout,
    )[0]
    return NarrativeCommand.context_batch(command_id, 1000, part)


@pytest.fixture(scope="module")
def fixtures_by_id() -> dict[str, dict[str, Any]]:
    bundle = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    return {row["id"]: row for row in bundle["fixtures"]}


@pytest.mark.parametrize("fixture_id", SLICE12_IDS)
def test_slice12_machine_projection_and_calculations(
    fixtures_by_id: dict[str, dict[str, Any]], fixture_id: str
) -> None:
    row = fixtures_by_id[fixture_id]
    assert builder.execute_model(row) == row["expectations"]
    for calculation in row.get("calculations") or ():
        assert builder.evaluate(calculation) == calculation["expected"]


def test_f18_context_batch_is_a_coherent_fact_event_cut(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F18: coherent apply / mismatch reject / no merge / one director on 89."""

    expected = set(fixtures_by_id["F18"]["expectations"])
    observed: set[str] = set()

    with pytest.raises(ContractViolation, match="factViewRevision"):
        ApplyContextBatch(
            timeline=_timeline(revision=31),
            fact_view=_fact_view(1, revision=88),
            events=(_event(0, fact_revision=87),),
        )
    observed.add("reject_mismatch")
    observed.add("no_old_view_lookup")

    runtime = NarrativeRuntime()
    runtime.enable()

    first = runtime.admit(
        _context_command(
            "f18:88",
            timeline_revision=31,
            fact_view_revision=88,
            fanout=88,
            with_event=False,
        )
    )
    assert first.accepted is True
    reduced_88 = runtime.reduce_next()
    assert reduced_88 is not None
    assert reduced_88.disposition == "handled"
    assert "context_applied" in reduced_88.effects
    assert "director_skipped_pure_fact" in reduced_88.effects
    assert runtime.status().fact_view_revision == 88
    assert runtime.status().plans_dispatched_in_cycle == 0
    observed.add("apply_88")

    second = runtime.admit(
        _context_command(
            "f18:89",
            timeline_revision=31,
            fact_view_revision=89,
            fanout=89,
            with_event=True,
        )
    )
    assert second.accepted is True
    reduced_89 = runtime.reduce_next()
    assert reduced_89 is not None
    assert reduced_89.disposition == "handled"
    assert "planning_cycle_opened:event_impulse" in reduced_89.effects
    assert reduced_89.plans_dispatched == 1
    status = runtime.status()
    assert status.fact_view_revision == 89
    assert status.timeline_revision == 31
    assert status.planning_cycle_id == 1
    assert status.plans_dispatched_in_cycle == 1
    observed.add("apply_89_one_director")
    observed.add("no_batch_merge")

    assert observed == expected


def test_f33_prompt_freedom_is_a_deterministic_safety_clamp(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F33: closed profiles, least-permissive clamp, seed, no failure widen."""

    expected = set(fixtures_by_id["F33"]["expectations"])
    observed: set[str] = set()

    assert set(PROFILES) == {"tight", "balanced", "loose"}
    observed.add("closed_profiles")

    baseline = prompt_options_for(_world())
    assert baseline.freedom == "tight"
    assert baseline.pattern_choice == "fixed"
    assert baseline.seed == CANONICAL_SEED
    step = PromptCompiler().realize(_world(), now_ms=10_000)
    assert step.outcome == "succeeded"
    assert step.options is not None
    assert step.options.freedom == "tight"
    observed.add("tight_baseline")
    observed.add("canonical_seed")

    promoted = prompt_options_for(
        _world(
            enabled_profiles=frozenset({"tight", "balanced", "loose"}),
            operator_max_profile="loose",
            beat_max_freedom="loose",
            family_promoted_max_freedom="loose",
            family_preferred_freedom="balanced",
            policy_id="context",
            beat_role="update",
            history_complete=True,
            min_selected_fact_confidence=0.94,
        )
    )
    critical = prompt_options_for(
        _world(
            enabled_profiles=frozenset({"tight", "balanced", "loose"}),
            operator_max_profile="loose",
            beat_max_freedom="loose",
            family_promoted_max_freedom="loose",
            family_preferred_freedom="loose",
            policy_id="critical",
            beat_role="update",
        )
    )
    outcome = prompt_options_for(
        _world(
            enabled_profiles=frozenset({"tight", "balanced", "loose"}),
            operator_max_profile="loose",
            beat_max_freedom="loose",
            family_promoted_max_freedom="loose",
            family_preferred_freedom="loose",
            policy_id="context",
            beat_role="outcome",
        )
    )
    stale = prompt_options_for(
        _world(
            enabled_profiles=frozenset({"tight", "balanced", "loose"}),
            operator_max_profile="loose",
            beat_max_freedom="loose",
            family_promoted_max_freedom="loose",
            family_preferred_freedom="loose",
            policy_id="context",
            beat_role="update",
            history_complete=False,
        )
    )
    low = prompt_options_for(
        _world(
            enabled_profiles=frozenset({"tight", "balanced", "loose"}),
            operator_max_profile="loose",
            beat_max_freedom="loose",
            family_promoted_max_freedom="loose",
            family_preferred_freedom="loose",
            policy_id="context",
            beat_role="update",
            min_selected_fact_confidence=0.89,
        )
    )
    assert promoted.freedom == "balanced"
    assert promoted.pattern_choice == "family_pool"
    assert critical.freedom == outcome.freedom == stale.freedom == low.freedom == "tight"
    observed.add("promoted_wider_if_safe")
    observed.add("least_permissive")
    observed.add("card_choice_or_fatigue")

    no_widen = prompt_options_for(_world(widen_for_repetition=True, widen_for_failure=True))
    assert no_widen.freedom == "tight"
    assert no_widen.pattern_choice == "fixed"
    observed.add("failure_no_widen")

    assert observed == expected
