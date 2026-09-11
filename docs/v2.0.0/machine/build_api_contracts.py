#!/usr/bin/env python3
"""Build and validate frozen commentary-runtime/2 HTTP API schemas and goldens."""

from __future__ import annotations

import argparse
import copy
import ipaddress
import json
import math
import unicodedata
from pathlib import Path
from typing import Any

from build_dto_schemas import canonical, schema_errors

ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = Path(__file__).with_name("freeze-registry.json")
DTO_SCHEMA_PATH = Path(__file__).with_name("dto-contracts.schema.json")
BEAT_CATALOG_PATH = Path(__file__).with_name("beat-catalog.json")
CONTRACT_PATH = Path(__file__).with_name("api-contract.json")
SCHEMA_PATH = Path(__file__).with_name("api-contracts.schema.json")
GOLDENS_PATH = Path(__file__).with_name("api-goldens.json")

VERSION = "commentary-runtime/2"
HASH_PATTERN = r"^sha256:[0-9a-f]{64}$"
ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
LINEAGE_PATTERN = (
    r"^[1-9][0-9]*:(practice|qualifying|race):(0|[1-9][0-9]*)"
    r"(>[1-9][0-9]*:(practice|qualifying|race):(0|[1-9][0-9]*))*$"
)
ERROR_STATUS = {
    "invalid_json": 400,
    "invalid_request": 400,
    "forbidden": 403,
    "not_found": 404,
    "speech_busy": 409,
    "validation_failed": 422,
    "component_unavailable": 503,
    "mailbox_overloaded": 503,
    "admission_timeout": 503,
}


def closed(
    properties: dict[str, Any], required: list[str] | None = None, **extra: Any
) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required or list(properties),
        **extra,
    }


def enum(*values: Any) -> dict[str, Any]:
    return {"enum": list(values)}


def nullable(schema: dict[str, Any]) -> dict[str, Any]:
    return {"oneOf": [schema, {"type": "null"}]}


def array(item: dict[str, Any], minimum: int, maximum: int, unique: bool = False) -> dict[str, Any]:
    result: dict[str, Any] = {
        "type": "array",
        "items": item,
        "minItems": minimum,
        "maxItems": maximum,
    }
    if unique:
        result["uniqueItems"] = True
    return result


