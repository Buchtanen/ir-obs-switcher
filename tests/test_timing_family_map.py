"""#275 Slice 1–5 — timing family map (timing + session intros/recaps)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from irswitch.contracts.coverage_matrix import can_create_event_opportunity
from irswitch.contracts.primitives import ContractViolation
from irswitch.contracts.resources import packaged_schema_bytes
from irswitch.contracts.timing_family_map import (
    INVALID_LAP_SESSION_MODES,
    SESSION_RECAP_WIRE_IDS,
    SESSION_STAGE_ORDER,
    TIMING_WIRE_IDS,
    TimingFamilyRow,
    en_patterns_and_tts_slots_are_curated,
    gain_and_loss_polarities_are_distinct,
    inherited_facts_use_active_lineage_only,
    invalid_lap_scope_is_explicit,
    lap_complete_is_not_race_finish,
    migration_status_by_wire_id,
    row_for_wire_id,
    rows_by_migration_status,
    session_stage_order_is_monotonic,
    timing_family_rows,
)

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "src" / "irswitch" / "commentary" / "data" / "sequence_graph.json"

_EXPECT = {
    "LAP_COMPLETE": {
        "beat_id": "timing.lap.completed",
        "beat_role": "result",
        "policy_id": "result",
        "outcome_ttl_ms": 30000,
        "polarity": "lap_complete",
        "scope_kind": "lap_sf",
        "legacy_node_id": "lap_complete",
        "story_routes": ("timing_attempt", "single_result"),
        "realization_family": "timing.lap_result",
        "session_stage": None,
        "requires_active_lineage": False,
    },
    "SECTOR_SPLIT": {
        "beat_id": "timing.sector.split",
        "beat_role": "update",
        "policy_id": "transient",
        "outcome_ttl_ms": 6000,
        "polarity": "sector_split",
        "scope_kind": "sector",
        "legacy_node_id": "sector_split",
        "story_routes": ("timing_attempt", "single_result"),
        "realization_family": "timing.sector",
        "session_stage": None,
        "requires_active_lineage": False,
    },
    "SECTOR_BEST": {
        "beat_id": "timing.sector.best",
        "beat_role": "result",
        "policy_id": "result",
        "outcome_ttl_ms": 30000,
        "polarity": "sector_best",
        "scope_kind": "sector",
        "legacy_node_id": None,
        "story_routes": ("timing_attempt", "single_result"),
        "realization_family": "timing.sector",
        "session_stage": None,
        "requires_active_lineage": False,
    },
    "PERSONAL_BEST": {
        "beat_id": "timing.lap.personal_best",
        "beat_role": "result",
        "policy_id": "result",
        "outcome_ttl_ms": 30000,
        "polarity": "personal_best",
        "scope_kind": "lap_pb",
        "legacy_node_id": "personal_best",
        "story_routes": ("timing_attempt", "single_result"),
        "realization_family": "timing.lap_result",
        "session_stage": None,
        "requires_active_lineage": False,
    },
    "GAIN_FOUND": {
        "beat_id": "timing.pace.gain",
        "beat_role": "update",
        "policy_id": "transient",
        "outcome_ttl_ms": 6000,
        "polarity": "gain_found",
        "scope_kind": "pace_delta",
        "legacy_node_id": "gain_found",
        "story_routes": ("timing_attempt", "single_result"),
        "realization_family": "timing.delta",
        "session_stage": None,
        "requires_active_lineage": False,
    },
    "TIME_LOST": {
        "beat_id": "timing.pace.loss",
        "beat_role": "update",
        "policy_id": "transient",
        "outcome_ttl_ms": 6000,
        "polarity": "time_lost",
        "scope_kind": "pace_delta",
        "legacy_node_id": "time_lost",
        "story_routes": ("timing_attempt", "single_result"),
        "realization_family": "timing.delta",
        "session_stage": None,
        "requires_active_lineage": False,
    },
    "HOT_LAP": {
        "beat_id": "timing.lap.hot",
        "beat_role": "opening",
        "policy_id": "live_story",
        "outcome_ttl_ms": 10000,
        "polarity": "hot_lap",
        "scope_kind": "lap_attempt",
        "legacy_node_id": "hot_lap",
        "story_routes": ("timing_attempt", "single_result"),
        "realization_family": "timing.attempt",
        "session_stage": None,
        "requires_active_lineage": False,
    },
    "PROJECTED_LAP": {
        "beat_id": "timing.lap.projected",
        "beat_role": "update",
        "policy_id": "live_story",
        "outcome_ttl_ms": 10000,
        "polarity": "projected_lap",
        "scope_kind": "lap_projection",
        "legacy_node_id": "projected_lap",
        "story_routes": ("timing_attempt", "single_result"),
        "realization_family": "timing.projection",
        "session_stage": None,
        "requires_active_lineage": False,
    },
    "INVALID_LAP": {
        "beat_id": "incident.invalid_lap",
        "beat_role": "result",
        "policy_id": "result",
        "outcome_ttl_ms": 30000,
        "polarity": "invalid_lap",
        "scope_kind": "invalid_lap",
        "legacy_node_id": "invalid_lap",
        "story_routes": ("incident", "single_result"),
        "realization_family": "incident.invalid_lap",
        "session_stage": None,
        "requires_active_lineage": False,
    },
    "SESSION_INTRO_PRACTICE": {
        "beat_id": "session.intro.practice",
        "beat_role": "opening",
        "policy_id": "context",
        "outcome_ttl_ms": 20000,
        "polarity": "session_intro_practice",
        "scope_kind": "session_intro",
        "legacy_node_id": "session_intro_practice",
        "story_routes": ("session_occurrence", "single_result"),
        "realization_family": "session.intro",
        "session_stage": "practice",
        "requires_active_lineage": True,
    },
    "SESSION_INTRO_QUALIFY": {
        "beat_id": "session.intro.qualifying",
        "beat_role": "opening",
        "policy_id": "context",
        "outcome_ttl_ms": 20000,
        "polarity": "session_intro_qualify",
        "scope_kind": "session_intro",
        "legacy_node_id": "session_intro_qualify",
        "story_routes": ("session_occurrence", "single_result"),
        "realization_family": "session.intro",
        "session_stage": "qualifying",
        "requires_active_lineage": True,
    },
    "SESSION_INTRO_RACE": {
        "beat_id": "session.intro.race",
        "beat_role": "opening",
        "policy_id": "context",
        "outcome_ttl_ms": 20000,
        "polarity": "session_intro_race",
        "scope_kind": "session_intro",
        "legacy_node_id": "session_intro_race",
        "story_routes": ("session_occurrence", "single_result"),
        "realization_family": "session.intro",
        "session_stage": "race",
        "requires_active_lineage": True,
    },
    "QUALI_RECAP": {
        "beat_id": "session.qualifying_recap",
        "beat_role": "outcome",
        "policy_id": "result",
        "outcome_ttl_ms": 30000,
        "polarity": "quali_recap",
        "scope_kind": "session_recap",
        "legacy_node_id": "quali_recap",
        "story_routes": ("session_occurrence", "single_result"),
        "realization_family": "session.recap",
        "session_stage": "race",
        "requires_active_lineage": True,
    },
}


def test_map_covers_every_timing_wire_id_exactly_once() -> None:
    rows = timing_family_rows()
    assert tuple(row.wire_id for row in rows) == TIMING_WIRE_IDS
    assert TIMING_WIRE_IDS == (
        "LAP_COMPLETE",
        "SECTOR_SPLIT",
        "SECTOR_BEST",
        "PERSONAL_BEST",
        "GAIN_FOUND",
        "TIME_LOST",
        "HOT_LAP",
        "PROJECTED_LAP",
        "INVALID_LAP",
        "SESSION_INTRO_PRACTICE",
        "SESSION_INTRO_QUALIFY",
        "SESSION_INTRO_RACE",
        "QUALI_RECAP",
    )
    assert len(rows) == len(set(TIMING_WIRE_IDS)) == 13


def test_every_creatable_row_is_shadow_after_activation() -> None:
    assert migration_status_by_wire_id() == {
        "LAP_COMPLETE": "shadow",
        "SECTOR_SPLIT": "shadow",
        "SECTOR_BEST": "shadow",
        "PERSONAL_BEST": "shadow",
        "GAIN_FOUND": "shadow",
        "TIME_LOST": "shadow",
        "HOT_LAP": "shadow",
        "PROJECTED_LAP": "shadow",
        "INVALID_LAP": "shadow",
        "SESSION_INTRO_PRACTICE": "shadow",
        "SESSION_INTRO_QUALIFY": "shadow",
        "SESSION_INTRO_RACE": "shadow",
        "QUALI_RECAP": "shadow",
    }
    assert len(rows_by_migration_status("shadow")) == 13
    assert rows_by_migration_status("legacy") == ()
    assert rows_by_migration_status("v2") == ()


def test_lap_complete_is_not_race_finish() -> None:
    assert lap_complete_is_not_race_finish() is True
    lap = row_for_wire_id("LAP_COMPLETE")
    assert lap.scope_kind == "lap_sf"
    assert lap.polarity == "lap_complete"
    assert lap.requires_active_lineage is False


def test_gain_and_loss_polarities_are_distinct() -> None:
    assert gain_and_loss_polarities_are_distinct() is True


def test_invalid_lap_scope_is_explicit() -> None:
    assert invalid_lap_scope_is_explicit() is True
    assert INVALID_LAP_SESSION_MODES == frozenset({"PRACTICE", "QUALIFYING"})


def test_session_stage_order_is_monotonic() -> None:
    assert SESSION_STAGE_ORDER == ("practice", "qualifying", "race")
    assert session_stage_order_is_monotonic() is True
    practice = row_for_wire_id("SESSION_INTRO_PRACTICE")
    qualify = row_for_wire_id("SESSION_INTRO_QUALIFY")
    race = row_for_wire_id("SESSION_INTRO_RACE")
    assert practice.session_stage == "practice"
    assert qualify.session_stage == "qualifying"
    assert race.session_stage == "race"
    assert practice.scope_kind == qualify.scope_kind == race.scope_kind == "session_intro"


def test_inherited_facts_use_active_lineage_only() -> None:
    assert inherited_facts_use_active_lineage_only() is True
    assert SESSION_RECAP_WIRE_IDS == frozenset(
        {
            "SESSION_INTRO_PRACTICE",
            "SESSION_INTRO_QUALIFY",
            "SESSION_INTRO_RACE",
            "QUALI_RECAP",
        }
    )
    for wire_id in SESSION_RECAP_WIRE_IDS:
        row = row_for_wire_id(wire_id)
        assert row.requires_active_lineage is True
        assert row.session_stage is not None
    # Non-recap timing wires do not silently inherit lineage.
    for row in timing_family_rows():
        if row.wire_id in SESSION_RECAP_WIRE_IDS:
            continue
        assert row.requires_active_lineage is False


def test_quali_recap_is_historical_into_race() -> None:
    recap = row_for_wire_id("QUALI_RECAP")
    assert recap.scope_kind == "session_recap"
    assert recap.session_stage == "race"
    assert recap.beat_role == "outcome"
    assert recap.realization_family == "session.recap"
    assert recap.emitter_module.endswith("GridStoryFsm")


def test_rows_match_freeze_registry_and_beats() -> None:
    registry = json.loads(packaged_schema_bytes("freeze-registry.json"))
    beats = {
        str(row["id"]): row
        for row in json.loads(packaged_schema_bytes("beat-catalog.json"))["beats"]
    }
    by_id = {str(row["id"]): row for row in registry["eventIdentifiers"]}
    ttl_by_policy = {
        str(row["id"]): int(row["ttlMs"])
        for row in json.loads(packaged_schema_bytes("beat-catalog.json"))["policies"]
    }

    for row in timing_family_rows():
        expect = _EXPECT[row.wire_id]
        reg = by_id[row.wire_id]
        assert row.event_class == reg["eventClass"] == "speakable"
        assert row.tape_channel == reg["tapeChannel"]
        assert row.can_create is can_create_event_opportunity(row.wire_id) is True
        assert reg["beatDefinitions"] == [row.beat_id]
        beat = beats[str(row.beat_id)]
        assert row.policy_id == beat["policyId"] == expect["policy_id"]
        assert row.beat_role == beat["role"] == expect["beat_role"]
        assert (
            row.realization_family == beat["realization"]["family"] == expect["realization_family"]
        )
        assert tuple(row.story_routes) == tuple(beat["storyRoutes"]) == expect["story_routes"]
        assert row.outcome_ttl_ms == ttl_by_policy[str(row.policy_id)] == expect["outcome_ttl_ms"]
        assert row.polarity == expect["polarity"]
        assert row.scope_kind == expect["scope_kind"]
        assert row.legacy_node_id == expect["legacy_node_id"]
        assert row.beat_id == expect["beat_id"]
        assert row.session_stage == expect["session_stage"]
        assert row.requires_active_lineage == expect["requires_active_lineage"]


def test_legacy_graph_nodes_exist_when_declared() -> None:
    nodes = json.loads(GRAPH.read_text(encoding="utf-8"))["nodes"]
    for row in timing_family_rows():
        if row.legacy_node_id is None:
            assert row.wire_id == "SECTOR_BEST"
            continue
        assert row.legacy_node_id in nodes


def test_emitters_and_adapters_are_documented() -> None:
    for row in timing_family_rows():
        assert "." in row.emitter_module and ":" in row.emitter_module
        assert "." in row.adapter_module and ":" in row.adapter_module
        assert row.policy_id in {"result", "transient", "live_story", "context"}
        assert row.outcome_ttl_ms is not None and row.outcome_ttl_ms > 0


def test_row_for_unknown_wire_raises() -> None:
    with pytest.raises(ContractViolation, match="unknown timing wire id"):
        row_for_wire_id("NOT_A_TIMING_WIRE")


def test_en_patterns_and_tts_slots_are_curated() -> None:
    assert en_patterns_and_tts_slots_are_curated() is True
    for row in timing_family_rows():
        assert len(row.en_pattern_ids) >= 4
        assert len(row.en_claim_surfaces) >= 4
        assert row.tts_slot_formats == ("subjectSurface", "requiredClaimSurface")
        assert row.beat_id is not None
        assert all(pid.startswith(f"{row.beat_id}:") for pid in row.en_pattern_ids)


def test_en_claim_surfaces_keep_gain_loss_polarity() -> None:
    gained = row_for_wire_id("GAIN_FOUND")
    lost = row_for_wire_id("TIME_LOST")
    assert gained.en_claim_surfaces
    assert lost.en_claim_surfaces
    for surface in gained.en_claim_surfaces:
        lowered = surface.lower()
        assert not any(token in lowered for token in gained.en_forbidden_tokens)
    for surface in lost.en_claim_surfaces:
        lowered = surface.lower()
        assert not any(token in lowered for token in lost.en_forbidden_tokens)
    assert set(gained.en_claim_surfaces).isdisjoint(set(lost.en_claim_surfaces))
    assert set(gained.en_forbidden_tokens).isdisjoint(set(lost.en_forbidden_tokens))


def test_lap_complete_en_surfaces_are_not_race_finish() -> None:
    lap = row_for_wire_id("LAP_COMPLETE")
    assert lap.en_forbidden_tokens
    for surface in lap.en_claim_surfaces:
        lowered = surface.lower()
        assert "wins the race" not in lowered
        assert "checkered" not in lowered
        assert not any(token in lowered for token in lap.en_forbidden_tokens)


def test_projected_lap_en_surfaces_are_not_completed_result() -> None:
    projected = row_for_wire_id("PROJECTED_LAP")
    for surface in projected.en_claim_surfaces:
        lowered = surface.lower()
        assert "has completed" not in lowered
        assert "checkered" not in lowered
        assert (
            "projected" in lowered
            or "on for" in lowered
            or "tracks toward" in lowered
            or "projection" in lowered
        )


def test_timing_family_row_is_frozen() -> None:
    row = row_for_wire_id("LAP_COMPLETE")
    assert isinstance(row, TimingFamilyRow)
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.migration_status = "v2"  # type: ignore[misc]
