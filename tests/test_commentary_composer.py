"""Deterministic multi-node commentary skeleton composition."""

from __future__ import annotations

from irswitch.commentary.composer import build_skeleton
from irswitch.commentary.director import CommentaryDirector, slot_bindings
from irswitch.commentary.graph import load_sequence_graph, parse_sequence_graph
from irswitch.commentary.tts import NullTtsSink
from irswitch.commentary.validator import validate_utterance
from irswitch.events.envelope import EventSubject, make_envelope
from irswitch.overlay.settings import CommentarySettings


def _graph():
    return parse_sequence_graph(
        {
            "version": 1,
            "locales": ["en", "cs"],
            "nodes": {
                "hunting": {
                    "family": "battle",
                    "event_types": ["HUNTING"],
                    "phases": ["ENTER"],
                    "speak_priority": 50,
                    "cooldown_s": 0,
                    "slots": [
                        {"name": "target_name", "type": "name", "example": "Rossi"},
                        {"name": "gap", "type": "gap", "example": "0.7"},
                    ],
                    "hr_states": ["unknown"],
                    "variants": {
                        "en": {"neutral": ["A chase is building."]},
                        "cs": {"neutral": ["Stíhání začíná."]},
                    },
                },
                "side_by_side": {
                    "family": "battle",
                    "event_types": ["SIDE_BY_SIDE"],
                    "phases": ["ENTER"],
                    "speak_priority": 70,
                    "cooldown_s": 0,
                    "slots": [{"name": "target_name", "type": "name", "example": "Rossi"}],
                    "hr_states": ["unknown"],
                    "variants": {
                        "en": {"neutral": ["They run side by side."]},
                        "cs": {"neutral": ["Jedou vedle sebe."]},
                    },
                },
                "overtake": {
                    "family": "position",
                    "event_types": ["OVERTAKE"],
                    "phases": ["RESULT"],
                    "speak_priority": 85,
                    "cooldown_s": 0,
                    "slots": [
                        {"name": "target_name", "type": "name", "example": "Rossi"},
                        {"name": "position", "type": "int", "example": "5"},
                    ],
                    "hr_states": ["unknown"],
                    "variants": {
                        "en": {"neutral": ["One completed lap."]},
                        "cs": {"neutral": ["Jedno dokončené kolo."]},
                    },
                },
                "lap": {
                    "family": "lap",
                    "event_types": ["LAP_COMPLETE"],
                    "phases": ["RESULT"],
                    "speak_priority": 50,
                    "cooldown_s": 0,
                    "slots": [
                        {"name": "lap", "type": "int", "example": "8"},
                        {"name": "lap_time", "type": "time", "example": "97.2"},
                    ],
                    "hr_states": ["unknown"],
                    "variants": {
                        "en": {"neutral": ["That's a lap for him."]},
                        "cs": {"neutral": ["Další kolo je hotové."]},
                    },
                },
            },
            "edges": [
                {
                    "from": "hunting",
                    "to": "side_by_side",
                    "when": {"same_correlation": True, "max_gap_s": 30},
                },
                {
                    "from": "side_by_side",
                    "to": "overtake",
                    "when": {"same_correlation": True, "max_gap_s": 30},
                },
            ],
        }
    )


def _beat(event_type: str, phase: str, node_time_ms: int) -> dict[str, object]:
    return {
        "event_id": f"event:{event_type}:{node_time_ms}",
        "event_type": event_type,
        "phase": phase,
        "mode": "RACE",
        "correlation_id": "battle:12",
        "monotonic_ms": node_time_ms,
        "target_name": "Rossi",
        "branch": None,
    }


def test_composer_walks_recent_graph_nodes_into_one_story() -> None:
    graph = _graph()
    envelope = make_envelope(
        event_type="OVERTAKE",
        phase="RESULT",
        mode="RACE",
        event_id="event:OVERTAKE:3000",
        correlation_id="battle:12",
        monotonic_ms=3_000,
        target=EventSubject(car_id="12", display_name="Rossi"),
        metrics={"newPosition": 5},
    )
    story = {
        "story": {
            "recent_beats": [
                _beat("HUNTING", "ENTER", 1_000),
                _beat("SIDE_BY_SIDE", "ENTER", 2_000),
            ]
        },
        "race": {"class_position": 5},
        "situation": {"current_lap": 8, "laps_remaining": 12},
    }

    result = build_skeleton(
        envelope,
        graph.node("overtake"),
        graph=graph,
        story=story,
        bindings=slot_bindings(envelope, "unknown"),
        emotion="unknown",
        language="en",
    )

    assert result is not None
    assert result.graph_path == ("hunting", "side_by_side", "overtake")
    assert 2 <= result.fact_count <= 4
    required = " ".join(fact["text"] for fact in result.fact_pack["required_facts"])
    assert "Rossi" in required
    assert "P5" in required
    assert result.tree_path[0] == "anchor"
    assert result.fact_pack["beat"]["next_possible"] == []


