"""Executable schema acceptance for NarrativeTape framing envelopes."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

from irswitch.contracts.resources import packaged_schema_bytes

ROOT = Path(__file__).resolve().parents[1]
FROZEN_MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
SCHEMA = json.loads(packaged_schema_bytes("dto-contracts.schema.json"))
GOLDENS = json.loads((FROZEN_MACHINE / "dto-schema-goldens.json").read_text(encoding="utf-8"))
FILE_HASH = "sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"

_BUILDER = importlib.util.spec_from_file_location(
    "v2_build_dto_schemas", FROZEN_MACHINE / "build_dto_schemas.py"
)
assert _BUILDER is not None and _BUILDER.loader is not None
_dto_builder = importlib.util.module_from_spec(_BUILDER)
_BUILDER.loader.exec_module(_dto_builder)


def _golden(fixture_id: str, group: str) -> dict:
    for row in GOLDENS[group]:
        if row["id"] == fixture_id:
            return row["value"]
    raise AssertionError(f"missing {group} golden {fixture_id}")


def _errors(value: object) -> list[str]:
    return _dto_builder.schema_errors(value, SCHEMA, SCHEMA)


def test_tape_manifest_uses_exact_projection_and_detector_snapshot_shapes() -> None:
    definitions = SCHEMA["$defs"]
    manifest = definitions["TapeManifest"]

    assert manifest["properties"]["effectiveConfigProjection"]["items"] == {
        "$ref": "#/$defs/EffectiveConfigProjectionEntry"
    }
    assert manifest["properties"]["detectorParameterSnapshots"]["items"] == {
        "$ref": "#/$defs/DetectorParameterSnapshot"
    }
    assert definitions["EffectiveConfigProjectionEntry"]["oneOf"] == [
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
    assert definitions["DetectorParameterSnapshot"]["required"] == [
        "parameterSnapshotId",
        "detectorId",
        "detectorVersion",
        "detectorConfigHash",
        "parameters",
    ]


def test_tape_record_type_is_closed_and_known_payloads_are_discriminated() -> None:
    record = SCHEMA["$defs"]["TapeRecord"]

    assert record["properties"]["recordType"]["enum"] == [
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
    branches = {
        branch["properties"]["recordType"]["const"]: branch["properties"]
        for branch in record["oneOf"]
        if "const" in branch["properties"]["recordType"]
    }
    assert branches["feature_frame"]["payload"] == {"$ref": "#/$defs/FeatureFrame"}
    assert branches["detector_observation"]["payload"] == {"$ref": "#/$defs/DetectorObservation"}
    assert branches["event_candidate"]["payload"] == {"$ref": "#/$defs/EventCandidateTap"}
    assert branches["narrative_event"]["payload"] == {"$ref": "#/$defs/NarrativeEvent"}
    assert branches["llm_attempt"]["payload"] == {"$ref": "#/$defs/LlmAttempt"}
    assert branches["speech_exposure"]["payload"] == {"$ref": "#/$defs/SpeechExposure"}
    assert branches["context_applied"]["payload"] == {"$ref": "#/$defs/ContextApplied"}
    assert branches["fact_change"]["payload"] == {"$ref": "#/$defs/FactChange"}
    assert branches["episode_change"]["payload"] == {"$ref": "#/$defs/EpisodeChange"}
    assert branches["opportunity_change"]["payload"] == {"$ref": "#/$defs/OpportunityChange"}
    assert branches["director_decision"]["payload"] == {"$ref": "#/$defs/DirectorDecision"}
    assert branches["health_change"]["payload"] == {"$ref": "#/$defs/HealthChange"}
    assert branches["mailbox_gap"]["payload"] == {"$ref": "#/$defs/MailboxGap"}
    assert SCHEMA["$defs"]["ContextApplied"]["properties"]["schemaVersion"]["const"] == (
        "context-applied/2"
    )
    assert SCHEMA["$defs"]["FactChange"]["properties"]["fact"] == {"$ref": "#/$defs/AtomicFact"}
    assert SCHEMA["$defs"]["EpisodeChange"]["properties"]["episode"] == {"$ref": "#/$defs/Episode"}
    assert SCHEMA["$defs"]["OpportunityChange"]["properties"]["opportunity"] == {
        "$ref": "#/$defs/EventOpportunity"
    }
    assert SCHEMA["$defs"]["DirectorDecision"]["properties"]["schemaVersion"]["const"] == (
        "director-decision/2"
    )
    assert SCHEMA["$defs"]["HealthChange"]["properties"]["schemaVersion"]["const"] == (
        "health-change/2"
    )
    assert SCHEMA["$defs"]["MailboxGap"]["properties"]["historyComplete"] == {"const": False}


def test_tape_record_enforces_reducer_order_and_tape_channel_boundaries() -> None:
    record = SCHEMA["$defs"]["TapeRecord"]

    reducer_order = record["allOf"][0]["oneOf"]
    assert reducer_order == [
        {
            "properties": {
                "recordType": {
                    "enum": [
                        "feature_frame",
                        "detector_observation",
                        "event_candidate",
                        "config_applied",
                        "drop_notice",
                        "manifest_trailer",
                    ]
                },
                "reducerSequence": {"type": "null"},
            }
        },
        {
            "properties": {
                "recordType": {
                    "enum": [
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
                },
                "reducerSequence": {"type": "integer", "minimum": 0},
            }
        },
    ]
    tape_channel = record["allOf"][1]["oneOf"]
    assert tape_channel[0]["properties"]["recordType"]["enum"] == [
        "detector_observation",
        "event_candidate",
        "narrative_event",
        "opportunity_change",
        "director_decision",
    ]
    assert tape_channel[0]["properties"]["tapeChannel"] == {
        "type": "string",
        "pattern": "^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$",
    }
    assert "tapeChannel" not in tape_channel[1]["properties"]


def test_config_applied_payload_is_exact_and_replay_safe() -> None:
    definitions = SCHEMA["$defs"]
    payload = definitions["ConfigApplied"]

    assert payload["required"] == [
        "schemaVersion",
        "applySequence",
        "desiredGeneration",
        "boundary",
        "changedKeys",
        "effectivePatch",
        "oldEffectiveHash",
        "newEffectiveHash",
    ]
    assert payload["additionalProperties"] is False
    assert payload["properties"]["effectivePatch"]["items"] == {
        "$ref": "#/$defs/EffectiveConfigProjectionEntry"
    }
    config_branch = next(
        branch
        for branch in definitions["TapeRecord"]["oneOf"]
        if branch["properties"]["recordType"].get("const") == "config_applied"
    )
    assert config_branch["properties"]["payloadSchemaVersion"] == {"const": "config-applied/2"}
    assert config_branch["properties"]["payload"] == {"$ref": "#/$defs/ConfigApplied"}


def test_loss_notice_and_manifest_trailer_are_bounded_exact_payloads() -> None:
    definitions = SCHEMA["$defs"]

    loss = definitions["TapeLossAccumulator"]
    assert loss["additionalProperties"] is False
    assert loss["properties"]["buckets"]["maxItems"] == 192
    assert loss["properties"]["configTransitions"]["maxItems"] == 128
    assert loss["x-irswitch-invariants"] == [
        "buckets_sorted_unique_by_type_priority_reason",
        "loss_time_range_ordered",
        "loss_reducer_range_both_or_neither_ordered",
        "config_transitions_sorted_unique",
    ]

    trailer = definitions["ManifestTrailer"]
    assert trailer["additionalProperties"] is False
    assert trailer["properties"]["recordCounts"]["maxItems"] == 16
    assert trailer["properties"]["purposeCounts"]["maxItems"] == 3
    assert trailer["properties"]["tapeChannelCounts"]["maxItems"] == 36
    assert trailer["properties"]["lossAccumulator"] == {
        "oneOf": [
            {"$ref": "#/$defs/TapeLossAccumulator"},
            {"type": "null"},
        ]
    }

    record_branches = {
        branch["properties"]["recordType"].get("const"): branch["properties"]
        for branch in definitions["TapeRecord"]["oneOf"]
    }
    assert record_branches["drop_notice"]["payload"] == {"$ref": "#/$defs/DropNotice"}
    assert record_branches["manifest_trailer"]["payload"] == {"$ref": "#/$defs/ManifestTrailer"}


def test_loss_trailer_goldens_cover_clean_loss_range_and_hash_chain() -> None:
    unordered = _golden("drop-notice-unordered-loss", "valid")
    actor = _golden("drop-notice-actor-loss", "valid")
    clean = _golden("manifest-trailer-clean", "valid")
    lost = _golden("manifest-trailer-with-loss", "valid")
    drop_record = _golden("tape-drop-notice-record", "valid")
    trailer_record = _golden("tape-trailer-record", "valid")
    continuation = _golden("tape-continuation-manifest", "valid")

    for value in (unordered, actor, clean, lost, drop_record, trailer_record, continuation):
        assert _errors(value) == []

    assert unordered["loss"]["firstLostReducerSequence"] is None
    assert unordered["loss"]["lastLostReducerSequence"] is None
    assert actor["loss"]["firstLostReducerSequence"] == 10
    assert actor["loss"]["lastLostReducerSequence"] == 12
    assert clean["complete"] is True
    assert clean["lossAccumulator"] is None
    assert clean["fileHash"] == FILE_HASH
    assert lost["complete"] is False
    assert lost["lossAccumulator"]["buckets"]
    assert drop_record["recordType"] == "drop_notice"
    assert drop_record["reducerSequence"] is None
    assert drop_record["recordPriority"] == "critical"
    assert trailer_record["recordType"] == "manifest_trailer"
    assert trailer_record["payload"]["fileHash"] == FILE_HASH
    assert continuation["previousFileHash"] == FILE_HASH
    assert continuation["previousFileHash"] == clean["fileHash"]


def test_loss_trailer_invalid_goldens_reject_pairing_completeness_and_order() -> None:
    invalid_ids = (
        "drop-notice-one-sided-reducer-range",
        "manifest-trailer-complete-with-loss",
        "manifest-trailer-complete-write-failed",
        "tape-drop-notice-with-reducer-order",
        "tape-drop-notice-normal-priority",
    )
    for fixture_id in invalid_ids:
        assert _errors(_golden(fixture_id, "invalid")), fixture_id

    reversed_range = _golden("drop-notice-actor-loss", "valid")["loss"]
    assert reversed_range["firstLostReducerSequence"] <= reversed_range["lastLostReducerSequence"]
    assert reversed_range["firstLostMonoMs"] <= reversed_range["lastLostMonoMs"]


def test_remaining_tape_payload_goldens_wrap_existing_truth_dtos() -> None:
    valid_ids = (
        "context-applied-batch",
        "fact-change-active",
        "episode-change-active",
        "opportunity-change-pending",
        "director-decision-event",
        "health-change-tape",
        "mailbox-gap-recovery",
        "tape-health-record",
    )
    for fixture_id in valid_ids:
        assert _errors(_golden(fixture_id, "valid")) == [], fixture_id

    context = _golden("context-applied-batch", "valid")
    assert set(context) == {"schemaVersion", "timeline", "factView", "events"}
    assert context["timeline"]["schemaVersion"] == "timeline-snapshot/2"
    assert context["factView"]["schemaVersion"] == "fact-view/2"
    assert _golden("fact-change-active", "valid")["fact"]["schemaVersion"] == "atomic-fact/2"
    assert _golden("episode-change-active", "valid")["episode"]["schemaVersion"] == "episode/2"
    assert (
        _golden("opportunity-change-pending", "valid")["opportunity"]["schemaVersion"]
        == "event-opportunity/2"
    )
    assert _golden("mailbox-gap-recovery", "valid")["historyComplete"] is False

    invalid_ids = (
        "health-change-mixed-scope",
        "mailbox-gap-history-complete",
        "director-decision-unknown-relation",
    )
    for fixture_id in invalid_ids:
        assert _errors(_golden(fixture_id, "invalid")), fixture_id


def test_feature_frame_and_observation_rows_are_exact() -> None:
    definitions = SCHEMA["$defs"]
    assert definitions["FeatureFrame"]["properties"]["values"]["items"] == {
        "$ref": "#/$defs/FeatureValue"
    }
    assert definitions["DetectorObservation"]["properties"]["windowFrameRange"] == {
        "oneOf": [{"$ref": "#/$defs/WindowFrameRange"}, {"type": "null"}]
    }
    assert definitions["DetectorObservation"]["properties"]["featureValues"]["items"] == {
        "$ref": "#/$defs/FeatureValue"
    }
    assert definitions["DetectorObservation"]["properties"]["predicateResults"]["items"] == {
        "$ref": "#/$defs/PredicateResult"
    }
    assert definitions["FeatureValue"]["required"] == [
        "featureId",
        "value",
        "unit",
        "quality",
        "observedMonoMs",
        "validUntilMonoMs",
        "evidenceRefs",
    ]
    assert definitions["WindowFrameRange"]["required"] == [
        "firstFrameSequence",
        "lastFrameSequence",
        "postWindowComplete",
    ]
    assert definitions["PredicateResult"]["properties"]["result"]["enum"] == [
        True,
        False,
        "unknown",
    ]

    for fixture_id in (
        "feature-frame-measured-gap",
        "detector-observation-windowed",
    ):
        assert _errors(_golden(fixture_id, "valid")) == [], fixture_id

    frame = _golden("feature-frame-measured-gap", "valid")
    assert frame["values"][0]["featureId"] == "gap.relation.seconds.estimated_v1"
    window = _golden("detector-observation-windowed", "valid")["windowFrameRange"]
    assert window["firstFrameSequence"] == 200
    assert window["lastFrameSequence"] == 214
    assert window["postWindowComplete"] is True

    for fixture_id in (
        "feature-frame-value-without-evidence",
        "detector-window-zero-sequence",
        "predicate-result-unknown-token",
    ):
        assert _errors(_golden(fixture_id, "invalid")), fixture_id


def test_coverage_bucket_and_redaction_policy_are_exact() -> None:
    definitions = SCHEMA["$defs"]
    assert definitions["DetectorObservation"]["properties"]["coverage"]["items"] == {
        "$ref": "#/$defs/CoverageBucket"
    }
    assert definitions["TapeManifest"]["properties"]["redactionPolicy"] == {
        "$ref": "#/$defs/RedactionPolicy"
    }
    assert definitions["CoverageBucket"]["required"] == [
        "bucketStartMonoMs",
        "bucketDurationS",
        "coveredDurationS",
        "sampleCount",
        "usable",
    ]
    assert definitions["RedactionPolicy"] == {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "sensitiveValues": {"const": "marker_only"},
            "prompt": {"enum": ["none", "hash", "full"]},
            "completion": {"type": "boolean"},
        },
        "required": ["sensitiveValues", "prompt", "completion"],
    }

    observation = _golden("detector-observation-windowed", "valid")
    assert _errors(observation) == []
    assert observation["coverage"][0] == {
        "bucketStartMonoMs": 1000,
        "bucketDurationS": 1.0,
        "coveredDurationS": 0.25,
        "sampleCount": 1,
        "usable": False,
    }
    manifest = _golden("tape-manifest-framing", "valid")
    assert _errors(manifest) == []
    assert manifest["redactionPolicy"] == {
        "sensitiveValues": "marker_only",
        "prompt": "hash",
        "completion": True,
    }

    for fixture_id in (
        "detector-coverage-zero-bucket",
        "redaction-policy-plaintext-sensitive",
    ):
        assert _errors(_golden(fixture_id, "invalid")), fixture_id
