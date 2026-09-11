"""#278 Slice 3 — offline F02/F03/F04 transition runtime drivers.

Consumes frozen machine rows and proves stage lineage / rewind / confirmed
restart locks through StreamTimeline + FactLedger + SpeechLane + FreshnessGate.
Does not rewrite ``docs/v2.0.0/machine/*`` hashes and does not claim live §24.9 GO.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from test_freshness_commit import _token as _freshness_token
from test_freshness_commit import _world as _freshness_world
from test_opportunity_queue import _intent as _opportunity_intent
from test_speech_lane import _intent as _speech_intent
from test_stream_timeline import _kinds, _session, _tick
from test_timing_family_replay_cases import (
    Q1,
    R2,
    _admit_minimal_rewind,
)

from irswitch.contracts import ContractViolation, FactScope, FactStatus
from irswitch.events.fact_ledger import FactLedger
from irswitch.events.freshness_commit import FreshnessGate
from irswitch.events.opportunity_queue import OpportunityQueue
from irswitch.events.speech_lane import SpeechLane
from irswitch.logic.stream_timeline import StreamTimeline

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
FIXTURES_PATH = MACHINE / "vertical-slice-fixtures.json"
BUILDER_PATH = MACHINE / "build_vertical_slice_fixtures.py"

SLICE3_IDS = ("F02", "F03", "F04")


def _load_builder() -> Any:
    module_name = "irswitch_vertical_slice_transition_builder_under_test"
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


@pytest.mark.parametrize("fixture_id", SLICE3_IDS)
def test_slice3_machine_projection_emits_frozen_expectations(
    fixtures_by_id: dict[str, dict[str, Any]], fixture_id: str
) -> None:
    row = fixtures_by_id[fixture_id]
    assert builder.execute_model(row) == row["expectations"]
    for calculation in row.get("calculations") or ():
        assert builder.evaluate(calculation) == calculation["expected"]


def test_f02_canonical_stage_progression_with_inheritance(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F02: P0>Q0>R0 lineage; current race facts; historical needs past marker."""

    expected = set(fixtures_by_id["F02"]["expectations"])
    observed: set[str] = set()

    timeline = StreamTimeline()
    timeline.observe(_tick(1_000, epoch=0, state="inactive"))
    practice = timeline.observe(_tick(2_000, epoch=1, session=_session(session_num=0)))
    qualifying = timeline.observe(_tick(3_000, epoch=1, session=_session(session_num=1)))
    race = timeline.observe(_tick(4_000, epoch=1, session=_session(session_num=2)))

    assert practice.snapshot["lineageId"] == "1:practice:0"
    assert qualifying.snapshot["lineageId"] == "1:practice:0>1:qualifying:0"
    assert race.snapshot["lineageId"] == "1:practice:0>1:qualifying:0>1:race:0"
    observed.add("lineage_p0_q0_r0")

    assert race.snapshot["stage"] == "race"
    assert race.snapshot["occurrenceId"] == "1:race:0"
    assert "warmup" not in race.snapshot["lineageId"]
    observed.add("no_absent_stage")

    ledger = FactLedger()
    _admit_minimal_rewind(ledger)
    # After forward progression into race, active battle marker is race-scoped.
    race_fact = ledger.current("battle.closing", subject_id="car:12", object_id="car:34")
    assert race_fact is not None
    assert str(race_fact.occurrence_id) == R2
    observed.add("current_facts_r0")

    with pytest.raises(ContractViolation, match="historical|recap"):
        ledger.historical(
            "session.qualifying_result",
            occurrence_id=Q1,
            subject_id="car:12",
        )
    recap = ledger.historical(
        "session.qualifying_result",
        occurrence_id=Q1,
        subject_id="car:12",
        framing="recap",
    )
    assert recap is not None
    assert recap.status in {FactStatus.HISTORICAL, FactStatus.SUPERSEDED}
    assert recap.scope is FactScope.DOWNSTREAM
    observed.add("historical_requires_past_marker")

    assert observed == expected


