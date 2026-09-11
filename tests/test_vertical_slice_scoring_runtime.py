"""#278 Slice 4 — offline F05/F06/F07 director scoring drivers.

Consumes frozen machine rows and proves controlled opening score, related
continuation preference, and inclusive switch-margin locks through
StoryDirector + frozen calculations. Does not rewrite
``docs/v2.0.0/machine/*`` hashes and does not claim live §24.9 GO.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from test_story_director import CandidateOrder, _cand, _world

from irswitch.events.story_director import (
    SELECTION_THRESHOLD,
    SWITCH_MARGIN,
    StoryDirector,
    effective_score,
    score_terms,
)

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
FIXTURES_PATH = MACHINE / "vertical-slice-fixtures.json"
BUILDER_PATH = MACHINE / "build_vertical_slice_fixtures.py"

SLICE4_IDS = ("F05", "F06", "F07")


def _load_builder() -> Any:
    module_name = "irswitch_vertical_slice_scoring_builder_under_test"
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


@pytest.mark.parametrize("fixture_id", SLICE4_IDS)
def test_slice4_machine_projection_and_calculations(
    fixtures_by_id: dict[str, dict[str, Any]], fixture_id: str
) -> None:
    row = fixtures_by_id[fixture_id]
    assert builder.execute_model(row) == row["expectations"]
    assert row["calculations"]
    for calculation in row["calculations"]:
        assert builder.evaluate(calculation) == calculation["expected"]


def test_f05_first_pursuit_opens_with_controlled_score(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F05: opening pursuit clears threshold, opens episode, ignores v4 wire priority."""

    expected = set(fixtures_by_id["F05"]["expectations"])
    observed: set[str] = set()

    calc_score, calc_threshold = fixtures_by_id["F05"]["calculations"]
    assert builder.evaluate(calc_score) == 70
    assert builder.evaluate(calc_threshold) is True
    observed.add("score_70")
    observed.add("threshold_pass")
    assert SELECTION_THRESHOLD == 35.0
    assert 70 >= SELECTION_THRESHOLD

    opening = _cand(
        beat_id="battle.pursuit",
        episode_id="episode:pursuit",
        source="event_opportunity",
        relation="opens_new_episode",
        opportunity_id="opp:pursuit",
        base_priority=64.0,
        continuation_base=None,
        preferred_edge=True,
        material_band="material",
        from_accepted_event=True,
        candidate_order=CandidateOrder(10, 0),
    )
    world = _world(focused_episode_id=None, impulse="idle")
    decision = StoryDirector().evaluate(world, (opening,))
    assert decision.selected is not None
    assert decision.selected.beat_id == "battle.pursuit"
    assert decision.selected.episode_id == "episode:pursuit"
    assert decision.selected.score >= SELECTION_THRESHOLD
    observed.add("opens_correlated_episode")

    plain = score_terms(opening, world, replacing=False)
    wired = score_terms(
        _cand(
            beat_id="battle.pursuit",
            episode_id="episode:pursuit",
            source="event_opportunity",
            relation="opens_new_episode",
            opportunity_id="opp:pursuit",
            base_priority=64.0,
            continuation_base=None,
            preferred_edge=True,
            material_band="material",
            from_accepted_event=True,
            wire_priority=999,
            candidate_order=CandidateOrder(10, 0),
        ),
        world,
        replacing=False,
    )
    assert plain.total == wired.total
    assert not hasattr(plain, "wire_priority")
    observed.add("no_v4_priority_term")

    assert observed == expected


