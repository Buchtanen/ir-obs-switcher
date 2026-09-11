"""#275 Slice 1–3 — timing family map (lap/SF, sector, PB/pace, quali/invalid)."""

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
    RACE_FINISH_WIRE_IDS,
    TIMING_WIRE_IDS,
    TimingFamilyRow,
    gain_and_loss_polarities_are_distinct,
    invalid_lap_scope_is_explicit,
    lap_complete_is_not_race_finish,
    migration_status_by_wire_id,
    row_for_wire_id,
    rows_by_migration_status,
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
    )
    assert len(rows) == len(set(TIMING_WIRE_IDS))


def test_every_row_is_legacy_before_shadow_cutover() -> None:
    assert migration_status_by_wire_id() == {
        "LAP_COMPLETE": "legacy",
        "SECTOR_SPLIT": "legacy",
        "SECTOR_BEST": "legacy",
        "PERSONAL_BEST": "legacy",
        "GAIN_FOUND": "legacy",
        "TIME_LOST": "legacy",
        "HOT_LAP": "legacy",
        "PROJECTED_LAP": "legacy",
        "INVALID_LAP": "legacy",
    }
    assert len(rows_by_migration_status("legacy")) == 9
    assert rows_by_migration_status("shadow") == ()
    assert rows_by_migration_status("v2") == ()


def test_lap_complete_is_not_race_finish() -> None:
    assert lap_complete_is_not_race_finish() is True
    lap = row_for_wire_id("LAP_COMPLETE")
    assert lap.scope_kind == "lap_sf"
    assert lap.polarity == "lap_complete"
    assert lap.beat_id == "timing.lap.completed"
    assert "finish" not in str(lap.beat_id)
    assert lap.realization_family != "session.finish"
    assert lap.wire_id not in RACE_FINISH_WIRE_IDS
    assert lap.beat_id != "session.hero_finish"


def test_sector_rows_use_sector_scope_and_distinct_beats() -> None:
    split = row_for_wire_id("SECTOR_SPLIT")
    best = row_for_wire_id("SECTOR_BEST")
    assert split.scope_kind == best.scope_kind == "sector"
    assert split.beat_id != best.beat_id
    assert split.polarity == "sector_split"
    assert best.polarity == "sector_best"
    assert split.legacy_node_id == "sector_split"
    assert best.legacy_node_id is None


def test_personal_best_uses_lap_pb_scope() -> None:
    pb = row_for_wire_id("PERSONAL_BEST")
    assert pb.scope_kind == "lap_pb"
    assert pb.polarity == "personal_best"
    assert pb.beat_id == "timing.lap.personal_best"
    assert pb.realization_family == "timing.lap_result"
    assert pb.legacy_node_id == "personal_best"
    assert pb.emitter_module.endswith("LapEmitter")
    assert "adapters.lap:" in pb.adapter_module


def test_gain_and_loss_polarities_are_distinct() -> None:
    assert gain_and_loss_polarities_are_distinct() is True
    gained = row_for_wire_id("GAIN_FOUND")
    lost = row_for_wire_id("TIME_LOST")
    assert gained.polarity == "gain_found"
    assert lost.polarity == "time_lost"
    assert gained.polarity != lost.polarity
    assert gained.beat_id != lost.beat_id
    assert gained.scope_kind == lost.scope_kind == "pace_delta"
    assert gained.realization_family == lost.realization_family == "timing.delta"


def test_hot_lap_is_attempt_not_result() -> None:
    hot = row_for_wire_id("HOT_LAP")
    assert hot.scope_kind == "lap_attempt"
    assert hot.polarity == "hot_lap"
    assert hot.beat_role == "opening"
    assert hot.policy_id == "live_story"
    assert hot.realization_family == "timing.attempt"
    assert hot.beat_id == "timing.lap.hot"
    assert hot.emitter_module.endswith("QualiEmitter")


def test_projected_lap_is_projection_not_completed_result() -> None:
    projected = row_for_wire_id("PROJECTED_LAP")
    assert projected.scope_kind == "lap_projection"
    assert projected.polarity == "projected_lap"
    assert projected.beat_id == "timing.lap.projected"
    assert projected.realization_family == "timing.projection"
    assert projected.policy_id == "live_story"
    assert "completed" not in projected.beat_id
    assert projected.emitter_module.endswith("QualiEmitter")


def test_invalid_lap_scope_is_explicit() -> None:
    assert invalid_lap_scope_is_explicit() is True
    assert INVALID_LAP_SESSION_MODES == frozenset({"PRACTICE", "QUALIFYING"})
    assert "RACE" not in INVALID_LAP_SESSION_MODES
    row = row_for_wire_id("INVALID_LAP")
    assert row.scope_kind == "invalid_lap"
    assert row.polarity == "invalid_lap"
    assert row.realization_family == "incident.invalid_lap"
    assert row.beat_id == "incident.invalid_lap"
    assert row.story_routes == ("incident", "single_result")
    assert row.emitter_module.endswith("InvalidLapEmitter")
    assert "exception_extra:" in row.adapter_module


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


def test_legacy_graph_nodes_exist_when_declared() -> None:
    nodes = json.loads(GRAPH.read_text(encoding="utf-8"))["nodes"]
    for row in timing_family_rows():
        if row.legacy_node_id is None:
            assert row.wire_id == "SECTOR_BEST"
            continue
        assert row.legacy_node_id in nodes


def test_emitters_and_adapters_are_documented() -> None:
    for row in timing_family_rows():
        assert row.emitter_module.startswith("irswitch.events.")
        assert row.adapter_module.startswith("irswitch.events.adapters.")
        assert row.policy_id in {"result", "transient", "live_story"}
        assert row.outcome_ttl_ms is not None and row.outcome_ttl_ms > 0


def test_row_for_unknown_wire_raises() -> None:
    with pytest.raises(ContractViolation, match="unknown timing wire id"):
        row_for_wire_id("NOT_A_TIMING_WIRE")


def test_timing_family_row_is_frozen() -> None:
    row = row_for_wire_id("LAP_COMPLETE")
    assert isinstance(row, TimingFamilyRow)
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.migration_status = "v2"  # type: ignore[misc]
