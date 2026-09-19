"""#275 closeout evidence for timing-family inventory."""

from __future__ import annotations

from irswitch.contracts.timing_family_closeout_evidence import (
    TimingFamilyEvidence,
    remaining_legacy_disposition,
    timing_family_closeout_evidence,
    timing_family_closeout_evidence_is_complete,
)
from irswitch.contracts.timing_family_map import TIMING_WIRE_IDS


def test_timing_family_closeout_evidence_is_complete() -> None:
    assert timing_family_closeout_evidence_is_complete() is True


def test_closeout_evidence_covers_every_timing_wire() -> None:
    evidence = timing_family_closeout_evidence()
    assert len(evidence) == len(TIMING_WIRE_IDS)
    assert all(isinstance(item, TimingFamilyEvidence) for item in evidence)
    assert {item.wire_id for item in evidence} == set(TIMING_WIRE_IDS)


def test_closeout_evidence_records_latency_and_fail_soft() -> None:
    for item in timing_family_closeout_evidence():
        assert item.migration_status == "shadow"
        assert item.can_create is True
        assert item.en_pattern_count >= 4
        assert item.replay_case_count >= 1
        assert item.shadow_family
        assert item.shadow_route == "shadow"
        assert item.compare_latency_ms is not None and item.compare_latency_ms >= 0
        assert item.fail_soft_reason == "observation_failed"


def test_remaining_legacy_disposition_covers_inventory() -> None:
    disposition = remaining_legacy_disposition()
    assert set(disposition) == set(TIMING_WIRE_IDS)
    assert all(
        "shadow" in text.lower() or "deferred" in text.lower() for text in disposition.values()
    )
