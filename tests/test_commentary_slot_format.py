"""Spoken timing formatters for commentary slots (M1)."""

from __future__ import annotations

import random

from irswitch.commentary.director import CommentaryDirector, choose_filled_line, slot_bindings
from irswitch.commentary.graph import parse_sequence_graph
from irswitch.commentary.slot_format import (
    format_spoken_bindings,
    speak_delta,
    speak_gap,
    speak_lap_time,
)
from irswitch.commentary.tts import NullTtsSink
from irswitch.events.envelope import make_envelope
from irswitch.overlay.settings import CommentarySettings


def test_speak_lap_time_matches_sdk_units() -> None:
    assert speak_lap_time(112.084) == "1:52.084"
    assert speak_lap_time(45.1) == "0:45.100"
    assert speak_lap_time(59.9996) == "1:00.000"


def test_speak_lap_time_sentinel_is_none() -> None:
    assert speak_lap_time(-1) is None
    assert speak_lap_time(-1.0) is None
    assert speak_lap_time(0) is None
    assert speak_lap_time(None) is None
    assert speak_lap_time("") is None


def test_speak_delta_signed() -> None:
    assert speak_delta(-0.318) == "-0.318"
    assert speak_delta(0.318) == "+0.318"
    assert speak_delta(0) == "+0.000"
    assert speak_delta(None) is None
    assert speak_delta("") is None


def test_speak_gap_with_unit() -> None:
    assert speak_gap(1.91) == "1.91 s"
    assert speak_gap(1.2) == "1.20 s"
    assert speak_gap(-1) is None
    assert speak_gap(-1.0) is None
    assert speak_gap(None) is None


def test_format_spoken_bindings_formats_known_slots() -> None:
    out = format_spoken_bindings(
        {
            "lap_time": 112.084,
            "delta": -0.4,
            "gap": 1.91,
            "segment_time": 28.5,
            "position": 5,
        }
    )
    assert out["lap_time"] == "1:52.084"
    assert out["delta"] == "-0.400"
    assert out["gap"] == "1.91 s"
    assert out["segment_time"] == "0:28.500"
    assert out["position"] == 5


def test_format_spoken_bindings_sentinel_clears_slot() -> None:
    out = format_spoken_bindings({"lap_time": -1.0, "gap": -1, "delta": None})
    assert out["lap_time"] is None
    assert out["gap"] is None
    assert out["delta"] is None


def test_choose_filled_line_skips_when_timing_slot_sentinel() -> None:
    texts = (
        "Lap done in {lap_time}.",
        "Closing, gap {gap}.",
        "Plain line with no slots.",
    )
    # lap_time / gap unbound after format → only plain line remains
    bindings = format_spoken_bindings({"lap_time": -1.0, "gap": -1.0})
    spoken = choose_filled_line(texts, bindings, random.Random(0))
    assert spoken == "Plain line with no slots."


def test_choose_filled_line_never_speaks_raw_sentinel() -> None:
    texts = ("Gap is {gap}.", "Lap {lap_time}.")
    bindings = format_spoken_bindings({"gap": -1.0, "lap_time": -1.0})
    assert choose_filled_line(texts, bindings, random.Random(0)) is None


def test_slot_bindings_format_lap_and_gap() -> None:
    env = make_envelope(
        event_type="LAP_COMPLETE",
        phase="RESULT",
        priority=40,
        metrics={"lap": 12, "lapTime": 112.084, "gap": 1.91, "deltaToBest": -0.318},
    )
    bound = slot_bindings(env, "unknown")
    assert bound["lap"] == 12
    assert bound["lap_time"] == "1:52.084"
    assert bound["gap"] == "1.91 s"
    assert bound["delta"] == "-0.318"


def test_director_skips_sentinel_gap_without_raw_speech() -> None:
    graph = parse_sequence_graph(
        {
            "version": 1,
            "locales": ["en"],
            "nodes": {
                "hunting": {
                    "family": "battle",
                    "event_types": ["HUNTING"],
                    "phases": ["ENTER"],
                    "speak_priority": 50,
                    "cooldown_s": 1,
                    "slots": [{"name": "gap", "type": "gap", "example": "1.0"}],
                    "hr_states": ["unknown"],
                    "variants": {
                        "en": {"neutral": ["Closing to {gap}."]},
                    },
                }
            },
            "edges": [],
        }
    )
    sink = NullTtsSink()
    director = CommentaryDirector(
        graph=graph,
        settings=CommentarySettings(enabled=True, cooldown_s=0.5, use_hr_emotion=False),
        sink=sink,
    )
    env = make_envelope(
        event_type="HUNTING",
        phase="ENTER",
        priority=55,
        metrics={"gap": -1.0},
    )
    assert director.observe([env], None, 10.0) is None
    assert sink.spoken == []
    assert director.decisions(1)[-1]["reason"] == "slot_unbound"


def test_director_speaks_formatted_lap_time_not_raw_seconds() -> None:
    graph = parse_sequence_graph(
        {
            "version": 1,
            "locales": ["en"],
            "nodes": {
                "lap_complete": {
                    "family": "timing",
                    "event_types": ["LAP_COMPLETE"],
                    "phases": ["RESULT"],
                    "speak_priority": 40,
                    "cooldown_s": 1,
                    "slots": [
                        {"name": "lap", "type": "int", "example": 7},
                        {"name": "lap_time", "type": "time", "example": "1:28.100"},
                    ],
                    "hr_states": ["unknown"],
                    "variants": {
                        "en": {"neutral": ["Lap {lap} done in {lap_time}."]},
                    },
                }
            },
            "edges": [],
        }
    )
    sink = NullTtsSink()
    director = CommentaryDirector(
        graph=graph,
        settings=CommentarySettings(enabled=True, cooldown_s=0.5, use_hr_emotion=False),
        sink=sink,
    )
    env = make_envelope(
        event_type="LAP_COMPLETE",
        phase="RESULT",
        priority=40,
        metrics={"lap": 7, "lapTime": 112.084},
    )
    spoken = director.observe([env], None, 10.0)
    assert spoken is not None
    assert spoken.text == "Lap 7 done in 1:52.084."
    assert "112.084" not in spoken.text
    assert "-1" not in spoken.text
