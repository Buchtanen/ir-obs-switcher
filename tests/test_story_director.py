"""#262 StoryDirector hard gates, §9.2 scores and §23.3 selection."""

from __future__ import annotations

import json
from pathlib import Path

from irswitch.events import __all__ as events_exports
from irswitch.events.beat_plan import CandidateOrder
from irswitch.events.story_director import (
    DECISION_CAPACITY,
    SCHEMA_VERSION,
    SELECTION_THRESHOLD,
    SWITCH_MARGIN,
    DirectorCandidate,
    DirectorWorld,
    EligibilityGates,
    FatigueTerms,
    StoryDirector,
    effective_score,
    score_terms,
)

SOURCE = Path(__file__).resolve().parents[1] / "src" / "irswitch" / "events" / "story_director.py"
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "story_director"


def _gates(**overrides: bool) -> EligibilityGates:
    values = {
        "phase_allowed": True,
        "occurrence_current": True,
        "lineage_current": True,
        "required_facts_available": True,
        "confidence_sufficient": True,
        "episode_valid": True,
        "not_expired": True,
        "not_conflicting": True,
        "cadence_allowed": True,
        "audience_allowed": True,
        "source_guard": True,
    }
    values.update(overrides)
    return EligibilityGates(**values)


def _cand(**overrides: object) -> DirectorCandidate:
    values: dict[str, object] = {
        "beat_id": "battle.approach",
        "episode_id": "episode:battle-1",
        "episode_revision": 1,
        "source": "story_successor",
        "relation": "continues_focused_episode",
        "urgency": "story",
        "policy_id": "live_story",
        "tape_channel": "race.battle.closing",
        "candidate_order": CandidateOrder(40, 3),
        "opportunity_id": None,
        "base_priority": 64.0,
        "continuation_base": 58.0,
        "penalty_coefficient": 0.8,
        "material_band": "material",
        "preferred_edge": True,
        "closure_edge": False,
        "unspoken_outcome": False,
        "created_mono_ms": 10_000,
        "expires_mono_ms": 20_000,
        "is_closing": False,
        "is_critical": False,
        "from_accepted_event": False,
        "wire_priority": None,
        "gates": _gates(),
        "fatigue": FatigueTerms(),
    }
    values.update(overrides)
    return DirectorCandidate(**values)  # type: ignore[arg-type]


def _world(**overrides: object) -> DirectorWorld:
    values: dict[str, object] = {
        "now_ms": 10_000,
        "stream_epoch": 3,
        "focused_episode_id": "episode:battle-1",
        "consecutive_story_beats": 0,
        "story_consecutive_cap": 3,
        "impulse": "post_beat",
    }
    values.update(overrides)
    return DirectorWorld(**values)  # type: ignore[arg-type]


def test_invalid_fact_or_lineage_never_selected() -> None:
    director = StoryDirector()
    broken = _cand(
        beat_id="position.pass",
        source="event_opportunity",
        relation="independent_of_focused_episode",
        urgency="critical",
        policy_id="critical",
        base_priority=90.0,
        opportunity_id="opp:pass",
        from_accepted_event=True,
        gates=_gates(required_facts_available=False, lineage_current=False),
    )
    decision = director.evaluate(_world(), (broken, _cand()))
    assert decision.reason == "active_story_continuation"
    assert decision.selected is not None
    assert decision.selected.beat_id == "battle.approach"
    rejected = [item for item in decision.records if item.beat_id == "position.pass"]
    assert rejected[0].eligible is False
    assert rejected[0].reject_reason == "hard_guard_failed"
    assert rejected[0].score > SELECTION_THRESHOLD


def test_same_state_selects_same_beat() -> None:
    director = StoryDirector()
    candidates = (
        _cand(),
        _cand(
            beat_id="timing.lap.completed",
            episode_id="episode:lap-1",
            source="event_opportunity",
            relation="independent_of_focused_episode",
            opportunity_id="opp:lap",
            policy_id="result",
            base_priority=78.0,
            candidate_order=CandidateOrder(41, 0),
        ),
    )
    first = director.evaluate(_world(), candidates)
    second = director.evaluate(_world(), candidates)
    assert first.selected == second.selected
    assert first.reason == second.reason
    assert first.selected is not None