def test_composer_omits_unbound_target_and_builds_czech_parts() -> None:
    graph = _graph()
    envelope = make_envelope(
        event_type="LAP_COMPLETE",
        phase="RESULT",
        mode="RACE",
        event_id="event:lap:8",
        monotonic_ms=8_000,
        metrics={"lap": 8, "lapTime": 97.2},
    )
    result = build_skeleton(
        envelope,
        graph.node("lap"),
        graph=graph,
        story={
            "race": {"class_position": 7},
            "situation": {"current_lap": 8, "laps_remaining": 12},
            "story": {"recent_beats": []},
        },
        bindings=slot_bindings(envelope, "unknown", language="cs"),
        emotion="unknown",
        language="cs",
    )

    assert result is not None
    assert 2 <= result.fact_count <= 4
    assert "Rossi" not in result.text
    required = " ".join(fact["text"] for fact in result.fact_pack["required_facts"])
    assert "8" in required
    assert result.fact_pack["target"] == {}


def test_director_uses_composer_only_for_polish_path() -> None:
    graph = _graph()
    envelope = make_envelope(
        event_type="LAP_COMPLETE",
        phase="RESULT",
        mode="RACE",
        event_id="event:lap:8",
        correlation_id="lap:8",
        monotonic_ms=8_000,
        metrics={"lap": 8, "lapTime": 97.2},
    )
    context = {
        "race": {"class_position": 7},
        "situation": {"current_lap": 8, "laps_remaining": 12},
        "story": {"recent_beats": []},
    }

    polished = CommentaryDirector(
        graph=graph,
        settings=CommentarySettings(enabled=True, cooldown_s=0, llm_polish=True),
        sink=NullTtsSink(),
    )
    polished.note_composition_context(context)
    composed = polished.observe([envelope], None, 10.0)
    assert composed is not None
    assert composed.text == "That's a lap for him."
    assert composed.fact_pack is not None
    assert composed.composition_path

    authored = CommentaryDirector(
        graph=graph,
        settings=CommentarySettings(enabled=True, cooldown_s=0, llm_polish=False),
        sink=NullTtsSink(),
    )
    authored.note_composition_context(context)
    fallback = authored.observe([envelope], None, 10.0)
    assert fallback is not None
    assert fallback.text == "That's a lap for him."
    assert fallback.fact_pack is None


def test_polish_plan_uses_authored_anchor_and_proposition_fact_pack() -> None:
    graph = _graph()
    envelope = make_envelope(
        event_type="HUNTING",
        phase="ENTER",
        mode="RACE",
        event_id="event:hunting:1",
        correlation_id="battle:12",
        monotonic_ms=1_000,
        target=EventSubject(car_id="12", display_name="Rossi"),
        metrics={"gap": 0.7},
    )

    result = build_skeleton(
        envelope,
        graph.node("hunting"),
        graph=graph,
        story={
            "race": {"class_position": 7},
            "situation": {"current_lap": 8, "laps_remaining": 12, "race_phase": "middle"},
            "story": {"recent_beats": []},
        },
        bindings=slot_bindings(envelope, "unknown"),
        emotion="unknown",
        language="en",
    )

    assert result is not None
    assert result.text == "A chase is building."
    assert "P7" not in result.text
    assert "laps remaining" not in result.text
    assert result.fact_pack["version"] == "commentary-facts/2"
    assert result.fact_pack["anchor"] == result.text
    assert result.fact_pack["required_facts"]
    assert result.fact_pack["required_facts"][0]["id"] == "beat:relation"
    assert any(fact["id"] == "target:gap" for fact in result.fact_pack["optional_facts"])
    assert "recent" not in result.fact_pack


