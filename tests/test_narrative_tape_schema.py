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
            "properties": {"redacted": {"type": "null"}},
        },
        {
            "required": ["key", "redacted"],
            "properties": {"redacted": {"const": True}},
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
