"""#275 timing family migration map (timing + session intros/recaps).

Maps wire identifiers for lap/sector/PB/pace/hot/projected/invalid lap and
practice→qualifying→race session intros/recaps onto legacy emitters, adapters,
beat/story routes, predicates, realization families, policy TTL and tape channels.

Slices 1–5 record every family as ``legacy``. They do **not** rewrite frozen
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
    "session_intro_practice",
    "session_intro_qualify",
    "session_intro_race",
    "quali_recap",
]
ScopeKind = Literal[
    "lap_sf",
    "sector",
    "lap_pb",
    "pace_delta",
    "lap_attempt",
    "lap_projection",
    "invalid_lap",
    "session_intro",
    "session_recap",
]
SessionStage = Literal["practice", "qualifying", "race"]

# Slice 1–5 inventory: timing wires + practice→qualifying→race session intros/recaps.
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
    "SESSION_INTRO_PRACTICE",
    "SESSION_INTRO_QUALIFY",
    "SESSION_INTRO_RACE",
    "QUALI_RECAP",
)

# Finish/race outcome wires that must never share lap-complete semantics.
RACE_FINISH_WIRE_IDS: frozenset[str] = frozenset({"FINISH"})

# Invalid-lap AC: explicit session-mode scope (not race finish / not race mode).
INVALID_LAP_SESSION_MODES: frozenset[str] = frozenset({"PRACTICE", "QUALIFYING"})

# Historical practice → qualifying → race order for session intros/recaps.
SESSION_STAGE_ORDER: tuple[SessionStage, ...] = ("practice", "qualifying", "race")

SESSION_RECAP_WIRE_IDS: frozenset[str] = frozenset(
    {
        "SESSION_INTRO_PRACTICE",
        "SESSION_INTRO_QUALIFY",
        "SESSION_INTRO_RACE",
        "QUALI_RECAP",
    }
)


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
    session_stage: SessionStage | None = None
    requires_active_lineage: bool = False
    en_pattern_ids: tuple[str, ...] = ()
    en_claim_surfaces: tuple[str, ...] = ()
    en_forbidden_tokens: tuple[str, ...] = ()
    tts_slot_formats: tuple[str, ...] = ()
    notes: str = ""


@dataclass(frozen=True, slots=True)
class _StaticSource:
    legacy_node_id: str | None
    race_event_name: str | None
    emitter_module: str
    adapter_module: str
    polarity: Polarity
    scope_kind: ScopeKind
    session_stage: SessionStage | None = None
    requires_active_lineage: bool = False
    en_pattern_ids: tuple[str, ...] = ()
    en_claim_surfaces: tuple[str, ...] = ()
    en_forbidden_tokens: tuple[str, ...] = ()
    tts_slot_formats: tuple[str, ...] = ()
    notes: str = ""


_STATIC: dict[str, _StaticSource] = {
    "LAP_COMPLETE": _StaticSource(
        legacy_node_id="lap_complete",
        race_event_name="lap_complete",
        emitter_module="irswitch.events.direct_edges:DirectEdgeBank",
        adapter_module="irswitch.events.adapters.lap:lap_race_event_to_envelope",
        polarity="lap_complete",
        scope_kind="lap_sf",
        en_pattern_ids=(
            "timing.lap.completed:tight:1",
            "timing.lap.completed:tight:2",
            "timing.lap.completed:tight:3",
            "timing.lap.completed:tight:4",
        ),
        en_claim_surfaces=(
            "completes lap {lapNumber}",
            "crosses the line on lap {lapNumber}",
            "finishes lap {lapNumber}",
            "banks lap {lapNumber}",
        ),
        en_forbidden_tokens=("wins the race", "checkered", "race finish", "takes the win"),
        tts_slot_formats=("subjectSurface", "requiredClaimSurface"),
        notes="Start/finish lap crossing; must not be treated as race finish.",
    ),
    "SECTOR_SPLIT": _StaticSource(
        legacy_node_id="sector_split",
        race_event_name="sector_split",
        emitter_module="irswitch.events.direct_edges:DirectEdgeBank",
        adapter_module="irswitch.events.adapters.timing:timing_race_event_to_envelope",
        polarity="sector_split",
        scope_kind="sector",
        en_pattern_ids=(
            "timing.sector.split:tight:1",
            "timing.sector.split:tight:2",
            "timing.sector.split:tight:3",
            "timing.sector.split:tight:4",
        ),
        en_claim_surfaces=(
            "splits sector {sectorId}",
            "ticks sector {sectorId}",
            "runs sector {sectorId}",
            "clears sector {sectorId}",
        ),
        en_forbidden_tokens=("sector best", "personal best", "invalid lap"),
        tts_slot_formats=("subjectSurface", "requiredClaimSurface"),
        notes="Intra-lap sector split; update/transient policy.",
    ),
    "SECTOR_BEST": _StaticSource(
        legacy_node_id=None,
        race_event_name="sector_best",
        emitter_module="irswitch.events.direct_edges:DirectEdgeBank",
        adapter_module="irswitch.events.adapters.timing:timing_race_event_to_envelope",
        polarity="sector_best",
        scope_kind="sector",
        en_pattern_ids=(
            "timing.sector.best:tight:1",
            "timing.sector.best:tight:2",
            "timing.sector.best:tight:3",
            "timing.sector.best:tight:4",
        ),
        en_claim_surfaces=(
            "sets a sector {sectorId} best",
            "improves sector {sectorId}",
            "finds time in sector {sectorId}",
            "beats the sector {sectorId} mark",
        ),
        en_forbidden_tokens=("loses time", "invalid lap", "race finish"),
        tts_slot_formats=("subjectSurface", "requiredClaimSurface"),
        notes="Session-best sector improvement; no dedicated sequence-graph node.",
    ),
    "PERSONAL_BEST": _StaticSource(
        legacy_node_id="personal_best",
        race_event_name="personal_best",
        emitter_module="irswitch.events.lap:LapEmitter",
        adapter_module="irswitch.events.adapters.lap:lap_race_event_to_envelope",
        polarity="personal_best",
        scope_kind="lap_pb",
        en_pattern_ids=(
            "timing.lap.personal_best:tight:1",
            "timing.lap.personal_best:tight:2",
            "timing.lap.personal_best:tight:3",
            "timing.lap.personal_best:tight:4",
        ),
        en_claim_surfaces=(
            "sets a personal best",
            "improves the personal best to {lapTime}",
            "beats the personal best",
            "posts a new personal best",
        ),
        en_forbidden_tokens=("sector only", "invalid lap", "race win"),
        tts_slot_formats=("subjectSurface", "requiredClaimSurface"),
        notes="Hero personal-best lap; LapEmitter may emit instead of lap_complete.",
    ),
    "GAIN_FOUND": _StaticSource(
        legacy_node_id="gain_found",
        race_event_name="gain_found",
        emitter_module="irswitch.events.practice:PracticeEmitter",
        adapter_module="irswitch.events.adapters.timing:timing_race_event_to_envelope",
        polarity="gain_found",
        scope_kind="pace_delta",
        en_pattern_ids=(
            "timing.pace.gain:tight:1",
            "timing.pace.gain:tight:2",
            "timing.pace.gain:tight:3",
            "timing.pace.gain:tight:4",
        ),
        en_claim_surfaces=(
            "finds {delta} against the reference",
            "gains time vs the reference",
            "picks up {delta}",
            "improves by {delta}",
        ),
        en_forbidden_tokens=("loses time", "drops time", "falls back", "worse than"),
        tts_slot_formats=("subjectSurface", "requiredClaimSurface"),
        notes="Pace improved vs reference; practice/qualifying temporal delta.",
    ),
    "TIME_LOST": _StaticSource(
        legacy_node_id="time_lost",
        race_event_name="time_lost",
        emitter_module="irswitch.events.practice:PracticeEmitter",
        adapter_module="irswitch.events.adapters.timing:timing_race_event_to_envelope",
        polarity="time_lost",
        scope_kind="pace_delta",
        en_pattern_ids=(
            "timing.pace.loss:tight:1",
            "timing.pace.loss:tight:2",
            "timing.pace.loss:tight:3",
            "timing.pace.loss:tight:4",
        ),
        en_claim_surfaces=(
            "loses {delta} against the reference",
            "drops time vs the reference",
            "gives up {delta}",
            "slips by {delta}",
        ),
        en_forbidden_tokens=("finds time", "gains time", "improves by", "picks up"),
        tts_slot_formats=("subjectSurface", "requiredClaimSurface"),
        notes="Pace worsened vs reference; opposite polarity of gain_found.",
    ),
    "HOT_LAP": _StaticSource(
        legacy_node_id="hot_lap",
        race_event_name="hot_lap",
        emitter_module="irswitch.events.quali:QualiEmitter",
        adapter_module="irswitch.events.adapters.timing:timing_race_event_to_envelope",
        polarity="hot_lap",
        scope_kind="lap_attempt",
        en_pattern_ids=(
            "timing.lap.hot:tight:1",
            "timing.lap.hot:tight:2",
            "timing.lap.hot:tight:3",
            "timing.lap.hot:tight:4",
        ),
        en_claim_surfaces=(
            "is on a hot lap",
            "starts flying lap {attemptId}",
            "pushes a hot lap",
            "goes purple on the attempt",
        ),
        en_forbidden_tokens=("completed result", "race finish", "invalid lap claimed as valid"),
        tts_slot_formats=("subjectSurface", "requiredClaimSurface"),
        notes="Active qualifying/practice attempt (hot lap); not a completed result.",
    ),
    "PROJECTED_LAP": _StaticSource(
        legacy_node_id="projected_lap",
        race_event_name="projected_lap",
        emitter_module="irswitch.events.quali:QualiEmitter",
        adapter_module="irswitch.events.adapters.timing:timing_race_event_to_envelope",
        polarity="projected_lap",
        scope_kind="lap_projection",
        en_pattern_ids=(
            "timing.lap.projected:tight:1",
            "timing.lap.projected:tight:2",
            "timing.lap.projected:tight:3",
            "timing.lap.projected:tight:4",
        ),
        en_claim_surfaces=(
            "projects {projectedTime}",
            "is on for {projectedTime}",
            "tracks toward {projectedTime}",
            "shows a {projectedTime} projection",
        ),
        en_forbidden_tokens=("has completed", "personal best confirmed", "checkered"),
        tts_slot_formats=("subjectSurface", "requiredClaimSurface"),
        notes="In-lap projection only; must not claim a completed lap result.",
    ),
    "INVALID_LAP": _StaticSource(
        legacy_node_id="invalid_lap",
        race_event_name="invalid_lap",
        emitter_module="irswitch.events.invalid_lap:InvalidLapEmitter",
        adapter_module="irswitch.events.adapters.exception_extra:invalid_lap_race_event_to_envelope",
        polarity="invalid_lap",
        scope_kind="invalid_lap",
        en_pattern_ids=(
            "incident.invalid_lap:tight:1",
            "incident.invalid_lap:tight:2",
            "incident.invalid_lap:tight:3",
            "incident.invalid_lap:tight:4",
        ),
        en_claim_surfaces=(
            "invalidates lap {lapNumber}",
            "loses lap {lapNumber} to a track limit",
            "has an invalid lap {lapNumber}",
            "wipes lap {lapNumber}",
        ),
        en_forbidden_tokens=("race finish", "wins the race", "personal best stands"),
        tts_slot_formats=("subjectSurface", "requiredClaimSurface"),
        notes="Invalid-lap scope is PRACTICE|QUALIFYING only (not RACE); incident.invalid_lap family.",
    ),
    "SESSION_INTRO_PRACTICE": _StaticSource(
        legacy_node_id="session_intro_practice",
        race_event_name="session_intro_practice",
        emitter_module="irswitch.commentary.session_briefs:SessionBriefsDetector",
        adapter_module="irswitch.commentary.session_briefs:SessionBriefsDetector",
        polarity="session_intro_practice",
        scope_kind="session_intro",
        session_stage="practice",
        requires_active_lineage=True,
        en_pattern_ids=(
            "session.intro.practice:tight:1",
            "session.intro.practice:tight:2",
            "session.intro.practice:tight:3",
            "session.intro.practice:tight:4",
        ),
        en_claim_surfaces=(
            "opens practice",
            "is into practice",
            "starts the practice session",
            "begins practice running",
        ),
        en_forbidden_tokens=("qualifying already decided", "race underway", "checkered"),
        tts_slot_formats=("subjectSurface", "requiredClaimSurface"),
        notes="Practice session opener; inherited facts require active lineage.",
    ),
    "SESSION_INTRO_QUALIFY": _StaticSource(
        legacy_node_id="session_intro_qualify",
        race_event_name="session_intro_qualify",
        emitter_module="irswitch.commentary.session_briefs:SessionBriefsDetector",
        adapter_module="irswitch.commentary.session_briefs:SessionBriefsDetector",
        polarity="session_intro_qualify",
        scope_kind="session_intro",
        session_stage="qualifying",
        requires_active_lineage=True,
        en_pattern_ids=(
            "session.intro.qualifying:tight:1",
            "session.intro.qualifying:tight:2",
            "session.intro.qualifying:tight:3",
            "session.intro.qualifying:tight:4",
        ),
        en_claim_surfaces=(
            "opens qualifying",
            "is into qualifying",
            "starts the qualifying session",
            "begins qualifying running",
        ),
        en_forbidden_tokens=("practice only", "race underway", "checkered"),
        tts_slot_formats=("subjectSurface", "requiredClaimSurface"),
        notes="Qualifying session opener; follows practice in SESSION_STAGE_ORDER.",
    ),
    "SESSION_INTRO_RACE": _StaticSource(
        legacy_node_id="session_intro_race",
        race_event_name="session_intro_race",
        emitter_module="irswitch.commentary.session_briefs:SessionBriefsDetector",
        adapter_module="irswitch.commentary.session_briefs:SessionBriefsDetector",
        polarity="session_intro_race",
        scope_kind="session_intro",
        session_stage="race",
        requires_active_lineage=True,
        en_pattern_ids=(
            "session.intro.race:tight:1",
            "session.intro.race:tight:2",
            "session.intro.race:tight:3",
            "session.intro.race:tight:4",
        ),
        en_claim_surfaces=(
            "opens the race",
            "is into the race",
            "starts the race session",
            "begins race running",
        ),
        en_forbidden_tokens=("practice only", "qualifying still open as live", "unofficial win"),
        tts_slot_formats=("subjectSurface", "requiredClaimSurface"),
        notes="Race session opener; may yield to QUALI_RECAP when quali bag exists.",
    ),
    "QUALI_RECAP": _StaticSource(
        legacy_node_id="quali_recap",
        race_event_name="quali_recap",
        emitter_module="irswitch.race.grid_story:GridStoryFsm",
        adapter_module="irswitch.race.grid_story:GridStoryFsm",
        polarity="quali_recap",
        scope_kind="session_recap",
        session_stage="race",
        requires_active_lineage=True,
        en_pattern_ids=(
            "session.qualifying_recap:tight:1",
            "session.qualifying_recap:tight:2",
            "session.qualifying_recap:tight:3",
            "session.qualifying_recap:tight:4",
        ),
        en_claim_surfaces=(
            "recaps qualifying in P{position}",
            "brings the quali result of P{position}",
            "recalls qualifying at P{position}",
            "carries the quali bag from P{position}",
        ),
        en_forbidden_tokens=("live sector split", "projected as final", "race already won"),
        tts_slot_formats=("subjectSurface", "requiredClaimSurface"),
        notes="Historical qualifying recap into race; active lineage only; not a live result claim.",
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
        if not static.en_pattern_ids:
            raise ContractViolation(f"{wire_id} must curate EN pattern ids")
        if not static.en_claim_surfaces:
            raise ContractViolation(f"{wire_id} must curate EN claim surfaces")
        if not static.tts_slot_formats:
            raise ContractViolation(f"{wire_id} must curate TTS slot formats")
        for pattern_id in static.en_pattern_ids:
            if not pattern_id.startswith(f"{beat_id}:"):
                raise ContractViolation(
                    f"{wire_id} pattern {pattern_id!r} must belong to beat {beat_id}"
                )
        for surface in static.en_claim_surfaces:
            lowered = surface.lower()
            if any(token in lowered for token in static.en_forbidden_tokens):
                raise ContractViolation(
                    f"{wire_id} claim surface {surface!r} contains forbidden token"
                )
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
                session_stage=static.session_stage,
                requires_active_lineage=static.requires_active_lineage,
                en_pattern_ids=static.en_pattern_ids,
                en_claim_surfaces=static.en_claim_surfaces,
                en_forbidden_tokens=static.en_forbidden_tokens,
                tts_slot_formats=static.tts_slot_formats,
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


def session_stage_order_is_monotonic() -> bool:
    """Slice 4 helper: practice → qualifying → race order stays closed and ordered."""

    if SESSION_STAGE_ORDER != ("practice", "qualifying", "race"):
        return False
    by_stage = {
        row.session_stage: row.wire_id
        for row in timing_family_rows()
        if row.wire_id.startswith("SESSION_INTRO_") and row.session_stage is not None
    }
    if set(by_stage) != set(SESSION_STAGE_ORDER):
        return False
    expected = {
        "practice": "SESSION_INTRO_PRACTICE",
        "qualifying": "SESSION_INTRO_QUALIFY",
        "race": "SESSION_INTRO_RACE",
    }
    return by_stage == expected


def inherited_facts_use_active_lineage_only() -> bool:
    """AC helper: session intros/recaps require active lineage; no silent inheritance."""

    recap_rows = tuple(row for row in timing_family_rows() if row.wire_id in SESSION_RECAP_WIRE_IDS)
    if {row.wire_id for row in recap_rows} != set(SESSION_RECAP_WIRE_IDS):
        return False
    if not recap_rows:
        return False
    if not all(row.requires_active_lineage for row in recap_rows):
        return False
    if any(row.session_stage is None for row in recap_rows):
        return False
    # Non-recap timing wires must not silently claim lineage inheritance.
    for row in timing_family_rows():
        if row.wire_id in SESSION_RECAP_WIRE_IDS:
            continue
        if row.requires_active_lineage:
            return False
    return session_stage_order_is_monotonic()


def en_patterns_and_tts_slots_are_curated() -> bool:
    """Slice 5 helper: every wire keeps ≥4 EN patterns, claim surfaces, and TTS slots."""

    rows = timing_family_rows()
    if len(rows) != len(TIMING_WIRE_IDS):
        return False
    for row in rows:
        if len(row.en_pattern_ids) < 4:
            return False
        if len(row.en_claim_surfaces) < 4:
            return False
        if not row.tts_slot_formats:
            return False
        if "subjectSurface" not in row.tts_slot_formats:
            return False
        if "requiredClaimSurface" not in row.tts_slot_formats:
            return False
        if not row.beat_id:
            return False
        if any(not pattern_id.startswith(f"{row.beat_id}:") for pattern_id in row.en_pattern_ids):
            return False
    # Polarity-safe gain vs loss claim surfaces.
    gained = row_for_wire_id("GAIN_FOUND")
    lost = row_for_wire_id("TIME_LOST")
    if set(gained.en_claim_surfaces) & set(lost.en_claim_surfaces):
        return False
    return True
