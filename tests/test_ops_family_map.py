"""#276 Slices 1-6 — ops family map (pit/incident/flags/closeout + unknown/tow/teleport + EN patterns)."""

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
    OPS_CLOSEOUT_WIRE_IDS,
    OPS_INCIDENT_WIRE_IDS,
    OPS_PIT_WIRE_IDS,
    OPS_TELEPORT_OUTCOME_REASON_IDS,
    OPS_TOW_OUTCOME_REASON_IDS,
    OPS_UNKNOWN_OUTCOME_REASON_IDS,
    OPS_WIRE_IDS,
    PIT_CYCLE_PHASE_ORDER,
    PIT_TERMINAL_WIRE_IDS,
    SESSION_WRAP_BRANCH_BEAT_IDS,
    SESSION_WRAP_PRIMARY_BEAT_ID,
    OpsFamilyRow,
    closeout_stories_are_separated,
    en_patterns_and_tts_slots_are_curated,
    incident_branch_beats_are_documented,
    incident_cycle_phase_order_is_monotonic,
    incident_stories_have_explicit_terminals,
    migration_status_by_wire_id,
    ops_family_rows,
    pit_cycle_phase_order_is_monotonic,
    pit_cycle_stories_have_explicit_terminals,
    row_for_wire_id,
    rows_by_migration_status,
    session_flag_branch_beats_are_documented,
    session_wrap_branch_beats_are_documented,
    unknown_tow_teleport_outcomes_are_defined,
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
        "incident_phase": None,
        "scope_kind": "pit_cycle",
        "legacy_node_id": "pit_entry",
        "story_routes": ("pit_cycle", "single_result"),
        "realization_family": "pit.lifecycle",
        "terminal": False,
        "branch_beat_ids": ("pit.entry",),
    },
    "PIT_LANE": {
        "beat_id": "pit.lane",
        "beat_role": "update",
        "policy_id": "live_story",
        "outcome_ttl_ms": 10000,
        "pit_phase": "lane",
        "incident_phase": None,
        "scope_kind": "pit_cycle",
        "legacy_node_id": None,
        "story_routes": ("pit_cycle", "single_result"),
        "realization_family": "pit.lifecycle",
        "terminal": False,
        "branch_beat_ids": ("pit.lane",),
    },
    "PIT_STOPPED": {
        "beat_id": "pit.stopped",
        "beat_role": "update",
        "policy_id": "live_story",
        "outcome_ttl_ms": 10000,
        "pit_phase": "stopped",
        "incident_phase": None,
        "scope_kind": "pit_cycle",
        "legacy_node_id": "pit_stopped",
        "story_routes": ("pit_cycle", "single_result"),
        "realization_family": "pit.lifecycle",
        "terminal": False,
        "branch_beat_ids": ("pit.stopped",),
    },
    "PIT_RELEASED": {
        "beat_id": "pit.released",
        "beat_role": "update",
        "policy_id": "live_story",
        "outcome_ttl_ms": 10000,
        "pit_phase": "released",
        "incident_phase": None,
        "scope_kind": "pit_cycle",
        "legacy_node_id": None,
        "story_routes": ("pit_cycle", "single_result"),
        "realization_family": "pit.lifecycle",
        "terminal": False,
        "branch_beat_ids": ("pit.released",),
    },
    "PIT_EXIT": {
        "beat_id": "pit.exit",
        "beat_role": "closure",
        "policy_id": "result",
        "outcome_ttl_ms": 30000,
        "pit_phase": "exit",
        "incident_phase": None,
        "scope_kind": "pit_cycle",
        "legacy_node_id": None,
        "story_routes": ("pit_cycle", "single_result"),
        "realization_family": "pit.lifecycle",
        "terminal": True,
        "branch_beat_ids": ("pit.exit",),
    },
    "PIT_OUTCOME": {
        "beat_id": "pit.outcome",
        "beat_role": "outcome",
        "policy_id": "result",
        "outcome_ttl_ms": 30000,
        "pit_phase": "outcome",
        "incident_phase": None,
        "scope_kind": "pit_outcome",
        "legacy_node_id": "pit_outcome",
        "story_routes": ("pit_cycle", "single_result"),
        "realization_family": "pit.outcome",
        "terminal": True,
        "branch_beat_ids": ("pit.outcome",),
    },
    "INCIDENT": {
        "beat_id": "incident.off_track",
        "beat_role": "opening",
        "policy_id": "result",
        "outcome_ttl_ms": 30000,
        "pit_phase": None,
        "incident_phase": "event",
        "scope_kind": "incident_event",
        "legacy_node_id": "incident",
        "story_routes": ("incident", "single_result"),
        "realization_family": "incident.event",
        "terminal": False,
        "branch_beat_ids": ("incident.off_track", "incident.unclassified"),
    },
    "INCIDENT_AFTERMATH": {
        "beat_id": "incident.aftermath",
        "beat_role": "update",
        "policy_id": "context",
        "outcome_ttl_ms": 20000,
        "pit_phase": None,
        "incident_phase": "aftermath",
        "scope_kind": "incident_aftermath",
        "legacy_node_id": "incident_aftermath",
        "story_routes": ("incident", "single_result"),
        "realization_family": "incident.aftermath",
        "terminal": False,
        "branch_beat_ids": ("incident.aftermath",),
    },
    "BACK_UNDER_WAY": {
        "beat_id": "incident.recovery",
        "beat_role": "closure",
        "policy_id": "result",
        "outcome_ttl_ms": 30000,
        "pit_phase": None,
        "incident_phase": "recovery",
        "scope_kind": "incident_recovery",
        "legacy_node_id": "back_under_way",
        "story_routes": ("incident", "single_result"),
        "realization_family": "incident.recovery",
        "terminal": True,
        "branch_beat_ids": ("incident.recovery",),
    },
    "SESSION_FLAG": {
        "beat_id": "session.flag.yellow",
        "beat_role": "control",
        "policy_id": "critical",
        "outcome_ttl_ms": 45000,
        "pit_phase": None,
        "incident_phase": None,
        "scope_kind": "flag_control",
        "legacy_node_id": "session_flag_yellow",
        "story_routes": ("session_occurrence", "single_result"),
        "realization_family": "session.flag",
        "terminal": True,
        "branch_beat_ids": ("session.flag.yellow", "session.flag.green", "session.checkered"),
    },
    "SESSION_CHECKERED": {
        "beat_id": "session.checkered",
        "beat_role": "outcome",
        "policy_id": "critical",
        "outcome_ttl_ms": 45000,
        "pit_phase": None,
        "incident_phase": None,
        "scope_kind": "session_checkered",
        "legacy_node_id": "session_checkered",
        "story_routes": ("session_occurrence", "single_result"),
        "realization_family": "session.flag",
        "terminal": True,
        "branch_beat_ids": ("session.checkered",),
    },
    "FINISH": {
        "beat_id": "session.hero_finish",
        "beat_role": "outcome",
        "policy_id": "critical",
        "outcome_ttl_ms": 45000,
        "pit_phase": None,
        "incident_phase": None,
        "scope_kind": "hero_finish",
        "legacy_node_id": "finish",
        "story_routes": ("session_occurrence", "single_result"),
        "realization_family": "session.finish",
        "terminal": True,
        "branch_beat_ids": ("session.hero_finish",),
    },
    "SESSION_WRAP": {
        "beat_id": "session.wrap.practice",
        "beat_role": "closure",
        "policy_id": "result",
        "outcome_ttl_ms": 30000,
        "pit_phase": None,
        "incident_phase": None,
        "scope_kind": "session_wrap",
        "legacy_node_id": "session_wrap",
        "story_routes": ("session_occurrence", "single_result"),
        "realization_family": "session.wrap",
        "terminal": True,
        "branch_beat_ids": (
            "session.wrap.practice",
            "session.wrap.qualifying",
            "session.wrap.race",
        ),
    },
}


