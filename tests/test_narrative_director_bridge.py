"""#284 live StoryDirector world/candidate seed from context facts."""

from __future__ import annotations

from pathlib import Path

from test_narrative_context_batch import _event, _fact_view, _timeline

from irswitch.contracts.command import NarrativeCommand
from irswitch.events import __all__ as events_exports
from irswitch.events.narrative import partition_context_batches
from irswitch.events.narrative_director_bridge import (
    DirectorSnapshot,
    build_director_snapshot,
    candidate_from_event,
)
from irswitch.events.narrative_runtime import NarrativeRuntime
from irswitch.events.story_director import StoryDirector

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "irswitch"
    / "events"
    / "narrative_director_bridge.py"
)


def _impulse_part(*, revision: int = 3, fanout: int = 11, index: int = 0):
    return partition_context_batches(
        timeline=_timeline(revision=revision),
        fact_view=_fact_view(1, revision=9),
        events=(_event(index, fanout=fanout),),
        fanout_stream_sequence=fanout,
    )[0]


def _event_cmd(command_id: str, *, revision: int = 3, fanout: int = 11) -> NarrativeCommand:
    part = _impulse_part(revision=revision, fanout=fanout)
    return NarrativeCommand.context_batch(command_id, 1000, part)


def test_bridge_not_exported_from_events_package() -> None:
    assert "build_director_snapshot" not in events_exports
    assert "narrative_director_bridge" not in events_exports
    assert SOURCE.is_file()


def test_candidate_from_event_is_event_opportunity() -> None:
    event = _event(0, fanout=42)
    candidate = candidate_from_event(event, reducer_sequence=7, source_ordinal=0)
    assert candidate.source == "event_opportunity"
    assert candidate.beat_id == "battle.pursuit"
    assert candidate.from_accepted_event is True
    assert candidate.tape_channel == "race.battle.closing"
    assert candidate.base_priority >= 35.0
    assert candidate.gates.required_facts_available is True
    assert candidate.created_mono_ms <= 1000
    assert candidate.expires_mono_ms > candidate.created_mono_ms


def test_build_director_snapshot_selects_speakable_event() -> None:
    part = _impulse_part(revision=5, fanout=20)
    snapshot = build_director_snapshot(
        events=part.batch.events,
        timeline=part.batch.timeline,
        fact_view=part.batch.fact_view,
        lane="idle",
        impulse="event",
        reducer_sequence=3,
    )
    assert isinstance(snapshot, DirectorSnapshot)
    assert snapshot.world.lane == "idle"
    assert snapshot.world.impulse == "event"
    assert snapshot.world.stream_epoch == 1
    assert len(snapshot.candidates) == 1
    decision = StoryDirector().evaluate(snapshot.world, snapshot.candidates)
    assert decision.speech == "speak"
    assert decision.selected is not None
    assert decision.selected.beat_id == "battle.pursuit"


def test_build_director_snapshot_building_uses_accepted_event_impulse() -> None:
    part = _impulse_part()
    snapshot = build_director_snapshot(
        events=part.batch.events,
        timeline=part.batch.timeline,
        fact_view=part.batch.fact_view,
        lane="building",
        impulse="accepted_event",
        reducer_sequence=1,
        incumbent_score=40.0,
        incumbent_urgency="story",
    )
    assert snapshot.world.lane == "building"
    assert snapshot.world.impulse == "accepted_event"
    decision = StoryDirector().evaluate(snapshot.world, snapshot.candidates)
    assert decision.reason == "replaced_precommit"
    assert decision.selected is not None


def test_build_director_snapshot_empty_events_yields_no_speak() -> None:
    timeline = _timeline()
    facts = _fact_view(1)
    snapshot = build_director_snapshot(
        events=(),
        timeline=timeline,
        fact_view=facts,
        lane="idle",
        impulse="event",
        reducer_sequence=1,
    )
    assert snapshot.candidates == ()
    decision = StoryDirector().evaluate(snapshot.world, snapshot.candidates)
    assert decision.speech == "silence"
    assert decision.reason == "no_candidate"


def test_runtime_auto_seeds_director_from_live_context() -> None:
    runtime = NarrativeRuntime(story_director=StoryDirector())
    runtime.enable()
    runtime.admit(_event_cmd("live:seed", revision=80, fanout=80))
    planned = runtime.reduce_next()
    assert planned is not None
    assert "director_live_seeded" in planned.effects
    assert "director_evaluated" in planned.effects
    assert "director_selected" in planned.effects
    assert "plan_dispatched" in planned.effects
    assert planned.lane_after == "building"
    assert runtime.director_selected_beat_for_test() == "battle.pursuit"


def test_runtime_manual_seed_not_overwritten_by_context() -> None:
    from test_story_director import _cand as _director_cand
    from test_story_director import _world as _director_world

    director = StoryDirector()
    runtime = NarrativeRuntime(story_director=director)
    runtime.enable()
    runtime.seed_director_for_test(world=_director_world(), candidates=(_director_cand(),))
    runtime.admit(_event_cmd("live:manual", revision=81, fanout=81))
    planned = runtime.reduce_next()
    assert planned is not None
    assert "director_live_seeded" not in planned.effects
    assert "director_selected" in planned.effects
    assert runtime.director_selected_beat_for_test() == "battle.approach"


def test_runtime_without_director_skips_live_seed() -> None:
    runtime = NarrativeRuntime()
    runtime.enable()
    runtime.admit(_event_cmd("live:none", revision=82, fanout=82))
    planned = runtime.reduce_next()
    assert planned is not None
    assert "director_live_seeded" not in planned.effects
    assert "plan_dispatched" in planned.effects
