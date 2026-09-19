#!/usr/bin/env python3
"""Build/check structural JSON Schemas for the frozen v2 narrative DTOs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

OUT = Path(__file__).with_name("dto-contracts.schema.json")
GOLDENS = Path(__file__).with_name("dto-schema-goldens.json")
ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"
LINEAGE_PATTERN = (
    r"^[1-9][0-9]*:(practice|qualifying|race):(0|[1-9][0-9]*)"
    r"(>[1-9][0-9]*:(practice|qualifying|race):(0|[1-9][0-9]*))*$"
)
HASH_PATTERN = r"^sha256:[0-9a-f]{64}$"

S = {"type": "string"}
ID = {"type": "string", "pattern": ID_PATTERN}
SCHEMA_VERSION = {
    "type": "string",
    "pattern": r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}(/[1-9][0-9]*)?$",
    "maxLength": 128,
}
LINEAGE_ID = {"type": "string", "pattern": LINEAGE_PATTERN, "maxLength": 512}
HASH = {"type": "string", "pattern": HASH_PATTERN}
N0 = {"type": "integer", "minimum": 0}
P1 = {"type": "integer", "minimum": 1}
NUM = {"type": "number"}
BOOL = {"type": "boolean"}
NULLABLE_ID = {"oneOf": [ID, {"type": "null"}]}
NULLABLE_LINEAGE_ID = {"oneOf": [LINEAGE_ID, {"type": "null"}]}
NULLABLE_S = {"type": ["string", "null"]}
NULLABLE_N0 = {"type": ["integer", "null"], "minimum": 0}


def arr(item: dict[str, Any], minimum: int, maximum: int) -> dict[str, Any]:
    return {
        "type": "array",
        "items": item,
        "minItems": minimum,
        "maxItems": maximum,
        "uniqueItems": True,
    }


def closed(
    version: str,
    fields: dict[str, dict[str, Any]],
    optional: set[str] | None = None,
    all_of: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    optional = optional or set()
    properties = {"schemaVersion": {"const": version}, **fields}
    result: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": ["schemaVersion", *[name for name in fields if name not in optional]],
    }
    if all_of:
        result["allOf"] = all_of
    return result


def enum(*values: str) -> dict[str, Any]:
    return {"enum": list(values)}


def nullable(value: dict[str, Any]) -> dict[str, Any]:
    return {"oneOf": [value, {"type": "null"}]}


def obj(fields: dict[str, dict[str, Any]], optional: set[str] | None = None) -> dict[str, Any]:
    optional = optional or set()
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": fields,
        "required": [name for name in fields if name not in optional],
    }


SESSION_REF = obj({"subSessionId": ID, "sessionNum": N0})
ORDER = obj({"reducerSequence": N0, "sourceOrdinal": N0})
SCALAR_UNITS = (
    "boolean",
    "id",
    "text",
    "seconds",
    "seconds_per_second",
    "fraction",
    "count",
    "signed_count",
    "ordinal",
    "lap_number",
    "celsius",
    "meters_per_second",
    "beats_per_minute",
    "stage",
    "vehicle_phase",
    "broadcast_context",
    "fact_quality",
)
FEATURE_VALUE = obj(
    {
        "featureId": ID,
        "value": {
            "oneOf": [
                {"type": "boolean"},
                {"type": "number"},
                {"type": "string", "minLength": 1, "maxLength": 160},
            ]
        },
        "unit": enum(*SCALAR_UNITS),
        "quality": enum("measured", "derived", "estimated", "degraded", "unknown"),
        "observedMonoMs": N0,
        "validUntilMonoMs": NULLABLE_N0,
        "evidenceRefs": arr(ID, 1, 16),
    }
)
WINDOW_FRAME_RANGE = obj(
    {
        "firstFrameSequence": P1,
        "lastFrameSequence": P1,
        "postWindowComplete": BOOL,
    }
)
PREDICATE_RESULT = obj(
    {
        "predicateId": ID,
        "result": {"enum": [True, False, "unknown"]},
    }
)
COVERAGE_BUCKET = obj(
    {
        "bucketStartMonoMs": N0,
        "bucketDurationS": {"type": "number", "exclusiveMinimum": 0},
        "coveredDurationS": {"type": "number", "minimum": 0},
        "sampleCount": N0,
        "usable": BOOL,
    }
)
REDACTION_POLICY = obj(
    {
        "sensitiveValues": {"const": "marker_only"},
        "prompt": enum("none", "hash", "full"),
        "completion": BOOL,
    }
)
FUNNEL = obj(
    {
        "sourceClass": enum("detector", "direct", "lifecycle", "silence", "successor"),
        "candidateId": NULLABLE_ID,
        "detectorObservationId": NULLABLE_ID,
        "eventId": NULLABLE_ID,
        "materialRevision": NULLABLE_N0,
        "opportunityId": NULLABLE_ID,
        "planId": NULLABLE_ID,
        "utteranceId": NULLABLE_ID,
        "tapeChannel": ID,
    }
)


def build_schema() -> dict[str, Any]:
    any_obj = {"type": "object"}

    def id_list(lo: int, hi: int) -> dict[str, Any]:
        return arr(ID, lo, hi)

    defs: dict[str, Any] = {}

    defs["SessionPlan"] = closed(
        "session-plan/2",
        {
            "planRevision": N0,
            "capturedMonoMs": N0,
            "subSessionId": NULLABLE_ID,
            "valid": BOOL,
            "reason": NULLABLE_S,
            "entries": arr(
                obj({"sessionRef": SESSION_REF, "stage": enum("practice", "qualifying", "race")}),
                0,
                3,
            ),
            "unsupportedEntries": arr(obj({"sessionNum": N0, "externalType": S}), 0, 16),
            "unsupportedOverflowCount": N0,
        },
    )
    defs["SessionPlan"]["oneOf"] = [
        {
            "properties": {
                "valid": {"const": True},
                "reason": {"type": "null"},
                "entries": {"minItems": 1},
            }
        },
        {
            "properties": {
                "valid": {"const": False},
                "reason": {"const": "session_plan_conflict"},
                "entries": {"maxItems": 0},
            }
        },
    ]
    defs["TimelineSnapshot"] = closed(
        "timeline-snapshot/2",
        {
            "timelineRevision": N0,
            "observedMonoMs": N0,
            "broadcastEpoch": N0,
            "streamEpoch": N0,
            "narrativeRunActive": BOOL,
            "obsState": enum("inactive", "active", "unknown"),
            "sessionRef": nullable(SESSION_REF),
            "stage": nullable(enum("practice", "qualifying", "race")),
            "sessionPlanRevision": NULLABLE_N0,
            "occurrenceId": NULLABLE_ID,
            "lineageId": NULLABLE_LINEAGE_ID,
            "historyComplete": BOOL,
            "transitionReasons": id_list(0, 8),
        },
    )
    defs["FeatureFrame"] = closed(
        "feature-frame/2",
        {
            "frameSequence": P1,
            "observedMonoMs": N0,
            "sourceSnapshotId": ID,
            "broadcastEpoch": N0,
            "streamEpoch": N0,
            "sessionRef": nullable(SESSION_REF),
            "occurrenceId": NULLABLE_ID,
            "lineageId": NULLABLE_LINEAGE_ID,
            "correlationKey": id_list(1, 8),
            "values": arr({"$ref": "#/$defs/FeatureValue"}, 0, 64),
        },
    )
    defs["FeatureValue"] = FEATURE_VALUE
    defs["WindowFrameRange"] = WINDOW_FRAME_RANGE
    defs["PredicateResult"] = PREDICATE_RESULT
    defs["CoverageBucket"] = COVERAGE_BUCKET
    defs["RedactionPolicy"] = REDACTION_POLICY
    defs["DetectorObservation"] = closed(
        "detector-observation/2",
        {
            "observationId": ID,
            "detectorId": ID,
            "detectorVersion": ID,
            "detectorConfigHash": HASH,
            "parameterSnapshotId": ID,
            "observedMonoMs": N0,
            "broadcastEpoch": N0,
            "streamEpoch": N0,
            "sessionRef": nullable(SESSION_REF),
            "occurrenceId": NULLABLE_ID,
            "lineageId": NULLABLE_LINEAGE_ID,
            "correlationKey": id_list(0, 8),
            "windowFrameRange": nullable({"$ref": "#/$defs/WindowFrameRange"}),
            "previousState": enum("inactive", "candidate", "active", "clearing"),
            "candidateState": enum("inactive", "candidate", "active", "clearing"),
            "transitionReason": ID,
            "featureValues": arr({"$ref": "#/$defs/FeatureValue"}, 0, 64),
            "predicateResults": arr({"$ref": "#/$defs/PredicateResult"}, 0, 64),
            "coverage": arr({"$ref": "#/$defs/CoverageBucket"}, 0, 16),
            "wouldEmitEventKind": NULLABLE_ID,
            "tapeChannel": ID,
        },
    )
    defs["EventCandidateTap"] = closed(
        "event-candidate-tap/2",
        {
            "candidateId": ID,
            "sourceClass": enum("detector", "direct", "lifecycle"),
            "detectorObservationId": NULLABLE_ID,
            "sourceEnvelope": nullable(any_obj),
            "kind": ID,
            "phase": enum("started", "updated", "ended", "result", "impulse"),
            "occurredMonoMs": N0,
            "broadcastEpoch": N0,
            "streamEpoch": N0,
            "sessionRef": nullable(SESSION_REF),
            "occurrenceId": NULLABLE_ID,
            "lineageId": NULLABLE_LINEAGE_ID,
            "correlationKey": id_list(0, 8),
            "materialRevision": N0,
            "tapeChannel": ID,
            "taxonomyHash": HASH,
            "arbitrationOutcome": enum("accepted", "rejected"),
            "arbitrationReason": ID,
            "acceptedEventId": NULLABLE_ID,
        },
    )
    defs["EventCandidateTap"]["oneOf"] = [
        {
            "properties": {
                "arbitrationOutcome": {"const": "accepted"},
                "arbitrationReason": {"const": "accepted"},
                "acceptedEventId": ID,
            }
        },
        {
            "properties": {
                "arbitrationOutcome": {"const": "rejected"},
                "arbitrationReason": {
                    "enum": [
                        "pit_cycle",
                        "cooldown",
                        "lower_priority",
                        "unmatched_exit",
                        "unmatched_update",
                        "overlay_disabled",
                        "invalid_candidate",
                    ]
                },
                "acceptedEventId": {"type": "null"},
            }
        },
    ]
    defs["NarrativeEvent"] = closed(
        "narrative-event/2",
        {
            "eventId": ID,
            "kind": ID,
            "phase": enum("started", "updated", "ended", "result", "impulse"),
            "deliveryClass": enum("ordinary", "protected"),
            "sourceEnvelope": nullable(any_obj),
            "sourceOrder": nullable(any_obj),
            "occurredMonoMs": N0,
            "broadcastEpoch": N0,
            "streamEpoch": N0,
            "sessionRef": nullable(SESSION_REF),
            "occurrenceId": NULLABLE_ID,
            "lineageId": NULLABLE_LINEAGE_ID,
            "correlationKey": id_list(0, 8),
            "factIds": id_list(1, 32),
            "factViewRevision": N0,
            "materialRevision": N0,
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "tapeChannel": ID,
            "funnel": FUNNEL,
            "taxonomyHash": HASH,
            "payload": {"type": "object", "maxProperties": 32},
        },
    )
    defs["AtomicFact"] = closed(
        "atomic-fact/2",
        {
            "factId": ID,
            "predicate": ID,
            "subjectId": NULLABLE_ID,
            "objectId": NULLABLE_ID,
            "attributes": {"type": "object", "maxProperties": 32},
            "polarity": enum("positive", "negative"),
            "validFromMonoMs": N0,
            "validUntilMonoMs": NULLABLE_N0,
            "observedAtMonoMs": N0,
            "broadcastEpoch": P1,
            "streamEpoch": P1,
            "occurrenceId": NULLABLE_ID,
            "lineageId": NULLABLE_LINEAGE_ID,
            "evidenceRefs": id_list(1, 16),
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "scope": enum("occurrence", "downstream", "stream", "revalidate", "historical_only"),
            "status": enum(
                "provisional",
                "active",
                "expired",
                "superseded",
                "historical",
                "rejected",
                "unknown",
            ),
            "revision": N0,
        },
    )
    defs["AtomicFact"]["oneOf"] = [
        {
            "properties": {
                "scope": {"const": "stream"},
                "occurrenceId": {"type": "null"},
                "lineageId": {"type": "null"},
            }
        },
        {
            "properties": {
                "scope": {"enum": ["occurrence", "downstream", "revalidate", "historical_only"]},
                "occurrenceId": ID,
                "lineageId": LINEAGE_ID,
            }
        },
    ]
    defs["FactView"] = closed(
        "fact-view/2",
        {
            "viewRevision": N0,
            "createdMonoMs": N0,
            "broadcastEpoch": N0,
            "streamEpoch": N0,
            "occurrenceId": NULLABLE_ID,
            "lineageId": NULLABLE_LINEAGE_ID,
            "historyComplete": BOOL,
            "facts": arr({"$ref": "#/$defs/AtomicFact"}, 0, 1024),
            "compactedSummaryRefs": id_list(0, 64),
        },
    )
    defs["Episode"] = closed(
        "episode/2",
        {
            "episodeId": ID,
            "definitionId": ID,
            "scope": enum("stream", "occurrence"),
            "occurrenceId": NULLABLE_ID,
            "lineageId": NULLABLE_LINEAGE_ID,
            "semanticIdentity": id_list(1, 8),
            "correlationIds": id_list(0, 8),
            "state": enum("candidate", "active", "suspended", "resolved", "invalidated"),
            "openedMonoMs": N0,
            "updatedMonoMs": N0,
            "resolvedMonoMs": NULLABLE_N0,
            "resolutionReason": NULLABLE_S,
            "factIds": id_list(0, 64),
            "materialRevision": N0,
            "spokenBeatIds": id_list(0, 64),
            "materialOrder": ORDER,
            "nextEligibleMonoMs": N0,
            "lastSpokenBeatId": NULLABLE_ID,
            "continuationPriority": NUM,
            "historyComplete": BOOL,
        },
    )
    defs["Episode"]["oneOf"] = [
        {
            "properties": {
                "state": {"enum": ["resolved", "invalidated"]},
                "resolvedMonoMs": N0,
                "resolutionReason": ID,
            }
        },
        {
            "properties": {
                "state": {"enum": ["candidate", "active", "suspended"]},
                "resolvedMonoMs": {"type": "null"},
                "resolutionReason": {"type": "null"},
            }
        },
    ]
    defs["EventOpportunity"] = closed(
        "event-opportunity/2",
        {
            "opportunityId": ID,
            "eventId": NULLABLE_ID,
            "eventKind": ID,
            "sourceOrder": nullable(any_obj),
            "funnel": FUNNEL,
            "candidateOrder": ORDER,
            "streamEpoch": P1,
            "occurrenceId": NULLABLE_ID,
            "lineageId": NULLABLE_LINEAGE_ID,
            "episodeId": ID,
            "correlationKey": id_list(0, 8),
            "tapeChannel": ID,
            "createdMonoMs": N0,
            "expiresMonoMs": N0,
            "basePriority": {"type": "number", "minimum": 0, "maximum": 100},
            "urgency": enum("background", "context", "story", "critical"),
            "penaltyCoefficient": {"type": "number", "minimum": 0, "maximum": 4},
            "materialRevision": N0,
            "state": enum(
                "pending", "reserved", "consumed", "expired", "superseded", "invalidated", "evicted"
            ),
            "reservationToken": NULLABLE_ID,
            "terminalReason": NULLABLE_S,
            "policyHash": HASH,
            "sourceFactIds": id_list(1, 32),
        },
    )
    defs["EventOpportunity"]["allOf"] = [
        {
            "oneOf": [
                {
                    "properties": {
                        "eventId": {"type": "null"},
                        "funnel": {"properties": {"sourceClass": {"const": "silence"}}},
                    }
                },
                {
                    "properties": {"eventId": ID},
                    "not": {
                        "properties": {
                            "funnel": {"properties": {"sourceClass": {"const": "silence"}}}
                        }
                    },
                },
            ]
        },
        {
            "oneOf": [
                {
                    "properties": {
                        "state": {"const": "reserved"},
                        "reservationToken": ID,
                        "terminalReason": {"type": "null"},
                    }
                },
                {
                    "properties": {
                        "state": {
                            "enum": ["consumed", "expired", "superseded", "invalidated", "evicted"]
                        },
                        "reservationToken": {"type": "null"},
                        "terminalReason": ID,
                    }
                },
                {
                    "properties": {
                        "state": {"const": "pending"},
                        "reservationToken": {"type": "null"},
                        "terminalReason": {"type": "null"},
                    }
                },
            ]
        },
    ]
    defs["PromptOptions"] = closed(
        "prompt-options/2",
        {
            "freedom": enum("tight", "balanced", "loose"),
            "patternChoice": enum("fixed", "family_pool"),
            "optionalClaimLimit": {"type": "integer", "minimum": 0, "maximum": 2},
            "allowClauseReorder": BOOL,
            "maxSentences": {"type": "integer", "minimum": 1, "maximum": 2},
            "temperature": {"type": "number", "minimum": 0, "maximum": 2},
            "topP": {"type": "number", "exclusiveMinimum": 0, "maximum": 1},
            "seed": {"type": "integer", "minimum": 0, "maximum": 18446744073709551615},
        },
    )
    defs["PromptOptions"]["oneOf"] = [
        {
            "properties": {
                "freedom": {"const": "tight"},
                "patternChoice": {"const": "fixed"},
                "optionalClaimLimit": {"const": 0},
                "allowClauseReorder": {"const": False},
                "maxSentences": {"const": 1},
                "temperature": {"const": 0.15},
                "topP": {"const": 0.75},
            }
        },
        {
            "properties": {
                "freedom": {"const": "balanced"},
                "patternChoice": {"const": "family_pool"},
                "optionalClaimLimit": {"maximum": 1},
                "maxSentences": {"const": 1},
                "temperature": {"const": 0.35},
                "topP": {"const": 0.85},
            }
        },
        {
            "properties": {
                "freedom": {"const": "loose"},
                "patternChoice": {"const": "family_pool"},
                "maxSentences": {"const": 2},
                "temperature": {"const": 0.55},
                "topP": {"const": 0.9},
            }
        },
    ]
    defs["BeatPlan"] = closed(
        "beat-plan/2",
        {
            "planId": ID,
            "planningCycleId": ID,
            "cycleAttemptOrdinal": enum(1, 2),
            "beatId": ID,
            "episodeId": ID,
            "opportunityId": NULLABLE_ID,
            "candidateSource": enum(
                "event_opportunity", "story_successor", "episode_beat", "filler"
            ),
            "funnel": FUNNEL,
            "candidateOrder": ORDER,
            "beatRole": enum("opening", "update", "outcome", "recap", "transition", "filler"),
            "streamEpoch": P1,
            "occurrenceId": NULLABLE_ID,
            "lineageId": NULLABLE_LINEAGE_ID,
            "episodeRevision": N0,
            "requiredClaims": arr(any_obj, 1, 16),
            "optionalClaims": arr(any_obj, 0, 2),
            "forbiddenClaimTypes": id_list(0, 32),
            "selectedFactIds": id_list(1, 32),
            "realizationFamily": ID,
            "realizationPattern": ID,
            "realizationBackend": enum("authored", "qwen_compiled"),
            "promptOptions": {"$ref": "#/$defs/PromptOptions"},
            "language": {"const": "en"},
            "styleCardId": NULLABLE_ID,
            "maxChars": {"type": "integer", "minimum": 1, "maximum": 512},
            "maxSeconds": NUM,
            "plannedMonoMs": N0,
            "expiresMonoMs": N0,
            "sourceRefs": id_list(1, 32),
            "catalogHash": HASH,
            "effectiveConfigHash": HASH,
            "configApplySequence": N0,
            "factViewRevision": N0,
        },
    )
    defs["RealizationBundle"] = closed(
        "realization-bundle/2",
        {
            "bundleId": ID,
            "beatPlan": {"$ref": "#/$defs/BeatPlan"},
            "factBindings": arr({"$ref": "#/$defs/AtomicFact"}, 1, 32),
            "actorBindings": arr(any_obj, 0, 16),
            "surfaceLexicon": any_obj,
            "factBindingHash": HASH,
            "surfaceLexiconHash": HASH,
            "bundleHash": HASH,
        },
    )
    defs["CompiledPrompt"] = closed(
        "compiled-prompt/2",
        {
            "promptId": ID,
            "promptContractVersion": {"const": "qwen-surface-en-tight/1"},
            "bundleId": ID,
            "bundleHash": HASH,
            "realizationFamily": ID,
            "realizationPattern": ID,
            "freedom": enum("tight", "balanced", "loose"),
            "systemText": {"type": "string", "maxLength": 12288},
            "userText": {"type": "string", "maxLength": 20480},
            "systemHash": HASH,
            "userHash": HASH,
            "promptHash": HASH,
            "systemBytes": {"type": "integer", "minimum": 0, "maximum": 12288},
            "userBytes": {"type": "integer", "minimum": 0, "maximum": 20480},
        },
    )
    defs["RealizationRequest"] = closed(
        "realization-request/2",
        {
            "requestId": ID,
            "requestOrdinal": P1,
            "dispatchGeneration": P1,
            "backend": enum("authored", "qwen_compiled"),
            "planId": ID,
            "planningCycleId": ID,
            "cycleAttemptOrdinal": enum(1, 2),
            "bundleId": ID,
            "bundleHash": HASH,
            "compiledPrompt": nullable({"$ref": "#/$defs/CompiledPrompt"}),
            "componentGeneration": NULLABLE_N0,
            "configGeneration": N0,
            "effectiveConfigHash": HASH,
            "configApplySequence": N0,
            "backendRequest": any_obj,
            "capturePolicy": any_obj,
            "dispatchedMonoMs": N0,
            "deadlineMonoMs": N0,
            "requestHash": HASH,
        },
    )
    defs["RealizationRequest"]["oneOf"] = [
        {
            "properties": {
                "backend": {"const": "authored"},
                "compiledPrompt": {"type": "null"},
                "componentGeneration": {"type": "null"},
            }
        },
        {
            "properties": {
                "backend": {"const": "qwen_compiled"},
                "compiledPrompt": {"$ref": "#/$defs/CompiledPrompt"},
                "componentGeneration": P1,
            }
        },
    ]
    defs["RealizationResult"] = closed(
        "realization-result/2",
        {
            "resultId": ID,
            "requestId": ID,
            "requestOrdinal": P1,
            "dispatchGeneration": P1,
            "backend": enum("authored", "qwen_compiled"),
            "outcome": enum("succeeded", "failed", "cancelled"),
            "text": NULLABLE_S,
            "textHash": nullable(HASH),
            "failureReason": NULLABLE_S,
            "modelReported": NULLABLE_S,
            "transportStartedMonoMs": N0,
            "responseStartedMonoMs": NULLABLE_N0,
            "firstContentMonoMs": NULLABLE_N0,
            "completedMonoMs": N0,
            "promptTokens": NULLABLE_N0,
            "completionTokens": NULLABLE_N0,
            "totalTokens": NULLABLE_N0,
            "usageSource": enum("server", "unavailable"),
            "finishReason": NULLABLE_S,
            "resultHash": HASH,
        },
    )
    defs["RealizationResult"]["oneOf"] = [
        {
            "properties": {
                "outcome": {"const": "succeeded"},
                "text": {"type": "string", "minLength": 1},
                "textHash": HASH,
                "failureReason": {"type": "null"},
            }
        },
        {
            "properties": {
                "outcome": {"const": "failed"},
                "text": {"type": "null"},
                "textHash": {"type": "null"},
                "failureReason": {
                    "enum": [
                        "realization_timeout",
                        "realization_transport",
                        "realization_invalid_response",
                        "realization_output_oversize",
                    ]
                },
            }
        },
        {
            "properties": {
                "outcome": {"const": "cancelled"},
                "text": {"type": "null"},
                "textHash": {"type": "null"},
                "failureReason": {"const": "realization_cancelled"},
            }
        },
    ]
    defs["LlmAttempt"] = closed(
        "llm-attempt/2",
        {
            "attemptId": ID,
            "requestId": ID,
            "planId": ID,
            "bundleId": ID,
            "bundleHash": HASH,
            "promptId": NULLABLE_ID,
            "promptHash": nullable(HASH),
            "requestHash": HASH,
            "backend": enum("authored", "qwen_compiled"),
            "configuredModel": NULLABLE_S,
            "componentGeneration": NULLABLE_N0,
            "configGeneration": N0,
            "effectiveConfigHash": HASH,
            "configApplySequence": N0,
            "residencyEvidence": NULLABLE_S,
            "transportOutcome": enum("succeeded", "failed", "cancelled", "timed_out", "stale"),
            "terminalSource": enum("worker", "actor_deadline", "actor_cancellation"),
            "terminalReason": NULLABLE_S,
            "textHash": nullable(HASH),
            "capturedPrompt": nullable(any_obj),
            "capturedCompletion": NULLABLE_S,
            "transportTimes": any_obj,
            "latencyMetrics": any_obj,
            "tokenUsage": any_obj,
            "verifierVerdict": nullable(any_obj),
            "commitVerdict": enum("current", "freshness_stale", "not_reached"),
            "resultHash": nullable(HASH),
        },
    )
    defs["TtsUtterance"] = closed(
        "tts-utterance/2",
        {
            "utteranceId": ID,
            "utteranceOrdinal": P1,
            "sourceKind": enum("narrative", "manual"),
            "funnel": nullable(FUNNEL),
            "planId": NULLABLE_ID,
            "opportunityId": NULLABLE_ID,
            "episodeId": NULLABLE_ID,
            "manualRequestId": NULLABLE_ID,
            "text": {"type": "string", "minLength": 1, "maxLength": 512},
            "textHash": HASH,
            "language": {"const": "en"},
            "backend": enum("sapi", "espeak", "supertonic"),
            "backendGeneration": P1,
            "configGeneration": N0,
            "effectiveConfigHash": HASH,
            "configApplySequence": N0,
            "voice": NULLABLE_S,
            "rate": NUM,
            "steps": NULLABLE_N0,
            "audioDevice": NULLABLE_S,
            "duckInput": NULLABLE_S,
            "duckRatio": NUM,
            "duckFadeMs": N0,
            "maxSeconds": NUM,
            "dispatchedMonoMs": N0,
            "requestHash": HASH,
        },
    )
    defs["TtsUtterance"]["oneOf"] = [
        {
            "properties": {
                "sourceKind": {"const": "narrative"},
                "funnel": FUNNEL,
                "planId": ID,
                "episodeId": ID,
                "manualRequestId": {"type": "null"},
            }
        },
        {
            "properties": {
                "sourceKind": {"const": "manual"},
                "funnel": {"type": "null"},
                "planId": {"type": "null"},
                "opportunityId": {"type": "null"},
                "episodeId": {"type": "null"},
                "manualRequestId": ID,
                "text": {"maxLength": 400},
            }
        },
    ]
    defs["TtsCallback"] = closed(
        "tts-callback/2",
        {
            "callbackId": ID,
            "kind": enum("playback_accepted", "completed", "interrupted", "failed"),
            "utteranceId": ID,
            "utteranceOrdinal": P1,
            "backend": enum("sapi", "espeak", "supertonic"),
            "backendGeneration": P1,
            "dispatchGeneration": P1,
            "workerSequence": P1,
            "observedMonoMs": N0,
            "detailCode": NULLABLE_S,
        },
    )
    defs["TtsCallback"]["oneOf"] = [
        {
            "properties": {
                "kind": {"enum": ["playback_accepted", "completed"]},
                "detailCode": {"type": "null"},
            }
        },
        {
            "properties": {
                "kind": {"const": "interrupted"},
                "detailCode": {"const": "backend_cancelled"},
            }
        },
        {
            "properties": {
                "kind": {"const": "failed"},
                "detailCode": {
                    "enum": [
                        "backend_rejected",
                        "backend_process_exit",
                        "backend_audio_error",
                        "backend_unavailable",
                    ]
                },
            }
        },
    ]
    defs["SpeechExposure"] = closed(
        "speech-exposure/2",
        {
            "utteranceId": ID,
            "sourceKind": enum("narrative", "manual"),
            "planId": NULLABLE_ID,
            "opportunityId": NULLABLE_ID,
            "episodeId": NULLABLE_ID,
            "manualRequestId": NULLABLE_ID,
            "funnel": nullable(FUNNEL),
            "requestHash": HASH,
            "textHash": HASH,
            "backend": enum("sapi", "espeak", "supertonic"),
            "backendGeneration": P1,
            "effectiveConfigHash": HASH,
            "configApplySequence": N0,
            "dispatchedMonoMs": N0,
            "acceptedMonoMs": NULLABLE_N0,
            "terminalMonoMs": N0,
            "terminalReason": ID,
            "opportunityConsumed": BOOL,
            "exposureWeight": enum(0, 1),
            "duckStatus": enum("not_configured", "applied", "unavailable", "restore_unconfirmed"),
            "callbackIds": id_list(0, 2),
        },
    )
    defs["SpeechExposure"]["oneOf"] = [
        {
            "properties": {
                "sourceKind": {"const": "narrative"},
                "funnel": FUNNEL,
                "planId": ID,
                "episodeId": ID,
            }
        },
        {
            "properties": {
                "sourceKind": {"const": "manual"},
                "funnel": {"type": "null"},
                "planId": {"type": "null"},
                "opportunityId": {"type": "null"},
                "episodeId": {"type": "null"},
                "manualRequestId": ID,
                "opportunityConsumed": {"const": False},
                "exposureWeight": {"const": 0},
            }
        },
    ]
    defs["ConfigLedger"] = closed(
        "commentary-config/2",
        {
            "desiredGeneration": N0,
            "desiredHash": HASH,
            "effectiveHash": HASH,
            "applySequence": N0,
            "desiredValues": any_obj,
            "effectiveValues": any_obj,
            "pendingChanges": arr(any_obj, 0, 128),
            "acceptedMonoMs": N0,
        },
    )
    replay_scalar = {
        "oneOf": [
            BOOL,
            {"type": "integer"},
            {"type": "number", "not": {"type": "integer"}},
            S,
            arr(S, 0, 128),
        ]
    }
    defs["EffectiveConfigProjectionEntry"] = obj(
        {
            "key": ID,
            "value": replay_scalar,
            "redacted": {"type": ["boolean", "null"]},
        },
        optional={"value", "redacted"},
    )
    defs["EffectiveConfigProjectionEntry"]["oneOf"] = [
        {
            "required": ["key", "value"],
            "not": {"required": ["redacted"]},
        },
        {
            "required": ["key", "redacted"],
            "properties": {"redacted": {"const": True}},
            "not": {"required": ["value"]},
        },
    ]
    defs["DetectorParameterSnapshot"] = obj(
        {
            "parameterSnapshotId": ID,
            "detectorId": ID,
            "detectorVersion": ID,
            "detectorConfigHash": HASH,
            "parameters": any_obj,
        }
    )
    tape_record_types = [
        "context_applied",
        "feature_frame",
        "detector_observation",
        "event_candidate",
        "narrative_event",
        "fact_change",
        "episode_change",
        "opportunity_change",
        "director_decision",
        "llm_attempt",
        "speech_exposure",
        "config_applied",
        "health_change",
        "mailbox_gap",
        "drop_notice",
        "manifest_trailer",
    ]
    purpose_channels = ["flow", "llm_eval", "detector_tuning"]
    record_priorities = ["sample", "normal", "critical"]
    tape_loss_reasons = [
        "tape_queue_drop",
        "tape_write_failed",
        "tape_flush_timeout",
        "config_transition_lost",
    ]
    defs["ConfigApplied"] = closed(
        "config-applied/2",
        {
            "applySequence": P1,
            "desiredGeneration": N0,
            "boundary": enum(
                "process_start",
                "command",
                "next_stream",
                "next_director_pass",
                "next_silence_deadline",
                "next_beat_plan",
                "next_plan_or_manual",
                "next_request",
                "next_utterance",
                "next_cancellation",
                "next_record",
                "next_rotated_file",
                "next_rotation",
                "next_writer_deadline",
                "next_shutdown",
            ),
            "changedKeys": arr(ID, 1, 128),
            "effectivePatch": arr(
                {"$ref": "#/$defs/EffectiveConfigProjectionEntry"}, 1, 128
            ),
            "oldEffectiveHash": HASH,
            "newEffectiveHash": HASH,
        },
    )
    defs["ConfigApplied"]["x-irswitch-invariants"] = [
        "changed_keys_sorted",
        "effective_patch_sorted",
        "changed_keys_equal_patch_keys",
        "hash_transition_matches_envelope",
    ]
    defs["TapeLossBucket"] = obj(
        {
            "recordType": enum(*tape_record_types),
            "recordPriority": enum(*record_priorities),
            "reason": enum(*tape_loss_reasons),
            "count": P1,
        }
    )
    defs["ConfigTransitionLoss"] = obj(
        {
            "applySequence": P1,
            "oldEffectiveHash": HASH,
            "newEffectiveHash": HASH,
        }
    )
    defs["TapeLossAccumulator"] = obj(
        {
            "buckets": arr({"$ref": "#/$defs/TapeLossBucket"}, 1, 192),
            "firstLostMonoMs": N0,
            "lastLostMonoMs": N0,
            "firstLostReducerSequence": NULLABLE_N0,
            "lastLostReducerSequence": NULLABLE_N0,
            "configTransitions": arr(
                {"$ref": "#/$defs/ConfigTransitionLoss"}, 0, 128
            ),
        }
    )
    defs["TapeLossAccumulator"]["x-irswitch-invariants"] = [
        "buckets_sorted_unique_by_type_priority_reason",
        "loss_time_range_ordered",
        "loss_reducer_range_both_or_neither_ordered",
        "config_transitions_sorted_unique",
    ]
    defs["TapeLossAccumulator"]["oneOf"] = [
        {
            "properties": {
                "firstLostReducerSequence": {"type": "null"},
                "lastLostReducerSequence": {"type": "null"},
            }
        },
        {
            "properties": {
                "firstLostReducerSequence": N0,
                "lastLostReducerSequence": N0,
            }
        },
    ]
    defs["DropNotice"] = closed(
        "drop-notice/2",
        {
            "noticeId": ID,
            "loss": {"$ref": "#/$defs/TapeLossAccumulator"},
        },
    )
    defs["TapeRecordCount"] = obj(
        {"recordType": enum(*tape_record_types), "count": P1}
    )
    defs["TapePurposeCount"] = obj(
        {"purposeChannel": enum(*purpose_channels), "count": P1}
    )
    defs["TapeChannelCount"] = obj({"tapeChannel": ID, "count": P1})
    defs["TapeDropCount"] = obj(
        {"reason": enum(*tape_loss_reasons), "count": P1}
    )
    defs["ManifestTrailer"] = closed(
        "manifest-trailer/2",
        {
            "finalRecordHash": nullable(HASH),
            "fileHash": HASH,
            "recordCounts": arr({"$ref": "#/$defs/TapeRecordCount"}, 0, 16),
            "purposeCounts": arr({"$ref": "#/$defs/TapePurposeCount"}, 0, 3),
            "tapeChannelCounts": arr({"$ref": "#/$defs/TapeChannelCount"}, 0, 36),
            "dropCounts": arr({"$ref": "#/$defs/TapeDropCount"}, 0, 4),
            "lossAccumulator": nullable(
                {"$ref": "#/$defs/TapeLossAccumulator"}
            ),
            "lastReducerSequence": NULLABLE_N0,
            "closeReason": enum(
                "rotation_size",
                "rotation_duration",
                "broadcast_ended",
                "commentary_disabled",
                "recording_disabled",
                "shutdown",
                "write_failed",
                "flush_timeout",
            ),
            "complete": BOOL,
        },
    )
    defs["ManifestTrailer"]["x-irswitch-invariants"] = [
        "counts_sorted_unique_and_match_file",
        "hashes_match_pre_trailer_bytes",
        "loss_requires_incomplete",
        "previous_file_hash_chains_file_hash",
    ]
    defs["ManifestTrailer"]["oneOf"] = [
        {
            "properties": {
                "complete": {"const": True},
                "lossAccumulator": {"type": "null"},
                "closeReason": {
                    "enum": [
                        "rotation_size",
                        "rotation_duration",
                        "broadcast_ended",
                        "commentary_disabled",
                        "recording_disabled",
                        "shutdown",
                    ]
                },
            }
        },
        {"properties": {"complete": {"const": False}}},
    ]
    defs["TapeManifest"] = closed(
        "narrative-tape-manifest/2",
        {
            "recordType": {"const": "manifest"},
            "processInstanceId": ID,
            "processStartedAtUtc": S,
            "processMonotonicOriginMs": {"const": 0},
            "appVersion": S,
            "gitRevision": NULLABLE_S,
            "platform": S,
            "broadcastEpoch": NULLABLE_N0,
            "streamEpoch": NULLABLE_N0,
            "fileOrdinal": N0,
            "openedAtUtc": S,
            "catalogVersion": ID,
            "catalogHash": HASH,
            "desiredConfigGeneration": N0,
            "desiredConfigHash": HASH,
            "effectiveConfigHash": HASH,
            "configApplySequence": N0,
            "effectiveConfigProjection": arr(
                {"$ref": "#/$defs/EffectiveConfigProjectionEntry"}, 1, 128
            ),
            "enabledPurposeChannels": arr(enum(*purpose_channels), 1, 3),
            "redactionPolicy": {"$ref": "#/$defs/RedactionPolicy"},
            "historyComplete": BOOL,
            "detectorParameterSnapshots": arr(
                {"$ref": "#/$defs/DetectorParameterSnapshot"}, 0, 128
            ),
            "previousFileHash": nullable(HASH),
        },
    )
    defs["TapeRecord"] = closed(
        "narrative-tape-record/2",
        {
            "recordId": ID,
            "recordType": enum(*tape_record_types),
            "processInstanceId": ID,
            "broadcastEpoch": NULLABLE_N0,
            "streamEpoch": NULLABLE_N0,
            "reducerSequence": NULLABLE_N0,
            "recordedMonoMs": N0,
            "recordedAtUtc": NULLABLE_S,
            "purposeChannel": enum(*purpose_channels),
            "recordPriority": enum(*record_priorities),
            "tapeChannel": NULLABLE_ID,
            "correlationIds": id_list(0, 8),
            "effectiveConfigHash": HASH,
            "configApplySequence": N0,
            "payloadSchemaVersion": SCHEMA_VERSION,
            "payload": any_obj,
        },
    )
    typed_tape_payloads = {
        "context_applied": ("context-applied/2", "ContextApplied"),
        "feature_frame": ("feature-frame/2", "FeatureFrame"),
        "detector_observation": ("detector-observation/2", "DetectorObservation"),
        "event_candidate": ("event-candidate-tap/2", "EventCandidateTap"),
        "narrative_event": ("narrative-event/2", "NarrativeEvent"),
        "fact_change": ("fact-change/2", "FactChange"),
        "episode_change": ("episode-change/2", "EpisodeChange"),
        "opportunity_change": ("opportunity-change/2", "OpportunityChange"),
        "director_decision": ("director-decision/2", "DirectorDecision"),
        "llm_attempt": ("llm-attempt/2", "LlmAttempt"),
        "speech_exposure": ("speech-exposure/2", "SpeechExposure"),
        "config_applied": ("config-applied/2", "ConfigApplied"),
        "health_change": ("health-change/2", "HealthChange"),
        "mailbox_gap": ("mailbox-gap/2", "MailboxGap"),
        "drop_notice": ("drop-notice/2", "DropNotice"),
        "manifest_trailer": ("manifest-trailer/2", "ManifestTrailer"),
    }
    defs["TapeRecord"]["oneOf"] = [
        {
            "properties": {
                "recordType": {"const": record_type},
                "payloadSchemaVersion": {"const": schema_version},
                "payload": {"$ref": f"#/$defs/{definition}"},
            }
        }
        for record_type, (schema_version, definition) in typed_tape_payloads.items()
    ]
    for branch in defs["TapeRecord"]["oneOf"]:
        if branch["properties"]["recordType"].get("const") in {
            "config_applied",
            "health_change",
            "mailbox_gap",
            "drop_notice",
            "manifest_trailer",
        }:
            branch["properties"]["recordPriority"] = {"const": "critical"}
    unordered_tape_records = [
        "feature_frame",
        "detector_observation",
        "event_candidate",
        "config_applied",
        "drop_notice",
        "manifest_trailer",
    ]
    actor_ordered_tape_records = [
        "context_applied",
        "narrative_event",
        "fact_change",
        "episode_change",
        "opportunity_change",
        "director_decision",
        "llm_attempt",
        "speech_exposure",
        "health_change",
        "mailbox_gap",
    ]
    channel_required_tape_records = [
        "detector_observation",
        "event_candidate",
        "narrative_event",
        "opportunity_change",
        "director_decision",
    ]
    channel_optional_tape_records = [
        record_type
        for record_type in typed_tape_payloads
        if record_type not in channel_required_tape_records
    ]
    defs["TapeRecord"]["allOf"] = [
        {
            "oneOf": [
                {
                    "properties": {
                        "recordType": {"enum": unordered_tape_records},
                        "reducerSequence": {"type": "null"},
                    }
                },
                {
                    "properties": {
                        "recordType": {"enum": actor_ordered_tape_records},
                        "reducerSequence": N0,
                    }
                },
            ]
        },
        {
            "oneOf": [
                {
                    "properties": {
                        "recordType": {"enum": channel_required_tape_records},
                        "tapeChannel": ID,
                    }
                },
                {"properties": {"recordType": {"enum": channel_optional_tape_records}}},
            ]
        },
    ]
    defs["ApplyContextBatch"] = obj(
        {
            "timeline": {"$ref": "#/$defs/TimelineSnapshot"},
            "factView": {"$ref": "#/$defs/FactView"},
            "events": arr({"$ref": "#/$defs/NarrativeEvent"}, 0, 64),
        }
    )
    context_fields = {
        "timeline": {"$ref": "#/$defs/TimelineSnapshot"},
        "factView": {"$ref": "#/$defs/FactView"},
        "events": arr({"$ref": "#/$defs/NarrativeEvent"}, 0, 64),
    }
    defs["ContextApplied"] = closed("context-applied/2", context_fields)
    defs["FactChange"] = closed("fact-change/2", {"fact": {"$ref": "#/$defs/AtomicFact"}})
    defs["EpisodeChange"] = closed("episode-change/2", {"episode": {"$ref": "#/$defs/Episode"}})
    defs["OpportunityChange"] = closed(
        "opportunity-change/2", {"opportunity": {"$ref": "#/$defs/EventOpportunity"}}
    )
    defs["DirectorScore"] = obj(
        {
            "basePriority": NUM,
            "continuityBonus": NUM,
            "edgePreference": NUM,
            "closureUrgency": NUM,
            "materialChangeBonus": NUM,
            "silencePressure": NUM,
            "semanticFatiguePenalty": NUM,
            "patternFatiguePenalty": NUM,
            "lexicalRepetitionPenalty": NUM,
            "stalenessPenalty": NUM,
            "replacementCost": NUM,
            "eventPenalty": NUM,
            "final": NUM,
        }
    )
    defs["DirectorDecision"] = closed(
        "director-decision/2",
        {
            "streamEpoch": P1,
            "occurrenceId": NULLABLE_ID,
            "lineageId": NULLABLE_LINEAGE_ID,
            "episodeId": NULLABLE_ID,
            "episodeRevision": NULLABLE_N0,
            "triggerEvent": NULLABLE_ID,
            "tapeChannel": ID,
            "candidateSource": enum(
                "event_opportunity", "successor", "other_story", "filler", "silence"
            ),
            "candidateOrder": ORDER,
            "relation": nullable(
                enum(
                    "opens_episode",
                    "updates_active_episode",
                    "resolves_active_episode",
                    "continues_focused_episode",
                    "conflicts_with_focused_episode",
                    "independent_of_focused_episode",
                )
            ),
            "beatRole": enum("opening", "update", "outcome", "recap", "filler"),
            "eligible": BOOL,
            "score": {"$ref": "#/$defs/DirectorScore"},
            "requiredSwitchMargin": NUM,
            "selectedFactIds": id_list(0, 32),
            "realizationFamily": ID,
            "realizationPattern": ID,
            "realizationBackend": enum("authored", "qwen_compiled"),
            "promptOptions": {"$ref": "#/$defs/PromptOptions"},
            "generationMs": N0,
            "verification": enum("accepted", "rejected", "skipped"),
            "commit": enum("current", "stale", "skipped"),
            "speech": enum("completed", "interrupted", "failed", "not_started", "silence"),
        },
    )
    defs["HealthChange"] = closed(
        "health-change/2",
        {
            "scope": enum("tape", "component"),
            "status": enum("ready", "degraded", "unavailable"),
            "recorderGeneration": NULLABLE_N0,
            "affectedDetectorIds": id_list(0, 128),
            "firstLostSequence": NULLABLE_N0,
            "lastLostSequence": NULLABLE_N0,
            "component": nullable(enum("llm", "tts")),
            "generation": NULLABLE_N0,
            "reason": NULLABLE_S,
        },
    )
    defs["HealthChange"]["oneOf"] = [
        {
            "properties": {
                "scope": {"const": "tape"},
                "recorderGeneration": N0,
                "component": {"type": "null"},
                "generation": {"type": "null"},
            }
        },
        {
            "properties": {
                "scope": {"const": "component"},
                "component": enum("llm", "tts"),
                "generation": N0,
                "recorderGeneration": {"type": "null"},
                "affectedDetectorIds": {"maxItems": 0},
                "firstLostSequence": {"type": "null"},
                "lastLostSequence": {"type": "null"},
            }
        },
    ]
    defs["MailboxGap"] = closed(
        "mailbox-gap/2",
        {
            "latestTimeline": {"$ref": "#/$defs/TimelineSnapshot"},
            "latestFactView": {"$ref": "#/$defs/FactView"},
            "lossFirstMailboxSequence": N0,
            "lossLastMailboxSequence": N0,
            "historyComplete": {"const": False},
            "safetyEffects": arr(any_obj, 1, 64),
        },
    )
    defs["NarrativeCommand"] = closed(
        "narrative-command/2",
        {
            "commandId": ID,
            "kind": enum(
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
            ),
            "enqueuedMonoMs": N0,
            "mailboxSequence": N0,
            "externalOrder": nullable(any_obj),
            "contextRevision": nullable(any_obj),
            "token": nullable(any_obj),
            "payload": any_obj,
        },
    )
    command_payloads = {
        "APPLY_CONTEXT_BATCH": {"$ref": "#/$defs/ApplyContextBatch"},
        "CONFIG_UPDATE": obj(
            {
                "valid": BOOL,
                "ledger": nullable({"$ref": "#/$defs/ConfigLedger"}),
                "diagnostics": arr(any_obj, 0, 32),
            }
        ),
        "LONG_SILENCE_ELAPSED": obj({}),
        "VALIDITY_DEADLINE_ELAPSED": obj({}),
        "REALIZATION_SUCCEEDED": {"$ref": "#/$defs/RealizationResult"},
        "REALIZATION_FAILED": {"$ref": "#/$defs/RealizationResult"},
        "REALIZATION_DEADLINE_ELAPSED": obj({}),
        "PLAYBACK_ACCEPTED": {"$ref": "#/$defs/TtsCallback"},
        "SPEECH_COMPLETED": {"$ref": "#/$defs/TtsCallback"},
        "SPEECH_INTERRUPTED": {"$ref": "#/$defs/TtsCallback"},
        "SPEECH_FAILED": {"$ref": "#/$defs/TtsCallback"},
        "SPEECH_DEADLINE_ELAPSED": obj({}),
        "MANUAL_SPEAK_REQUEST": obj(
            {
                "text": {"type": "string", "minLength": 1, "maxLength": 400},
                "language": {"const": "en"},
            }
        ),
        "TAPE_HEALTH_CHANGED": obj(
            {
                "recorderGeneration": N0,
                "status": enum("ready", "degraded", "unavailable"),
                "affectedDetectorIds": id_list(0, 128),
                "firstLostSequence": NULLABLE_N0,
                "lastLostSequence": NULLABLE_N0,
            }
        ),
        "COMPONENT_HEALTH_CHANGED": obj(
            {
                "component": enum("llm", "tts"),
                "generation": N0,
                "status": enum("ready", "degraded", "unavailable"),
                "reason": NULLABLE_S,
            }
        ),
        "MAILBOX_RECOVERY": obj(
            {
                "latestTimeline": {"$ref": "#/$defs/TimelineSnapshot"},
                "latestFactView": {"$ref": "#/$defs/FactView"},
                "lossFirstMailboxSequence": N0,
                "lossLastMailboxSequence": N0,
                "historyComplete": {"const": False},
                "safetyEffects": arr(any_obj, 1, 64),
            }
        ),
        "SHUTDOWN": obj({"reason": ID, "requestedMonoMs": N0}),
    }
    deadline_token = obj({"generation": N0, "deadlineMonoMs": N0})
    realization_token = obj({"requestId": ID, "requestOrdinal": P1, "dispatchGeneration": P1})
    realization_deadline_token = obj({**realization_token["properties"], "deadlineMonoMs": N0})
    tts_token = obj(
        {
            "utteranceId": ID,
            "utteranceOrdinal": P1,
            "backendGeneration": P1,
            "dispatchGeneration": P1,
        }
    )
    speech_deadline_token = obj(
        {
            **tts_token["properties"],
            "stage": enum("start", "playback", "stop"),
            "deadlineMonoMs": N0,
        }
    )
    manual_token = obj({"manualRequestId": ID, "admissionOrdinal": P1})
    token_by_kind = {
        "LONG_SILENCE_ELAPSED": deadline_token,
        "VALIDITY_DEADLINE_ELAPSED": deadline_token,
        "REALIZATION_SUCCEEDED": realization_token,
        "REALIZATION_FAILED": realization_token,
        "REALIZATION_DEADLINE_ELAPSED": realization_deadline_token,
        "PLAYBACK_ACCEPTED": tts_token,
        "SPEECH_COMPLETED": tts_token,
        "SPEECH_INTERRUPTED": tts_token,
        "SPEECH_FAILED": tts_token,
        "SPEECH_DEADLINE_ELAPSED": speech_deadline_token,
        "MANUAL_SPEAK_REQUEST": manual_token,
    }
    external_order = obj(
        {
            "fanoutStreamSequence": P1,
            "firstSourceOrdinal": NULLABLE_N0,
            "lastSourceOrdinal": NULLABLE_N0,
        }
    )
    context_revision = obj({"timelineRevision": N0, "factViewRevision": N0})
    command_branches = []
    for kind, payload in command_payloads.items():
        contextual = kind in {"APPLY_CONTEXT_BATCH", "MAILBOX_RECOVERY"}
        command_branches.append(
            {
                "properties": {
                    "kind": {"const": kind},
                    "payload": payload,
                    "token": token_by_kind.get(kind, {"type": "null"}),
                    "externalOrder": external_order if contextual else {"type": "null"},
                    "contextRevision": context_revision if contextual else {"type": "null"},
                }
            }
        )
    defs["NarrativeCommand"]["oneOf"] = command_branches
    semantic_invariants = {
        "SessionPlan": ["valid_shape", "canonical_stage_order", "immutable_prefix_per_run"],
        "TimelineSnapshot": ["session_identity_all_or_none", "transition_reason_canonical_order"],
        "FeatureFrame": ["values_sorted_by_feature_id", "identity_all_or_none"],
        "DetectorObservation": [
            "inclusive_frame_range_ordered",
            "registered_feature_units",
            "coverage_sorted_unique_by_bucket_start",
            "covered_duration_lte_bucket",
        ],
        "EventCandidateTap": ["source_provenance_union", "candidate_id_canonical_content"],
        "NarrativeEvent": ["delivery_class_derived", "facts_resolve_same_view_identity"],
        "AtomicFact": ["valid_until_gte_valid_from", "registered_predicate_attributes_scope"],
        "FactView": ["facts_sorted_unique", "fact_observed_lte_view_created"],
        "Episode": ["opened_lte_updated_lte_resolved", "scope_identity_contract"],
        "EventOpportunity": ["expires_gt_created", "funnel_identity_monotonic"],
        "BeatPlan": [
            "expires_gt_planned",
            "selected_facts_equal_claim_union",
            "funnel_identity_monotonic",
        ],
        "RealizationBundle": ["binding_ids_equal_selected_facts", "canonical_hashes_match"],
        "CompiledPrompt": [
            "utf8_byte_counts_match",
            "combined_bytes_lte_32768",
            "canonical_hashes_match",
        ],
        "RealizationRequest": [
            "deadline_gt_dispatched",
            "backend_request_discriminated",
            "canonical_hash_matches",
        ],
        "RealizationResult": [
            "monotonic_time_order",
            "server_usage_all_or_none_and_sums",
            "canonical_hash_matches",
        ],
        "LlmAttempt": ["latency_equations_match_milestones", "capture_policy_projection"],
        "TtsUtterance": [
            "backend_steps_contract",
            "funnel_identity_monotonic",
            "canonical_hashes_match",
        ],
        "TtsCallback": ["callback_id_matches_sequence", "worker_sequence_protocol"],
        "SpeechExposure": [
            "accepted_consumption_weight_contract",
            "terminal_gte_dispatch",
            "callback_ids_ordered",
        ],
        "ConfigLedger": ["pending_sorted_and_matches_diff", "hashes_match_full_values"],
        "TapeManifest": [
            "file_scope_single_stream",
            "parameter_snapshots_sorted",
            "redaction_full_prompt_requires_llm_eval",
        ],
        "TapeRecord": ["priority_derived", "payload_matches_record_type", "config_pair_coherent"],
        "ApplyContextBatch": ["projection_revisions_coherent", "event_source_order_partition"],
        "NarrativeCommand": ["context_fields_match_payload", "mailbox_sequence_total_order"],
    }
    for name, invariants in semantic_invariants.items():
        defs[name]["x-irswitch-invariants"] = invariants
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://irswitch.local/schema/v2/dto-contracts.schema.json",
        "title": "iRSwitch v2 frozen narrative DTO contracts",
        "oneOf": [{"$ref": f"#/$defs/{name}"} for name in defs],
        "$defs": defs,
    }


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def schema_errors(
    value: Any, schema: dict[str, Any], root: dict[str, Any], path: str = "$"
) -> list[str]:
    if "$ref" in schema:
        prefix = "#/$defs/"
        ref = schema["$ref"]
        if not ref.startswith(prefix) or ref[len(prefix) :] not in root["$defs"]:
            return [f"{path}: unresolved ref {ref}"]
        return schema_errors(value, root["$defs"][ref[len(prefix) :]], root, path)
    errors: list[str] = []
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: expected const {schema['const']!r}")
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value outside enum")
    expected = schema.get("type")
    if expected is not None:
        allowed = expected if isinstance(expected, list) else [expected]
        checks = {
            "null": value is None,
            "boolean": isinstance(value, bool),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "string": isinstance(value, str),
            "array": isinstance(value, list),
            "object": isinstance(value, dict),
        }
        if not any(checks[item] for item in allowed):
            return [f"{path}: expected type {allowed}"]
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0) or len(value) > schema.get(
            "maxLength", sys.maxsize
        ):
            errors.append(f"{path}: string length out of range")
        if "pattern" in schema and re.fullmatch(schema["pattern"], value) is None:
            errors.append(f"{path}: pattern mismatch")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: above maximum")
        if "exclusiveMinimum" in schema and value <= schema["exclusiveMinimum"]:
            errors.append(f"{path}: below exclusive minimum")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0) or len(value) > schema.get(
            "maxItems", sys.maxsize
        ):
            errors.append(f"{path}: item count out of range")
        if schema.get("uniqueItems") and len({canonical(item) for item in value}) != len(value):
            errors.append(f"{path}: duplicate array item")
        if "items" in schema:
            for index, item in enumerate(value):
                errors.extend(schema_errors(item, schema["items"], root, f"{path}[{index}]"))
    if isinstance(value, dict):
        required = schema.get("required", [])
        errors.extend(f"{path}: missing {name}" for name in required if name not in value)
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            errors.extend(f"{path}: unknown {name}" for name in value if name not in properties)
        for name, subschema in properties.items():
            if name in value:
                errors.extend(schema_errors(value[name], subschema, root, f"{path}.{name}"))
    for subschema in schema.get("allOf", []):
        errors.extend(schema_errors(value, subschema, root, path))
    if "oneOf" in schema:
        matches = sum(not schema_errors(value, branch, root, path) for branch in schema["oneOf"])
        if matches != 1:
            errors.append(f"{path}: expected exactly one oneOf match, got {matches}")
    if "not" in schema and not schema_errors(value, schema["not"], root, path):
        errors.append(f"{path}: forbidden schema matched")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--emit", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    generated = build_schema()
    if generated.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        raise ValueError("wrong JSON Schema dialect")
    if args.emit:
        print(json.dumps(generated, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    if args.write:
        OUT.write_text(
            json.dumps(generated, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {OUT.name}")
        return 0
    checked = json.loads(OUT.read_text(encoding="utf-8"))
    if canonical(generated) != canonical(checked):
        print("dto-contracts.schema.json is stale", file=sys.stderr)
        return 1
    fixture_set = json.loads(GOLDENS.read_text(encoding="utf-8"))
    for row in fixture_set["valid"]:
        errors = schema_errors(row["value"], checked, checked)
        if errors:
            raise ValueError(f"valid golden {row['id']} rejected: {errors[0]}")
    for row in fixture_set["invalid"]:
        if not schema_errors(row["value"], checked, checked):
            raise ValueError(f"invalid golden {row['id']} accepted")
    print(
        f"DTO schemas OK: {len(checked['$defs'])} definitions, {len(fixture_set['valid'])} valid + {len(fixture_set['invalid'])} invalid goldens"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
