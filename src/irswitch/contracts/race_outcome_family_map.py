"""#274 race-outcome family migration map (inventory + story/TTL contract).

Maps wire identifiers for position pass / gain / loss, leader change and
finish onto legacy emitters, adapters, beat/story routes, predicates,
realization families, policy TTL, tape channels and correlation bindings.

Slice 1 recorded every family as ``legacy``. Slice 2 locks story/beat roles,
correlation identity and outcome TTL. It does **not** rewrite frozen
``docs/v2.0.0/machine/*`` hashes and does **not** flip ``FAMILY_ROUTE``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from .coverage_matrix import can_create_event_opportunity
from .primitives import ContractViolation
from .resources import packaged_schema_bytes

MigrationStatus = Literal["legacy", "shadow", "v2"]
Polarity = Literal["pass", "gain", "loss", "leader", "finish", "alias"]
CorrelationKind = Literal["target", "hero_position", "leader", "hero_finish", "none"]
FALLBACK_STORY_ROUTE = "single_result"

# Speakable race-outcome families + the rejected OVERTAKEN alias.
RACE_OUTCOME_WIRE_IDS: tuple[str, ...] = (
    "OVERTAKE",
    "POSITION_GAINED",
    "POSITION_LOST",
    "LEADER_CHANGE",
    "FINISH",
    "OVERTAKEN",
)

# Policies whose outcomes stay speakable without a spoken opening beat.
SELF_CONTAINED_POLICIES: frozenset[str] = frozenset({"critical", "result"})


@dataclass(frozen=True, slots=True)
class RaceOutcomeFamilyRow:
    """One race-outcome wire identifier and its migration inventory."""

    wire_id: str
    legacy_node_id: str | None
    race_event_name: str | None
    emitter_module: str
    adapter_module: str
    predicate_id: str | None
    direction_equals: str | None
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
    self_contained: bool
    migration_status: MigrationStatus
    correlation_kind: CorrelationKind
    correlation_bindings: tuple[str, ...]
    closing_story_routes: tuple[str, ...]
    fallback_story_route: str | None
    adapter_correlation_prefix: str | None
    notes: str = ""


@dataclass(frozen=True, slots=True)
class _StaticSource:
    legacy_node_id: str | None
    race_event_name: str | None
    emitter_module: str
    adapter_module: str
    polarity: Polarity
    correlation_kind: CorrelationKind
    correlation_bindings: tuple[str, ...]
    closing_story_routes: tuple[str, ...]
    fallback_story_route: str | None
    adapter_correlation_prefix: str | None
    notes: str = ""


# Emitter/adapter/legacy-graph + correlation sources are branch inventory.
_STATIC: dict[str, _StaticSource] = {
    "OVERTAKE": _StaticSource(
        legacy_node_id="overtake",
        race_event_name="overtake",
        emitter_module="irswitch.events.overtake:OvertakeClassifierEmitter",
        adapter_module="irswitch.events.adapters.position:position_race_event_to_envelope",
        polarity="pass",
        correlation_kind="target",
        correlation_bindings=("hero", "target"),
        closing_story_routes=("battle_ahead", "battle_two_front"),
        fallback_story_route=FALLBACK_STORY_ROUTE,
        adapter_correlation_prefix="position:",
        notes="Passer→passed order; closes battle_ahead/two_front or single_result.",
    ),
    "POSITION_GAINED": _StaticSource(
        legacy_node_id="position_gained",
        race_event_name="position_change",
        emitter_module="irswitch.events.position:PositionEmitter",
        adapter_module="irswitch.events.adapters.position:_event_type_for_position_change",
        polarity="gain",
        correlation_kind="hero_position",
        correlation_bindings=("hero", "oldPosition", "newPosition", "direction"),
        closing_story_routes=(),
        fallback_story_route=FALLBACK_STORY_ROUTE,
        adapter_correlation_prefix="position:",
        notes="Adapter maps RaceEvent direction gain → POSITION_GAINED.",
    ),
    "POSITION_LOST": _StaticSource(
        legacy_node_id="position_lost",
        race_event_name="position_change",
        emitter_module="irswitch.events.position:PositionEmitter",
        adapter_module="irswitch.events.adapters.position:_event_type_for_position_change",
        polarity="loss",
        correlation_kind="hero_position",
        correlation_bindings=("hero", "oldPosition", "newPosition", "direction"),
        closing_story_routes=("battle_behind", "battle_two_front"),
        fallback_story_route=FALLBACK_STORY_ROUTE,
        adapter_correlation_prefix="position:",
        notes="Adapter maps RaceEvent direction loss → POSITION_LOST.",
    ),
    "LEADER_CHANGE": _StaticSource(
        legacy_node_id="leader_change",
        race_event_name="leader_change",
        emitter_module="irswitch.events.leader_change:LeaderChangeEmitter",
        adapter_module="irswitch.events.adapters.position:position_race_event_to_envelope",
        polarity="leader",
        correlation_kind="leader",
        correlation_bindings=("oldLeader", "newLeader"),
        closing_story_routes=(),
        fallback_story_route=FALLBACK_STORY_ROUTE,
        adapter_correlation_prefix="leader:",
        notes="Old leader → new leader; hero involvement only when bound.",
    ),
    "FINISH": _StaticSource(
        legacy_node_id="finish",
        race_event_name="finish",
        emitter_module="irswitch.events.lifecycle_edges:LifecycleTriggerBank",
        adapter_module="irswitch.events.adapters.session:session_race_event_to_envelope",
        polarity="finish",
        correlation_kind="hero_finish",
        correlation_bindings=("occurrence", "hero"),
        closing_story_routes=("session_occurrence",),
        fallback_story_route=FALLBACK_STORY_ROUTE,
        adapter_correlation_prefix="session:",
        notes="Hero finish / checkered result; self-contained critical outcome.",
    ),
    "OVERTAKEN": _StaticSource(
        legacy_node_id=None,
        race_event_name=None,
        emitter_module="—",
        adapter_module="—",
        polarity="alias",
        correlation_kind="none",
        correlation_bindings=(),
        closing_story_routes=(),
        fallback_story_route=None,
        adapter_correlation_prefix=None,
        notes="compatibility_alias; reject as v2 input; migrate to POSITION_LOST + cause.",
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
    raise ContractViolation(f"unknown race-outcome wire id: {wire_id}")


def _claim_meta(beat: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    claims = beat.get("claims")
    if not isinstance(claims, dict):
        return None, None, None
    required = claims.get("required")
    if not isinstance(required, list) or not required:
        return None, None, None
    first = required[0]
    if not isinstance(first, dict):
        return None, None, None
    predicate_id = str(first["id"]) if "id" in first else None
    actor_frame = str(first["actorFrame"]) if "actorFrame" in first else None
    direction: str | None = None
    equals = first.get("attributeEquals")
    if isinstance(equals, dict) and "direction" in equals:
        direction = str(equals["direction"])
    return predicate_id, actor_frame, direction


def _story_routes(beat: dict[str, Any]) -> tuple[str, ...]:
    routes = beat.get("storyRoutes")
    if not isinstance(routes, list) or any(not isinstance(item, str) for item in routes):
        raise ContractViolation(f"beat {beat.get('id')!r} storyRoutes must be strings")
    return tuple(routes)


def race_outcome_family_rows() -> tuple[RaceOutcomeFamilyRow, ...]:
    """Return the closed race-outcome migration inventory (currently all legacy)."""

    registry = _load("freeze-registry.json")
    beat_doc = _load("beat-catalog.json")
    beats = _beat_index(beat_doc)
    ttl_by_policy = _policy_ttl(beat_doc)

    rows: list[RaceOutcomeFamilyRow] = []
    for wire_id in RACE_OUTCOME_WIRE_IDS:
        static = _STATIC[wire_id]
        reg = _registry_row(registry, wire_id)
        event_class = str(reg["eventClass"])
        tape_channel = str(reg["tapeChannel"])
        can_create = can_create_event_opportunity(wire_id)
        beat_ids = reg.get("beatDefinitions")
        if not isinstance(beat_ids, list):
            raise ContractViolation(f"{wire_id} beatDefinitions must be a list")

        if event_class == "compatibility_alias":
            if beat_ids or can_create:
                raise ContractViolation(f"alias {wire_id} must not create opportunities")
            rows.append(
                RaceOutcomeFamilyRow(
                    wire_id=wire_id,
                    legacy_node_id=static.legacy_node_id,
                    race_event_name=static.race_event_name,
                    emitter_module=static.emitter_module,
                    adapter_module=static.adapter_module,
                    predicate_id=None,
                    direction_equals=None,
                    actor_frame=None,
                    beat_id=None,
                    beat_role=None,
                    realization_family=None,
                    story_routes=(),
                    policy_id=None,
                    outcome_ttl_ms=None,
                    tape_channel=tape_channel,
                    event_class=event_class,
                    can_create=False,
                    polarity=static.polarity,
                    self_contained=False,
                    migration_status="legacy",
                    correlation_kind=static.correlation_kind,
                    correlation_bindings=static.correlation_bindings,
                    closing_story_routes=static.closing_story_routes,
                    fallback_story_route=static.fallback_story_route,
                    adapter_correlation_prefix=static.adapter_correlation_prefix,
                    notes=static.notes,
                )
            )
            continue

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
        predicate_id, actor_frame, direction_equals = _claim_meta(beat)
        story_routes = _story_routes(beat)
        for route in static.closing_story_routes:
            if route not in story_routes:
                raise ContractViolation(
                    f"{wire_id} closing route {route!r} missing from beat storyRoutes"
                )
        if (
            static.fallback_story_route is not None
            and static.fallback_story_route not in story_routes
        ):
            raise ContractViolation(
                f"{wire_id} fallback {static.fallback_story_route!r} missing from beat storyRoutes"
            )
        rows.append(
            RaceOutcomeFamilyRow(
                wire_id=wire_id,
                legacy_node_id=static.legacy_node_id,
                race_event_name=static.race_event_name,
                emitter_module=static.emitter_module,
                adapter_module=static.adapter_module,
                predicate_id=predicate_id,
                direction_equals=direction_equals,
                actor_frame=actor_frame,
                beat_id=beat_id,
                beat_role=str(beat["role"]),
                realization_family=str(realization["family"]),
                story_routes=story_routes,
                policy_id=policy_id,
                outcome_ttl_ms=ttl_by_policy[policy_id],
                tape_channel=tape_channel,
                event_class=event_class,
                can_create=can_create,
                polarity=static.polarity,
                self_contained=policy_id in SELF_CONTAINED_POLICIES,
                migration_status="legacy",
                correlation_kind=static.correlation_kind,
                correlation_bindings=static.correlation_bindings,
                closing_story_routes=static.closing_story_routes,
                fallback_story_route=static.fallback_story_route,
                adapter_correlation_prefix=static.adapter_correlation_prefix,
                notes=static.notes,
            )
        )
    return tuple(rows)


def row_for_wire_id(wire_id: str) -> RaceOutcomeFamilyRow:
    """Return one inventory row or raise ``ContractViolation``."""

    for row in race_outcome_family_rows():
        if row.wire_id == wire_id:
            return row
    raise ContractViolation(f"unknown race-outcome wire id: {wire_id}")


def rows_by_migration_status(status: MigrationStatus) -> tuple[RaceOutcomeFamilyRow, ...]:
    """Filter inventory rows by migration status."""

    return tuple(row for row in race_outcome_family_rows() if row.migration_status == status)


def migration_status_by_wire_id() -> dict[str, MigrationStatus]:
    """Coverage-matrix companion: every race-outcome family → migration status."""

    return {row.wire_id: row.migration_status for row in race_outcome_family_rows()}
