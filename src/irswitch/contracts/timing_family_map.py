"""#275 timing family migration map (lap/SF, sector, PB/pace, quali/invalid).

Maps wire identifiers for lap completion (start/finish crossing), sector
split/best, personal best, pace gain/loss, hot-lap attempt, projected lap,
and invalid lap onto legacy emitters, adapters, beat/story routes, predicates,
realization families, policy TTL and tape channels.

Slices 1–3 record every family as ``legacy``. They do **not** rewrite frozen
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
Polarity = Literal[
    "lap_complete",
    "sector_split",
    "sector_best",
    "personal_best",
    "gain_found",
    "time_lost",
    "hot_lap",
    "projected_lap",
    "invalid_lap",
]
ScopeKind = Literal[
    "lap_sf", "sector", "lap_pb", "pace_delta", "lap_attempt", "lap_projection", "invalid_lap"
]

# Slice 1–3 inventory: lap/SF + sector + PB/pace + hot/projected/invalid lap.
TIMING_WIRE_IDS: tuple[str, ...] = (
    "LAP_COMPLETE",
    "SECTOR_SPLIT",
    "SECTOR_BEST",
    "PERSONAL_BEST",
    "GAIN_FOUND",
    "TIME_LOST",
    "HOT_LAP",
    "PROJECTED_LAP",
    "INVALID_LAP",
)

# Finish/race outcome wires that must never share lap-complete semantics.
RACE_FINISH_WIRE_IDS: frozenset[str] = frozenset({"FINISH"})

# Invalid-lap AC: explicit session-mode scope (not race finish / not race mode).
INVALID_LAP_SESSION_MODES: frozenset[str] = frozenset({"PRACTICE", "QUALIFYING"})


@dataclass(frozen=True, slots=True)
class TimingFamilyRow:
    """One timing wire identifier and its migration inventory."""

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
    polarity: Polarity
    scope_kind: ScopeKind
    migration_status: MigrationStatus
    notes: str = ""


@dataclass(frozen=True, slots=True)
class _StaticSource:
    legacy_node_id: str | None
    race_event_name: str | None
    emitter_module: str
    adapter_module: str
    polarity: Polarity
    scope_kind: ScopeKind
    notes: str = ""


_STATIC: dict[str, _StaticSource] = {
    "LAP_COMPLETE": _StaticSource(
        legacy_node_id="lap_complete",
        race_event_name="lap_complete",
        emitter_module="irswitch.events.direct_edges:DirectEdgeBank",
        adapter_module="irswitch.events.adapters.lap:lap_race_event_to_envelope",
        polarity="lap_complete",
        scope_kind="lap_sf",
        notes="Start/finish lap crossing; must not be treated as race finish.",
    ),
    "SECTOR_SPLIT": _StaticSource(
        legacy_node_id="sector_split",
        race_event_name="sector_split",
        emitter_module="irswitch.events.direct_edges:DirectEdgeBank",
        adapter_module="irswitch.events.adapters.timing:timing_race_event_to_envelope",
        polarity="sector_split",
        scope_kind="sector",
        notes="Intra-lap sector split; update/transient policy.",
    ),
    "SECTOR_BEST": _StaticSource(
        legacy_node_id=None,
        race_event_name="sector_best",
        emitter_module="irswitch.events.direct_edges:DirectEdgeBank",
        adapter_module="irswitch.events.adapters.timing:timing_race_event_to_envelope",
        polarity="sector_best",
        scope_kind="sector",
        notes="Session-best sector improvement; no dedicated sequence-graph node.",
    ),
    "PERSONAL_BEST": _StaticSource(
        legacy_node_id="personal_best",
        race_event_name="personal_best",
        emitter_module="irswitch.events.lap:LapEmitter",
        adapter_module="irswitch.events.adapters.lap:lap_race_event_to_envelope",
        polarity="personal_best",
        scope_kind="lap_pb",
        notes="Hero personal-best lap; LapEmitter may emit instead of lap_complete.",
    ),
    "GAIN_FOUND": _StaticSource(
        legacy_node_id="gain_found",
        race_event_name="gain_found",
        emitter_module="irswitch.events.practice:PracticeEmitter",
        adapter_module="irswitch.events.adapters.timing:timing_race_event_to_envelope",
        polarity="gain_found",
        scope_kind="pace_delta",
        notes="Pace improved vs reference; practice/qualifying temporal delta.",
    ),
    "TIME_LOST": _StaticSource(
        legacy_node_id="time_lost",
        race_event_name="time_lost",
        emitter_module="irswitch.events.practice:PracticeEmitter",
        adapter_module="irswitch.events.adapters.timing:timing_race_event_to_envelope",
        polarity="time_lost",
        scope_kind="pace_delta",
        notes="Pace worsened vs reference; opposite polarity of gain_found.",
    ),
    "HOT_LAP": _StaticSource(
        legacy_node_id="hot_lap",
        race_event_name="hot_lap",
        emitter_module="irswitch.events.quali:QualiEmitter",
        adapter_module="irswitch.events.adapters.timing:timing_race_event_to_envelope",
        polarity="hot_lap",
        scope_kind="lap_attempt",
        notes="Active qualifying/practice attempt (hot lap); not a completed result.",
    ),
    "PROJECTED_LAP": _StaticSource(
        legacy_node_id="projected_lap",
        race_event_name="projected_lap",
        emitter_module="irswitch.events.quali:QualiEmitter",
        adapter_module="irswitch.events.adapters.timing:timing_race_event_to_envelope",
        polarity="projected_lap",
        scope_kind="lap_projection",
        notes="In-lap projection only; must not claim a completed lap result.",
    ),
    "INVALID_LAP": _StaticSource(
        legacy_node_id="invalid_lap",
        race_event_name="invalid_lap",
        emitter_module="irswitch.events.invalid_lap:InvalidLapEmitter",
        adapter_module="irswitch.events.adapters.exception_extra:invalid_lap_race_event_to_envelope",
        polarity="invalid_lap",
        scope_kind="invalid_lap",
        notes="Invalid-lap scope is PRACTICE|QUALIFYING only (not RACE); incident.invalid_lap family.",
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
    raise ContractViolation(f"unknown timing wire id: {wire_id}")


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


def timing_family_rows() -> tuple[TimingFamilyRow, ...]:
    """Return the closed timing migration inventory (currently all legacy)."""

    registry = _load("freeze-registry.json")
    beat_doc = _load("beat-catalog.json")
    beats = _beat_index(beat_doc)
    ttl_by_policy = _policy_ttl(beat_doc)

    rows: list[TimingFamilyRow] = []
    for wire_id in TIMING_WIRE_IDS:
        static = _STATIC[wire_id]
        reg = _registry_row(registry, wire_id)
        event_class = str(reg["eventClass"])
        tape_channel = str(reg["tapeChannel"])
        can_create = can_create_event_opportunity(wire_id)
        beat_ids = reg.get("beatDefinitions")
        if not isinstance(beat_ids, list):
            raise ContractViolation(f"{wire_id} beatDefinitions must be a list")
        if len(beat_ids) != 1 or not isinstance(beat_ids[0], str):
            raise ContractViolation(f"{wire_id} must bind exactly one beat")
        beat_id = beat_ids[0]
        beat = beats.get(beat_id)
        if beat is None:
            raise ContractViolation(f"missing beat {beat_id} for {wire_id}")
        policy_id = str(beat["policyId"])
        realization = beat.get("realization")
        if not isinstance(realization, dict) or "family" not in realization:
            raise ContractViolation(f"beat {beat_id} missing realization.family")
        predicate_id, actor_frame = _claim_meta(beat)
        rows.append(
            TimingFamilyRow(
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
                polarity=static.polarity,
                scope_kind=static.scope_kind,
                migration_status="legacy",
                notes=static.notes,
            )
        )
    return tuple(rows)


def row_for_wire_id(wire_id: str) -> TimingFamilyRow:
    """Return one inventory row or raise ``ContractViolation``."""

    for row in timing_family_rows():
        if row.wire_id == wire_id:
            return row
    raise ContractViolation(f"unknown timing wire id: {wire_id}")


def rows_by_migration_status(status: MigrationStatus) -> tuple[TimingFamilyRow, ...]:
    """Filter inventory rows by migration status."""

    return tuple(row for row in timing_family_rows() if row.migration_status == status)


def migration_status_by_wire_id() -> dict[str, MigrationStatus]:
    """Coverage-matrix companion: every timing inventory family -> migration status."""

    return {row.wire_id: row.migration_status for row in timing_family_rows()}


def lap_complete_is_not_race_finish() -> bool:
    """AC helper: completed lap must stay distinct from race finish semantics."""

    lap = row_for_wire_id("LAP_COMPLETE")
    if lap.scope_kind != "lap_sf" or lap.polarity != "lap_complete":
        return False
    if lap.realization_family == "session.finish":
        return False
    if lap.wire_id in RACE_FINISH_WIRE_IDS:
        return False
    # Finish lives on race-outcome inventory, not this timing slice.
    finish_ids = RACE_FINISH_WIRE_IDS
    return lap.beat_id != "session.hero_finish" and lap.wire_id not in finish_ids


def gain_and_loss_polarities_are_distinct() -> bool:
    """Slice 2 helper: pace gain must never share polarity/beat with time lost."""

    gained = row_for_wire_id("GAIN_FOUND")
    lost = row_for_wire_id("TIME_LOST")
    if gained.polarity != "gain_found" or lost.polarity != "time_lost":
        return False
    if gained.polarity == lost.polarity:
        return False
    if gained.beat_id == lost.beat_id:
        return False
    if gained.scope_kind != "pace_delta" or lost.scope_kind != "pace_delta":
        return False
    return gained.realization_family == lost.realization_family == "timing.delta"


def invalid_lap_scope_is_explicit() -> bool:
    """AC helper: invalid-lap scope stays PRACTICE|QUALIFYING, never race finish."""

    row = row_for_wire_id("INVALID_LAP")
    if row.scope_kind != "invalid_lap" or row.polarity != "invalid_lap":
        return False
    if row.realization_family != "incident.invalid_lap":
        return False
    if row.beat_id == "session.hero_finish" or row.wire_id in RACE_FINISH_WIRE_IDS:
        return False
    if "RACE" in INVALID_LAP_SESSION_MODES:
        return False
    return INVALID_LAP_SESSION_MODES == frozenset({"PRACTICE", "QUALIFYING"})
