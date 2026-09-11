"""#276 Slice 1 — ops family map (pit entry/service/exit cycle)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from irswitch.contracts.coverage_matrix import can_create_event_opportunity
from irswitch.contracts.ops_family_map import (
    OPS_PIT_WIRE_IDS,
    PIT_CYCLE_PHASE_ORDER,
    PIT_TERMINAL_WIRE_IDS,
    OpsFamilyRow,
    migration_status_by_wire_id,
    ops_family_rows,
    pit_cycle_phase_order_is_monotonic,
    pit_cycle_stories_have_explicit_terminals,
    row_for_wire_id,
    rows_by_migration_status,
)
from irswitch.contracts.primitives import ContractViolation
from irswitch.contracts.resources import packaged_schema_bytes

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "src" / "irswitch" / "commentary" / "data" / "sequence_graph.json"

_EXPECT = {
    "PIT_ENTRY": {
        "beat_id": "pit.entry",
        "beat_role": "opening",
        "policy_id": "live_story",
        "outcome_ttl_ms": 10000,
        "pit_phase": "entry",
        "scope_kind": "pit_cycle",
        "legacy_node_id": "pit_entry",
        "story_routes": ("pit_cycle", "single_result"),
        "realization_family": "pit.lifecycle",
        "terminal": False,
    },
    "PIT_LANE": {
        "beat_id": "pit.lane",
        "beat_role": "update",
        "policy_id": "live_story",
        "outcome_ttl_ms": 10000,
        "pit_phase": "lane",
        "scope_kind": "pit_cycle",
        "legacy_node_id": None,
        "story_routes": ("pit_cycle", "single_result"),
        "realization_family": "pit.lifecycle",
        "terminal": False,
    },
    "PIT_STOPPED": {
        "beat_id": "pit.stopped",
        "beat_role": "update",
        "policy_id": "live_story",
        "outcome_ttl_ms": 10000,
        "pit_phase": "stopped",
        "scope_kind": "pit_cycle",
        "legacy_node_id": "pit_stopped",
        "story_routes": ("pit_cycle", "single_result"),
        "realization_family": "pit.lifecycle",
        "terminal": False,
    },
    "PIT_RELEASED": {
        "beat_id": "pit.released",
        "beat_role": "update",
        "policy_id": "live_story",
        "outcome_ttl_ms": 10000,
        "pit_phase": "released",
        "scope_kind": "pit_cycle",
        "legacy_node_id": None,
        "story_routes": ("pit_cycle", "single_result"),
        "realization_family": "pit.lifecycle",
        "terminal": False,
    },
    "PIT_EXIT": {
        "beat_id": "pit.exit",
        "beat_role": "closure",
        "policy_id": "result",
        "outcome_ttl_ms": 30000,
        "pit_phase": "exit",
        "scope_kind": "pit_cycle",
        "legacy_node_id": None,
        "story_routes": ("pit_cycle", "single_result"),
        "realization_family": "pit.lifecycle",
        "terminal": True,
    },
    "PIT_OUTCOME": {
        "beat_id": "pit.outcome",
        "beat_role": "outcome",
        "policy_id": "result",
        "outcome_ttl_ms": 30000,
        "pit_phase": "outcome",
        "scope_kind": "pit_outcome",
        "legacy_node_id": "pit_outcome",
        "story_routes": ("pit_cycle", "single_result"),
        "realization_family": "pit.outcome",
        "terminal": True,
    },
}


def test_ops_family_rows_cover_pit_cycle_inventory() -> None:
    rows = ops_family_rows()
    assert tuple(row.wire_id for row in rows) == OPS_PIT_WIRE_IDS
    assert len(rows) == 6
    assert all(isinstance(row, OpsFamilyRow) for row in rows)


def test_every_pit_row_is_legacy_before_shadow_cutover() -> None:
    assert migration_status_by_wire_id() == dict.fromkeys(OPS_PIT_WIRE_IDS, "legacy")
    assert len(rows_by_migration_status("legacy")) == 6
    assert rows_by_migration_status("shadow") == ()
    assert rows_by_migration_status("v2") == ()


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

    for row in ops_family_rows():
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
        assert row.pit_phase == expect["pit_phase"]
        assert row.scope_kind == expect["scope_kind"]
        assert row.legacy_node_id == expect["legacy_node_id"]
        assert row.beat_id == expect["beat_id"]
        assert bool(row.terminal_reasons) is expect["terminal"]


def test_legacy_graph_nodes_exist_when_declared() -> None:
    nodes = json.loads(GRAPH.read_text(encoding="utf-8"))["nodes"]
    for row in ops_family_rows():
        if row.legacy_node_id is None:
            assert row.wire_id in {"PIT_LANE", "PIT_RELEASED", "PIT_EXIT"}
            continue
        assert row.legacy_node_id in nodes


def test_emitters_and_adapters_are_documented() -> None:
    for row in ops_family_rows():
        assert "." in row.emitter_module and ":" in row.emitter_module
        assert "." in row.adapter_module and ":" in row.adapter_module
        assert row.policy_id in {"live_story", "result"}
        assert row.outcome_ttl_ms is not None and row.outcome_ttl_ms > 0
        assert row.invalidate_reasons


def test_pit_cycle_phase_order_is_monotonic() -> None:
    assert PIT_CYCLE_PHASE_ORDER == (
        "entry",
        "lane",
        "stopped",
        "released",
        "exit",
        "outcome",
    )
    assert pit_cycle_phase_order_is_monotonic() is True


def test_pit_cycle_stories_have_explicit_terminals() -> None:
    assert PIT_TERMINAL_WIRE_IDS == frozenset({"PIT_EXIT", "PIT_OUTCOME"})
    assert pit_cycle_stories_have_explicit_terminals() is True
    assert not row_for_wire_id("PIT_ENTRY").terminal_reasons
    assert row_for_wire_id("PIT_EXIT").terminal_reasons
    assert row_for_wire_id("PIT_OUTCOME").terminal_reasons


def test_row_for_unknown_wire_raises() -> None:
    with pytest.raises(ContractViolation, match="unknown ops wire id"):
        row_for_wire_id("NOT_AN_OPS_WIRE")


def test_ops_family_row_is_frozen() -> None:
    row = row_for_wire_id("PIT_ENTRY")
    assert isinstance(row, OpsFamilyRow)
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.migration_status = "v2"  # type: ignore[misc]