def test_ops_family_rows_cover_full_ops_inventory() -> None:
    rows = ops_family_rows()
    assert tuple(row.wire_id for row in rows) == OPS_WIRE_IDS
    assert len(rows) == 13
    assert all(isinstance(row, OpsFamilyRow) for row in rows)


def test_every_ops_row_is_legacy_before_shadow_cutover() -> None:
    assert migration_status_by_wire_id() == dict.fromkeys(OPS_WIRE_IDS, "legacy")
    assert len(rows_by_migration_status("legacy")) == 13
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
            row.realization_family == beat["realization"]["family"] == expect["realization_family"]
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
    node_ids = (
        set(nodes)
        if isinstance(nodes, dict)
        else {(n if isinstance(n, str) else n["id"]) for n in nodes}
    )
    for row in ops_family_rows():
        if row.legacy_node_id is None:
            continue
        assert row.legacy_node_id in node_ids


def test_emitters_and_adapters_are_documented() -> None:
    for row in ops_family_rows():
        assert "." in row.emitter_module and ":" in row.emitter_module
        assert "." in row.adapter_module and ":" in row.adapter_module
        assert row.policy_id in {"live_story", "result", "context", "critical"}
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


def test_incident_cycle_phase_order_is_monotonic() -> None:
    assert INCIDENT_CYCLE_PHASE_ORDER == ("event", "aftermath", "recovery")
    assert OPS_INCIDENT_WIRE_IDS == ("INCIDENT", "INCIDENT_AFTERMATH", "BACK_UNDER_WAY")
    assert incident_cycle_phase_order_is_monotonic() is True