def build_schema() -> dict[str, Any]:
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    dto_schema = json.loads(DTO_SCHEMA_PATH.read_text(encoding="utf-8"))
    relation_ids = [row["id"] for row in registry["relationRegistry"]]
    all_reason_ids = sorted(
        {reason for domain in registry["reasonRegistry"] for reason in domain["ids"]}
    )
    # /health commentary.reason + runtime status.reason must cover both
    # config/runtime health and actor mailbox/tape recovery codes (#284).
    health_reasons = sorted(
        {
            reason
            for row in registry["reasonRegistry"]
            if row["domain"] in {"config/runtime health", "mailbox/tape health"}
            for reason in row["ids"]
        }
    )
    director_reasons = sorted(
        {
            reason
            for row in registry["reasonRegistry"]
            if row["domain"] in {"director selection", "director silence/reject"}
            for reason in row["ids"]
        }
    )
    verifier_reasons = next(
        row["ids"] for row in registry["reasonRegistry"] if row["domain"] == "verifier rejection"
    )
    id_value = {"type": "string", "pattern": ID_PATTERN}
    lineage = {"type": "string", "pattern": LINEAGE_PATTERN, "maxLength": 512}
    n0 = {"type": "integer", "minimum": 0}
    positive = {"type": "integer", "minimum": 1}
    finite = {"type": "number"}
    reason = nullable(enum(*all_reason_ids))
    session_ref = closed({"subSessionId": id_value, "sessionNum": n0})
    session_plan = closed(
        {
            "revision": n0,
            "valid": {"type": "boolean"},
            "reason": nullable(enum("session_plan_conflict")),
            "stages": array(enum("practice", "qualifying", "race"), 0, 3, True),
        },
        **{"x-irswitch-invariants": ["session_plan_validity_shape_and_canonical_stage_order"]},
    )
    timeline = closed(
        {
            "broadcastEpoch": n0,
            "streamEpoch": n0,
            "narrativeRunActive": {"type": "boolean"},
            "streamActive": {"type": ["boolean", "null"]},
            "streamState": enum("inactive", "active", "unknown"),
            "sessionPlan": nullable(session_plan),
            "sessionRef": nullable(session_ref),
            "occurrenceId": nullable(id_value),
            "lineageId": nullable(lineage),
            "stage": nullable(enum("practice", "qualifying", "race")),
            "historyComplete": {"type": "boolean"},
        },
        **{
            "x-irswitch-invariants": [
                "stream_state_active_projection",
                "session_identity_all_or_none",
            ]
        },
    )
    last_terminal = closed(
        {
            "utteranceId": id_value,
            "sourceKind": enum("narrative", "manual"),
            "reason": enum(
                *next(
                    row["ids"]
                    for row in registry["reasonRegistry"]
                    if row["domain"] == "speech terminal"
                )
            ),
            "atMonoMs": n0,
        }
    )
    speech = closed(
        {
            "state": enum(*registry["stateRegistry"]["speechLane"]),
            "sourceKind": nullable(enum("narrative", "manual")),
            "utteranceId": nullable(id_value),
            "beatId": nullable(id_value),
            "opportunityId": nullable(id_value),
            "backend": nullable(enum("sapi", "espeak", "supertonic")),
            "backendGeneration": nullable(n0),
            "dispatchedAtMonoMs": nullable(n0),
            "acceptedAtMonoMs": nullable(n0),
            "lastTerminal": nullable(last_terminal),
        },
        **{
            "x-irswitch-invariants": [
                "speech_idle_fields_null",
                "speech_source_identity_shape",
                "accepted_gte_dispatched",
            ]
        },
    )
    queue = closed({"depth": n0, "capacity": positive, "overflows": n0})
    opportunity_queue = closed({"depth": n0, "capacity": positive, "expired": n0, "evicted": n0})
    pending_change = closed(
        {
            "key": {"type": "string", "minLength": 1, "maxLength": 256},
            "boundary": enum(
                "command",
                "next_stream",
                "next_plan_or_manual",
                "next_beat_plan",
                "next_director_pass",
                "next_silence_deadline",
                "next_request",
                "next_utterance",
                "next_cancellation",
                "next_record",
                "next_rotated_file",
                "next_rotation",
                "next_writer_deadline",
                "next_shutdown",
            ),
            "desiredGeneration": n0,
        }
    )
    attempt = closed(
        {
            "requestId": id_value,
            "outcome": enum("succeeded", "failed", "cancelled", "timed_out", "stale"),
            "ttfbMs": nullable(n0),
            "ttftMs": nullable(n0),
            "totalMs": nullable(n0),
            "reducerLagMs": nullable(n0),
            "terminalReason": reason,
        },
        **{"x-irswitch-invariants": ["llm_latency_milestone_order"]},
    )
    component_status = enum("disabled", "starting", "ready", "degraded", "unavailable")
    disabled_detector = closed({"id": id_value, "reason": enum(*all_reason_ids)})
    counter = closed(
        dict.fromkeys(("kick", "accepted", "queued", "selected", "started", "expired"), n0)
    )
    defs: dict[str, Any] = {
        "AtomicFact": copy.deepcopy(dto_schema["$defs"]["AtomicFact"]),
        "ErrorResponse": closed(
            {
                "schemaVersion": {"const": VERSION},
                "error": closed(
                    {
                        "code": enum(*ERROR_STATUS),
                        "message": {"type": "string", "minLength": 1, "maxLength": 256},
                        "fields": {
                            "type": "object",
                            "maxProperties": 32,
                            "additionalProperties": {"type": "string", "maxLength": 128},
                        },
                    }
                ),
            }
        ),
        "StatusResponse": closed(
            {
                "schemaVersion": {"const": VERSION},
                "status": enum(*registry["stateRegistry"]["narrativeRuntime"]),
                "reason": nullable(enum(*health_reasons)),
                "language": {"const": "en"},
                "timeline": timeline,
                "speech": speech,
                "queues": closed({"mailbox": queue, "opportunities": opportunity_queue}),
                "episodes": closed(
                    {
                        "active": n0,
                        "candidate": n0,
                        "suspended": n0,
                        "retainedCurrentCapacity": positive,
                        "resolved": n0,
                        "resolvedCapacity": positive,
                    }
                ),
                "catalog": closed(
                    {
                        "schemaVersion": {"const": "narrative-catalog/2"},
                        "hash": {"type": "string", "pattern": HASH_PATTERN},
                        "eventIdentifierCount": {"const": 60},
                        "beatCount": {"const": 64},
                    }
                ),
                "config": closed(
                    {
                        "schemaVersion": {"const": "commentary-config/2"},
                        "desiredGeneration": n0,
                        "desiredHash": {"type": "string", "pattern": HASH_PATTERN},
                        "effectiveHash": {"type": "string", "pattern": HASH_PATTERN},
                        "applySequence": n0,
                        "pendingChanges": array(pending_change, 0, 128),
                    }
                ),
                "components": closed(
                    {
                        "llm": closed(
                            {
                                "status": component_status,
                                "reason": reason,
                                "generation": n0,
                                "configGeneration": n0,
                                "model": {"type": "string", "minLength": 1, "maxLength": 128},
                                "residencyEvidence": enum("warmup_succeeded", "not_requested"),
                                "lastAttempt": nullable(attempt),
                            }
                        ),
                        "tts": closed(
                            {
                                "status": component_status,
                                "reason": reason,
                                "backend": nullable(enum("sapi", "espeak", "supertonic")),
                                "backendGeneration": n0,
                                "configGeneration": n0,
                                "quarantinedGeneration": nullable(n0),
                                "voice": nullable({"type": "string", "maxLength": 128}),
                            }
                        ),
                        "tape": closed(
                            {
                                "status": component_status,
                                "reason": reason,
                                "path": nullable({"type": "string", "maxLength": 512}),
                                "size": n0,
                                "drops": n0,
                                "dropsByPriority": closed(
                                    {"sample": n0, "normal": n0, "critical": n0}
                                ),
                                "purposeCounts": array(
                                    closed(
                                        {
                                            "purposeChannel": enum(
                                                "flow", "llm_eval", "detector_tuning"
                                            ),
                                            "count": n0,
                                        }
                                    ),
                                    0,
                                    3,
                                ),
                            }
                        ),
                        "detectors": closed(
                            {
                                "status": component_status,
                                "reason": reason,
                                "disabled": array(disabled_detector, 0, 128),
                            }
                        ),
                        "facts": closed(
                            {
                                "status": component_status,
                                "reason": nullable(enum(*health_reasons)),
                                "viewRevision": n0,
                                "active": n0,
                                "historicalSummaries": n0,
                                "historyComplete": {"type": "boolean"},
                            }
                        ),
                    }
                ),
                "byTapeChannel": {
                    "type": "object",
                    "maxProperties": 128,
                    "propertyNames": enum(*registry["tapeChannels"]),
                    "additionalProperties": counter,
                },
            },
            **{
                "x-irswitch-invariants": [
                    "status_reason_matches_state",
                    "pending_changes_sorted_unique",
                    "episode_counts_within_capacities",
                    "component_generations_coherent",
                    "tts_quarantine_unavailable",
                    "tape_drops_equal_priority_sum",
                    "detectors_disabled_sorted_unique",
                    "channel_counters_nonzero_and_sorted_known",
                ]
            },
        ),
    }
    runner_up = closed({"beatId": id_value, "score": finite})
    candidate_order = closed({"reducerSequence": n0, "sourceOrdinal": n0})
    decision = closed(
        {
            "reducerSequence": n0,
            "atMonoMs": n0,
            "decision": enum(
                "selected", "silence", "discarded", "replaced", "expired", "invalidated"
            ),
            "reason": enum(*director_reasons),
            "beatId": nullable(id_value),
            "episodeId": nullable(id_value),
            "opportunityId": nullable(id_value),
            "tapeChannel": nullable(enum(*registry["tapeChannels"])),
            "candidateSource": nullable(
                enum("event_opportunity", "story_successor", "episode_beat", "filler")
            ),
            "candidateOrder": nullable(candidate_order),
            "relation": nullable(enum(*relation_ids)),
            "urgency": nullable(enum("background", "context", "story", "critical")),
            "score": nullable(finite),
            "threshold": finite,
            "runnerUp": nullable(runner_up),
            "terminalReason": reason,
        },
        **{
            "x-irswitch-invariants": [
                "silence_has_no_candidate_identity",
                "non_silence_has_candidate_identity",
                "decisions_newest_first",
            ]
        },
    )
    actor_binding = closed(
        {
            "actorId": id_value,
            "aliases": array({"type": "string", "minLength": 1, "maxLength": 64}, 1, 8, True),
        }
    )
    issue = closed(
        {
            "code": enum(*verifier_reasons),
            "severity": enum("error", "warning"),
            "message": {"type": "string", "minLength": 1, "maxLength": 256},
        }
    )
    claim = closed(
        {
            "predicate": id_value,
            "subjectId": nullable(id_value),
            "objectId": nullable(id_value),
            "verdict": enum("supported", "unsupported", "ambiguous"),
        }
    )
    defs.update(
        {
            "DecisionsResponse": closed(
                {
                    "schemaVersion": {"const": VERSION},
                    "runtime": {"type": "boolean"},
                    "decisions": array(decision, 0, 100),
                }
            ),
            "ValidateRequest": closed(
                {
                    "schemaVersion": {"const": VERSION},
                    "text": {"type": "string", "minLength": 1, "maxLength": 512},
                    "beatId": id_value,
                    "evaluationAtMonoMs": n0,
                    "actorBindings": array(actor_binding, 0, 16),
                    "factBindings": array({"$ref": "#/$defs/AtomicFact"}, 1, 32),
                }
            ),
            "ValidateResponse": closed(
                {
                    "schemaVersion": {"const": VERSION},
                    "valid": {"type": "boolean"},
                    "beatId": id_value,
                    "issues": array(issue, 0, 32),
                    "claims": array(claim, 0, 64),
                },
                **{"x-irswitch-invariants": ["valid_iff_no_error_issues"]},
            ),
            "SpeakRequest": closed(
                {
                    "schemaVersion": {"const": VERSION},
                    "text": {"type": "string", "minLength": 1, "maxLength": 400},
                    "language": {"const": "en"},
                }
            ),
            "SpeakAcceptedResponse": closed(
                {
                    "schemaVersion": {"const": VERSION},
                    "accepted": {"const": True},
                    "requestId": id_value,
                    "admittedState": {"const": "committed"},
                }
            ),
            "HealthCommentarySummary": closed(
                {
                    "status": enum(*registry["stateRegistry"]["narrativeRuntime"]),
                    "reason": nullable(enum(*health_reasons)),
                }
            ),
        }
    )
    public_names = [
        "ErrorResponse",
        "StatusResponse",
        "DecisionsResponse",
        "ValidateRequest",
        "ValidateResponse",
        "SpeakRequest",
        "SpeakAcceptedResponse",
        "HealthCommentarySummary",
    ]
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://irswitch.local/contracts/v2/api-contracts.schema.json",
        "title": "irswitch commentary-runtime/2 public API payloads",
        "oneOf": [{"$ref": f"#/$defs/{name}"} for name in public_names],
        "$defs": defs,
        "x-irswitch-invariants": [
            "atomic_fact_definition_byte_equivalent_to_dto_bundle",
            "finite_numbers_only",
            "normalized_strings_no_control_characters",
            "registered_reason_relation_channel_ids_only",
        ],
    }


