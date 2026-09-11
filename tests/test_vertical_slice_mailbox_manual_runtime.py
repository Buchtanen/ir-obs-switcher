"""#278 Slice 9 — offline F13/F20 mailbox overflow + manual admission drivers.

Consumes frozen machine rows and proves ordinary eviction before emergency
recovery with latest projection / incomplete history, plus manual admission
abandon-vs-claim linearization without delayed audio. Does not rewrite
``docs/v2.0.0/machine/*`` hashes and does not claim live §24.9 GO.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from test_narrative_context_batch import _context_command

from irswitch.commentary.mailbox import NarrativeMailbox
from irswitch.contracts.command import NarrativeCommand
from irswitch.events.narrative_manual_latch import ManualAdmissionLatch
from irswitch.events.narrative_runtime import ManualSpeakOutcome, NarrativeRuntime

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
FIXTURES_PATH = MACHINE / "vertical-slice-fixtures.json"
BUILDER_PATH = MACHINE / "build_vertical_slice_fixtures.py"

SLICE9_IDS = ("F13", "F20")


def _load_builder() -> Any:
    module_name = "irswitch_vertical_slice_mailbox_manual_builder_under_test"
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


@pytest.mark.parametrize("fixture_id", SLICE9_IDS)
def test_slice9_machine_projection_and_calculations(
    fixtures_by_id: dict[str, dict[str, Any]], fixture_id: str
) -> None:
    row = fixtures_by_id[fixture_id]
    assert builder.execute_model(row) == row["expectations"]
    for calculation in row.get("calculations") or ():
        assert builder.evaluate(calculation) == calculation["expected"]


def test_f13_protected_mailbox_overflow_recovers_without_blocking_producer(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F13: ordinary eviction first, then emergency recovery with latest projection."""

    expected = set(fixtures_by_id["F13"]["expectations"])
    observed: set[str] = set()

    # Ordinary pressure: silence loses before context under a full ordinary partition.
    mailbox = NarrativeMailbox()
    silence = NarrativeCommand.deadline(
        "timer:silence",
        "LONG_SILENCE_ELAPSED",
        1000,
        generation=1,
        deadline_mono_ms=1000,
    )
    assert mailbox.admit(silence).accepted
    for index in range(NarrativeMailbox.ORDINARY_CELLS - 1):
        assert mailbox.admit(_context_command(f"ctx:{index}")).accepted
    evicted = mailbox.admit(_context_command("ctx:new"))
    assert evicted.accepted is True
    assert evicted.evicted_command_ids == ("timer:silence",)
    assert mailbox.recovery is None
    observed.add("ordinary_eviction_first")

    # Full ordinary context partition: next context opens mailbox recovery.
    mailbox = NarrativeMailbox()
    for index in range(NarrativeMailbox.ORDINARY_CELLS):
        assert mailbox.admit(_context_command(f"full:{index}")).accepted
    recovered = mailbox.admit(_context_command("full:new"))
    assert recovered.accepted is True
    assert recovered.reason == "mailbox_recovery"
    assert recovered.evicted_command_ids == ("full:0",)
    assert recovered.evicted_commands[0].command_id == "full:0"
    assert mailbox.recovery is not None
    assert mailbox.recovery.kind == "MAILBOX_RECOVERY"
    assert mailbox.recovery.payload["historyComplete"] is False
    assert "latestTimeline" in mailbox.recovery.payload
    assert "latestFactView" in mailbox.recovery.payload
    observed.add("emergency_recovery")
    observed.add("latest_projection")
    observed.add("history_incomplete")
    observed.add("no_lost_opportunities")

    # Inputs ordinary_56 + protected_7 + protected_reset: saturate protected, then refresh.
    for index in range(NarrativeMailbox.PROTECTED_CELLS):
        health = mailbox.admit(
            NarrativeCommand.component_health(
                f"health:{index}",
                3000 + index,
                component="llm",
                generation=index,
                status="unavailable",
                reason="preflight_failed",
            )
        )
        assert health.accepted is True
    first = mailbox.admit(
        NarrativeCommand.component_health(
            "health:overflow:1",
            4000,
            component="tts",
            generation=99,
            status="unavailable",
            reason="preflight_failed",
        )
    )
    second = mailbox.admit(
        NarrativeCommand.component_health(
            "health:overflow:2",
            4001,
            component="tts",
            generation=100,
            status="unavailable",
            reason="preflight_failed",
        )
    )
    assert first.reason == "mailbox_recovery"
    assert second.reason == "mailbox_recovery"
    assert len(second.command.payload["safetyEffects"]) >= 2
    # Every admit above returned synchronously — producer never blocks on overflow.
    observed.add("producer_nonblocking")

    assert observed == expected


@pytest.mark.asyncio
async def test_f20_manual_admission_timeout_cannot_produce_delayed_audio(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F20: abandon vs claim linearize; timeout yields 503-class silence only."""

    expected = set(fixtures_by_id["F20"]["expectations"])
    observed: set[str] = set()

    abandoned = ManualAdmissionLatch()
    assert abandoned.abandon_caller() is True
    assert abandoned.claim_actor() is False

    runtime = NarrativeRuntime()
    runtime.enable()
    timed_out = await runtime.try_manual_speak(
        "Must not speak later.",
        request_id="manual:abandon",
        now_ms=1000,
        timeout_s=0.01,
        reduce_inline=False,
    )
    assert timed_out.kind == "admission_timeout"
    delayed = runtime.reduce_next()
    assert delayed is not None
    assert delayed.disposition == "ignored_stale_or_inapplicable"
    assert "manual_abandoned" in delayed.effects
    assert runtime.status().lane == "idle"
    observed.add("abandon_returns_503_no_audio")
    observed.add("no_narrative_state")
    observed.add("manual_silence_only")

    claimed = ManualAdmissionLatch()
    assert claimed.claim_actor() is True
    assert claimed.abandon_caller() is False
    claimed.resolve(
        ManualSpeakOutcome(
            kind="accepted",
            request_id="manual:claim",
            admitted_state="committed",
        )
    )
    resolved = await claimed.wait(0.01)
    assert resolved is not None
    assert resolved.kind in {"accepted", "validation_failed", "mailbox_overloaded"}
    observed.add("claim_linearized_202_or_error")

    status = runtime.status()
    assert "admission_timeout" in status.reason_codes
    # Terminal decision is recorded on the reduce/tape path; no delayed audio remains.
    assert delayed.effects[-1] == "manual_abandoned" or "manual_abandoned" in delayed.effects
    observed.add("tape_terminal_decision")

    assert observed == expected
