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


def _fill_ordinary_partition(runtime: Any) -> None:
    """Saturate the ordinary mailbox partition with distinct silence deadlines."""

    from irswitch.commentary.mailbox import NarrativeMailbox
    from irswitch.contracts.command import NarrativeCommand

    for index in range(NarrativeMailbox.ORDINARY_CELLS):
        admitted = runtime.admit(
            NarrativeCommand.deadline(
                f"overflow:fill:{index}",
                "LONG_SILENCE_ELAPSED",
                20_000 + index,
                generation=1 + index,
                deadline_mono_ms=20_000 + index,
            )
        )
        assert admitted.accepted


@pytest.mark.asyncio
async def test_narrative_runtime_manual_full_partition_linearization() -> None:
    """#284: manual admission linearizes under ordinary overflow (no later speech).

    Maps to overflow golden ``manual_full_partition`` + ManualAdmissionLatch abandon
    when admit rejects — rejected request must not produce audio later.
    """

    from irswitch.commentary.mailbox import NarrativeMailbox
    from irswitch.events.narrative_runtime import NarrativeRuntime

    runtime = NarrativeRuntime()
    runtime.enable()
    _fill_ordinary_partition(runtime)
    assert len(runtime._mailbox) == NarrativeMailbox.ORDINARY_CELLS  # noqa: SLF001

    outcome = await runtime.try_manual_speak(
        "Should not speak.",
        request_id="overflow:manual-linearize",
        now_ms=30_000,
    )
    assert outcome.kind == "mailbox_overloaded"
    status = runtime.status()
    assert status.lane == "idle"
    assert status.last_admission_reason == "mailbox_overloaded"
    assert "mailbox_overloaded" in status.reason_codes
    assert len(runtime._mailbox) == NarrativeMailbox.ORDINARY_CELLS  # noqa: SLF001
    assert "overflow:manual-linearize" not in runtime._manual_latches  # noqa: SLF001

    # Rejected path cannot speak later even if reducer drains the fill.
    while runtime.reduce_next() is not None:
        pass
    assert runtime.status().lane in {"idle", "building"}  # silence may plan
    # No pending manual latch remains to resolve into speech.
    assert runtime._manual_latches == {}  # noqa: SLF001


def test_narrative_runtime_deadline_admission_skipped_under_overflow() -> None:
    """#284: validity deadline admission skips under ordinary overflow.

    Maps to overflow golden ``different_generation_does_not_coalesce`` /
    ``deadline_admission_skipped`` — no recovery, depth stays full.
    """

    from irswitch.commentary.mailbox import NarrativeMailbox
    from irswitch.contracts.command import NarrativeCommand
    from irswitch.events.narrative_runtime import NarrativeRuntime

    runtime = NarrativeRuntime()
    runtime.enable()
    _fill_ordinary_partition(runtime)
    skipped = runtime.admit(
        NarrativeCommand.deadline(
            "overflow:validity-skip",
            "VALIDITY_DEADLINE_ELAPSED",
            30_500,
            generation=1,
            deadline_mono_ms=30_500,
        )
    )
    assert skipped.accepted is False
    assert skipped.reason == "deadline_admission_skipped"
    status = runtime.status()
    assert status.last_admission_reason == "deadline_admission_skipped"
    assert "deadline_admission_skipped" in status.reason_codes
    assert len(runtime._mailbox) == NarrativeMailbox.ORDINARY_CELLS  # noqa: SLF001
    assert status.recovery_count == 0


@pytest.mark.asyncio
async def test_narrative_runtime_quarantined_cannot_admit_under_overflow() -> None:
    """#284: TTS quarantine + ordinary overflow both fail-soft (no utterance).

    Maps to invariant ``quarantined_generation_cannot_admit`` under saturated
    ordinary partition — overflow rejects first; after quarantine alone,
    manual reduce fails closed with ``component_unavailable``.
    """

    from irswitch.commentary.mailbox import NarrativeMailbox
    from irswitch.contracts.command import NarrativeCommand
    from irswitch.events.narrative_runtime import NarrativeRuntime

    runtime = NarrativeRuntime(speech_deadline_delay_s=0.02)
    runtime.enable()
    assert runtime.admit(
        NarrativeCommand.manual_speak(
            "overflow:q-seed", 40_000, text="Seed quarantine.", admission_ordinal=1
        )
    ).accepted
    committed = runtime.reduce_next()
    assert committed is not None
    await runtime.apply_effects(committed.effects)
    await runtime.wait_deadline_timers_idle()
    start_elapsed = runtime.reduce_next()
    assert start_elapsed is not None
    await runtime.apply_effects(start_elapsed.effects)
    await runtime.wait_deadline_timers_idle()
    stop_elapsed = runtime.reduce_next()
    assert stop_elapsed is not None
    await runtime.apply_effects(stop_elapsed.effects)
    assert "tts_backend_quarantined" in stop_elapsed.effects
    assert runtime.status().speech_quarantined_generation == 1
    assert runtime.status().component_health["tts"] == "unavailable"
    assert runtime.status().lane == "idle"

    # Quarantine alone: manual fails closed (no speech).
    blocked = await runtime.try_manual_speak(
        "Blocked by quarantine.",
        request_id="overflow:q-blocked",
        now_ms=40_100,
    )
    assert blocked.kind == "component_unavailable"
    assert runtime.status().lane == "idle"
    assert runtime.status().speech_quarantined_generation == 1

    # Same-generation ready must hold quarantine.
    assert runtime.admit(
        NarrativeCommand.component_health(
            "overflow:q-hold",
            40_110,
            component="tts",
            generation=1,
            status="ready",
            reason=None,
        )
    ).accepted
    held = runtime.reduce_next()
    assert held is not None
    assert "tts_quarantine_held" in held.effects
    assert runtime.status().component_health["tts"] == "unavailable"

    # Under ordinary overflow while still quarantined: mailbox rejects first.
    _fill_ordinary_partition(runtime)
    overloaded = await runtime.try_manual_speak(
        "Blocked by overflow too.",
        request_id="overflow:q-overloaded",
        now_ms=40_200,
    )
    assert overloaded.kind == "mailbox_overloaded"
    status = runtime.status()
    assert status.lane == "idle"
    assert status.speech_quarantined_generation == 1
    assert "mailbox_overloaded" in status.reason_codes
    assert len(runtime._mailbox) == NarrativeMailbox.ORDINARY_CELLS  # noqa: SLF001
    assert "overflow:q-overloaded" not in runtime._manual_latches  # noqa: SLF001