def build_contract() -> dict[str, Any]:
    return {
        "schemaVersion": "commentary-api-contract/2",
        "runtimeSchemaVersion": VERSION,
        "responseContentType": "application/json",
        "writeTransport": {
            "contentType": "application/json",
            "csrfHeader": {"name": "X-Requested-With", "value": "irswitch"},
            "peerPolicy": "socket_peer_loopback_only_forwarded_headers_ignored",
            "maximumBodyBytes": 65536,
            "admissionTimeoutMs": 1000,
        },
        "routes": [
            {
                "method": "GET",
                "path": "/api/commentary/status",
                "requestSchema": None,
                "successStatus": 200,
                "responseSchema": "StatusResponse",
            },
            {
                "method": "GET",
                "path": "/api/commentary/decisions",
                "requestSchema": None,
                "successStatus": 200,
                "responseSchema": "DecisionsResponse",
                "query": {
                    "limitDefault": 20,
                    "limitMinimum": 1,
                    "limitMaximum": 100,
                    "behavior": "integer_then_clamp",
                },
            },
            {
                "method": "POST",
                "path": "/api/commentary/validate",
                "requestSchema": "ValidateRequest",
                "successStatus": 200,
                "responseSchema": "ValidateResponse",
            },
            {
                "method": "POST",
                "path": "/api/commentary/speak",
                "requestSchema": "SpeakRequest",
                "successStatus": 202,
                "responseSchema": "SpeakAcceptedResponse",
            },
        ],
        "errorStatus": ERROR_STATUS,
        "removedRoutes": [
            {
                "method": "GET",
                "path": "/api/commentary/assignments",
                "behavior": "generic_server_404_no_commentary_tombstone",
            }
        ],
        "healthAugmentation": {
            "method": "GET",
            "path": "/health",
            "field": "commentary",
            "schema": "HealthCommentarySummary",
            "commentaryDegradationChangesOverallSuccess": False,
        },
        "privacy": {
            "forbiddenResponseFields": [
                "prompt",
                "completion",
                "endpoint",
                "exception",
                "absolutePath",
                "dispatchToken",
                "device",
            ],
            "tapePathForm": "relative_only",
        },
    }


