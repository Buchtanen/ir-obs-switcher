"""#274 closeout evidence for race-outcome shadow activation.

Records per-family coverage, verifier-pair counts, shadow routes and
fail-soft observation outcomes without rewriting frozen machine hashes
or flipping live speech ownership.
"""

from __future__ import annotations

from dataclasses import dataclass

from irswitch.contracts.race_outcome_family_map import (
    RACE_OUTCOME_WIRE_IDS,
    race_outcome_family_rows,
    row_for_wire_id,
)
from irswitch.contracts.race_outcome_verifier_pairs import pairs_for_wire_id
from irswitch.events.legacy_v2_shadow_compare import (
    family_for_event_type,
    observe_family_safely,
    route_for_family,
)


@dataclass(frozen=True, slots=True)
class RaceOutcomeFamilyEvidence:
    wire_id: str
    migration_status: str
    can_create: bool
    self_contained: bool
    verifier_pair_count: int
    accept_pairs: int
    reject_pairs: int
    shadow_family: str | None
    shadow_route: str | None
    compare_latency_ms: float | None
    fail_soft_reason: str | None


def _shadow_family_for_wire(wire_id: str) -> str | None:
    if wire_id == "OVERTAKEN":
        return family_for_event_type("OVERTAKEN")
    return family_for_event_type(wire_id)


def race_outcome_activation_evidence() -> tuple[RaceOutcomeFamilyEvidence, ...]:
    """Collect closeout evidence for every race-outcome wire id."""

    out: list[RaceOutcomeFamilyEvidence] = []
    for wire_id in RACE_OUTCOME_WIRE_IDS:
        row = row_for_wire_id(wire_id)
        pairs = pairs_for_wire_id(wire_id)
        shadow_family = _shadow_family_for_wire(wire_id)
        shadow_route = route_for_family(shadow_family) if shadow_family else None
        latency: float | None = None
        fail_soft: str | None = None
        if row.can_create and shadow_family is not None:
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
            RaceOutcomeFamilyEvidence(
                wire_id=wire_id,
                migration_status=row.migration_status,
                can_create=row.can_create,
                self_contained=row.self_contained,
                verifier_pair_count=len(pairs),
                accept_pairs=sum(1 for p in pairs if p.expect_accepted),
                reject_pairs=sum(1 for p in pairs if not p.expect_accepted),
                shadow_family=shadow_family,
                shadow_route=shadow_route,
                compare_latency_ms=latency,
                fail_soft_reason=fail_soft,
            )
        )
    return tuple(out)


def _boom() -> None:
    raise RuntimeError("forced shadow observation failure")


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


def creatable_self_contained_wire_ids() -> tuple[str, ...]:
    return tuple(
        row.wire_id for row in race_outcome_family_rows() if row.can_create and row.self_contained
    )


def remaining_legacy_disposition() -> dict[str, str]:
    """Human-readable disposition for wires/aliases left outside shadow creatable set."""

    return {
        "OVERTAKEN": "compatibility alias; reject as creatable input; migrate later to POSITION_LOST + cause",
        "BATTLE_OVERTAKE": "stays on battle family (not race-outcome inventory); substring trap preserved",
        "visual-only battle chrome": "unchanged; not part of race-outcome speakable inventory",
    }
