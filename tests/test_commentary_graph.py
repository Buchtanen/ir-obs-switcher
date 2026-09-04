"""Sequence graph load + catalog alignment."""

from __future__ import annotations

import pytest

from irswitch.commentary.graph import (
    COMMENTARY_ONLY_EVENTS,
    GRAPH_VERSION,
    Criticality,
    EditorialPolicy,
    SemanticPolicy,
    load_sequence_graph,
    parse_sequence_graph,
    validate_graph_document,
)
from irswitch.events.event_catalog import catalog_entries, catalog_fallbacks


def test_default_graph_loads_and_is_fully_filled() -> None:
    graph = load_sequence_graph()
    assert graph.version == GRAPH_VERSION
    assert "overtake" in graph.nodes
    assert graph.nodes["overtake"].event_types == ("OVERTAKE",)
    assert graph.unfilled_cells() == []
    assert graph.nodes["overtake"].variant_bucket("en", "neutral")
    assert graph.nodes["overtake"].variant_bucket("cs", "neutral")
    assert graph.nodes_for("BATTLE_FOR_POSITION", "ENTER")[0].id == "two_front_battle"
    # Dense content from commentary-extension-texts (#130 M0) + W4/H4 session briefs
    # + observer fillers + session_checkered + N11 A + sparse B/C/D.
    assert {
        "track_excursion",
        "track_rejoined",
        "motion_restored",
        "tow_started_race",
    } <= graph.nodes.keys()
    assert "leader_change" in graph.nodes
    assert graph.nodes["leader_change"].event_types == ("LEADER_CHANGE",)
    assert graph.nodes["leader_change"].speak_priority == 75
    assert "sector_split" in graph.nodes
    assert graph.nodes["sector_split"].event_types == ("SECTOR_SPLIT", "SECTOR_BEST")
    assert "session_intro_race" in graph.nodes
    assert "session_checkered" in graph.nodes
    assert "stream_start" in graph.nodes
    assert graph.nodes["stream_start"].event_types == ("STREAM_START",)
    assert graph.nodes["stream_start"].tts.max_seconds >= 15.0
    assert graph.nodes["in_car_race"].modes == ("race",)
    assert graph.outgoing("track_excursion")
    assert all(node.editorial.policy for node in graph.nodes.values())
    assert all(edge.editorial.transition_bonus >= 0 for edge in graph.edges)
    assert graph.nodes["hunting"].editorial.policy is EditorialPolicy.LIVE_RELATION
    assert graph.nodes["hunting"].editorial.semantic_policy is SemanticPolicy.BATTLE_RELATION
    assert graph.nodes["finish"].editorial.criticality is Criticality.CRITICAL
    assert next(
        edge for edge in graph.edges if edge.source == "side_by_side" and edge.target == "overtake"
    ).editorial.closure


def test_default_graph_critical_inventory_is_explicit() -> None:
    graph = load_sequence_graph()
    critical = {
        node.id: node.event_types
        for node in graph.nodes.values()
        if node.editorial.criticality is Criticality.CRITICAL
    }

    assert critical == {
        "position_gained": ("POSITION_GAINED",),
        "position_lost": ("POSITION_LOST", "OVERTAKEN"),
        "final_lap": ("FINAL_LAP",),
        "finish": ("FINISH",),
        "leader_change": ("LEADER_CHANGE",),
        "session_checkered": ("SESSION_CHECKERED",),
        "session_flag_checkered": ("SESSION_FLAG",),
    }


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
    assert "PACE_HUNT" in COMMENTARY_ONLY_EVENTS
    assert "SESSION_FLAG" in COMMENTARY_ONLY_EVENTS
    assert "QUALI_RECAP" in COMMENTARY_ONLY_EVENTS
    assert "PARADE_PAD" in COMMENTARY_ONLY_EVENTS
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
    off = graph.nodes_for("INCIDENT", "RESULT", branch="off_track")
    assert off[0].id == "incident_off_track"
    unknown = graph.nodes_for("INCIDENT", "RESULT", branch="unknown")
    assert unknown[0].id == "incident_unknown"
    generic = graph.nodes_for("INCIDENT", "RESULT")
    assert generic[0].id == "incident"
    yellow = graph.nodes_for("SESSION_FLAG", "RESULT", branch="yellow")
    assert yellow[0].id == "session_flag_yellow"
    recap = graph.nodes_for("QUALI_RECAP", "RESULT")
    assert recap[0].id == "quali_recap"
    pad = graph.nodes_for("PARADE_PAD", "RESULT")
    assert pad[0].id == "parade_pad"


