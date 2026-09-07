#!/usr/bin/env python3
"""Build and validate the three frozen v2 temporal detector definitions."""

from __future__ import annotations

import argparse
import copy
import json
import math
from pathlib import Path
from typing import Any

from build_dto_schemas import canonical

REGISTRY_PATH = Path(__file__).with_name("freeze-registry.json")
CATALOG_PATH = Path(__file__).with_name("detector-catalog.json")
SCHEMA_PATH = Path(__file__).with_name("detector-catalog.schema.json")
GOLDENS_PATH = Path(__file__).with_name("detector-catalog-goldens.json")
MUTATIONS_PATH = Path(__file__).with_name("detector-catalog-mutations.json")

PARAMETERS: dict[str, tuple[str, str, float | int, float | int, float | int]] = {
    "sample_interval_s": ("number", "seconds", 0.25, 0.10, 1.00),
    "trend_window_s": ("number", "seconds", 12.0, 6.0, 30.0),
    "bucket_s": ("number", "seconds", 1.0, 0.5, 2.0),
    "min_samples": ("integer", "count", 8, 6, 60),
    "min_coverage": ("number", "fraction", 0.80, 0.60, 1.00),
    "min_confidence": ("number", "fraction", 0.70, 0.50, 1.00),
    "enter_gap_max_s": ("number", "seconds", 3.0, 1.0, 8.0),
    "min_closing_change_s": ("number", "seconds", 0.60, 0.20, 2.00),
    "max_closing_slope": ("number", "seconds_per_second", -0.04, -0.30, -0.01),
    "confirm_s": ("number", "seconds", 3.0, 1.0, 10.0),
    "material_change_s": ("number", "seconds", 0.40, 0.10, 1.50),
    "update_min_interval_s": ("number", "seconds", 6.0, 2.0, 30.0),
    "exit_gap_min_s": ("number", "seconds", 4.0, 1.5, 12.0),
    "clear_slope": ("number", "seconds_per_second", -0.01, -0.05, 0.10),
    "clear_s": ("number", "seconds", 2.0, 1.0, 10.0),
    "stale_after_s": ("number", "seconds", 1.0, 0.5, 3.0),
    "approach_enter_s": ("number", "gap_seconds", 1.50, 0.80, 3.00),
    "approach_exit_s": ("number", "gap_seconds", 1.80, 1.00, 4.00),
    "attack_enter_s": ("number", "gap_seconds", 0.80, 0.30, 1.50),
    "attack_exit_s": ("number", "gap_seconds", 1.10, 0.50, 2.00),
    "overlap_enter_s": ("number", "gap_seconds", 0.35, 0.10, 0.80),
    "overlap_exit_s": ("number", "gap_seconds", 0.55, 0.20, 1.20),
    "overlap_confirm_s": ("number", "seconds", 0.50, 0.25, 2.00),
}
COMPOSITE_PARAMETERS = {
    "two_front_confirm_s": ("number", "seconds", 1.00, 0.50, 4.00),
    "two_front_clear_s": ("number", "seconds", 1.00, 0.50, 4.00),
}
FEATURES = [
    "gap.relation.seconds.estimated_v1",
    "gap.trend.slope",
    "gap.trend.net_closing",
    "gap.trend.coverage",
    "gap.trend.confidence",
    "gap.target_stable",
    "vehicle.phase.current",
]
INVARIANTS = [
    "sample_interval_s < bucket_s <= trend_window_s",
    "min_samples * sample_interval_s <= trend_window_s",
    "confirm_s <= trend_window_s",
    "enter_gap_max_s < exit_gap_min_s",
    "overlap_enter_s < overlap_exit_s <= attack_enter_s < attack_exit_s",
    "attack_exit_s <= approach_enter_s < approach_exit_s <= enter_gap_max_s",
    "update_min_interval_s >= clear_s",
    "stale_after_s <= trend_window_s",
]


def parameter_rows(
    source: dict[str, tuple[str, str, float | int, float | int, float | int]],
) -> list[dict[str, Any]]:
    return [
        {
            "id": key,
            "type": spec[0],
            "unit": spec[1],
            "default": spec[2],
            "minimum": spec[3],
            "maximum": spec[4],
            "provenance": "estimated",
        }
        for key, spec in source.items()
    ]


