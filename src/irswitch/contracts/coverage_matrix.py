"""Implementation-time audit of the frozen v2 event-family coverage matrix."""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from .primitives import (
    BroadcastContext,
    ContractViolation,
    Stage,
    VehiclePhase,
    canonical_sha256,
)
from .resources import packaged_schema_bytes

EVENT_CLASSES = frozenset({"speakable", "visual_only", "compatibility_alias"})
CLAIM_FAMILIES = ("transition", "identity", "expiry", "counterfactual")
FORBIDDEN_LEGACY_TRIGGERS = frozenset(
    {
        "STREAM_START",
        "SESSION_INTRO_PRACTICE",
        "SESSION_INTRO_QUALIFY",
        "SESSION_INTRO_RACE",
        "SESSION_WRAP",
    }
)
FREEDOM_ORDER = ("tight", "balanced", "loose")
ENABLED_FREEDOM = frozenset({"tight"})
STAGE_VALUES = frozenset(item.value for item in Stage)
CONTEXT_VALUES = frozenset(item.value for item in BroadcastContext)
PHASE_VALUES = frozenset(item.value for item in VehiclePhase)
FORBIDDEN_SCENE_TOKENS = frozenset(
    {
        "ON TRACK",
        "ON_TRACK",
        "IRACING",
        "iRacing",
        "GARAGE",
        "LOBBY",
        "REPLAY",
    }
)


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise ContractViolation(f"{label} must be a JSON object")
    return value