def test_incident_stories_have_explicit_terminals() -> None:
    assert INCIDENT_TERMINAL_WIRE_IDS == frozenset({"BACK_UNDER_WAY"})
    assert incident_stories_have_explicit_terminals() is True


def test_incident_branch_beats_are_documented() -> None:
    assert INCIDENT_PRIMARY_BEAT_ID == "incident.off_track"
    assert INCIDENT_BRANCH_BEAT_IDS == (
        "incident.off_track",
        "incident.unclassified",
    )
    assert incident_branch_beats_are_documented() is True


def test_session_flag_branch_beats_are_documented() -> None:
    assert session_flag_branch_beats_are_documented() is True


def test_session_wrap_branch_beats_are_documented() -> None:
    assert SESSION_WRAP_PRIMARY_BEAT_ID == "session.wrap.practice"
    assert SESSION_WRAP_BRANCH_BEAT_IDS == (
        "session.wrap.practice",
        "session.wrap.qualifying",
        "session.wrap.race",
    )
    assert session_wrap_branch_beats_are_documented() is True


def test_closeout_stories_are_separated() -> None:
    assert OPS_CLOSEOUT_WIRE_IDS == (
        "SESSION_CHECKERED",
        "FINISH",
        "SESSION_WRAP",
    )
    assert closeout_stories_are_separated() is True


def test_unknown_tow_teleport_outcomes_are_defined() -> None:
    assert "unknown_exit_explicit" in OPS_UNKNOWN_OUTCOME_REASON_IDS
    assert "hero_towing" in OPS_TOW_OUTCOME_REASON_IDS
    assert "hero_teleport" in OPS_TELEPORT_OUTCOME_REASON_IDS
    assert unknown_tow_teleport_outcomes_are_defined() is True
    for row in ops_family_rows():
        assert "hero_teleport" in row.invalidate_reasons
        if row.terminal_reasons:
            assert OPS_UNKNOWN_OUTCOME_REASON_IDS & set(row.terminal_reasons)
    aftermath = row_for_wire_id("INCIDENT_AFTERMATH")
    recovery = row_for_wire_id("BACK_UNDER_WAY")
    assert OPS_TOW_OUTCOME_REASON_IDS & set(aftermath.invalidate_reasons)
    assert OPS_TOW_OUTCOME_REASON_IDS & set(recovery.invalidate_reasons)
    assert OPS_TELEPORT_OUTCOME_REASON_IDS & set(recovery.invalidate_reasons)


