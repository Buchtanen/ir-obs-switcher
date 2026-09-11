"""#277 context family migration map — session/stream leftovers + filler + weather/field + bio style (Slices 1–6).

Maps remaining non-race session/stream, filler, weather and field wire identifiers onto legacy
emitters, adapters, beat/story routes, predicates, realization families, policy
TTL and tape channels.

Slices 1–6 record these wires as ``legacy``. They do **not** rewrite frozen
``docs/v2.0.0/machine/*`` hashes and do **not** flip ``FAMILY_ROUTE``.
Session intros/recaps stay owned by the timing map; session wrap/checkered/finish
stay owned by the ops / race-outcome maps. Beat-only silence fillers are documented without inventing freeze wires.
Weather/field wires require explicit current vs historical currency;
forecast weather is not speakable inventory.
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
    "weather_brief",
    "weather_change",
    "field_fact",
    "sof_brief",
    "bio_style",
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


WeatherCurrency = Literal["current", "historical"]

# Slice 3 inventory: weather + field context with explicit currency / revalidation.
CONTEXT_WEATHER_FIELD_WIRE_IDS: tuple[str, ...] = (
    "WEATHER_BRIEF",
    "WEATHER_CHANGE",
    "FIELD_FACT",
    "SOF_BRIEF",
)


# Slice 4 inventory: HR pressure as optional style fact (not sport truth).
CONTEXT_BIO_STYLE_WIRE_IDS: tuple[str, ...] = ("HR_PRESSURE_RISING",)

# Compatibility alias — not speakable inventory (do not invent a freeze row).
CONTEXT_BIO_ALIAS_WIRE_IDS: tuple[str, ...] = ("HEART_RATE",)

# Slice 5 — long-silence eligibility + fatigue (impulse, not a freeze wire).
CONTEXT_LONG_SILENCE_IMPULSE_ID = "LONG_SILENCE_ELAPSED"
CONTEXT_LONG_SILENCE_MS = 33_000
CONTEXT_LONG_SILENCE_BUSY_LANES: tuple[str, ...] = (
    "building",
    "committed",
    "speaking",
    "stopping",
)
# Beats that may be selected from a long-silence impulse (filler + weather/field briefs).
CONTEXT_LONG_SILENCE_ELIGIBLE_BEAT_IDS: tuple[str, ...] = (
    "filler.out_lap",
    "filler.in_lap",
    "filler.parade_lap",
    "filler.garage",
    "filler.lobby",
    "filler.quiet_track",
    "session.weather_brief",
    "session.field_fact",
    "session.sof_brief",
)
CONTEXT_LONG_SILENCE_OUTCOMES: tuple[str, ...] = (
    "selected",
    "source_guard_failed",
    "no_candidate",
    "busy_lane",
)
CONTEXT_LONG_SILENCE_FATIGUE_AXES: tuple[str, ...] = (
    "node",
    "semantic",
    "edge",
    "path",
)

# Slice 6 — EN-only curation + reject generic forced filler (inventory vs packaged cards).
CONTEXT_EN_AUDITED_LANGUAGE = "en"
CONTEXT_EN_LEGACY_DISPOSITION = "reject_unreviewed_not_migrate"
CONTEXT_EN_CURATED_BEAT_IDS: tuple[str, ...] = (
    "stream.started",
    "session.preview.next",
    "session.enter_car.practice",
    "session.enter_car.qualifying",
    "session.enter_car.race",
    "session.final_lap",
    "filler.out_lap",
    "filler.in_lap",
    "filler.parade_lap",
    "filler.garage",
    "filler.lobby",
    "filler.quiet_track",
    "session.weather_brief",
    "session.weather_change",
    "session.field_fact",
    "session.sof_brief",
    "bio.pressure",
)
CONTEXT_EN_PATTERN_IDS_BY_BEAT_ID: dict[str, tuple[str, ...]] = {
    "stream.started": (
        "stream.started:tight:1",
        "stream.started:tight:2",
        "stream.started:tight:3",
        "stream.started:tight:4",
    ),
    "session.preview.next": (
        "session.preview.next:tight:1",
        "session.preview.next:tight:2",
        "session.preview.next:tight:3",
        "session.preview.next:tight:4",
    ),
    "session.enter_car.practice": (
        "session.enter_car.practice:tight:1",
        "session.enter_car.practice:tight:2",
        "session.enter_car.practice:tight:3",
        "session.enter_car.practice:tight:4",
    ),
    "session.enter_car.qualifying": (
        "session.enter_car.qualifying:tight:1",
        "session.enter_car.qualifying:tight:2",
        "session.enter_car.qualifying:tight:3",
        "session.enter_car.qualifying:tight:4",
    ),
    "session.enter_car.race": (
        "session.enter_car.race:tight:1",
        "session.enter_car.race:tight:2",
        "session.enter_car.race:tight:3",
        "session.enter_car.race:tight:4",
    ),
    "session.final_lap": (
        "session.final_lap:tight:1",
        "session.final_lap:tight:2",
        "session.final_lap:tight:3",
        "session.final_lap:tight:4",
    ),
    "filler.out_lap": (
        "filler.out_lap:tight:1",
        "filler.out_lap:tight:2",
        "filler.out_lap:tight:3",
        "filler.out_lap:tight:4",
    ),
    "filler.in_lap": (
        "filler.in_lap:tight:1",
        "filler.in_lap:tight:2",
        "filler.in_lap:tight:3",
        "filler.in_lap:tight:4",
    ),
    "filler.parade_lap": (
        "filler.parade_lap:tight:1",
        "filler.parade_lap:tight:2",
        "filler.parade_lap:tight:3",
        "filler.parade_lap:tight:4",
    ),
    "filler.garage": (
        "filler.garage:tight:1",
        "filler.garage:tight:2",
        "filler.garage:tight:3",
        "filler.garage:tight:4",
    ),
    "filler.lobby": (
        "filler.lobby:tight:1",
        "filler.lobby:tight:2",
        "filler.lobby:tight:3",
        "filler.lobby:tight:4",
    ),
    "filler.quiet_track": (
        "filler.quiet_track:tight:1",
        "filler.quiet_track:tight:2",
        "filler.quiet_track:tight:3",
        "filler.quiet_track:tight:4",
    ),
    "session.weather_brief": (
        "session.weather_brief:tight:1",
        "session.weather_brief:tight:2",
        "session.weather_brief:tight:3",
        "session.weather_brief:tight:4",
    ),
    "session.weather_change": (
        "session.weather_change:tight:1",
        "session.weather_change:tight:2",
        "session.weather_change:tight:3",
        "session.weather_change:tight:4",
    ),
    "session.field_fact": (
        "session.field_fact:tight:1",
        "session.field_fact:tight:2",
        "session.field_fact:tight:3",
        "session.field_fact:tight:4",
    ),
    "session.sof_brief": (
        "session.sof_brief:tight:1",
        "session.sof_brief:tight:2",
        "session.sof_brief:tight:3",
        "session.sof_brief:tight:4",
    ),
    "bio.pressure": (
        "bio.pressure:tight:1",
        "bio.pressure:tight:2",
        "bio.pressure:tight:3",
        "bio.pressure:tight:4",
    ),
}
CONTEXT_EN_PATTERN_IDS: tuple[str, ...] = tuple(
    pattern_id
    for beat_id in CONTEXT_EN_CURATED_BEAT_IDS
    for pattern_id in CONTEXT_EN_PATTERN_IDS_BY_BEAT_ID[beat_id]
)
# Spoken phrases that must not be used as forced generic filler openers.
CONTEXT_GENERIC_FORCED_FILLER_PHRASES: tuple[str, ...] = (
    "as we wait",
    "nothing happening",
    "nothing to report",
    "filling time",
    "just filling",
    "stay tuned for nothing",
    "dead air",
    "meanwhile nothing",
    "generic update",
)


CONTEXT_WIRE_IDS: tuple[str, ...] = (
    CONTEXT_SESSION_WIRE_IDS
    + CONTEXT_FILLER_WIRE_IDS
    + CONTEXT_WEATHER_FIELD_WIRE_IDS
    + CONTEXT_BIO_STYLE_WIRE_IDS
)

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
    "HEART_RATE": "compatibility_alias/not_speakable",
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
    "WEATHER_BRIEF": _StaticSource(
        legacy_node_id="weather_brief",
        race_event_name=None,
        emitter_module="irswitch.commentary.session_briefs:SessionBriefsDetector",
        adapter_module="irswitch.commentary.session_briefs:SessionBriefsDetector",
        lifecycle_phase=None,
        scope_kind="weather_brief",
        invalidate_reasons=("stream_ended", "session_reset", "weather_stale", "forecast_rejected"),
        terminal_reasons=(),
        notes=(
            "Session weather brief from confirmed current facts (live/session source). "
            "Currency must be explicit: current (live|session) vs historical framing. "
            "Forecast weather is not speakable — silence_clock source_guard rejects "
            "forecast. Never invent dry→sunny or causal track effects."
        ),
    ),
    "WEATHER_CHANGE": _StaticSource(
        legacy_node_id="weather_change",
        race_event_name="weather_change",
        emitter_module="irswitch.race.observer:RaceObserver",
        adapter_module="irswitch.race.observer:RaceObserver",
        lifecycle_phase=None,
        scope_kind="weather_change",
        invalidate_reasons=(
            "stream_ended",
            "session_reset",
            "change_superseded",
            "forecast_rejected",
        ),
        terminal_reasons=(),
        notes=(
            "Material weather revision between current snapshots. Revalidation "
            "compares oldFactId→newFactId; speak only confirmed current metrics. "
            "Historical recap must be framed historical_only — never present "
            "forecast or unobserved track effect as live weather."
        ),
    ),
    "FIELD_FACT": _StaticSource(
        legacy_node_id="field_fact",
        race_event_name="field_fact",
        emitter_module="irswitch.race.observer:RaceObserver",
        adapter_module="irswitch.race.observer:RaceObserver",
        lifecycle_phase=None,
        scope_kind="field_fact",
        invalidate_reasons=("stream_ended", "session_reset", "field_stale", "roster_reset"),
        terminal_reasons=(),
        notes=(
            "Confirmed field context fact (W_field allowlist). Current roster/"
            "field evidence only unless explicitly historical. Revalidate when "
            "roster or SoF sample changes. Never extrapolate beyond the selected "
            "fact or invent race outcomes."
        ),
    ),
    "SOF_BRIEF": _StaticSource(
        legacy_node_id="sof_brief",
        race_event_name=None,
        emitter_module="irswitch.commentary.session_briefs:SessionBriefsDetector",
        adapter_module="irswitch.commentary.session_briefs:SessionBriefsDetector",
        lifecycle_phase=None,
        scope_kind="sof_brief",
        invalidate_reasons=("stream_ended", "session_reset", "roster_reset", "sof_stale"),
        terminal_reasons=(),
        notes=(
            "Field strength / SoF brief (field.strength). Current official sample "
            "only; historical SoF must be framed historical. Never judge quality "
            "or predict results from SoF alone."
        ),
    ),
    "HR_PRESSURE_RISING": _StaticSource(
        legacy_node_id="hr_pressure_rising",
        race_event_name="hr_pressure",
        emitter_module="irswitch.events.hr_pressure:HrPressureEmitter",
        adapter_module="irswitch.events.adapters.bio:bio_race_event_to_envelope",
        lifecycle_phase=None,
        scope_kind="bio_style",
        invalidate_reasons=(
            "stream_ended",
            "session_reset",
            "sensor_stale",
            "hr_disabled",
            "style_suppressed",
        ),
        terminal_reasons=(),
        notes=(
            "Optional style fact only (director resolve_emotion / use_hr_emotion). "
            "Maps bio.hr_state band/bpm — never medical diagnosis, never invent "
            "emotion cause, never change sport truth or invent performance claims. "
            "HEART_RATE remains compatibility_alias outside speakable inventory. "
            "Missing/stale sensor → suppress style, do not invent pressure."
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
    """Return the closed context migration inventory (Slices 1–6: session leftovers + filler + weather/field + bio style, legacy)."""

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


def weather_and_field_wires_are_documented() -> bool:
    """Slice 3 helper: weather/field freeze set stays closed with currency notes."""

    if CONTEXT_WEATHER_FIELD_WIRE_IDS != (
        "WEATHER_BRIEF",
        "WEATHER_CHANGE",
        "FIELD_FACT",
        "SOF_BRIEF",
    ):
        return False
    expect = {
        "WEATHER_BRIEF": ("session.weather_brief", "weather_brief", "session.weather"),
        "WEATHER_CHANGE": ("session.weather_change", "weather_change", "session.weather"),
        "FIELD_FACT": ("session.field_fact", "field_fact", "session.context"),
        "SOF_BRIEF": ("session.sof_brief", "sof_brief", "session.context"),
    }
    for wire_id, (beat_id, scope_kind, family) in expect.items():
        row = row_for_wire_id(wire_id)
        if row.beat_id != beat_id:
            return False
        if row.scope_kind != scope_kind:
            return False
        if row.realization_family != family:
            return False
        if row.policy_id != "context":
            return False
        if not row.invalidate_reasons:
            return False
        if row.lifecycle_phase is not None:
            return False
    return True


def weather_and_field_currency_is_explicit() -> bool:
    """AC helper: weather/history must be current or historical; forecast rejected."""

    if not weather_and_field_wires_are_documented():
        return False
    weather_brief = row_for_wire_id("WEATHER_BRIEF")
    weather_change = row_for_wire_id("WEATHER_CHANGE")
    field_fact = row_for_wire_id("FIELD_FACT")
    sof = row_for_wire_id("SOF_BRIEF")
    for row in (weather_brief, weather_change, field_fact, sof):
        lowered = row.notes.lower()
        if "current" not in lowered:
            return False
        if "historical" not in lowered:
            return False
    # Forecast must be explicitly non-speakable on weather wires.
    for row in (weather_brief, weather_change):
        lowered = row.notes.lower()
        if "forecast" not in lowered:
            return False
        if "not speakable" not in lowered and "reject" not in lowered and "never" not in lowered:
            return False
    # Field must forbid inventing race outcomes / extrapolation.
    if "never" not in field_fact.notes.lower() and "not invent" not in field_fact.notes.lower():
        return False
    if "never" not in sof.notes.lower() and "not" not in sof.notes.lower():
        return False
    return True


def bio_style_wires_are_documented() -> bool:
    """Slice 4 helper: HR pressure style wire stays closed; HEART_RATE stays alias."""

    if CONTEXT_BIO_STYLE_WIRE_IDS != ("HR_PRESSURE_RISING",):
        return False
    if CONTEXT_BIO_ALIAS_WIRE_IDS != ("HEART_RATE",):
        return False
    if "HEART_RATE" in CONTEXT_WIRE_IDS:
        return False
    if CONTEXT_OWNED_ELSEWHERE.get("HEART_RATE") != "compatibility_alias/not_speakable":
        return False
    row = row_for_wire_id("HR_PRESSURE_RISING")
    if row.beat_id != "bio.pressure":
        return False
    if row.scope_kind != "bio_style":
        return False
    if row.realization_family != "bio.context":
        return False
    if row.policy_id != "context":
        return False
    if row.lifecycle_phase is not None:
        return False
    if not row.invalidate_reasons:
        return False
    if "style_suppressed" not in row.invalidate_reasons and "style" not in " ".join(
        row.invalidate_reasons
    ):
        # require style_suppressed specifically
        if "style_suppressed" not in row.invalidate_reasons:
            return False
    lowered = row.notes.lower()
    if "optional style" not in lowered and "style fact" not in lowered:
        return False
    return True


def bio_cannot_invent_sport_truth() -> bool:
    """AC helper: bio/HR style must not invent sport truth, medical, or causal emotion."""

    if not bio_style_wires_are_documented():
        return False
    row = row_for_wire_id("HR_PRESSURE_RISING")
    lowered = row.notes.lower()
    if "sport truth" not in lowered and "never change sport" not in lowered:
        return False
    if "medical" not in lowered:
        return False
    if "emotion" not in lowered and "cause" not in lowered:
        return False
    if (
        "never invent" not in lowered
        and "do not invent" not in lowered
        and "not invent" not in lowered
    ):
        return False
    if "performance" not in lowered:
        return False
    # Alias must remain non-speakable.
    if "HEART_RATE" in set(CONTEXT_WIRE_IDS):
        return False
    return True


def long_silence_eligibility_is_documented() -> bool:
    """Slice 5 helper: long-silence impulse eligibility stays closed and silence-safe."""

    if CONTEXT_LONG_SILENCE_IMPULSE_ID != "LONG_SILENCE_ELAPSED":
        return False
    if CONTEXT_LONG_SILENCE_MS != 33_000:
        return False
    if CONTEXT_LONG_SILENCE_BUSY_LANES != (
        "building",
        "committed",
        "speaking",
        "stopping",
    ):
        return False
    # Impulse must not be invented as a freeze wire.
    if CONTEXT_LONG_SILENCE_IMPULSE_ID in CONTEXT_WIRE_IDS:
        return False
    # Eligible beat set includes filler beats + weather/field silence briefs.
    required = set(CONTEXT_FILLER_BEAT_IDS) | {
        "session.weather_brief",
        "session.field_fact",
        "session.sof_brief",
    }
    if set(CONTEXT_LONG_SILENCE_ELIGIBLE_BEAT_IDS) != required:
        return False
    outcomes = set(CONTEXT_LONG_SILENCE_OUTCOMES)
    if not {"selected", "source_guard_failed", "no_candidate", "busy_lane"} <= outcomes:
        return False
    # Silence-capable outcomes must remain documented.
    if "no_candidate" not in outcomes or "source_guard_failed" not in outcomes:
        return False
    # Parade pad notes already admit silence; keep AC linked.
    if not filler_may_resolve_to_silence():
        return False
    return True


def long_silence_fatigue_is_documented() -> bool:
    """Slice 5 helper: graph fatigue axes apply to silence-selected context/filler."""

    if not long_silence_eligibility_is_documented():
        return False
    if CONTEXT_LONG_SILENCE_FATIGUE_AXES != ("node", "semantic", "edge", "path"):
        return False
    # Fatigue is observational inventory only — no FAMILY_ROUTE flip for bio/session.
    # Re-check parade notes still forbid forced filler under fatigue pressure.
    row = row_for_wire_id("PARADE_PAD")
    lowered = row.notes.lower()
    if "silence" not in lowered:
        return False
    if "never force" not in lowered and "not force" not in lowered:
        return False
    return True


def filler_can_result_in_silence() -> bool:
    """AC helper: long-silence path may yield silence instead of forced filler speech."""

    if not long_silence_eligibility_is_documented():
        return False
    if not long_silence_fatigue_is_documented():
        return False
    if not filler_may_resolve_to_silence():
        return False
    # Explicit silence outcomes on the long-silence path.
    if "no_candidate" not in CONTEXT_LONG_SILENCE_OUTCOMES:
        return False
    if "source_guard_failed" not in CONTEXT_LONG_SILENCE_OUTCOMES:
        return False
    if "busy_lane" not in CONTEXT_LONG_SILENCE_OUTCOMES:
        return False
    return True


def context_en_content_is_curated() -> bool:
    """Slice 6 helper: context realization cards stay EN-only and fully curated."""

    if CONTEXT_EN_AUDITED_LANGUAGE != "en":
        return False
    registry = _load("realization-pattern-cards.json")
    if str(registry.get("legacyDisposition") or "") != CONTEXT_EN_LEGACY_DISPOSITION:
        return False
    cards = {
        str(row["id"]): row
        for row in _rows(registry.get("cards"), "realization-pattern-cards.cards")
    }
    if not CONTEXT_EN_CURATED_BEAT_IDS:
        return False
    if set(CONTEXT_EN_PATTERN_IDS_BY_BEAT_ID) != set(CONTEXT_EN_CURATED_BEAT_IDS):
        return False
    seen: set[str] = set()
    for beat_id in CONTEXT_EN_CURATED_BEAT_IDS:
        pattern_ids = CONTEXT_EN_PATTERN_IDS_BY_BEAT_ID[beat_id]
        if len(pattern_ids) < 4:
            return False
        for pattern_id in pattern_ids:
            if pattern_id in seen:
                return False
            seen.add(pattern_id)
            if not pattern_id.startswith(f"{beat_id}:"):
                return False
            card = cards.get(pattern_id)
            if card is None:
                return False
            if str(card.get("auditedLanguage") or "") != "en":
                return False
            if card.get("enabled") is not True:
                return False
            if str(card.get("beatId") or "") != beat_id:
                return False
            pattern = str(card.get("pattern") or "")
            if not pattern.strip():
                return False
            # No Czech diacritics / non-EN inventory leakage in curated cards.
            if any(ch in pattern for ch in "áčďéěíňóřšťúůýžÁČĎÉĚÍŇÓŘŠŤÚŮÝŽ"):
                return False
    # Catalog must not keep non-EN enabled cards for curated beats.
    for card in cards.values():
        beat_id = str(card.get("beatId") or "")
        if beat_id not in CONTEXT_EN_CURATED_BEAT_IDS:
            continue
        if card.get("enabled") is True and str(card.get("auditedLanguage") or "") != "en":
            return False
    if set(CONTEXT_EN_PATTERN_IDS) != seen:
        return False
    return True


def generic_forced_filler_is_removed() -> bool:
    """Slice 6 AC helper: no generic forced filler — silence preferred when empty."""

    if not context_en_content_is_curated():
        return False
    if not filler_can_result_in_silence():
        return False
    if not CONTEXT_GENERIC_FORCED_FILLER_PHRASES:
        return False
    registry = _load("realization-pattern-cards.json")
    cards = _rows(registry.get("cards"), "realization-pattern-cards.cards")
    curated = set(CONTEXT_EN_PATTERN_IDS)
    for card in cards:
        if str(card.get("id") or "") not in curated:
            continue
        blob = " ".join(
            str(card.get(key) or "") for key in ("pattern", "id", "family", "beatId")
        ).lower()
        for phrase in CONTEXT_GENERIC_FORCED_FILLER_PHRASES:
            if phrase in blob:
                return False
    # Parade inventory notes remain the anti-force contract.
    row = row_for_wire_id("PARADE_PAD")
    lowered = row.notes.lower()
    if "never force" not in lowered and "not force" not in lowered:
        return False
    if "silence" not in lowered:
        return False
    return True