def test_f03_rewind_race_to_qualifying_ordered_and_cancels_speech(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F03: ordered R0 end→Q1 start; no SESSION_REWOUND; cancel old speech; lineage evolves."""

    expected = set(fixtures_by_id["F03"]["expectations"])
    observed: set[str] = set()

    timeline = StreamTimeline()
    timeline.observe(_tick(1_000, epoch=0, state="inactive"))
    timeline.observe(_tick(2_000, epoch=1, session=_session(session_num=0)))
    timeline.observe(_tick(3_000, epoch=1, session=_session(session_num=1)))
    race = timeline.observe(
        _tick(4_000, epoch=1, session=_session(session_num=2, session_time_s=80.0))
    )
    assert race.snapshot["lineageId"] == "1:practice:0>1:qualifying:0>1:race:0"

    rewind = timeline.observe(_tick(5_000, epoch=1, session=_session(session_num=1)))
    assert _kinds(rewind) == ["SESSION_ENDED", "SESSION_STARTED"]
    assert "SESSION_REWOUND" not in _kinds(rewind)
    observed.add("ordered_r0_end_q1_start")
    observed.add("no_session_rewound_command")
    assert rewind.snapshot["lineageId"] == "1:practice:0>1:qualifying:1"
    observed.add("lineage_p0_q1")

    retained_ids = {str(item.occurrence_id) for item in rewind.occurrences}
    assert "1:practice:0" in retained_ids
    observed.add("persistent_downstream")

    lane = SpeechLane()
    started = lane.try_start(_speech_intent())
    assert started.reason in {"started", "started_building"}
    assert lane.commit("utt:1", now_ms=10_100).lane == "committed"
    cancelled = lane.cancel("occurrence_reset", now_ms=10_200)
    assert cancelled.reason == "cancel_requested"
    assert cancelled.lane == "stopping"
    observed.add("cancel_old_speech")

    race_again = timeline.observe(
        _tick(6_000, epoch=1, session=_session(session_num=2, session_time_s=12.0))
    )
    assert race_again.snapshot["lineageId"] == "1:practice:0>1:qualifying:1>1:race:1"
    observed.add("lineage_p0_q1_r1")

    assert observed == expected


def test_f04_same_session_confirmed_restart_without_false_positive(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F04: confirmed same-ref restart; archive; invalidate old opp; unconfirmed is no-op."""

    expected = set(fixtures_by_id["F04"]["expectations"])
    observed: set[str] = set()

    timeline = StreamTimeline()
    timeline.observe(_tick(1_000, epoch=0, state="inactive"))
    first = timeline.observe(
        _tick(2_000, epoch=1, session=_session(session_num=2, session_time_s=80.0))
    )
    old_occurrence = first.snapshot["occurrenceId"]
    assert old_occurrence == "1:race:0"

    unconfirmed = timeline.observe(
        _tick(2_050, epoch=1, session=_session(session_num=2, session_time_s=10.0))
    )
    assert "SESSION_RESTARTED" not in _kinds(unconfirmed)
    assert unconfirmed.snapshot["occurrenceId"] == old_occurrence
    observed.add("no_false_restart")

    confirmed = timeline.observe(
        _tick(2_160, epoch=1, session=_session(session_num=2, session_time_s=10.2))
    )
    assert _kinds(confirmed) == ["SESSION_RESTARTED"]
    assert confirmed.snapshot["transitionReasons"] == ["session_restarted"]
    observed.add("one_session_restarted")
    new_occurrence = confirmed.snapshot["occurrenceId"]
    assert new_occurrence == "1:race:1"
    assert new_occurrence != old_occurrence
    observed.add("new_occurrence")

    retained = {str(item.occurrence_id) for item in confirmed.occurrences}
    assert old_occurrence in retained
    assert new_occurrence in retained
    observed.add("archive_by_scope")

    queue = OpportunityQueue()
    admitted = queue.admit(
        _opportunity_intent(
            opportunity_id="opp:f04-old",
            occurrence_id=str(old_occurrence),
            lineage_id=str(old_occurrence),
            stream_epoch=1,
            created_mono_ms=2_000,
        )
    )
    assert admitted.opportunity is not None
    stale = FreshnessGate().evaluate(
        _freshness_token(
            opportunity_id="opp:f04-old",
            occurrence_id=str(old_occurrence),
            lineage_id=str(old_occurrence),  # occurrence is the lineage tail
        ),
        _freshness_world(
            occurrence_id=str(new_occurrence),
            lineage_id=str(new_occurrence),
        ),
    )
    assert stale.verdict == "invalidated"
    observed.add("invalidate_old_opportunities")

    assert observed == expected
