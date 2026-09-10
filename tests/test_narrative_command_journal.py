"""#284 NarrativeTape-shaped command journal → mailbox command reconstruction."""

from __future__ import annotations

import json
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
    append_command_journal_row,
    capture_reducer_trace,
    command_from_dict,
    read_commands_from_journal,
    replay_command_journal,
    traces_equivalent,
    write_command_journal,
)

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "irswitch"
    / "events"
    / "narrative_reducer_replay.py"
)
RACE_SOURCE = Path(__file__).resolve().parents[1] / "src" / "irswitch" / "race" / "runtime.py"


def test_command_journal_helpers_not_exported() -> None:
    assert "write_command_journal" not in events_exports
    assert "read_commands_from_journal" not in events_exports
    assert "replay_command_journal" not in events_exports
    assert "command_from_dict" not in events_exports
    text = SOURCE.read_text(encoding="utf-8")
    assert "write_command_journal" in text
    assert "read_commands_from_journal" in text
    assert "replay_command_journal" in text


def test_command_from_dict_round_trips_supported_kinds() -> None:
    pure = _pure_fact("journal:pure")
    deadline = NarrativeCommand.deadline(
        "journal:deadline",
        "LONG_SILENCE_ELAPSED",
        2,
        generation=1,
        deadline_mono_ms=2,
    )
    token = {"requestId": "request:9", "requestOrdinal": 2, "dispatchGeneration": 3}
    realization = NarrativeCommand.realization_result(
        "journal:rz",
        "REALIZATION_SUCCEEDED",
        4,
        request_id="request:9",
        request_ordinal=2,
        dispatch_generation=3,
        result=_result_for(token),
    )
    shutdown = NarrativeCommand.shutdown("journal:stop", 3, "application_exit")

    for original in (pure, deadline, realization, shutdown):
        rebuilt = command_from_dict(original.to_dict())
        assert rebuilt.kind == original.kind
        assert rebuilt.command_id == original.command_id
        assert rebuilt.to_dict()["payload"] == original.to_dict()["payload"]
        assert rebuilt.to_dict()["token"] == original.to_dict()["token"]


def test_journal_file_replay_matches_live_reducer_trace(tmp_path: Path) -> None:
    commands = (
        _pure_fact("file:1"),
        NarrativeCommand.deadline(
            "file:2", "LONG_SILENCE_ELAPSED", 2, generation=1, deadline_mono_ms=2
        ),
        NarrativeCommand.shutdown("file:3", 3, "application_exit"),
    )
    live = capture_reducer_trace(commands)
    path = tmp_path / "commands.ndjson"
    write_command_journal(path, live)

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert [row["reducerSequence"] for row in rows] == [1, 2, 3]
    assert all(row["schemaVersion"] == "narrative-command-journal/1" for row in rows)
    assert rows[0]["command"]["kind"] == "APPLY_CONTEXT_BATCH"

    loaded = read_commands_from_journal(path)
    assert [command.command_id for command in loaded] == ["file:1", "file:2", "file:3"]

    from_file = replay_command_journal(path)
    assert traces_equivalent(live, from_file)
    assert [step.reducer_sequence for step in from_file.steps] == [1, 2, 3]
    assert from_file.final_status.runtime_state == "stopped"


def test_journal_read_orders_by_reducer_sequence_not_file_order(tmp_path: Path) -> None:
    commands = (
        _pure_fact("order:a"),
        NarrativeCommand.shutdown("order:b", 20, "application_exit"),
    )
    live = capture_reducer_trace(commands)
    path = tmp_path / "shuffled.ndjson"
    write_command_journal(path, live)

    # Reverse file bytes so wall/file order disagrees with reducerSequence.
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    path.write_text(
        "\n".join(json.dumps(row, separators=(",", ":")) for row in reversed(rows)) + "\n",
        encoding="utf-8",
    )

    loaded = read_commands_from_journal(path)
    assert [command.command_id for command in loaded] == ["order:a", "order:b"]
    replayed = replay_command_journal(path)
    assert traces_equivalent(live, replayed)


def test_status_fingerprint_ignores_loop_mono_clock_drift() -> None:
    """Replay equivalence must not depend on wall/monotonic reduce timestamps."""
    from dataclasses import replace

    from irswitch.events.narrative_reducer_replay import ReducerTrace, _status_fingerprint

    commands = (
        _pure_fact("mono:1"),
        NarrativeCommand.shutdown("mono:2", 20, "application_exit"),
    )
    live = capture_reducer_trace(commands)
    base = int(live.final_status.loop_last_reduce_mono_ms or 0)
    drifted_status = replace(live.final_status, loop_last_reduce_mono_ms=base + 7)
    assert live.final_status.loop_last_reduce_mono_ms != drifted_status.loop_last_reduce_mono_ms
    assert _status_fingerprint(live.final_status) == _status_fingerprint(drifted_status)
    drifted_trace = ReducerTrace(
        commands=live.commands,
        steps=live.steps,
        final_status=drifted_status,
    )
    assert traces_equivalent(live, drifted_trace)


def test_append_command_journal_row_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "live.ndjson"
    first = _pure_fact("append:1")
    second = NarrativeCommand.shutdown("append:2", 9, "application_exit")
    append_command_journal_row(path, reducer_sequence=1, command=first)
    append_command_journal_row(path, reducer_sequence=2, command=second)
    loaded = read_commands_from_journal(path)
    assert [command.command_id for command in loaded] == ["append:1", "append:2"]


def test_narrative_runtime_appends_command_journal_on_reduce(tmp_path: Path) -> None:
    from irswitch.events.narrative_runtime import NarrativeRuntime

    path = tmp_path / "runtime.ndjson"
    runtime = NarrativeRuntime(command_journal_path=path)
    runtime.enable()
    runtime.admit(_pure_fact("live:1"))
    runtime.admit(NarrativeCommand.shutdown("live:2", 11, "application_exit"))
    assert runtime.reduce_next() is not None
    assert runtime.reduce_next() is not None
    loaded = read_commands_from_journal(path)
    assert [command.command_id for command in loaded] == ["live:1", "live:2"]
    assert traces_equivalent(capture_reducer_trace(loaded), replay_command_journal(path))




def test_journal_replay_reproduces_director_decisions_with_recorded_qwen(tmp_path: Path) -> None:
    """#284 replay closure: director_selected + recorded realization via journal."""
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
        _event_impulse("closure:impulse", revision=71, fanout=71),
        NarrativeCommand.realization_result(
            "closure:rz",
            "REALIZATION_SUCCEEDED",
            2000,
            request_id="request:1",
            request_ordinal=1,
            dispatch_generation=1,
            result=_result_for(token),
        ),
    )
    live = capture_reducer_trace(commands, runtime_factory=runtime_factory)
    assert "director_selected" in live.steps[0].effects
    assert live.steps[1].lane_after == "committed"

    path = tmp_path / "director-qwen.ndjson"
    write_command_journal(path, live)
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert rows[1]["command"]["kind"] == "REALIZATION_SUCCEEDED"

    from_file = replay_command_journal(path, runtime_factory=runtime_factory)
    assert traces_equivalent(live, from_file)
    assert "director_selected" in from_file.steps[0].effects
    assert from_file.steps[1].lane_after == "committed"


def test_race_wires_command_journal_path() -> None:
    race = RACE_SOURCE.read_text(encoding="utf-8")
    assert "command_journal_path=" in race
    assert "narrative-command-journal.ndjson" in race
    # Full write/read/replay helpers stay library-side; race only passes the path.
    assert "write_command_journal" not in race
    assert "read_commands_from_journal" not in race
    assert "replay_command_journal" not in race
