"""#274 race-outcome family map: inventory, polarity, story/TTL contract."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from irswitch.contracts.coverage_matrix import can_create_event_opportunity
from irswitch.contracts.primitives import ContractViolation
from irswitch.contracts.race_outcome_family_map import (
    FALLBACK_STORY_ROUTE,
    RACE_OUTCOME_WIRE_IDS,
    SELF_CONTAINED_POLICIES,
    migration_status_by_wire_id,
    race_outcome_family_rows,
    row_for_wire_id,
    rows_by_migration_status,
)
from irswitch.contracts.resources import packaged_schema_bytes
from irswitch.events.adapters.position import _event_type_for_position_change

ROOT = Path(__file__).resolve().parents[1]
GRAPH = ROOT / "src" / "irswitch" / "commentary" / "data" / "sequence_graph.json"

# Slice 2 ground truth: beat role + correlation + closing routes + adapter prefix.
_STORY_TTL_EXPECT = {
    "OVERTAKE": {
        "beat_role": "outcome",
        "policy_id": "critical",
        "outcome_ttl_ms": 45_000,
        "correlation_kind": "target",
        "correlation_bindings": ("hero", "target"),
        "closing_story_routes": ("battle_ahead", "battle_two_front"),
        "fallback_story_route": FALLBACK_STORY_ROUTE,
        "adapter_correlation_prefix": "position:",
        "story_routes": ("battle_ahead", "battle_two_front", "single_result"),
    },
    "POSITION_GAINED": {
        "beat_role": "result",
        "policy_id": "result",
        "outcome_ttl_ms": 30_000,
        "correlation_kind": "hero_position",
        "correlation_bindings": ("hero", "oldPosition", "newPosition", "direction"),
        "closing_story_routes": (),
        "fallback_story_route": FALLBACK_STORY_ROUTE,
        "adapter_correlation_prefix": "position:",
        "story_routes": ("single_result",),
    },
    "POSITION_LOST": {
        "beat_role": "result",
        "policy_id": "result",
        "outcome_ttl_ms": 30_000,
        "correlation_kind": "hero_position",
        "correlation_bindings": ("hero", "oldPosition", "newPosition", "direction"),
        "closing_story_routes": ("battle_behind", "battle_two_front"),
        "fallback_story_route": FALLBACK_STORY_ROUTE,
        "adapter_correlation_prefix": "position:",
        "story_routes": ("battle_behind", "battle_two_front", "single_result"),
    },
    "LEADER_CHANGE": {
        "beat_role": "result",
        "policy_id": "result",
        "outcome_ttl_ms": 30_000,
        "correlation_kind": "leader",
        "correlation_bindings": ("oldLeader", "newLeader"),
        "closing_story_routes": (),
        "fallback_story_route": FALLBACK_STORY_ROUTE,
        "adapter_correlation_prefix": "leader:",
        "story_routes": ("single_result",),
    },
    "FINISH": {
        "beat_role": "outcome",
        "policy_id": "critical",
        "outcome_ttl_ms": 45_000,
        "correlation_kind": "hero_finish",
        "correlation_bindings": ("occurrence", "hero"),
        "closing_story_routes": ("session_occurrence",),
        "fallback_story_route": FALLBACK_STORY_ROUTE,
        "adapter_correlation_prefix": "session:",
        "story_routes": ("session_occurrence", "single_result"),
    },
}


def test_map_covers_every_race_outcome_wire_id_exactly_once() -> None:
    rows = race_outcome_family_rows()
    assert tuple(row.wire_id for row in rows) == RACE_OUTCOME_WIRE_IDS
    assert len(rows) == len(set(RACE_OUTCOME_WIRE_IDS))


def test_speakable_rows_match_freeze_registry_and_beats() -> None:
    registry = json.loads(packaged_schema_bytes("freeze-registry.json"))
    beats = {
        str(row["id"]): row
        for row in json.loads(packaged_schema_bytes("beat-catalog.json"))["beats"]
    }
    by_id = {str(row["id"]): row for row in registry["eventIdentifiers"]}

    for row in race_outcome_family_rows():
        reg = by_id[row.wire_id]
        assert row.event_class == reg["eventClass"]
        assert row.tape_channel == reg["tapeChannel"]
        assert row.can_create is can_create_event_opportunity(row.wire_id)
        if row.event_class == "compatibility_alias":
            assert row.beat_id is None
            assert row.can_create is False
            continue
        assert reg["beatDefinitions"] == [row.beat_id]
        beat = beats[str(row.beat_id)]
        assert row.policy_id == beat["policyId"]
        assert row.realization_family == beat["realization"]["family"]
        assert list(row.story_routes) == beat["storyRoutes"]
        assert row.self_contained is True


def test_legacy_graph_nodes_exist_for_creatable_families() -> None:
    nodes = json.loads(GRAPH.read_text(encoding="utf-8"))["nodes"]
    for row in race_outcome_family_rows():
        if not row.can_create:
            assert row.legacy_node_id is None
            continue
        assert row.legacy_node_id in nodes


def test_gain_and_loss_polarity_never_reversed() -> None:
    gained = row_for_wire_id("POSITION_GAINED")
    lost = row_for_wire_id("POSITION_LOST")

    assert gained.polarity == "gain"
    assert lost.polarity == "loss"
    assert gained.direction_equals == "gained"
    assert lost.direction_equals == "lost"
    assert gained.direction_equals != lost.direction_equals
    assert gained.beat_id != lost.beat_id
    assert gained.realization_family == lost.realization_family == "position.change"
    assert _event_type_for_position_change("gain") == "POSITION_GAINED"
    assert _event_type_for_position_change("loss") == "POSITION_LOST"
    assert _event_type_for_position_change("gain") != _event_type_for_position_change("loss")


def test_pass_actor_frame_keeps_passer_before_passed() -> None:
    overtake = row_for_wire_id("OVERTAKE")
    assert overtake.polarity == "pass"
    assert overtake.actor_frame == "hero→target"
    assert overtake.predicate_id == "position.passed"
    assert overtake.beat_id == "position.pass"
    # Required ordinal attrs stay passer-then-target in catalog claim order.
    beat = next(
        row
        for row in json.loads(packaged_schema_bytes("beat-catalog.json"))["beats"]
        if row["id"] == "position.pass"
    )
    attrs = beat["claims"]["required"][0]["requiredAttributes"]
    assert attrs == [
        "oldPasserPosition",
        "newPasserPosition",
        "oldTargetPosition",
        "newTargetPosition",
    ]


def test_overtaken_alias_cannot_create_opportunity() -> None:
    alias = row_for_wire_id("OVERTAKEN")
    assert alias.polarity == "alias"
    assert alias.can_create is False
    assert alias.beat_id is None
    assert can_create_event_opportunity("OVERTAKEN") is False


def test_migration_status_records_every_family_as_legacy() -> None:
    status = migration_status_by_wire_id()
    assert set(status) == set(RACE_OUTCOME_WIRE_IDS)
    assert set(status.values()) == {"legacy"}
    assert {row.wire_id for row in rows_by_migration_status("legacy")} == set(RACE_OUTCOME_WIRE_IDS)
    assert rows_by_migration_status("shadow") == ()
    assert rows_by_migration_status("v2") == ()


def test_unknown_wire_id_raises() -> None:
    with pytest.raises(ContractViolation, match="unknown race-outcome wire id"):
        row_for_wire_id("NOT_A_RACE_OUTCOME")


def test_story_and_beat_roles_match_catalog() -> None:
    for wire_id, expect in _STORY_TTL_EXPECT.items():
        row = row_for_wire_id(wire_id)
        assert row.beat_role == expect["beat_role"]
        assert row.story_routes == expect["story_routes"]
        assert row.fallback_story_route == expect["fallback_story_route"]
        assert row.closing_story_routes == expect["closing_story_routes"]
        # Closing routes are a subset of authored storyRoutes; fallback is one of them.
        assert set(row.closing_story_routes).issubset(row.story_routes)
        assert row.fallback_story_route in row.story_routes


def test_correlation_bindings_and_adapter_prefixes() -> None:
    for wire_id, expect in _STORY_TTL_EXPECT.items():
        row = row_for_wire_id(wire_id)
        assert row.correlation_kind == expect["correlation_kind"]
        assert row.correlation_bindings == expect["correlation_bindings"]
        assert row.adapter_correlation_prefix == expect["adapter_correlation_prefix"]

    alias = row_for_wire_id("OVERTAKEN")
    assert alias.correlation_kind == "none"
    assert alias.correlation_bindings == ()
    assert alias.closing_story_routes == ()
    assert alias.fallback_story_route is None
    assert alias.adapter_correlation_prefix is None


def test_outcome_ttl_matches_policy_catalog() -> None:
    policies = {
        str(row["id"]): int(row["ttlMs"])
        for row in json.loads(packaged_schema_bytes("beat-catalog.json"))["policies"]
    }
    for wire_id, expect in _STORY_TTL_EXPECT.items():
        row = row_for_wire_id(wire_id)
        assert row.policy_id == expect["policy_id"]
        assert row.outcome_ttl_ms == expect["outcome_ttl_ms"]
        assert row.outcome_ttl_ms == policies[str(row.policy_id)]
        assert row.policy_id in SELF_CONTAINED_POLICIES
        assert row.self_contained is True

    alias = row_for_wire_id("OVERTAKEN")
    assert alias.policy_id is None
    assert alias.outcome_ttl_ms is None
    assert alias.self_contained is False
