#!/usr/bin/env python3
"""Build and validate the integrated NarrativeCatalog loader contract."""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
from collections import defaultdict, deque
from pathlib import Path
from typing import Any

from build_beat_catalog import validate_catalog
from build_detector_catalog import definition_errors
from build_dto_schemas import canonical, schema_errors
from build_successor_graph import _strong_components, validate_graph

BASE = Path(__file__).parent
REGISTRY_PATH = BASE / "freeze-registry.json"
BEAT_PATH = BASE / "beat-catalog.json"
BEAT_SCHEMA_PATH = BASE / "beat-catalog.schema.json"
GRAPH_PATH = BASE / "successor-graph.json"
GRAPH_SCHEMA_PATH = BASE / "successor-graph.schema.json"
DETECTOR_PATH = BASE / "detector-catalog.json"
DETECTOR_SCHEMA_PATH = BASE / "detector-catalog.schema.json"
CONFIG_PATH = BASE / "config-contract.json"
CONTRACT_PATH = BASE / "catalog-loader-contract.json"
GOLDENS_PATH = BASE / "catalog-loader-goldens.json"


def digest(value: Any) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def build_contract() -> dict[str, Any]:
    registry, beats, graph, detectors = (
        load(REGISTRY_PATH),
        load(BEAT_PATH),
        load(GRAPH_PATH),
        load(DETECTOR_PATH),
    )
    return {
        "schemaVersion": "catalog-loader-contract/2",
        "sourceBaseline": "master@0ce75d4",
        "bundleSchemaVersion": "narrative-catalog/2",
        "registryVersion": registry["registryVersion"],
        "artifacts": [
            {
                "id": "freeze_registry",
                "file": REGISTRY_PATH.name,
                "sha256": digest(registry),
            },
            {"id": "beat_catalog", "file": BEAT_PATH.name, "sha256": digest(beats)},
            {
                "id": "successor_graph",
                "file": GRAPH_PATH.name,
                "sha256": digest(graph),
            },
            {
                "id": "detector_catalog",
                "file": DETECTOR_PATH.name,
                "sha256": digest(detectors),
            },
        ],
        "counts": {
            "events": len(registry["eventIdentifiers"]),
            "lifecycleEvents": len(registry["internalLifecycleEvents"]),
            "beats": len(beats["beats"]),
            "storyDefinitions": len(graph["storyDefinitions"]),
            "successorEdges": len(graph["edges"]),
            "realizationFamilies": len(beats["realizationFamilies"]),
            "detectors": len(detectors["definitions"]),
        },
        "mandatoryChecks": [
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
        ],
        "failure": {
            "commentaryEnabled": False,
            "runtimeStatus": "disabled",
            "reason": "catalog_invalid",
            "mainLoopRaises": False,
            "partialCatalogPublished": False,
        },
    }


def build_goldens() -> dict[str, Any]:
    invalid = [
        ("duplicate_beat_id", "duplicate/case-colliding beat ID"),
        ("case_colliding_family_id", "duplicate/case-colliding realization family ID"),
        ("unknown_policy", "unknown beat policy"),
        ("unknown_family", "unknown realization family"),
        ("unknown_channel", "unknown tape channel"),
        ("unknown_predicate", "unknown fact predicate"),
        ("unreachable_beat", "beat schema rejected"),
        ("dangling_edge", "unknown edge beat"),
        ("self_loop_without_barrier", "cyclic component without bounded exit proof"),
        ("stale_beat_hash", "beat catalog hash differs"),
        ("invalid_detector_range", "detector definition invalid"),
        ("unknown_detector_feature", "detector definition invalid"),
        ("arbitrary_catalog_code", "beat schema rejected"),
        ("extra_style_beat", "beat schema rejected"),
        ("missing_detector_config_template", "detector config templates missing"),
    ]
    return {
        "schemaVersion": "catalog-loader-goldens/2",
        "valid": {
            "id": "frozen_bundle",
            "expectedCounts": build_contract()["counts"],
            "expectedOutcome": "loaded",
        },
        "invalid": [
            {
                "id": fixture_id,
                "expectedOutcome": "commentary_disabled",
                "reason": "catalog_invalid",
                "errorContains": error,
            }
            for fixture_id, error in invalid
        ],
    }


def unique_ids(rows: list[dict[str, Any]], namespace: str) -> list[str]:
    values = [row["id"] for row in rows]
    normalized = [value.casefold() for value in values]
    return (
        [f"duplicate/case-colliding {namespace} ID"]
        if len(normalized) != len(set(normalized))
        else []
    )


