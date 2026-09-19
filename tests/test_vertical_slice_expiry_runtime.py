"""#278 Slice 2 — offline F08/F15/F24 expiry runtime drivers.

Consumes frozen machine rows and proves no-prepared-queue / fact-only /
half-open TTL locks through OpportunityQueue + NarrativeRuntime. Does not
rewrite ``docs/v2.0.0/machine/*`` hashes and does not claim live §24.9 GO.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from test_narrative_runtime import (
    _drive_to,
    _event_impulse,
    _pure_fact,
    _result_for,
    _tts_callback,
)
from test_opportunity_queue import _ctx as _arbitration_ctx
from test_opportunity_queue import _intent as _opportunity_intent

from irswitch.commentary.mailbox import NarrativeMailbox
from irswitch.contracts.command import NarrativeCommand
from irswitch.events.narrative_runtime import NarrativeRuntime
from irswitch.events.opportunity_queue import OpportunityQueue

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
FIXTURES_PATH = MACHINE / "vertical-slice-fixtures.json"
BUILDER_PATH = MACHINE / "build_vertical_slice_fixtures.py"

SLICE2_IDS = ("F08", "F15", "F24")


def _load_builder() -> Any:
    module_name = "irswitch_vertical_slice_expiry_builder_under_test"
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


@pytest.mark.parametrize("fixture_id", SLICE2_IDS)
def test_slice2_machine_projection_emits_frozen_expectations(
    fixtures_by_id: dict[str, dict[str, Any]], fixture_id: str
) -> None:
    row = fixtures_by_id[fixture_id]
    assert builder.execute_model(row) == row["expectations"]
    for calculation in row.get("calculations") or ():
        assert builder.evaluate(calculation) == calculation["expected"]


def test_f08_speaking_critical_pass_never_prepares_a_queue(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F08: critical arrival while speaking updates truth without interrupt/queue."""

    expected = set(fixtures_by_id["F08"]["expectations"])
    observed: set[str] = set()

    runtime = _drive_to("speaking")
    utterance = runtime.current_utterance_token()
    assert utterance is not None
    assert runtime.status().lane == "speaking"

    admitted = runtime.admit(_event_impulse("f08:critical", revision=40, fanout=40))
    assert admitted.accepted
    reduced = runtime.reduce_next()
    assert reduced is not None
    assert runtime.status().lane == "speaking"
    assert runtime.current_utterance_token() == utterance
    assert "truth_updated_without_barge_in" in reduced.effects
    assert not any(effect.startswith("plan_dispatched") for effect in reduced.effects)
    assert not any(effect.startswith("planning_cycle_opened:") for effect in reduced.effects)
    observed.add("no_interrupt")
    observed.add("no_prepared_queue")
    observed.add("truth_updates_immediately")

    done = runtime.admit(_tts_callback("SPEECH_COMPLETED", utterance, command_id="f08:done"))
    assert done.accepted
    terminal = runtime.reduce_next()
    assert terminal is not None
    assert runtime.status().lane == "idle"
    assert "director_reentry_eligible" in terminal.effects
    live = runtime.admit(_event_impulse("f08:terminal-live", revision=41, fanout=41))
    assert live.accepted
    planned = runtime.reduce_next()
    assert planned is not None
    assert "plan_dispatched" in planned.effects
    observed.add("terminal_replans_live")

    queue = OpportunityQueue()
    admitted_opp = queue.admit(
        _opportunity_intent(opportunity_id="opp:f08-expired", created_mono_ms=1_000)
    )
    opportunity = admitted_opp.opportunity
    assert opportunity is not None
    expired = queue.expire_due(opportunity.expires_mono_ms)
    assert expired and expired[0].opportunity is not None
    assert expired[0].opportunity.state == "expired"
    assert expired[0].opportunity.terminal_reason == "expired_ttl"
    silent = queue.arbitrate(
        _arbitration_ctx(
            now_ms=opportunity.expires_mono_ms,
            last_spoken_beat_id="battle.pursuit",
        )
    )
    assert silent.selected is None
    observed.add("expired_never_narrated")

    assert observed == expected


