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
    # + session_checkered out-lap node.
    assert len(graph.nodes) == 41
    assert "sector_split" in graph.nodes
    assert graph.nodes["sector_split"].event_types == ("SECTOR_SPLIT", "SECTOR_BEST")
    assert "session_intro_race" in graph.nodes
    assert "session_checkered" in graph.nodes
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


def test_nodes_for_ranks_by_speak_priority() -> None:
    graph = load_sequence_graph()
    nodes = graph.nodes_for("OVERTAKE", "RESULT")
    assert nodes
    assert nodes[0].id == "overtake"


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