def _rows(value: object, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ContractViolation(f"{label} must be a JSON object list")
    return value


def _unique_ids(rows: list[dict[str, Any]], field: str, label: str) -> list[str]:
    values = [str(row[field]) for row in rows]
    folded = [item.casefold() for item in values]
    if len(folded) != len(set(folded)):
        raise ContractViolation(f"duplicate {label} id")
    return values


def _load(name: str, override: dict[str, Any] | None) -> dict[str, Any]:
    if override is not None:
        return _object(override, name)
    return _object(json.loads(packaged_schema_bytes(name)), name)


def _id_tuple(value: object, label: str) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ContractViolation(f"{label} must contain strings")
    return tuple(value)


def _enum_tuple(values: object, allowed: frozenset[str], label: str) -> tuple[str, ...]:
    items = _id_tuple(values, label)
    unknown = [item for item in items if item not in allowed]
    scene = [item for item in items if item in FORBIDDEN_SCENE_TOKENS or " " in item]
    if scene:
        raise ContractViolation(f"{label} uses a raw OBS scene name")
    if unknown:
        raise ContractViolation(f"{label} uses an unknown enum")
    return items


def _has_cycle(node_ids: set[str], edges: list[dict[str, Any]]) -> bool:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        adjacency[str(edge["fromBeatId"])].append(str(edge["toBeatId"]))
    visiting: set[str] = set()
    seen: set[str] = set()

    def walk(node: str) -> bool:
        if node in visiting:
            return True
        if node in seen:
            return False
        visiting.add(node)
        if any(walk(target) for target in adjacency[node]):
            return True
        visiting.remove(node)
        seen.add(node)
        return False

    return any(walk(node) for node in node_ids)


@dataclass(frozen=True, slots=True)
class IdentifierDisposition:
    id: str
    event_class: str
    beat_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BeatCoverage:
    id: str
    story_routes: tuple[str, ...]
    family: str
    policy_id: str
    tape_channel: str
    max_freedom: str
    enabled_pattern_cards: int
    trigger_ids: tuple[str, ...]
    stage_any_of: tuple[str, ...]
    broadcast_contexts: tuple[str, ...]
    vehicle_phases: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReplayFamilyRef:
    id: str
    fixture_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CoverageMatrixReport:
    event_count: int
    speakable_count: int
    visual_only_count: int
    alias_count: int
    beat_count: int
    family_count: int
    policy_count: int
    tape_channel_count: int
    pattern_card_count: int
    successor_edge_count: int
    story_count: int
    predicate_count: int
    feature_count: int
    detector_count: int
    is_directed_acyclic: bool
    cyclic_component_count: int
    nonterminal_count: int
    guarded_edge_count: int
    material_revision_bonus: int
    raw_obs_scene_count: int
    legacy_trigger_count: int
    released_required_tuning_count: int
    experimental_detector_count: int
    identifiers: tuple[IdentifierDisposition, ...]
    beats: tuple[BeatCoverage, ...]
    replay_refs: tuple[ReplayFamilyRef, ...]


def can_create_event_opportunity(event_id: str) -> bool:
    """Return whether a current identifier may create an EventOpportunity."""

    registry = _load("freeze-registry.json", None)
    for row in _rows(registry["eventIdentifiers"], "eventIdentifiers"):
        if row["id"] == event_id:
            return str(row["eventClass"]) == "speakable"
    raise ContractViolation(f"unknown event identifier: {event_id}")


def load_coverage_matrix() -> CoverageMatrixReport:
    return audit_coverage_matrix()


def audit_coverage_matrix(
    *,
    registry: dict[str, Any] | None = None,
    beats: dict[str, Any] | None = None,
    graph: dict[str, Any] | None = None,
    cards: dict[str, Any] | None = None,
    detectors: dict[str, Any] | None = None,
    replay_refs: dict[str, Any] | None = None,
) -> CoverageMatrixReport:
    """Prove the frozen 60-identifier / 64-beat coverage matrix still closes."""

    registry_doc = _load("freeze-registry.json", registry)
    beat_doc = _load("beat-catalog.json", beats)
    graph_doc = _load("successor-graph.json", graph)
    card_doc = _load("realization-pattern-cards.json", cards)
    detector_doc = _load("detector-catalog.json", detectors)
    replay_doc = _load("coverage-matrix-replay-refs.json", replay_refs)

    events = _rows(registry_doc["eventIdentifiers"], "eventIdentifiers")
    beat_rows = _rows(beat_doc["beats"], "beats")
    family_rows = _rows(beat_doc["realizationFamilies"], "realizationFamilies")
    policy_rows = _rows(beat_doc["policies"], "policies")
    edge_rows = _rows(graph_doc["edges"], "edges")
    story_rows = _rows(graph_doc["storyDefinitions"], "storyDefinitions")
    policy_nodes = _rows(graph_doc["nodePolicies"], "nodePolicies")
    guard_rows = _rows(graph_doc["guardProfiles"], "guardProfiles")
    card_rows = _rows(card_doc["cards"], "cards")
    detector_rows = _rows(detector_doc["definitions"], "definitions")
    replay_rows = _rows(replay_doc["claimFamilies"], "claimFamilies")

    event_ids = _unique_ids(events, "id", "event")
    beat_ids = set(_unique_ids(beat_rows, "id", "beat"))
    family_ids = set(_unique_ids(family_rows, "id", "realization family"))
    policy_ids = set(_unique_ids(policy_rows, "id", "policy"))
    story_ids = set(_unique_ids(story_rows, "id", "story"))
    channel_ids = set(_id_tuple(registry_doc["tapeChannels"], "tapeChannels"))
    predicate_ids = set(_unique_ids(_rows(registry_doc["factPredicates"], "facts"), "id", "fact"))
    feature_ids = _unique_ids(_rows(registry_doc["features"], "features"), "id", "feature")
    guard_ids = {str(row["id"]) for row in guard_rows}
    node_policy = {str(row["beatId"]): row for row in policy_nodes}

    if len(event_ids) != 60:
        raise ContractViolation("event inventory differs")
    if len(beat_ids) != 64:
        raise ContractViolation("beat inventory differs")
    if len(family_ids) != 37:
        raise ContractViolation("realization family inventory differs")
    if len(policy_ids) != 6:
        raise ContractViolation("policy inventory differs")
    if len(channel_ids) != 36:
        raise ContractViolation("tape channel inventory differs")
    if len(predicate_ids) != 57:
        raise ContractViolation("fact predicate inventory differs")
    if len(feature_ids) != 21:
        raise ContractViolation("feature inventory differs")
    if len(detector_rows) != 3:
        raise ContractViolation("detector inventory differs")

    identifiers: list[IdentifierDisposition] = []
    speakable = visual = alias = 0
    for row in events:
        event_class = str(row["eventClass"])
        if event_class not in EVENT_CLASSES:
            raise ContractViolation("unclassified event identifier")
        mapped = tuple(item for item in row["beatDefinitions"] if isinstance(item, str))
        if event_class == "speakable":
            speakable += 1
            if not mapped or any(item not in beat_ids for item in mapped):
                raise ContractViolation("speakable identifier missing BeatDefinition")
            beat_tuple = mapped
        else:
            if event_class == "visual_only":
                visual += 1
            else:
                alias += 1
            beat_tuple = ()
        identifiers.append(
            IdentifierDisposition(id=str(row["id"]), event_class=event_class, beat_ids=beat_tuple)
        )

    cards_by_beat: dict[str, int] = defaultdict(int)
    for card in card_rows:
        if not card.get("enabled"):
            continue
        if card.get("auditedLanguage") != "en":
            raise ContractViolation("pattern card language is not EN")
        if card.get("freedom") not in ENABLED_FREEDOM:
            raise ContractViolation("pattern card freedom is not enabled")
        cards_by_beat[str(card["beatId"])] += 1
    if sum(cards_by_beat.values()) != 256:
        raise ContractViolation("pattern card inventory differs")
    if set(cards_by_beat) != beat_ids:
        raise ContractViolation("pattern card beat coverage differs")

    family_freedom = {row["id"]: str(row["promotedMaxFreedom"]) for row in family_rows}
    stories = {row["id"]: row for row in story_rows}
    beat_reports: list[BeatCoverage] = []
    used_families: set[str] = set()
    trigger_ids: list[str] = []
    for beat in beat_rows:
        routes = _id_tuple(beat["storyRoutes"], "storyRoutes")
        if not routes or any(item not in story_ids for item in routes):
            raise ContractViolation("unknown story route")
        family = str(beat["realization"]["family"])
        if family not in family_ids:
            raise ContractViolation("unknown realization family")
        used_families.add(family)
        policy_id = str(beat["policyId"])
        if policy_id not in policy_ids:
            raise ContractViolation("unknown beat policy")
        channel = str(beat["tapeChannel"])
        if channel not in channel_ids:
            raise ContractViolation("unknown tape channel")
        max_freedom = str(beat["realization"]["maxFreedom"])
        if max_freedom not in ENABLED_FREEDOM:
            raise ContractViolation("beat freedom is not enabled")
        promoted = family_freedom[family]
        if FREEDOM_ORDER.index(max_freedom) > FREEDOM_ORDER.index(promoted):
            raise ContractViolation("beat freedom exceeds family maximum")
        required_cards = int(beat["realization"]["requiredPatternCardCount"])
        enabled_cards = cards_by_beat[str(beat["id"])]
        if enabled_cards < required_cards or enabled_cards < 4:
            raise ContractViolation("pattern card pool is insufficient")
        for claim in beat["claims"]["required"]:
            if claim["kind"] == "predicate" and claim["id"] not in predicate_ids:
                raise ContractViolation("unknown fact predicate")
        hard = _object(beat["hardContext"], "hardContext")
        broadcast = _object(hard["broadcastContext"], "broadcastContext")
        stages = _enum_tuple(hard["stageAnyOf"], STAGE_VALUES, "stageAnyOf")
        contexts = _enum_tuple(broadcast["values"], CONTEXT_VALUES, "broadcastContext")
        phases = _enum_tuple(hard["vehiclePhaseAnyOf"], PHASE_VALUES, "vehiclePhaseAnyOf")
        beat_triggers = tuple(str(item["id"]) for item in beat["triggers"])
        trigger_ids.extend(beat_triggers)
        for story_id in routes:
            story = stories[story_id]
            if int(story["cadenceMinimumMs"]) < 0:
                raise ContractViolation("story cadence barrier missing")
            if int(story["maxConsecutiveNonClosingBeats"]) < 1:
                raise ContractViolation("story material-revision guard missing")
        beat_reports.append(
            BeatCoverage(
                id=str(beat["id"]),
                story_routes=routes,
                family=family,
                policy_id=policy_id,
                tape_channel=channel,
                max_freedom=max_freedom,
                enabled_pattern_cards=enabled_cards,
                trigger_ids=beat_triggers,
                stage_any_of=stages,
                broadcast_contexts=contexts,
                vehicle_phases=phases,
            )
        )
    if used_families != family_ids:
        raise ContractViolation("unused realization family")

    legacy = [item for item in trigger_ids if item in FORBIDDEN_LEGACY_TRIGGERS]
    if legacy:
        raise ContractViolation("legacy trigger cannot be a v2 runtime trigger")
    expected_hash = str(canonical_sha256(beat_doc)).removeprefix("sha256:")
    if graph_doc["sourceBaseline"]["beatCatalogSha256"] != expected_hash:
        raise ContractViolation("beat catalog hash differs")
    if card_doc["catalogSha256"] != f"sha256:{expected_hash}":
        raise ContractViolation("pattern card catalog hash differs")

    if set(node_policy) != beat_ids:
        raise ContractViolation("node policy coverage differs")
    outgoing: dict[str, int] = defaultdict(int)
    guarded = 0
    for edge in edge_rows:
        source = str(edge["fromBeatId"])
        target = str(edge["toBeatId"])
        if source not in beat_ids or target not in beat_ids:
            raise ContractViolation("unknown successor")
        if str(edge["guardProfileId"]) not in guard_ids:
            raise ContractViolation("unknown successor guard")
        outgoing[source] += 1
        guarded += 1
    cyclic = _has_cycle(beat_ids, edge_rows)
    analysis = _object(graph_doc["analysis"], "analysis")
    if cyclic or analysis.get("isDirectedAcyclic") is not True:
        raise ContractViolation("successor graph is not a DAG")
    if analysis.get("cyclicComponents"):
        raise ContractViolation("cyclic component without bounded exit proof")
    nonterminal = 0
    for beat_id in beat_ids:
        expected = "expand_explicit_edges" if outgoing[beat_id] else "no_implicit_continuation"
        if node_policy[beat_id]["successorDisposition"] != expected:
            raise ContractViolation("unintended dead end")
        if outgoing[beat_id]:
            nonterminal += 1
    bonus = int(graph_doc["selectionContract"]["materialRevisionBonus"])
    if bonus < 0:
        raise ContractViolation("material-revision guard missing")

    released_required = 0
    experimental = 0
    for detector in detector_rows:
        if detector.get("experimental") is True:
            experimental += 1
            continue
        if detector.get("tuningPolicy") == "required":
            released_required += 1
    if released_required:
        raise ContractViolation("released detector requires default-off tuning capture")

    if tuple(row["id"] for row in replay_rows) != CLAIM_FAMILIES:
        raise ContractViolation("replay fixture claim families differ")
    replay_reports: list[ReplayFamilyRef] = []
    for row in replay_rows:
        fixtures = _rows(row["fixtures"], "replay fixtures")
        ids = _unique_ids(fixtures, "id", f"{row['id']} fixture")
        if not ids:
            raise ContractViolation("replay fixture family is empty")
        replay_reports.append(ReplayFamilyRef(id=str(row["id"]), fixture_ids=tuple(ids)))

    return CoverageMatrixReport(
        event_count=len(event_ids),
        speakable_count=speakable,
        visual_only_count=visual,
        alias_count=alias,
        beat_count=len(beat_ids),
        family_count=len(family_ids),
        policy_count=len(policy_ids),
        tape_channel_count=len(channel_ids),
        pattern_card_count=sum(cards_by_beat.values()),
        successor_edge_count=len(edge_rows),
        story_count=len(story_ids),
        predicate_count=len(predicate_ids),
        feature_count=len(feature_ids),
        detector_count=len(detector_rows),
        is_directed_acyclic=True,
        cyclic_component_count=0,
        nonterminal_count=nonterminal,
        guarded_edge_count=guarded,
        material_revision_bonus=bonus,
        raw_obs_scene_count=0,
        legacy_trigger_count=0,
        released_required_tuning_count=0,
        experimental_detector_count=experimental,
        identifiers=tuple(identifiers),
        beats=tuple(beat_reports),
        replay_refs=tuple(replay_reports),
    )