def test_f15_fact_only_invalidation_is_not_a_speech_trigger(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F15: fact-only batch closes/cancels without opportunity or director pass."""

    expected = set(fixtures_by_id["F15"]["expectations"])
    observed: set[str] = set()

    runtime = _drive_to("building")
    before_cycle = runtime.status().planning_cycle_id
    admitted = runtime.admit(_pure_fact("f15:fact-only", revision=50, fanout=50))
    assert admitted.accepted
    result = runtime.reduce_next()
    assert result is not None
    assert result.lane_after == "idle"
    assert "context_applied" in result.effects
    assert "director_skipped_pure_fact" in result.effects
    assert "fact_only_wait" in result.effects
    assert "building_invalidated" in result.effects
    assert not any(effect.startswith("plan_dispatched") for effect in result.effects)
    assert not any(effect.startswith("planning_cycle_opened:") for effect in result.effects)
    assert runtime.status().planning_cycle_id == before_cycle
    observed.update(
        {
            "apply_new_view",
            "close_episode",
            "cancel_preaccept",
            "no_opportunity",
            "no_director_pass",
        }
    )

    later = runtime.admit(_event_impulse("f15:later", revision=51, fanout=51))
    assert later.accepted
    follow = runtime.reduce_next()
    assert follow is not None
    # Cancelled preaccept stays dead: a later impulse must start from idle, not resume it.
    assert follow.lane_before == "idle"
    assert "plan_dispatched" in follow.effects
    assert runtime.status().lane == "building"
    observed.add("later_cannot_continue")

    assert observed == expected


def test_f24_half_open_validity_expires_building_without_fallback(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F24: half-open invalid at deadline; generation cancels; mailbox skip equal."""

    expected = set(fixtures_by_id["F24"]["expectations"])
    observed: set[str] = set()
    row = fixtures_by_id["F24"]
    calculation = row["calculations"][0]
    assert calculation["op"] == "half_open"
    assert builder.evaluate(calculation) is False
    observed.add("half_open_invalid")

    queue = OpportunityQueue()
    admitted = queue.admit(_opportunity_intent(opportunity_id="opp:f24", created_mono_ms=40_000))
    opportunity = admitted.opportunity
    assert opportunity is not None
    assert opportunity.expires_mono_ms == 50_000
    assert opportunity.is_valid_at(49_999)
    assert not opportunity.is_valid_at(50_000)
    reserved = queue.reserve(opportunity.opportunity_id, now_ms=41_000)
    assert reserved.reason == "reserved"
    expired = queue.expire_due(50_000)
    assert expired and expired[0].opportunity is not None
    assert expired[0].opportunity.state == "expired"
    assert expired[0].opportunity.terminal_reason == "expired_ttl"
    observed.add("expired_ttl")
    observed.add("cancel_generation")

    runtime = _drive_to("building")
    token = runtime.current_realization_token()
    assert token is not None
    generation = runtime._validity_generation  # noqa: SLF001
    assert runtime.admit(
        NarrativeCommand.deadline(
            "f24:validity",
            "VALIDITY_DEADLINE_ELAPSED",
            50_000,
            generation=generation,
            deadline_mono_ms=50_000,
        )
    ).accepted
    expired_reduce = runtime.reduce_next()
    assert expired_reduce is not None
    assert runtime.status().lane == "idle"
    assert not any(effect.startswith("plan_dispatched") for effect in expired_reduce.effects)
    assert not any(effect.startswith("planning_cycle_opened:") for effect in expired_reduce.effects)
    observed.add("no_director")
    observed.add("no_attempt2")
    assert runtime.admit(
        NarrativeCommand.realization_result(
            "f24:late-worker",
            "REALIZATION_SUCCEEDED",
            50_001,
            request_id=str(token["requestId"]),
            request_ordinal=int(token["requestOrdinal"]),  # type: ignore[arg-type]
            dispatch_generation=int(token["dispatchGeneration"]),  # type: ignore[arg-type]
            result=_result_for(token),
        )
    ).accepted
    late = runtime.reduce_next()
    assert late is not None
    assert late.disposition == "ignored_stale_or_inapplicable" or runtime.status().lane == "idle"
    observed.add("late_worker_stale")

    full = NarrativeRuntime()
    full.enable()
    for index in range(NarrativeMailbox.ORDINARY_CELLS):
        assert full.admit(
            NarrativeCommand.deadline(
                f"f24:fill:{index}",
                "LONG_SILENCE_ELAPSED",
                9_000 + index,
                generation=1 + index,
                deadline_mono_ms=9_000 + index,
            )
        ).accepted
    before = full.status().lane
    skipped = full.admit(
        NarrativeCommand.deadline(
            "f24:skip-validity",
            "VALIDITY_DEADLINE_ELAPSED",
            50_000,
            generation=1,
            deadline_mono_ms=50_000,
        )
    )
    assert skipped.reason == "deadline_admission_skipped"
    assert "deadline_admission_skipped" in full.status().reason_codes
    assert full.status().lane == before
    observed.add("skipped_admission_sweep_equal")

    assert observed == expected
