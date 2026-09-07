#!/usr/bin/env python3
"""Build and validate the branch-only NarrativeRuntime actor transition model."""

from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path
from typing import Any

from build_dto_schemas import canonical, schema_errors

DTO_PATH = Path(__file__).with_name("dto-contracts.schema.json")
MODEL_PATH = Path(__file__).with_name("actor-transition-model.json")
SCHEMA_PATH = Path(__file__).with_name("actor-transition-model.schema.json")
GOLDENS_PATH = Path(__file__).with_name("actor-transition-goldens.json")
MUTATIONS_PATH = Path(__file__).with_name("actor-transition-mutations.json")

VERSION = "actor-transition-model/2"
LANES = ("idle", "building", "committed", "speaking", "stopping")
COMMANDS = (
    "APPLY_CONTEXT_BATCH",
    "CONFIG_UPDATE",
    "LONG_SILENCE_ELAPSED",
    "VALIDITY_DEADLINE_ELAPSED",
    "REALIZATION_SUCCEEDED",
    "REALIZATION_FAILED",
    "REALIZATION_DEADLINE_ELAPSED",
    "PLAYBACK_ACCEPTED",
    "SPEECH_COMPLETED",
    "SPEECH_INTERRUPTED",
    "SPEECH_FAILED",
    "SPEECH_DEADLINE_ELAPSED",
    "MANUAL_SPEAK_REQUEST",
    "TAPE_HEALTH_CHANGED",
    "COMPONENT_HEALTH_CHANGED",
    "MAILBOX_RECOVERY",
    "SHUTDOWN",
)
PROTECTED = {
    "CONFIG_UPDATE": "always",
    "REALIZATION_SUCCEEDED": "always",
    "REALIZATION_FAILED": "always",
    "REALIZATION_DEADLINE_ELAPSED": "always",
    "PLAYBACK_ACCEPTED": "always",
    "SPEECH_COMPLETED": "always",
    "SPEECH_INTERRUPTED": "always",
    "SPEECH_FAILED": "always",
    "SPEECH_DEADLINE_ELAPSED": "always",
    "COMPONENT_HEALTH_CHANGED": "status_unavailable",
    "MAILBOX_RECOVERY": "always",
    "SHUTDOWN": "always",
    "APPLY_CONTEXT_BATCH": "timeline_transition_or_protected_event",
    "TAPE_HEALTH_CHANGED": "required_capture_loss",
}
COALESCE = {
    "LONG_SILENCE_ELAPSED": ["kind", "token.generation"],
    "VALIDITY_DEADLINE_ELAPSED": ["kind", "token.generation"],
    "REALIZATION_DEADLINE_ELAPSED": [
        "kind",
        "token.requestId",
        "token.requestOrdinal",
        "token.dispatchGeneration",
    ],
    "TAPE_HEALTH_CHANGED": [
        "kind",
        "payload.recorderGeneration",
        "payload.status",
        "payload.affectedDetectorIds",
    ],
    "COMPONENT_HEALTH_CHANGED": [
        "kind",
        "payload.component",
        "payload.generation",
        "payload.status",
    ],
}
IGNORED_OUTSIDE = {
    "REALIZATION_SUCCEEDED": {"idle", "committed", "speaking", "stopping"},
    "REALIZATION_FAILED": {"idle", "committed", "speaking", "stopping"},
    "REALIZATION_DEADLINE_ELAPSED": {"idle", "committed", "speaking", "stopping"},
    "PLAYBACK_ACCEPTED": {"idle", "building", "stopping"},
    "SPEECH_COMPLETED": {"idle", "building"},
    "SPEECH_INTERRUPTED": {"idle", "building"},
    "SPEECH_FAILED": {"idle", "building"},
    "SPEECH_DEADLINE_ELAPSED": {"idle", "building"},
}


def enum(*values: str) -> dict[str, Any]:
    return {"type": "string", "enum": list(values)}


def array(items: dict[str, Any], minimum: int = 0, maximum: int | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"type": "array", "items": items, "minItems": minimum}
    if maximum is not None:
        result["maxItems"] = maximum
    return result


