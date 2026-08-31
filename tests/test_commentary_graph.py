"""Sequence graph load + catalog alignment."""

from __future__ import annotations

import pytest

from irswitch.commentary.graph import (
    COMMENTARY_ONLY_EVENTS,
    load_sequence_graph,
    parse_sequence_graph,
    validate_graph_document,
)
from irswitch.events.event_catalog import catalog_entries, catalog_fallbacks


def test_default_graph_loads_and_is_fully_filled() -> None:
    graph = load_sequence_graph()
    assert graph.version == 1
    assert "overtake" in graph.nodes
    assert graph.nodes["overtake"].event_types == ("OVERTAKE",)
    assert graph.unfilled_cells() == []
    assert graph.nodes["overtake"].variant_bucket("en", "neutral")
    assert graph.nodes["overtake"].variant_bucket("cs", "neutral")
    # Dense content from commentary-extension-texts (#130 M0) + W4/H4 session briefs
    # + observer fillers + session_checkered + N11 wave A (stream_start + mode in_car).
    assert len(graph.nodes) == 45
    assert "sector_split" in graph.nodes
    assert graph.nodes["sector_split"].event_types == ("SECTOR_SPLIT", "SECTOR_BEST")
    assert "session_intro_race" in graph.nodes
    assert "session_checkered" in graph.nodes
    assert "stream_start" in graph.nodes
    assert graph.nodes["stream_start"].event_types == ("STREAM_START",)
    assert graph.nodes["stream_start"].tts.max_seconds >= 15.0
    assert graph.nodes["in_car_race"].modes == ("race",)
    assert len(graph.edges) == 20


def test_finish_ambiguous_lines_include_position() -> None:
    graph = load_sequence_graph()
    node = graph.nodes["finish"]
    needles = (
        "whole stint",
        "earlier sequence",
        "celým stintem",
        "předchozí sekvence",
    )
    for locale, buckets in node.variants.items():
        for emotion, lines in buckets.items():
            for line in lines:
                lowered = line.lower()
                if any(needle in lowered for needle in needles):
                    assert "{position}" in line, f"{locale}/{emotion}: {line}"


def test_graph_event_types_are_in_catalog() -> None:
    graph = load_sequence_graph()
    known = set(catalog_entries()) | set(catalog_fallbacks()) | COMMENTARY_ONLY_EVENTS
    for node in graph.nodes.values():
        for event_type in node.event_types:
            assert event_type in known, event_type
    assert "STREAM_START" in COMMENTARY_ONLY_EVENTS
    assert "SESSION_FLAG" in COMMENTARY_ONLY_EVENTS
    assert "BACK_UNDER_WAY" in COMMENTARY_ONLY_EVENTS
    assert "INCIDENT_RECOVERED" not in COMMENTARY_ONLY_EVENTS


def test_nodes_for_ranks_by_speak_priority() -> None:
    graph = load_sequence_graph()
    nodes = graph.nodes_for("OVERTAKE", "RESULT")
    assert nodes
    assert nodes[0].id == "overtake"


def _incident_graph() -> object:
    return parse_sequence_graph(
        {
            "version": 1,
            "locales": ["en"],
            "nodes": {
                "incident_generic": {
                    "family": "exception",
                    "event_types": ["INCIDENT"],
                    "phases": ["RESULT"],
                    "speak_priority": 90,
                    "hr_states": ["unknown"],
                    "variants": {"en": {"neutral": ["Contact."]}},
                },
                "incident_off_track": {
                    "family": "exception",
                    "event_types": ["INCIDENT"],
                    "phases": ["RESULT"],
                    "speak_priority": 40,
                    "branch": "off_track",
                    "hr_states": ["unknown"],
                    "variants": {"en": {"neutral": ["Off track."]}},
                },
                "in_car_race": {
                    "family": "session",
                    "event_types": ["ENTER_CAR"],
                    "phases": ["ENTER"],
                    "speak_priority": 20,
                    "modes": ["race"],
                    "hr_states": ["unknown"],
                    "variants": {"en": {"neutral": ["Race car."]}},
                },
                "in_car_any": {
                    "family": "session",
                    "event_types": ["ENTER_CAR"],
                    "phases": ["ENTER"],
                    "speak_priority": 10,
                    "hr_states": ["unknown"],
                    "variants": {"en": {"neutral": ["In the car."]}},
                },
            },
            "edges": [],
        }
    )


def test_branch_match_beats_higher_generic_priority() -> None:
    graph = _incident_graph()
    nodes = graph.nodes_for("INCIDENT", "RESULT", branch="off_track")
    assert [node.id for node in nodes] == ["incident_off_track"]
    fallback = graph.nodes_for("INCIDENT", "RESULT", branch="unknown")
    assert fallback[0].id == "incident_generic"


def test_mode_filter_prefers_matching_then_unrestricted() -> None:
    graph = _incident_graph()
    race = graph.nodes_for("ENTER_CAR", "ENTER", mode="RACE")
    assert race[0].id == "in_car_race"
    practice = graph.nodes_for("ENTER_CAR", "ENTER", mode="PRACTICE")
    assert [node.id for node in practice] == ["in_car_any"]


def test_live_graph_picks_mode_in_car_then_generic() -> None:
    graph = load_sequence_graph()
    race = graph.nodes_for("ENTER_CAR", "RESULT", mode="RACE")
    assert race[0].id == "in_car_race"
    practice = graph.nodes_for("ENTER_CAR", "RESULT", mode="PRACTICE")
    assert practice[0].id == "in_car_practice"
    qualify = graph.nodes_for("ENTER_CAR", "RESULT", mode="QUALIFYING")
    assert qualify[0].id == "in_car_qualify"
    warmup = graph.nodes_for("ENTER_CAR", "RESULT", mode="GENERIC")
    assert warmup[0].id == "in_car"
    stream = graph.nodes_for("STREAM_START", "ENTER")
    assert stream[0].id == "stream_start"


def test_stream_start_and_session_flag_graphs_load() -> None:
    raw = {
        "version": 1,
        "locales": ["en"],
        "nodes": {
            "stream_start": {
                "family": "session",
                "event_types": ["STREAM_START"],
                "phases": ["ENTER"],
                "speak_priority": 1,
                "hr_states": ["unknown"],
            },
            "session_flag": {
                "family": "session",
                "event_types": ["SESSION_FLAG"],
                "phases": ["ENTER"],
                "speak_priority": 1,
                "hr_states": ["unknown"],
            },
        },
        "edges": [],
    }
    graph = parse_sequence_graph(raw)
    assert "stream_start" in graph.nodes
    assert "session_flag" in graph.nodes


def test_unknown_event_type_is_rejected() -> None:
    raw = {
        "version": 1,
        "locales": ["en"],
        "nodes": {
            "bogus": {
                "family": "timing",
                "event_types": ["NOT_A_REAL_EVENT"],
                "phases": ["RESULT"],
                "speak_priority": 1,
                "hr_states": ["unknown"],
            }
        },
        "edges": [],
    }
    errors = validate_graph_document(raw)
    assert any("NOT_A_REAL_EVENT" in item for item in errors)
    with pytest.raises(ValueError, match="invalid sequence graph"):
        parse_sequence_graph(raw)
