"""#276 Slice 7 — ops family observational shadow activation evidence."""

from __future__ import annotations

from irswitch.contracts.ops_family_activation_evidence import (
    ops_family_activation_evidence,
    ops_family_activation_evidence_is_complete,
    remaining_legacy_disposition,
)
from irswitch.contracts.ops_family_map import OPS_WIRE_IDS
from irswitch.events.legacy_v2_shadow_compare import FAMILY_ROUTE, unmigrated_families


def test_ops_family_activation_evidence_is_complete() -> None:
    assert ops_family_activation_evidence_is_complete() is True
    items = ops_family_activation_evidence()
    assert len(items) == len(OPS_WIRE_IDS) == 13
    for item in items:
        assert item.migration_status == "shadow"
        assert item.shadow_route == "shadow"
        assert item.shadow_family in {"pit", "incident", "session"}
        assert item.en_pattern_count >= 4
        assert item.invalidate_reason_count >= 1
        assert item.fail_soft_reason == "observation_failed"


def test_ops_family_route_table_flips_pit_and_incident_to_shadow() -> None:
    assert FAMILY_ROUTE["pit"] == "shadow"
    assert FAMILY_ROUTE["incident"] == "shadow"
    assert FAMILY_ROUTE["session"] == "shadow"  # shared with #274 finish/checkered
    unmigrated = unmigrated_families()
    assert "pit" not in unmigrated
    assert "incident" not in unmigrated
    assert "battle" in unmigrated
    assert "bio" in unmigrated


def test_remaining_legacy_disposition_documents_non_ops_owners() -> None:
    disposition = remaining_legacy_disposition()
    assert "battle" in disposition
    assert "bio" in disposition
    assert "live v2 speech" in disposition