def closed(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or list(properties),
        "additionalProperties": False,
    }


def possible_next(lane: str, command: str) -> list[str]:
    table: dict[str, dict[str, list[str]]] = {
        "APPLY_CONTEXT_BATCH": {
            "idle": ["idle", "building"],
            "building": ["idle", "building"],
            "committed": ["committed", "stopping"],
            "speaking": ["speaking", "stopping"],
            "stopping": ["stopping"],
        },
        "LONG_SILENCE_ELAPSED": {
            "idle": ["idle", "building"],
            "building": ["building"],
            "committed": ["committed"],
            "speaking": ["speaking"],
            "stopping": ["stopping"],
        },
        "VALIDITY_DEADLINE_ELAPSED": {
            "idle": ["idle"],
            "building": ["idle"],
            "committed": ["committed", "stopping"],
            "speaking": ["speaking"],
            "stopping": ["stopping"],
        },
        "REALIZATION_SUCCEEDED": {
            "idle": ["idle"],
            "building": ["idle", "building", "committed"],
            "committed": ["committed"],
            "speaking": ["speaking"],
            "stopping": ["stopping"],
        },
        "REALIZATION_FAILED": {
            "idle": ["idle"],
            "building": ["idle", "building"],
            "committed": ["committed"],
            "speaking": ["speaking"],
            "stopping": ["stopping"],
        },
        "REALIZATION_DEADLINE_ELAPSED": {
            "idle": ["idle"],
            "building": ["idle", "building"],
            "committed": ["committed"],
            "speaking": ["speaking"],
            "stopping": ["stopping"],
        },
        "PLAYBACK_ACCEPTED": {
            "idle": ["idle"],
            "building": ["building"],
            "committed": ["speaking"],
            "speaking": ["stopping"],
            "stopping": ["stopping"],
        },
        "SPEECH_COMPLETED": {
            "idle": ["idle"],
            "building": ["building"],
            "committed": ["stopping"],
            "speaking": ["idle", "building"],
            "stopping": ["idle"],
        },
        "SPEECH_INTERRUPTED": {
            "idle": ["idle"],
            "building": ["building"],
            "committed": ["stopping"],
            "speaking": ["idle", "building"],
            "stopping": ["idle"],
        },
        "SPEECH_FAILED": {
            "idle": ["idle"],
            "building": ["building"],
            "committed": ["idle", "building"],
            "speaking": ["idle", "building"],
            "stopping": ["idle"],
        },
        "SPEECH_DEADLINE_ELAPSED": {
            "idle": ["idle"],
            "building": ["building"],
            "committed": ["stopping"],
            "speaking": ["stopping"],
            "stopping": ["idle", "stopping"],
        },
        "MANUAL_SPEAK_REQUEST": {
            "idle": ["idle", "committed"],
            "building": ["building"],
            "committed": ["committed"],
            "speaking": ["speaking"],
            "stopping": ["stopping"],
        },
        "MAILBOX_RECOVERY": {
            "idle": ["idle"],
            "building": ["idle"],
            "committed": ["stopping"],
            "speaking": ["speaking", "stopping"],
            "stopping": ["stopping"],
        },
        "SHUTDOWN": {
            "idle": ["idle"],
            "building": ["idle"],
            "committed": ["stopping"],
            "speaking": ["stopping"],
            "stopping": ["stopping"],
        },
    }
    return table.get(command, {}).get(lane, [lane])


def disposition(lane: str, command: str) -> str:
    if command == "MANUAL_SPEAK_REQUEST" and lane != "idle":
        return "rejected_busy"
    if lane in IGNORED_OUTSIDE.get(command, set()):
        return "ignored_stale_or_inapplicable"
    return "handled"


