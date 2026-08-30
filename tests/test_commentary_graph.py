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


def test_default_graph_loads_fully_filled() -> None:
    graph = load_sequence_graph()
    assert graph.version == 1
    assert "overtake" in graph.nodes
    assert graph.nodes["overtake"].event_types == ("OVERTAKE",)
    assert graph.unfilled_cells() == []
    assert graph.nodes["overtake"].variant_bucket("en", "neutral")
    assert graph.nodes["overtake"].variant_bucket("cs", "neutral")


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