def directional(
    detector_id: str,
    actors: list[str],
    start_event: str,
    internal_kind: str,
    channel: str,
) -> dict[str, Any]:
    return {
        "id": detector_id,
        "version": 1,
        "algorithm": "bucketed_ols_closing_v1",
        "kind": "directional",
        "orderedActors": actors,
        "correlationKey": ["streamEpoch", "occurrenceId", "relationEpoch"],
        "fsmStates": ["inactive", "candidate", "active", "clearing"],
        "features": FEATURES,
        "parameters": parameter_rows(PARAMETERS),
        "crossFieldInvariants": INVARIANTS,
        "entry": {
            "holdParameter": "confirm_s",
            "allPredicates": [
                "stream_confirmed_active",
                "stage_race",
                "both_actors_racing_or_target_surface_known",
                "race_flag_green",
                "ordered_relation_stable",
                "feature_age_lte_stale_after_s",
                "gap_lte_enter_gap_max_s",
                "net_closing_gte_min_closing_change_s",
                "slope_lte_max_closing_slope",
                "coverage_gte_min_coverage",
                "confidence_gte_min_confidence",
                "actors_world_valid",
            ],
            "unknownSatisfies": False,
        },
        "clear": {
            "holdParameter": "clear_s",
            "anyPredicates": [
                "gap_gte_exit_gap_min_s",
                "slope_gte_clear_slope",
                "coverage_lt_min_coverage",
                "confidence_lt_min_confidence",
                "feature_stale_or_unknown",
                "race_flag_not_green",
            ],
            "immediateInvalidators": [
                "occurrence_or_stream_change",
                "ordered_target_or_relation_change",
                "pit_tow_teleport_or_not_in_world",
                "unsupported_stage",
                "checkered_or_session_end",
                "identity_conflict",
            ],
        },
        "output": {
            "startEvent": start_event,
            "internalKind": internal_kind,
            "factPredicate": "battle.closing",
            "tapeChannel": channel,
            "endedEvent": None,
        },
        "materialUpdate": {
            "conditions": ["hysteretic_band_changed", "net_closing_delta_gte_material_change_s"],
            "minimumIntervalParameter": "update_min_interval_s",
            "maximumCandidatesPerFrame": 1,
        },
        "bands": [
            {
                "id": "closing",
                "factPredicate": "battle.closing",
                "enterGapParameter": None,
                "exitGapParameter": "approach_enter_s",
                "event": None,
            },
            {
                "id": "approach",
                "factPredicate": "battle.approaching",
                "enterGapParameter": "approach_enter_s",
                "exitGapParameter": "approach_exit_s",
                "event": "APPROACH",
            },
            {
                "id": "attack",
                "factPredicate": "battle.attack_range",
                "enterGapParameter": "attack_enter_s",
                "exitGapParameter": "attack_exit_s",
                "event": "ATTACK_RANGE",
            },
            {
                "id": "overlap",
                "factPredicate": "battle.side_by_side",
                "enterGapParameter": "overlap_enter_s",
                "exitGapParameter": "overlap_exit_s",
                "event": "SIDE_BY_SIDE",
            },
        ],
        "experimental": True,
        "tuningPolicy": "required",
    }


def build_catalog() -> dict[str, Any]:
    return {
        "schemaVersion": "detector-catalog/2",
        "catalogProjectionVersion": 1,
        "sourceBaseline": "master@0ce75d4",
        "frameOrder": "strictly_increasing_process_global_frameSequence",
        "duplicateOrOlderFrame": "audited_noop",
        "definitions": [
            directional(
                "battle_ahead_v1",
                ["hero", "targetAhead"],
                "HUNTING",
                "battle.pursuit",
                "race.battle.closing",
            ),
            directional(
                "battle_behind_v1",
                ["challengerBehind", "hero"],
                "HUNTED",
                "battle.pressure_behind",
                "race.battle.pressure",
            ),
            {
                "id": "battle_two_front_v1",
                "version": 1,
                "algorithm": "two_active_relations_v1",
                "kind": "composite",
                "orderedActors": ["rear", "hero", "front"],
                "correlationKey": [
                    "streamEpoch",
                    "occurrenceId",
                    "frontRelationEpoch",
                    "rearRelationEpoch",
                ],
                "fsmStates": ["inactive", "candidate", "active", "clearing"],
                "features": [],
                "parameters": parameter_rows(COMPOSITE_PARAMETERS),
                "crossFieldInvariants": [],
                "entry": {
                    "holdParameter": "two_front_confirm_s",
                    "allPredicates": [
                        "front_relation_active",
                        "rear_relation_active",
                        "same_stream_occurrence_hero",
                        "distinct_targets",
                    ],
                    "unknownSatisfies": False,
                },
                "clear": {
                    "holdParameter": "two_front_clear_s",
                    "anyPredicates": ["either_relation_inactive"],
                    "immediateInvalidators": [
                        "target_or_relation_epoch_replaced",
                        "occurrence_or_stream_change",
                    ],
                },
                "output": {
                    "startEvent": "BATTLE_FOR_POSITION",
                    "internalKind": "battle.two_front",
                    "factPredicate": None,
                    "featureId": "battle.two_front_active",
                    "tapeChannel": "race.battle.two_front",
                    "endedEvent": None,
                },
                "materialUpdate": None,
                "bands": [],
                "experimental": True,
                "tuningPolicy": "required",
            },
        ],
        "capturePlan": {
            "preWindow": "complete_trend_window",
            "postWindowSeconds": 5.0,
            "requiredFields": [
                "effectiveParameters",
                "featureQuality",
                "coverage",
                "predicateTrace",
                "transitionReason",
                "nearThresholdNegatives",
            ],
            "requiredCaptureLossDisablesDetectorForRun": True,
        },
    }