def test_filler_only_when_story_empty() -> None:
    director = StoryDirector()
    filler = _cand(
        beat_id="filler.quiet_track",
        episode_id="episode:fill",
        source="filler",
        relation=None,
        urgency="background",
        policy_id="filler",
        base_priority=24.0,
        continuation_base=None,
        preferred_edge=False,
        material_band="none",
        from_accepted_event=False,
    )
    blocked = director.evaluate(_world(silence_impulse=True), (_cand(), filler))
    assert blocked.selected is not None
    assert blocked.selected.source != "filler"
    only = director.evaluate(_world(silence_impulse=True, focused_episode_id=None), (filler,))
    assert only.reason == "highest_valid_candidate"
    assert only.selected is not None
    assert only.selected.beat_id == "filler.quiet_track"
    assert only.selected.score >= SELECTION_THRESHOLD


def test_f23_fatigue_tie_break_and_consecutive_cap() -> None:
    older = _cand(candidate_order=CandidateOrder(40, 3), fatigue=FatigueTerms(0.5, 0.5, 0.0, 0.0))
    newer = _cand(
        beat_id="battle.attack_range",
        candidate_order=CandidateOrder(40, 4),
        fatigue=FatigueTerms(0.5, 0.5, 0.0, 0.0),
    )
    terms = score_terms(older, _world(), replacing=False)
    assert terms.semantic_fatigue_penalty == 4.0
    assert terms.pattern_fatigue_penalty == 2.5
    decision = StoryDirector().evaluate(_world(), (newer, older))
    assert decision.selected is not None
    assert decision.selected.candidate_order == CandidateOrder(40, 3)

    capped = StoryDirector().evaluate(
        _world(consecutive_story_beats=2, story_consecutive_cap=2),
        (
            _cand(),
            _cand(
                beat_id="battle.won",
                source="event_opportunity",
                relation="resolves_active_episode",
                urgency="story",
                policy_id="result",
                base_priority=78.0,
                opportunity_id="opp:won",
                is_closing=True,
                from_accepted_event=True,
                preferred_edge=False,
                closure_edge=True,
                unspoken_outcome=True,
                candidate_order=CandidateOrder(41, 0),
            ),
        ),
    )
    assert capped.selected is not None
    assert capped.selected.beat_id == "battle.won"
    successor = next(item for item in capped.records if item.beat_id == "battle.approach")
    assert successor.eligible is False
    assert successor.reject_reason == "cadence_blocked"