def build_model() -> dict[str, Any]:
    inventory = []
    for kind in COMMANDS:
        inventory.append(
            {
                "kind": kind,
                "protectedWhen": PROTECTED.get(kind, "never"),
                "coalesceKey": COALESCE.get(kind),
                "atomicBundle": (
                    "config_then_context"
                    if kind == "CONFIG_UPDATE"
                    else "capture_health_then_context"
                    if kind == "TAPE_HEALTH_CHANGED"
                    else None
                ),
            }
        )
    matrix = [
        {
            "lane": lane,
            "command": command,
            "disposition": disposition(lane, command),
            "possibleNextLanes": possible_next(lane, command),
        }
        for lane in LANES
        for command in COMMANDS
    ]
    return {
        "schemaVersion": VERSION,
        "sourceBaseline": "master@0ce75d4",
        "runtimeStates": ["disabled", "starting", "ready", "degraded", "stopping", "stopped"],
        "laneStates": list(LANES),
        "mailbox": {
            "totalCapacity": 64,
            "ordinaryCells": 56,
            "protectedCells": 7,
            "emergencyCells": 1,
            "dequeueOrder": "mailbox_sequence_ascending",
            "reducerOrder": "assign_reducer_sequence_at_dequeue",
            "priorityReorders": False,
            "recoveryKeepsOriginalPosition": True,
            "shutdownOwnsEmergencyCell": True,
        },
        "commands": inventory,
        "transitionMatrix": matrix,
        "invariants": [
            "single_actor_writer",
            "one_mailbox_total_order",
            "at_most_one_realizer",
            "at_most_one_utterance",
            "no_prepared_text_queue",
            "pure_fact_batch_never_plans",
            "callback_token_idempotence",
            "recovery_never_recreates_lost_events",
            "manual_admission_linearized",
            "quarantined_generation_cannot_admit",
            "shutdown_fail_soft",
        ],
        "planningCycle": {
            "maximumDistinctPlansPerImpulse": 2,
            "replacementStartsNewCycle": True,
            "pureFactBatchStartsCycle": False,
            "manualTerminalStartsCycle": False,
        },
    }


def build_schema() -> dict[str, Any]:
    command = closed(
        {
            "kind": enum(*COMMANDS),
            "protectedWhen": enum(
                "never",
                "always",
                "status_unavailable",
                "timeline_transition_or_protected_event",
                "required_capture_loss",
            ),
            "coalesceKey": {
                "oneOf": [
                    {"type": "null"},
                    array({"type": "string", "minLength": 1}, 2, 5),
                ]
            },
            "atomicBundle": {
                "type": ["string", "null"],
                "enum": [None, "config_then_context", "capture_health_then_context"],
            },
        }
    )
    matrix = closed(
        {
            "lane": enum(*LANES),
            "command": enum(*COMMANDS),
            "disposition": enum("handled", "ignored_stale_or_inapplicable", "rejected_busy"),
            "possibleNextLanes": array(enum(*LANES), 1, len(LANES)),
        }
    )
    schema = closed(
        {
            "schemaVersion": {"const": VERSION},
            "sourceBaseline": {"const": "master@0ce75d4"},
            "runtimeStates": array({"type": "string"}, 6, 6),
            "laneStates": array(enum(*LANES), 5, 5),
            "mailbox": closed(
                {
                    "totalCapacity": {"const": 64},
                    "ordinaryCells": {"const": 56},
                    "protectedCells": {"const": 7},
                    "emergencyCells": {"const": 1},
                    "dequeueOrder": {"const": "mailbox_sequence_ascending"},
                    "reducerOrder": {"const": "assign_reducer_sequence_at_dequeue"},
                    "priorityReorders": {"const": False},
                    "recoveryKeepsOriginalPosition": {"const": True},
                    "shutdownOwnsEmergencyCell": {"const": True},
                }
            ),
            "commands": array(command, len(COMMANDS), len(COMMANDS)),
            "transitionMatrix": array(
                matrix, len(LANES) * len(COMMANDS), len(LANES) * len(COMMANDS)
            ),
            "invariants": array({"type": "string"}, 11, 11),
            "planningCycle": closed(
                {
                    "maximumDistinctPlansPerImpulse": {"const": 2},
                    "replacementStartsNewCycle": {"const": True},
                    "pureFactBatchStartsCycle": {"const": False},
                    "manualTerminalStartsCycle": {"const": False},
                }
            ),
        }
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://irswitch.local/contracts/actor-transition-model-v2.schema.json",
        **schema,
        "x-irswitch-invariants": [
            "command_inventory_matches_narrative_command_union",
            "lane_command_product_is_exactly_total",
            "possible_next_lanes_match_frozen_table",
            "coalescing_allowlist_is_exact",
            "mailbox_partitions_sum_to_total",
        ],
    }