def _fact() -> dict[str, Any]:
    return {
        "schemaVersion": "atomic-fact/2",
        "factId": "fact:88",
        "predicate": "battle.approaching",
        "subjectId": "hero",
        "objectId": "car:22",
        "attributes": {"materialBand": "material", "gap": 1.4, "targetEpoch": "relation:4"},
        "polarity": "positive",
        "validFromMonoMs": 89000,
        "validUntilMonoMs": 94000,
        "observedAtMonoMs": 90180,
        "broadcastEpoch": 2,
        "streamEpoch": 3,
        "occurrenceId": "3:race:2",
        "lineageId": "3:practice:0>3:qualifying:1>3:race:2",
        "evidenceRefs": ["event:401", "feature:gap-ahead:77"],
        "confidence": 0.94,
        "scope": "occurrence",
        "status": "active",
        "revision": 4,
    }


def _status() -> dict[str, Any]:
    digest = "sha256:" + "1" * 64
    return {
        "schemaVersion": VERSION,
        "status": "ready",
        "reason": None,
        "language": "en",
        "timeline": {
            "broadcastEpoch": 2,
            "streamEpoch": 3,
            "narrativeRunActive": True,
            "streamActive": True,
            "streamState": "active",
            "sessionPlan": {
                "revision": 4,
                "valid": True,
                "reason": None,
                "stages": ["practice", "qualifying", "race"],
            },
            "sessionRef": {"subSessionId": "123", "sessionNum": 2},
            "occurrenceId": "3:race:2",
            "lineageId": "3:practice:0>3:qualifying:1>3:race:2",
            "stage": "race",
            "historyComplete": True,
        },
        "speech": {
            "state": "idle",
            "sourceKind": None,
            "utteranceId": None,
            "beatId": None,
            "opportunityId": None,
            "backend": None,
            "backendGeneration": None,
            "dispatchedAtMonoMs": None,
            "acceptedAtMonoMs": None,
            "lastTerminal": {
                "utteranceId": "utt:17",
                "sourceKind": "narrative",
                "reason": "completed",
                "atMonoMs": 88710,
            },
        },
        "queues": {
            "mailbox": {"depth": 0, "capacity": 64, "overflows": 0},
            "opportunities": {"depth": 2, "capacity": 128, "expired": 4, "evicted": 0},
        },
        "episodes": {
            "active": 1,
            "candidate": 0,
            "suspended": 0,
            "retainedCurrentCapacity": 64,
            "resolved": 12,
            "resolvedCapacity": 256,
        },
        "catalog": {
            "schemaVersion": "narrative-catalog/2",
            "hash": digest,
            "eventIdentifierCount": 60,
            "beatCount": 64,
        },
        "config": {
            "schemaVersion": "commentary-config/2",
            "desiredGeneration": 7,
            "desiredHash": digest,
            "effectiveHash": "sha256:" + "2" * 64,
            "applySequence": 12,
            "pendingChanges": [
                {
                    "key": "commentary.detector.battle_ahead_v1.max_closing_slope",
                    "boundary": "next_stream",
                    "desiredGeneration": 7,
                }
            ],
        },
        "components": {
            "llm": {
                "status": "ready",
                "reason": None,
                "generation": 2,
                "configGeneration": 7,
                "model": "qwen3:4b-instruct-2507-q4_K_M",
                "residencyEvidence": "warmup_succeeded",
                "lastAttempt": {
                    "requestId": "rr:12",
                    "outcome": "succeeded",
                    "ttfbMs": 82,
                    "ttftMs": 130,
                    "totalMs": 530,
                    "reducerLagMs": 3,
                    "terminalReason": None,
                },
            },
            "tts": {
                "status": "ready",
                "reason": None,
                "backend": "supertonic",
                "backendGeneration": 4,
                "configGeneration": 7,
                "quarantinedGeneration": None,
                "voice": "M1",
            },
            "tape": {
                "status": "disabled",
                "reason": None,
                "path": None,
                "size": 0,
                "drops": 0,
                "dropsByPriority": {"sample": 0, "normal": 0, "critical": 0},
                "purposeCounts": [],
            },
            "detectors": {"status": "ready", "reason": None, "disabled": []},
            "facts": {
                "status": "ready",
                "reason": None,
                "viewRevision": 204,
                "active": 87,
                "historicalSummaries": 19,
                "historyComplete": True,
            },
        },
        "byTapeChannel": {
            "race.battle.closing": {
                "kick": 3,
                "accepted": 2,
                "queued": 2,
                "selected": 1,
                "started": 1,
                "expired": 1,
            }
        },
    }


