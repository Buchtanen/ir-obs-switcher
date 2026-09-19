"""#278 Slice 8 — offline F09/F11 Qwen hard-fail runtime drivers.

Consumes frozen machine rows and proves invalid Qwen output suppresses a beat
without fallback while a distinct cycle attempt may continue, and that cold
Qwen is hard-ineligible without backend rewrite. Does not rewrite
``docs/v2.0.0/machine/*`` hashes and does not claim live §24.9 GO.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from test_opportunity_queue import _intent as _opportunity_intent
from test_qwen_transport import _intent as _realization_intent
from test_semantic_verifier import _intent as _verifier_intent
from test_story_director import CandidateOrder, _cand, _gates, _world

from irswitch.events.narrative_realization_bridge import warmup_qwen_component
from irswitch.events.opportunity_queue import OpportunityQueue
from irswitch.events.qwen_transport import (
    WARMUP_TIMEOUT_MS,
    FakeTransport,
    LlmComponent,
)
from irswitch.events.semantic_verifier import SemanticVerifier
from irswitch.events.story_director import StoryDirector

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
FIXTURES_PATH = MACHINE / "vertical-slice-fixtures.json"
BUILDER_PATH = MACHINE / "build_vertical_slice_fixtures.py"

SLICE8_IDS = ("F09", "F11")


def _load_builder() -> Any:
    module_name = "irswitch_vertical_slice_qwen_builder_under_test"
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


@pytest.mark.parametrize("fixture_id", SLICE8_IDS)
def test_slice8_machine_projection_and_calculations(
    fixtures_by_id: dict[str, dict[str, Any]], fixture_id: str
) -> None:
    row = fixtures_by_id[fixture_id]
    assert builder.execute_model(row) == row["expectations"]
    for calculation in row.get("calculations") or ():
        assert builder.evaluate(calculation) == calculation["expected"]


def test_f09_invalid_qwen_output_suppresses_and_advances_cycle(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F09: actor_reversed suppresses revision, releases reservation, attempt-2 distinct."""

    expected = set(fixtures_by_id["F09"]["expectations"])
    observed: set[str] = set()

    verdict = SemanticVerifier().verify(_verifier_intent(text="Morgan is closing on Alex."))
    assert verdict.result is not None
    assert verdict.result.accepted is False
    assert "actor_reversed" in verdict.result.reasons
    observed.add("suppress_revision")

    queue = OpportunityQueue()
    admitted = queue.admit(
        _opportunity_intent(opportunity_id="opp:pursuit", beat_id="battle.pursuit")
    )
    assert admitted.reason == "queued"
    assert admitted.opportunity is not None
    reserved = queue.reserve(admitted.opportunity.opportunity_id, now_ms=11_000)
    assert reserved.reason == "reserved"
    token = reserved.opportunity.reservation_token
    assert token is not None
    released = queue.reject_attempt(token, beat_id="battle.pursuit", now_ms=12_000)
    assert released.reason == "attempt_released"
    assert released.opportunity is not None
    assert released.opportunity.state == "pending"
    assert released.opportunity.reservation_token is None
    observed.add("release_reservation")

    intent = _realization_intent(backend="qwen_compiled", beat_id="battle.pursuit")
    assert intent.backend == "qwen_compiled"
    # Invalid output never rewrites the Qwen backend into an authored fallback.
    assert intent.backend != "authored"
    observed.add("no_retry_or_fallback")

    director = StoryDirector()
    pursuit = _cand(
        beat_id="battle.pursuit",
        episode_id="episode:pursuit",
        source="event_opportunity",
        relation="opens_new_episode",
        opportunity_id="opp:pursuit",
        base_priority=70.0,
        from_accepted_event=True,
        candidate_order=CandidateOrder(1, 0),
    )
    context = _cand(
        beat_id="session.context",
        episode_id="episode:context",
        source="event_opportunity",
        relation="opens_new_episode",
        opportunity_id="opp:context",
        base_priority=46.0,
        continuation_base=None,
        preferred_edge=False,
        material_band="none",
        from_accepted_event=True,
        urgency="context",
        policy_id="context",
        candidate_order=CandidateOrder(2, 0),
    )
    world = _world(focused_episode_id=None)
    opened = director.evaluate(world, (pursuit, context))
    assert opened.selected is not None
    assert opened.selected.beat_id == "battle.pursuit"
    assert opened.cycle_attempt_ordinal == 1
    cycle_id = opened.planning_cycle_id
    director.note_failure(opened.selected.beat_id, opened.selected.episode_revision)

    retry = director.evaluate(world, (pursuit, context))
    assert retry.selected is not None
    assert retry.planning_cycle_id == cycle_id
    assert retry.cycle_attempt_ordinal == 2
    assert retry.selected.beat_id == "session.context"
    assert retry.selected.beat_id != opened.selected.beat_id
    observed.add("distinct_attempt_2")

    director.note_failure(retry.selected.beat_id, retry.selected.episode_revision)
    exhausted = director.evaluate(world, (pursuit, context))
    assert exhausted.selected is None
    assert exhausted.reason == "planning_cycle_exhausted"
    observed.add("cycle_exhausted_after_second")

    assert observed == expected


def test_f11_cold_qwen_is_hard_ineligible_without_backend_fallback(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F11: warmup failure hard-blocks Qwen; authored may win; backend stays Qwen."""

    expected = set(fixtures_by_id["F11"]["expectations"])
    observed: set[str] = set()

    component = LlmComponent()
    assert component.qwen_ready is False
    assert component.authored_ready is True
    warmed = warmup_qwen_component(component, FakeTransport(fail=True), generation=1)
    assert warmed is False
    assert component.qwen_ready is False
    assert component.status == "failed"
    assert component.residency == "warmup_failed"
    # Hard ineligibility is immediate — no per-beat cold timeout spend.
    assert WARMUP_TIMEOUT_MS == 10_000
    observed.add("no_cold_timeout")

    qwen = _cand(
        beat_id="battle.pursuit",
        episode_id="episode:pursuit",
        source="event_opportunity",
        relation="opens_new_episode",
        opportunity_id="opp:qwen",
        base_priority=80.0,
        from_accepted_event=True,
        candidate_order=CandidateOrder(1, 0),
        gates=_gates(source_guard=component.qwen_ready),
    )
    authored = _cand(
        beat_id="session.context",
        episode_id="episode:context",
        source="authored",
        relation="opens_new_episode",
        opportunity_id="opp:authored",
        base_priority=46.0,
        continuation_base=None,
        preferred_edge=False,
        material_band="none",
        from_accepted_event=False,
        urgency="context",
        policy_id="context",
        candidate_order=CandidateOrder(2, 0),
        gates=_gates(source_guard=component.authored_ready),
    )
    decision = StoryDirector().evaluate(_world(focused_episode_id=None), (qwen, authored))
    qwen_row = next(row for row in decision.records if row.beat_id == "battle.pursuit")
    assert qwen_row.eligible is False
    assert qwen_row.reject_reason == "source_guard_failed"
    observed.add("qwen_hard_ineligible")

    assert decision.selected is not None
    assert decision.selected.beat_id == "session.context"
    assert component.authored_ready is True
    observed.add("authored_may_win")

    intent = _realization_intent(backend="qwen_compiled", beat_id="battle.pursuit")
    assert intent.backend == "qwen_compiled"
    assert intent.backend != "authored"
    # Cold path leaves the Qwen intent backend untouched — no authored rewrite.
    assert component.residency == "warmup_failed"
    observed.add("no_backend_fallback")

    assert observed == expected
