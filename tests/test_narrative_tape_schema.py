"""Executable schema acceptance for NarrativeTape framing envelopes."""

from __future__ import annotations

import json

from irswitch.contracts.resources import packaged_schema_bytes

SCHEMA = json.loads(packaged_schema_bytes("dto-contracts.schema.json"))


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
