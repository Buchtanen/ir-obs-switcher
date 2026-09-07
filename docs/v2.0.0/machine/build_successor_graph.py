#!/usr/bin/env python3
"""Build and validate the frozen v2 natural-successor graph."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from build_dto_schemas import canonical, schema_errors

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / "docs" / "v2.0.0"
EVENT_DOC = DOCS / "event-beat-disposition.md"
CATALOG_PATH = Path(__file__).with_name("beat-catalog.json")
GRAPH_PATH = Path(__file__).with_name("successor-graph.json")
SCHEMA_PATH = Path(__file__).with_name("successor-graph.schema.json")
MUTATIONS_PATH = Path(__file__).with_name("successor-graph-mutations.json")

STORIES = {
    "timing_attempt": (2, 8_000),
    "battle_ahead": (3, 8_000),
    "battle_behind": (2, 8_000),
    "battle_two_front": (2, 8_000),
    "pit_cycle": (3, 8_000),
    "incident": (2, 8_000),
    "session_occurrence": (3, 8_000),
    "stream_lifecycle": (1, 0),
    "bio_pressure": (1, 0),
    "single_result": (1, 0),
    "filler_single": (1, 0),
}

# The prose remains reviewable in the human table. These closed tokens are the
# machine input to the later typed predicate compiler; they are not expressions.
GUARDS: dict[str, tuple[list[str], list[str]]] = {
    "current confirmed practice occurrence": (["current_occurrence"], ["stage_practice"]),
    "current confirmed qualifying occurrence": (["current_occurrence"], ["stage_qualifying"]),
    "current confirmed race occurrence": (["current_occurrence"], ["stage_race"]),
    "same attempt revision; projection valid": (
        ["attempt", "attempt_revision"],
        ["projection_valid"],
    ),
    "same attempt; target valid": (["attempt"], ["target_valid"]),
    "same attempt; qualifying position target": (["attempt"], ["qualifying_position_target_true"]),
    "same attempt; material gain": (["attempt"], ["material_gain_true"]),
    "same attempt; material loss": (["attempt"], ["material_loss_true"]),
    "same sector result explicitly best": (["sector_result"], ["sector_best_true"]),
    "same lap completed": (["attempt", "lap"], ["lap_completed"]),
    "same attempt invalidated": (["attempt"], ["attempt_invalidated"]),
    "same target/relation; approach claims true": (["target_relation"], ["approach_claims_true"]),
    "same front relation plus valid rear relation": (["front_relation"], ["rear_relation_valid"]),
    "same target/relation; attack band true": (["target_relation"], ["attack_band_true"]),
    "same target/relation; overlap true": (["target_relation"], ["overlap_true"]),
    "same target; ordered pass result": (["target_relation"], ["ordered_pass_result_true"]),
    "same target; battle outcome without pass claim": (
        ["target_relation"],
        ["battle_won_without_pass_true"],
    ),
    "same rear target/relation; threat claims true": (["rear_relation"], ["threat_claims_true"]),
    "same rear relation plus valid front relation": (["rear_relation"], ["front_relation_valid"]),
    "correlated position-loss result": (["rear_relation"], ["position_loss_result_true"]),
    "one declared relation becomes overlap": (["front_relation"], ["overlap_true"]),
    "correlated front relation result": (["front_relation"], ["front_result_true"]),
    "correlated rear relation result": (["rear_relation"], ["rear_result_true"]),
    "same pit cycle; lane fact active": (["pit_cycle"], ["lane_active"]),
    "same pit cycle; stopped fact active": (["pit_cycle"], ["stopped_active"]),
    "same cycle; no stop observed; released fact active": (
        ["pit_cycle"],
        ["no_stop_observed", "released_active"],
    ),
    "same pit cycle; released fact active": (["pit_cycle"], ["released_active"]),
    "same pit cycle; exit fact active": (["pit_cycle"], ["exit_active"]),
    "same cycle; exit without observed stop/release": (
        ["pit_cycle"],
        ["no_stop_or_release_observed", "exit_active"],
    ),
    "same cycle; comparison fact valid": (["pit_cycle"], ["comparison_valid"]),
    "same incident; aftermath revision valid": (["incident"], ["aftermath_revision_valid"]),
    "same occurrence/lap; invalid result": (
        ["current_occurrence", "lap"],
        ["invalid_lap_result_true"],
    ),
    "same incident; recovery evidence valid": (["incident"], ["recovery_true"]),
    "same race occurrence; checkered active": (
        ["session_occurrence"],
        ["stage_race", "checkered_active"],
    ),
    "same race occurrence; hero finished": (
        ["session_occurrence"],
        ["stage_race", "hero_finished"],
    ),
    "same occurrence; hero finish observed": (["session_occurrence"], ["hero_finished"]),
    "same occurrence ended; finish may be unknown": (["session_occurrence"], ["occurrence_ended"]),
    "same occurrence; fact fresh and not exposed": (
        ["session_occurrence"],
        ["fresh_unexposed_fact"],
    ),
    "next present stage known": (["next_present_stage"], ["next_present_stage_known"]),
    "qualifying result facts valid": (["session_occurrence"], ["qualifying_result_valid"]),
}

GLOBAL_GUARDS = [
    "source_is_last_playback_accepted_beat",
    "same_narrative_stream_epoch",
    "target_required_claims_true_not_unknown",
    "target_hard_context_true_not_unknown",
    "target_material_not_previously_exposed",
    "target_within_half_open_validity",
    "story_cadence_open",
    "nonclosing_story_cap_open",
]


def _clean(cell: str) -> str:
    return cell.strip().replace("`", "")


def _edge_rows() -> list[list[str]]:
    lines = EVENT_DOC.read_text(encoding="utf-8").splitlines()
    start = lines.index("## Natural successor edges") + 1
    rows: list[list[str]] = []
    entered = False
    for line in lines[start:]:
        if line.startswith("|"):
            cells = [_clean(cell) for cell in line.strip().strip("|").split("|")]
            if (
                len(cells) == 4
                and cells[0] not in {"From", "---"}
                and not cells[0].startswith("---")
            ):
                rows.append(cells)
                entered = True
        elif entered and line.strip():
            break
    return rows


def _slug(text: str) -> str:
    value = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return value


def _sha(value: Any) -> str:
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def _strong_components(nodes: list[str], edges: list[dict[str, Any]]) -> list[list[str]]:
    adjacency: dict[str, list[str]] = defaultdict(list)
    for edge in edges:
        adjacency[edge["fromBeatId"]].append(edge["toBeatId"])
    index = 0
    stack: list[str] = []
    indices: dict[str, int] = {}
    low: dict[str, int] = {}
    on_stack: set[str] = set()
    result: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indices[node] = low[node] = index
        index += 1
        stack.append(node)
        on_stack.add(node)
        for target in adjacency[node]:
            if target not in indices:
                visit(target)
                low[node] = min(low[node], low[target])
            elif target in on_stack:
                low[node] = min(low[node], indices[target])
        if low[node] == indices[node]:
            component: list[str] = []
            while True:
                member = stack.pop()
                on_stack.remove(member)
                component.append(member)
                if member == node:
                    break
            result.append(sorted(component))

    for node in sorted(nodes):
        if node not in indices:
            visit(node)
    return sorted(result, key=lambda row: row[0])


def build_graph() -> dict[str, Any]:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    beat_ids = [beat["id"] for beat in catalog["beats"]]
    rows = _edge_rows()
    documented_guards = {row[2] for row in rows}
    if documented_guards != set(GUARDS):
        raise ValueError(
            "guard mapping differs from human table: "
            f"missing={sorted(documented_guards - set(GUARDS))}, "
            f"extra={sorted(set(GUARDS) - documented_guards)}"
        )
    catalog_stories = {story_id for beat in catalog["beats"] for story_id in beat["storyRoutes"]}
    if catalog_stories != set(STORIES):
        raise ValueError("story definitions differ from beat catalog routes")
    profiles = []
    profile_ids: dict[str, str] = {}
    for text in sorted(GUARDS):
        profile_id = _slug(text)
        profile_ids[text] = profile_id
        identities, conditions = GUARDS[text]
        profiles.append(
            {
                "id": profile_id,
                "normativeText": text,
                "identityBindings": identities,
                "conditions": conditions,
                "unknownVerdict": "ineligible",
            }
        )
    edges = []
    for ordinal, (source, target, guard, policy) in enumerate(rows, 1):
        preference, closure = [part.strip() for part in policy.split(",", 1)]
        edges.append(
            {
                "id": f"{source}->{target}",
                "ordinal": ordinal,
                "fromBeatId": source,
                "toBeatId": target,
                "guardProfileId": profile_ids[guard],
                "preference": preference,
                "scoreBonus": 6 if preference == "preferred" else 0,
                "edgeClass": closure,
                "episodeTruthEffect": "none",
            }
        )
    outgoing = Counter(edge["fromBeatId"] for edge in edges)
    incoming = Counter(edge["toBeatId"] for edge in edges)
    components = _strong_components(beat_ids, edges)
    self_loops = {edge["fromBeatId"] for edge in edges if edge["fromBeatId"] == edge["toBeatId"]}
    cyclic = [row for row in components if len(row) > 1 or row[0] in self_loops]
    return {
        "schemaVersion": "successor-graph/2",
        "graphProjectionVersion": 1,
        "language": "en",
        "sourceBaseline": {
            "document": "docs/v2.0.0/event-beat-disposition.md",
            "heading": "Natural successor edges",
            "beatCatalogSha256": _sha(catalog),
        },
        "selectionContract": {
            "edgeSet": "closed_explicit_only",
            "continuationBasePriority": 58,
            "continuityBonus": 6,
            "preferredEdgeBonus": 6,
            "allowedEdgeBonus": 0,
            "materialRevisionBonus": 6,
            "deduplicateEventAndSuccessor": True,
            "closingBypassesConsecutiveCap": True,
            "closingMutatesEpisodeTruth": False,
            "noEligibleSuccessor": "return_to_normal_arbitration",
            "tieBreak": [
                "urgency_desc",
                "effective_score_desc",
                "candidate_order_asc",
                "stable_ids_asc",
            ],
        },
        "globalGuards": GLOBAL_GUARDS,
        "storyDefinitions": [
            {
                "id": story_id,
                "maxConsecutiveNonClosingBeats": values[0],
                "cadenceMinimumMs": values[1],
                "onNoEligibleSuccessor": "remain_truth_owned_and_return_to_arbitration",
            }
            for story_id, values in STORIES.items()
        ],
        "guardProfiles": profiles,
        "edges": edges,
        "nodePolicies": [
            {
                "beatId": beat_id,
                "incomingEdgeCount": incoming[beat_id],
                "outgoingEdgeCount": outgoing[beat_id],
                "successorDisposition": "expand_explicit_edges"
                if outgoing[beat_id]
                else "no_implicit_continuation",
            }
            for beat_id in beat_ids
        ],
        "analysis": {
            "nodeCount": len(beat_ids),
            "edgeCount": len(edges),
            "strongComponentCount": len(components),
            "cyclicComponents": cyclic,
            "isDirectedAcyclic": not cyclic,
            "nonterminalComponentPolicy": "every expansion is bounded by explicit edge progress, validity, cadence, material exposure and story cap",
        },
    }


def _closed_object(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required or list(properties),
    }


def build_schema() -> dict[str, Any]:
    ident = {"type": "string", "pattern": "^[a-z0-9][a-z0-9._>-]*$", "maxLength": 160}

    def strings(minimum: int = 0) -> dict[str, Any]:
        return {
            "type": "array",
            "minItems": minimum,
            "uniqueItems": True,
            "items": ident,
        }

    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://irswitch.local/contracts/v2/successor-graph.schema.json",
        "title": "irswitch v2 natural successor graph",
        **_closed_object(
            {
                "schemaVersion": {"const": "successor-graph/2"},
                "graphProjectionVersion": {"const": 1},
                "language": {"const": "en"},
                "sourceBaseline": _closed_object(
                    {
                        "document": {"type": "string"},
                        "heading": {"const": "Natural successor edges"},
                        "beatCatalogSha256": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
                    }
                ),
                "selectionContract": _closed_object(
                    {
                        "edgeSet": {"const": "closed_explicit_only"},
                        "continuationBasePriority": {"const": 58},
                        "continuityBonus": {"const": 6},
                        "preferredEdgeBonus": {"const": 6},
                        "allowedEdgeBonus": {"const": 0},
                        "materialRevisionBonus": {"const": 6},
                        "deduplicateEventAndSuccessor": {"const": True},
                        "closingBypassesConsecutiveCap": {"const": True},
                        "closingMutatesEpisodeTruth": {"const": False},
                        "noEligibleSuccessor": {"const": "return_to_normal_arbitration"},
                        "tieBreak": {
                            "const": [
                                "urgency_desc",
                                "effective_score_desc",
                                "candidate_order_asc",
                                "stable_ids_asc",
                            ]
                        },
                    }
                ),
                "globalGuards": {"const": GLOBAL_GUARDS},
                "storyDefinitions": {
                    "type": "array",
                    "minItems": 11,
                    "maxItems": 11,
                    "items": _closed_object(
                        {
                            "id": ident,
                            "maxConsecutiveNonClosingBeats": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 8,
                            },
                            "cadenceMinimumMs": {
                                "type": "integer",
                                "minimum": 0,
                                "maximum": 300000,
                            },
                            "onNoEligibleSuccessor": {
                                "const": "remain_truth_owned_and_return_to_arbitration"
                            },
                        }
                    ),
                },
                "guardProfiles": {
                    "type": "array",
                    "minItems": 1,
                    "items": _closed_object(
                        {
                            "id": ident,
                            "normativeText": {"type": "string", "minLength": 1},
                            "identityBindings": strings(1),
                            "conditions": strings(1),
                            "unknownVerdict": {"const": "ineligible"},
                        }
                    ),
                },
                "edges": {
                    "type": "array",
                    "minItems": 1,
                    "items": _closed_object(
                        {
                            "id": ident,
                            "ordinal": {"type": "integer", "minimum": 1},
                            "fromBeatId": ident,
                            "toBeatId": ident,
                            "guardProfileId": ident,
                            "preference": {"enum": ["preferred", "allowed"]},
                            "scoreBonus": {"enum": [0, 6]},
                            "edgeClass": {"enum": ["non-closing", "closing"]},
                            "episodeTruthEffect": {"const": "none"},
                        }
                    ),
                },
                "nodePolicies": {
                    "type": "array",
                    "minItems": 1,
                    "items": _closed_object(
                        {
                            "beatId": ident,
                            "incomingEdgeCount": {"type": "integer", "minimum": 0},
                            "outgoingEdgeCount": {"type": "integer", "minimum": 0},
                            "successorDisposition": {
                                "enum": ["expand_explicit_edges", "no_implicit_continuation"]
                            },
                        }
                    ),
                },
                "analysis": _closed_object(
                    {
                        "nodeCount": {"const": 64},
                        "edgeCount": {"const": 50},
                        "strongComponentCount": {"const": 64},
                        "cyclicComponents": {"const": []},
                        "isDirectedAcyclic": {"const": True},
                        "nonterminalComponentPolicy": {"type": "string", "minLength": 1},
                    }
                ),
            }
        ),
        "x-irswitch-invariants": [
            "successor_edges_match_human_table_exactly",
            "all_beat_and_guard_references_resolve",
            "edge_ids_and_ordinals_unique",
            "preference_bonus_matches_policy",
            "node_degrees_match_edges",
            "scc_analysis_matches_graph",
            "no_unbounded_nonterminal_component",
            "beat_catalog_hash_matches",
        ],
    }


def validate_graph(graph: dict[str, Any], schema: dict[str, Any]) -> None:
    errors = schema_errors(graph, schema, schema)
    if errors:
        raise ValueError(errors[0])
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    beat_ids = [beat["id"] for beat in catalog["beats"]]
    if graph["sourceBaseline"]["beatCatalogSha256"] != _sha(catalog):
        raise ValueError("beat catalog hash differs")
    edges = graph["edges"]
    edge_ids = [edge["id"] for edge in edges]
    ordinals = [edge["ordinal"] for edge in edges]
    if len(set(edge_ids)) != len(edge_ids) or ordinals != list(range(1, len(edges) + 1)):
        raise ValueError("edge IDs or ordinals are not unique and contiguous")
    known_beats = set(beat_ids)
    known_guards = {row["id"] for row in graph["guardProfiles"]}
    for edge in edges:
        if edge["fromBeatId"] not in known_beats or edge["toBeatId"] not in known_beats:
            raise ValueError("edge has unknown beat reference")
        if edge["guardProfileId"] not in known_guards:
            raise ValueError("edge has unknown guard reference")
        expected_bonus = 6 if edge["preference"] == "preferred" else 0
        if edge["scoreBonus"] != expected_bonus:
            raise ValueError("edge preference bonus differs")
    components = _strong_components(beat_ids, edges)
    self_loops = {edge["fromBeatId"] for edge in edges if edge["fromBeatId"] == edge["toBeatId"]}
    cyclic = [row for row in components if len(row) > 1 or row[0] in self_loops]
    if cyclic:
        raise ValueError("unbounded nonterminal component")
    outgoing = Counter(edge["fromBeatId"] for edge in edges)
    incoming = Counter(edge["toBeatId"] for edge in edges)
    policies = {row["beatId"]: row for row in graph["nodePolicies"]}
    if set(policies) != known_beats:
        raise ValueError("node policies do not cover exact beat catalog")
    for beat_id, policy in policies.items():
        if (
            policy["incomingEdgeCount"] != incoming[beat_id]
            or policy["outgoingEdgeCount"] != outgoing[beat_id]
        ):
            raise ValueError("node degree differs from edge set")
        expected_disposition = (
            "expand_explicit_edges" if outgoing[beat_id] else "no_implicit_continuation"
        )
        if policy["successorDisposition"] != expected_disposition:
            raise ValueError("node successor disposition differs")
    analysis = graph["analysis"]
    if (
        analysis["strongComponentCount"] != len(components)
        or analysis["cyclicComponents"] != cyclic
        or analysis["isDirectedAcyclic"] != (not cyclic)
    ):
        raise ValueError("SCC analysis differs from graph")
    expected = build_graph()
    if canonical(graph["edges"]) != canonical(expected["edges"]):
        raise ValueError("edges differ from frozen human table")
    if canonical(graph["guardProfiles"]) != canonical(expected["guardProfiles"]):
        raise ValueError("guard profiles differ from frozen contract")
    if canonical(graph["storyDefinitions"]) != canonical(expected["storyDefinitions"]):
        raise ValueError("story definitions differ from frozen contract")


def _set_path(value: Any, path: list[Any], replacement: Any) -> None:
    target = value
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = replacement


def validate_mutations(graph: dict[str, Any], schema: dict[str, Any]) -> int:
    fixtures = json.loads(MUTATIONS_PATH.read_text(encoding="utf-8"))
    for fixture in fixtures["invalid"]:
        mutated = copy.deepcopy(graph)
        if fixture["operation"] == "delete":
            target = mutated
            for part in fixture["path"][:-1]:
                target = target[part]
            del target[fixture["path"][-1]]
        elif fixture["operation"] == "set":
            _set_path(mutated, fixture["path"], fixture["value"])
        else:
            raise ValueError(f"unknown mutation operation {fixture['operation']}")
        try:
            validate_graph(mutated, schema)
        except ValueError as exc:
            if fixture["errorContains"] not in str(exc):
                raise ValueError(
                    f"mutation {fixture['id']} failed for wrong reason: {exc}"
                ) from exc
        else:
            raise ValueError(f"mutation {fixture['id']} was accepted")
    return len(fixtures["invalid"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    generated_graph = build_graph()
    generated_schema = build_schema()
    if args.write:
        GRAPH_PATH.write_text(
            json.dumps(generated_graph, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        SCHEMA_PATH.write_text(
            json.dumps(generated_schema, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {GRAPH_PATH.name} and {SCHEMA_PATH.name}")
        return 0
    checked_graph = json.loads(GRAPH_PATH.read_text(encoding="utf-8"))
    checked_schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if canonical(generated_graph) != canonical(checked_graph):
        print("successor-graph.json is stale", file=sys.stderr)
        return 1
    if canonical(generated_schema) != canonical(checked_schema):
        print("successor-graph.schema.json is stale", file=sys.stderr)
        return 1
    validate_graph(checked_graph, checked_schema)
    mutation_count = validate_mutations(checked_graph, checked_schema)
    terminal_count = sum(row["outgoingEdgeCount"] == 0 for row in checked_graph["nodePolicies"])
    print(
        f"Successor graph OK: 64 nodes, 50 edges, {terminal_count} no-continuation nodes, DAG, {mutation_count} rejected mutations"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