def trace(
    trace_id: str,
    initial: str,
    steps: list[tuple[str, str, str]],
    assertions: list[str],
) -> dict[str, Any]:
    lane = initial
    rows = []
    for command, outcome, next_lane in steps:
        rows.append(
            {
                "command": command,
                "outcome": outcome,
                "laneBefore": lane,
                "laneAfter": next_lane,
            }
        )
        lane = next_lane
    return {
        "id": trace_id,
        "initialLane": initial,
        "steps": rows,
        "finalLane": lane,
        "assertions": assertions,
    }


def build_goldens() -> dict[str, Any]:
    traces = [
        trace(
            "result_before_deadline",
            "building",
            [
                ("REALIZATION_SUCCEEDED", "matching_verified_fresh", "committed"),
                ("REALIZATION_DEADLINE_ELAPSED", "stale_token_noop", "committed"),
            ],
            ["one_utterance", "deadline_cannot_strand_building"],
        ),
        trace(
            "deadline_before_result",
            "building",
            [
                ("REALIZATION_DEADLINE_ELAPSED", "matching_attempt_two_selected", "building"),
                ("REALIZATION_SUCCEEDED", "stale_token_noop", "building"),
            ],
            ["one_realizer", "late_result_cannot_commit"],
        ),
        trace(
            "reset_before_result",
            "building",
            [
                ("APPLY_CONTEXT_BATCH", "occurrence_reset", "idle"),
                ("REALIZATION_SUCCEEDED", "stale_token_noop", "idle"),
            ],
            ["reservation_released", "old_occurrence_cannot_speak"],
        ),
        trace(
            "duplicate_acceptance_quarantines",
            "committed",
            [
                ("PLAYBACK_ACCEPTED", "matching", "speaking"),
                ("PLAYBACK_ACCEPTED", "duplicate_protocol_violation", "stopping"),
                ("SPEECH_INTERRUPTED", "matching_cleanup", "idle"),
            ],
            ["exposure_consumed_once", "generation_quarantined"],
        ),
        trace(
            "completion_then_duplicate",
            "speaking",
            [
                ("SPEECH_COMPLETED", "matching_natural", "idle"),
                ("SPEECH_COMPLETED", "duplicate_stale_noop", "idle"),
            ],
            ["terminalized_once", "director_pass_once"],
        ),
        trace(
            "committed_terminal_protocol_violation",
            "committed",
            [
                ("SPEECH_COMPLETED", "terminal_before_acceptance", "stopping"),
                ("SPEECH_DEADLINE_ELAPSED", "stop_timeout", "idle"),
            ],
            ["opportunity_unconsumed", "generation_quarantined"],
        ),
        trace(
            "manual_claim_wins",
            "idle",
            [("MANUAL_SPEAK_REQUEST", "actor_claimed_and_dispatched", "committed")],
            ["http_202", "no_episode_or_exposure"],
        ),
        trace(
            "manual_abandon_wins",
            "idle",
            [("MANUAL_SPEAK_REQUEST", "caller_abandoned_stale_noop", "idle")],
            ["http_503_admission_timeout", "no_audio_later"],
        ),
        trace(
            "manual_busy",
            "speaking",
            [("MANUAL_SPEAK_REQUEST", "rejected_speech_busy", "speaking")],
            ["http_409", "current_playback_unchanged"],
        ),
        trace(
            "validity_exact_upper_bound",
            "building",
            [("VALIDITY_DEADLINE_ELAPSED", "expires_at_equal_deadline", "idle")],
            ["half_open_validity", "no_director_impulse"],
        ),
        trace(
            "playback_watchdog",
            "speaking",
            [
                ("SPEECH_DEADLINE_ELAPSED", "playback_timeout", "stopping"),
                ("SPEECH_DEADLINE_ELAPSED", "stop_timeout", "idle"),
                ("SPEECH_COMPLETED", "late_stale_noop", "idle"),
            ],
            ["exposure_retained", "component_unavailable", "late_callback_noop"],
        ),
        trace(
            "shutdown_during_playback",
            "speaking",
            [
                ("SHUTDOWN", "ingress_closed_cancel_requested", "stopping"),
                ("SPEECH_INTERRUPTED", "matching_shutdown_terminal", "idle"),
            ],
            ["never_replan", "bounded_tape_flush", "fail_soft"],
        ),
        trace(
            "recovery_cancels_building",
            "building",
            [
                ("MAILBOX_RECOVERY", "jump_latest_history_incomplete", "idle"),
                ("REALIZATION_SUCCEEDED", "stale_token_noop", "idle"),
            ],
            ["lost_events_not_recreated", "old_revision_stale"],
        ),
    ]
    overflow = [
        {
            "id": "coalesce_same_silence_generation",
            "operation": "coalesce",
            "incoming": "LONG_SILENCE_ELAPSED",
            "expected": "existing_position_refreshed",
        },
        {
            "id": "different_generation_does_not_coalesce",
            "operation": "ordinary_admit",
            "incoming": "VALIDITY_DEADLINE_ELAPSED",
            "expected": "distinct_item_or_deadline_admission_skipped",
        },
        {
            "id": "manual_full_partition",
            "operation": "ordinary_full",
            "incoming": "MANUAL_SPEAK_REQUEST",
            "expected": "reject_mailbox_overloaded",
        },
        {
            "id": "ordinary_context_evicts_oldest_silence",
            "operation": "ordinary_full",
            "incoming": "APPLY_CONTEXT_BATCH",
            "expected": "evict_oldest_ordinary_silence",
        },
        {
            "id": "ordinary_context_loss_creates_recovery",
            "operation": "ordinary_full_no_silence",
            "incoming": "APPLY_CONTEXT_BATCH",
            "expected": "evict_oldest_context_and_place_recovery",
        },
        {
            "id": "protected_saturation_collapses",
            "operation": "protected_full",
            "incoming": "REALIZATION_SUCCEEDED",
            "expected": "refresh_recovery_with_safety_effect",
        },
        {
            "id": "config_pair_all_or_recovery",
            "operation": "protected_atomic_pair",
            "incoming": "CONFIG_UPDATE+APPLY_CONTEXT_BATCH",
            "expected": "two_consecutive_sequences_or_one_recovery",
        },
        {
            "id": "capture_pair_all_or_recovery",
            "operation": "protected_atomic_pair",
            "incoming": "TAPE_HEALTH_CHANGED+APPLY_CONTEXT_BATCH",
            "expected": "two_consecutive_sequences_or_one_recovery",
        },
        {
            "id": "recovery_refresh_keeps_order",
            "operation": "refresh_recovery",
            "incoming": "newer_projection_and_loss",
            "expected": "same_mailbox_sequence_expanded_range_latest_projection",
        },
        {
            "id": "shutdown_takes_emergency",
            "operation": "shutdown",
            "incoming": "SHUTDOWN",
            "expected": "ingress_closed_recovery_metadata_attached",
        },
    ]
    ordering = [
        {
            "id": "same_time_external_before_callback",
            "admissions": [
                {"mailboxSequence": 41, "kind": "APPLY_CONTEXT_BATCH"},
                {"mailboxSequence": 42, "kind": "REALIZATION_SUCCEEDED"},
            ],
            "expectedReducerOrder": [41, 42],
        },
        {
            "id": "same_time_callback_before_reset",
            "admissions": [
                {"mailboxSequence": 51, "kind": "REALIZATION_SUCCEEDED"},
                {"mailboxSequence": 52, "kind": "APPLY_CONTEXT_BATCH"},
            ],
            "expectedReducerOrder": [51, 52],
        },
    ]
    return {
        "schemaVersion": "actor-transition-goldens/2",
        "pairCoverage": [
            {"lane": lane, "command": command} for lane in LANES for command in COMMANDS
        ],
        "raceTraces": traces,
        "overflowScenarios": overflow,
        "orderingScenarios": ordering,
    }


