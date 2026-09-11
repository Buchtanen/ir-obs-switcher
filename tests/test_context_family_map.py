"""#277 Slice 1 — context family map (session/stream leftovers)."""

from __future__ import annotations

import dataclasses

import pytest

from irswitch.contracts.context_family_map import (
    CONTEXT_OWNED_ELSEWHERE,
    CONTEXT_SESSION_PHASE_ORDER,
    CONTEXT_SESSION_WIRE_IDS,
    CONTEXT_WIRE_IDS,
    ENTER_CAR_BRANCH_BEAT_IDS,
    ENTER_CAR_PRIMARY_BEAT_ID,
    ContextFamilyRow,
    context_family_rows,
    context_session_phase_order_is_monotonic,
    context_session_stories_have_explicit_invalidation,
    enter_car_branch_beats_are_documented,
    migration_status_by_wire_id,
    owned_elsewhere_session_wires_are_documented,
    row_for_wire_id,
    rows_by_migration_status,
)
from irswitch.contracts.coverage_matrix import can_create_event_opportunity
from irswitch.contracts.ops_family_map import OPS_WIRE_IDS
from irswitch.contracts.primitives import ContractViolation
from irswitch.contracts.timing_family_map import TIMING_WIRE_IDS

_EXPECT = {
    "STREAM_START": {
        "beat_id": "stream.started",
        "beat_role": "opening",
        "policy_id": "critical",
        "outcome_ttl_ms": 45000,
        "lifecycle_phase": "stream_start",
        "scope_kind": "stream_lifecycle",
        "legacy_node_id": "stream_start",
        "realization_family": "stream.lifecycle",
        "branch_beat_ids": ("stream.started",),
        "terminal": False,
    },
    "SESSION_PREVIEW": {
        "beat_id": "session.preview.next",
        "beat_role": "bridge",
        "policy_id": "context",
        "outcome_ttl_ms": 20000,
        "lifecycle_phase": "preview",
        "scope_kind": "session_preview",
        "legacy_node_id": "session_preview",
        "realization_family": "session.preview",
        "branch_beat_ids": ("session.preview.next",),
        "terminal": False,
    },
    "ENTER_CAR": {
        "beat_id": "session.enter_car.practice",
        "beat_role": "vehicle",
        "policy_id": "context",
        "outcome_ttl_ms": 20000,
        "lifecycle_phase": "enter_car",
        "scope_kind": "enter_car",
        "legacy_node_id": "enter_car",
        "realization_family": "session.vehicle",
        "branch_beat_ids": ENTER_CAR_BRANCH_BEAT_IDS,
        "terminal": False,
    },
    "FINAL_LAP": {
        "beat_id": "session.final_lap",
        "beat_role": "escalation",
        "policy_id": "critical",
        "outcome_ttl_ms": 45000,
        "lifecycle_phase": "final_lap",
        "scope_kind": "final_lap",
        "legacy_node_id": "final_lap",
        "realization_family": "session.final_lap",
        "branch_beat_ids": ("session.final_lap",),
        "terminal": True,
    },
}


def test_context_family_rows_cover_session_leftover_inventory() -> None:
    rows = context_family_rows()
    assert tuple(row.wire_id for row in rows) == CONTEXT_WIRE_IDS
    assert (
        CONTEXT_WIRE_IDS
        == CONTEXT_SESSION_WIRE_IDS
        == (
            "STREAM_START",
            "SESSION_PREVIEW",
            "ENTER_CAR",
            "FINAL_LAP",
        )
    )
    assert len(rows) == 4


def test_every_context_row_is_legacy_before_shadow_cutover() -> None:
    assert migration_status_by_wire_id() == dict.fromkeys(CONTEXT_WIRE_IDS, "legacy")
    assert len(rows_by_migration_status("legacy")) == 4
    assert rows_by_migration_status("shadow") == ()
    assert rows_by_migration_status("v2") == ()


def test_context_rows_match_freeze_and_beat_catalog() -> None:
    for row in context_family_rows():
        expect = _EXPECT[row.wire_id]
        assert row.beat_id == expect["beat_id"]
        assert row.beat_role == expect["beat_role"]
        assert row.policy_id == expect["policy_id"]
        assert row.outcome_ttl_ms == expect["outcome_ttl_ms"]
        assert row.lifecycle_phase == expect["lifecycle_phase"]
        assert row.scope_kind == expect["scope_kind"]
        assert row.legacy_node_id == expect["legacy_node_id"]
        assert row.realization_family == expect["realization_family"]
        assert row.branch_beat_ids == expect["branch_beat_ids"]
        assert row.event_class == "speakable"
        assert row.can_create is can_create_event_opportunity(row.wire_id)
        assert row.invalidate_reasons
        assert bool(row.terminal_reasons) is expect["terminal"]
        assert row.migration_status == "legacy"
        assert row.emitter_module
        assert row.adapter_module
        assert row.notes


def test_context_wires_do_not_overlap_timing_or_ops_inventory() -> None:
    overlap = set(CONTEXT_WIRE_IDS) & set(TIMING_WIRE_IDS) & set(OPS_WIRE_IDS)
    assert overlap == set()
    assert set(CONTEXT_WIRE_IDS).isdisjoint(set(TIMING_WIRE_IDS))
    assert set(CONTEXT_WIRE_IDS).isdisjoint(set(OPS_WIRE_IDS))
    assert set(CONTEXT_OWNED_ELSEWHERE).isdisjoint(set(CONTEXT_WIRE_IDS))


def test_context_session_phase_order_is_monotonic() -> None:
    assert CONTEXT_SESSION_PHASE_ORDER == (
        "stream_start",
        "preview",
        "enter_car",
        "final_lap",
    )
    assert context_session_phase_order_is_monotonic() is True


def test_enter_car_branch_beats_are_documented() -> None:
    assert ENTER_CAR_PRIMARY_BEAT_ID == "session.enter_car.practice"
    assert ENTER_CAR_BRANCH_BEAT_IDS == (
        "session.enter_car.practice",
        "session.enter_car.qualifying",
        "session.enter_car.race",
    )
    assert enter_car_branch_beats_are_documented() is True


def test_context_session_stories_have_explicit_invalidation() -> None:
    assert context_session_stories_have_explicit_invalidation() is True
    final_lap = row_for_wire_id("FINAL_LAP")
    assert "final_lap_observed" in final_lap.terminal_reasons
    assert "checkered" in final_lap.notes.lower()


def test_owned_elsewhere_session_wires_are_documented() -> None:
    assert owned_elsewhere_session_wires_are_documented() is True
    assert CONTEXT_OWNED_ELSEWHERE["SESSION_INTRO_PRACTICE"] == "timing_family_map"
    assert CONTEXT_OWNED_ELSEWHERE["SESSION_WRAP"] == "ops_family_map"


def test_row_for_unknown_wire_raises() -> None:
    with pytest.raises(ContractViolation, match="unknown context wire id"):
        row_for_wire_id("NOT_A_CONTEXT_WIRE")


def test_context_family_row_is_frozen() -> None:
    row = row_for_wire_id("STREAM_START")
    assert isinstance(row, ContextFamilyRow)
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.migration_status = "v2"  # type: ignore[misc]
