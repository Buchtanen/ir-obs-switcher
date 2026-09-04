"""Graph-v3 typed scenario matching and parent-story identity."""

from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from irswitch.commentary.graph import (
    EdgeIdentityPolicy,
    MaterialChangePolicy,
    SemanticPolicy,
    parse_sequence_graph,
    validate_graph_document,
)
from irswitch.commentary.graph_runtime import SequenceGraphRuntime, candidate_from_envelope
from irswitch.events.envelope import make_envelope


def _node(event_type: str, match: dict[str, object]) -> dict[str, object]:
    return {
        "family": "exception",
        "event_types": [event_type],
        "phases": ["RESULT"],
        "speak_priority": 80,
        "hr_states": ["unknown"],
        "match": match,
        "variants": {"en": {"neutral": ["Off track."]}},
        "editorial": {
            "policy": "story_result",
            "semantic_policy": "scenario_episode",
            "criticality": "story",
            "repeat_weight": 1.0,
            "silence_affinity": 0.0,
            "material_change_policy": "scenario_beat",
        },
    }


def _v3_graph() -> dict[str, object]:
    return {
        "version": 3,
        "locales": ["en"],
        "nodes": {
            "track_excursion": _node(
                "INCIDENT",
                {
                    "beat_role": ["root"],
                    "primary_relation": "track_excursion",
                },
            ),
            "slide_to_excursion": _node(
                "INCIDENT",
                {
                    "beat_role": ["root"],
                    "primary_relation": "track_excursion",
                    "cause": ["slide"],
                    "evidence_level": ["CONFIRMED", "PROBABLE_HIGH"],
                    "minimum_confidence": 0.9,
                },
            ),
            "track_rejoined": _node(
                "BACK_UNDER_WAY",
                {
                    "beat_role": ["closure"],
                    "primary_relation": "track_excursion",
                    "outcome": ["back_on_track"],
                },
            ),
        },
        "edges": [
            {
                "from": "track_excursion",
                "to": "track_rejoined",
                "when": {
                    "identity": "same_parent_story",
                    "min_gap_s": 0.3,
                    "max_gap_s": 90.0,
                },
                "editorial": {
                    "transition_bonus": 8,
                    "closure": True,
                    "repeat_weight": 1.0,
                },
            }
        ],
    }


def test_v3_specific_match_dominates_generic_and_can_abstain() -> None:
    graph = parse_sequence_graph(_v3_graph())

    specific = graph.nodes_for(
        "INCIDENT",
        "RESULT",
        beat_role="root",
        primary_relation="track_excursion",
        cause="slide",
        evidence_level="PROBABLE_HIGH",
        confidence=0.93,
    )
    fallback = graph.nodes_for(
        "INCIDENT",
        "RESULT",
        beat_role="root",
        primary_relation="track_excursion",
        cause="slide",
        evidence_level="PROBABLE_HIGH",
        confidence=0.70,
    )

    assert [node.id for node in specific] == ["slide_to_excursion"]
    assert [node.id for node in fallback] == ["track_excursion"]
    assert specific[0].match.minimum_confidence == 0.9


def test_v3_edge_uses_explicit_parent_story_identity() -> None:
    graph = parse_sequence_graph(_v3_graph())
    edge = graph.edges[0]

    assert edge.identity is EdgeIdentityPolicy.SAME_PARENT_STORY
    assert edge.same_correlation is False


def test_v2_boolean_identity_maps_to_closed_policy() -> None:
    raw = _v3_graph()
    raw["version"] = 2
    for node in raw["nodes"].values():
        node.pop("match", None)
        node["editorial"]["semantic_policy"] = "context_fact"
        node["editorial"]["material_change_policy"] = "occurrence"
    raw["edges"][0]["when"] = {"same_correlation": False}

    graph = parse_sequence_graph(raw)

    assert graph.edges[0].identity is EdgeIdentityPolicy.ANY


