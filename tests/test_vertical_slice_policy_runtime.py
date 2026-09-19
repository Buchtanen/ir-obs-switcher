"""#278 Slice 6 — offline F23/F37 director policy runtime drivers.

Consumes frozen machine rows and proves single-formula fatigue/order/story-cap
locks plus switch-policy locks that urgency sort and filler cannot undo.
Does not rewrite ``docs/v2.0.0/machine/*`` hashes and does not claim live §24.9 GO.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from test_story_director import CandidateOrder, _cand, _world

from irswitch.events.exposure_store import (
    PATTERN_HALF_LIFE_MS,
    SEMANTIC_HALF_LIFE_MS,
    half_life_decay,
)
from irswitch.events.story_director import (
    GLOBAL_CONSECUTIVE_CAP,
    SWITCH_MARGIN,
    StoryDirector,
    score_terms,
)

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
FIXTURES_PATH = MACHINE / "vertical-slice-fixtures.json"
BUILDER_PATH = MACHINE / "build_vertical_slice_fixtures.py"

SLICE6_IDS = ("F23", "F37")


def _load_builder() -> Any:
    module_name = "irswitch_vertical_slice_policy_builder_under_test"
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


@pytest.mark.parametrize("fixture_id", SLICE6_IDS)
def test_slice6_machine_projection_and_calculations(
    fixtures_by_id: dict[str, dict[str, Any]], fixture_id: str
) -> None:
    row = fixtures_by_id[fixture_id]
    assert builder.execute_model(row) == row["expectations"]
    for calculation in row.get("calculations") or ():
        assert builder.evaluate(calculation) == calculation["expected"]


def test_f23_fatigue_order_and_story_cap_share_one_formula(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F23: half-life fatigue, stable (40,3) order, effective cap 2, closing still eligible."""

    expected = set(fixtures_by_id["F23"]["expectations"])
    observed: set[str] = set()

    calc_semantic, calc_pattern, calc_cap = fixtures_by_id["F23"]["calculations"]
    assert builder.evaluate(calc_semantic) == 0.5
    assert builder.evaluate(calc_pattern) == 0.5
    assert builder.evaluate(calc_cap) == 2
    assert half_life_decay(90_000, SEMANTIC_HALF_LIFE_MS) == 0.5
    assert half_life_decay(180_000, PATTERN_HALF_LIFE_MS) == 0.5
    # Named coefficients are applied later; decay itself is base-2 half-life only.
    assert half_life_decay(90_000, SEMANTIC_HALF_LIFE_MS) != __import__("math").exp(-1)
    observed.add("fatigue_half_each")

    left = _cand(
        beat_id="story.left",
        episode_id="episode:timing",
        source="story_successor",
        relation="continues_focused_episode",
        opportunity_id="opp:left",
        base_priority=40.0,
        continuation_base=40.0,
        preferred_edge=False,
        material_band="none",
        candidate_order=CandidateOrder(40, 3),
    )
    right = _cand(
        beat_id="story.right",
        episode_id="episode:timing",
        source="story_successor",
        relation="continues_focused_episode",
        opportunity_id="opp:right",
        base_priority=40.0,
        continuation_base=40.0,
        preferred_edge=False,
        material_band="none",
        candidate_order=CandidateOrder(40, 4),
    )
    open_world = _world(
        focused_episode_id="episode:timing",
        consecutive_story_beats=0,
        story_consecutive_cap=3,
    )
    # Offer reverse insertion order; stable (40,3) must still win.
    decision = StoryDirector().evaluate(open_world, (right, left))
    assert decision.selected is not None
    assert decision.selected.beat_id == "story.left"
    assert decision.selected.candidate_order == CandidateOrder(40, 3)
    observed.add("stable_order_40_3")

    assert GLOBAL_CONSECUTIVE_CAP == 3
    effective_cap = min(GLOBAL_CONSECUTIVE_CAP, 2)
    assert effective_cap == 2
    assert builder.evaluate(calc_cap) == effective_cap
    observed.add("effective_cap2")

    capped = _world(
        focused_episode_id="episode:timing",
        consecutive_story_beats=2,
        story_consecutive_cap=2,
    )
    blocked = StoryDirector().evaluate(capped, (left, right))
    assert blocked.selected is None
    assert all(record.reject_reason == "cadence_blocked" for record in blocked.records)
    observed.add("nonclosing_ineligible")

    closing = _cand(
        beat_id="story.close",
        episode_id="episode:timing",
        source="event_opportunity",
        relation="resolves_active_episode",
        opportunity_id="opp:close",
        base_priority=50.0,
        continuation_base=None,
        preferred_edge=False,
        material_band="none",
        from_accepted_event=True,
        urgency="critical",
        policy_id="critical",
        is_closing=True,
        is_critical=True,
        candidate_order=CandidateOrder(41, 0),
    )
    allowed = StoryDirector().evaluate(capped, (left, closing))
    assert allowed.selected is not None
    assert allowed.selected.beat_id == "story.close"
    observed.add("closure_critical_eligible")

    assert observed == expected