def test_f37_switch_margin_urgency_and_replacement() -> None:
    continuation = _cand()
    assert effective_score(continuation, _world(), replacing=False) == 76.0
    story = _cand(
        beat_id="position.gained",
        episode_id="episode:gain",
        source="event_opportunity",
        relation="independent_of_focused_episode",
        opportunity_id="opp:a",
        policy_id="result",
        base_priority=84.0,
        continuation_base=None,
        preferred_edge=False,
        material_band="none",
        candidate_order=CandidateOrder(50, 0),
        from_accepted_event=True,
    )
    context = _cand(
        beat_id="session.sof_brief",
        episode_id="episode:sof",
        source="event_opportunity",
        relation="independent_of_focused_episode",
        urgency="context",
        policy_id="context",
        opportunity_id="opp:b",
        base_priority=90.0,
        continuation_base=None,
        preferred_edge=False,
        material_band="none",
        candidate_order=CandidateOrder(51, 0),
        from_accepted_event=True,
    )
    critical = _cand(
        beat_id="session.flag.yellow",
        episode_id="episode:flag",
        source="event_opportunity",
        relation="independent_of_focused_episode",
        urgency="critical",
        policy_id="critical",
        opportunity_id="opp:c",
        base_priority=36.0,
        continuation_base=None,
        preferred_edge=False,
        material_band="none",
        is_critical=True,
        candidate_order=CandidateOrder(52, 0),
        from_accepted_event=True,
    )
    filler = _cand(
        beat_id="filler.quiet_track",
        episode_id="episode:fill",
        source="filler",
        relation=None,
        urgency="background",
        policy_id="filler",
        base_priority=100.0,
        continuation_base=None,
        preferred_edge=False,
        material_band="none",
    )
    margin = StoryDirector().evaluate(_world(), (continuation, story))
    assert margin.reason == "switch_margin_met"
    assert margin.selected is not None
    assert margin.selected.beat_id == "position.gained"
    context_win = StoryDirector().evaluate(_world(), (continuation, context))
    assert context_win.reason == "switch_margin_met"
    assert context_win.selected is not None
    assert context_win.selected.beat_id == "session.sof_brief"
    both = StoryDirector().evaluate(_world(), (continuation, story, critical))
    assert both.reason == "higher_urgency_switch"
    assert both.selected is not None
    assert both.selected.beat_id == "session.flag.yellow"
    filled = StoryDirector().evaluate(_world(silence_impulse=True), (continuation, filler))
    assert filled.selected is not None
    assert filled.selected.beat_id == "battle.approach"

    incumbent = _world(
        lane="building",
        impulse="accepted_event",
        incumbent_score=70.0,
        incumbent_urgency="story",
        building_elapsed_ms=4_000,
        request_timeout_ms=8_000,
    )
    replace = StoryDirector().evaluate(incumbent, (context,))
    assert replace.reason == "replaced_precommit"
    assert replace.selected is not None
    assert replace.selected.score == 78.0
    assert replace.cycle_attempt_ordinal == 1
    too_low = _cand(
        beat_id="session.weather_brief",
        episode_id="episode:wx",
        source="event_opportunity",
        relation="independent_of_focused_episode",
        urgency="context",
        policy_id="context",
        opportunity_id="opp:wx",
        base_priority=89.0,
        continuation_base=None,
        preferred_edge=False,
        material_band="none",
        from_accepted_event=True,
        candidate_order=CandidateOrder(53, 0),
    )
    held = StoryDirector().evaluate(incumbent, (too_low,))
    assert held.reason == "incumbent_held"
    assert held.selected is None
    timer = StoryDirector().evaluate(
        _world(lane="building", impulse="timer", incumbent_score=70.0, incumbent_urgency="story"),
        (continuation,),
    )
    assert timer.reason == "incumbent_held"


def test_below_threshold_is_silence() -> None:
    weak = _cand(
        source="event_opportunity",
        relation="independent_of_focused_episode",
        opportunity_id="opp:weak",
        base_priority=30.0,
        continuation_base=None,
        preferred_edge=False,
        material_band="none",
        from_accepted_event=True,
    )
    decision = StoryDirector().evaluate(_world(focused_episode_id=None), (weak,))
    assert decision.reason == "below_threshold"
    assert decision.selected is None
    assert decision.speech == "silence"
    assert all(
        item.eligible is False or item.score < SELECTION_THRESHOLD for item in decision.records
    )


def test_planning_cycle_replace_and_attempt_two() -> None:
    director = StoryDirector()
    first = _cand(source="event_opportunity", opportunity_id="opp:1", from_accepted_event=True)
    second = _cand(
        beat_id="battle.side_by_side",
        source="event_opportunity",
        opportunity_id="opp:2",
        urgency="critical",
        policy_id="critical",
        base_priority=90.0,
        from_accepted_event=True,
        is_critical=True,
        candidate_order=CandidateOrder(41, 0),
    )
    opened = director.evaluate(_world(), (first, second))
    assert opened.selected is not None
    assert opened.cycle_attempt_ordinal == 1
    cycle = opened.planning_cycle_id
    director.note_failure(opened.selected.beat_id, opened.selected.episode_revision)
    retry = director.evaluate(_world(), (first, second))
    assert retry.selected is not None
    assert retry.planning_cycle_id == cycle
    assert retry.cycle_attempt_ordinal == 2
    assert retry.selected.beat_id != opened.selected.beat_id
    director.note_failure(retry.selected.beat_id, retry.selected.episode_revision)
    exhausted = director.evaluate(_world(), (first, second))
    assert exhausted.reason == "planning_cycle_exhausted"
    assert exhausted.selected is None
    replacement = director.evaluate(
        _world(
            lane="building",
            impulse="accepted_event",
            incumbent_score=40.0,
            incumbent_urgency="story",
        ),
        (second,),
    )
    assert replacement.reason == "replaced_precommit"
    assert replacement.planning_cycle_id != cycle
    assert replacement.cycle_attempt_ordinal == 1


