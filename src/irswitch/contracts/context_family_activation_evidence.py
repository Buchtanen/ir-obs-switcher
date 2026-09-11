"""#277 closeout evidence for context-family inventory shadow readiness.

Records per-wire coverage, EN pattern counts, invalidate/terminal reasons and
compare-harness family/route *observation* (informational only) without
flipping ``FAMILY_ROUTE``, rewriting frozen ``docs/v2.0.0/machine/*`` hashes,
or cutting over live ``v2`` speech.
"""

from __future__ import annotations

from dataclasses import dataclass

from irswitch.contracts.context_family_map import (
    CONTEXT_EN_PATTERN_IDS_BY_BEAT_ID,
    CONTEXT_WIRE_IDS,
    context_family_rows,
    context_family_shadow_readiness_is_complete,
    row_for_wire_id,
)
from irswitch.events.legacy_v2_shadow_compare import (
    FAMILY_ROUTE,
    family_for_event_type,
    route_for_family,
)


@dataclass(frozen=True, slots=True)
class ContextFamilyEvidence:
    wire_id: str
    migration_status: str
    can_create: bool
    en_pattern_count: int
    invalidate_reason_count: int
    terminal_reason_count: int
    observed_family: str
    observed_route: str


def context_family_activation_evidence() -> tuple[ContextFamilyEvidence, ...]:
    """Collect inventory shadow evidence for every context-family wire id."""

    out: list[ContextFamilyEvidence] = []
    for wire_id in CONTEXT_WIRE_IDS:
        row = row_for_wire_id(wire_id)
        pattern_ids: list[str] = []
        for beat_id in row.branch_beat_ids:
            pattern_ids.extend(CONTEXT_EN_PATTERN_IDS_BY_BEAT_ID.get(beat_id, ()))
        observed_family = family_for_event_type(wire_id)
        observed_route = route_for_family(observed_family)
        out.append(
            ContextFamilyEvidence(
                wire_id=wire_id,
                migration_status=row.migration_status,
                can_create=row.can_create,
                en_pattern_count=len(pattern_ids),
                invalidate_reason_count=len(row.invalidate_reasons),
                terminal_reason_count=len(row.terminal_reasons),
                observed_family=observed_family,
                observed_route=observed_route,
            )
        )
    return tuple(out)


def context_family_activation_evidence_is_complete() -> bool:
    """Slice 7 helper: inventory shadow ready; FAMILY_ROUTE intentionally unchanged."""

    if not context_family_shadow_readiness_is_complete():
        return False
    items = context_family_activation_evidence()
    if len(items) != len(CONTEXT_WIRE_IDS):
        return False
    if {row.wire_id for row in context_family_rows()} != set(CONTEXT_WIRE_IDS):
        return False
    # Guardrail: do not silently require route ownership for context wires.
    if FAMILY_ROUTE.get("bio") != "legacy":
        return False
    for item in items:
        if item.migration_status != "shadow":
            return False
        if item.en_pattern_count < 4:
            return False
        if item.invalidate_reason_count < 1:
            return False
        # Informational only — most wires remain unknown/legacy under the harness.
        if item.observed_family not in {"session", "unknown", "bio"}:
            return False
    return True


def remaining_legacy_disposition() -> dict[str, str]:
    """Human-readable disposition for surfaces left outside inventory shadow."""

    return {
        "bio FAMILY_ROUTE": "stays legacy; HR pressure is style inventory only (#277)",
        "battle FAMILY_ROUTE": "unmigrated; not part of #277 context inventory",
        "compare harness ownership": (
            "most context wires still resolve to unknown; no FAMILY_ROUTE flip in #277"
        ),
        "beat-only fillers": (
            "out/in/garage/lobby/quiet stay beat-only (no freeze wires); silence ok"
        ),
        "live v2 speech": "deferred until cutover (#279); inventory shadow only",
    }
