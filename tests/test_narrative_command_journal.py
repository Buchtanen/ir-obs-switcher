"""#284 NarrativeTape-shaped command journal → mailbox command reconstruction."""

from __future__ import annotations

import json
from pathlib import Path

from test_narrative_runtime import _pure_fact

from irswitch.contracts.command import NarrativeCommand
from irswitch.events import __all__ as events_exports
from irswitch.events.narrative_reducer_replay import (
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
    shutdown = NarrativeCommand.shutdown("journal:stop", 3, "application_exit")

    for original in (pure, deadline, shutdown):
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


def test_race_does_not_wire_command_journal_yet() -> None:
    race = RACE_SOURCE.read_text(encoding="utf-8")
    assert "write_command_journal" not in race
    assert "read_commands_from_journal" not in race
    assert "replay_command_journal" not in race