def test_f37_switch_policy_survives_urgency_sort_and_filler(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F37: inclusive margin, lower-urgency switch, critical priority, filler fallback-only."""

    expected = set(fixtures_by_id["F37"]["expectations"])
    observed: set[str] = set()

    focused = _cand()
    story_challenger = _cand(
        beat_id="story.challenger",
        episode_id="episode:other",
        source="event_opportunity",
        relation="independent_of_focused_episode",
        urgency="story",
        policy_id="result",
        opportunity_id="opp:story",
        base_priority=84.0,
        continuation_base=None,
        preferred_edge=False,
        material_band="none",
        from_accepted_event=True,
        candidate_order=CandidateOrder(10, 0),
    )
    margin = StoryDirector().evaluate(_world(), (focused, story_challenger))
    assert margin.reason == "switch_margin_met"
    assert margin.selected is not None
    assert margin.selected.beat_id == "story.challenger"
    assert margin.selected.score >= 76.0 + SWITCH_MARGIN
    observed.add("margin_switch")

    context_challenger = _cand(
        beat_id="context.challenger",
        episode_id="episode:context",
        source="event_opportunity",
        relation="independent_of_focused_episode",
        urgency="context",
        policy_id="context",
        opportunity_id="opp:context",
        base_priority=90.0,
        continuation_base=None,
        preferred_edge=False,
        material_band="none",
        from_accepted_event=True,
        candidate_order=CandidateOrder(11, 0),
    )
    lower = StoryDirector().evaluate(_world(), (focused, context_challenger))
    assert lower.reason == "switch_margin_met"
    assert lower.selected is not None
    assert lower.selected.beat_id == "context.challenger"
    observed.add("lower_urgency_can_switch")

    critical = _cand(
        beat_id="critical.challenger",
        episode_id="episode:critical",
        source="event_opportunity",
        relation="independent_of_focused_episode",
        urgency="critical",
        policy_id="critical",
        opportunity_id="opp:critical",
        base_priority=36.0,
        continuation_base=None,
        preferred_edge=False,
        material_band="none",
        from_accepted_event=True,
        is_critical=True,
        candidate_order=CandidateOrder(12, 0),
    )
    urgent = StoryDirector().evaluate(_world(), (focused, story_challenger, critical))
    assert urgent.reason == "higher_urgency_switch"
    assert urgent.selected is not None
    assert urgent.selected.beat_id == "critical.challenger"
    observed.add("critical_priority")

    filler = _cand(
        beat_id="filler.pad",
        episode_id="episode:filler",
        source="filler",
        relation="opens_new_episode",
        urgency="context",
        policy_id="filler",
        opportunity_id="opp:filler",
        base_priority=100.0,
        continuation_base=None,
        preferred_edge=False,
        material_band="none",
        from_accepted_event=False,
        candidate_order=CandidateOrder(13, 0),
    )
    with_story = StoryDirector().evaluate(
        _world(focused_episode_id=None), (filler, story_challenger)
    )
    assert with_story.selected is not None
    assert with_story.selected.beat_id == "story.challenger"
    only_filler = StoryDirector().evaluate(
        _world(focused_episode_id=None, impulse="silence", silence_impulse=True),
        (filler,),
    )
    assert only_filler.selected is not None
    assert only_filler.selected.beat_id == "filler.pad"
    observed.add("filler_fallback_only")

    building = _world(
        lane="building",
        impulse="accepted_event",
        incumbent_score=70.0,
        incumbent_urgency="story",
        focused_episode_id="episode:battle-1",
        building_elapsed_ms=4_000,
        request_timeout_ms=8_000,
    )
    replacement = _cand(
        beat_id="context.replacement",
        episode_id="episode:replacement",
        source="event_opportunity",
        relation="independent_of_focused_episode",
        urgency="context",
        policy_id="context",
        opportunity_id="opp:replacement",
        base_priority=90.0,
        continuation_base=None,
        preferred_edge=False,
        material_band="none",
        from_accepted_event=True,
        candidate_order=CandidateOrder(20, 0),
    )
    terms = score_terms(replacement, building, replacing=True)
    assert terms.base == 90.0
    assert terms.replacement_cost == 12.0
    assert terms.total == 78.0
    assert terms.total >= 70.0 + SWITCH_MARGIN
    replaced = StoryDirector().evaluate(building, (replacement,))
    assert replaced.reason == "replaced_precommit"
    assert replaced.selected is not None
    assert replaced.selected.beat_id == "context.replacement"
    observed.add("replacement_inclusive_78")

    successor = _cand(
        beat_id="story.successor",
        episode_id="episode:battle-1",
        source="story_successor",
        relation="continues_focused_episode",
        opportunity_id="opp:successor",
        base_priority=100.0,
        candidate_order=CandidateOrder(21, 0),
    )
    held_successor = StoryDirector().evaluate(building, (successor,))
    held_filler = StoryDirector().evaluate(building, (filler,))
    assert held_successor.reason == "incumbent_held"
    assert held_successor.selected is None
    assert held_filler.reason == "incumbent_held"
    assert held_filler.selected is None
    observed.add("no_non_event_replace")

    assert terms.total == replaced.selected.score
    assert hasattr(terms, "replacement_cost")
    assert hasattr(terms, "base")
    assert hasattr(terms, "continuity_bonus")
    observed.add("full_breakdown")

    assert observed == expected