def build_schema() -> dict[str, Any]:
    # The builder performs the referential and algorithmic checks; this schema closes
    # the complete generated shape without introducing a runtime dependency.
    catalog = build_catalog()

    def shape(value: Any) -> dict[str, Any]:
        if value is None:
            return {"type": "null"}
        if isinstance(value, bool):
            return {"type": "boolean"}
        if isinstance(value, int):
            return {"type": "integer"}
        if isinstance(value, float):
            return {"type": "number"}
        if isinstance(value, str):
            return {"type": "string"}
        if isinstance(value, list):
            item_shapes = {canonical(shape(item)): shape(item) for item in value}
            if not item_shapes:
                items = {}
            elif len(item_shapes) == 1:
                items = next(iter(item_shapes.values()))
            else:
                items = {"anyOf": list(item_shapes.values())}
            return {"type": "array", "items": items}
        properties = {key: shape(item) for key, item in value.items()}
        return {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        }

    result = shape(catalog)
    result.update(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "$id": "https://irswitch.local/contracts/detector-catalog-v2.schema.json",
            "x-irswitch-invariants": [
                "exact_three_detector_ids",
                "parameter_ranges_and_cross_fields",
                "directional_algorithms_are_identical",
                "registry_references_resolve",
                "actor_direction_is_ordered",
                "unknown_never_enters_or_updates",
            ],
        }
    )
    return result


def signal(
    enter: bool | None,
    clear: bool | None = False,
    elapsed: float = 0.0,
    invalidator: bool = False,
    material: bool = False,
    since_update: float = 0.0,
) -> dict[str, Any]:
    return {
        "enter": enter,
        "clear": clear,
        "elapsedInStateSeconds": elapsed,
        "immediateInvalidator": invalidator,
        "materialChange": material,
        "secondsSinceUpdate": since_update,
    }


def reduce_directional(
    state: str, row: dict[str, Any], confirm: float = 3.0, clear_hold: float = 2.0
) -> tuple[str, str | None]:
    if row["immediateInvalidator"]:
        return "inactive", "ended" if state in {"active", "clearing"} else None
    enter, clear = row["enter"], row["clear"]
    if state == "inactive":
        return ("candidate", None) if enter is True else ("inactive", None)
    if state == "candidate":
        if enter is not True:
            return "inactive", None
        return (
            ("active", "started")
            if row["elapsedInStateSeconds"] >= confirm
            else ("candidate", None)
        )
    if state == "active":
        if clear is True or clear is None:
            return "clearing", None
        if (
            row["materialChange"]
            and row["secondsSinceUpdate"] >= PARAMETERS["update_min_interval_s"][2]
        ):
            return "active", "updated"
        return "active", None
    if enter is True:
        return "active", None
    if (clear is True or clear is None) and row["elapsedInStateSeconds"] >= clear_hold:
        return "inactive", "ended"
    return "clearing", None


def directional_trace(
    fixture_id: str, steps: list[dict[str, Any]], assertions: list[str]
) -> dict[str, Any]:
    state = "inactive"
    output = []
    for row in steps:
        next_state, emission = reduce_directional(state, row)
        output.append({**row, "stateBefore": state, "stateAfter": next_state, "emission": emission})
        state = next_state
    return {"id": fixture_id, "steps": output, "assertions": assertions}


