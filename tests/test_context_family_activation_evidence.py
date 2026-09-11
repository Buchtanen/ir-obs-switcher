"""#277 Slice 7 — context family inventory shadow activation evidence."""

from __future__ import annotations

from irswitch.contracts.context_family_activation_evidence import (
    context_family_activation_evidence,
    context_family_activation_evidence_is_complete,
    remaining_legacy_disposition,
)
from irswitch.contracts.context_family_map import CONTEXT_WIRE_IDS
from irswitch.events.legacy_v2_shadow_compare import FAMILY_ROUTE, unmigrated_families


def test_context_family_activation_evidence_is_complete() -> None:
    assert context_family_activation_evidence_is_complete() is True
    items = context_family_activation_evidence()
    assert len(items) == len(CONTEXT_WIRE_IDS) == 10
    for item in items:
        assert item.migration_status == "shadow"
        assert item.en_pattern_count >= 4
        assert item.invalidate_reason_count >= 1
        assert item.observed_family in {"session", "unknown", "bio"}


def test_context_family_route_table_stays_unflipped() -> None:
    """Slice 7 deliberately does not flip FAMILY_ROUTE for context wires."""

    assert FAMILY_ROUTE["bio"] == "legacy"
    assert FAMILY_ROUTE["session"] == "shadow"  # shared; not a #277 flip
    assert FAMILY_ROUTE["battle"] == "legacy"
    unmigrated = unmigrated_families()
    assert "bio" in unmigrated
    assert "battle" in unmigrated
    # No dedicated context/weather/filler family key was introduced.
    assert "weather" not in FAMILY_ROUTE
    assert "filler" not in FAMILY_ROUTE
    assert "context" not in FAMILY_ROUTE


def test_remaining_legacy_disposition_documents_deferred_surfaces() -> None:
    disposition = remaining_legacy_disposition()
    assert "bio FAMILY_ROUTE" in disposition
    assert "live v2 speech" in disposition
    assert "compare harness ownership" in disposition
    assert "beat-only fillers" in disposition