def build_goldens() -> dict[str, Any]:
    ready = _status()
    unknown = copy.deepcopy(ready)
    unknown.update(status="degraded", reason="obs_state_unknown")
    unknown["timeline"].update(
        streamActive=None,
        streamState="unknown",
        sessionRef=None,
        occurrenceId=None,
        lineageId=None,
        stage=None,
        historyComplete=False,
    )
    unknown["timeline"]["sessionPlan"] = {
        "revision": 5,
        "valid": False,
        "reason": "session_plan_conflict",
        "stages": [],
    }
    validate_request = {
        "schemaVersion": VERSION,
        "text": "He is closing on Morgan, the gap at one point four seconds.",
        "beatId": "battle.approach",
        "evaluationAtMonoMs": 90231,
        "actorBindings": [
            {"actorId": "hero", "aliases": ["he", "the driver"]},
            {"actorId": "car:22", "aliases": ["Morgan", "the car ahead"]},
        ],
        "factBindings": [_fact()],
    }
    decision = {
        "reducerSequence": 418,
        "atMonoMs": 90231,
        "decision": "selected",
        "reason": "highest_valid_candidate",
        "beatId": "battle.approach",
        "episodeId": "battle-ahead:3:17:22:4",
        "opportunityId": "opp:401",
        "tapeChannel": "race.battle.closing",
        "candidateSource": "event_opportunity",
        "candidateOrder": {"reducerSequence": 417, "sourceOrdinal": 0},
        "relation": "updates_active_episode",
        "urgency": "story",
        "score": 68.5,
        "threshold": 35.0,
        "runnerUp": {"beatId": "battle.pursuit", "score": 56.0},
        "terminalReason": None,
    }
    valid = [
        {"id": "status_ready", "schema": "StatusResponse", "value": ready},
        {"id": "status_unknown_invalid_plan", "schema": "StatusResponse", "value": unknown},
        {
            "id": "decisions_selected",
            "schema": "DecisionsResponse",
            "value": {"schemaVersion": VERSION, "runtime": True, "decisions": [decision]},
        },
        {"id": "validate_request", "schema": "ValidateRequest", "value": validate_request},
        {
            "id": "validate_supported",
            "schema": "ValidateResponse",
            "value": {
                "schemaVersion": VERSION,
                "valid": True,
                "beatId": "battle.approach",
                "issues": [],
                "claims": [
                    {
                        "predicate": "battle.approaching",
                        "subjectId": "hero",
                        "objectId": "car:22",
                        "verdict": "supported",
                    }
                ],
            },
        },
        {
            "id": "validate_rejected",
            "schema": "ValidateResponse",
            "value": {
                "schemaVersion": VERSION,
                "valid": False,
                "beatId": "battle.approach",
                "issues": [
                    {
                        "code": "actor_reversed",
                        "severity": "error",
                        "message": "Actor direction is reversed.",
                    }
                ],
                "claims": [
                    {
                        "predicate": "battle.approaching",
                        "subjectId": "car:22",
                        "objectId": "hero",
                        "verdict": "unsupported",
                    }
                ],
            },
        },
        {
            "id": "speak_request",
            "schema": "SpeakRequest",
            "value": {"schemaVersion": VERSION, "text": "Commentary audio test.", "language": "en"},
        },
        {
            "id": "speak_accepted",
            "schema": "SpeakAcceptedResponse",
            "value": {
                "schemaVersion": VERSION,
                "accepted": True,
                "requestId": "manual:7f5b",
                "admittedState": "committed",
            },
        },
        {
            "id": "health_ready",
            "schema": "HealthCommentarySummary",
            "value": {"status": "ready", "reason": None},
        },
    ]
    for code, status in ERROR_STATUS.items():
        valid.append(
            {
                "id": f"error_{code}",
                "schema": "ErrorResponse",
                "httpStatus": status,
                "value": {
                    "schemaVersion": VERSION,
                    "error": {"code": code, "message": "Bounded public detail.", "fields": {}},
                },
            }
        )
    collision = copy.deepcopy(validate_request)
    collision["actorBindings"][1]["aliases"].append(" HE ")
    expired = copy.deepcopy(validate_request)
    expired["evaluationAtMonoMs"] = 94000
    idle_leak = copy.deepcopy(ready)
    idle_leak["speech"]["utteranceId"] = "utt:active"
    drop_mismatch = copy.deepcopy(ready)
    drop_mismatch["components"]["tape"]["drops"] = 1
    partial_session = copy.deepcopy(ready)
    partial_session["timeline"]["lineageId"] = None
    unknown_beat = copy.deepcopy(validate_request)
    unknown_beat["beatId"] = "unknown.beat"
    control_text = {
        "schemaVersion": VERSION,
        "text": "Bad\u0001text",
        "language": "en",
    }
    invalid = [
        {
            "id": "speak_unknown_field",
            "schema": "SpeakRequest",
            "value": {**valid[6]["value"], "force": True},
            "errorContains": "unknown force",
        },
        {
            "id": "speak_wrong_language",
            "schema": "SpeakRequest",
            "value": {**valid[6]["value"], "language": "cs"},
            "errorContains": "expected const 'en'",
        },
        {
            "id": "validate_alias_collision",
            "schema": "ValidateRequest",
            "value": collision,
            "errorContains": "alias collision",
        },
        {
            "id": "validate_at_expiry",
            "schema": "ValidateRequest",
            "value": expired,
            "errorContains": "fact not valid at evaluation instant",
        },
        {
            "id": "status_idle_identity_leak",
            "schema": "StatusResponse",
            "value": idle_leak,
            "errorContains": "idle speech field is non-null",
        },
        {
            "id": "status_drop_sum_mismatch",
            "schema": "StatusResponse",
            "value": drop_mismatch,
            "errorContains": "tape drop sum differs",
        },
        {
            "id": "status_partial_session_identity",
            "schema": "StatusResponse",
            "value": partial_session,
            "errorContains": "session identity is partial",
        },
        {
            "id": "decision_unknown_relation",
            "schema": "DecisionsResponse",
            "value": {
                "schemaVersion": VERSION,
                "runtime": True,
                "decisions": [{**decision, "relation": "similar_by_embedding"}],
            },
            "errorContains": "expected exactly one oneOf match",
        },
        {
            "id": "validate_unknown_beat",
            "schema": "ValidateRequest",
            "value": unknown_beat,
            "errorContains": "unknown beat",
        },
        {
            "id": "speak_control_character",
            "schema": "SpeakRequest",
            "value": control_text,
            "errorContains": "control character",
        },
    ]
    return {
        "schemaVersion": "commentary-api-goldens/2",
        "valid": valid,
        "invalid": invalid,
        "transport": {
            "valid": [
                {
                    "id": "validate_ipv4_loopback",
                    "method": "POST",
                    "path": "/api/commentary/validate",
                    "peer": "127.0.0.2",
                    "contentType": "application/json",
                    "csrf": "irswitch",
                    "bodyBytes": 4096,
                },
                {
                    "id": "speak_ipv6_loopback",
                    "method": "POST",
                    "path": "/api/commentary/speak",
                    "peer": "::1",
                    "contentType": "application/json",
                    "csrf": "irswitch",
                    "bodyBytes": 128,
                },
            ],
            "invalid": [
                {
                    "id": "public_peer_forwarded_loopback",
                    "peer": "192.168.1.8",
                    "forwardedFor": "127.0.0.1",
                    "contentType": "application/json",
                    "csrf": "irswitch",
                    "bodyBytes": 128,
                    "error": "forbidden",
                },
                {
                    "id": "missing_csrf",
                    "peer": "127.0.0.1",
                    "contentType": "application/json",
                    "csrf": None,
                    "bodyBytes": 128,
                    "error": "forbidden",
                },
                {
                    "id": "wrong_content_type",
                    "peer": "127.0.0.1",
                    "contentType": "text/plain",
                    "csrf": "irswitch",
                    "bodyBytes": 128,
                    "error": "invalid_request",
                },
                {
                    "id": "oversized_body",
                    "peer": "127.0.0.1",
                    "contentType": "application/json",
                    "csrf": "irswitch",
                    "bodyBytes": 65537,
                    "error": "invalid_request",
                },
            ],
        },
        "query": [
            {"input": None, "effectiveLimit": 20},
            {"input": -4, "effectiveLimit": 1},
            {"input": 999, "effectiveLimit": 100},
        ],
        "removed": {
            "method": "GET",
            "path": "/api/commentary/assignments",
            "commentaryJson": False,
            "behavior": "generic_server_404_no_commentary_tombstone",
        },
    }


