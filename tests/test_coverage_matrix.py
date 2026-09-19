"""#256 event-family coverage matrix: 60 identifiers, 64 beats, successor DAG."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from irswitch.contracts import (
    ContractViolation,
    audit_coverage_matrix,
    can_create_event_opportunity,
    load_coverage_matrix,
)
from irswitch.contracts.resources import packaged_schema_bytes
from irswitch.events import __all__ as events_exports

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
DISPOSITION = ROOT / "docs" / "v2.0.0" / "event-beat-disposition.md"
SOURCE = ROOT / "src" / "irswitch" / "contracts" / "coverage_matrix.py"
PACKAGED_CATALOGS = (
    "beat-catalog.json",
    "successor-graph.json",
    "realization-pattern-cards.json",
)
EVENT_CLASSES = frozenset({"speakable", "visual_only", "compatibility_alias"})
CLAIM_FAMILIES = ("transition", "identity", "expiry", "counterfactual")
FORBIDDEN_LEGACY_TRIGGERS = frozenset(
    {
        "STREAM_START",
        "SESSION_INTRO_PRACTICE",
        "SESSION_INTRO_QUALIFY",
        "SESSION_INTRO_RACE",
        "SESSION_WRAP",
    }
)


def _disposition_identifier_ids() -> list[str]:
    section = DISPOSITION.read_text(encoding="utf-8").split("## Identifier disposition", 1)[1]
    table = section.split("## ", 1)[0]
    ids: list[str] = []
    for line in table.splitlines():
        if not line.startswith("| `"):
            continue
        ident = line.split("`", 2)[1]
        if ident == "tape_channel":
            continue
        ids.append(ident)
    return ids


def _vertical_slice_ids() -> set[str]:
    payload = json.loads((MACHINE / "vertical-slice-fixtures.json").read_text(encoding="utf-8"))
    return {str(row["id"]) for row in payload["fixtures"]}


@pytest.mark.parametrize("name", PACKAGED_CATALOGS)
def test_packaged_coverage_catalogs_match_frozen_machine_sources(name: str) -> None:
    assert json.loads(packaged_schema_bytes(name)) == json.loads(
        (MACHINE / name).read_text(encoding="utf-8")
    )


def test_audit_proves_frozen_identifier_and_beat_counts() -> None:
    report = audit_coverage_matrix()

    assert report.event_count == 60
    assert report.speakable_count == 52
    assert report.visual_only_count == 4
    assert report.alias_count == 4
    assert report.beat_count == 64
    assert report.family_count == 37
    assert report.policy_count == 6
    assert report.tape_channel_count == 36
    assert report.pattern_card_count == 256
    assert report.successor_edge_count == 50
    assert report.story_count == 11
    assert report.predicate_count == 57
    assert report.feature_count == 21
    assert report.detector_count == 3
    assert report.is_directed_acyclic is True
    assert report.legacy_trigger_count == 0
    assert load_coverage_matrix() == report


def test_disposition_markdown_lists_each_current_identifier_once() -> None:
    report = audit_coverage_matrix()
    markdown_ids = _disposition_identifier_ids()

    assert len(markdown_ids) == 60
    assert len(set(markdown_ids)) == 60
    assert set(markdown_ids) == {row.id for row in report.identifiers}
    assert {row.event_class for row in report.identifiers} <= EVENT_CLASSES


def test_speakable_rows_resolve_and_aliases_cannot_create_opportunity() -> None:
    report = audit_coverage_matrix()
    beat_ids = {beat.id for beat in report.beats}

    for row in report.identifiers:
        if row.event_class == "speakable":
            assert row.beat_ids
            assert set(row.beat_ids) <= beat_ids
            assert can_create_event_opportunity(row.id) is True
            continue
        assert row.beat_ids == ()
        assert can_create_event_opportunity(row.id) is False

    with pytest.raises(ContractViolation, match="unknown event identifier"):
        can_create_event_opportunity("UNDER_PRESSURE")


def test_every_beat_has_story_family_policy_channel_and_cards() -> None:
    report = audit_coverage_matrix()

    assert len(report.beats) == 64
    for beat in report.beats:
        assert beat.story_routes
        assert beat.family
        assert beat.policy_id
        assert beat.tape_channel
        assert beat.max_freedom == "tight"
        assert beat.enabled_pattern_cards == 4


def test_successor_dag_has_exits_and_cadence_material_guards() -> None:
    report = audit_coverage_matrix()

    assert report.is_directed_acyclic is True
    assert report.cyclic_component_count == 0
    assert report.nonterminal_count == 28
    assert report.guarded_edge_count == 50
    assert report.material_revision_bonus == 6


def test_stage_specific_beats_use_normalized_enums_not_obs_scenes() -> None:
    report = audit_coverage_matrix()

    assert report.raw_obs_scene_count == 0
    stages = {value for beat in report.beats for value in beat.stage_any_of}
    contexts = {value for beat in report.beats for value in beat.broadcast_contexts}
    phases = {value for beat in report.beats for value in beat.vehicle_phases}
    assert stages <= {"practice", "qualifying", "race"}
    assert contexts <= {"on_track", "garage", "lobby", "replay", "transition", "unknown"}
    assert phases <= {
        "garage",
        "pit_lane",
        "out_lap",
        "timed_lap",
        "in_lap",
        "parade_lap",
        "racing",
        "unknown",
    }


def test_replaced_legacy_identifiers_are_not_runtime_triggers() -> None:
    report = audit_coverage_matrix()
    trigger_ids = {trigger for beat in report.beats for trigger in beat.trigger_ids}

    assert FORBIDDEN_LEGACY_TRIGGERS.isdisjoint(trigger_ids)
    assert "STREAM_STARTED" in trigger_ids
    assert "SESSION_STARTED" in trigger_ids
    assert "SESSION_ENDED" in trigger_ids


def test_released_detectors_never_require_default_off_tuning() -> None:
    report = audit_coverage_matrix()

    assert report.released_required_tuning_count == 0
    assert report.experimental_detector_count == 3


def test_replay_fixture_refs_cover_claim_families_and_exist() -> None:
    report = audit_coverage_matrix()
    known = _vertical_slice_ids()

    assert tuple(item.id for item in report.replay_refs) == CLAIM_FAMILIES
    for family in report.replay_refs:
        assert family.fixture_ids
        assert set(family.fixture_ids) <= known


def test_unknown_or_visual_mutation_cannot_create_speech() -> None:
    registry = json.loads(packaged_schema_bytes("freeze-registry.json"))
    alias = next(row for row in registry["eventIdentifiers"] if row["id"] == "BATTLE_LOST")
    alias["beatDefinitions"] = ["position.lost"]

    report = audit_coverage_matrix(registry=registry)
    assert can_create_event_opportunity("BATTLE_LOST") is False
    assert report.alias_count == 4

    beats = json.loads(packaged_schema_bytes("beat-catalog.json"))
    beats["beats"][0]["triggers"] = [{"id": "STREAM_START", "kind": "accepted_event"}]
    with pytest.raises(ContractViolation, match="legacy trigger"):
        audit_coverage_matrix(beats=beats)

    scene = json.loads(packaged_schema_bytes("beat-catalog.json"))
    scene["beats"][0]["hardContext"]["stageAnyOf"] = ["ON TRACK"]
    with pytest.raises(ContractViolation, match="OBS scene"):
        audit_coverage_matrix(beats=scene)

    cards = json.loads(packaged_schema_bytes("realization-pattern-cards.json"))
    cards["cards"] = cards["cards"][:255]
    with pytest.raises(ContractViolation, match="pattern card"):
        audit_coverage_matrix(cards=cards)


def test_coverage_matrix_is_not_exported_from_events_and_never_uses_eval() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert "coverage_matrix" not in events_exports
    assert "NarrativeRuntime" not in source
    assert "eval(" not in source
    assert "exec(" not in source
    assert "compile(" not in source
    for banned in ("irswitch.commentary", "irswitch.overlay", "irswitch.events"):
        assert banned not in source


def test_dangling_successor_and_released_required_tuning_fail_closed() -> None:
    graph = json.loads(packaged_schema_bytes("successor-graph.json"))
    graph["edges"][0]["toBeatId"] = "missing.beat"
    with pytest.raises(ContractViolation, match="unknown successor"):
        audit_coverage_matrix(graph=graph)

    detectors = json.loads(packaged_schema_bytes("detector-catalog.json"))
    detectors["definitions"][0]["experimental"] = False
    with pytest.raises(ContractViolation, match="released detector"):
        audit_coverage_matrix(detectors=detectors)
