"""Prepared-commentary graph is the complete semantic source of truth."""

from __future__ import annotations

from irswitch.commentary.graph import (
    GRAPH_VERSION,
    PreparedRelation,
    load_sequence_graph,
    parse_sequence_graph,
    validate_graph_document,
)

CORE_PREPARED_NODE_IDS = {
    "stream_intro_venue",
    "stream_intro_circuit_character",
    "stream_intro_conditions",
    "stream_intro_surface_state",
    "stream_intro_field_overall",
    "stream_intro_field_class",
    "stream_intro_ai_field",
    "practice_quiet_track",
    "event_intro_practice",
    "event_intro_qualifying",
    "event_intro_race",
    "hero_prepares_to_drive",
    "engine_started",
    "rollout_started",
    "out_lap_preparation",
    "out_lap_field_context",
    "returned_to_car",
    "race_quali_recap_result",
    "race_grid_field",
    "race_grid_highest_rated",
    "rolling_start_setup",
    "formation_lap_preparation",
    "formation_lap_tension",
    "standing_start_setup",
    "start_lights_ready",
    "start_lights_set",
    "practice_checkered_summary",
    "practice_value_debrief",
    "practice_lobby_break",
    "quali_result_pole",
    "quali_result_podium",
    "quali_result_top_third",
    "quali_result_middle_third",
    "quali_result_rear_third",
    "quali_result_classified",
    "quali_result_unclassified",
    "quali_to_race_bridge",
    "race_result_win",
    "race_result_podium",
    "race_result_gain_vs_quali",
    "race_result_hold_vs_quali",
    "race_result_loss_vs_quali",
    "race_result_gain_vs_grid",
    "race_result_hold_vs_grid",
    "race_result_loss_vs_grid",
    "race_result_top_third",
    "race_result_middle_third",
    "race_result_rear_third",
    "race_result_classified",
    "race_result_unclassified",
    "result_unconfirmed",
    "stream_chapter_bridge",
    "prepared_filler_fatal_notice",
}


def _prepared_node() -> dict[str, object]:
    return {
        "family": "session",
        "event_types": ["PREPARED_FILLER"],
        "phases": ["RESULT"],
        "modes": ["race"],
        "speak_priority": 30,
        "cooldown_s": 0,
        "slots": [],
        "hr_states": ["unknown"],
        "variants": {},
        "editorial": {
            "policy": "periodic_context",
            "semantic_policy": "context_fact",
            "criticality": "context",
            "repeat_weight": 1.0,
            "silence_affinity": 1.0,
            "material_change_policy": "context_value",
        },
        "prepared": {
            "allowed_stages": ["SESSION_CONCLUSION"],
            "tier": 0,
            "terminal": True,
            "required_facts": ["finish_position", "qualifying_position"],
            "optional_facts": ["track"],
            "relation": "finish_better_than_qualifying",
            "intent": {
                "en": "Confirmed finish improved on qualifying.",
                "cs": "Potvrzený výsledek je lepší než kvalifikace.",
            },
            "forbidden_claims": ["cause", "prediction", "blame"],
            "anchors": {
                "en": ["He gained places from qualifying to the confirmed finish."],
                "cs": ["Proti kvalifikaci si v potvrzeném výsledku polepšil."],
            },
        },
    }


def _document(node: dict[str, object]) -> dict[str, object]:
    return {
        "version": 4,
        "locales": ["en", "cs"],
        "default_tts": {"max_chars": 160, "max_seconds": 13.0},
        "nodes": {"race_result_gain_vs_quali": node},
        "edges": [],
    }


def test_graph_v4_parses_prepared_contract() -> None:
    graph = parse_sequence_graph(_document(_prepared_node()))
    contract = graph.nodes["race_result_gain_vs_quali"].prepared

    assert graph.version == GRAPH_VERSION == 4
    assert contract is not None
    assert contract.allowed_stages == ("SESSION_CONCLUSION",)
    assert contract.relation is PreparedRelation.FINISH_BETTER_THAN_QUALIFYING
    assert contract.intent["cs"].startswith("Potvrzený")


def test_graph_v4_rejects_incomplete_prepared_contract() -> None:
    node = _prepared_node()
    prepared = node["prepared"]
    assert isinstance(prepared, dict)
    prepared["intent"] = {"en": "English only."}
    prepared["required_facts"] = ["finish_position", "unknown_fact"]

    errors = validate_graph_document(_document(node))

    assert any("prepared.intent.cs" in error for error in errors)
    assert any("unknown_fact" in error for error in errors)


def test_default_graph_has_exact_complete_prepared_manifest() -> None:
    graph = load_sequence_graph()
    prepared = {node.id for node in graph.nodes.values() if node.prepared is not None}

    assert graph.version == GRAPH_VERSION == 4
    assert prepared == CORE_PREPARED_NODE_IDS
    assert graph.nodes["prepared_filler"].prepared is None


def test_comparison_nodes_require_explicit_relation_fact() -> None:
    graph = load_sequence_graph()

    for node_id in (
        "race_result_gain_vs_quali",
        "race_result_hold_vs_quali",
        "race_result_loss_vs_quali",
        "race_result_gain_vs_grid",
        "race_result_hold_vs_grid",
        "race_result_loss_vs_grid",
    ):
        contract = graph.nodes[node_id].prepared
        assert contract is not None
        assert "result_relation" in contract.required_facts


def test_every_prepared_node_has_localized_contract_and_topology() -> None:
    graph = load_sequence_graph()
    stage_roots = {
        "stream_intro_venue",
        "event_intro_practice",
        "event_intro_qualifying",
        "event_intro_race",
        "result_unconfirmed",
        "prepared_filler_fatal_notice",
    }

    for node_id in CORE_PREPARED_NODE_IDS:
        node = graph.nodes[node_id]
        contract = node.prepared
        assert contract is not None
        assert set(contract.intent) == {"en", "cs"}
        assert set(contract.anchors) == {"en", "cs"}
        assert all(contract.anchors[locale] for locale in ("en", "cs"))
        assert node.event_types in {("PREPARED_FILLER",), ("PREPARED_FATAL",)}
        assert graph.incoming(node_id) or node_id in stage_roots


def test_every_prepared_node_is_reachable_from_a_lifecycle_root() -> None:
    graph = load_sequence_graph()
    roots = {
        "stream_start",
        "event_intro_practice",
        "event_intro_qualifying",
        "event_intro_race",
        "session_checkered",
        "finish",
        "result_unconfirmed",
        "prepared_filler_fatal_notice",
    }
    reachable = set(roots)
    pending = list(roots)
    while pending:
        source = pending.pop()
        for edge in graph.outgoing(source):
            if edge.target not in reachable:
                reachable.add(edge.target)
                pending.append(edge.target)

    assert CORE_PREPARED_NODE_IDS <= reachable
    assert any(
        edge.target == "session_flag_green"
        for node_id in ("formation_lap_tension", "start_lights_set")
        for edge in graph.outgoing(node_id)
    )


def test_prepared_nodes_do_not_require_legacy_audible_variant_cells() -> None:
    graph = load_sequence_graph()
    missing = {node_id for node_id, _locale, _emotion in graph.unfilled_cells()}

    assert not (missing & CORE_PREPARED_NODE_IDS)