def test_every_graph_node_composes_from_its_declared_slots_in_en_and_cs() -> None:
    graph = load_sequence_graph()
    metric_key = {
        "position": "newPosition",
        "old_position": "oldPosition",
        "target_name": "targetName",
        "leader_name": "leaderName",
        "p1_name": "p1Name",
        "p2_name": "p2Name",
        "p3_name": "p3Name",
        "lap": "lap",
        "lap_time": "lapTime",
        "delta": "delta",
        "gap": "gap",
        "front_target_name": "frontTargetName",
        "front_gap": "frontGap",
        "front_position": "frontTargetPosition",
        "rear_target_name": "rearTargetName",
        "rear_gap": "rearGap",
        "bpm": "bpm",
        "streak": "streak",
        "value": "value",
        "segment": "segment",
        "sector": "sector",
        "segment_time": "segmentTime",
        "target_time": "targetTime",
        "projected_time": "projectedTime",
        "confidence": "confidence",
        "track": "track",
        "field_size": "field_size",
        "sof": "sof",
        "sof_class": "sof_class",
        "skies": "skies",
        "air_temp": "air_temp",
        "track_temp": "track_temp",
        "wind_speed": "wind_speed",
        "precipitation": "precipitation",
        "mode": "modeLabel",
        "kind": "kind",
        "current_lap": "current_lap",
        "lap_context": "lap_context",
        "race_phase": "race_phase",
        "remaining_context": "remaining_context",
        "hero_irating": "hero_irating",
        "hero_safety_rating": "hero_safety_rating",
        "hero_car": "hero_car",
        "hero_start_position": "hero_start_position",
        "target_irating": "target_irating",
        "target_safety_rating": "target_safety_rating",
        "target_car": "target_car",
        "target_nationality": "target_nationality",
    }
    declared_slots = {slot.name for node in graph.nodes.values() for slot in node.slots}
    runtime_keys = set(slot_bindings(make_envelope(), "unknown"))
    assert declared_slots <= set(metric_key)
    assert declared_slots <= runtime_keys
    for language in ("en", "cs"):
        for node in graph.nodes.values():
            metrics = {
                metric_key[slot.name]: slot.example
                for slot in node.slots
                if slot.name in metric_key
            }
            if node.id == "sector_split":
                metrics["segmentTime"] = 28.5
            envelope = make_envelope(
                event_type=node.event_types[0],
                phase=node.phases[0],
                mode=node.modes[0] if node.modes else "RACE",
                monotonic_ms=10_000,
                metrics=metrics,
                target=EventSubject(
                    car_id="8", display_name=str(metrics.get("targetName") or "Rossi")
                ),
            )
            result = build_skeleton(
                envelope,
                node,
                graph=graph,
                story={
                    "race": {"class_position": 7},
                    "situation": {
                        "current_lap": 8,
                        "laps_remaining": 12,
                        "race_phase": "middle",
                    },
                    "story": {"recent_beats": []},
                },
                bindings=slot_bindings(envelope, "unknown", language=language),
                emotion="unknown",
                language=language,
            )
            assert result is not None, (language, node.id)
            assert 2 <= result.fact_count <= 4, (language, node.id, result.text)
            assert validate_utterance(result.text, node) == [], (
                language,
                node.id,
                result.text,
            )


def test_every_sequence_edge_can_feed_a_composed_history_part() -> None:
    graph = load_sequence_graph()
    for edge in graph.edges:
        source = graph.nodes[edge.source]
        target = graph.nodes[edge.target]
        gap_s = edge.min_gap_s + min(0.1, max(0.0, edge.max_gap_s - edge.min_gap_s))
        current_ms = 1_000 + int(gap_s * 1_000)
        correlation = f"story:{edge.source}:{edge.target}"
        source_mode = source.modes[0] if source.modes else "RACE"
        target_mode = target.modes[0] if target.modes else source_mode
        story = {
            "story": {
                "recent_beats": [
                    {
                        "event_id": f"event:{edge.source}",
                        "event_type": source.event_types[0],
                        "phase": source.phases[0],
                        "mode": source_mode,
                        "correlation_id": correlation,
                        "monotonic_ms": 1_000,
                        "target_name": "Rossi",
                        "branch": source.branch or None,
                    }
                ]
            },
            "race": {"class_position": 7},
            "situation": {"current_lap": 8, "laps_remaining": 12},
        }
        envelope = make_envelope(
            event_type=target.event_types[0],
            phase=target.phases[0],
            mode=target_mode,
            correlation_id=correlation,
            monotonic_ms=current_ms,
            target=EventSubject(car_id="8", display_name="Rossi"),
            metrics={"branch": target.branch} if target.branch else {},
        )
        result = build_skeleton(
            envelope,
            target,
            graph=graph,
            story=story,
            bindings=slot_bindings(envelope, "unknown"),
            emotion="unknown",
            language="en",
        )
        assert result is not None, (edge.source, edge.target)
        assert result.graph_path == (edge.source, edge.target)
        assert result.tree_path[0] == "anchor", (edge.source, edge.target, result.text)
        assert result.fact_pack["beat"]["graph_path"] == [edge.source, edge.target]