def test_row_for_unknown_wire_raises() -> None:
    with pytest.raises(ContractViolation, match="unknown ops wire id"):
        row_for_wire_id("NOT_AN_OPS_WIRE")


def test_ops_family_row_is_frozen() -> None:
    row = row_for_wire_id("PIT_ENTRY")
    assert isinstance(row, OpsFamilyRow)
    with pytest.raises(dataclasses.FrozenInstanceError):
        row.migration_status = "v2"  # type: ignore[misc]


def test_en_patterns_and_tts_slots_are_curated() -> None:
    assert en_patterns_and_tts_slots_are_curated() is True
    for row in ops_family_rows():
        assert len(row.en_pattern_ids) >= 4
        assert len(row.en_claim_surfaces) >= 4
        assert row.tts_slot_formats == ("subjectSurface", "requiredClaimSurface")
        assert row.beat_id is not None
        assert all(pid.startswith(f"{row.beat_id}:") for pid in row.en_pattern_ids)
        for surface in row.en_claim_surfaces:
            lowered = surface.lower()
            assert not any(token in lowered for token in row.en_forbidden_tokens)


def test_ops_en_pattern_ids_match_catalog_cards() -> None:
    cards = {
        str(row["id"]): row
        for row in json.loads(packaged_schema_bytes("realization-pattern-cards.json"))["cards"]
    }
    for row in ops_family_rows():
        assert len(row.en_pattern_ids) >= 4
        for pattern_id in row.en_pattern_ids:
            card = cards[pattern_id]
            assert card["beatId"] == row.beat_id
            assert card["family"] == row.realization_family
            assert card["enabled"] is True
            assert card["auditedLanguage"] == "en"


def test_closeout_en_claim_surfaces_are_adversarially_disjoint() -> None:
    checkered = row_for_wire_id("SESSION_CHECKERED")
    finish = row_for_wire_id("FINISH")
    wrap = row_for_wire_id("SESSION_WRAP")
    assert set(checkered.en_claim_surfaces).isdisjoint(set(finish.en_claim_surfaces))
    assert set(finish.en_claim_surfaces).isdisjoint(set(wrap.en_claim_surfaces))
    assert set(checkered.en_claim_surfaces).isdisjoint(set(wrap.en_claim_surfaces))
    # Finish keeps observed finish-position wording; wrap must not.
    assert all("p{finishposition}" in s.lower() for s in finish.en_claim_surfaces)
    assert not any("p{finishposition}" in s.lower() for s in wrap.en_claim_surfaces)
    assert not any("p{finishposition}" in s.lower() for s in checkered.en_claim_surfaces)


def test_pit_en_surfaces_are_not_race_finish() -> None:
    for wire_id in OPS_PIT_WIRE_IDS:
        row = row_for_wire_id(wire_id)
        assert row.en_forbidden_tokens
        for surface in row.en_claim_surfaces:
            lowered = surface.lower()
            assert "wins the race" not in lowered
            assert "finishes p" not in lowered
            assert not any(token in lowered for token in row.en_forbidden_tokens)


def test_session_flag_en_surfaces_stay_yellow_primary() -> None:
    flag = row_for_wire_id("SESSION_FLAG")
    assert flag.beat_id == "session.flag.yellow"
    blob = " ".join(flag.en_claim_surfaces).lower()
    assert "yellow" in blob
    assert "green flag" not in blob
    assert "checkered" not in blob
    for surface in flag.en_claim_surfaces:
        lowered = surface.lower()
        assert not any(token in lowered for token in flag.en_forbidden_tokens)


def test_incident_en_surfaces_do_not_invent_contact_or_tow() -> None:
    incident = row_for_wire_id("INCIDENT")
    blob = " ".join(incident.en_claim_surfaces).lower()
    assert "off track" in blob or "racing surface" in blob or "paved surface" in blob
    assert "contact" not in blob
    assert "tow" not in blob
    for surface in incident.en_claim_surfaces:
        lowered = surface.lower()
        assert not any(token in lowered for token in incident.en_forbidden_tokens)