def test_current_offtrack_root_reaches_closure_without_intermediate_speech() -> None:
    graph = load_sequence_graph()
    targets = {edge.target for edge in graph.outgoing("track_excursion")}
    assert {
        "track_rejoined",
        "motion_restored",
        "tow_started_race",
        "pit_return_observed",
    } <= targets
    assert all(
        edge.identity.value == "same_parent_story" for edge in graph.outgoing("track_excursion")
    )


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


def test_unknown_style_card_is_rejected() -> None:
    raw = {
        "version": 1,
        "locales": ["en"],
        "nodes": {
            "lap": {
                "family": "lap",
                "event_types": ["LAP_COMPLETE"],
                "phases": ["RESULT"],
                "speak_priority": 1,
                "hr_states": ["unknown"],
                "style_cards": ["not-a-card"],
            }
        },
        "edges": [],
    }
    assert any("style_cards" in item for item in validate_graph_document(raw))


def test_v2_requires_typed_editorial_node_metadata() -> None:
    raw = {
        "version": 2,
        "locales": ["en"],
        "nodes": {
            "lap": {
                "family": "timing",
                "event_types": ["LAP_COMPLETE"],
                "phases": ["RESULT"],
                "speak_priority": 1,
                "hr_states": ["unknown"],
            }
        },
        "edges": [],
    }
    errors = validate_graph_document(raw)
    assert any("nodes.lap.editorial is required" in item for item in errors)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("policy", "invented"),
        ("semantic_policy", "invented"),
        ("criticality", "urgent-ish"),
        ("repeat_weight", 2.1),
        ("silence_affinity", -0.1),
        ("material_change_policy", "invented"),
    ],
)
def test_v2_rejects_invalid_editorial_node_metadata(field: str, value: object) -> None:
    editorial = {
        "policy": "periodic_context",
        "semantic_policy": "lap_result",
        "criticality": "context",
        "repeat_weight": 1.0,
        "silence_affinity": 0.5,
        "material_change_policy": "lap_result",
    }
    editorial[field] = value
    raw = {
        "version": 2,
        "locales": ["en"],
        "nodes": {
            "lap": {
                "family": "timing",
                "event_types": ["LAP_COMPLETE"],
                "phases": ["RESULT"],
                "speak_priority": 1,
                "hr_states": ["unknown"],
                "editorial": editorial,
            }
        },
        "edges": [],
    }
    assert any(f"editorial.{field}" in item for item in validate_graph_document(raw))


def test_v2_rejects_invalid_editorial_edge_metadata() -> None:
    node = {
        "family": "timing",
        "event_types": ["LAP_COMPLETE"],
        "phases": ["RESULT"],
        "speak_priority": 1,
        "hr_states": ["unknown"],
        "editorial": {
            "policy": "periodic_context",
            "semantic_policy": "lap_result",
            "criticality": "context",
            "repeat_weight": 1.0,
            "silence_affinity": 0.5,
            "material_change_policy": "lap_result",
        },
    }
    raw = {
        "version": 2,
        "locales": ["en"],
        "nodes": {"a": node, "b": node},
        "edges": [
            {
                "from": "a",
                "to": "b",
                "editorial": {
                    "transition_bonus": 21,
                    "closure": "yes",
                    "repeat_weight": -1,
                },
            }
        ],
    }
    errors = validate_graph_document(raw)
    assert any("transition_bonus" in item for item in errors)
    assert any("closure" in item for item in errors)
    assert any("repeat_weight" in item for item in errors)