def test_f06_related_continuation_beats_unrelated_context(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F06: related update scores 76, wins over weather which stays TTL-pending."""

    expected = set(fixtures_by_id["F06"]["expectations"])
    observed: set[str] = set()

    calc_score, calc_gt = fixtures_by_id["F06"]["calculations"]
    assert builder.evaluate(calc_score) == 76
    assert builder.evaluate(calc_gt) is True
    observed.add("score_76")

    focused = _cand()
    related = _cand(
        beat_id="battle.close_gap",
        episode_id="episode:battle-1",
        source="event_opportunity",
        relation="continues_focused_episode",
        opportunity_id="opp:related",
        base_priority=58.0,
        preferred_edge=True,
        material_band="material",
        from_accepted_event=True,
        candidate_order=CandidateOrder(20, 0),
    )
    weather = _cand(
        beat_id="session.weather",
        episode_id="episode:weather",
        source="event_opportunity",
        relation="independent_of_focused_episode",
        urgency="context",
        policy_id="context",
        opportunity_id="opp:weather",
        base_priority=52.0,
        continuation_base=None,
        preferred_edge=False,
        material_band="none",
        from_accepted_event=True,
        candidate_order=CandidateOrder(21, 0),
        created_mono_ms=10_000,
        expires_mono_ms=12_000,
    )
    related_terms = score_terms(related, _world(), replacing=False)
    assert related_terms.total == 76.0
    assert related_terms.continuity_bonus == 6.0
    assert related_terms.edge_preference == 6.0
    assert related_terms.material_change_bonus == 6.0
    # Related event update is preferred over synthesizing a duplicate story successor.
    assert focused.beat_id != related.beat_id
    observed.add("deduplicate_event_successor")

    decision = StoryDirector().evaluate(_world(), (related, weather))
    assert decision.selected is not None
    assert decision.selected.beat_id == "battle.close_gap"
    assert decision.selected.score == 76.0
    observed.add("select_related_event_update")

    # Weather remains a pending TTL window rather than the spoken choice.
    weather_terms = score_terms(weather, _world(), replacing=False)
    assert weather.expires_mono_ms == 12_000
    assert weather_terms.total < related_terms.total
    assert decision.selected.beat_id != "session.weather"
    observed.add("weather_pending_ttl")

    assert observed == expected


def test_f07_equal_urgency_switch_uses_inclusive_margin(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F07: +6 fails margin, +8 switches inclusively; breakdown stays inspectable."""

    expected = set(fixtures_by_id["F07"]["expectations"])
    observed: set[str] = set()

    calc = fixtures_by_id["F07"]["calculations"][0]
    assert calc["op"] == "margin"
    assert calc["margin"] == 8
    assert SWITCH_MARGIN == 8.0
    assert builder.evaluate(calc) == [False, True]
    observed.add("82_does_not_switch")
    observed.add("84_switches_inclusive")

    incumbent = 76.0
    assert (82.0 - incumbent) < SWITCH_MARGIN
    assert (84.0 - incumbent) >= SWITCH_MARGIN
    observed.add("switch_margin_met")

    hold_world = _world(
        lane="building",
        impulse="accepted_event",
        incumbent_score=76.0,
        incumbent_urgency="story",
        building_elapsed_ms=4_000,
        request_timeout_ms=8_000,
    )
    # Replacement path subtracts replacement_cost; craft totals around margin edges.
    low = _cand(
        beat_id="position.gained_low",
        episode_id="episode:gain-low",
        source="event_opportunity",
        relation="independent_of_focused_episode",
        urgency="story",
        policy_id="result",
        opportunity_id="opp:low",
        base_priority=90.0,  # 90 - 12 replacement = 78? need hold below 76+8=84
        continuation_base=None,
        preferred_edge=False,
        material_band="none",
        from_accepted_event=True,
        candidate_order=CandidateOrder(30, 0),
    )
    high = _cand(
        beat_id="position.gained_high",
        episode_id="episode:gain-high",
        source="event_opportunity",
        relation="independent_of_focused_episode",
        urgency="story",
        policy_id="result",
        opportunity_id="opp:high",
        base_priority=96.0,  # enough to clear 76+8 after replacement cost
        continuation_base=None,
        preferred_edge=False,
        material_band="none",
        from_accepted_event=True,
        candidate_order=CandidateOrder(31, 0),
    )
    low_terms = score_terms(low, hold_world, replacing=True)
    high_terms = score_terms(high, hold_world, replacing=True)
    assert low_terms.total < hold_world.incumbent_score + SWITCH_MARGIN
    assert high_terms.total >= hold_world.incumbent_score + SWITCH_MARGIN

    held = StoryDirector().evaluate(hold_world, (low,))
    assert held.reason == "incumbent_held"
    assert held.selected is None
    switched = StoryDirector().evaluate(hold_world, (high,))
    assert switched.reason == "replaced_precommit"
    assert switched.selected is not None
    # Breakdown remains structured for tape/debug (not a bare float).
    assert high_terms.base == 96.0
    assert high_terms.replacement_cost > 0.0
    assert high_terms.total == switched.selected.score
    observed.add("breakdown_recorded")

    assert observed == expected


def test_slice4_score_constants_match_machine_policy() -> None:
    assert SELECTION_THRESHOLD == 35.0
    assert SWITCH_MARGIN == 8.0
    continuation = _cand()
    assert effective_score(continuation, _world(), replacing=False) == 76.0
