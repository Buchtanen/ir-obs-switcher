"""Typed StoryDefinition / BeatDefinition loader for the frozen narrative catalog."""

from __future__ import annotations

import copy
import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from .coverage_matrix import FORBIDDEN_LEGACY_TRIGGERS, _has_cycle
from .feature import validate_detector_feature_units
from .primitives import ContractViolation, Stage, canonical_sha256
from .resources import packaged_schema_bytes

SCHEMA_VERSION = "narrative-catalog/2"
BEAT_INVARIANTS = (
    "unique_ids_and_exact_group_counts",
    "claims_resolve_fact_registry",
    "families_policies_channels_resolve",
    "speakable_dispositions_resolve_beats",
    "nonspeakable_dispositions_have_no_beats",
    "trigger_and_context_axes_are_coherent",
    "baseline_realization_routing",
)
GRAPH_INVARIANTS = (
    "successor_edges_match_human_table_exactly",
    "all_beat_and_guard_references_resolve",
    "edge_ids_and_ordinals_unique",
    "preference_bonus_matches_policy",
    "node_degrees_match_edges",
    "scc_analysis_matches_graph",
    "no_unbounded_nonterminal_component",
    "beat_catalog_hash_matches",
)
MANDATORY_CHECKS = (
    "closed_schema_and_bounds",
    "unique_casefolded_ids",
    "registry_referential_integrity",
    "event_to_beat_to_story_to_family_coverage",
    "all_beats_reachable_from_declared_triggers",
    "no_unintended_dead_end",
    "scc_has_exit_and_progress_barrier",
    "finite_guard_domain_is_satisfiable",
    "detector_ranges_and_cross_fields",
    "artifact_hashes_match",
    "no_executable_code_or_factual_prose",
    "no_sequence_graph_v1_fallback",
)
EXPECTED_GROUPS = {
    "timing": 12,
    "battle": 8,
    "position": 4,
    "incident": 5,
    "pit": 6,
    "stream": 1,
    "session": 21,
    "bio": 1,
    "filler": 6,
}
BEAT_FIELDS = frozenset(
    {
        "claims",
        "group",
        "hardContext",
        "id",
        "lifecycleText",
        "policyId",
        "realization",
        "role",
        "storyRoutes",
        "tapeChannel",
        "triggers",
    }
)
REALIZATION_FIELDS = frozenset({"backend", "family", "maxFreedom", "requiredPatternCardCount"})
CATALOG_FIELDS = frozenset(
    {
        "beats",
        "catalogProjectionVersion",
        "globalForbiddenClaimTypes",
        "language",
        "policies",
        "realizationFamilies",
        "schemaVersion",
        "sourceBaseline",
    }
)
OPEN_ROLES = frozenset({"opening", "composite", "control", "vehicle"})
UPDATE_ROLES = frozenset({"update", "escalation", "context", "bridge"})
CLOSE_ROLES = frozenset({"result", "outcome", "closure", "climax", "single"})
LIFECYCLE_BEATS = frozenset(
    {
        "stream.started",
        "session.intro.practice",
        "session.intro.qualifying",
        "session.intro.race",
        "session.restart",
        "session.wrap.practice",
        "session.wrap.qualifying",
        "session.wrap.race",
        "session.preview.next",
        "session.enter_car.practice",
        "session.enter_car.qualifying",
        "session.enter_car.race",
    }
)
DETECTOR_IDS = ("battle_ahead_v1", "battle_behind_v1", "battle_two_front_v1")
STAGE_VALUES = frozenset(item.value for item in Stage)


class CatalogInvalid(ValueError):
    """Catalog failed a named loader check; callers must disable commentary."""


def _object(value: object, label: str) -> dict[str, Any]:
    if not isinstance(value, dict) or any(not isinstance(key, str) for key in value):
        raise CatalogInvalid(f"{label} must be a JSON object")
    return value


def _rows(value: object, label: str) -> list[dict[str, Any]]:
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise CatalogInvalid(f"{label} must be a JSON object list")
    return value


def _load(name: str, override: dict[str, Any] | None) -> dict[str, Any]:
    if override is not None:
        return _object(override, name)
    return _object(json.loads(packaged_schema_bytes(name)), name)


