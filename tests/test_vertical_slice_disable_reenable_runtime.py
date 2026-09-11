"""#278 Slice 15 — offline F16 disable/re-enable-within-broadcast drivers.

Consumes frozen machine rows and proves NarrativeRuntime ownership of mid-stream
commentary disable/re-enable inside one OBS broadcast (close run 3, trailer flush,
manual independence while disabled, allocate run 4 / stream epoch 2, incomplete
history across the gap, no state leak into the new run). Does not rewrite
``docs/v2.0.0/machine/*`` hashes and does not claim live §24.9 GO.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from test_narrative_runtime import (
    _context_with_timeline,
    _pure_fact,
    _timeline_run,
    _tts_callback,
)

from irswitch.events.narrative_runtime import NarrativeCommand, NarrativeRuntime

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
FIXTURES_PATH = MACHINE / "vertical-slice-fixtures.json"
BUILDER_PATH = MACHINE / "build_vertical_slice_fixtures.py"

SLICE15_IDS = ("F16",)


def _load_builder() -> Any:
    module_name = "irswitch_vertical_slice_disable_reenable_builder_under_test"
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


@pytest.mark.parametrize("fixture_id", SLICE15_IDS)
def test_slice15_machine_projection_and_calculations(
    fixtures_by_id: dict[str, dict[str, Any]], fixture_id: str
) -> None:
    row = fixtures_by_id[fixture_id]
    assert builder.execute_model(row) == row["expectations"]
    for calculation in row.get("calculations") or ():
        assert builder.evaluate(calculation) == calculation["expected"]


@pytest.mark.asyncio
async def test_f16_disable_reenable_within_broadcast_is_runtime_owned(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F16: disable closes run + flushes trailer; re-enable allocates a fresh epoch."""

    expected = set(fixtures_by_id["F16"]["expectations"])
    observed: set[str] = set()

    flushed: list[dict[str, object]] = []

    async def tape_flush(token: dict[str, object]) -> None:
        flushed.append(dict(token))
        await asyncio.sleep(0)

    runtime = NarrativeRuntime(tape_effect=tape_flush, shutdown_flush_timeout_s=1.0)
    runtime.enable()

    runtime.admit(
        _context_with_timeline(
            "f16:open",
            _timeline_run(revision=20, stream_epoch=1, narrative_run_active=True),
            fanout=20,
            with_event=True,
        )
    )
    opened = runtime.reduce_next()
    assert opened is not None
    assert runtime.status().narrative_run_active is True
    assert runtime.status().stream_epoch == 1
    plan_run3 = runtime.status().planning_cycle_id

    runtime.admit(
        _context_with_timeline(
            "f16:disable",
            _timeline_run(
                revision=21,
                stream_epoch=1,
                narrative_run_active=False,
                transition_reasons=["narrative_disabled"],
            ),
            fanout=21,
        )
    )
    disabled = runtime.reduce_next()
    assert disabled is not None
    assert "narrative_run_closed" in disabled.effects
    assert "building_cancelled_on_disable" in disabled.effects
    assert "effect:flush_tape" in disabled.effects
    assert runtime.status().narrative_run_active is False
    assert runtime.status().stream_epoch == 1
    assert runtime.status().lane == "idle"
    observed.add("close_run3")
    observed.add("commentary_disabled")

    await runtime.apply_effects(disabled.effects)
    await runtime.wait_effects_idle()
    assert flushed
    observed.add("complete_trailer")

    plan_before_manual = runtime.status().planning_cycle_id
    runtime.admit(
        NarrativeCommand.manual_speak(
            "f16:manual",
            6_000,
            text="Independent while disabled.",
            admission_ordinal=1,
        )
    )
    manual = runtime.reduce_next()
    assert manual is not None
    assert "manual_committed" in manual.effects
    assert runtime.status().planning_cycle_id == plan_before_manual
    assert not any(effect.startswith("planning_cycle_opened") for effect in manual.effects)
    observed.add("manual_independent")

    utterance = runtime.current_utterance_token()
    assert utterance is not None
    runtime.admit(_tts_callback("PLAYBACK_ACCEPTED", utterance, command_id="f16:manual:pb"))
    assert runtime.reduce_next() is not None
    runtime.admit(_tts_callback("SPEECH_COMPLETED", utterance, command_id="f16:manual:done"))
    done = runtime.reduce_next()
    assert done is not None
    assert runtime.status().lane == "idle"
    assert runtime.current_utterance_token() is None

    latest = _pure_fact("f16:latest", revision=80, fanout=80)
    runtime.admit(
        NarrativeCommand.recovery(
            "f16:recovery",
            9_000,
            latest_context=latest.context_part,
            loss_first_sequence=1,
            loss_last_sequence=2,
            safety_effects=(latest.safety_effect(),),
        )
    )
    recovered = runtime.reduce_next()
    assert recovered is not None
    assert "history_incomplete" in recovered.effects
    assert runtime.status().history_complete is False
    assert "history_incomplete" in runtime.status().reason_codes
    observed.add("incomplete_history")

    runtime.admit(
        _context_with_timeline(
            "f16:enable",
            _timeline_run(
                revision=22,
                stream_epoch=2,
                narrative_run_active=True,
                transition_reasons=["narrative_enabled"],
            ),
            fanout=22,
            with_event=True,
        )
    )
    enabled = runtime.reduce_next()
    assert enabled is not None
    assert "narrative_run_opened" in enabled.effects
    assert "stream_epoch_allocated:2" in enabled.effects
    assert runtime.status().narrative_run_active is True
    assert runtime.status().stream_epoch == 2
    observed.add("allocate_run4")
    observed.add("one_enabled_mid_stream")

    # Prior run's building/speech must not leak; new epoch opens a fresh planning cycle.
    assert runtime.current_utterance_token() is None
    assert runtime.status().lane == "building"
    assert runtime.status().planning_cycle_id != plan_run3
    assert "building_cancelled_on_disable" in disabled.effects
    assert "narrative_run_closed" in disabled.effects
    observed.add("no_state_leak")

    assert observed == expected
