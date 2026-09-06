"""Frozen cross-layer contracts for deterministic race scenarios."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path

import pytest

from irswitch.events.scenarios.loader import (
    ScenarioDefinitionError,
    load_scenario_definition,
    parse_scenario_definition,
    validate_scenario_document,
)
from irswitch.events.scenarios.model import (
    EpisodeScope,
    EvidenceValue,
    GuardDecision,
    GuardResult,
    ScenarioBeat,
)
from irswitch.overlay.protocol import CandidateEvent


def test_evidence_value_accepts_bounded_quality_and_uncertainty() -> None:
    evidence = EvidenceValue(
        value=12.5,
        observed_at=100.0,
        age_s=0.2,
        valid=True,
        quality=0.85,
        uncertainty=0.4,
        source="RaceState.speed_mps",
    )

    assert evidence.value == 12.5
    assert evidence.quality == 0.85


@pytest.mark.parametrize(
    "changes",
    [
        {"age_s": -0.1},
        {"age_s": math.inf},
        {"quality": -0.01},
        {"quality": 1.01},
        {"quality": math.nan},
        {"uncertainty": -0.1},
        {"source": ""},
        {"valid": True, "value": None},
    ],
)
def test_evidence_value_rejects_invalid_contract(changes: dict[str, object]) -> None:
    values: dict[str, object] = {
        "value": 1.0,
        "observed_at": 10.0,
        "age_s": 0.0,
        "valid": True,
        "quality": 1.0,
        "uncertainty": None,
        "source": "RaceState.speed_mps",
    }
    values.update(changes)

    with pytest.raises(ValueError):
        EvidenceValue(**values)  # type: ignore[arg-type]


def test_guard_result_distinguishes_no_match_from_unknown() -> None:
    no_match = GuardResult(
        decision=GuardDecision.NO_MATCH,
        confidence=0.9,
        reason="surface_is_on_track",
        evidence=("track_surface",),
    )
    unknown = GuardResult(
        decision=GuardDecision.UNKNOWN,
        confidence=0.0,
        reason="motion_sources_missing",
        evidence=("speed", "lap_distance"),
    )

    assert no_match.matched is False
    assert no_match.unknown is False
    assert unknown.matched is False
    assert unknown.unknown is True


def test_episode_scope_builds_stable_namespaced_identity() -> None:
    scope = EpisodeScope(
        scenario_id="track_excursion_story",
        subsession_id="test7",
        session_num=0,
        run_epoch=2,
        player_car_idx=12,
    )

    episode_id = scope.episode_id(3)

    assert episode_id == ("scenario:track_excursion_story:session:test7:0:run:2:hero:12:episode:3")


@pytest.mark.parametrize(
    "changes",
    [
        {"scenario_id": "Track Excursion"},
        {"subsession_id": ""},
        {"session_num": -1},
        {"run_epoch": -1},
        {"player_car_idx": -1},
    ],
)
def test_episode_scope_rejects_incomplete_or_unstable_identity(
    changes: dict[str, object],
) -> None:
    values: dict[str, object] = {
        "scenario_id": "track_excursion_story",
        "subsession_id": "test7",
        "session_num": 0,
        "run_epoch": 0,
        "player_car_idx": 12,
    }
    values.update(changes)

    with pytest.raises(ValueError):
        EpisodeScope(**values)  # type: ignore[arg-type]


def test_scenario_beat_has_distinct_correlation_and_immutable_metrics() -> None:
    episode_id = "scenario:track_excursion_story:session:test7:0:run:0:hero:12:episode:1"
    source_metrics = {"surface": 1, "outcome": "back_on_track"}
    beat = ScenarioBeat(
        scenario_id="track_excursion_story",
        scenario_version=1,
        episode_id=episode_id,
        parent_story_id=episode_id,
        beat_id="track_rejoined",
        event_type="BACK_ON_TRACK",
        phase="RESULT",
        priority=68,
        confidence=0.91,
        reason="surface_rejoin_held",
        metrics=source_metrics,
    )
    source_metrics["surface"] = 99

    assert beat.correlation_id == f"{episode_id}:beat:track_rejoined"
    assert beat.metrics["surface"] == 1
    with pytest.raises(TypeError):
        beat.metrics["surface"] = 2  # type: ignore[index]
    assert beat.to_dict()["correlation_id"] == beat.correlation_id


def test_scenario_beat_rejects_invalid_phase_confidence_and_identity() -> None:
    values: dict[str, object] = {
        "scenario_id": "track_excursion_story",
        "scenario_version": 1,
        "episode_id": "episode:1",
        "parent_story_id": "episode:1",
        "beat_id": "track_rejoined",
        "event_type": "BACK_ON_TRACK",
        "phase": "RESULT",
        "priority": 68,
        "confidence": 0.9,
        "reason": "surface_rejoin_held",
        "metrics": {},
    }
    for changes in (
        {"phase": "SOMETIME"},
        {"confidence": 1.1},
        {"scenario_version": 0},
        {"episode_id": ""},
        {"parent_story_id": ""},
        {"beat_id": "Back On Track"},
    ):
        invalid = dict(values)
        invalid.update(changes)
        with pytest.raises(ValueError):
            ScenarioBeat(**invalid)  # type: ignore[arg-type]


def test_candidate_event_scenario_metadata_is_optional_and_inert() -> None:
    legacy = CandidateEvent(name="lap", channel="lap", priority=10)
    assert legacy.confidence == 1.0
    assert legacy.reason == ""
    assert legacy.scenario_id == ""
    assert legacy.episode_id == ""
    assert legacy.parent_story_id == ""

    scenario = CandidateEvent(
        name="back_on_track",
        channel="commentary_only",
        priority=68,
        confidence=0.91,
        reason="surface_rejoin_held",
        scenario_id="track_excursion_story",
        episode_id="episode:1",
        parent_story_id="episode:1",
    )
    assert scenario.confidence == 0.91
    assert scenario.parent_story_id == scenario.episode_id


_REFERENCE_SCENARIO = (
    Path(__file__).resolve().parents[1]
    / "docs"
    / "scenarios"
    / "incident_offtrack_recovery_v1.json"
)


def _reference_document() -> dict[str, object]:
    return json.loads(_REFERENCE_SCENARIO.read_text(encoding="utf-8"))


def test_reference_scenario_loads_to_deterministic_typed_definition() -> None:
    definition = load_scenario_definition(_REFERENCE_SCENARIO)

    assert definition.scenario_id == "incident_offtrack_recovery"
    assert definition.scenario_version == 1
    assert definition.initial_state == "IDLE"
    assert definition.scope_modes == ("PRACTICE", "QUALIFYING", "RACE", "GENERIC")
    assert definition.transitions[0].id == "start_incident_episode"
    assert definition.transitions[-1].id == "episode_timeout"
    assert definition.emissions["recovery"].event_type == "BACK_UNDER_WAY"


def test_loader_rejects_unknown_top_level_field() -> None:
    raw = _reference_document()
    raw["expressionLanguage"] = "speed > 2.5"

    assert "unknown top-level field: expressionLanguage" in validate_scenario_document(raw)
    with pytest.raises(ScenarioDefinitionError, match="unknown top-level field"):
        parse_scenario_definition(raw)


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (
            lambda raw: raw["transitions"][0].update(guard="eval_python"),
            "unknown guard: eval_python",
        ),
        (
            lambda raw: raw["transitions"][0].update(actions=["speak_now"]),
            "unknown action: speak_now",
        ),
        (
            lambda raw: raw["observations"]["speed"].update(unit="furlongs"),
            "unknown unit: furlongs",
        ),
        (
            lambda raw: raw["resets"][0].update(reason="whenever"),
            "unknown reset reason: whenever",
        ),
    ],
)
def test_loader_rejects_unregistered_names(mutate: object, expected: str) -> None:
    raw = _reference_document()
    mutate(raw)  # type: ignore[operator]

    assert any(expected in error for error in validate_scenario_document(raw))


def test_loader_rejects_duplicate_transitions_and_unreachable_states() -> None:
    raw = _reference_document()
    raw["transitions"].append(copy.deepcopy(raw["transitions"][0]))
    raw["states"].append(
        {
            "id": "ORPHANED",
            "initial": False,
            "terminal": True,
            "meaning": "Never entered.",
        }
    )

    errors = validate_scenario_document(raw)

    assert any("duplicate transition id: start_incident_episode" in error for error in errors)
    assert any("unreachable state: ORPHANED" in error for error in errors)


@pytest.mark.parametrize("field", ["holdS", "withinS", "afterS"])
def test_loader_rejects_negative_transition_time(field: str) -> None:
    raw = _reference_document()
    raw["transitions"][7][field] = -0.01

    assert any(
        f"{field} must be non-negative" in error for error in validate_scenario_document(raw)
    )


def test_loader_rejects_unregistered_emission_and_missing_identity_input() -> None:
    raw = _reference_document()
    raw["emissions"]["recovery"]["eventType"] = "TELEPORT_TO_MARS"
    raw["identity"]["fields"].remove("run_epoch")

    errors = validate_scenario_document(raw)

    assert any("unknown event type: TELEPORT_TO_MARS" in error for error in errors)
    assert any("missing identity field: run_epoch" in error for error in errors)


@pytest.mark.parametrize(
    "path",
    [
        ("transitions", 0, "guard"),
        ("transitions", 0, "to"),
        ("observations", "speed", "unit"),
        ("observations", "speed", "missingPolicy"),
        ("features", "motion", "estimator"),
        ("features", "motion", "resetScope"),
        ("resets", 0, "reason"),
        ("resets", 0, "action"),
        ("emissions", "recovery", "eventType"),
        ("emissions", "recovery", "phase"),
    ],
)
def test_malformed_values_are_validation_errors_not_type_errors(path) -> None:
    raw = _reference_document()
    target = raw
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = {"bad": "object"}
    assert validate_scenario_document(raw)
    with pytest.raises(ScenarioDefinitionError):
        parse_scenario_definition(raw)


@pytest.mark.parametrize(
    "section", ["scope", "identity", "coalescing", "terminalPolicy", "director"]
)
def test_unknown_nested_policy_fields_are_rejected(section: str) -> None:
    raw = _reference_document()
    raw[section]["executePython"] = "eval()"
    assert any("executePython" in error for error in validate_scenario_document(raw))


def test_typo_in_hold_and_negative_nontransition_timeout_are_rejected() -> None:
    raw = _reference_document()
    raw["transitions"][0]["holdSeconds"] = 10
    raw["coalescing"]["windowS"] = -1
    raw["terminalPolicy"]["retainForS"] = float("nan")
    errors = validate_scenario_document(raw)
    assert any("holdSeconds" in error for error in errors)
    assert any("windowS" in error for error in errors)
    assert any("retainForS" in error for error in errors)


def test_definition_retains_full_immutable_policy_without_aliases() -> None:
    raw = _reference_document()
    definition = parse_scenario_definition(raw)
    raw["parameters"]["incidentNarrationMinDelta"]["default"] = 99
    raw["coalescing"]["windowS"] = 99
    assert definition.parameters["incidentNarrationMinDelta"]["default"] == 2
    assert definition.document["coalescing"]["windowS"] == 0.75
    with pytest.raises(TypeError):
        definition.document["coalescing"]["windowS"] = 99


def test_loader_rejects_duplicate_json_keys(tmp_path: Path) -> None:
    source = tmp_path / "duplicate.json"
    source.write_text('{"schemaVersion": 1, "schemaVersion": 2}', encoding="utf-8")
    with pytest.raises(ScenarioDefinitionError, match="duplicate JSON key"):
        load_scenario_definition(source)


def test_nested_beat_metrics_are_copied_and_json_serializable() -> None:
    metrics = {"evidence": {"sources": ["surface", "speed"]}}
    beat = ScenarioBeat(
        scenario_id="track_excursion_story",
        scenario_version=1,
        episode_id="e:1",
        parent_story_id="e:1",
        beat_id="root",
        event_type="INCIDENT",
        phase="RESULT",
        priority=80,
        confidence=0.9,
        reason="off_track_confirmed",
        metrics=metrics,
    )
    metrics["evidence"]["sources"].append("invented")
    assert beat.metrics["evidence"]["sources"] == ("surface", "speed")
    assert json.loads(json.dumps(beat.to_dict()))["metrics"]["evidence"]["sources"] == [
        "surface",
        "speed",
    ]
