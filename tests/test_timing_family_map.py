"""#275 Slice 1 — timing family map (lap/SF + sector inventory)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from irswitch.contracts.coverage_matrix import can_create_event_opportunity
from irswitch.contracts.primitives import ContractViolation
from irswitch.contracts.resources import packaged_schema_bytes
from irswitch.contracts.timing_family_map import (
    RACE_FINISH_WIRE_IDS,
    TIMING_WIRE_IDS,
    TimingFamilyRow,
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
        "outcome_ttl_ms": 30_000,
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
        "outcome_ttl_ms": 6_000,
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
        "outcome_ttl_ms": 30_000,
        "polarity": "sector_best",
        "scope_kind": "sector",
        "legacy_node_id": None,
        "story_routes": ("timing_attempt", "single_result"),
        "realization_family": "timing.sector",
    },
}


def test_map_covers_every_timing_wire_id_exactly_once() -> None:
    rows = timing_family_rows()
    assert tuple(row.wire_id for row in rows) == TIMING_WIRE_IDS
    assert TIMING_WIRE_IDS == ("LAP_COMPLETE", "SECTOR_SPLIT", "SECTOR_BEST")
    assert len(rows) == len(set(TIMING_WIRE_IDS))


def test_every_row_is_legacy_before_shadow_cutover() -> None:
    assert migration_status_by_wire_id() == {
        "LAP_COMPLETE": "legacy",
        "SECTOR_SPLIT": "legacy",
        "SECTOR_BEST": "legacy",
    }
    assert len(rows_by_migration_status("legacy")) == 3
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
            # SECTOR_BEST: creatable speakable without dedicated sequence-graph node.
            assert row.wire_id == "SECTOR_BEST"
            continue
        assert row.legacy_node_id in nodes


def test_emitters_and_adapters_are_documented() -> None:
    for row in timing_family_rows():
        assert row.emitter_module.startswith("irswitch.events.")
        assert row.adapter_module.startswith("irswitch.events.adapters.")
        assert row.policy_id in {"result", "transient"}
        assert row.outcome_ttl_ms is not None and row.outcome_ttl_ms > 0


def test_row_for_unknown_wire_raises() -> None:
    with pytest.raises(ContractViolation, match="unknown timing wire id"):
        row_for_wire_id("NOT_A_TIMING_WIRE")


def test_timing_family_row_is_frozen() -> None:
    row = row_for_wire_id("LAP_COMPLETE")
    assert isinstance(row, TimingFamilyRow)
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.migration_status = "v2"  # type: ignore[misc]