def test_v4_wire_priority_never_enters_score() -> None:
    plain = _cand(wire_priority=None)
    wired = _cand(wire_priority=99)
    world = _world()
    assert (
        score_terms(plain, world, replacing=False).total
        == score_terms(wired, world, replacing=False).total
    )
    assert "wire" not in SOURCE.read_text(
        encoding="utf-8"
    ).lower() or "wire_priority" in SOURCE.read_text(encoding="utf-8")
    breakdown = score_terms(wired, world, replacing=False)
    assert breakdown.total == 76.0
    assert SWITCH_MARGIN == 8.0


def test_named_penalties_only() -> None:
    terms = score_terms(
        _cand(
            fatigue=FatigueTerms(
                semantic=1.0, pattern=1.0, lexical_jaccard=0.25, channel_pressure=6.0
            )
        ),
        _world(),
        replacing=False,
    )
    assert terms.semantic_fatigue_penalty == 8.0
    assert terms.pattern_fatigue_penalty == 5.0
    assert terms.lexical_repetition_penalty == 2.0
    assert terms.event_penalty == 4.8
    assert not hasattr(terms, "family_penalty")
    assert not hasattr(terms, "role_penalty")


def test_replay_fixtures_cover_transition_identity_and_expiry() -> None:
    transition = json.loads((FIXTURES / "transition.json").read_text(encoding="utf-8"))
    identity = json.loads((FIXTURES / "counterfactual_identity.json").read_text(encoding="utf-8"))
    expiry = json.loads((FIXTURES / "expiry.json").read_text(encoding="utf-8"))
    director = StoryDirector()
    step = director.evaluate(
        _world(now_ms=transition["nowMs"]),
        (
            _cand(
                beat_id=transition["beatId"],
                candidate_order=CandidateOrder(*transition["candidateOrder"]),
            ),
        ),
    )
    assert step.reason == transition["expectReason"]
    assert step.selected is not None
    assert step.selected.beat_id == transition["beatId"]
    assert step.schema_version == SCHEMA_VERSION

    other = director.evaluate(
        _world(),
        (
            _cand(),
            _cand(
                beat_id="battle.pressure_behind",
                episode_id=identity["otherEpisodeId"],
                source="event_opportunity",
                relation="independent_of_focused_episode",
                opportunity_id="opp:other",
                candidate_order=CandidateOrder(8, 0),
            ),
        ),
    )
    assert other.selected is not None
    assert other.selected.episode_id != identity["otherEpisodeId"]

    expired = director.evaluate(
        _world(now_ms=expiry["nowMs"]),
        (
            _cand(
                gates=_gates(not_expired=False),
                expires_mono_ms=expiry["expiresMonoMs"],
            ),
        ),
    )
    assert expired.reason == expiry["expectReason"]
    assert expired.selected is None


def test_records_rejection_reasons_and_exports_stay_out() -> None:
    director = StoryDirector()
    decision = director.evaluate(
        _world(),
        (
            _cand(gates=_gates(source_guard=False), beat_id="session.field_fact"),
            _cand(
                beat_id="timing.lap.hot",
                episode_revision=9,
                gates=_gates(),
            ),
        ),
    )
    reasons = {item.beat_id: item.reject_reason for item in decision.records}
    assert reasons["session.field_fact"] == "source_guard_failed"
    director.note_failure("timing.lap.hot", 9)
    suppressed = director.evaluate(
        _world(),
        (_cand(beat_id="timing.lap.hot", episode_revision=9),),
    )
    assert any(item.reject_reason == "attempt_suppressed" for item in suppressed.records)
    assert DECISION_CAPACITY == 128
    source = SOURCE.read_text(encoding="utf-8")
    assert "story_director" not in events_exports
    for banned in (
        "NarrativeRuntime",
        "eval(",
        "exec(",
        "compile(",
        "irswitch.commentary",
        "irswitch.overlay",
        "math.exp",
    ):
        assert banned not in source