def build_goldens() -> dict[str, Any]:
    traces = [
        directional_trace(
            "sustained_closing_enters_once",
            [signal(True), signal(True, elapsed=2.99), signal(True, elapsed=3.0), signal(True)],
            ["one_started", "sign_slope_negative_net_closing_positive"],
        ),
        directional_trace(
            "braking_oscillation_does_not_enter",
            [signal(True), signal(False, elapsed=1.0), signal(True), signal(False, elapsed=1.0)],
            ["no_started", "insufficient_net_closing_false"],
        ),
        directional_trace(
            "unknown_breaks_confirmation",
            [signal(True), signal(None, clear=None, elapsed=1.0)],
            ["unknown_never_satisfies_enter"],
        ),
        directional_trace(
            "active_stale_clears_after_hold",
            [
                signal(True),
                signal(True, elapsed=3.0),
                signal(None, clear=None),
                signal(None, clear=None, elapsed=1.99),
                signal(None, clear=None, elapsed=2.0),
            ],
            ["one_started", "one_ended", "unknown_clear_hold"],
        ),
        directional_trace(
            "target_swap_closes_immediately",
            [signal(True), signal(True, elapsed=3.0), signal(None, invalidator=True)],
            ["relation_epoch_immutable", "one_ended"],
        ),
        directional_trace(
            "material_update_rate_limited",
            [
                signal(True),
                signal(True, elapsed=3.0),
                signal(True, material=True, since_update=5.99),
                signal(True, material=True, since_update=6.0),
            ],
            ["one_updated", "latest_candidate_only"],
        ),
        directional_trace(
            "clear_cancelled_by_full_enter",
            [
                signal(True),
                signal(True, elapsed=3.0),
                signal(False, clear=True),
                signal(True, clear=False, elapsed=1.0),
            ],
            ["no_second_started", "same_relation_restored"],
        ),
    ]
    bands = [
        {"id": "approach_enter", "from": "closing", "gap": 1.50, "to": "approach"},
        {
            "id": "approach_hold_inside_hysteresis",
            "from": "approach",
            "gap": 1.79,
            "to": "approach",
        },
        {"id": "approach_exit", "from": "approach", "gap": 1.80, "to": "closing"},
        {"id": "attack_enter", "from": "approach", "gap": 0.80, "to": "attack"},
        {"id": "attack_exit", "from": "attack", "gap": 1.10, "to": "approach"},
        {
            "id": "overlap_enter_requires_hold",
            "from": "attack",
            "gap": 0.35,
            "overlapHeld": 0.50,
            "to": "overlap",
        },
        {
            "id": "overlap_exit",
            "from": "overlap",
            "gap": 0.55,
            "overlapKnown": True,
            "to": "attack",
        },
        {
            "id": "skip_inward_bands",
            "from": "closing",
            "gap": 0.30,
            "overlapHeld": 0.50,
            "to": "overlap",
        },
    ]
    composite = [
        {
            "id": "distinct_relations_open",
            "sameHero": True,
            "distinctTargets": True,
            "heldSeconds": 1.0,
            "result": "started",
        },
        {
            "id": "same_target_rejected",
            "sameHero": True,
            "distinctTargets": False,
            "heldSeconds": 1.0,
            "result": "inactive",
        },
        {
            "id": "one_relation_unknown",
            "sameHero": True,
            "distinctTargets": True,
            "heldSeconds": 1.0,
            "relationKnown": False,
            "result": "inactive",
        },
        {
            "id": "relation_replacement_closes",
            "sameHero": True,
            "distinctTargets": True,
            "replacement": True,
            "result": "ended",
        },
        {
            "id": "temporary_loss_restored",
            "sameHero": True,
            "distinctTargets": True,
            "lossSeconds": 0.99,
            "result": "active",
        },
        {
            "id": "loss_at_boundary_closes",
            "sameHero": True,
            "distinctTargets": True,
            "lossSeconds": 1.0,
            "result": "ended",
        },
    ]
    determinism = {
        "identicalInputs": [
            "frameSequence",
            "featureValues",
            "quality",
            "parameterHash",
            "correlationKey",
        ],
        "authorityOrder": "frameSequence",
        "expected": "byte_identical_facts_events_and_transition_reasons",
    }
    return {
        "schemaVersion": "detector-catalog-goldens/2",
        "directionalTraces": traces,
        "bandBoundaries": bands,
        "compositeScenarios": composite,
        "determinism": determinism,
    }


