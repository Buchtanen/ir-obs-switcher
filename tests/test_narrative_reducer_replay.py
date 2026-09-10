"""#284 NarrativeRuntime reducer-state tape replay equivalence (library slice)."""

from __future__ import annotations

from pathlib import Path

from test_narrative_runtime import (
    _director_cand,
    _director_world,
    _event_impulse,
    _pure_fact,
    _result_for,
)

from irswitch.contracts.command import NarrativeCommand
from irswitch.events import __all__ as events_exports
from irswitch.events.narrative_reducer_replay import (
    capture_reducer_trace,
    replay_reducer_trace,
    traces_equivalent,
)

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "irswitch"
    / "events"
    / "narrative_reducer_replay.py"
)
RACE_SOURCE = Path(__file__).resolve().parents[1] / "src" / "irswitch" / "race" / "runtime.py"


def test_reducer_replay_helper_not_exported() -> None:
    assert "capture_reducer_trace" not in events_exports
    assert "replay_reducer_trace" not in events_exports
    assert "traces_equivalent" not in events_exports
    assert "ReducerTrace" not in events_exports
    assert SOURCE.is_file()


def test_capture_and_replay_traces_are_equivalent() -> None:
    commands = (
        _pure_fact("trace:1"),
        NarrativeCommand.deadline(
            "trace:2", "LONG_SILENCE_ELAPSED", 2, generation=1, deadline_mono_ms=2
        ),
        NarrativeCommand.shutdown("trace:3", 3, "application_exit"),
    )
    recorded = capture_reducer_trace(commands)
    assert [step.reducer_sequence for step in recorded.steps] == [1, 2, 3]
    assert recorded.final_status.runtime_state == "stopped"

    replayed = replay_reducer_trace(recorded)
    assert traces_equivalent(recorded, replayed)
    assert [step.command_id for step in replayed.steps] == ["trace:1", "trace:2", "trace:3"]
    assert replayed.final_status.reducer_sequence == recorded.final_status.reducer_sequence


def test_tape_shaped_rows_round_trip_preserves_reducer_sequence() -> None:
    commands = (
        _pure_fact("tape:a"),
        NarrativeCommand.shutdown("tape:b", 20, "application_exit"),
    )
    live = capture_reducer_trace(commands)
    rows = live.to_tape_rows()
    assert rows[0]["reducerSequence"] == 1
    assert rows[0]["commandId"] == "tape:a"
    assert rows[0]["commandKind"] == "APPLY_CONTEXT_BATCH"
    assert rows[-1]["reducerSequence"] == 2
    assert rows[-1]["disposition"] == live.steps[-1].disposition

    # Replaying the same command list must rematerialize matching tape-shaped rows.
    replayed = replay_reducer_trace(live)
    assert replayed.to_tape_rows() == rows
    assert traces_equivalent(live, replayed)




def test_capture_replay_with_runtime_factory_preserves_director_and_qwen() -> None:
    from irswitch.events.narrative_runtime import NarrativeRuntime
    from irswitch.events.story_director import StoryDirector

    def runtime_factory() -> NarrativeRuntime:
        runtime = NarrativeRuntime(story_director=StoryDirector())
        runtime.seed_director_for_test(
            world=_director_world(),
            candidates=(_director_cand(),),
        )
        return runtime

    token = {"requestId": "request:1", "requestOrdinal": 1, "dispatchGeneration": 1}
    commands = (
        _event_impulse("factory:impulse", revision=71, fanout=71),
        NarrativeCommand.realization_result(
            "factory:rz",
            "REALIZATION_SUCCEEDED",
            2000,
            request_id="request:1",
            request_ordinal=1,
            dispatch_generation=1,
            result=_result_for(token),
        ),
    )
    recorded = capture_reducer_trace(commands, runtime_factory=runtime_factory)
    assert "director_selected" in recorded.steps[0].effects
    replayed = replay_reducer_trace(recorded, runtime_factory=runtime_factory)
    assert traces_equivalent(recorded, replayed)
    assert "director_selected" in replayed.steps[0].effects
    assert replayed.steps[1].lane_after == "committed"


def test_race_does_not_wire_reducer_replay_yet() -> None:
    race = RACE_SOURCE.read_text(encoding="utf-8")
    assert "capture_reducer_trace" not in race
    assert "replay_reducer_trace" not in race
    assert "narrative_reducer_replay" not in race