def invariant_errors(schema_name: str, value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    predicates = {row["id"]: row for row in registry["factPredicates"]}
    beats = {
        row["id"] for row in json.loads(BEAT_CATALOG_PATH.read_text(encoding="utf-8"))["beats"]
    }

    def inspect(node: Any) -> None:
        if isinstance(node, float) and not math.isfinite(node):
            errors.append("non-finite number")
        elif isinstance(node, str) and any(
            unicodedata.category(character) == "Cc" for character in node
        ):
            errors.append("control character")
        elif isinstance(node, list):
            for item in node:
                inspect(item)
        elif isinstance(node, dict):
            for item in node.values():
                inspect(item)

    inspect(value)
    if schema_name == "StatusResponse":
        timeline = value["timeline"]
        expected_active = {"inactive": False, "active": True, "unknown": None}[
            timeline["streamState"]
        ]
        if timeline["streamActive"] != expected_active:
            errors.append("stream active projection differs")
        session_values = [
            timeline[name] for name in ("sessionRef", "occurrenceId", "lineageId", "stage")
        ]
        if any(item is None for item in session_values) and not all(
            item is None for item in session_values
        ):
            errors.append("session identity is partial")
        if timeline["sessionRef"] is None and timeline["historyComplete"]:
            errors.append("missing session cannot be history complete")
        plan = timeline["sessionPlan"]
        if plan and (
            (plan["valid"] and (not plan["stages"] or plan["reason"] is not None))
            or (not plan["valid"] and (plan["stages"] or plan["reason"] != "session_plan_conflict"))
        ):
            errors.append("session plan shape differs")
        speech = value["speech"]
        if speech["state"] == "idle" and any(
            speech[name] is not None
            for name in (
                "sourceKind",
                "utteranceId",
                "beatId",
                "opportunityId",
                "backend",
                "backendGeneration",
                "dispatchedAtMonoMs",
                "acceptedAtMonoMs",
            )
        ):
            errors.append("idle speech field is non-null")
        tape = value["components"]["tape"]
        if tape["drops"] != sum(tape["dropsByPriority"].values()):
            errors.append("tape drop sum differs")
        purpose_counts = tape.get("purposeCounts") or []
        if [row["purposeChannel"] for row in purpose_counts] != sorted(
            {row["purposeChannel"] for row in purpose_counts}
        ):
            errors.append("tape purpose counts not sorted unique")
        if any(row["count"] < 1 for row in purpose_counts):
            errors.append("tape purpose count is zero")
        pending = value["config"]["pendingChanges"]
        if [row["key"] for row in pending] != sorted({row["key"] for row in pending}):
            errors.append("pending changes not sorted unique")
        disabled = value["components"]["detectors"]["disabled"]
        if [row["id"] for row in disabled] != sorted({row["id"] for row in disabled}):
            errors.append("disabled detectors not sorted unique")
        if any(not any(counter.values()) for counter in value["byTapeChannel"].values()):
            errors.append("zero-only tape channel counter exposed")
    elif schema_name == "ValidateRequest":
        if value["beatId"] not in beats:
            errors.append("unknown beat")
        fact_ids = [fact["factId"] for fact in value["factBindings"]]
        if len(fact_ids) != len(set(fact_ids)):
            errors.append("duplicate fact ID")
        normalized: dict[str, str] = {}
        used_actors = {
            actor
            for fact in value["factBindings"]
            for actor in (fact["subjectId"], fact["objectId"])
            if actor is not None
        }
        bound_actors = {row["actorId"] for row in value["actorBindings"]}
        if len(bound_actors) != len(value["actorBindings"]):
            errors.append("duplicate actor binding")
        if used_actors != bound_actors:
            errors.append("actor bindings are incomplete or unused")
        for binding in value["actorBindings"]:
            local_aliases: set[str] = set()
            for alias in binding["aliases"]:
                key = " ".join(alias.split()).casefold()
                if key in local_aliases:
                    errors.append("duplicate normalized alias")
                local_aliases.add(key)
                if key in normalized and normalized[key] != binding["actorId"]:
                    errors.append("alias collision across actor IDs")
                normalized[key] = binding["actorId"]
        now = value["evaluationAtMonoMs"]
        for fact in value["factBindings"]:
            predicate = predicates.get(fact["predicate"])
            if predicate is None:
                errors.append("unknown fact predicate")
            else:
                allowed = {row["id"] for row in predicate["attributes"]}
                required = {row["id"] for row in predicate["attributes"] if row["required"]}
                present = set(fact["attributes"])
                if present - allowed:
                    errors.append("unknown fact attribute")
                if required - present:
                    errors.append("required fact attribute missing")
            if (
                now < fact["validFromMonoMs"]
                or fact["validUntilMonoMs"] is not None
                and now >= fact["validUntilMonoMs"]
            ):
                errors.append("fact not valid at evaluation instant")
    elif schema_name == "ValidateResponse":
        has_error = any(row["severity"] == "error" for row in value["issues"])
        if value["valid"] == has_error:
            errors.append("valid flag differs from issue severities")
    elif schema_name == "DecisionsResponse":
        sequences = [row["reducerSequence"] for row in value["decisions"]]
        if sequences != sorted(sequences, reverse=True):
            errors.append("decisions not newest first")
        for row in value["decisions"]:
            identity_fields = (
                "beatId",
                "episodeId",
                "tapeChannel",
                "candidateSource",
                "candidateOrder",
                "urgency",
                "score",
            )
            if row["decision"] == "silence" and any(
                row[name] is not None for name in identity_fields
            ):
                errors.append("silence has candidate identity")
            if row["decision"] != "silence" and any(row[name] is None for name in identity_fields):
                errors.append("non-silence missing candidate identity")
    return errors


def transport_error(row: dict[str, Any], maximum: int) -> str | None:
    try:
        peer = ipaddress.ip_address(row["peer"])
    except ValueError:
        return "forbidden"
    if not peer.is_loopback or row["csrf"] != "irswitch":
        return "forbidden"
    if row["contentType"] != "application/json" or row["bodyBytes"] > maximum:
        return "invalid_request"
    return None


def validate_all(contract: dict[str, Any], schema: dict[str, Any], goldens: dict[str, Any]) -> None:
    expected_contract = build_contract()
    expected_schema = build_schema()
    expected_goldens = build_goldens()
    if (
        canonical(contract) != canonical(expected_contract)
        or canonical(schema) != canonical(expected_schema)
        or canonical(goldens) != canonical(expected_goldens)
    ):
        raise ValueError("API contract, schema or goldens are stale")
    dto_atomic = json.loads(DTO_SCHEMA_PATH.read_text(encoding="utf-8"))["$defs"]["AtomicFact"]
    if canonical(schema["$defs"]["AtomicFact"]) != canonical(dto_atomic):
        raise ValueError("API AtomicFact differs from DTO bundle")
    for fixture in goldens["valid"]:
        target = schema["$defs"][fixture["schema"]]
        errors = schema_errors(fixture["value"], target, schema) + invariant_errors(
            fixture["schema"], fixture["value"]
        )
        if errors:
            raise ValueError(f"valid API golden {fixture['id']} rejected: {errors[0]}")
        if (
            fixture["schema"] == "ErrorResponse"
            and fixture["httpStatus"] != contract["errorStatus"][fixture["value"]["error"]["code"]]
        ):
            raise ValueError(f"error status mismatch in {fixture['id']}")
    for fixture in goldens["invalid"]:
        target = schema["$defs"][fixture["schema"]]
        errors = schema_errors(fixture["value"], target, schema) + invariant_errors(
            fixture["schema"], fixture["value"]
        )
        if not errors or fixture["errorContains"] not in errors[0]:
            raise ValueError(
                f"invalid API golden {fixture['id']} failed for wrong reason: {errors[:1]}"
            )
    maximum = contract["writeTransport"]["maximumBodyBytes"]
    for fixture in goldens["transport"]["valid"]:
        if transport_error(fixture, maximum) is not None:
            raise ValueError(f"valid transport golden {fixture['id']} rejected")
    for fixture in goldens["transport"]["invalid"]:
        if transport_error(fixture, maximum) != fixture["error"]:
            raise ValueError(f"invalid transport golden {fixture['id']} differed")
    for row in goldens["query"]:
        effective = 20 if row["input"] is None else min(100, max(1, row["input"]))
        if effective != row["effectiveLimit"]:
            raise ValueError("decision limit clamp differs")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    contract, schema, goldens = build_contract(), build_schema(), build_goldens()
    if args.write:
        for path, value in (
            (CONTRACT_PATH, contract),
            (SCHEMA_PATH, schema),
            (GOLDENS_PATH, goldens),
        ):
            path.write_text(
                json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
                encoding="utf-8",
            )
        print(f"wrote {CONTRACT_PATH.name}, {SCHEMA_PATH.name} and {GOLDENS_PATH.name}")
        return 0
    checked = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (CONTRACT_PATH, SCHEMA_PATH, GOLDENS_PATH)
    ]
    validate_all(*checked)
    print(
        f"API contracts OK: 4 routes, 8 public schemas, {len(goldens['valid'])} valid + {len(goldens['invalid'])} invalid payload goldens, 6 transport/query guards, 1 removed route"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
