"""#277 context family migration map — session/stream leftovers + filler (Slices 1–2).

Maps remaining non-race session/stream and filler wire identifiers onto legacy
emitters, adapters, beat/story routes, predicates, realization families, policy
TTL and tape channels.

Slices 1–2 record these wires as ``legacy``. They do **not** rewrite frozen
``docs/v2.0.0/machine/*`` hashes and do **not** flip ``FAMILY_ROUTE``.
Session intros/recaps stay owned by the timing map; session wrap/checkered/finish
stay owned by the ops / race-outcome maps. Beat-only silence fillers are
documented without inventing freeze wires.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

from .coverage_matrix import can_create_event_opportunity
from .primitives import ContractViolation
from .resources import packaged_schema_bytes

MigrationStatus = Literal["legacy", "shadow", "v2"]
ScopeKind = Literal[
    "stream_lifecycle",
    "session_preview",
    "enter_car",
    "final_lap",
    "filler_parade",
]
LifecyclePhase = Literal["stream_start", "preview", "enter_car", "final_lap"]
FillerKind = Literal[
    "out_lap",
    "in_lap",
    "parade_lap",
    "garage",
    "lobby",
    "quiet_track",
]

# Slice 1 inventory: stream/session leftovers not owned by timing/ops maps.
CONTEXT_SESSION_WIRE_IDS: tuple[str, ...] = (
    "STREAM_START",
    "SESSION_PREVIEW",
    "ENTER_CAR",
    "FINAL_LAP",
)

# Slice 2 inventory: parade pad is the only freeze wire for filler impulses.
CONTEXT_FILLER_WIRE_IDS: tuple[str, ...] = ("PARADE_PAD",)

CONTEXT_WIRE_IDS: tuple[str, ...] = CONTEXT_SESSION_WIRE_IDS + CONTEXT_FILLER_WIRE_IDS

# Silence-clock filler beats (policy filler). Parade also binds PARADE_PAD.
CONTEXT_FILLER_BEAT_IDS: tuple[str, ...] = (
    "filler.out_lap",
    "filler.in_lap",
    "filler.parade_lap",
    "filler.garage",
    "filler.lobby",
    "filler.quiet_track",
)

# Beat-only fillers — no dedicated freeze wire; selected by silence_clock or fail to silence.
CONTEXT_FILLER_BEAT_ONLY_IDS: tuple[str, ...] = (
    "filler.out_lap",
    "filler.in_lap",
    "filler.garage",
    "filler.lobby",
    "filler.quiet_track",
)

CONTEXT_FILLER_KIND_BY_BEAT_ID: dict[str, FillerKind] = {
    "filler.out_lap": "out_lap",
    "filler.in_lap": "in_lap",
    "filler.parade_lap": "parade_lap",
    "filler.garage": "garage",
    "filler.lobby": "lobby",
    "filler.quiet_track": "quiet_track",
}

# Documented ownership outside this map (do not duplicate inventory rows).
CONTEXT_OWNED_ELSEWHERE: dict[str, str] = {
    "SESSION_INTRO_PRACTICE": "timing_family_map",
    "SESSION_INTRO_QUALIFY": "timing_family_map",
    "SESSION_INTRO_RACE": "timing_family_map",
    "QUALI_RECAP": "timing_family_map",
    "SESSION_WRAP": "ops_family_map",
    "SESSION_CHECKERED": "ops_family_map",
    "SESSION_FLAG": "ops_family_map",
    "FINISH": "ops_family_map/race_outcome_family_map",
}

# ENTER_CAR freeze binds stage-routed vehicle beats; primary follows registry order.
ENTER_CAR_BRANCH_BEAT_IDS: tuple[str, ...] = (
    "session.enter_car.practice",
    "session.enter_car.qualifying",
    "session.enter_car.race",
)
ENTER_CAR_PRIMARY_BEAT_ID = "session.enter_car.practice"

# Lifecycle order for leftover session/stream commentary (not a full story FSM).
CONTEXT_SESSION_PHASE_ORDER: tuple[LifecyclePhase, ...] = (
    "stream_start",
    "preview",
    "enter_car",
    "final_lap",
)


@dataclass(frozen=True, slots=True)
class ContextFamilyRow:
    """One context (session/stream leftover) wire identifier and its inventory."""

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
    lifecycle_phase: LifecyclePhase | None
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
    lifecycle_phase: LifecyclePhase | None
    scope_kind: ScopeKind
    invalidate_reasons: tuple[str, ...]
    terminal_reasons: tuple[str, ...]
    primary_beat_id: str | None = None
    notes: str = ""


_STATIC: dict[str, _StaticSource] = {
    "STREAM_START": _StaticSource(
        legacy_node_id="stream_start",
        race_event_name=None,
        emitter_module="irswitch.events.lifecycle_edges:LifecycleTriggerBank",
        adapter_module="irswitch.events.lifecycle_edges:LifecycleTriggerBank",
        lifecycle_phase="stream_start",
        scope_kind="stream_lifecycle",
        invalidate_reasons=("stream_ended", "session_reset"),
        terminal_reasons=(),
        notes=(
            "OBS/stream open leftover. Freeze disposition rejects the wire from the "
            "final narrative catalog in favor of internal STREAM_STARTED; inventory "
            "keeps the speakable adapter surface. Not a session intro/wrap claim."
        ),
    ),
    "SESSION_PREVIEW": _StaticSource(
        legacy_node_id="session_preview",
        race_event_name=None,
        emitter_module="irswitch.race.narrative:StreamNarrativeFsm",
        adapter_module="irswitch.race.narrative:StreamNarrativeFsm",
        lifecycle_phase="preview",
        scope_kind="session_preview",
        invalidate_reasons=("stream_ended", "session_reset", "session_superseded"),
        terminal_reasons=(),
        notes=(
            "Bridge into the next session. Distinct from stage intros owned by "
            "timing_family_map and from SESSION_WRAP owned by ops_family_map. "
            "Missing stage evidence stays unknown — never invent the next session type."
        ),
    ),
    "ENTER_CAR": _StaticSource(
        legacy_node_id="enter_car",
        race_event_name=None,
        emitter_module="irswitch.commentary.opener:OpenerMutex",
        adapter_module="irswitch.events.adapters.session:session_race_event_to_envelope",
        lifecycle_phase="enter_car",
        scope_kind="enter_car",
        invalidate_reasons=("stream_ended", "session_reset", "hero_teleport"),
        terminal_reasons=(),
        primary_beat_id=ENTER_CAR_PRIMARY_BEAT_ID,
        notes=(
            "Vehicle/on-track entry routed by confirmed stage "
            "(practice|qualifying|race). Primary beat session.enter_car.practice; "
            "branch list documents all three stage beats. Not a race-start or "
            "finish claim."
        ),
    ),
    "FINAL_LAP": _StaticSource(
        legacy_node_id="final_lap",
        race_event_name="final_lap",
        emitter_module="irswitch.events.session:SessionEmitter",
        adapter_module="irswitch.events.adapters.session:session_race_event_to_envelope",
        lifecycle_phase="final_lap",
        scope_kind="final_lap",
        invalidate_reasons=("stream_ended", "session_reset", "checkered_already_out"),
        terminal_reasons=("final_lap_observed",),
        notes=(
            "Last-lap escalation. Distinct from SESSION_CHECKERED / FINISH / "
            "SESSION_WRAP. Missing lap evidence stays unknown — never invent "
            "checkered or hero finish from final-lap alone."
        ),
    ),
    "PARADE_PAD": _StaticSource(
        legacy_node_id="parade_pad",
        race_event_name="parade_pad",
        emitter_module="irswitch.race.grid_story:GridStoryFsm",
        adapter_module="irswitch.race.grid_story:GridStoryFsm",
        lifecycle_phase=None,
        scope_kind="filler_parade",
        invalidate_reasons=("stream_ended", "session_reset", "green_or_racing", "parade_cap"),
        terminal_reasons=(),
        notes=(
            "Only freeze wire for filler impulses (GridStory parade pads). Beat "
            "filler.parade_lap also admits LONG_SILENCE_ELAPSED. Beat-only silence "
            "fillers stay outside CONTEXT_WIRE_IDS: out_lap, in_lap, garage, lobby, "
            "quiet_track (selected by silence_clock or fail to silence / "
            "no_candidate / source_guard_failed). Never force generic filler speech "
            "when facts are missing — silence is a valid outcome."
        ),
    ),
}


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ContractViolation(f"{label} must be a JSON object")
    return value


def _rows(value: object, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ContractViolation(f"{label} must be a list of objects")
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
    raise ContractViolation(f"unknown context wire id: {wire_id}")


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


def context_family_rows() -> tuple[ContextFamilyRow, ...]:
    """Return the closed context migration inventory (Slices 1–2: session leftovers + filler, legacy)."""

    registry = _load("freeze-registry.json")
    beat_doc = _load("beat-catalog.json")
    beats = _beat_index(beat_doc)
    ttl_by_policy = _policy_ttl(beat_doc)

    rows: list[ContextFamilyRow] = []
    for wire_id in CONTEXT_WIRE_IDS:
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
            ContextFamilyRow(
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
                lifecycle_phase=static.lifecycle_phase,
                scope_kind=static.scope_kind,
                migration_status="legacy",
                invalidate_reasons=static.invalidate_reasons,
                terminal_reasons=static.terminal_reasons,
                branch_beat_ids=branch_beat_ids,
                notes=static.notes,
            )
        )
    return tuple(rows)


def row_for_wire_id(wire_id: str) -> ContextFamilyRow:
    """Return one inventory row or raise ``ContractViolation``."""

    for row in context_family_rows():
        if row.wire_id == wire_id:
            return row
    raise ContractViolation(f"unknown context wire id: {wire_id}")


def rows_by_migration_status(status: MigrationStatus) -> tuple[ContextFamilyRow, ...]:
    """Filter inventory rows by migration status."""

    return tuple(row for row in context_family_rows() if row.migration_status == status)


def migration_status_by_wire_id() -> dict[str, MigrationStatus]:
    """Coverage-matrix companion: every context inventory family -> migration status."""

    return {row.wire_id: row.migration_status for row in context_family_rows()}


def context_session_phase_order_is_monotonic() -> bool:
    """Slice 1 helper: leftover session/stream phases keep a closed order."""

    if CONTEXT_SESSION_PHASE_ORDER != ("stream_start", "preview", "enter_car", "final_lap"):
        return False
    by_phase = {
        row.lifecycle_phase: row.wire_id
        for row in context_family_rows()
        if row.lifecycle_phase is not None
    }
    expected = {
        "stream_start": "STREAM_START",
        "preview": "SESSION_PREVIEW",
        "enter_car": "ENTER_CAR",
        "final_lap": "FINAL_LAP",
    }
    return by_phase == expected


def enter_car_branch_beats_are_documented() -> bool:
    """Slice 1 helper: ENTER_CAR documents practice + qualifying + race beats."""

    row = row_for_wire_id("ENTER_CAR")
    if row.beat_id != ENTER_CAR_PRIMARY_BEAT_ID:
        return False
    if row.branch_beat_ids != ENTER_CAR_BRANCH_BEAT_IDS:
        return False
    lowered = row.notes.lower()
    if "practice" not in lowered or "qualifying" not in lowered or "race" not in lowered:
        return False
    if not row.invalidate_reasons:
        return False
    return True


def context_session_stories_have_explicit_invalidation() -> bool:
    """AC helper: every leftover session/stream wire invalidates explicitly."""

    if not context_session_phase_order_is_monotonic():
        return False
    for wire_id in CONTEXT_SESSION_WIRE_IDS:
        row = row_for_wire_id(wire_id)
        if not row.invalidate_reasons:
            return False
        if "unknown" not in row.notes.lower() and "never invent" not in row.notes.lower():
            # STREAM_START notes use catalog-disposition language; still require invalidate.
            if wire_id != "STREAM_START" and "not a" not in row.notes.lower():
                return False
    final_lap = row_for_wire_id("FINAL_LAP")
    if not final_lap.terminal_reasons:
        return False
    return True


def owned_elsewhere_session_wires_are_documented() -> bool:
    """Slice 1 helper: intros/wrap/finish ownership stays outside this inventory."""

    if not CONTEXT_OWNED_ELSEWHERE:
        return False
    owned_ids = set(CONTEXT_OWNED_ELSEWHERE)
    if owned_ids & set(CONTEXT_WIRE_IDS):
        return False
    required = {
        "SESSION_INTRO_PRACTICE",
        "SESSION_INTRO_QUALIFY",
        "SESSION_INTRO_RACE",
        "QUALI_RECAP",
        "SESSION_WRAP",
        "SESSION_CHECKERED",
        "FINISH",
    }
    return required <= owned_ids


def filler_beats_are_documented() -> bool:
    """Slice 2 helper: parade wire + beat-only filler set stays closed and named."""

    if CONTEXT_FILLER_WIRE_IDS != ("PARADE_PAD",):
        return False
    if set(CONTEXT_FILLER_BEAT_ONLY_IDS) | {"filler.parade_lap"} != set(CONTEXT_FILLER_BEAT_IDS):
        return False
    if set(CONTEXT_FILLER_KIND_BY_BEAT_ID) != set(CONTEXT_FILLER_BEAT_IDS):
        return False
    row = row_for_wire_id("PARADE_PAD")
    if row.beat_id != "filler.parade_lap":
        return False
    if row.scope_kind != "filler_parade":
        return False
    if row.realization_family != "filler.track_state":
        return False
    if row.policy_id != "filler":
        return False
    if not row.invalidate_reasons:
        return False
    lowered = row.notes.lower()
    if "silence" not in lowered:
        return False
    if "out_lap" not in lowered or "in_lap" not in lowered:
        return False
    if "garage" not in lowered or "lobby" not in lowered:
        return False
    if "quiet_track" not in lowered and "quiet track" not in lowered:
        return False
    return True


def filler_may_resolve_to_silence() -> bool:
    """AC helper: filler inventory admits silence instead of forced speech."""

    if not filler_beats_are_documented():
        return False
    row = row_for_wire_id("PARADE_PAD")
    lowered = row.notes.lower()
    if "never force" not in lowered and "not force" not in lowered:
        return False
    if "silence" not in lowered:
        return False
    # Beat-only fillers must remain outside CONTEXT_WIRE_IDS (no invented wires).
    if set(CONTEXT_FILLER_BEAT_ONLY_IDS) & set(CONTEXT_WIRE_IDS):
        return False
    return True

