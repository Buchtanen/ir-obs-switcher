"""#284 frozen actor-transition raceTraces / overflowScenarios model-tests."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
GOLDENS_PATH = MACHINE / "actor-transition-goldens.json"
MODEL_PATH = MACHINE / "actor-transition-model.json"
BUILDER_PATH = MACHINE / "build_actor_transition_model.py"

GOLDENS = json.loads(GOLDENS_PATH.read_text(encoding="utf-8"))


def _load_builder() -> Any:
    """Import the frozen machine builder without packaging it into irswitch."""

    module_name = "irswitch_actor_transition_builder_under_test"
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


def test_on_disk_actor_transition_artifacts_match_builder() -> None:
    disk_goldens = json.loads(GOLDENS_PATH.read_text(encoding="utf-8"))
    disk_model = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    assert builder.canonical(disk_goldens) == builder.canonical(builder.build_goldens())
    assert builder.canonical(disk_model) == builder.canonical(builder.build_model())


@pytest.mark.parametrize(
    "fixture",
    GOLDENS["raceTraces"],
    ids=lambda row: str(row["id"]),
)
def test_race_trace_model(fixture: dict[str, Any]) -> None:
    state = builder.initial_trace_state(str(fixture["initialLane"]))
    for step in fixture["steps"]:
        assert state["lane"] == step["laneBefore"]
        builder.reduce_trace_step(state, str(step["command"]), str(step["outcome"]))
        assert state["lane"] == step["laneAfter"]
    assert state["lane"] == fixture["finalLane"]
    for assertion in fixture["assertions"]:
        assert builder.assertion_holds(str(assertion), state)


@pytest.mark.parametrize(
    "fixture",
    GOLDENS["overflowScenarios"],
    ids=lambda row: str(row["id"]),
)
def test_overflow_scenario_model(fixture: dict[str, Any]) -> None:
    assert builder.evaluate_overflow(fixture) == fixture["expected"]


@pytest.mark.parametrize(
    "fixture",
    GOLDENS["orderingScenarios"],
    ids=lambda row: str(row["id"]),
)
def test_same_time_ordering_follows_mailbox_sequence(fixture: dict[str, Any]) -> None:
    sequences = [int(row["mailboxSequence"]) for row in fixture["admissions"]]
    assert sorted(sequences) == list(fixture["expectedReducerOrder"])


def test_pair_coverage_matches_transition_matrix() -> None:
    model = json.loads(MODEL_PATH.read_text(encoding="utf-8"))
    matrix_pairs = {(row["lane"], row["command"]) for row in model["transitionMatrix"]}
    golden_pairs = {(row["lane"], row["command"]) for row in GOLDENS["pairCoverage"]}
    assert golden_pairs == matrix_pairs
    assert len(GOLDENS["pairCoverage"]) == 85
    assert len(GOLDENS["raceTraces"]) == 13
    assert len(GOLDENS["overflowScenarios"]) == 10


def test_narrative_runtime_result_before_deadline_race() -> None:
    """Library evidence for the result_before_deadline golden race."""

    from test_narrative_runtime import _drive_to, _result_for

    from irswitch.contracts.command import NarrativeCommand

    runtime = _drive_to("building")
    token = runtime.current_realization_token()
    assert token is not None
    assert runtime.admit(
        NarrativeCommand.realization_result(
            "race:result-first",
            "REALIZATION_SUCCEEDED",
            3000,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(token),
        )
    ).accepted
    committed = runtime.reduce_next()
    assert committed is not None
    assert committed.lane_after == "committed"
    assert runtime.admit(
        NarrativeCommand.realization_deadline(
            "race:late-deadline",
            3100,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            deadline_mono_ms=3100,
        )
    ).accepted
    late = runtime.reduce_next()
    assert late is not None
    assert late.disposition == "ignored_stale_or_inapplicable"
    assert late.lane_after == "committed"
    assert runtime.status().lane == "committed"


def test_narrative_runtime_shutdown_during_speaking_race() -> None:
    """Library evidence for shutdown_during_playback golden race."""

    from test_narrative_runtime import _drive_to

    from irswitch.contracts.command import NarrativeCommand

    runtime = _drive_to("speaking")
    assert runtime.admit(
        NarrativeCommand.shutdown("race:shutdown", 5000, "application_exit")
    ).accepted
    stopped = runtime.reduce_next()
    assert stopped is not None
    assert stopped.disposition == "handled"
    assert runtime.status().runtime_state == "stopped"