def build_mutations() -> list[dict[str, str]]:
    return [
        {
            "id": "positive_closing_slope",
            "target": "battle_ahead_v1.max_closing_slope",
            "value": "0.04",
        },
        {
            "id": "reversed_ahead_actors",
            "target": "battle_ahead_v1.orderedActors",
            "value": "targetAhead,hero",
        },
        {
            "id": "reversed_behind_actors",
            "target": "battle_behind_v1.orderedActors",
            "value": "hero,challengerBehind",
        },
        {
            "id": "gap_hysteresis_inverted",
            "target": "battle_ahead_v1.exit_gap_min_s",
            "value": "2.0",
        },
        {
            "id": "band_hysteresis_inverted",
            "target": "battle_ahead_v1.attack_exit_s",
            "value": "0.7",
        },
        {"id": "sample_window_impossible", "target": "battle_ahead_v1.min_samples", "value": "60"},
        {
            "id": "unknown_enters",
            "target": "battle_ahead_v1.entry.unknownSatisfies",
            "value": "true",
        },
        {
            "id": "unregistered_feature",
            "target": "battle_ahead_v1.features[0]",
            "value": "gap.magic",
        },
        {
            "id": "unregistered_fact",
            "target": "battle_ahead_v1.output.factPredicate",
            "value": "battle.magic",
        },
        {
            "id": "same_two_front_epoch",
            "target": "battle_two_front_v1.correlationKey",
            "value": "one_relation_epoch",
        },
        {
            "id": "released_required_capture",
            "target": "battle_ahead_v1.experimental",
            "value": "false",
        },
        {
            "id": "invented_end_event",
            "target": "battle_ahead_v1.output.endedEvent",
            "value": "HUNTING_ENDED",
        },
    ]


def parameter_map(definition: dict[str, Any]) -> dict[str, Any]:
    return {row["id"]: row["default"] for row in definition["parameters"]}


