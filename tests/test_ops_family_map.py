"""#276 Slices 1-2 — ops family map (pit cycle + incident/aftermath/recovery)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from irswitch.contracts.coverage_matrix import can_create_event_opportunity
from irswitch.contracts.ops_family_map import (
    INCIDENT_BRANCH_BEAT_IDS,
    INCIDENT_CYCLE_PHASE_ORDER,
    INCIDENT_PRIMARY_BEAT_ID,
    INCIDENT_TERMINAL_WIRE_IDS,
    OPS_INCIDENT_WIRE_IDS,
    OPS_PIT_WIRE_IDS,
    OPS_WIRE_IDS,
    PIT_CYCLE_PHASE_ORDER,
    PIT_TERMINAL_WIRE_IDS,
    OpsFamilyRow,
    incident_branch_beats_are_documented,
    incident_cycle_phase_order_is_monotonic,
    incident_stories_have_explicit_terminals,
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
    'PIT_ENTRY': {
        'beat_id': 'pit.entry',
        'beat_role': 'opening',
        'policy_id': 'live_story',
        'outcome_ttl_ms': 10000,
        'pit_phase': 'entry',
        'incident_phase': None,
        'scope_kind': 'pit_cycle',
        'legacy_node_id': 'pit_entry',
        'story_routes': ('pit_cycle', 'single_result'),
        'realization_family': 'pit.lifecycle',
        'terminal': False,
        'branch_beat_ids': ('pit.entry',),
    },
    'PIT_LANE': {
        'beat_id': 'pit.lane',
        'beat_role': 'update',
        'policy_id': 'live_story',
        'outcome_ttl_ms': 10000,
        'pit_phase': 'lane',
        'incident_phase': None,
        'scope_kind': 'pit_cycle',
        'legacy_node_id': None,
        'story_routes': ('pit_cycle', 'single_result'),
        'realization_family': 'pit.lifecycle',
        'terminal': False,
        'branch_beat_ids': ('pit.lane',),
    },
    'PIT_STOPPED': {
        'beat_id': 'pit.stopped',
        'beat_role': 'update',
        'policy_id': 'live_story',
        'outcome_ttl_ms': 10000,
        'pit_phase': 'stopped',
        'incident_phase': None,
        'scope_kind': 'pit_cycle',
        'legacy_node_id': 'pit_stopped',
        'story_routes': ('pit_cycle', 'single_result'),
        'realization_family': 'pit.lifecycle',
        'terminal': False,
        'branch_beat_ids': ('pit.stopped',),
    },
    'PIT_RELEASED': {
        'beat_id': 'pit.released',
        'beat_role': 'update',
        'policy_id': 'live_story',
        'outcome_ttl_ms': 10000,
        'pit_phase': 'released',
        'incident_phase': None,
        'scope_kind': 'pit_cycle',
        'legacy_node_id': None,
        'story_routes': ('pit_cycle', 'single_result'),
        'realization_family': 'pit.lifecycle',
        'terminal': False,
        'branch_beat_ids': ('pit.released',),
    },
    'PIT_EXIT': {
        'beat_id': 'pit.exit',
        'beat_role': 'closure',
        'policy_id': 'result',
        'outcome_ttl_ms': 30000,
        'pit_phase': 'exit',
        'incident_phase': None,
        'scope_kind': 'pit_cycle',
        'legacy_node_id': None,
        'story_routes': ('pit_cycle', 'single_result'),
        'realization_family': 'pit.lifecycle',
        'terminal': True,
        'branch_beat_ids': ('pit.exit',),
    },
    'PIT_OUTCOME': {
        'beat_id': 'pit.outcome',
        'beat_role': 'outcome',
        'policy_id': 'result',
        'outcome_ttl_ms': 30000,
        'pit_phase': 'outcome',
        'incident_phase': None,
        'scope_kind': 'pit_outcome',
        'legacy_node_id': 'pit_outcome',
        'story_routes': ('pit_cycle', 'single_result'),
        'realization_family': 'pit.outcome',
        'terminal': True,
        'branch_beat_ids': ('pit.outcome',),
    },
    'INCIDENT': {
        'beat_id': 'incident.off_track',
        'beat_role': 'opening',
        'policy_id': 'result',
        'outcome_ttl_ms': 30000,
        'pit_phase': None,
        'incident_phase': 'event',
        'scope_kind': 'incident_event',
        'legacy_node_id': 'incident',
        'story_routes': ('incident', 'single_result'),
        'realization_family': 'incident.event',
        'terminal': False,
        'branch_beat_ids': ('incident.off_track', 'incident.unclassified'),
    },
    'INCIDENT_AFTERMATH': {
        'beat_id': 'incident.aftermath',
        'beat_role': 'update',
        'policy_id': 'context',
        'outcome_ttl_ms': 20000,
        'pit_phase': None,
        'incident_phase': 'aftermath',
        'scope_kind': 'incident_aftermath',
        'legacy_node_id': 'incident_aftermath',
        'story_routes': ('incident', 'single_result'),
        'realization_family': 'incident.aftermath',
        'terminal': False,
        'branch_beat_ids': ('incident.aftermath',),
    },
    'BACK_UNDER_WAY': {
        'beat_id': 'incident.recovery',
        'beat_role': 'closure',
        'policy_id': 'result',
        'outcome_ttl_ms': 30000,
        'pit_phase': None,
        'incident_phase': 'recovery',
        'scope_kind': 'incident_recovery',
        'legacy_node_id': 'back_under_way',
        'story_routes': ('incident', 'single_result'),
        'realization_family': 'incident.recovery',
        'terminal': True,
        'branch_beat_ids': ('incident.recovery',),
    },
}


def test_ops_family_rows_cover_pit_and_incident_inventory() -> None:
    rows = ops_family_rows()
    assert tuple(row.wire_id for row in rows) == OPS_WIRE_IDS
    assert OPS_WIRE_IDS[: len(OPS_PIT_WIRE_IDS)] == OPS_PIT_WIRE_IDS
    assert OPS_WIRE_IDS[len(OPS_PIT_WIRE_IDS) :] == OPS_INCIDENT_WIRE_IDS
    assert len(rows) == 9
    assert all(isinstance(row, OpsFamilyRow) for row in rows)


def test_every_ops_row_is_legacy_before_shadow_cutover() -> None:
    assert migration_status_by_wire_id() == dict.fromkeys(OPS_WIRE_IDS, "legacy")
    assert len(rows_by_migration_status("legacy")) == 9
    assert rows_by_migration_status("shadow") == ()
    assert rows_by_migration_status("v2") == ()


def test_rows_match_freeze_registry_and_beats() -> None:
    registry = json.loads(packaged_schema_bytes("freeze-registry.json"))
    beat_doc = json.loads(packaged_schema_bytes("beat-catalog.json"))
    beats = {str(row["id"]): row for row in beat_doc["beats"]}
    by_id = {str(row["id"]): row for row in registry["eventIdentifiers"]}
    ttl_by_policy = {str(row["id"]): int(row["ttlMs"]) for row in beat_doc["policies"]}

    for row in ops_family_rows():
        expect = _EXPECT[row.wire_id]
        reg = by_id[row.wire_id]
        assert row.event_class == reg["eventClass"] == "speakable"
        assert row.tape_channel == reg["tapeChannel"]
        assert row.can_create is can_create_event_opportunity(row.wire_id) is True
        assert list(reg["beatDefinitions"]) == list(row.branch_beat_ids)
        assert row.beat_id == expect["beat_id"]
        beat = beats[str(row.beat_id)]
        assert row.policy_id == beat["policyId"] == expect["policy_id"]
        assert row.beat_role == beat["role"] == expect["beat_role"]
        assert (
            row.realization_family
            == beat["realization"]["family"]
            == expect["realization_family"]
        )
        assert tuple(row.story_routes) == tuple(beat["storyRoutes"]) == expect["story_routes"]
        assert row.outcome_ttl_ms == ttl_by_policy[str(row.policy_id)] == expect["outcome_ttl_ms"]
        assert row.pit_phase == expect["pit_phase"]
        assert row.incident_phase == expect["incident_phase"]
        assert row.scope_kind == expect["scope_kind"]
        assert row.legacy_node_id == expect["legacy_node_id"]
        assert bool(row.terminal_reasons) is expect["terminal"]
        assert row.branch_beat_ids == expect["branch_beat_ids"]


def test_legacy_graph_nodes_exist_when_declared() -> None:
    nodes = json.loads(GRAPH.read_text(encoding="utf-8"))["nodes"]
    node_ids = set(nodes) if isinstance(nodes, dict) else {
        (n if isinstance(n, str) else n["id"]) for n in nodes
    }
    for row in ops_family_rows():
        if row.legacy_node_id is None:
            continue
        assert row.legacy_node_id in node_ids


def test_emitters_and_adapters_are_documented() -> None:
    for row in ops_family_rows():
        assert "." in row.emitter_module and ":" in row.emitter_module
        assert "." in row.adapter_module and ":" in row.adapter_module
        assert row.policy_id in {"live_story", "result", "context"}
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


def test_incident_cycle_phase_order_is_monotonic() -> None:
    assert INCIDENT_CYCLE_PHASE_ORDER == ("event", "aftermath", "recovery")
    assert OPS_INCIDENT_WIRE_IDS == ("INCIDENT", "INCIDENT_AFTERMATH", 'BACK_UNDER_WAY')
    assert incident_cycle_phase_order_is_monotonic() is True


def test_incident_stories_have_explicit_terminals() -> None:
    assert INCIDENT_TERMINAL_WIRE_IDS == frozenset({'BACK_UNDER_WAY'})
    assert incident_stories_have_explicit_terminals() is True
    assert not row_for_wire_id("INCIDENT").terminal_reasons
    assert not row_for_wire_id("INCIDENT_AFTERMATH").terminal_reasons
    assert row_for_wire_id('BACK_UNDER_WAY').terminal_reasons


def test_incident_branch_beats_are_documented() -> None:
    assert INCIDENT_PRIMARY_BEAT_ID == "incident.off_track"
    assert INCIDENT_BRANCH_BEAT_IDS == (
        "incident.off_track",
        "incident.unclassified",
    )
    assert incident_branch_beats_are_documented() is True
    row = row_for_wire_id("INCIDENT")
    assert row.beat_id == INCIDENT_PRIMARY_BEAT_ID
    assert row.branch_beat_ids == INCIDENT_BRANCH_BEAT_IDS


def test_row_for_unknown_wire_raises() -> None:
    with pytest.raises(ContractViolation, match="unknown ops wire id"):
        row_for_wire_id("NOT_AN_OPS_WIRE")


def test_ops_family_row_is_frozen() -> None:
    row = row_for_wire_id("PIT_ENTRY")
    assert isinstance(row, OpsFamilyRow)
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.migration_status = "v2"  # type: ignore[misc]
