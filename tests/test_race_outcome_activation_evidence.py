"""#274 closeout: self-contained, evidence, fail-soft, legacy disposition."""

from __future__ import annotations

from irswitch.contracts.race_outcome_activation_evidence import (
    creatable_self_contained_wire_ids,
    race_outcome_activation_evidence,
    remaining_legacy_disposition,
)
from irswitch.contracts.race_outcome_family_map import (
    SELF_CONTAINED_POLICIES,
    race_outcome_family_rows,
    row_for_wire_id,
)
from irswitch.events.legacy_v2_shadow_compare import FAMILY_ROUTE, route_for_family


def test_creatable_race_outcomes_are_self_contained_without_spoken_opening() -> None:
    creatable = [row for row in race_outcome_family_rows() if row.can_create]
    assert creatable
    assert all(row.self_contained for row in creatable)
    assert all(row.policy_id in SELF_CONTAINED_POLICIES for row in creatable)
    assert set(creatable_self_contained_wire_ids()) == {row.wire_id for row in creatable}
    # Alias is not a speakable outcome and is not self-contained.
    assert row_for_wire_id("OVERTAKEN").self_contained is False


def test_per_family_coverage_semantic_and_latency_evidence() -> None:
    evidence = race_outcome_activation_evidence()
    by_wire = {row.wire_id: row for row in evidence}
    assert set(by_wire) == {row.wire_id for row in race_outcome_family_rows()}

    for wire_id, row in by_wire.items():
        if not row.can_create:
            assert row.migration_status == "legacy"
            assert row.verifier_pair_count == 0
            assert row.fail_soft_reason is None
            continue
        assert row.migration_status == "shadow"
        assert row.self_contained is True
        assert row.accept_pairs >= 1
        assert row.reject_pairs >= 1
        assert row.shadow_family in {"position", "session"}
        assert row.shadow_route == "shadow"
        assert row.compare_latency_ms is not None
        assert row.compare_latency_ms >= 0.0
        assert row.fail_soft_reason == "observation_failed"


def test_fail_soft_shadow_observation_and_legacy_rollback_surface() -> None:
    # Battle family remains the legacy rollback owner for non-migrated overtake chrome.
    assert FAMILY_ROUTE["battle"] == "legacy"
    assert route_for_family("battle") == "legacy"
    # Position/session are shadow-activated but observational only.
    assert FAMILY_ROUTE["position"] == "shadow"
    assert FAMILY_ROUTE["session"] == "shadow"
    disposition = remaining_legacy_disposition()
    assert "OVERTAKEN" in disposition
    assert "BATTLE_OVERTAKE" in disposition