def build_mutations() -> list[dict[str, str]]:
    return [
        {
            "id": "capacity_65",
            "path": "mailbox.totalCapacity",
            "operation": "replace",
            "value": "65",
        },
        {
            "id": "ordinary_55",
            "path": "mailbox.ordinaryCells",
            "operation": "replace",
            "value": "55",
        },
        {
            "id": "priority_reorders",
            "path": "mailbox.priorityReorders",
            "operation": "replace",
            "value": "true",
        },
        {
            "id": "missing_lane_pair",
            "path": "transitionMatrix[0]",
            "operation": "remove",
            "value": "",
        },
        {
            "id": "duplicate_lane_pair",
            "path": "transitionMatrix[1]",
            "operation": "duplicate_previous",
            "value": "",
        },
        {
            "id": "context_coalesces",
            "path": "commands.APPLY_CONTEXT_BATCH.coalesceKey",
            "operation": "replace",
            "value": "kind",
        },
        {
            "id": "manual_protected",
            "path": "commands.MANUAL_SPEAK_REQUEST.protectedWhen",
            "operation": "replace",
            "value": "always",
        },
        {
            "id": "three_plan_cycle",
            "path": "planningCycle.maximumDistinctPlansPerImpulse",
            "operation": "replace",
            "value": "3",
        },
        {"id": "removed_command", "path": "commands.SHUTDOWN", "operation": "remove", "value": ""},
        {
            "id": "unknown_command",
            "path": "commands[0].kind",
            "operation": "replace",
            "value": "SESSION_REWOUND",
        },
    ]


