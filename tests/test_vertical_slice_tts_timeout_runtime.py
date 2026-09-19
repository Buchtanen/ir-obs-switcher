"""#278 Slice 16 — offline F26 unresponsive-TTS lane watchdog drivers.

Consumes frozen machine rows and proves NarrativeRuntime ownership of TTS
start/playback/stop watchdogs: start timeout releases an unconsumed reservation,
playback-stage timeout keeps a consumed acceptance then stop-quarantines the
backend, admission stays blocked under quarantine, late callbacks are no-ops,
and only a higher backend generation restores speech. Does not rewrite
``docs/v2.0.0/machine/*`` hashes and does not claim live §24.9 GO.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from test_narrative_runtime import _tts_callback

from irswitch.events.narrative_runtime import NarrativeCommand, NarrativeRuntime

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
FIXTURES_PATH = MACHINE / "vertical-slice-fixtures.json"
BUILDER_PATH = MACHINE / "build_vertical_slice_fixtures.py"

SLICE16_IDS = ("F26",)


def _load_builder() -> Any:
    module_name = "irswitch_vertical_slice_tts_timeout_builder_under_test"
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


@pytest.mark.parametrize("fixture_id", SLICE16_IDS)
def test_slice16_machine_projection_and_calculations(
    fixtures_by_id: dict[str, dict[str, Any]], fixture_id: str
) -> None:
    row = fixtures_by_id[fixture_id]
    assert builder.execute_model(row) == row["expectations"]
    for calculation in row.get("calculations") or ():
        assert builder.evaluate(calculation) == calculation["expected"]


@pytest.mark.asyncio
async def test_f26_unresponsive_tts_cannot_strand_or_overlap_lane(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F26: start/playback/stop watchdogs quarantine TTS without lane overlap."""

    expected = set(fixtures_by_id["F26"]["expectations"])
    observed: set[str] = set()

    # --- start timeout releases an unconsumed reservation ---
    runtime = NarrativeRuntime(speech_deadline_delay_s=0.02)
    runtime.enable()
    runtime.admit(
        NarrativeCommand.manual_speak(
            "f26:start", 1_000, text="Start watchdog.", admission_ordinal=1
        )
    )
    committed = runtime.reduce_next()
    assert committed is not None
    await runtime.apply_effects(committed.effects)
    assert runtime.status().speech_accepted_at_mono_ms is None
    await runtime.wait_deadline_timers_idle()
    start_elapsed = runtime.reduce_next()
    assert start_elapsed is not None
    await runtime.apply_effects(start_elapsed.effects)
    await runtime.wait_deadline_timers_idle()
    stop_elapsed = runtime.reduce_next()
    assert stop_elapsed is not None
    await runtime.apply_effects(stop_elapsed.effects)
    assert runtime.status().speech_quarantine_reason == "tts_start_timeout"
    assert runtime.status().speech_accepted_at_mono_ms is None
    assert runtime.status().speech_quarantined_generation == 1
    observed.add("start_timeout_unconsumed")

    # --- playback-stage timeout keeps consumed acceptance, then stop-quarantines ---
    runtime = NarrativeRuntime(speech_deadline_delay_s=0.02)
    runtime.enable()
    runtime.admit(
        NarrativeCommand.manual_speak(
            "f26:playback", 2_000, text="Playback watchdog.", admission_ordinal=1
        )
    )
    committed = runtime.reduce_next()
    assert committed is not None
    await runtime.apply_effects(committed.effects)
    utterance = dict(runtime.current_utterance_token() or {})
    assert utterance
    runtime.admit(_tts_callback("PLAYBACK_ACCEPTED", utterance, command_id="f26:pb"))
    accepted = runtime.reduce_next()
    assert accepted is not None
    await runtime.apply_effects(accepted.effects)
    assert runtime.status().speech_accepted_at_mono_ms is not None
    observed.add("playback_timeout_consumed")

    await runtime.wait_deadline_timers_idle()
    playback_elapsed = runtime.reduce_next()
    assert playback_elapsed is not None
    await runtime.apply_effects(playback_elapsed.effects)
    await runtime.wait_deadline_timers_idle()
    stop_elapsed = runtime.reduce_next()
    assert stop_elapsed is not None
    await runtime.apply_effects(stop_elapsed.effects)
    assert runtime.status().speech_quarantine_reason == "tts_stop_timeout"
    assert runtime.status().speech_quarantined_generation == 1
    assert "tts_backend_quarantined" in stop_elapsed.effects
    observed.add("stop_timeout_quarantine")

    # --- admission blocked while quarantined ---
    runtime.admit(
        NarrativeCommand.manual_speak(
            "f26:blocked", 3_000, text="Should not speak.", admission_ordinal=2
        )
    )
    blocked = runtime.reduce_next()
    assert blocked is not None
    assert "tts_unavailable" in blocked.effects
    observed.add("admission_blocked")

    # --- late callbacks are no-ops ---
    runtime.admit(_tts_callback("PLAYBACK_ACCEPTED", utterance, command_id="f26:late-pb"))
    late_pb = runtime.reduce_next()
    assert late_pb is not None
    assert late_pb.disposition.startswith("ignored")
    assert "stale_playback_token" in late_pb.effects
    runtime.admit(_tts_callback("SPEECH_COMPLETED", utterance, command_id="f26:late-done"))
    late_done = runtime.reduce_next()
    assert late_done is not None
    assert late_done.disposition.startswith("ignored")
    assert "stale_speech_token" in late_done.effects
    observed.add("late_noop")

    # --- only a higher backend generation restores admission ---
    runtime.admit(
        NarrativeCommand.component_health(
            "f26:hold",
            4_000,
            component="tts",
            generation=1,
            status="ready",
            reason=None,
        )
    )
    held = runtime.reduce_next()
    assert held is not None
    assert "tts_quarantine_held" in held.effects
    assert runtime.status().speech_quarantined_generation == 1

    runtime.admit(
        NarrativeCommand.component_health(
            "f26:clear",
            4_010,
            component="tts",
            generation=2,
            status="ready",
            reason=None,
        )
    )
    cleared = runtime.reduce_next()
    assert cleared is not None
    assert "tts_quarantine_cleared" in cleared.effects
    assert runtime.status().speech_quarantined_generation is None
    observed.add("higher_generation_restores")

    assert observed == expected