def test_v3_rejects_unknown_match_field_and_legacy_or_any_identity() -> None:
    unknown_selector = _v3_graph()
    unknown_selector["nodes"]["track_excursion"]["match"]["python"] = "eval()"
    legacy_identity = copy.deepcopy(_v3_graph())
    legacy_identity["edges"][0]["when"] = {"same_correlation": False}
    any_identity = copy.deepcopy(_v3_graph())
    any_identity["edges"][0]["when"]["identity"] = "any"

    assert any(
        "unknown match field: python" in error
        for error in validate_graph_document(unknown_selector)
    )
    assert any(
        "identity is required" in error for error in validate_graph_document(legacy_identity)
    )
    assert any("identity 'any'" in error for error in validate_graph_document(any_identity))


def test_scenario_episode_semantics_and_edge_match_use_parent_story() -> None:
    graph = parse_sequence_graph(_v3_graph())
    runtime = SequenceGraphRuntime(graph)
    runtime.reset(run_epoch=2, now=0.0)
    parent = "scenario:track_excursion_story:session:s:0:run:2:hero:7:episode:1"

    root_env = make_envelope(
        event_type="INCIDENT",
        event_id="root",
        correlation_id=f"{parent}:beat:root",
        sequence=1,
        monotonic_ms=1000,
        metrics={
            "scenarioId": "track_excursion_story",
            "parentStoryId": parent,
            "beatRole": "root",
            "primaryRelation": "track_excursion",
            "cause": "unknown",
            "evidenceLevel": "CONFIRMED",
        },
    )
    closure_env = make_envelope(
        event_type="BACK_UNDER_WAY",
        event_id="closure",
        correlation_id=f"{parent}:beat:track_rejoined",
        sequence=2,
        monotonic_ms=2000,
        metrics={
            "scenarioId": "track_excursion_story",
            "parentStoryId": parent,
            "beatRole": "closure",
            "primaryRelation": "track_excursion",
            "outcome": "back_on_track",
            "evidenceLevel": "CONFIRMED",
        },
    )
    root = candidate_from_envelope(
        graph.nodes["track_excursion"],
        root_env,
        run_epoch=2,
        story_id=None,
        source_revision=1,
    )
    closure = candidate_from_envelope(
        graph.nodes["track_rejoined"],
        closure_env,
        run_epoch=2,
        story_id=None,
        source_revision=1,
    )

    assert root.semantic_key == closure.semantic_key
    assert root.material_revision != closure.material_revision
    assert runtime.record_speaking(root, now=1.0)
    assert runtime.score(closure, now=2.0).transition == 8.0
    assert runtime.score(closure, now=2.0).closure > 0.0

    other_env = make_envelope(
        **{
            **closure_env.to_dict(),
            "eventId": "other",
            "correlationId": "other:beat:track_rejoined",
            "metrics": {
                **closure_env.metrics,
                "parentStoryId": "scenario:other:episode:2",
            },
        }
    )
    other = candidate_from_envelope(
        graph.nodes["track_rejoined"],
        other_env,
        run_epoch=2,
        story_id=None,
        source_revision=1,
    )
    assert runtime.score(other, now=2.0).transition == 0.0


def test_v3_adds_only_closed_scenario_policies() -> None:
    assert SemanticPolicy.SCENARIO_EPISODE.value == "scenario_episode"
    assert MaterialChangePolicy.SCENARIO_BEAT.value == "scenario_beat"


def _candidate_pair(identity: str = "same_parent_story"):
    raw = _v3_graph()
    raw["edges"][0]["when"]["identity"] = identity
    graph = parse_sequence_graph(raw)
    runtime = SequenceGraphRuntime(graph)
    runtime.reset(run_epoch=2, now=0.0)
    candidates = []
    for name, role in (("track_excursion", "root"), ("track_rejoined", "closure")):
        env = make_envelope(
            event_type=graph.nodes[name].event_types[0],
            phase="RESULT",
            event_id=name,
            correlation_id=f"episode:1:beat:{name}",
            session_id="session:s:0",
            subject={"car_id": "7"},
            metrics={
                "scenarioId": "track_excursion_story",
                "parentStoryId": "episode:1",
                "beatRole": role,
                "primaryRelation": "track_excursion",
                "outcome": "back_on_track" if role == "closure" else "unknown",
                "evidenceLevel": "CONFIRMED",
            },
        )
        candidates.append(
            candidate_from_envelope(
                graph.nodes[name], env, run_epoch=2, story_id=None, source_revision=1
            )
        )
    return runtime, candidates[0], candidates[1]


