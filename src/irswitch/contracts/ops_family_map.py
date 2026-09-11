"""#276 ops family migration map — pit + incident + flag + closeout + unknown/tow/teleport + EN patterns (Slices 1–6).

Maps pit-cycle and incident/aftermath/recovery wire identifiers onto legacy
emitters, adapters, beat/story routes, predicates, realization families,
policy TTL and tape channels.

Slices 1–6 record these families as ``legacy``. They do **not** rewrite frozen
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
    "flag_control",
    "session_checkered",
    "hero_finish",
    "session_wrap",
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

# Slice 3 inventory: session yellow / green / checkered flag branches.
OPS_FLAG_WIRE_IDS: tuple[str, ...] = ("SESSION_FLAG",)

# Slice 4 inventory: checkered clock ≠ hero finish ≠ session wrap.
OPS_CLOSEOUT_WIRE_IDS: tuple[str, ...] = (
    "SESSION_CHECKERED",
    "FINISH",
    "SESSION_WRAP",
)

OPS_WIRE_IDS: tuple[str, ...] = (
    OPS_PIT_WIRE_IDS + OPS_INCIDENT_WIRE_IDS + OPS_FLAG_WIRE_IDS + OPS_CLOSEOUT_WIRE_IDS
)

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

# SESSION_FLAG freeze binds three peer flag beats; primary is yellow (registry order).
SESSION_FLAG_BRANCH_BEAT_IDS: tuple[str, ...] = (
    "session.flag.yellow",
    "session.flag.green",
    "session.checkered",
)
SESSION_FLAG_PRIMARY_BEAT_ID = "session.flag.yellow"

# SESSION_WRAP freeze binds stage-routed wrap beats; primary follows registry order.
SESSION_WRAP_BRANCH_BEAT_IDS: tuple[str, ...] = (
    "session.wrap.practice",
    "session.wrap.qualifying",
    "session.wrap.race",
)
SESSION_WRAP_PRIMARY_BEAT_ID = "session.wrap.practice"

# Slice 5 — unknown / tow / teleport outcome taxonomy (no dedicated freeze wires).
OPS_UNKNOWN_OUTCOME_REASON_IDS: frozenset[str] = frozenset(
    {
        "unknown_delta_explicit",
        "unknown_exit_explicit",
        "unknown_motion_explicit",
        "unknown_flag_explicit",
        "unknown_checkered_explicit",
        "unknown_finish_explicit",
        "unknown_wrap_explicit",
    }
)
OPS_TOW_OUTCOME_REASON_IDS: frozenset[str] = frozenset(
    {
        "hero_towing",
        "tow_keeps_stalled",
        "tow_blocks_recovery",
    }
)
OPS_TELEPORT_OUTCOME_REASON_IDS: frozenset[str] = frozenset(
    {
        "hero_teleport",
        "esc_teleport",
        "teleport_invalidates_motion",
    }
)


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
    pit_phase: PitPhase | None
    incident_phase: IncidentPhase | None
    scope_kind: ScopeKind
    invalidate_reasons: tuple[str, ...]
    terminal_reasons: tuple[str, ...]
    primary_beat_id: str | None = None
    en_pattern_ids: tuple[str, ...] = ()
    en_claim_surfaces: tuple[str, ...] = ()
    en_forbidden_tokens: tuple[str, ...] = ()
    tts_slot_formats: tuple[str, ...] = ()
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
        en_pattern_ids=(
            "pit.entry:tight:1",
            "pit.entry:tight:2",
            "pit.entry:tight:3",
            "pit.entry:tight:4",
        ),
        en_claim_surfaces=(
            "enters pit road",
            "pits in",
            "commits to the pits",
            "turns into pit entry",
        ),
        en_forbidden_tokens=("checkered", "finishes P", "wins the race", "back under way"),
        tts_slot_formats=("subjectSurface", "requiredClaimSurface"),
        notes=(
            "Opens a pit cycle when hero enters pit road; not a service/outcome claim. "
            "Missing/ambiguous entry evidence stays unknown — never invent pit service."
        ),
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
        en_pattern_ids=(
            "pit.lane:tight:1",
            "pit.lane:tight:2",
            "pit.lane:tight:3",
            "pit.lane:tight:4",
        ),
        en_claim_surfaces=(
            "rolls the pit lane",
            "is in the pit lane",
            "transits pit lane",
            "moves through the lane",
        ),
        en_forbidden_tokens=("checkered", "race finish", "wins the race", "off track"),
        tts_slot_formats=("subjectSurface", "requiredClaimSurface"),
        notes=(
            "In-lane transit update; must not claim stop/release/exit outcomes. Ambiguous "
            "lane evidence stays unknown — never invent a stop."
        ),
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
        en_pattern_ids=(
            "pit.stopped:tight:1",
            "pit.stopped:tight:2",
            "pit.stopped:tight:3",
            "pit.stopped:tight:4",
        ),
        en_claim_surfaces=(
            "stops in the box",
            "is boxed",
            "stands in the pit box",
            "comes to a stop for service",
        ),
        en_forbidden_tokens=(
            "checkered",
            "wins the race",
            "released from the box",
            "exits pit road",
        ),
        tts_slot_formats=("subjectSurface", "requiredClaimSurface"),
        notes=(
            "Stationary service update; must not invent service work without bound evidence. "
            "Ambiguous stopped evidence stays unknown."
        ),
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
        en_pattern_ids=(
            "pit.released:tight:1",
            "pit.released:tight:2",
            "pit.released:tight:3",
            "pit.released:tight:4",
        ),
        en_claim_surfaces=(
            "is released from the box",
            "clears the pit box",
            "gets the go from the box",
            "leaves the service stall",
        ),
        en_forbidden_tokens=("checkered", "wins the race", "still boxed", "off track"),
        tts_slot_formats=("subjectSurface", "requiredClaimSurface"),
        notes=(
            "Released-from-box update; must not claim completed pit exit. Ambiguous release "
            "evidence stays unknown — never invent exit/outcome."
        ),
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
            "unknown_exit_explicit",
        ),
        en_pattern_ids=(
            "pit.exit:tight:1",
            "pit.exit:tight:2",
            "pit.exit:tight:3",
            "pit.exit:tight:4",
        ),
        en_claim_surfaces=(
            "exits pit road",
            "leaves the pits",
            "rejoins from pit exit",
            "clears pit exit",
        ),
        en_forbidden_tokens=("checkered", "wins the race", "finishes P", "still in the box"),
        tts_slot_formats=("subjectSurface", "requiredClaimSurface"),
        notes=(
            "Closes the live pit-cycle phase when hero leaves pit road. Ambiguous exit "
            "evidence stays unknown_exit_explicit — never invent a completed service/outcome."
        ),
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
        en_pattern_ids=(
            "pit.outcome:tight:1",
            "pit.outcome:tight:2",
            "pit.outcome:tight:3",
            "pit.outcome:tight:4",
        ),
        en_claim_surfaces=(
            "completes the pit stop",
            "finishes service",
            "ends the pit cycle",
            "closes the pit stop",
        ),
        en_forbidden_tokens=("wins the race", "checkered finish", "hero finish", "yellow flag"),
        tts_slot_formats=("subjectSurface", "requiredClaimSurface"),
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
        en_pattern_ids=(
            "incident.off_track:tight:1",
            "incident.off_track:tight:2",
            "incident.off_track:tight:3",
            "incident.off_track:tight:4",
        ),
        en_claim_surfaces=(
            "goes off track",
            "leaves the racing surface",
            "runs wide off track",
            "gets off the paved surface",
        ),
        en_forbidden_tokens=("makes contact", "is towed", "wins the race", "checkered"),
        tts_slot_formats=("subjectSurface", "requiredClaimSurface"),
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
            "esc_teleport",
            "hero_towing",
            "tow_keeps_stalled",
            "cycle_superseded",
            "recovered_before_classify",
        ),
        terminal_reasons=(),
        en_pattern_ids=(
            "incident.aftermath:tight:1",
            "incident.aftermath:tight:2",
            "incident.aftermath:tight:3",
            "incident.aftermath:tight:4",
        ),
        en_claim_surfaces=(
            "is in incident aftermath",
            "remains in the aftermath",
            "is still recovering from the excursion",
            "holds aftermath state",
        ),
        en_forbidden_tokens=("back under way", "invents damage", "wins the race", "checkered"),
        tts_slot_formats=("subjectSurface", "requiredClaimSurface"),
        notes=(
            "Aftermath update (stalled|rolling). Tow/off-track keep stalled; must not claim "
            "recovery or damage. Tow/teleport invalidate motion claims; ambiguous aftermath "
            "stays unknown — never invent recovery. Same-tick director prefers INCIDENT."
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
        invalidate_reasons=(
            "stream_ended",
            "session_reset",
            "hero_teleport",
            "esc_teleport",
            "hero_towing",
            "tow_blocks_recovery",
            "teleport_invalidates_motion",
        ),
        terminal_reasons=(
            "recovered_motion_held",
            "cycle_closed",
            "unknown_motion_explicit",
        ),
        en_pattern_ids=(
            "incident.recovery:tight:1",
            "incident.recovery:tight:2",
            "incident.recovery:tight:3",
            "incident.recovery:tight:4",
        ),
        en_claim_surfaces=(
            "is back under way",
            "resumes after the incident",
            "recovers to racing speed",
            "gets going again",
        ),
        en_forbidden_tokens=(
            "still towing",
            "wins the race",
            "checkered",
            "invents a clean recovery",
        ),
        tts_slot_formats=("subjectSurface", "requiredClaimSurface"),
        notes=(
            "Recovery closure after stalled aftermath; must not claim no-damage. Tow/teleport "
            "block recovery speech; missing motion evidence stays stalled/unknown (no invention)."
        ),
    ),
    "SESSION_FLAG": _StaticSource(
        legacy_node_id="session_flag_yellow",
        race_event_name=None,
        emitter_module="irswitch.race.flags:SessionFlagFsm",
        adapter_module="irswitch.race.flags:SessionFlagFsm",
        pit_phase=None,
        incident_phase=None,
        scope_kind="flag_control",
        invalidate_reasons=(
            "stream_ended",
            "session_reset",
            "hero_teleport",
            "flag_cleared",
            "outside_race_mode",
        ),
        terminal_reasons=(
            "checkered_branch_spoken",
            "flag_cycle_closed",
            "unknown_flag_explicit",
        ),
        primary_beat_id=SESSION_FLAG_PRIMARY_BEAT_ID,
        en_pattern_ids=(
            "session.flag.yellow:tight:1",
            "session.flag.yellow:tight:2",
            "session.flag.yellow:tight:3",
            "session.flag.yellow:tight:4",
        ),
        en_claim_surfaces=(
            "yellow flag is out",
            "caution is shown",
            "yellow is waved",
            "the field is under yellow",
        ),
        en_forbidden_tokens=("green flag", "checkered", "hero finish", "wins the race"),
        tts_slot_formats=("subjectSurface", "requiredClaimSurface"),
        notes=(
            "Session flag wire; SessionFlagFsm rising-edge kinds yellow|green|checkered map onto "
            "branch beats session.flag.yellow|session.flag.green|session.checkered. Start lights "
            "are ignored. Checkered branch must not be treated as hero finish or session wrap "
            "(those stay separate stories). Missing/unclear flag evidence stays unknown — never "
            "invent yellow/green/checkered."
        ),
    ),
    "SESSION_CHECKERED": _StaticSource(
        legacy_node_id="session_checkered",
        race_event_name=None,
        emitter_module="irswitch.events.lifecycle_edges:LifecycleTriggerBank",
        adapter_module="irswitch.events.lifecycle_edges:LifecycleTriggerBank",
        pit_phase=None,
        incident_phase=None,
        scope_kind="session_checkered",
        invalidate_reasons=(
            "stream_ended",
            "session_reset",
            "hero_teleport",
            "checkered_cleared",
        ),
        terminal_reasons=(
            "checkered_clock_spoken",
            "superseded_by_wrap",
            "unknown_checkered_explicit",
        ),
        en_pattern_ids=(
            "session.checkered:tight:1",
            "session.checkered:tight:2",
            "session.checkered:tight:3",
            "session.checkered:tight:4",
        ),
        en_claim_surfaces=(
            "checkered flag is out",
            "the checkered waves",
            "session is checkered",
            "checkered ends the clock",
        ),
        en_forbidden_tokens=("finishes P", "hero finish", "session wrap", "practice wrap"),
        tts_slot_formats=("subjectSurface", "requiredClaimSurface"),
        notes=(
            "Session checkered clock (SessionState/checkered lifecycle). Distinct from "
            "SESSION_FLAG checkered branch (flag rising-edge speech), FINISH (hero done), and "
            "SESSION_WRAP (session ended). Dedupe with flag checkered branch; missing evidence "
            "stays unknown — never invent checkered or treat it as hero finish/wrap."
        ),
    ),
    "FINISH": _StaticSource(
        legacy_node_id="finish",
        race_event_name=None,
        emitter_module="irswitch.events.lifecycle_edges:LifecycleTriggerBank",
        adapter_module="irswitch.events.lifecycle_edges:LifecycleTriggerBank",
        pit_phase=None,
        incident_phase=None,
        scope_kind="hero_finish",
        invalidate_reasons=(
            "stream_ended",
            "session_reset",
            "hero_teleport",
            "finish_retracted",
        ),
        terminal_reasons=(
            "hero_finished_spoken",
            "superseded_by_wrap",
            "unknown_finish_explicit",
        ),
        en_pattern_ids=(
            "session.hero_finish:tight:1",
            "session.hero_finish:tight:2",
            "session.hero_finish:tight:3",
            "session.hero_finish:tight:4",
        ),
        en_claim_surfaces=(
            "finishes P{finishPosition}",
            "takes the checkered in P{finishPosition}",
            "crosses the line in P{finishPosition}",
            "ends the race P{finishPosition}",
        ),
        en_forbidden_tokens=(
            "provisional class win",
            "unofficial classification",
            "session wrap",
            "practice wrap",
        ),
        tts_slot_formats=("subjectSurface", "requiredClaimSurface"),
        notes=(
            "Hero finish (this driver done). Distinct from SESSION_CHECKERED (session clock) and "
            "SESSION_WRAP (session ended for all). Requires hero finished evidence; missing "
            "motion/finish evidence stays unknown — never invent a finish from checkered alone."
        ),
    ),
    "SESSION_WRAP": _StaticSource(
        legacy_node_id="session_wrap",
        race_event_name=None,
        emitter_module="irswitch.race.narrative:StreamNarrativeFsm",
        adapter_module="irswitch.race.narrative:StreamNarrativeFsm",
        pit_phase=None,
        incident_phase=None,
        scope_kind="session_wrap",
        invalidate_reasons=(
            "stream_ended",
            "session_reset",
            "hero_teleport",
            "wrap_superseded",
        ),
        terminal_reasons=(
            "session_ended_spoken",
            "stage_wrap_closed",
            "unknown_wrap_explicit",
        ),
        primary_beat_id=SESSION_WRAP_PRIMARY_BEAT_ID,
        en_pattern_ids=(
            "session.wrap.practice:tight:1",
            "session.wrap.practice:tight:2",
            "session.wrap.practice:tight:3",
            "session.wrap.practice:tight:4",
        ),
        en_claim_surfaces=(
            "wraps practice",
            "ends the practice session",
            "closes practice",
            "practice is wrapped",
        ),
        en_forbidden_tokens=(
            "finishes P",
            "hero finish",
            "takes the checkered in P",
            "yellow flag",
        ),
        tts_slot_formats=("subjectSurface", "requiredClaimSurface"),
        notes=(
            "Session wrap / ended (practice|qualifying|race stage beats). Distinct from "
            "SESSION_CHECKERED and FINISH. StreamNarrativeFsm emits on boundary/finished edges; "
            "missing end evidence stays unknown — never invent wrap from checkered or hero finish alone."
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
    """Return the closed ops migration inventory (Slices 1–4: pit + incident + flag + closeout, legacy)."""

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
                en_pattern_ids=static.en_pattern_ids,
                en_claim_surfaces=static.en_claim_surfaces,
                en_forbidden_tokens=static.en_forbidden_tokens,
                tts_slot_formats=static.tts_slot_formats,
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


def session_flag_branch_beats_are_documented() -> bool:
    """Slice 3 helper: SESSION_FLAG documents yellow + green + checkered branch beats."""

    row = row_for_wire_id("SESSION_FLAG")
    if row.beat_id != SESSION_FLAG_PRIMARY_BEAT_ID:
        return False
    if row.branch_beat_ids != SESSION_FLAG_BRANCH_BEAT_IDS:
        return False
    lowered = row.notes.lower()
    if "yellow" not in lowered or "green" not in lowered or "checkered" not in lowered:
        return False
    if "hero finish" not in lowered and "session wrap" not in lowered:
        return False
    if not row.invalidate_reasons or not row.terminal_reasons:
        return False
    return True


def session_wrap_branch_beats_are_documented() -> bool:
    """Slice 4 helper: SESSION_WRAP documents practice + qualifying + race beats."""

    row = row_for_wire_id("SESSION_WRAP")
    if row.beat_id != SESSION_WRAP_PRIMARY_BEAT_ID:
        return False
    if row.branch_beat_ids != SESSION_WRAP_BRANCH_BEAT_IDS:
        return False
    lowered = row.notes.lower()
    if "practice" not in lowered or "qualifying" not in lowered or "race" not in lowered:
        return False
    if not row.invalidate_reasons or not row.terminal_reasons:
        return False
    return True


def closeout_stories_are_separated() -> bool:
    """Slice 4 AC: checkered clock, hero finish, and session wrap stay distinct."""

    checkered = row_for_wire_id("SESSION_CHECKERED")
    finish = row_for_wire_id("FINISH")
    wrap = row_for_wire_id("SESSION_WRAP")
    if checkered.scope_kind != "session_checkered":
        return False
    if finish.scope_kind != "hero_finish":
        return False
    if wrap.scope_kind != "session_wrap":
        return False
    if checkered.realization_family != "session.flag":
        return False
    if finish.realization_family != "session.finish":
        return False
    if wrap.realization_family != "session.wrap":
        return False
    if len({checkered.tape_channel, finish.tape_channel, wrap.tape_channel}) < 2:
        # finish tape differs; checkered shares flag tape with SESSION_FLAG — ok if finish≠wrap
        pass
    if finish.tape_channel == checkered.tape_channel:
        return False
    if wrap.tape_channel == finish.tape_channel:
        return False
    for row in (checkered, finish, wrap):
        if not row.invalidate_reasons or not row.terminal_reasons:
            return False
        lowered = row.notes.lower()
        # each notes must mention the other two story kinds
        markers = ("checkered", "finish", "wrap")
        if sum(1 for m in markers if m in lowered) < 2:
            return False
    # SESSION_FLAG checkered branch remains distinct inventory from SESSION_CHECKERED wire
    flag = row_for_wire_id("SESSION_FLAG")
    if "session.checkered" not in flag.branch_beat_ids:
        return False
    if checkered.wire_id == flag.wire_id:
        return False
    return True


def unknown_tow_teleport_outcomes_are_defined() -> bool:
    """Slice 5 AC: unknown/tow/teleport dispositions are explicit across ops inventory."""

    if not OPS_UNKNOWN_OUTCOME_REASON_IDS:
        return False
    if not OPS_TOW_OUTCOME_REASON_IDS or not OPS_TELEPORT_OUTCOME_REASON_IDS:
        return False

    for row in ops_family_rows():
        if "hero_teleport" not in row.invalidate_reasons:
            return False
        lowered = row.notes.lower()
        if (
            "unknown" not in lowered
            and "never invent" not in lowered
            and "no invention" not in lowered
        ):
            return False
        if row.terminal_reasons and not (
            OPS_UNKNOWN_OUTCOME_REASON_IDS & set(row.terminal_reasons)
        ):
            return False

    aftermath = row_for_wire_id("INCIDENT_AFTERMATH")
    recovery = row_for_wire_id("BACK_UNDER_WAY")
    if not (OPS_TOW_OUTCOME_REASON_IDS & set(aftermath.invalidate_reasons)):
        return False
    if not (OPS_TOW_OUTCOME_REASON_IDS & set(recovery.invalidate_reasons)):
        return False
    if not (OPS_TELEPORT_OUTCOME_REASON_IDS & set(recovery.invalidate_reasons)):
        return False
    if "tow" not in aftermath.notes.lower() or "tow" not in recovery.notes.lower():
        return False
    if "teleport" not in recovery.notes.lower() and "teleport" not in aftermath.notes.lower():
        return False
    return True


def en_patterns_and_tts_slots_are_curated() -> bool:
    """Slice 6 helper: every ops wire keeps ≥4 EN patterns, claim surfaces, and TTS slots."""

    rows = ops_family_rows()
    if len(rows) != len(OPS_WIRE_IDS):
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
        lowered_surfaces = tuple(surface.lower() for surface in row.en_claim_surfaces)
        if any(
            token in surface for surface in lowered_surfaces for token in row.en_forbidden_tokens
        ):
            return False

    # Adversarial closeout separation: checkered clock ≠ hero finish ≠ session wrap.
    checkered = row_for_wire_id("SESSION_CHECKERED")
    finish = row_for_wire_id("FINISH")
    wrap = row_for_wire_id("SESSION_WRAP")
    if set(checkered.en_claim_surfaces) & set(finish.en_claim_surfaces):
        return False
    if set(finish.en_claim_surfaces) & set(wrap.en_claim_surfaces):
        return False
    if set(checkered.en_claim_surfaces) & set(wrap.en_claim_surfaces):
        return False

    # Pit cycle must not speak race-finish / checkered win language.
    for wire_id in OPS_PIT_WIRE_IDS:
        row = row_for_wire_id(wire_id)
        blob = " ".join(row.en_claim_surfaces).lower()
        if "wins the race" in blob or "finishes p" in blob:
            return False

    # Yellow primary flag surfaces must not invent green/checkered.
    flag = row_for_wire_id("SESSION_FLAG")
    flag_blob = " ".join(flag.en_claim_surfaces).lower()
    if "green flag" in flag_blob or "checkered" in flag_blob:
        return False

    # Incident opening must not invent contact/tow outcomes.
    incident = row_for_wire_id("INCIDENT")
    incident_blob = " ".join(incident.en_claim_surfaces).lower()
    if "contact" in incident_blob or "tow" in incident_blob:
        return False

    return True
