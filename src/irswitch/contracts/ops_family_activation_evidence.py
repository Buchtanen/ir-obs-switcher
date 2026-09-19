"""#276 closeout evidence for ops-family observational shadow activation.

Records per-wire coverage, EN pattern counts, invalidate/terminal reasons,
shadow routes and fail-soft observation outcomes without rewriting frozen
``docs/v2.0.0/machine/*`` hashes or cutting over live ``v2`` speech.
"""

from __future__ import annotations

from dataclasses import dataclass

from irswitch.contracts.ops_family_map import (
    OPS_WIRE_IDS,
    ops_family_rows,
    row_for_wire_id,
)
from irswitch.events.legacy_v2_shadow_compare import (
    family_for_event_type,
    observe_family_safely,
    route_for_family,
)


@dataclass(frozen=True, slots=True)
class OpsFamilyEvidence:
    wire_id: str
    migration_status: str
    can_create: bool
    en_pattern_count: int
    invalidate_reason_count: int
    terminal_reason_count: int
    shadow_family: str
    shadow_route: str
    compare_latency_ms: float | None
    fail_soft_reason: str | None


def ops_family_activation_evidence() -> tuple[OpsFamilyEvidence, ...]:
    """Collect closeout evidence for every ops-family wire id."""

    out: list[OpsFamilyEvidence] = []
    for wire_id in OPS_WIRE_IDS:
        row = row_for_wire_id(wire_id)
        shadow_family = family_for_event_type(wire_id)
        shadow_route = route_for_family(shadow_family)
        latency: float | None = None
        fail_soft: str | None = None
        if row.can_create:
            ok = observe_family_safely(
                family=shadow_family,
                observer=lambda fam=shadow_family, wid=wire_id: _timed_match(fam, wid),
            )
            latency = ok.latency_ms
            boom = observe_family_safely(
                family=shadow_family,
                observer=_boom,
            )
            fail_soft = boom.divergences[0].reason if boom.divergences else None
        out.append(
            OpsFamilyEvidence(
                wire_id=wire_id,
                migration_status=row.migration_status,
                can_create=row.can_create,
                en_pattern_count=len(row.en_pattern_ids),
                invalidate_reason_count=len(row.invalidate_reasons),
                terminal_reason_count=len(row.terminal_reasons),
                shadow_family=shadow_family,
                shadow_route=shadow_route,
                compare_latency_ms=latency,
                fail_soft_reason=fail_soft,
            )
        )
    return tuple(out)


def _boom() -> None:
    raise RuntimeError("forced ops shadow observation failure")


def _timed_match(family: str, wire_id: str):
    from irswitch.events.envelope import make_envelope
    from irswitch.events.legacy_v2_shadow_compare import compare_event_decisions

    envelope = make_envelope(event_type=wire_id, phase="ENTER")
    return compare_event_decisions(
        family=family,
        legacy_event_type=wire_id,
        legacy_phase="ENTER",
        envelope=envelope,
    )


def ops_family_activation_evidence_is_complete() -> bool:
    """Slice 7 helper: every ops wire is observational shadow with fail-soft evidence."""

    items = ops_family_activation_evidence()
    if len(items) != len(OPS_WIRE_IDS):
        return False
    if {row.wire_id for row in ops_family_rows()} != set(OPS_WIRE_IDS):
        return False
    for item in items:
        if item.migration_status != "shadow":
            return False
        if item.shadow_route != "shadow":
            return False
        if item.shadow_family not in {"pit", "incident", "session"}:
            return False
        if item.en_pattern_count < 4:
            return False
        if item.invalidate_reason_count < 1:
            return False
        if item.can_create and item.fail_soft_reason != "observation_failed":
            return False
    return True


def remaining_legacy_disposition() -> dict[str, str]:
    """Human-readable disposition for families left outside ops shadow creatable set."""

    return {
        "battle": "unmigrated FAMILY_ROUTE owner; not part of #276 ops inventory",
        "bio": "unmigrated FAMILY_ROUTE owner; not part of #276 ops inventory",
        "live v2 speech": "deferred until cutover (#279); observational shadow only",
    }