@pytest.mark.parametrize("conflict", ["parent", "scenario", "run", "session", "hero", "missing"])
def test_parent_story_edge_rejects_scope_conflicts(conflict: str) -> None:
    runtime, root, closure = _candidate_pair()
    if conflict == "parent":
        closure = replace(closure, parent_story_id="episode:2", correlation_id=root.correlation_id)
    elif conflict == "scenario":
        closure = replace(closure, scenario_id="unrelated_story")
    elif conflict == "run":
        closure = replace(closure, run_epoch=3)
    elif conflict == "session":
        closure = replace(closure, envelope=replace(closure.envelope, session_id="session:other"))
    elif conflict == "hero":
        other_subject = replace(closure.envelope.subject, car_id="8")
        closure = replace(closure, envelope=replace(closure.envelope, subject=other_subject))
    else:
        closure = replace(closure, parent_story_id="")
    assert runtime.record_speaking(root, now=1.0)
    assert runtime.score(closure, now=2.0).closure == 0.0


def test_caused_by_edge_requires_explicit_directional_link() -> None:
    runtime, root, closure = _candidate_pair("caused_by_parent_story")
    child = replace(closure, parent_story_id="pit:1", scenario_id="pit_story")
    assert runtime.record_speaking(root, now=1.0)
    assert runtime.score(child, now=2.0).closure == 0.0
    linked = replace(child, caused_by_parent_story_id=root.parent_story_id)
    assert runtime.score(linked, now=2.0).closure > 0.0


def test_runtime_does_not_score_or_commit_underqualified_candidate() -> None:
    raw = _v3_graph()
    graph = parse_sequence_graph(raw)
    runtime, root, _ = _candidate_pair()
    runtime.graph = graph
    candidate = replace(root, node_id="slide_to_excursion", cause="slide", confidence=0.7)
    assert runtime.select([candidate], now=1.0) is None
    assert runtime.record_speaking(candidate, now=1.0) is False
    assert runtime.occurrence_count == 0


def test_matching_excludes_other_modes_before_specificity() -> None:
    raw = _v3_graph()
    raw["nodes"]["slide_to_excursion"]["modes"] = ["race"]
    graph = parse_sequence_graph(raw)
    selected = graph.nodes_for(
        "INCIDENT",
        "RESULT",
        mode="PRACTICE",
        beat_role="root",
        primary_relation="track_excursion",
        cause="slide",
        evidence_level="CONFIRMED",
        confidence=0.99,
    )
    assert [node.id for node in selected] == ["track_excursion"]


@pytest.mark.parametrize("confidence", [float("nan"), float("inf"), -0.1, 1.1])
def test_invalid_confidence_abstains(confidence: float) -> None:
    graph = parse_sequence_graph(_v3_graph())
    assert (
        graph.nodes_for(
            "INCIDENT",
            "RESULT",
            beat_role="root",
            primary_relation="track_excursion",
            confidence=confidence,
        )
        == []
    )


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1.0])
def test_v3_rejects_invalid_edge_times(value: float) -> None:
    raw = _v3_graph()
    raw["edges"][0]["when"]["max_gap_s"] = value
    assert any("max_gap_s" in error for error in validate_graph_document(raw))


def test_legacy_consumers_cannot_treat_parent_edge_as_unrestricted() -> None:
    from irswitch.commentary.composer import _BeatRef, _matching_edge
    from irswitch.commentary.director import _edge_matches

    graph = parse_sequence_graph(_v3_graph())
    assert not _edge_matches(graph.edges[0], "beat:root", "beat:closure", 1.0)
    assert (
        _matching_edge(
            graph,
            _BeatRef("track_excursion", "INCIDENT", "RESULT", "RACE", "root", 1000),
            _BeatRef("track_rejoined", "BACK_UNDER_WAY", "RESULT", "RACE", "closure", 2000),
        )
        is None
    )