def definition_errors(catalog: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    definitions = catalog["definitions"]
    if [row["id"] for row in definitions] != [
        "battle_ahead_v1",
        "battle_behind_v1",
        "battle_two_front_v1",
    ]:
        errors.append("detector IDs differ")
        return errors
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    features = {row["id"] for row in registry["features"]}
    facts = {row["id"] for row in registry["factPredicates"]}
    events = {row["id"] for row in registry["eventIdentifiers"]}
    channels = set(registry["tapeChannels"])
    for definition in definitions:
        values = parameter_map(definition)
        for parameter in definition["parameters"]:
            value = parameter["default"]
            if not isinstance(value, (int, float)) or not math.isfinite(value):
                errors.append("parameter is non-finite")
            if not parameter["minimum"] <= value <= parameter["maximum"]:
                errors.append("parameter outside range")
        if not set(definition["features"]) <= features:
            errors.append("unknown feature reference")
        output = definition["output"]
        if output.get("factPredicate") is not None and output["factPredicate"] not in facts:
            errors.append("unknown fact reference")
        if output["startEvent"] not in events or output["tapeChannel"] not in channels:
            errors.append("unknown event or tape channel")
        if output["endedEvent"] is not None:
            errors.append("invented ended event")
        if not definition["experimental"] and definition["tuningPolicy"] == "required":
            errors.append("released detector requires capture")
        if definition["entry"]["unknownSatisfies"]:
            errors.append("unknown satisfies entry")
        if definition["kind"] == "directional":
            if definition["id"] == "battle_ahead_v1" and definition["orderedActors"] != [
                "hero",
                "targetAhead",
            ]:
                errors.append("ahead actor direction differs")
            if definition["id"] == "battle_behind_v1" and definition["orderedActors"] != [
                "challengerBehind",
                "hero",
            ]:
                errors.append("behind actor direction differs")
            if not (
                values["sample_interval_s"] < values["bucket_s"] <= values["trend_window_s"]
                and values["min_samples"] * values["sample_interval_s"] <= values["trend_window_s"]
                and values["confirm_s"] <= values["trend_window_s"]
                and values["enter_gap_max_s"] < values["exit_gap_min_s"]
                and values["overlap_enter_s"]
                < values["overlap_exit_s"]
                <= values["attack_enter_s"]
                < values["attack_exit_s"]
                and values["attack_exit_s"]
                <= values["approach_enter_s"]
                < values["approach_exit_s"]
                <= values["enter_gap_max_s"]
                and values["update_min_interval_s"] >= values["clear_s"]
                and values["stale_after_s"] <= values["trend_window_s"]
            ):
                errors.append("directional cross-field invariant fails")
        elif definition["correlationKey"][-2:] != ["frontRelationEpoch", "rearRelationEpoch"]:
            errors.append("two-front correlation epochs differ")
    first = copy.deepcopy(definitions[0])
    second = copy.deepcopy(definitions[1])
    for row in (first, second):
        for key in ("id", "orderedActors"):
            row.pop(key)
        row["output"]["startEvent"] = "<directional>"
        row["output"]["internalKind"] = "<directional>"
        row["output"]["tapeChannel"] = "<directional>"
    if canonical(first) != canonical(second):
        errors.append("directional algorithms differ")
    return errors


def mutate(catalog: dict[str, Any], mutation_id: str) -> dict[str, Any]:
    result = copy.deepcopy(catalog)
    ahead, behind, composite = result["definitions"]
    params = {row["id"]: row for row in ahead["parameters"]}
    if mutation_id == "positive_closing_slope":
        params["max_closing_slope"]["default"] = 0.04
    elif mutation_id == "reversed_ahead_actors":
        ahead["orderedActors"] = ["targetAhead", "hero"]
    elif mutation_id == "reversed_behind_actors":
        behind["orderedActors"] = ["hero", "challengerBehind"]
    elif mutation_id == "gap_hysteresis_inverted":
        params["exit_gap_min_s"]["default"] = 2.0
    elif mutation_id == "band_hysteresis_inverted":
        params["attack_exit_s"]["default"] = 0.7
    elif mutation_id == "sample_window_impossible":
        params["min_samples"]["default"] = 60
    elif mutation_id == "unknown_enters":
        ahead["entry"]["unknownSatisfies"] = True
    elif mutation_id == "unregistered_feature":
        ahead["features"][0] = "gap.magic"
    elif mutation_id == "unregistered_fact":
        ahead["output"]["factPredicate"] = "battle.magic"
    elif mutation_id == "same_two_front_epoch":
        composite["correlationKey"] = [
            "streamEpoch",
            "occurrenceId",
            "relationEpoch",
            "relationEpoch",
        ]
    elif mutation_id == "released_required_capture":
        ahead["experimental"] = False
    elif mutation_id == "invented_end_event":
        ahead["output"]["endedEvent"] = "HUNTING_ENDED"
    else:
        raise ValueError(mutation_id)
    return result


def validate_goldens(goldens: dict[str, Any]) -> None:
    for fixture in goldens["directionalTraces"]:
        state = "inactive"
        for step in fixture["steps"]:
            expected = reduce_directional(state, step)
            if expected != (step["stateAfter"], step["emission"]):
                raise ValueError(f"directional trace {fixture['id']} differs")
            state = step["stateAfter"]
    if len(goldens["bandBoundaries"]) != 8 or len(goldens["compositeScenarios"]) != 6:
        raise ValueError("boundary/composite fixture count differs")


def validate_all(
    catalog: dict[str, Any],
    schema: dict[str, Any],
    goldens: dict[str, Any],
    mutations: list[dict[str, str]],
) -> None:
    expected = (build_catalog(), build_schema(), build_goldens(), build_mutations())
    if any(
        canonical(actual) != canonical(wanted)
        for actual, wanted in zip((catalog, schema, goldens, mutations), expected, strict=True)
    ):
        raise ValueError("detector catalog artifacts are stale")
    errors = definition_errors(catalog)
    if errors:
        raise ValueError(f"detector catalog rejected: {errors[0]}")
    validate_goldens(goldens)
    for mutation in mutations:
        if not definition_errors(mutate(catalog, mutation["id"])):
            raise ValueError(f"mutation {mutation['id']} unexpectedly accepted")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    artifacts = (build_catalog(), build_schema(), build_goldens(), build_mutations())
    paths = (CATALOG_PATH, SCHEMA_PATH, GOLDENS_PATH, MUTATIONS_PATH)
    if args.write:
        for path, value in zip(paths, artifacts, strict=True):
            path.write_text(
                json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
        print("wrote detector catalog, schema, goldens and mutations")
        return 0
    validate_all(*(json.loads(path.read_text(encoding="utf-8")) for path in paths))
    print(
        "Detector catalog OK: 3 definitions, 23 directional + 2 composite parameters, "
        "7 FSM traces + 14 boundary/composite fixtures, 12 rejected mutations"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
