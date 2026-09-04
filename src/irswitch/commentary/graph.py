"""JSON sequence graph: nodes, edges, TTS constraints. No external graph DB."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any, TypeVar

from irswitch.commentary.style_cards import load_style_cards
from irswitch.events.audience import COMMENTARY_ONLY_EVENTS
from irswitch.events.envelope import EventEnvelope
from irswitch.events.event_catalog import catalog_entries, catalog_fallbacks

GRAPH_VERSION = 4
SCENARIO_GRAPH_VERSION = 3
STATEFUL_GRAPH_VERSION = 2
LEGACY_GRAPH_VERSION = 1
SUPPORTED_GRAPH_VERSIONS = frozenset(
    {
        LEGACY_GRAPH_VERSION,
        STATEFUL_GRAPH_VERSION,
        SCENARIO_GRAPH_VERSION,
        GRAPH_VERSION,
    }
)
ALLOWED_HR_STATES = frozenset({"unknown", "calm", "focused", "pushing", "high"})
ALLOWED_GRAPH_MODES = frozenset({"practice", "qualify", "race", "warmup"})
_MODE_ALIASES = {
    "practice": "practice",
    "qualify": "qualify",
    "qualifying": "qualify",
    "race": "race",
    "warmup": "warmup",
    "generic": "warmup",
}
ALLOWED_SLOT_TYPES = frozenset({"int", "time", "delta", "gap", "name", "label"})
ALLOWED_SSML = frozenset({"break", "emphasis"})
VARIANT_KEYS = ("neutral", "calm", "focused", "pushing", "high")
SUPPORTED_LOCALES = ("en", "cs")
PREPARED_STAGES = frozenset(
    {
        "STREAM_LOBBY_INTRO",
        "SESSION_EVENT_INTRO",
        "IN_CAR_PREP",
        "OUT_LAP",
        "GRID_PREP",
        "FORMATION_OR_LIGHTS",
        "LIVE_SESSION",
        "SESSION_CONCLUSION",
        "BETWEEN_SESSIONS",
    }
)
PREPARED_FACT_IDS = frozenset(
    {
        "track",
        "layout",
        "city",
        "country",
        "circuit_length",
        "turn_count",
        "track_type",
        "track_direction",
        "sky",
        "air_temperature",
        "track_temperature",
        "wind_speed",
        "precipitation",
        "surface_wetness",
        "rubber_state",
        "field_size",
        "class_field_size",
        "overall_sof",
        "class_sof",
        "ai_count",
        "ai_ratio",
        "circulating_cars",
        "traffic_band",
        "session",
        "class_position",
        "hero_position",
        "engine_state",
        "rollout_state",
        "out_lap",
        "qualifying_position",
        "grid_position",
        "start_position",
        "highest_rated_driver",
        "start_mode",
        "formation_state",
        "distance_to_start",
        "start_ready",
        "start_set",
        "hr_band",
        "completed_laps",
        "best_lap_seconds",
        "finish_position",
        "result_status",
        "result_relation",
    }
)

_DEFAULT_GRAPH = Path(__file__).resolve().parent / "data" / "sequence_graph.json"


class EditorialPolicy(StrEnum):
    CRITICAL_RESULT = "critical_result"
    LIVE_RELATION = "live_relation"
    STORY_RESULT = "story_result"
    PERIODIC_CONTEXT = "periodic_context"
    ONCE_PER_SCOPE = "once_per_scope"


class SemanticPolicy(StrEnum):
    UNIQUE_RESULT = "unique_result"
    POSITION_RESULT = "position_result"
    BATTLE_RELATION = "battle_relation"
    PIT_STORY = "pit_story"
    LAP_RESULT = "lap_result"
    CONTEXT_FACT = "context_fact"
    WEATHER_FACT = "weather_fact"
    ONCE_SCOPE = "once_scope"
    SCENARIO_EPISODE = "scenario_episode"


class Criticality(StrEnum):
    CRITICAL = "critical"
    STORY = "story"
    CONTEXT = "context"


class MaterialChangePolicy(StrEnum):
    OCCURRENCE = "occurrence"
    POSITION_CHANGE = "position_change"
    GAP_INTENSITY = "gap_intensity"
    STORY_PHASE = "story_phase"
    LAP_RESULT = "lap_result"
    CONTEXT_VALUE = "context_value"
    WEATHER_THRESHOLD = "weather_threshold"
    ONCE = "once"
    SCENARIO_BEAT = "scenario_beat"


class PreparedRelation(StrEnum):
    NONE = "none"
    CONTEXT = "context"
    STAGE_TRANSITION = "stage_transition"
    CONFIRMED_RESULT = "confirmed_result"
    UNCONFIRMED_RESULT = "unconfirmed_result"
    FINISH_BETTER_THAN_QUALIFYING = "finish_better_than_qualifying"
    FINISH_EQUAL_TO_QUALIFYING = "finish_equal_to_qualifying"
    FINISH_WORSE_THAN_QUALIFYING = "finish_worse_than_qualifying"
    FINISH_BETTER_THAN_GRID = "finish_better_than_grid"
    FINISH_EQUAL_TO_GRID = "finish_equal_to_grid"
    FINISH_WORSE_THAN_GRID = "finish_worse_than_grid"


class PreparedForbiddenClaim(StrEnum):
    CAUSE = "cause"
    PREDICTION = "prediction"
    BLAME = "blame"
    NATIONALITY = "nationality"
    RESULT_CERTAINTY = "result_certainty"
    SETUP_IMPROVEMENT = "setup_improvement"
    DIFFICULTY = "difficulty"


class EdgeIdentityPolicy(StrEnum):
    SAME_CORRELATION = "same_correlation"
    SAME_PARENT_STORY = "same_parent_story"
    CAUSED_BY_PARENT_STORY = "caused_by_parent_story"
    SAME_RUN = "same_run"
    ANY = "any"


class BeatRole(StrEnum):
    ROOT = "root"
    DEVELOPMENT = "development"
    CLOSURE = "closure"
    TERMINAL = "terminal"


class PrimaryRelation(StrEnum):
    TRACK_EXCURSION = "track_excursion"
    CONTACT = "contact"
    CONTROL = "control"
    PACE = "pace"
    PIT_RETURN = "pit_return"


class ScenarioCause(StrEnum):
    UNKNOWN = "unknown"
    LOSS_OF_CONTROL = "loss_of_control"
    SLIDE = "slide"
    SPIN = "spin"
    CONTACT_VEHICLE = "contact_vehicle"
    CONTACT_BARRIER = "contact_barrier"
    BRAKING_OVERSHOOT = "braking_overshoot"
    AVOIDANCE_MANEUVER = "avoidance_maneuver"


class ScenarioOutcome(StrEnum):
    UNKNOWN = "unknown"
    BACK_ON_TRACK = "back_on_track"
    MOTION_RESTORED = "motion_restored"
    PIT_RETURN_OBSERVED = "pit_return_observed"
    CONTROL_REGAINED = "control_regained"
    NORMAL_RUNNING_RESUMED = "normal_running_resumed"
    PACE_LOSS_SUSTAINED = "pace_loss_sustained"
    LIMPING_TO_PITS = "limping_to_pits"
    PIT_FOR_REPAIRS = "pit_for_repairs"
    TOW_STARTED = "tow_started"
    RESET_TO_PITS = "reset_to_pits"
    STOPPED_AFTER_EXCURSION = "stopped_after_excursion"
    RUN_CONTINUATION_LOST = "run_continuation_lost"


class TemporalRelation(StrEnum):
    BEFORE_CORE = "before_core"
    DURING_CORE = "during_core"
    AFTER_CORE = "after_core"


class EvidenceLevel(StrEnum):
    CONFIRMED = "CONFIRMED"
    PROBABLE_HIGH = "PROBABLE_HIGH"
    PROBABLE_LOW = "PROBABLE_LOW"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class NodeEditorial:
    policy: EditorialPolicy
    semantic_policy: SemanticPolicy
    criticality: Criticality
    repeat_weight: float = 1.0
    silence_affinity: float = 0.0
    material_change_policy: MaterialChangePolicy = MaterialChangePolicy.CONTEXT_VALUE


@dataclass(frozen=True)
class EdgeEditorial:
    transition_bonus: int = 0
    closure: bool = False
    repeat_weight: float = 1.0


_LEGACY_NODE_EDITORIAL = NodeEditorial(
    policy=EditorialPolicy.PERIODIC_CONTEXT,
    semantic_policy=SemanticPolicy.CONTEXT_FACT,
    criticality=Criticality.CONTEXT,
)


@dataclass(frozen=True)
class SlotSpec:
    name: str
    type: str
    example: str


@dataclass(frozen=True)
class TtsLimits:
    max_chars: int = 160
    max_seconds: float = 13.0
    ssml_allowed: tuple[str, ...] = ("break", "emphasis")
    require_terminal_punct: bool = True


@dataclass(frozen=True)
class GraphNodeMatch:
    scenario_ids: tuple[str, ...] = ()
    beat_roles: tuple[BeatRole, ...] = ()
    primary_relations: tuple[PrimaryRelation, ...] = ()
    causes: tuple[ScenarioCause, ...] = ()
    outcomes: tuple[ScenarioOutcome, ...] = ()
    temporal_relations: tuple[TemporalRelation, ...] = ()
    evidence_levels: tuple[EvidenceLevel, ...] = ()
    minimum_confidence: float = 0.0

    @property
    def specificity(self) -> int:
        return sum(
            bool(value)
            for value in (
                self.scenario_ids,
                self.beat_roles,
                self.primary_relations,
                self.causes,
                self.outcomes,
                self.temporal_relations,
                self.evidence_levels,
            )
        ) + int(self.minimum_confidence > 0.0)

    def matches(
        self,
        *,
        scenario_id: str | None,
        beat_role: str | None,
        primary_relation: str | None,
        cause: str | None,
        outcome: str | None,
        temporal_relation: str | None,
        evidence_level: str | None,
        confidence: float,
    ) -> bool:
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
            return False
        return (
            _matches_text(self.scenario_ids, scenario_id)
            and _matches_enum(self.beat_roles, beat_role)
            and _matches_enum(self.primary_relations, primary_relation)
            and _matches_enum(self.causes, cause)
            and _matches_enum(self.outcomes, outcome)
            and _matches_enum(self.temporal_relations, temporal_relation)
            and _matches_enum(self.evidence_levels, evidence_level)
            and math.isfinite(confidence)
            and 0.0 <= confidence <= 1.0
            and confidence >= self.minimum_confidence
        )


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    identity: EdgeIdentityPolicy = EdgeIdentityPolicy.SAME_CORRELATION
    min_gap_s: float = 0.0
    max_gap_s: float = 60.0
    editorial: EdgeEditorial = field(default_factory=EdgeEditorial)

    @property
    def same_correlation(self) -> bool:
        """Compatibility view used by graph-v1/v2 callers."""
        return self.identity is EdgeIdentityPolicy.SAME_CORRELATION

    @property
    def legacy_identity_compatible(self) -> bool:
        """Whether correlation-only consumers have enough context to evaluate this edge."""
        return self.identity in {EdgeIdentityPolicy.SAME_CORRELATION, EdgeIdentityPolicy.ANY}


@dataclass(frozen=True)
class PreparedNodeContract:
    allowed_stages: tuple[str, ...]
    tier: int
    terminal: bool
    required_facts: tuple[str, ...]
    optional_facts: tuple[str, ...]
    relation: PreparedRelation
    intent: dict[str, str]
    forbidden_claims: tuple[PreparedForbiddenClaim, ...]
    anchors: dict[str, tuple[str, ...]]

    def canonical(self) -> dict[str, object]:
        """Stable content-policy payload used by prepared plan identity."""
        return {
            "allowed_stages": list(self.allowed_stages),
            "tier": self.tier,
            "terminal": self.terminal,
            "required_facts": list(self.required_facts),
            "optional_facts": list(self.optional_facts),
            "relation": self.relation.value,
            "intent": dict(sorted(self.intent.items())),
            "forbidden_claims": [item.value for item in self.forbidden_claims],
            "anchors": {locale: list(self.anchors[locale]) for locale in sorted(self.anchors)},
        }


@dataclass
class GraphNode:
    id: str
    family: str
    event_types: tuple[str, ...]
    phases: tuple[str, ...]
    speak_priority: int
    cooldown_s: float
    slots: tuple[SlotSpec, ...]
    hr_states: tuple[str, ...]
    notes: str = ""
    tts: TtsLimits = field(default_factory=TtsLimits)
    variants: dict[str, dict[str, tuple[str, ...]]] = field(default_factory=dict)
    modes: tuple[str, ...] = ()
    branch: str = ""
    style_cards: tuple[str, ...] = ()
    editorial: NodeEditorial = _LEGACY_NODE_EDITORIAL
    match: GraphNodeMatch = field(default_factory=GraphNodeMatch)
    prepared: PreparedNodeContract | None = None

    def variant_bucket(self, locale: str, emotion: str) -> tuple[str, ...]:
        locale_map = self.variants.get(locale) or {}
        picked = self._bucket_from(locale_map, emotion)
        if picked:
            return picked
        if locale != "en":
            return self._bucket_from(self.variants.get("en") or {}, emotion)
        return ()

    @staticmethod
    def _bucket_from(locale_map: dict[str, tuple[str, ...]], emotion: str) -> tuple[str, ...]:
        if emotion in locale_map and locale_map[emotion]:
            return locale_map[emotion]
        # Mock / unfilled emotion cells fall back to neutral instead of silence.
        if locale_map.get("neutral"):
            return locale_map["neutral"]
        return ()


@dataclass
class SequenceGraph:
    version: int
    locales: tuple[str, ...]
    default_tts: TtsLimits
    nodes: dict[str, GraphNode]
    edges: tuple[GraphEdge, ...]

    def node(self, node_id: str) -> GraphNode | None:
        return self.nodes.get(node_id)

    def nodes_for(
        self,
        event_type: str,
        phase: str,
        *,
        mode: str | None = None,
        branch: str | None = None,
        scenario_id: str | None = None,
        beat_role: str | None = None,
        primary_relation: str | None = None,
        cause: str | None = None,
        outcome: str | None = None,
        temporal_relation: str | None = None,
        evidence_level: str | None = None,
        confidence: float = 1.0,
    ) -> list[GraphNode]:
        key = event_type.strip().upper()
        phase_key = phase.strip().upper()
        pool = [
            node
            for node in self.nodes.values()
            if key in node.event_types and phase_key in node.phases
        ]
        typed = [
            node
            for node in pool
            if node.match.matches(
                scenario_id=scenario_id,
                beat_role=beat_role,
                primary_relation=primary_relation,
                cause=cause,
                outcome=outcome,
                temporal_relation=temporal_relation,
                evidence_level=evidence_level,
                confidence=confidence,
            )
        ]
        if self.version >= SCENARIO_GRAPH_VERSION:
            # Exclude other session modes before specificity. Never let a more
            # specific Race node hide the truthful Practice/Qualifying fallback.
            wanted_mode = normalize_graph_mode(mode)
            typed = [node for node in typed if not node.modes or wanted_mode in node.modes]
        if typed:
            specificity = max(node.match.specificity for node in typed)
            typed = [node for node in typed if node.match.specificity == specificity]
        selected = _select_mode_branch(typed, mode=mode, branch=branch)
        selected.sort(key=lambda item: item.speak_priority, reverse=True)
        return selected

    def nodes_for_envelope(self, envelope: EventEnvelope) -> list[GraphNode]:
        return self.nodes_for(
            envelope.event_type,
            envelope.phase,
            mode=envelope.mode,
            branch=envelope.metrics.get("branch"),
            **scenario_selectors(envelope.metrics, envelope.confidence),
        )

    def outgoing(self, node_id: str) -> list[GraphEdge]:
        return [edge for edge in self.edges if edge.source == node_id]

    def incoming(self, node_id: str) -> list[GraphEdge]:
        return [edge for edge in self.edges if edge.target == node_id]

    def unfilled_cells(self) -> list[tuple[str, str, str]]:
        """Return (node_id, locale, emotion) cells with no authored text."""
        missing: list[tuple[str, str, str]] = []
        for node in self.nodes.values():
            if node.prepared is not None:
                continue
            for locale in self.locales:
                locale_map = node.variants.get(locale) or {}
                for emotion in node.hr_states:
                    bucket = emotion if emotion != "unknown" else "neutral"
                    texts = locale_map.get(bucket) or locale_map.get(emotion) or ()
                    if not texts:
                        missing.append((node.id, locale, bucket))
        return missing


def scenario_selectors(metrics: dict[str, Any], confidence: float = 1.0) -> dict[str, Any]:
    names = {
        "scenario_id": "scenarioId",
        "beat_role": "beatRole",
        "primary_relation": "primaryRelation",
        "cause": "cause",
        "outcome": "outcome",
        "temporal_relation": "temporalRelation",
        "evidence_level": "evidenceLevel",
    }
    return {
        **{key: metrics.get(camel, metrics.get(key)) for key, camel in names.items()},
        "confidence": confidence,
    }


def default_graph_path() -> Path:
    return _DEFAULT_GRAPH


def load_sequence_graph(path: Path | None = None) -> SequenceGraph:
    raw = json.loads((path or default_graph_path()).read_text(encoding="utf-8"))
    return parse_sequence_graph(raw)


def parse_sequence_graph(raw: dict[str, Any]) -> SequenceGraph:
    errors = validate_graph_document(raw)
    if errors:
        raise ValueError("invalid sequence graph: " + "; ".join(errors[:8]))
    default_tts = _tts_limits(raw.get("default_tts") or {})
    locales = tuple(str(item) for item in raw.get("locales") or SUPPORTED_LOCALES)
    nodes_raw = raw.get("nodes") or {}
    version = int(raw.get("version") or GRAPH_VERSION)
    nodes: dict[str, GraphNode] = {}
    for node_id, payload in nodes_raw.items():
        nodes[str(node_id)] = _parse_node(str(node_id), payload, default_tts, locales)
    edges = tuple(
        GraphEdge(
            source=str(item["from"]),
            target=str(item["to"]),
            identity=_parse_edge_identity(item.get("when"), version=version),
            min_gap_s=float((item.get("when") or {}).get("min_gap_s", 0.0)),
            max_gap_s=float((item.get("when") or {}).get("max_gap_s", 60.0)),
            editorial=_parse_edge_editorial(item.get("editorial")),
        )
        for item in raw.get("edges") or []
    )
    return SequenceGraph(
        version=version,
        locales=locales,
        default_tts=default_tts,
        nodes=nodes,
        edges=edges,
    )


def validate_graph_document(raw: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(raw, dict):
        return ["graph must be an object"]
    version = raw.get("version")
    if version not in SUPPORTED_GRAPH_VERSIONS:
        errors.append(f"unsupported version: {version!r}")
    locales = raw.get("locales") or []
    if not isinstance(locales, list) or not locales:
        errors.append("locales must be a non-empty list")
    else:
        for locale in locales:
            if locale not in SUPPORTED_LOCALES:
                errors.append(f"unsupported locale: {locale!r}")
    known_events = set(catalog_entries()) | set(catalog_fallbacks()) | COMMENTARY_ONLY_EVENTS
    nodes = raw.get("nodes")
    if not isinstance(nodes, dict) or not nodes:
        errors.append("nodes must be a non-empty object")
        return errors
    for node_id, payload in nodes.items():
        errors.extend(_validate_node(str(node_id), payload, known_events, version=version))
    for index, edge in enumerate(raw.get("edges") or []):
        if not isinstance(edge, dict):
            errors.append(f"edges[{index}] must be an object")
            continue
        src = edge.get("from")
        dst = edge.get("to")
        if src not in nodes:
            errors.append(f"edges[{index}] unknown from: {src!r}")
        if dst not in nodes:
            errors.append(f"edges[{index}] unknown to: {dst!r}")
        errors.extend(
            _validate_edge_when(
                index,
                edge.get("when"),
                version=version,
                source=nodes.get(src),
                target=nodes.get(dst),
            )
        )
        errors.extend(_validate_edge_editorial(index, edge.get("editorial")))
    return errors


def _validate_node(
    node_id: str,
    payload: Any,
    known_events: set[str],
    *,
    version: object,
) -> list[str]:
    errors: list[str] = []
    prefix = f"nodes.{node_id}"
    if not isinstance(payload, dict):
        return [f"{prefix} must be an object"]
    cards = payload.get("style_cards", [])
    known_cards = {card.id for card in load_style_cards()}
    if not isinstance(cards, list) or any(
        not isinstance(card, str) or card not in known_cards for card in cards
    ):
        errors.append(f"{prefix}.style_cards must reference known card IDs")
    event_types = payload.get("event_types") or []
    if not event_types:
        errors.append(f"{prefix}.event_types is required")
    for event_type in event_types:
        key = str(event_type).upper()
        if key not in known_events:
            errors.append(f"{prefix} unknown event type: {event_type!r}")
    phases = payload.get("phases") or []
    if not phases:
        errors.append(f"{prefix}.phases is required")
    for phase in phases:
        if str(phase).upper() not in {
            "ENTER",
            "ACTIVE",
            "UPDATE",
            "RESULT",
            "EXIT",
            "COMPACT",
            "SUSPEND",
            "RESUME",
        }:
            errors.append(f"{prefix} invalid phase: {phase!r}")
    for slot in payload.get("slots") or []:
        if not isinstance(slot, dict) or not slot.get("name"):
            errors.append(f"{prefix} slot missing name")
            continue
        slot_type = str(slot.get("type") or "")
        if slot_type not in ALLOWED_SLOT_TYPES:
            errors.append(f"{prefix} slot {slot.get('name')!r} bad type: {slot_type!r}")
    for hr_state in payload.get("hr_states") or []:
        if hr_state not in ALLOWED_HR_STATES:
            errors.append(f"{prefix} bad hr_state: {hr_state!r}")
    for mode in payload.get("modes") or []:
        normalized = normalize_graph_mode(str(mode))
        if normalized is None or normalized not in ALLOWED_GRAPH_MODES:
            errors.append(f"{prefix} bad mode: {mode!r}")
    branch = payload.get("branch")
    if branch is not None and branch != "" and not isinstance(branch, str):
        errors.append(f"{prefix}.branch must be a string")
    priority = payload.get("speak_priority")
    if not isinstance(priority, int) or priority < 0:
        errors.append(f"{prefix}.speak_priority must be a non-negative int")
    errors.extend(
        _validate_node_editorial(
            prefix,
            payload.get("editorial"),
            required=isinstance(version, int) and version >= STATEFUL_GRAPH_VERSION,
        )
    )
    editorial_raw = payload.get("editorial")
    scenario_policy = isinstance(editorial_raw, dict) and (
        editorial_raw.get("semantic_policy") == SemanticPolicy.SCENARIO_EPISODE.value
        or editorial_raw.get("material_change_policy") == MaterialChangePolicy.SCENARIO_BEAT.value
    )
    errors.extend(
        _validate_node_match(
            prefix,
            payload.get("match"),
            version=version,
            required=scenario_policy,
        )
    )
    errors.extend(
        _validate_prepared_contract(
            prefix,
            payload.get("prepared"),
            version=version,
            event_types=event_types,
        )
    )
    return errors


_PREPARED_FIELDS = frozenset(
    {
        "allowed_stages",
        "tier",
        "terminal",
        "required_facts",
        "optional_facts",
        "relation",
        "intent",
        "forbidden_claims",
        "anchors",
    }
)


def _validate_prepared_contract(
    prefix: str,
    raw: object,
    *,
    version: object,
    event_types: object,
) -> list[str]:
    path = f"{prefix}.prepared"
    if raw is None:
        return []
    if version != GRAPH_VERSION:
        return [f"{path} requires graph v{GRAPH_VERSION}"]
    if not isinstance(raw, dict):
        return [f"{path} must be an object"]
    errors: list[str] = []
    for key in sorted(set(raw) - _PREPARED_FIELDS):
        errors.append(f"{path} unknown field: {key}")
    normalized_events = (
        {str(item).upper() for item in event_types}
        if isinstance(event_types, list)
        else set()
    )
    if normalized_events not in ({"PREPARED_FILLER"}, {"PREPARED_FATAL"}):
        errors.append(f"{path} requires exactly PREPARED_FILLER or PREPARED_FATAL")

    stages = raw.get("allowed_stages")
    if not isinstance(stages, list) or not stages:
        errors.append(f"{path}.allowed_stages must be a non-empty list")
    else:
        for stage in stages:
            if not isinstance(stage, str) or stage not in PREPARED_STAGES:
                errors.append(f"{path}.allowed_stages contains unsupported stage: {stage!r}")
        if len(stages) != len({str(item) for item in stages}):
            errors.append(f"{path}.allowed_stages must not contain duplicates")

    tier = raw.get("tier")
    if isinstance(tier, bool) or not isinstance(tier, int) or not 0 <= tier <= 9:
        errors.append(f"{path}.tier must be an int in range 0..9")
    if not isinstance(raw.get("terminal"), bool):
        errors.append(f"{path}.terminal must be a bool")

    required = _validate_prepared_fact_list(errors, raw, path, "required_facts")
    optional = _validate_prepared_fact_list(errors, raw, path, "optional_facts")
    overlap = set(required) & set(optional)
    if overlap:
        errors.append(f"{path} facts overlap: {sorted(overlap)}")

    relation = raw.get("relation")
    allowed_relations = {item.value for item in PreparedRelation}
    if not isinstance(relation, str) or relation not in allowed_relations:
        errors.append(f"{path}.relation must be one of {sorted(allowed_relations)}")

    intent = raw.get("intent")
    if not isinstance(intent, dict):
        errors.append(f"{path}.intent must be an object")
    else:
        for locale in SUPPORTED_LOCALES:
            value = intent.get(locale)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{path}.intent.{locale} must be a non-empty string")
        for locale in sorted(set(intent) - set(SUPPORTED_LOCALES)):
            errors.append(f"{path}.intent has unsupported locale: {locale!r}")

    claims = raw.get("forbidden_claims")
    allowed_claims = {item.value for item in PreparedForbiddenClaim}
    if not isinstance(claims, list):
        errors.append(f"{path}.forbidden_claims must be a list")
    else:
        for claim in claims:
            if not isinstance(claim, str) or claim not in allowed_claims:
                errors.append(f"{path}.forbidden_claims contains unsupported claim: {claim!r}")
        if len(claims) != len({str(item) for item in claims}):
            errors.append(f"{path}.forbidden_claims must not contain duplicates")

    anchors = raw.get("anchors")
    if not isinstance(anchors, dict):
        errors.append(f"{path}.anchors must be an object")
    else:
        for locale in SUPPORTED_LOCALES:
            values = anchors.get(locale)
            if not isinstance(values, list) or not 1 <= len(values) <= 5:
                errors.append(f"{path}.anchors.{locale} must contain 1..5 strings")
                continue
            if any(not isinstance(value, str) or not value.strip() for value in values):
                errors.append(f"{path}.anchors.{locale} values must be non-empty strings")
            if len(values) != len({str(value) for value in values}):
                errors.append(f"{path}.anchors.{locale} must not contain duplicates")
        for locale in sorted(set(anchors) - set(SUPPORTED_LOCALES)):
            errors.append(f"{path}.anchors has unsupported locale: {locale!r}")
    return errors


def _validate_prepared_fact_list(
    errors: list[str], raw: dict[str, Any], path: str, name: str
) -> tuple[str, ...]:
    value = raw.get(name)
    if not isinstance(value, list):
        errors.append(f"{path}.{name} must be a list")
        return ()
    parsed: list[str] = []
    for item in value:
        if not isinstance(item, str) or item not in PREPARED_FACT_IDS:
            errors.append(f"{path}.{name} contains unsupported fact: {item!r}")
            continue
        parsed.append(item)
    if len(value) != len({str(item) for item in value}):
        errors.append(f"{path}.{name} must not contain duplicates")
    return tuple(parsed)


_MATCH_FIELDS = frozenset(
    {
        "scenario_id",
        "beat_role",
        "primary_relation",
        "cause",
        "outcome",
        "temporal_relation",
        "evidence_level",
        "minimum_confidence",
    }
)


def _validate_node_match(
    prefix: str,
    raw: object,
    *,
    version: object,
    required: bool,
) -> list[str]:
    path = f"{prefix}.match"
    if raw is None:
        return [f"{path} is required for scenario policies"] if required else []
    if not isinstance(version, int) or version < SCENARIO_GRAPH_VERSION:
        return [f"{path} requires graph v{SCENARIO_GRAPH_VERSION}+"]
    if not isinstance(raw, dict):
        return [f"{path} must be an object"]
    errors: list[str] = []
    for key in sorted(set(raw) - _MATCH_FIELDS):
        errors.append(f"{path} unknown match field: {key}")
    _validate_match_selector(errors, raw, path, "scenario_id", None)
    _validate_match_selector(errors, raw, path, "beat_role", BeatRole)
    _validate_match_selector(errors, raw, path, "primary_relation", PrimaryRelation)
    _validate_match_selector(errors, raw, path, "cause", ScenarioCause)
    _validate_match_selector(errors, raw, path, "outcome", ScenarioOutcome)
    _validate_match_selector(errors, raw, path, "temporal_relation", TemporalRelation)
    _validate_match_selector(errors, raw, path, "evidence_level", EvidenceLevel)
    _validate_float_range(
        errors,
        raw,
        path,
        "minimum_confidence",
        0.0,
        1.0,
        default=0.0,
    )
    return errors


def _validate_match_selector(
    errors: list[str],
    raw: dict[str, Any],
    path: str,
    name: str,
    enum_type: type[StrEnum] | None,
) -> None:
    if name not in raw:
        return
    value = raw[name]
    values = value if isinstance(value, list) else [value]
    if not values:
        errors.append(f"{path}.{name} must not be empty")
        return
    allowed = {item.value for item in enum_type} if enum_type is not None else None
    for item in values:
        if not isinstance(item, str):
            errors.append(f"{path}.{name} values must be strings")
        elif allowed is not None and item not in allowed:
            errors.append(f"{path}.{name} must use one of {sorted(allowed)}")
        elif enum_type is None and not re.fullmatch(r"[a-z][a-z0-9_]*", item):
            errors.append(f"{path}.{name} must use lowercase snake-case IDs")


def _parse_node_match(raw: object) -> GraphNodeMatch:
    if not isinstance(raw, dict):
        return GraphNodeMatch()
    return GraphNodeMatch(
        scenario_ids=_string_selector(raw.get("scenario_id")),
        beat_roles=_enum_selector(raw.get("beat_role"), BeatRole),
        primary_relations=_enum_selector(raw.get("primary_relation"), PrimaryRelation),
        causes=_enum_selector(raw.get("cause"), ScenarioCause),
        outcomes=_enum_selector(raw.get("outcome"), ScenarioOutcome),
        temporal_relations=_enum_selector(raw.get("temporal_relation"), TemporalRelation),
        evidence_levels=_enum_selector(raw.get("evidence_level"), EvidenceLevel),
        minimum_confidence=float(raw.get("minimum_confidence", 0.0)),
    )


def _string_selector(raw: object) -> tuple[str, ...]:
    if raw is None:
        return ()
    values = raw if isinstance(raw, list) else [raw]
    return tuple(str(value) for value in values)


_Enum = TypeVar("_Enum", bound=StrEnum)


def _enum_selector(raw: object, enum_type: type[_Enum]) -> tuple[_Enum, ...]:
    if raw is None:
        return ()
    values = raw if isinstance(raw, list) else [raw]
    return tuple(enum_type(str(value)) for value in values)


def _matches_text(allowed: tuple[str, ...], value: str | None) -> bool:
    return not allowed or value in allowed


def _matches_enum(allowed: tuple[StrEnum, ...], value: str | None) -> bool:
    return not allowed or value in allowed


def _parse_node(
    node_id: str,
    payload: dict[str, Any],
    default_tts: TtsLimits,
    locales: tuple[str, ...],
) -> GraphNode:
    slots = tuple(
        SlotSpec(
            name=str(item["name"]),
            type=str(item.get("type") or "label"),
            example=str(item.get("example") if item.get("example") is not None else ""),
        )
        for item in payload.get("slots") or []
    )
    tts_raw = payload.get("tts") or {}
    tts = _tts_limits(tts_raw, default_tts) if tts_raw else default_tts
    variants = _parse_variants(payload.get("variants") or {}, locales)
    return GraphNode(
        id=node_id,
        style_cards=tuple(payload.get("style_cards") or ()),
        family=str(payload.get("family") or ""),
        event_types=tuple(str(item).upper() for item in payload.get("event_types") or []),
        phases=tuple(str(item).upper() for item in payload.get("phases") or []),
        speak_priority=int(payload.get("speak_priority") or 0),
        cooldown_s=float(payload.get("cooldown_s") or 0.0),
        slots=slots,
        hr_states=tuple(str(item) for item in payload.get("hr_states") or ("unknown",)),
        notes=str(payload.get("notes") or ""),
        tts=tts,
        variants=variants,
        modes=_parse_modes(payload.get("modes")),
        branch=str(payload.get("branch") or "").strip(),
        editorial=_parse_node_editorial(payload.get("editorial")),
        match=_parse_node_match(payload.get("match")),
        prepared=_parse_prepared_contract(payload.get("prepared")),
    )


def _parse_prepared_contract(raw: object) -> PreparedNodeContract | None:
    if not isinstance(raw, dict):
        return None
    return PreparedNodeContract(
        allowed_stages=tuple(str(item) for item in raw["allowed_stages"]),
        tier=int(raw["tier"]),
        terminal=bool(raw["terminal"]),
        required_facts=tuple(str(item) for item in raw["required_facts"]),
        optional_facts=tuple(str(item) for item in raw["optional_facts"]),
        relation=PreparedRelation(str(raw["relation"])),
        intent={str(key): str(value) for key, value in raw["intent"].items()},
        forbidden_claims=tuple(
            PreparedForbiddenClaim(str(item)) for item in raw["forbidden_claims"]
        ),
        anchors={
            str(locale): tuple(str(item) for item in values)
            for locale, values in raw["anchors"].items()
        },
    )


def _parse_node_editorial(raw: object) -> NodeEditorial:
    if not isinstance(raw, dict):
        return _LEGACY_NODE_EDITORIAL
    return NodeEditorial(
        policy=EditorialPolicy(str(raw["policy"])),
        semantic_policy=SemanticPolicy(str(raw["semantic_policy"])),
        criticality=Criticality(str(raw["criticality"])),
        repeat_weight=float(raw.get("repeat_weight", 1.0)),
        silence_affinity=float(raw.get("silence_affinity", 0.0)),
        material_change_policy=MaterialChangePolicy(str(raw["material_change_policy"])),
    )


def _parse_edge_editorial(raw: object) -> EdgeEditorial:
    if not isinstance(raw, dict):
        return EdgeEditorial()
    return EdgeEditorial(
        transition_bonus=int(raw.get("transition_bonus", 0)),
        closure=bool(raw.get("closure", False)),
        repeat_weight=float(raw.get("repeat_weight", 1.0)),
    )


def _parse_edge_identity(raw: object, *, version: int) -> EdgeIdentityPolicy:
    when = raw if isinstance(raw, dict) else {}
    if isinstance(version, int) and version >= SCENARIO_GRAPH_VERSION:
        return EdgeIdentityPolicy(str(when["identity"]))
    return (
        EdgeIdentityPolicy.SAME_CORRELATION
        if bool(when.get("same_correlation", True))
        else EdgeIdentityPolicy.ANY
    )


def _validate_edge_when(
    index: int,
    raw: object,
    *,
    version: object,
    source: object,
    target: object,
) -> list[str]:
    path = f"edges[{index}].when"
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        return [f"{path} must be an object"]
    errors: list[str] = []
    if isinstance(version, int) and version >= SCENARIO_GRAPH_VERSION:
        identity = raw.get("identity")
        allowed = {item.value for item in EdgeIdentityPolicy}
        if identity is None:
            errors.append(f"{path}.identity is required for graph v{SCENARIO_GRAPH_VERSION}+")
        elif not isinstance(identity, str) or identity not in allowed:
            errors.append(f"{path}.identity must be one of {sorted(allowed)}")
        elif identity == EdgeIdentityPolicy.ANY.value and (
            _raw_node_is_track_excursion(source) or _raw_node_is_track_excursion(target)
        ):
            errors.append(f"{path}.identity 'any' is forbidden for track-excursion edges")
        if "same_correlation" in raw:
            errors.append(f"{path}.same_correlation is legacy-only; use identity")
    else:
        same_correlation = raw.get("same_correlation", True)
        if not isinstance(same_correlation, bool):
            errors.append(f"{path}.same_correlation must be a bool")

    minimum = raw.get("min_gap_s", 0.0)
    maximum = raw.get("max_gap_s", 60.0)
    for name, value in (("min_gap_s", minimum), ("max_gap_s", maximum)):
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(float(value))
            or float(value) < 0.0
        ):
            errors.append(f"{path}.{name} must be a non-negative number")
    if (
        isinstance(minimum, (int, float))
        and not isinstance(minimum, bool)
        and isinstance(maximum, (int, float))
        and not isinstance(maximum, bool)
        and float(minimum) > float(maximum)
    ):
        errors.append(f"{path}.min_gap_s must not exceed max_gap_s")
    return errors


def _raw_node_is_track_excursion(raw: object) -> bool:
    if not isinstance(raw, dict):
        return False
    editorial = raw.get("editorial")
    if isinstance(editorial, dict) and editorial.get("semantic_policy") == "scenario_episode":
        return True
    match = raw.get("match")
    if not isinstance(match, dict):
        return False
    relation = match.get("primary_relation")
    values = relation if isinstance(relation, list) else [relation]
    return PrimaryRelation.TRACK_EXCURSION.value in values


def _validate_node_editorial(prefix: str, raw: object, *, required: bool) -> list[str]:
    path = f"{prefix}.editorial"
    if raw is None:
        return [f"{path} is required for graph v{GRAPH_VERSION}"] if required else []
    if not isinstance(raw, dict):
        return [f"{path} must be an object"]
    errors: list[str] = []
    _validate_enum_field(errors, raw, path, "policy", EditorialPolicy)
    _validate_enum_field(errors, raw, path, "semantic_policy", SemanticPolicy)
    _validate_enum_field(errors, raw, path, "criticality", Criticality)
    _validate_enum_field(
        errors,
        raw,
        path,
        "material_change_policy",
        MaterialChangePolicy,
    )
    _validate_float_range(errors, raw, path, "repeat_weight", 0.0, 2.0, default=1.0)
    _validate_float_range(errors, raw, path, "silence_affinity", 0.0, 1.0, default=0.0)
    return errors


def _validate_edge_editorial(index: int, raw: object) -> list[str]:
    path = f"edges[{index}].editorial"
    if raw is None:
        return []
    if not isinstance(raw, dict):
        return [f"{path} must be an object"]
    errors: list[str] = []
    bonus = raw.get("transition_bonus", 0)
    if isinstance(bonus, bool) or not isinstance(bonus, int) or not 0 <= bonus <= 20:
        errors.append(f"{path}.transition_bonus must be an int in range 0..20")
    closure = raw.get("closure", False)
    if not isinstance(closure, bool):
        errors.append(f"{path}.closure must be a bool")
    _validate_float_range(errors, raw, path, "repeat_weight", 0.0, 2.0, default=1.0)
    return errors


def _validate_enum_field(
    errors: list[str],
    raw: dict[str, Any],
    path: str,
    name: str,
    enum_type: type[StrEnum],
) -> None:
    value = raw.get(name)
    allowed = {item.value for item in enum_type}
    if value not in allowed:
        errors.append(f"{path}.{name} must be one of {sorted(allowed)}")


def _validate_float_range(
    errors: list[str],
    raw: dict[str, Any],
    path: str,
    name: str,
    minimum: float,
    maximum: float,
    *,
    default: float,
) -> None:
    value = raw.get(name, default)
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not minimum <= float(value) <= maximum
    ):
        errors.append(f"{path}.{name} must be a number in range {minimum:g}..{maximum:g}")


def _parse_variants(
    raw: dict[str, Any],
    locales: tuple[str, ...],
) -> dict[str, dict[str, tuple[str, ...]]]:
    parsed: dict[str, dict[str, tuple[str, ...]]] = {}
    for locale in locales:
        locale_raw = raw.get(locale) or {}
        buckets: dict[str, tuple[str, ...]] = {}
        if isinstance(locale_raw, dict):
            for key in VARIANT_KEYS:
                texts = locale_raw.get(key) or []
                buckets[key] = tuple(str(item) for item in texts if str(item).strip())
        parsed[locale] = buckets
    return parsed


def _tts_limits(raw: dict[str, Any], base: TtsLimits | None = None) -> TtsLimits:
    seed = base or TtsLimits()
    allowed = tuple(
        str(item)
        for item in raw.get("ssml_allowed", seed.ssml_allowed)
        if str(item) in ALLOWED_SSML
    )
    return TtsLimits(
        max_chars=int(raw.get("max_chars", seed.max_chars)),
        max_seconds=float(raw.get("max_seconds", seed.max_seconds)),
        ssml_allowed=allowed or seed.ssml_allowed,
        require_terminal_punct=bool(raw.get("require_terminal_punct", seed.require_terminal_punct)),
    )


def normalize_graph_mode(mode: str | None) -> str | None:
    """Map envelope overlay_mode / JSON aliases onto graph ``modes`` tokens."""
    if mode is None:
        return None
    text = str(mode).strip().lower()
    if not text or text == "unknown":
        return None
    return _MODE_ALIASES.get(text)


def _parse_modes(raw: object) -> tuple[str, ...]:
    if not raw:
        return ()
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        return ()
    seen: list[str] = []
    for item in items:
        normalized = normalize_graph_mode(str(item))
        if normalized and normalized not in seen:
            seen.append(normalized)
    return tuple(seen)


def _select_mode_branch(
    pool: list[GraphNode],
    *,
    mode: str | None,
    branch: str | None,
) -> list[GraphNode]:
    """Ladder: mode+branch → branch → mode → unrestricted. First non-empty tier wins."""
    want_mode = normalize_graph_mode(mode)
    want_branch = str(branch).strip() if branch else ""

    def mode_ok(node: GraphNode) -> bool:
        if not node.modes:
            return True
        if want_mode is None:
            return False
        return want_mode in node.modes

    def branch_eq(node: GraphNode) -> bool:
        return bool(node.branch) and node.branch == want_branch

    def unbranched(node: GraphNode) -> bool:
        return not node.branch

    if want_branch:
        exact = [node for node in pool if mode_ok(node) and branch_eq(node)]
        if exact:
            return exact
        by_branch = [node for node in pool if branch_eq(node)]
        if by_branch:
            return by_branch
    by_mode = [node for node in pool if mode_ok(node) and unbranched(node)]
    if by_mode:
        return by_mode
    return [node for node in pool if not node.modes and unbranched(node)]