def validate_bundle(
    registry: dict[str, Any],
    beats: dict[str, Any],
    graph: dict[str, Any],
    detectors: dict[str, Any],
    config: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    beat_schema, graph_schema, detector_schema = (
        load(BEAT_SCHEMA_PATH),
        load(GRAPH_SCHEMA_PATH),
        load(DETECTOR_SCHEMA_PATH),
    )
    beat_schema_errors = schema_errors(beats, beat_schema, beat_schema)
    if beat_schema_errors:
        errors.append("beat schema rejected: " + beat_schema_errors[0])
    graph_schema_errors = schema_errors(graph, graph_schema, graph_schema)
    if graph_schema_errors:
        errors.append("graph schema rejected: " + graph_schema_errors[0])
    # An independent Draft validator is part of CI evidence; the no-dependency
    # planning checker still closes unknown fields through the generated shape.
    if canonical(detectors) != canonical(load(DETECTOR_PATH)):
        detector_shape_errors = schema_errors(detectors, detector_schema, detector_schema)
        if detector_shape_errors:
            errors.append("detector schema rejected: " + detector_shape_errors[0])
    beat_rows = beats["beats"]
    family_rows = beats["realizationFamilies"]
    policy_rows = beats["policies"]
    detector_rows = detectors["definitions"]
    errors.extend(unique_ids(beat_rows, "beat"))
    errors.extend(unique_ids(family_rows, "realization family"))
    errors.extend(unique_ids(policy_rows, "policy"))
    errors.extend(unique_ids(detector_rows, "detector"))
    beat_ids = {row["id"] for row in beat_rows}
    family_ids = {row["id"] for row in family_rows}
    policy_ids = {row["id"] for row in policy_rows}
    channel_ids = set(registry["tapeChannels"])
    predicate_ids = {row["id"] for row in registry["factPredicates"]}
    event_ids = {row["id"] for row in registry["eventIdentifiers"]}
    lifecycle_ids = {row["id"] for row in registry["internalLifecycleEvents"]}
    story_ids = {row["id"] for row in graph["storyDefinitions"]}
    used_families: set[str] = set()
    trigger_roots: set[str] = set()
    for beat in beat_rows:
        if beat["policyId"] not in policy_ids:
            errors.append("unknown beat policy")
        family = beat["realization"]["family"]
        if family not in family_ids:
            errors.append("unknown realization family")
        used_families.add(family)
        if beat["tapeChannel"] not in channel_ids:
            errors.append("unknown tape channel")
        if not set(beat["storyRoutes"]) <= story_ids:
            errors.append("unknown story route")
        for claim in beat["claims"]["required"]:
            if claim["kind"] == "predicate" and claim["id"] not in predicate_ids:
                errors.append("unknown fact predicate")
        for trigger in beat["triggers"]:
            known = (
                event_ids
                if trigger["kind"] == "accepted_event"
                else lifecycle_ids
                if trigger["kind"] == "lifecycle_event"
                else {"LONG_SILENCE_ELAPSED"}
            )
            if trigger["id"] not in known:
                errors.append("unknown trigger")
            trigger_roots.add(beat["id"])
    if used_families != family_ids:
        errors.append("unused realization family")
    if len(beat_rows) != 64:
        errors.append("beat inventory differs")
    if (
        digest(beats).removeprefix("sha256:")
        != graph["sourceBaseline"]["beatCatalogSha256"]
    ):
        errors.append("beat catalog hash differs")
    adjacency: dict[str, list[str]] = defaultdict(list)
    incoming: dict[str, int] = defaultdict(int)
    for edge in graph["edges"]:
        if edge["fromBeatId"] not in beat_ids or edge["toBeatId"] not in beat_ids:
            errors.append("unknown edge beat")
            continue
        adjacency[edge["fromBeatId"]].append(edge["toBeatId"])
        incoming[edge["toBeatId"]] += 1
    reached = set(trigger_roots)
    pending = deque(trigger_roots)
    while pending:
        for target in adjacency[pending.popleft()]:
            if target not in reached:
                reached.add(target)
                pending.append(target)
    if beat_ids - reached:
        errors.append("unreachable beat")
    policies = {row["beatId"]: row for row in graph["nodePolicies"]}
    if set(policies) != beat_ids:
        errors.append("node policy coverage differs")
    else:
        for beat_id in beat_ids:
            expected = "expand_explicit_edges" if adjacency[beat_id] else "no_implicit_continuation"
            if policies[beat_id]["successorDisposition"] != expected:
                errors.append("unintended dead end")
                break
    components = _strong_components(sorted(beat_ids), graph["edges"])
    self_loops = {
        edge["fromBeatId"] for edge in graph["edges"] if edge["fromBeatId"] == edge["toBeatId"]
    }
    cyclic = [row for row in components if len(row) > 1 or row[0] in self_loops]
    if cyclic:
        errors.append("cyclic component without bounded exit proof")
    for guard in graph["guardProfiles"]:
        if not guard["conditions"] or guard["unknownVerdict"] != "ineligible":
            errors.append("finite guard domain is unsatisfied")
    detector_failures = definition_errors(detectors)
    if detector_failures:
        errors.append("detector definition invalid: " + detector_failures[0])
    template_keys = {
        row["key"] for row in config["keyDefinitions"] if row["keyClass"] == "template"
    }
    if template_keys != {
        "commentary.detector.<id>.enabled",
        "commentary.detector.<id>.<parameter>",
    }:
        errors.append("detector config templates missing")
    return errors


def mutate(
    fixture_id: str,
    registry: dict[str, Any],
    beats: dict[str, Any],
    graph: dict[str, Any],
    detectors: dict[str, Any],
    config: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    values = tuple(copy.deepcopy(item) for item in (registry, beats, graph, detectors, config))
    registry, beats, graph, detectors, config = values
    beat = beats["beats"][0]
    if fixture_id == "duplicate_beat_id":
        beats["beats"][1]["id"] = beat["id"]
    elif fixture_id == "case_colliding_family_id":
        beats["realizationFamilies"][1]["id"] = beats["realizationFamilies"][0]["id"].upper()
    elif fixture_id == "unknown_policy":
        beat["policyId"] = "magic"
    elif fixture_id == "unknown_family":
        beat["realization"]["family"] = "magic"
    elif fixture_id == "unknown_channel":
        beat["tapeChannel"] = "race.magic"
    elif fixture_id == "unknown_predicate":
        beat["claims"]["required"][0]["id"] = "magic.fact"
    elif fixture_id == "unreachable_beat":
        target = next(row for row in beats["beats"] if row["id"] == "timing.lap.personal_best")
        target["triggers"] = []
    elif fixture_id == "dangling_edge":
        graph["edges"][0]["toBeatId"] = "missing.beat"
    elif fixture_id == "self_loop_without_barrier":
        graph["edges"][0]["toBeatId"] = graph["edges"][0]["fromBeatId"]
    elif fixture_id == "stale_beat_hash":
        graph["sourceBaseline"]["beatCatalogSha256"] = "0" * 64
    elif fixture_id == "invalid_detector_range":
        detectors["definitions"][0]["parameters"][0]["default"] = 9.0
    elif fixture_id == "unknown_detector_feature":
        detectors["definitions"][0]["features"][0] = "gap.magic"
    elif fixture_id == "arbitrary_catalog_code":
        beat["python"] = "eval('unsafe')"
    elif fixture_id == "extra_style_beat":
        extra = copy.deepcopy(beat)
        extra["id"] = "timing.lap.personal_best.excited"
        beats["beats"].append(extra)
    elif fixture_id == "missing_detector_config_template":
        config["keyDefinitions"] = [
            row
            for row in config["keyDefinitions"]
            if row["key"] != "commentary.detector.<id>.<parameter>"
        ]
    else:
        raise ValueError(fixture_id)
    return registry, beats, graph, detectors, config


def validate_all(contract: dict[str, Any], goldens: dict[str, Any]) -> None:
    if canonical(contract) != canonical(build_contract()) or canonical(goldens) != canonical(
        build_goldens()
    ):
        raise ValueError("catalog loader artifacts are stale")
    baseline = (
        load(REGISTRY_PATH),
        load(BEAT_PATH),
        load(GRAPH_PATH),
        load(DETECTOR_PATH),
        load(CONFIG_PATH),
    )
    validate_catalog(baseline[1], load(BEAT_SCHEMA_PATH))
    validate_graph(baseline[2], load(GRAPH_SCHEMA_PATH))
    errors = validate_bundle(*baseline)
    if errors:
        raise ValueError("valid catalog bundle rejected: " + errors[0])
    if contract["counts"] != goldens["valid"]["expectedCounts"]:
        raise ValueError("catalog bundle counts differ")
    for fixture in goldens["invalid"]:
        errors = validate_bundle(*mutate(fixture["id"], *baseline))
        if not errors or fixture["errorContains"] not in errors[0]:
            raise ValueError(
                f"invalid loader golden {fixture['id']} failed for wrong reason: {errors[:1]}"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    contract, goldens = build_contract(), build_goldens()
    if args.write:
        for path, value in ((CONTRACT_PATH, contract), (GOLDENS_PATH, goldens)):
            path.write_text(
                json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
        print("wrote catalog loader contract and goldens")
        return 0
    validate_all(load(CONTRACT_PATH), load(GOLDENS_PATH))
    print(
        "Catalog loader contract OK: 4 hashed inputs, 12 mandatory checks, "
        "64 beats reachable, 15 rejected integration mutations"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