def model_errors(model: dict[str, Any], dto: dict[str, Any]) -> list[str]:
    errors = schema_errors(model, build_schema(), build_schema())
    if errors:
        return errors
    dto_kinds = [
        branch["properties"]["kind"]["const"]
        for branch in dto["$defs"]["NarrativeCommand"]["oneOf"]
    ]
    kinds = [row["kind"] for row in model["commands"]]
    if kinds != list(COMMANDS) or kinds != dto_kinds:
        errors.append("command inventory differs from NarrativeCommand union")
    pairs = [(row["lane"], row["command"]) for row in model["transitionMatrix"]]
    expected_pairs = [(lane, command) for lane in LANES for command in COMMANDS]
    if pairs != expected_pairs:
        errors.append("lane-command product is not exact and ordered")
    for row in model["transitionMatrix"]:
        if row["possibleNextLanes"] != possible_next(row["lane"], row["command"]):
            errors.append("possible next lanes differ")
            break
        if row["disposition"] != disposition(row["lane"], row["command"]):
            errors.append("disposition differs")
            break
    if (
        sum(
            model["mailbox"][name] for name in ("ordinaryCells", "protectedCells", "emergencyCells")
        )
        != model["mailbox"]["totalCapacity"]
    ):
        errors.append("mailbox partitions do not sum")
    actual_coalesce = {
        row["kind"]: row["coalesceKey"]
        for row in model["commands"]
        if row["coalesceKey"] is not None
    }
    if actual_coalesce != COALESCE:
        errors.append("coalescing allowlist differs")
    actual_protected = {
        row["kind"]: row["protectedWhen"]
        for row in model["commands"]
        if row["protectedWhen"] != "never"
    }
    if actual_protected != PROTECTED:
        errors.append("protected admission matrix differs")
    return errors