def _unique(rows: list[dict[str, Any]], field: str, label: str) -> list[str]:
    values = [str(row[field]) for row in rows]
    folded = [item.casefold() for item in values]
    if len(folded) != len(set(folded)):
        raise CatalogInvalid(f"duplicate/case-colliding {label} ID")
    return values


def _walk_keys(value: object) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            found.append(str(key))
            found.extend(_walk_keys(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_walk_keys(item))
    return found


def _expected_backend(beat_id: str, policy_id: str) -> str:
    if policy_id in {"critical", "result"} or beat_id in LIFECYCLE_BEATS:
        return "authored"
    return "qwen_compiled"


@dataclass(frozen=True, slots=True)
class ClaimRequirement:
    id: str
    kind: str
    actor_frame: str
    required_attributes: tuple[str, ...]
    optional_attributes: tuple[str, ...]
    min_claims: int
    max_claims: int


@dataclass(frozen=True, slots=True)
class PolicyProfile:
    id: str
    base_priority: int
    ttl_ms: int
    penalty_coefficient: float
    cadence_minimum_ms: int | None
    urgency: str


@dataclass(frozen=True, slots=True)
class RealizationRef:
    family: str
    backend: str
    max_freedom: str
    same_beat_authored_fallback: bool


@dataclass(frozen=True, slots=True)
class BeatTrigger:
    id: str
    kind: str


@dataclass(frozen=True, slots=True)
class BeatDefinition:
    id: str
    group: str
    role: str
    story_routes: tuple[str, ...]
    tape_channel: str
    policy: PolicyProfile
    stage_any_of: tuple[str, ...]
    broadcast_contexts: tuple[str, ...]
    vehicle_phases: tuple[str, ...]
    claims: tuple[ClaimRequirement, ...]
    triggers: tuple[BeatTrigger, ...]
    realization: RealizationRef
    successor_edge_ids: tuple[str, ...]
    detector_id: str | None


@dataclass(frozen=True, slots=True)
class StoryDefinition:
    id: str
    cadence_minimum_ms: int
    max_consecutive_non_closing_beats: int
    on_no_eligible_successor: str
    open_beat_ids: tuple[str, ...]
    update_beat_ids: tuple[str, ...]
    close_beat_ids: tuple[str, ...]
    successor_edge_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class SuccessorEdge:
    id: str
    from_beat_id: str
    to_beat_id: str
    guard_profile_id: str
    preference: str
    score_bonus: int
    edge_class: str


@dataclass(frozen=True, slots=True)
class EventRoute:
    event_id: str
    beat_ids: tuple[str, ...]
    story_routes: tuple[str, ...]
    tape_channel: str


@dataclass(frozen=True, slots=True)
class NarrativeCatalog:
    schema_version: str
    catalog_hash: str
    stories: tuple[StoryDefinition, ...]
    beats: tuple[BeatDefinition, ...]
    edges: tuple[SuccessorEdge, ...]
    policies: tuple[PolicyProfile, ...]
    families: tuple[str, ...]
    detector_ids: tuple[str, ...]
    event_routes: tuple[EventRoute, ...]
    same_beat_authored_fallback: bool
    sequence_graph_fallback: bool

    def story(self, story_id: str) -> StoryDefinition:
        for item in self.stories:
            if item.id == story_id:
                return item
        raise ContractViolation(f"unknown story {story_id}")

    def beat(self, beat_id: str) -> BeatDefinition:
        for item in self.beats:
            if item.id == beat_id:
                return item
        raise ContractViolation(f"unknown beat {beat_id}")

    def route_event(self, event_id: str) -> EventRoute | None:
        for item in self.event_routes:
            if item.event_id == event_id:
                return item
        return None


@dataclass(frozen=True, slots=True)
class CatalogLoadFailure:
    commentary_enabled: bool
    main_loop_raises: bool
    partial_catalog_published: bool
    reason: str
    runtime_status: str
    error: str


@dataclass(frozen=True, slots=True)
class CatalogLoadResult:
    outcome: str
    catalog: NarrativeCatalog | None
    failure: CatalogLoadFailure | None
    counts: dict[str, int]
    executed_invariants: tuple[str, ...]
    executed_checks: tuple[str, ...]
    catalog_hash: str | None

    def require_catalog(self) -> NarrativeCatalog:
        if self.catalog is None or self.failure is not None:
            reason = self.failure.reason if self.failure is not None else "catalog_invalid"
            raise RuntimeError(reason)
        return self.catalog


def apply_catalog_mutation(
    fixture_id: str,
    *,
    registry: dict[str, Any],
    beats: dict[str, Any],
    graph: dict[str, Any],
    detectors: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Apply one frozen catalog-loader-goldens mutation."""

    values = {
        "registry": copy.deepcopy(registry),
        "beats": copy.deepcopy(beats),
        "graph": copy.deepcopy(graph),
        "detectors": copy.deepcopy(detectors),
        "config": copy.deepcopy(config),
    }
    beat = values["beats"]["beats"][0]
    if fixture_id == "duplicate_beat_id":
        values["beats"]["beats"][1]["id"] = beat["id"]
    elif fixture_id == "case_colliding_family_id":
        values["beats"]["realizationFamilies"][1]["id"] = values["beats"]["realizationFamilies"][0][
            "id"
        ].upper()
    elif fixture_id == "unknown_policy":
        beat["policyId"] = "magic"
    elif fixture_id == "unknown_family":
        beat["realization"]["family"] = "magic"
    elif fixture_id == "unknown_channel":
        beat["tapeChannel"] = "race.magic"
    elif fixture_id == "unknown_predicate":
        beat["claims"]["required"][0]["id"] = "magic.fact"
    elif fixture_id == "unreachable_beat":
        target = next(
            row for row in values["beats"]["beats"] if row["id"] == "timing.lap.personal_best"
        )
        target["triggers"] = []
    elif fixture_id == "dangling_edge":
        values["graph"]["edges"][0]["toBeatId"] = "missing.beat"
    elif fixture_id == "self_loop_without_barrier":
        values["graph"]["edges"][0]["toBeatId"] = values["graph"]["edges"][0]["fromBeatId"]
    elif fixture_id == "stale_beat_hash":
        values["graph"]["sourceBaseline"]["beatCatalogSha256"] = "0" * 64
    elif fixture_id == "invalid_detector_range":
        values["detectors"]["definitions"][0]["parameters"][0]["default"] = 9.0
    elif fixture_id == "unknown_detector_feature":
        values["detectors"]["definitions"][0]["features"][0] = "gap.magic"
    elif fixture_id == "arbitrary_catalog_code":
        beat["python"] = "unsafe"
    elif fixture_id == "extra_style_beat":
        extra = copy.deepcopy(beat)
        extra["id"] = "timing.lap.personal_best.excited"
        values["beats"]["beats"].append(extra)
    elif fixture_id == "missing_detector_config_template":
        values["config"]["keyDefinitions"] = [
            row
            for row in values["config"]["keyDefinitions"]
            if row["key"] != "commentary.detector.<id>.<parameter>"
        ]
    else:
        raise ContractViolation(f"unknown catalog mutation {fixture_id}")
    return values


def load_narrative_catalog(
    *,
    registry: dict[str, Any] | None = None,
    beats: dict[str, Any] | None = None,
    graph: dict[str, Any] | None = None,
    detectors: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
) -> CatalogLoadResult:
    """Load the frozen catalog or disable commentary without raising."""

    try:
        catalog, counts = _load_or_raise(
            registry=registry,
            beats=beats,
            graph=graph,
            detectors=detectors,
            config=config,
        )
        return CatalogLoadResult(
            outcome="loaded",
            catalog=catalog,
            failure=None,
            counts=counts,
            executed_invariants=BEAT_INVARIANTS + GRAPH_INVARIANTS,
            executed_checks=MANDATORY_CHECKS,
            catalog_hash=catalog.catalog_hash,
        )
    except CatalogInvalid as exc:
        return CatalogLoadResult(
            outcome="commentary_disabled",
            catalog=None,
            failure=CatalogLoadFailure(
                commentary_enabled=False,
                main_loop_raises=False,
                partial_catalog_published=False,
                reason="catalog_invalid",
                runtime_status="disabled",
                error=str(exc),
            ),
            counts={},
            executed_invariants=BEAT_INVARIANTS + GRAPH_INVARIANTS,
            executed_checks=MANDATORY_CHECKS,
            catalog_hash=None,
        )


def _load_or_raise(
    *,
    registry: dict[str, Any] | None,
    beats: dict[str, Any] | None,
    graph: dict[str, Any] | None,
    detectors: dict[str, Any] | None,
    config: dict[str, Any] | None,
) -> tuple[NarrativeCatalog, dict[str, int]]:
    registry_doc = _load("freeze-registry.json", registry)
    beat_doc = _load("beat-catalog.json", beats)
    graph_doc = _load("successor-graph.json", graph)
    detector_doc = _load("detector-catalog.json", detectors)
    config_doc = _load("config-contract.json", config)
    contract = _load("catalog-loader-contract.json", None)

    keys = _walk_keys({"beats": beat_doc, "graph": graph_doc})
    if any("sequence_graph" in key.casefold() or "sequenceGraph" in key for key in keys):
        raise CatalogInvalid("sequence_graph v1 fallback is forbidden")
    extra_catalog = set(beat_doc) - CATALOG_FIELDS
    if extra_catalog:
        if any("sequence" in key.casefold() for key in extra_catalog):
            raise CatalogInvalid("sequence_graph v1 fallback is forbidden")
        raise CatalogInvalid("beat schema rejected")

    beat_rows = _rows(beat_doc.get("beats"), "beats")
    if len(beat_rows) != 64:
        raise CatalogInvalid("beat schema rejected")
    for beat in beat_rows:
        extra = set(beat) - BEAT_FIELDS
        if extra:
            if any(key in extra for key in ("python", "eval", "exec", "compile")):
                raise CatalogInvalid("beat schema rejected")
            raise CatalogInvalid("beat schema rejected")
        realization = _object(beat.get("realization"), "realization")
        extra_real = set(realization) - REALIZATION_FIELDS
        if extra_real:
            raise CatalogInvalid("same-beat authored fallback is forbidden")
        triggers = beat.get("triggers")
        if not isinstance(triggers, list) or not triggers:
            raise CatalogInvalid("beat schema rejected")
        suffix = str(beat["id"]).rsplit(".", 1)[-1]
        if suffix in {"excited", "angry", "warm"}:
            raise CatalogInvalid("beat schema rejected")

    beat_ids = _unique(beat_rows, "id", "beat")
    family_rows = _rows(beat_doc.get("realizationFamilies"), "realizationFamilies")
    policy_rows = _rows(beat_doc.get("policies"), "policies")
    _unique(family_rows, "id", "realization family")
    _unique(policy_rows, "id", "policy")
    if Counter(str(row["group"]) for row in beat_rows) != Counter(EXPECTED_GROUPS):
        raise CatalogInvalid("beat schema rejected")

    family_ids = {str(row["id"]) for row in family_rows}
    policy_map = {
        str(row["id"]): PolicyProfile(
            id=str(row["id"]),
            base_priority=int(row["basePriority"]),
            ttl_ms=int(row["ttlMs"]),
            penalty_coefficient=float(row["penaltyCoefficient"]),
            cadence_minimum_ms=(
                None if row["cadenceMinimumMs"] is None else int(row["cadenceMinimumMs"])
            ),
            urgency=str(row["urgency"]),
        )
        for row in policy_rows
    }
    channel_ids = {str(item) for item in registry_doc["tapeChannels"]}
    predicate_ids = {str(row["id"]) for row in registry_doc["factPredicates"]}
    event_rows = _rows(registry_doc["eventIdentifiers"], "eventIdentifiers")
    event_ids = {str(row["id"]) for row in event_rows}
    lifecycle_ids = {str(row["id"]) for row in registry_doc["internalLifecycleEvents"]}
    story_rows = _rows(graph_doc["storyDefinitions"], "storyDefinitions")
    story_ids = set(_unique(story_rows, "id", "story"))
    edge_rows = _rows(graph_doc["edges"], "edges")
    _unique(edge_rows, "id", "edge")
    ordinals = [int(row["ordinal"]) for row in edge_rows]
    if len(ordinals) != len(set(ordinals)):
        raise CatalogInvalid("duplicate edge ordinal")
    guard_ids = {str(row["id"]) for row in _rows(graph_doc["guardProfiles"], "guardProfiles")}
    node_policies = {
        str(row["beatId"]): row for row in _rows(graph_doc["nodePolicies"], "nodePolicies")
    }

    used_families: set[str] = set()
    trigger_roots: set[str] = set()
    for beat_row in beat_rows:
        if beat_row["policyId"] not in policy_map:
            raise CatalogInvalid("unknown beat policy")
        family = str(beat_row["realization"]["family"])
        if family not in family_ids:
            raise CatalogInvalid("unknown realization family")
        used_families.add(family)
        if beat_row["tapeChannel"] not in channel_ids:
            raise CatalogInvalid("unknown tape channel")
        story_routes = tuple(str(item) for item in beat_row["storyRoutes"])
        if not story_routes or any(item not in story_ids for item in story_routes):
            raise CatalogInvalid("unknown story route")
        for claim in beat_row["claims"]["required"]:
            if claim["kind"] == "predicate" and claim["id"] not in predicate_ids:
                raise CatalogInvalid("unknown fact predicate")
        expected = _expected_backend(str(beat_row["id"]), str(beat_row["policyId"]))
        if beat_row["realization"]["backend"] != expected:
            raise CatalogInvalid("baseline realization routing")
        if beat_row["realization"]["maxFreedom"] != "tight":
            raise CatalogInvalid("baseline realization routing")
        for trigger in beat_row["triggers"]:
            known = (
                event_ids
                if trigger["kind"] == "accepted_event"
                else (
                    lifecycle_ids
                    if trigger["kind"] == "lifecycle_event"
                    else {"LONG_SILENCE_ELAPSED"}
                )
            )
            if trigger["id"] not in known:
                raise CatalogInvalid("unknown trigger")
            if trigger["id"] in FORBIDDEN_LEGACY_TRIGGERS:
                raise CatalogInvalid("legacy trigger cannot be a v2 runtime trigger")
            trigger_roots.add(str(beat_row["id"]))
        hard = _object(beat_row["hardContext"], "hardContext")
        stages = tuple(str(item) for item in hard["stageAnyOf"])
        if any(item not in STAGE_VALUES for item in stages):
            raise CatalogInvalid("trigger_and_context_axes_are_coherent")
    if used_families != family_ids:
        raise CatalogInvalid("unused realization family")

    speakable_beats: set[str] = set()
    event_routes: list[EventRoute] = []
    beat_id_set = set(beat_ids)
    for row in event_rows:
        mapped = tuple(str(item) for item in row["beatDefinitions"])
        if row["eventClass"] == "speakable":
            if not mapped or any(item not in beat_id_set for item in mapped):
                raise CatalogInvalid("speakable identifier missing BeatDefinition")
            speakable_beats.update(mapped)
            if str(row["id"]) in FORBIDDEN_LEGACY_TRIGGERS:
                continue
            first = next(item for item in beat_rows if item["id"] == mapped[0])
            event_routes.append(
                EventRoute(
                    event_id=str(row["id"]),
                    beat_ids=mapped,
                    story_routes=tuple(str(item) for item in first["storyRoutes"]),
                    tape_channel=str(first["tapeChannel"]),
                )
            )
        elif mapped:
            raise CatalogInvalid("nonspeakable dispositions have no beats")
    if not speakable_beats:
        raise CatalogInvalid("speakable identifier missing BeatDefinition")

    outgoing: dict[str, int] = defaultdict(int)
    incoming: dict[str, int] = defaultdict(int)
    edges: list[SuccessorEdge] = []
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge_row in edge_rows:
        source = str(edge_row["fromBeatId"])
        target = str(edge_row["toBeatId"])
        if source not in beat_id_set or target not in beat_id_set:
            raise CatalogInvalid("unknown edge beat")
        if str(edge_row["guardProfileId"]) not in guard_ids:
            raise CatalogInvalid("unknown successor guard")
        bonus = 6 if edge_row["preference"] == "preferred" else 0
        if int(edge_row["scoreBonus"]) != bonus:
            raise CatalogInvalid("preference bonus differs")
        outgoing[source] += 1
        incoming[target] += 1
        adjacency[source].append(target)
        edges.append(
            SuccessorEdge(
                id=str(edge_row["id"]),
                from_beat_id=source,
                to_beat_id=target,
                guard_profile_id=str(edge_row["guardProfileId"]),
                preference=str(edge_row["preference"]),
                score_bonus=bonus,
                edge_class=str(edge_row["edgeClass"]),
            )
        )
    if (
        _has_cycle(beat_id_set, edge_rows)
        or graph_doc["analysis"].get("isDirectedAcyclic") is not True
    ):
        raise CatalogInvalid("cyclic component without bounded exit proof")
    if graph_doc["analysis"].get("cyclicComponents"):
        raise CatalogInvalid("cyclic component without bounded exit proof")
    if set(node_policies) != beat_id_set:
        raise CatalogInvalid("unintended dead end")
    for beat_id in beat_ids:
        expected = "expand_explicit_edges" if outgoing[beat_id] else "no_implicit_continuation"
        if node_policies[beat_id]["successorDisposition"] != expected:
            raise CatalogInvalid("unintended dead end")
        if node_policies[beat_id]["outgoingEdgeCount"] != outgoing[beat_id]:
            raise CatalogInvalid("node degree differs")
        if node_policies[beat_id]["incomingEdgeCount"] != incoming[beat_id]:
            raise CatalogInvalid("node degree differs")
    reached = set(trigger_roots)
    pending = list(trigger_roots)
    while pending:
        current = pending.pop()
        for target in adjacency[current]:
            if target not in reached:
                reached.add(target)
                pending.append(target)
    if beat_id_set - reached:
        raise CatalogInvalid("unreachable beat")
    for guard in graph_doc["guardProfiles"]:
        if not guard["conditions"] or guard["unknownVerdict"] != "ineligible":
            raise CatalogInvalid("finite guard domain is unsatisfied")
    for story in story_rows:
        if int(story["cadenceMinimumMs"]) < 0:
            raise CatalogInvalid("story cadence barrier missing")
        if int(story["maxConsecutiveNonClosingBeats"]) < 1:
            raise CatalogInvalid("story material-revision guard missing")

    expected_hash = str(canonical_sha256(beat_doc)).removeprefix("sha256:")
    if graph_doc["sourceBaseline"]["beatCatalogSha256"] != expected_hash:
        raise CatalogInvalid("beat catalog hash differs")
    if contract["artifacts"][1]["sha256"] != f"sha256:{expected_hash}":
        raise CatalogInvalid("artifact hashes match")

    detector_rows = _rows(detector_doc.get("definitions"), "detectors")
    if [str(row["id"]) for row in detector_rows] != list(DETECTOR_IDS):
        raise CatalogInvalid("detector definition invalid")
    feature_ids = {str(row["id"]) for row in registry_doc["features"]}
    try:
        validate_detector_feature_units()
    except ContractViolation as exc:
        if detectors is not None:
            raise CatalogInvalid("detector definition invalid: " + str(exc)) from exc
        raise CatalogInvalid("detector definition invalid") from exc
    for detector in detector_rows:
        if not set(detector["features"]) <= feature_ids:
            raise CatalogInvalid("detector definition invalid")
        for parameter in detector["parameters"]:
            value = parameter["default"]
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                raise CatalogInvalid("detector definition invalid")
            if not parameter["minimum"] <= value <= parameter["maximum"]:
                raise CatalogInvalid("detector definition invalid")
    template_keys = {
        str(row["key"]) for row in config_doc["keyDefinitions"] if row["keyClass"] == "template"
    }
    if template_keys != {
        "commentary.detector.<id>.enabled",
        "commentary.detector.<id>.<parameter>",
    }:
        raise CatalogInvalid("detector config templates missing")

    policies = tuple(policy_map[key] for key in sorted(policy_map))
    edge_ids_by_from: dict[str, list[str]] = defaultdict(list)
    for typed_edge in edges:
        edge_ids_by_from[typed_edge.from_beat_id].append(typed_edge.id)
    typed_beats: list[BeatDefinition] = []
    for beat_row in beat_rows:
        hard = beat_row["hardContext"]
        broadcast = hard["broadcastContext"]
        typed_beats.append(
            BeatDefinition(
                id=str(beat_row["id"]),
                group=str(beat_row["group"]),
                role=str(beat_row["role"]),
                story_routes=tuple(str(item) for item in beat_row["storyRoutes"]),
                tape_channel=str(beat_row["tapeChannel"]),
                policy=policy_map[str(beat_row["policyId"])],
                stage_any_of=tuple(str(item) for item in hard["stageAnyOf"]),
                broadcast_contexts=tuple(str(item) for item in broadcast["values"]),
                vehicle_phases=tuple(str(item) for item in hard["vehiclePhaseAnyOf"]),
                claims=tuple(
                    ClaimRequirement(
                        id=str(claim["id"]),
                        kind=str(claim["kind"]),
                        actor_frame=str(claim["actorFrame"]),
                        required_attributes=tuple(
                            str(item) for item in claim["requiredAttributes"]
                        ),
                        optional_attributes=tuple(
                            str(item) for item in claim["optionalAttributes"]
                        ),
                        min_claims=int(claim["minClaims"]),
                        max_claims=int(claim["maxClaims"]),
                    )
                    for claim in beat_row["claims"]["required"]
                ),
                triggers=tuple(
                    BeatTrigger(id=str(item["id"]), kind=str(item["kind"]))
                    for item in beat_row["triggers"]
                ),
                realization=RealizationRef(
                    family=str(beat_row["realization"]["family"]),
                    backend=str(beat_row["realization"]["backend"]),
                    max_freedom=str(beat_row["realization"]["maxFreedom"]),
                    same_beat_authored_fallback=False,
                ),
                successor_edge_ids=tuple(edge_ids_by_from[str(beat_row["id"])]),
                detector_id=None,
            )
        )
    beats_by_story: dict[str, list[BeatDefinition]] = defaultdict(list)
    for typed_beat in typed_beats:
        for story_id in typed_beat.story_routes:
            beats_by_story[story_id].append(typed_beat)
    stories = []
    for row in story_rows:
        members = beats_by_story[str(row["id"])]
        stories.append(
            StoryDefinition(
                id=str(row["id"]),
                cadence_minimum_ms=int(row["cadenceMinimumMs"]),
                max_consecutive_non_closing_beats=int(row["maxConsecutiveNonClosingBeats"]),
                on_no_eligible_successor=str(row["onNoEligibleSuccessor"]),
                open_beat_ids=tuple(item.id for item in members if item.role in OPEN_ROLES),
                update_beat_ids=tuple(item.id for item in members if item.role in UPDATE_ROLES),
                close_beat_ids=tuple(item.id for item in members if item.role in CLOSE_ROLES),
                successor_edge_ids=tuple(
                    edge.id
                    for edge in edges
                    if any(edge.from_beat_id == item.id for item in members)
                    and any(edge.to_beat_id == item.id for item in members)
                ),
            )
        )
    counts = {
        "events": len(event_rows),
        "lifecycleEvents": len(registry_doc["internalLifecycleEvents"]),
        "beats": len(typed_beats),
        "storyDefinitions": len(stories),
        "successorEdges": len(edges),
        "realizationFamilies": len(family_ids),
        "detectors": len(detector_rows),
    }
    catalog = NarrativeCatalog(
        schema_version=SCHEMA_VERSION,
        catalog_hash=str(canonical_sha256(beat_doc)),
        stories=tuple(stories),
        beats=tuple(typed_beats),
        edges=tuple(edges),
        policies=policies,
        families=tuple(sorted(family_ids)),
        detector_ids=DETECTOR_IDS,
        event_routes=tuple(event_routes),
        same_beat_authored_fallback=False,
        sequence_graph_fallback=False,
    )
    return catalog, counts
