"""#275 closeout evidence for timing-family migration inventory.

Records per-family coverage, restart/rewind replay counts, shadow/legacy
routes, compare latency and fail-soft observation outcomes without
rewriting frozen ``docs/v2.0.0/machine/*`` hashes or flipping
``FAMILY_ROUTE`` / live speech ownership.
"""

from __future__ import annotations

from dataclasses import dataclass

from irswitch.contracts.timing_family_map import (
    TIMING_WIRE_IDS,
    row_for_wire_id,
    timing_family_rows,
)
from irswitch.contracts.timing_family_replay_cases import cases_for_wire_id
from irswitch.events.legacy_v2_shadow_compare import (
    family_for_event_type,
    observe_family_safely,
    route_for_family,
)


@dataclass(frozen=True, slots=True)
class TimingFamilyEvidence:
    wire_id: str
    migration_status: str
    can_create: bool
    requires_active_lineage: bool
    en_pattern_count: int
    replay_case_count: int
    shadow_family: str | None
    shadow_route: str | None
    compare_latency_ms: float | None
    fail_soft_reason: str | None


def _shadow_family_for_wire(wire_id: str) -> str | None:
    return family_for_event_type(wire_id)


def timing_family_closeout_evidence() -> tuple[TimingFamilyEvidence, ...]:
    """Collect closeout evidence for every timing-family wire id."""

    out: list[TimingFamilyEvidence] = []
    for wire_id in TIMING_WIRE_IDS:
        row = row_for_wire_id(wire_id)
        shadow_family = _shadow_family_for_wire(wire_id)
        if shadow_family is None:
            shadow_family = "unknown"
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
            TimingFamilyEvidence(
                wire_id=wire_id,
                migration_status=row.migration_status,
                can_create=row.can_create,
                requires_active_lineage=row.requires_active_lineage,
                en_pattern_count=len(row.en_pattern_ids),
                replay_case_count=len(cases_for_wire_id(wire_id)),
                shadow_family=shadow_family,
                shadow_route=shadow_route,
                compare_latency_ms=latency,
                fail_soft_reason=fail_soft,
            )
        )
    return tuple(out)


def _boom() -> None:
    raise RuntimeError("forced timing shadow observation failure")


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


def remaining_legacy_disposition() -> dict[str, str]:
    """Human-readable disposition for timing wires still outside v2 speech ownership."""

    return dict.fromkeys(
        TIMING_WIRE_IDS,
        "inventory+replay complete; remains legacy speak path until dedicated "
        "timing activation flips FAMILY_ROUTE / live ownership",
    )


def timing_family_closeout_evidence_is_complete() -> bool:
    """Closeout helper: every wire has coverage, replay, latency and fail-soft evidence."""

    rows = timing_family_rows()
    if len(rows) != len(TIMING_WIRE_IDS):
        return False
    evidence = timing_family_closeout_evidence()
    if {item.wire_id for item in evidence} != set(TIMING_WIRE_IDS):
        return False
    disposition = remaining_legacy_disposition()
    if set(disposition) != set(TIMING_WIRE_IDS):
        return False
    for item in evidence:
        if item.migration_status != "legacy":
            return False
        if not item.can_create:
            return False
        if item.en_pattern_count < 4:
            return False
        if item.replay_case_count < 1:
            return False
        if item.shadow_family is None or item.shadow_route is None:
            return False
        if item.compare_latency_ms is None or item.compare_latency_ms < 0:
            return False
        if item.fail_soft_reason != "observation_failed":
            return False
    return True
