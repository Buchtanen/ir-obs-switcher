"""#284 NarrativeTapeBridge + race tape_effect wiring."""

from __future__ import annotations

from pathlib import Path

import pytest

from irswitch.contracts.command import NarrativeCommand
from irswitch.events import __all__ as events_exports
from irswitch.events.narrative_runtime import NarrativeRuntime
from irswitch.events.narrative_tape_bridge import (
    build_tape_flush_effect,
    default_narrative_tape_manifest,
    open_narrative_tape_writer,
)

RACE_SRC = Path(__file__).resolve().parents[1] / "src" / "irswitch" / "race" / "runtime.py"
BRIDGE_SRC = (
    Path(__file__).resolve().parents[1] / "src" / "irswitch" / "events" / "narrative_tape_bridge.py"
)


def test_tape_bridge_helpers_not_exported() -> None:
    assert "build_tape_flush_effect" not in events_exports
    assert "open_narrative_tape_writer" not in events_exports
    assert "default_narrative_tape_manifest" not in events_exports
    text = BRIDGE_SRC.read_text(encoding="utf-8")
    assert "def build_tape_flush_effect" in text
    assert "def open_narrative_tape_writer" in text


def test_race_wires_tape_effect_when_writer_opens() -> None:
    """Race cutover creates NarrativeTapeWriter and passes tape_effect into NarrativeRuntime."""
    race = RACE_SRC.read_text(encoding="utf-8")
    assert "open_narrative_tape_writer" in race
    assert "build_tape_flush_effect" in race
    assert "tape_effect=tape_effect" in race
    assert "_request_narrative_shutdown" in race
    block_start = race.index("runtime = NarrativeRuntime(")
    depth = 0
    block_end = None
    for index, char in enumerate(race[block_start:], start=block_start):
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                block_end = index + 1
                break
    assert block_end is not None
    block = race[block_start:block_end]
    assert "tape_effect=tape_effect" in block
    assert "semantic_verifier=SemanticVerifier()" in block


@pytest.mark.asyncio
async def test_open_writer_flush_effect_closes_on_shutdown(tmp_path: Path) -> None:
    writer = open_narrative_tape_writer(tmp_path, app_version="9.9.9")
    assert default_narrative_tape_manifest()["recordType"] == "manifest"
    writer.start()
    runtime = NarrativeRuntime(
        tape_effect=build_tape_flush_effect(writer),
        shutdown_flush_timeout_s=1.0,
    )
    runtime.enable()
    runtime.admit(NarrativeCommand.shutdown("tape:sd", 1000, "application_exit"))
    result = runtime.reduce_next()
    assert result is not None
    assert "effect:flush_tape" in result.effects
    await runtime.apply_effects(result.effects)
    await runtime.wait_effects_idle()
    assert not runtime.tape_task_active()
    files = list(tmp_path.glob("narrative-*.ndjson"))
    assert len(files) == 1
