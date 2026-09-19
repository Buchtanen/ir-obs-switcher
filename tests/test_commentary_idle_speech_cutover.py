"""#284 CommentaryConsumer idle-lane speech cutover."""

from __future__ import annotations

import time
from pathlib import Path
from unittest.mock import MagicMock

from irswitch.commentary.consumer import CommentaryConsumer
from irswitch.commentary.director import CommentaryDirector
from irswitch.commentary.graph import parse_sequence_graph
from irswitch.commentary.tts import NullTtsSink
from irswitch.events.async_fanout import AsyncEventFanout
from irswitch.events.stream import CONTEXT_SCHEMA_VERSION, freeze_context
from irswitch.overlay.settings import CommentarySettings

RACE_SOURCE = Path(__file__).resolve().parents[1] / "src" / "irswitch" / "race" / "runtime.py"
CONSUMER_SOURCE = (
    Path(__file__).resolve().parents[1] / "src" / "irswitch" / "commentary" / "consumer.py"
)


def _graph():
    return parse_sequence_graph(
        {
            "version": 1,
            "locales": ["en"],
            "nodes": {
                "lap": {
                    "family": "lap",
                    "event_types": ["LAP_COMPLETE"],
                    "phases": ["RESULT"],
                    "speak_priority": 50,
                    "cooldown_s": 0,
                    "slots": [],
                    "hr_states": ["unknown"],
                    "variants": {"en": {"neutral": ["A lap is complete."]}},
                }
            },
            "edges": [],
        }
    )


def _context_payload() -> bytes:
    return freeze_context(
        {
            "schema_version": CONTEXT_SCHEMA_VERSION,
            "version": 1,
            "session_id": "session",
            "captured_monotonic_ms": int(time.monotonic() * 1000),
            "identity": {},
            "race": {"class_position": 4},
            "bio": {"status": "connected", "connected": True, "hr_state": "focused"},
            "story": {"hero": {"speakable_names": ["Alex"]}},
            "situation": {},
            "config": {},
        }
    )


def test_idle_speech_disabled_skips_director_tick() -> None:
    settings = CommentarySettings(enabled=True, cooldown_s=0)
    director = CommentaryDirector(graph=_graph(), settings=settings, sink=NullTtsSink())
    director.tick = MagicMock(return_value=None)  # type: ignore[method-assign]
    consumer = CommentaryConsumer(
        AsyncEventFanout().subscribe("commentary"),
        director,
        lambda: (settings, "en"),
        idle_speech_enabled=False,
    )
    consumer._mirrored_latest_context = _context_payload()
    consumer._idle_tick()
    director.tick.assert_not_called()


def test_idle_speech_enabled_still_ticks_director() -> None:
    settings = CommentarySettings(enabled=True, cooldown_s=0)
    director = CommentaryDirector(graph=_graph(), settings=settings, sink=NullTtsSink())
    director.tick = MagicMock(return_value=None)  # type: ignore[method-assign]
    consumer = CommentaryConsumer(
        None,
        director,
        lambda: (settings, "en"),
        idle_speech_enabled=True,
    )
    consumer._mirrored_latest_context = _context_payload()
    consumer._idle_tick()
    director.tick.assert_called()


def test_run_loop_guards_idle_tick_on_flag() -> None:
    source = CONSUMER_SOURCE.read_text(encoding="utf-8")
    assert "idle_speech_enabled" in source
    assert "if self.idle_speech_enabled" in source


def test_race_disables_idle_speech_under_narrative_cutover() -> None:
    race = RACE_SOURCE.read_text(encoding="utf-8")
    assert "idle_speech_enabled=False" in race or "idle_speech_enabled = False" in race
