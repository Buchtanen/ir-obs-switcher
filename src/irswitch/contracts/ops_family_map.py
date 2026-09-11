"""#276 ops family migration map — pit + incident inventory (Slices 1–2).

Maps pit-cycle and incident/aftermath/recovery wire identifiers onto legacy
emitters, adapters, beat/story routes, predicates, realization families,
policy TTL and tape channels.

Slices 1–2 record these families as ``legacy``. They do **not** rewrite frozen
``docs/v2.0.0/machine/*`` hashes and do **not** flip ``FAMILY_ROUTE``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from .coverage_matrix import can_create_event_opportunity
from .primitives import ContractViolation
from .resources import packaged_schema_bytes

MigrationStatus = Literal["legacy", "shadow", "v2"]
PitPhase = Literal["entry", "lane", "stopped", "released", "exit", "outcome"]
IncidentPhase = Literal["event", "aftermath", "recovery"]
ScopeKind = Literal[
    "pit_cycle",
    "pit_outcome",
    "incident_event",
    "incident_aftermath",
    "incident_recovery",
]

# Slice 1 inventory: pit entry → service → exit/outcome cycle.
OPS_PIT_WIRE_IDS: tuple[str, ...] = (
    "PIT_ENTRY",
    "PIT_LANE",
    "PIT_STOPPED",
    "PIT_RELEASED",
    "PIT_EXIT",
    "PIT_OUTCOME",
)

# Slice 2 inventory: incident opening → aftermath update → recovery closure.
OPS_INCIDENT_WIRE_IDS: tuple[str, ...] = (
    "INCIDENT",
    "INCIDENT_AFTERMATH",
    "BACK_UNDER_WAY",
)

OPS_WIRE_IDS: tuple[str, ...] = OPS_PIT_WIRE_IDS + OPS_INCIDENT_WIRE_IDS

# Historical pit-cycle phase order (service may visit lane and/or stopped/released).
PIT_CYCLE_PHASE_ORDER: tuple[PitPhase, ...] = (
    "entry",
    "lane",
    "stopped",
    "released",
    "exit",
    "outcome",
)

# Incident story order: opening → aftermath update → recovery closure.
INCIDENT_CYCLE_PHASE_ORDER: tuple[IncidentPhase, ...] = (
    "event",
    "aftermath",
    "recovery",
)

# Terminal pit-cycle wires (explicit close / outcome).
PIT_TERMINAL_WIRE_IDS: frozenset[str] = frozenset({"PIT_EXIT", "PIT_OUTCOME"})

# Terminal incident-cycle wire (explicit recovery closure).
INCIDENT_TERMINAL_WIRE_IDS: frozenset[str] = frozenset({"BACK_UNDER_WAY"})

# INCIDENT freeze binds two branch beats; primary matches off-track when classified.
INCIDENT_BRANCH_BEAT_IDS: tuple[str, ...] = (
    "incident.off_track",
    "incident.unclassified",
)
INCIDENT_PRIMARY_BEAT_ID = "incident.off_track"


@dataclass(frozen=True, slots=True)
class OpsFamilyRow:
    """One ops (pit/incident/flag/recovery) wire identifier and its inventory."""

    wire_id: str
    legacy_node_id: str | None
    race_event_name: str | None
    emitter_module: str
    adapter_module: str
    predicate_id: str | None
    actor_frame: str | None
    beat_id: str | None
    beat_role: str | None
    realization_family: str | None
    story_routes: tuple[str, ...]
    policy_id: str | None
    outcome_ttl_ms: int | None
    tape_channel: str
    event_class: str
    can_create: bool
    pit_phase: PitPhase | None
    incident_phase: IncidentPhase | None
    scope_kind: ScopeKind
    migration_status: MigrationStatus
    invalidate_reasons: tuple[str, ...]
    terminal_reasons: tuple[str, ...]
    branch_beat_ids: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True, slots=True)
class _StaticSource:
    legacy_node_id: str | None
    race_event_name: str | None
    emitter_module: str
    adapter_module: str
    pit_phase: PitPhase | None
    incident_phase: IncidentPhase | None
    scope_kind: ScopeKind
    invalidate_reasons: tuple[str, ...]
    terminal_reasons: tuple[str, ...]
    primary_beat_id: str | None = None
    notes: str = ""


_STATIC: dict[str, _StaticSource] = {
    "PIT_ENTRY": _StaticSource(
        legacy_node_id="pit_entry",
        race_event_name="pit_story",
        emitter_module="irswitch.events.pit:PitEmitter",
        adapter_module="irswitch.events.adapters.pit:pit_race_event_to_envelope",
        pit_phase="entry",
        incident_phase=None,
        scope_kind="pit_cycle",
        invalidate_reasons=(
            "stream_ended",
            "session_reset",
            "hero_teleport",
            "cycle_superseded",
        ),
        terminal_reasons=(),
        notes="Opens a pit cycle when hero enters pit road; not a service/outcome claim.",
    ),
    "PIT_LANE": _StaticSource(
        legacy_node_id=None,
        race_event_name="pit_story",
        emitter_module="irswitch.events.pit:PitEmitter",
        adapter_module="irswitch.events.adapters.pit:pit_race_event_to_envelope",
        pit_phase="lane",
        incident_phase=None,
        scope_kind="pit_cycle",
        invalidate_reasons=(
            "stream_ended",
            "session_reset",
            "hero_teleport",
            "cycle_superseded",
            "left_pit_road_without_stop",
        ),
        terminal_reasons=(),
        notes="In-lane transit update; must not claim stop/release/exit outcomes.",
    ),
    "PIT_STOPPED": _StaticSource(
        legacy_node_id="pit_stopped",
        race_event_name="pit_story",
        emitter_module="irswitch.events.pit:PitEmitter",
        adapter_module="irswitch.events.adapters.pit:pit_race_event_to_envelope",
        pit_phase="stopped",
        incident_phase=None,
        scope_kind="pit_cycle",
        invalidate_reasons=(
            "stream_ended",
            "session_reset",
            "hero_teleport",
            "cycle_superseded",
            "motion_resumed_without_release",
        ),
        terminal_reasons=(),
        notes="Stationary service update; must not invent service work without bound evidence.",
    ),
    "PIT_RELEASED": _StaticSource(
        legacy_node_id=None,
        race_event_name="pit_story",
        emitter_module="irswitch.events.pit:PitEmitter",
        adapter_module="irswitch.events.adapters.pit:pit_race_event_to_envelope",
        pit_phase="released",
        incident_phase=None,
        scope_kind="pit_cycle",
        invalidate_reasons=(
            "stream_ended",
            "session_reset",
            "hero_teleport",
            "cycle_superseded",
        ),
        terminal_reasons=(),
        notes="Released-from-box update; must not claim completed pit exit.",
    ),
    "PIT_EXIT": _StaticSource(
        legacy_node_id=None,
        race_event_name="pit_story",
        emitter_module="irswitch.events.pit:PitEmitter",
        adapter_module="irswitch.events.adapters.pit:pit_race_event_to_envelope",
        pit_phase="exit",
        incident_phase=None,
        scope_kind="pit_cycle",
        invalidate_reasons=("stream_ended", "session_reset", "hero_teleport"),
        terminal_reasons=(
            "left_pit_road",
            "cycle_closed_without_outcome",
            "superseded_by_outcome",
        ),
        notes="Closes the live pit-cycle phase when hero leaves pit road.",
    ),
    "PIT_OUTCOME": _StaticSource(
        legacy_node_id="pit_outcome",
        race_event_name="pit_story",
        emitter_module="irswitch.events.pit:PitEmitter",
        adapter_module="irswitch.events.adapters.pit:pit_race_event_to_envelope",
        pit_phase="outcome",
        incident_phase=None,
        scope_kind="pit_outcome",
        invalidate_reasons=("stream_ended", "session_reset", "hero_teleport"),
        terminal_reasons=(
            "position_delta_bound",
            "cycle_completed",
            "unknown_delta_explicit",
        ),
        notes="Terminal pit-cycle outcome; unknown position delta must stay explicit.",
    ),
    "INCIDENT": _StaticSource(
        legacy_node_id="incident",
        race_event_name="incident",
        emitter_module="irswitch.events.incident:IncidentEmitter",
        adapter_module="irswitch.events.adapters.exception_extra:incident_race_event_to_envelope",
        pit_phase=None,
        incident_phase="event",
        scope_kind="incident_event",
        invalidate_reasons=(
            "stream_ended",
            "session_reset",
            "hero_teleport",
            "cycle_superseded",
        ),
        terminal_reasons=(),
        primary_beat_id=INCIDENT_PRIMARY_BEAT_ID,
        notes=(
            "Opening incident wire; classify_incident_branch maps off_track|unknown onto branch beats "
            "incident.off_track|incident.unclassified. Missing surface evidence stays "
            "unclassified (unknown) — never invent contact or damage."
        ),
    ),
    "INCIDENT_AFTERMATH": _StaticSource(
        legacy_node_id="incident_aftermath",
        race_event_name=None,
        emitter_module="irswitch.race.aftermath:IncidentAftermathFsm",
        adapter_module="irswitch.race.aftermath:IncidentAftermathFsm",
        pit_phase=None,
        incident_phase="aftermath",
        scope_kind="incident_aftermath",
        invalidate_reasons=(
            "stream_ended",
            "session_reset",
            "hero_teleport",
            "cycle_superseded",
            "recovered_before_classify",
        ),
        terminal_reasons=(),
        notes=(
            "Aftermath update (stalled|rolling). Tow/off-track keep stalled; must not claim "
            "recovery or damage. Same-tick director prefers INCIDENT over aftermath."
        ),
    ),
    "BACK_UNDER_WAY": _StaticSource(
        legacy_node_id="back_under_way",
        race_event_name=None,
        emitter_module="irswitch.race.aftermath:IncidentAftermathFsm",
        adapter_module="irswitch.race.aftermath:IncidentAftermathFsm",
        pit_phase=None,
        incident_phase="recovery",
        scope_kind="incident_recovery",
        invalidate_reasons=("stream_ended", "session_reset", "hero_teleport"),
        terminal_reasons=(
            "recovered_motion_held",
            "cycle_closed",
            "unknown_motion_explicit",
        ),
        notes=(
            "Recovery closure after stalled aftermath; must not claim no-damage. Missing "
            "motion evidence stays stalled/unknown (no invention)."
        ),
    ),
}


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ContractViolation(f"{label} must be a JSON object")
    return value


def _rows(value: object, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ContractViolation(f"{label} must be a JSON object list")
    return value


def _load(name: str) -> dict[str, Any]:
    return _object(json.loads(packaged_schema_bytes(name)), name)


def _beat_index(beat_doc: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(row["id"]): row for row in _rows(beat_doc["beats"], "beats")}


def _policy_ttl(beat_doc: dict[str, Any]) -> dict[str, int]:
    out: dict[str, int] = {}
    for row in _rows(beat_doc["policies"], "policies"):
        out[str(row["id"])] = int(row["ttlMs"])
    return out


def _registry_row(registry: dict[str, Any], wire_id: str) -> dict[str, Any]:
    for row in _rows(registry["eventIdentifiers"], "eventIdentifiers"):
        if str(row["id"]) == wire_id:
            return row
    raise ContractViolation(f"unknown ops wire id: {wire_id}")


def _claim_meta(beat: dict[str, Any]) -> tuple[str | None, str | None]:
    claims = beat.get("claims")
    if not isinstance(claims, dict):
        return None, None
    required = claims.get("required")
    if not isinstance(required, list) or not required:
        return None, None
    first = required[0]
    if not isinstance(first, dict):
        return None, None
    predicate_id = str(first["id"]) if "id" in first else None
    actor_frame = str(first["actorFrame"]) if "actorFrame" in first else None
    return predicate_id, actor_frame


def _story_routes(beat: dict[str, Any]) -> tuple[str, ...]:
    routes = beat.get("storyRoutes")
    if not isinstance(routes, list) or any(not isinstance(item, str) for item in routes):
        raise ContractViolation(f"beat {beat.get('id')!r} storyRoutes must be strings")
    return tuple(routes)


def _resolve_beat_ids(
    wire_id: str,
    reg: dict[str, Any],
    static: _StaticSource,
) -> tuple[str, tuple[str, ...]]:
    beat_ids = reg.get("beatDefinitions")
    if not isinstance(beat_ids, list) or any(not isinstance(item, str) for item in beat_ids):
        raise ContractViolation(f"{wire_id} beatDefinitions must be a string list")
    if not beat_ids:
        raise ContractViolation(f"{wire_id} beatDefinitions must not be empty")
    branch = tuple(str(item) for item in beat_ids)
    if static.primary_beat_id is not None:
        if static.primary_beat_id not in branch:
            raise ContractViolation(
                f"{wire_id} primary beat {static.primary_beat_id!r} missing from registry"
            )
        return static.primary_beat_id, branch
    if len(branch) != 1:
        raise ContractViolation(f"{wire_id} must bind exactly one beat")
    return branch[0], branch


def ops_family_rows() -> tuple[OpsFamilyRow, ...]:
    """Return the closed ops migration inventory (Slices 1–2: pit + incident, legacy)."""

    registry = _load("freeze-registry.json")
    beat_doc = _load("beat-catalog.json")
    beats = _beat_index(beat_doc)
    ttl_by_policy = _policy_ttl(beat_doc)

    rows: list[OpsFamilyRow] = []
    for wire_id in OPS_WIRE_IDS:
        static = _STATIC[wire_id]
        reg = _registry_row(registry, wire_id)
        event_class = str(reg["eventClass"])
        tape_channel = str(reg["tapeChannel"])
        can_create = can_create_event_opportunity(wire_id)
        beat_id, branch_beat_ids = _resolve_beat_ids(wire_id, reg, static)
        beat = beats.get(beat_id)
        if beat is None:
            raise ContractViolation(f"missing beat {beat_id} for {wire_id}")
        policy_id = str(beat["policyId"])
        realization = beat.get("realization")
        if not isinstance(realization, dict) or "family" not in realization:
            raise ContractViolation(f"beat {beat_id} missing realization.family")
        predicate_id, actor_frame = _claim_meta(beat)
        rows.append(
            OpsFamilyRow(
                wire_id=wire_id,
                legacy_node_id=static.legacy_node_id,
                race_event_name=static.race_event_name,
                emitter_module=static.emitter_module,
                adapter_module=static.adapter_module,
                predicate_id=predicate_id,
                actor_frame=actor_frame,
                beat_id=beat_id,
                beat_role=str(beat["role"]),
                realization_family=str(realization["family"]),
                story_routes=_story_routes(beat),
                policy_id=policy_id,
                outcome_ttl_ms=ttl_by_policy[policy_id],
                tape_channel=tape_channel,
                event_class=event_class,
                can_create=can_create,
                pit_phase=static.pit_phase,
                incident_phase=static.incident_phase,
                scope_kind=static.scope_kind,
                migration_status="legacy",
                invalidate_reasons=static.invalidate_reasons,
                terminal_reasons=static.terminal_reasons,
                branch_beat_ids=branch_beat_ids,
                notes=static.notes,
            )
        )
    return tuple(rows)


def row_for_wire_id(wire_id: str) -> OpsFamilyRow:
    """Return one inventory row or raise ``ContractViolation``."""

    for row in ops_family_rows():
        if row.wire_id == wire_id:
            return row
    raise ContractViolation(f"unknown ops wire id: {wire_id}")


def rows_by_migration_status(status: MigrationStatus) -> tuple[OpsFamilyRow, ...]:
    """Filter inventory rows by migration status."""

    return tuple(row for row in ops_family_rows() if row.migration_status == status)


def migration_status_by_wire_id() -> dict[str, MigrationStatus]:
    """Coverage-matrix companion: every ops inventory family -> migration status."""

    return {row.wire_id: row.migration_status for row in ops_family_rows()}


def pit_cycle_phase_order_is_monotonic() -> bool:
    """Slice 1 helper: pit phases follow entry → service → exit → outcome order."""

    if PIT_CYCLE_PHASE_ORDER != ("entry", "lane", "stopped", "released", "exit", "outcome"):
        return False
    by_phase = {
        row.pit_phase: row.wire_id for row in ops_family_rows() if row.pit_phase is not None
    }
    if set(by_phase) != set(PIT_CYCLE_PHASE_ORDER):
        return False
    expected = {
        "entry": "PIT_ENTRY",
        "lane": "PIT_LANE",
        "stopped": "PIT_STOPPED",
        "released": "PIT_RELEASED",
        "exit": "PIT_EXIT",
        "outcome": "PIT_OUTCOME",
    }
    return by_phase == expected


def pit_cycle_stories_have_explicit_terminals() -> bool:
    """AC helper: exit/outcome carry terminal reasons; openers stay non-terminal."""

    if not pit_cycle_phase_order_is_monotonic():
        return False
    for wire_id in OPS_PIT_WIRE_IDS:
        row = row_for_wire_id(wire_id)
        if not row.invalidate_reasons:
            return False
        if wire_id in PIT_TERMINAL_WIRE_IDS:
            if not row.terminal_reasons:
                return False
        elif row.terminal_reasons:
            return False
    return True


def incident_cycle_phase_order_is_monotonic() -> bool:
    """Slice 2 helper: incident phases follow event → aftermath → recovery."""

    if INCIDENT_CYCLE_PHASE_ORDER != ("event", "aftermath", "recovery"):
        return False
    by_phase = {
        row.incident_phase: row.wire_id
        for row in ops_family_rows()
        if row.incident_phase is not None
    }
    if set(by_phase) != set(INCIDENT_CYCLE_PHASE_ORDER):
        return False
    expected = {
        "event": "INCIDENT",
        "aftermath": "INCIDENT_AFTERMATH",
        "recovery": "BACK_UNDER_WAY",
    }
    return by_phase == expected


def incident_stories_have_explicit_terminals() -> bool:
    """AC helper: only recovery wire is terminal; every incident wire invalidates."""

    if not incident_cycle_phase_order_is_monotonic():
        return False
    for wire_id in OPS_INCIDENT_WIRE_IDS:
        row = row_for_wire_id(wire_id)
        if not row.invalidate_reasons:
            return False
        if wire_id in INCIDENT_TERMINAL_WIRE_IDS:
            if not row.terminal_reasons:
                return False
        elif row.terminal_reasons:
            return False
    return True


def incident_branch_beats_are_documented() -> bool:
    """Slice 2 helper: INCIDENT documents off-track + unclassified branch beats."""

    row = row_for_wire_id("INCIDENT")
    if row.beat_id != INCIDENT_PRIMARY_BEAT_ID:
        return False
    if row.branch_beat_ids != INCIDENT_BRANCH_BEAT_IDS:
        return False
    lowered = row.notes.lower()
    if "unknown" not in lowered and "unclassified" not in lowered:
        return False
    return True