def validate_goldens(model: dict[str, Any], goldens: dict[str, Any]) -> None:
    coverage = {(row["lane"], row["command"]) for row in goldens["pairCoverage"]}
    if coverage != {(lane, command) for lane in LANES for command in COMMANDS}:
        raise ValueError("pair coverage is incomplete")
    matrix = {(row["lane"], row["command"]): row for row in model["transitionMatrix"]}
    for fixture in goldens["raceTraces"]:
        lane = fixture["initialLane"]
        for step in fixture["steps"]:
            if step["laneBefore"] != lane:
                raise ValueError(f"trace {fixture['id']} has discontinuous lane")
            if step["laneAfter"] not in matrix[(lane, step["command"])]["possibleNextLanes"]:
                raise ValueError(f"trace {fixture['id']} uses forbidden transition")
            lane = step["laneAfter"]
        if lane != fixture["finalLane"]:
            raise ValueError(f"trace {fixture['id']} final lane differs")
    for fixture in goldens["orderingScenarios"]:
        sequences = [row["mailboxSequence"] for row in fixture["admissions"]]
        if sorted(sequences) != fixture["expectedReducerOrder"]:
            raise ValueError(f"ordering fixture {fixture['id']} differs")
    expected_overflow = {
        "coalesce_same_silence_generation",
        "different_generation_does_not_coalesce",
        "manual_full_partition",
        "ordinary_context_evicts_oldest_silence",
        "ordinary_context_loss_creates_recovery",
        "protected_saturation_collapses",
        "config_pair_all_or_recovery",
        "capture_pair_all_or_recovery",
        "recovery_refresh_keeps_order",
        "shutdown_takes_emergency",
    }
    if {row["id"] for row in goldens["overflowScenarios"]} != expected_overflow:
        raise ValueError("overflow scenario coverage differs")


def mutate(model: dict[str, Any], mutation: dict[str, str]) -> dict[str, Any]:
    result = copy.deepcopy(model)
    mutation_id = mutation["id"]
    if mutation_id == "capacity_65":
        result["mailbox"]["totalCapacity"] = 65
    elif mutation_id == "ordinary_55":
        result["mailbox"]["ordinaryCells"] = 55
    elif mutation_id == "priority_reorders":
        result["mailbox"]["priorityReorders"] = True
    elif mutation_id == "missing_lane_pair":
        result["transitionMatrix"].pop(0)
    elif mutation_id == "duplicate_lane_pair":
        result["transitionMatrix"][1] = copy.deepcopy(result["transitionMatrix"][0])
    elif mutation_id == "context_coalesces":
        result["commands"][0]["coalesceKey"] = ["kind"]
    elif mutation_id == "manual_protected":
        result["commands"][12]["protectedWhen"] = "always"
    elif mutation_id == "three_plan_cycle":
        result["planningCycle"]["maximumDistinctPlansPerImpulse"] = 3
    elif mutation_id == "removed_command":
        result["commands"].pop()
    elif mutation_id == "unknown_command":
        result["commands"][0]["kind"] = "SESSION_REWOUND"
    else:
        raise ValueError(f"unknown mutation {mutation_id}")
    return result


def validate_all(
    model: dict[str, Any],
    schema: dict[str, Any],
    goldens: dict[str, Any],
    mutations: list[dict[str, str]],
) -> None:
    expected = (build_model(), build_schema(), build_goldens(), build_mutations())
    if any(
        canonical(actual) != canonical(wanted)
        for actual, wanted in zip((model, schema, goldens, mutations), expected, strict=True)
    ):
        raise ValueError("actor model artifacts are stale")
    dto = json.loads(DTO_PATH.read_text(encoding="utf-8"))
    errors = model_errors(model, dto)
    if errors:
        raise ValueError(f"actor model rejected: {errors[0]}")
    validate_goldens(model, goldens)
    for mutation in mutations:
        if not model_errors(mutate(model, mutation), dto):
            raise ValueError(f"mutation {mutation['id']} unexpectedly accepted")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    artifacts = (build_model(), build_schema(), build_goldens(), build_mutations())
    paths = (MODEL_PATH, SCHEMA_PATH, GOLDENS_PATH, MUTATIONS_PATH)
    if args.write:
        for path, value in zip(paths, artifacts, strict=True):
            path.write_text(
                json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
        print("wrote actor transition model, schema, goldens and mutations")
        return 0
    loaded = tuple(json.loads(path.read_text(encoding="utf-8")) for path in paths)
    validate_all(*loaded)
    print(
        "Actor transition model OK: "
        f"{len(LANES)} lanes × {len(COMMANDS)} commands = "
        f"{len(LANES) * len(COMMANDS)} pairs, "
        f"{len(artifacts[2]['raceTraces'])} race traces, "
        f"{len(artifacts[2]['overflowScenarios'])} overflow scenarios, "
        f"{len(artifacts[3])} rejected mutations"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
