#!/usr/bin/env python3
"""Build and validate the frozen v2 public configuration contract and goldens."""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import math
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from build_dto_schemas import canonical, schema_errors

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / "docs" / "v2.0.0"
PUBLIC_DOC = DOCS / "public-contracts.md"
REGISTRY_PATH = Path(__file__).with_name("freeze-registry.json")
CONTRACT_PATH = Path(__file__).with_name("config-contract.json")
SCHEMA_PATH = Path(__file__).with_name("config-contract.schema.json")
GOLDENS_PATH = Path(__file__).with_name("config-goldens.json")

CONFIG_HEADINGS = ["### Root and director", "### LLM and TTS", "### Detectors and tape"]
BOUNDARY_OWNERS = {
    "command": "stream_config_coordinator",
    "next_stream": "stream_config_coordinator",
    "next_plan_or_manual": "narrative_actor",
    "next_beat_plan": "narrative_actor",
    "next_director_pass": "narrative_actor",
    "next_silence_deadline": "narrative_actor",
    "next_request": "narrative_actor",
    "next_utterance": "narrative_actor",
    "next_cancellation": "narrative_actor",
    "next_record": "tape_writer",
    "next_rotated_file": "tape_writer",
    "next_rotation": "tape_writer",
    "next_writer_deadline": "tape_writer",
    "next_shutdown": "composition_root",
}
SENSITIVE_KEYS = {
    "commentary.driver_name",
    "commentary.driver_nickname",
    "commentary.llm.base_url",
    "commentary.tts.voice",
    "commentary.tts.audio_device",
    "commentary.tts.duck_input",
    "commentary.tape.output_dir",
}
PREFLIGHT_KEYS = {
    "commentary.llm.enabled": "llm",
    "commentary.llm.base_url": "llm",
    "commentary.llm.model": "llm",
    "commentary.llm.warmup": "llm",
    "commentary.tts.backend": "tts",
    "commentary.tts.voice": "tts",
    "commentary.tts.steps": "tts",
    "commentary.tts.audio_device": "tts",
}
EXPECTED_STATIC_KEYS = 50
EXPECTED_TEMPLATE_KEYS = 2


def _clean(cell: str) -> str:
    return cell.strip().replace("`", "")


def _table(heading: str) -> list[list[str]]:
    lines = PUBLIC_DOC.read_text(encoding="utf-8").splitlines()
    start = lines.index(heading) + 1
    rows: list[list[str]] = []
    entered = False
    for line in lines[start:]:
        if line.startswith("|"):
            cells = [_clean(cell) for cell in line.strip().strip("|").split("|")]
            if cells and cells[0] not in {"Key", "v1 key"} and not cells[0].startswith("---"):
                rows.append(cells)
            entered = True
        elif entered and line.strip():
            break
    return rows


def _value_type(raw: str) -> str:
    return {
        "bool": "boolean",
        "float": "number",
        "int": "integer",
        "string": "string",
        "enum": "enum",
        "URL": "url",
        "path": "path",
        "enum set": "enum_set",
        "string set": "string_set",
        "catalog typed": "catalog_typed",
    }[raw]


def _literal(raw: str, value_type: str) -> Any:
    if raw == "catalog value":
        return None
    if raw == "empty":
        return [] if value_type.endswith("_set") else ""
    if value_type == "boolean":
        return raw == "true"
    if value_type == "integer":
        return int(raw)
    if value_type == "number":
        return float(raw)
    if value_type.endswith("_set"):
        return [item.strip() for item in raw.split(",")]
    return raw


def _constraints(value_type: str, allowed: str) -> dict[str, Any]:
    result: dict[str, Any] = {"normativeAllowed": allowed}
    numeric = re.fullmatch(r"(-?\d+(?:\.\d+)?)–(-?\d+(?:\.\d+)?)", allowed)
    length = re.match(r"(\d+)–(\d+).*chars", allowed)
    if numeric and value_type in {"integer", "number"}:
        cast = int if value_type == "integer" else float
        result.update(minimum=cast(numeric.group(1)), maximum=cast(numeric.group(2)))
    elif length and value_type == "string":
        result.update(minLength=int(length.group(1)), maxLength=int(length.group(2)))
    elif value_type == "enum":
        result["values"] = [item.strip() for item in allowed.split(",")]
    elif value_type == "enum_set":
        match = re.search(r"subset of (.+)", allowed)
        result["values"] = [item.strip() for item in match.group(1).split(",")]
        result["unique"] = True
    elif value_type == "url":
        result["policy"] = "local_lan_v1_base_url"
    elif value_type == "path":
        result["policy"] = "safe_non_root_output_path"
    elif value_type == "string_set":
        result["unique"] = True
        if "channel" in allowed:
            registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
            result["values"] = ["*", *registry["tapeChannels"]]
        else:
            result["reference"] = "exported_detector_ids"
    elif value_type == "catalog_typed":
        result["reference"] = "exported_detector_parameter_contract"
    return result


def _definition(row: list[str]) -> dict[str, Any]:
    key, raw_type, raw_default, allowed, unit, raw_boundary = row
    value_type = _value_type(raw_type)
    boundary, _, boundary_note = raw_boundary.partition(";")
    boundary = boundary.strip()
    return {
        "key": key,
        "keyClass": "template" if "<" in key else "static",
        "valueType": value_type,
        "default": _literal(raw_default, value_type),
        "defaultSource": "catalog" if raw_default == "catalog value" else "literal",
        "constraints": _constraints(value_type, allowed),
        "unit": None if unit == "—" else unit,
        "applyBoundary": boundary,
        "boundaryOwner": BOUNDARY_OWNERS[boundary],
        "sensitive": key in SENSITIVE_KEYS,
        "preflightComponent": PREFLIGHT_KEYS.get(key),
        "boundaryNote": boundary_note.strip() or None,
    }


def _replacement_keys(source: str, result: str) -> list[str]:
    if source == "commentary.use_hr_emotion":
        return ["commentary.tone_source"]
    if source == "commentary.decision_log_size":
        return ["commentary.director.decision_capacity"]
    if source == "commentary.llm_polish":
        return ["commentary.llm.enabled"]
    if source == "commentary.llm_base_url/model/timeout_s/max_tokens":
        return [
            "commentary.llm.base_url",
            "commentary.llm.model",
            "commentary.llm.timeout_s",
            "commentary.llm.max_tokens",
        ]
    match = re.search(r"(commentary\.[a-z0-9_.]+)", result)
    return [match.group(1)] if match and not result.startswith("removed") else []


def build_contract() -> dict[str, Any]:
    definitions = [_definition(row) for heading in CONFIG_HEADINGS for row in _table(heading)]
    migrations = []
    for source, result in _table("### v1 migration table"):
        match_kind = (
            "section"
            if source.startswith("[")
            else "prefix" if "*" in source else "group" if "/" in source else "exact"
        )
        migrations.append(
            {
                "source": source,
                "matchKind": match_kind,
                "result": result,
                "replacementKeys": _replacement_keys(source, result),
                "runtimeAction": "reject_generation_with_legacy_key",
                "diagnosticReason": "legacy_key",
            }
        )
    static_defaults = {
        row["key"]: row["default"] for row in definitions if row["keyClass"] == "static"
    }
    boundary_order = list(BOUNDARY_OWNERS)
    return {
        "schemaVersion": "commentary-config-contract/2",
        "contractProjectionVersion": 1,
        "sourceBaseline": {
            "document": "docs/v2.0.0/public-contracts.md",
            "configurationHeadings": CONFIG_HEADINGS,
        },
        "keyDefinitions": definitions,
        "defaultConfig": static_defaults,
        "boundaries": [
            {"id": boundary, "owner": owner, "registryOrdinal": index}
            for index, (boundary, owner) in enumerate(BOUNDARY_OWNERS.items(), 1)
        ],
        "ledgerContract": {
            "installMode": "full_validated_candidate",
            "pendingRecomputedFromWholeDesiredMap": True,
            "applyOnlyNamedBoundary": True,
            "changedKeysSortedUnique": True,
            "noOpBoundaryEmitsRecord": False,
            "applySequenceMonotonic": True,
            "preflightStartsAtDesiredAcceptance": True,
            "preflightSuccessDoesNotStartWork": True,
            "noFallbackToOlderComponentGeneration": True,
            "invalidCandidateCreatesGeneration": False,
            "invalidCandidateDisablesAutomaticOnly": True,
            "sensitiveKeys": sorted(SENSITIVE_KEYS),
            "boundaryVocabulary": boundary_order,
        },
        "crossFieldInvariants": [
            "active_episode_capacity_lte_resolved_episode_capacity",
            "tape_channels_nonempty_when_enabled",
            "full_prompt_requires_llm_eval_channel",
            "output_path_not_filesystem_home_or_repository_root",
            "detector_overrides_resolve_exported_contract",
            "required_tuning_detector_requires_calibration_capture_preflight",
        ],
        "migrationContract": {
            "compatibilityLoader": False,
            "absentCommentarySectionEquivalent": {"commentary.enabled": False},
            "entries": migrations,
        },
    }


def _closed(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": properties,
        "required": required or list(properties),
    }


def build_schema() -> dict[str, Any]:
    any_json = {"type": ["null", "boolean", "integer", "number", "string", "array", "object"]}
    string_array = {"type": "array", "items": {"type": "string"}, "uniqueItems": True}
    definition = _closed(
        {
            "key": {"type": "string", "minLength": 1},
            "keyClass": {"enum": ["static", "template"]},
            "valueType": {
                "enum": [
                    "boolean",
                    "number",
                    "integer",
                    "string",
                    "enum",
                    "url",
                    "path",
                    "enum_set",
                    "string_set",
                    "catalog_typed",
                ]
            },
            "default": any_json,
            "defaultSource": {"enum": ["literal", "catalog"]},
            "constraints": {"type": "object"},
            "unit": {"type": ["string", "null"]},
            "applyBoundary": {"enum": list(BOUNDARY_OWNERS)},
            "boundaryOwner": {"enum": sorted(set(BOUNDARY_OWNERS.values()))},
            "sensitive": {"type": "boolean"},
            "preflightComponent": {"enum": ["llm", "tts", None]},
            "boundaryNote": {"type": ["string", "null"]},
        }
    )
    migration = _closed(
        {
            "source": {"type": "string"},
            "matchKind": {"enum": ["exact", "prefix", "group", "section"]},
            "result": {"type": "string"},
            "replacementKeys": string_array,
            "runtimeAction": {"const": "reject_generation_with_legacy_key"},
            "diagnosticReason": {"const": "legacy_key"},
        }
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://irswitch.local/contracts/v2/config-contract.schema.json",
        "title": "irswitch v2 public commentary configuration contract",
        **_closed(
            {
                "schemaVersion": {"const": "commentary-config-contract/2"},
                "contractProjectionVersion": {"const": 1},
                "sourceBaseline": _closed(
                    {
                        "document": {"const": "docs/v2.0.0/public-contracts.md"},
                        "configurationHeadings": {"const": CONFIG_HEADINGS},
                    }
                ),
                "keyDefinitions": {
                    "type": "array",
                    "minItems": 52,
                    "maxItems": 52,
                    "items": definition,
                },
                "defaultConfig": {"type": "object", "minProperties": 50, "maxProperties": 50},
                "boundaries": {
                    "type": "array",
                    "minItems": 14,
                    "maxItems": 14,
                    "items": _closed(
                        {
                            "id": {"enum": list(BOUNDARY_OWNERS)},
                            "owner": {"type": "string"},
                            "registryOrdinal": {
                                "type": "integer",
                                "minimum": 1,
                                "maximum": 14,
                            },
                        }
                    ),
                },
                "ledgerContract": {"type": "object"},
                "crossFieldInvariants": {
                    "type": "array",
                    "minItems": 6,
                    "uniqueItems": True,
                    "items": {"type": "string"},
                },
                "migrationContract": _closed(
                    {
                        "compatibilityLoader": {"const": False},
                        "absentCommentarySectionEquivalent": {
                            "const": {"commentary.enabled": False}
                        },
                        "entries": {
                            "type": "array",
                            "minItems": 13,
                            "maxItems": 13,
                            "items": migration,
                        },
                    }
                ),
            }
        ),
        "x-irswitch-invariants": [
            "config_rows_match_human_tables_exactly",
            "static_defaults_match_key_definitions",
            "config_key_ids_unique",
            "boundary_owner_mapping_complete",
            "sensitive_and_preflight_sets_exact",
            "migration_rows_match_human_table_exactly",
            "golden_config_values_and_cross_fields_validate",
            "mixed_boundary_ledger_replay_matches",
        ],
    }


def _validate_url(value: str) -> bool:
    parsed = urlsplit(value)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        return False
    try:
        port = parsed.port
    except ValueError:
        return False
    if port is not None and not 1 <= port <= 65535:
        return False
    path = re.sub(r"/+", "/", parsed.path or "")
    if path not in {"", "/", "/v1"} and not path.endswith("/v1"):
        return False
    if parsed.hostname == "localhost":
        return True
    try:
        address = ipaddress.ip_address(parsed.hostname or "")
    except ValueError:
        return False
    return address.is_loopback or address.is_private or address.is_link_local


def validate_values(values: dict[str, Any], contract: dict[str, Any]) -> None:
    definitions = {
        row["key"]: row for row in contract["keyDefinitions"] if row["keyClass"] == "static"
    }
    unknown = set(values) - set(definitions)
    if unknown:
        raise ValueError(f"unknown config key {sorted(unknown)[0]}")
    merged = {**contract["defaultConfig"], **values}
    for key, value in merged.items():
        definition = definitions[key]
        kind = definition["valueType"]
        ok = {
            "boolean": isinstance(value, bool),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "number": isinstance(value, (int, float))
            and not isinstance(value, bool)
            and math.isfinite(value),
            "string": isinstance(value, str),
            "enum": isinstance(value, str),
            "url": isinstance(value, str),
            "path": isinstance(value, str),
            "enum_set": isinstance(value, list),
            "string_set": isinstance(value, list),
        }[kind]
        if not ok:
            raise ValueError(f"{key}: invalid type")
        constraints = definition["constraints"]
        if (
            "minimum" in constraints
            and value < constraints["minimum"]
            or "maximum" in constraints
            and value > constraints["maximum"]
        ):
            raise ValueError(f"{key}: out of range")
        if (
            "minLength" in constraints
            and len(value) < constraints["minLength"]
            or "maxLength" in constraints
            and len(value) > constraints["maxLength"]
        ):
            raise ValueError(f"{key}: length out of range")
        if "values" in constraints:
            candidates = value if isinstance(value, list) else [value]
            if any(item not in constraints["values"] for item in candidates):
                raise ValueError(f"{key}: value outside enum")
        if isinstance(value, list) and len(value) != len(set(value)):
            raise ValueError(f"{key}: duplicate set member")
        if kind == "url" and not _validate_url(value):
            raise ValueError(f"{key}: URL outside local/LAN policy")
        if kind == "path":
            candidate = Path(value).expanduser()
            resolved = (
                candidate.resolve() if candidate.is_absolute() else (ROOT / candidate).resolve()
            )
            if resolved in {Path("/").resolve(), Path.home().resolve(), ROOT.resolve()}:
                raise ValueError(f"{key}: unsafe root path")
    if (
        merged["commentary.director.active_episode_capacity"]
        > merged["commentary.director.resolved_episode_capacity"]
    ):
        raise ValueError("active episode capacity exceeds resolved capacity")
    if merged["commentary.tape.enabled"] and not merged["commentary.tape.channels"]:
        raise ValueError("tape channels empty while enabled")
    if (
        merged["commentary.tape.llm_eval.capture_prompt"] == "full"
        and "llm_eval" not in merged["commentary.tape.channels"]
    ):
        raise ValueError("full prompt requires llm_eval channel")


def _hash(values: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(canonical(values).encode("utf-8")).hexdigest()


def _ledger_scenario(contract: dict[str, Any]) -> dict[str, Any]:
    definitions = {
        row["key"]: row for row in contract["keyDefinitions"] if row["keyClass"] == "static"
    }
    dynamic_key = "commentary.detector.battle_ahead_v1.max_closing_slope"
    initial = {**contract["defaultConfig"], dynamic_key: -0.04}
    generation7 = {
        **initial,
        "commentary.director.selection_threshold": 42.0,
        "commentary.max_utterance_s": 12.0,
        "commentary.tts.backend": "supertonic",
        "commentary.tts.voice": "golden-voice",
        dynamic_key: -0.05,
        "commentary.tape.detail": "full",
    }
    effective = initial.copy()
    apply_sequence = 20
    transitions = []
    for boundary in ("next_record", "next_director_pass", "next_plan_or_manual", "next_utterance"):
        keys = sorted(
            key
            for key in generation7
            if key in definitions
            and definitions[key]["applyBoundary"] == boundary
            and generation7[key] != effective[key]
        )
        old_hash = _hash(effective)
        for key in keys:
            effective[key] = generation7[key]
        apply_sequence += 1
        transitions.append(
            {
                "applySequence": apply_sequence,
                "desiredGeneration": 7,
                "boundary": boundary,
                "changedKeys": keys,
                "effectivePatch": [
                    (
                        {"key": key, "redacted": True}
                        if key in SENSITIVE_KEYS
                        else {"key": key, "value": effective[key]}
                    )
                    for key in keys
                ],
                "oldEffectiveHash": old_hash,
                "newEffectiveHash": _hash(effective),
            }
        )
    pending7 = [{"key": dynamic_key, "boundary": "next_stream", "desiredGeneration": 7}]
    generation8 = {**generation7, dynamic_key: -0.04}
    pending8 = []
    return {
        "id": "mixed_boundary_preflight_and_revert",
        "initialDesiredGeneration": 6,
        "initialEffectiveHash": _hash(initial),
        "acceptedDesiredGeneration": 7,
        "generation7DesiredHash": _hash(generation7),
        "changedKeys": sorted(key for key in generation7 if generation7[key] != initial[key]),
        "preflightsStarted": [{"component": "tts", "generation": 7, "status": "pending"}],
        "appliedTransitions": transitions,
        "pendingAfterAvailableBoundaries": pending7,
        "effectiveAfterAvailableBoundariesHash": _hash(effective),
        "firstGeneration7TtsAdmission": "component_unavailable_no_old_generation_fallback",
        "currentPreflightSuccessEffect": "later_normal_admission_only",
        "generation8DesiredHash": _hash(generation8),
        "pendingAfterGeneration8Revert": pending8,
        "invalidReloadEffect": "no_generation_disable_automatic_preserve_last_valid_manual_backend",
    }


def build_goldens(contract: dict[str, Any]) -> dict[str, Any]:
    return {
        "schemaVersion": "commentary-config-goldens/2",
        "valid": [
            {"id": "all_defaults", "values": contract["defaultConfig"]},
            {
                "id": "enabled_private_llm_full_capture",
                "values": {
                    "commentary.enabled": True,
                    "commentary.llm.base_url": "http://192.168.1.20:11434/v1",
                    "commentary.tape.enabled": True,
                    "commentary.tape.channels": ["flow", "llm_eval"],
                    "commentary.tape.llm_eval.capture_prompt": "full",
                },
            },
        ],
        "invalid": [
            {
                "id": "unknown_key",
                "values": {"commentary.magic": True},
                "errorContains": "unknown config key",
            },
            {
                "id": "selection_out_of_range",
                "values": {"commentary.director.selection_threshold": 101.0},
                "errorContains": "out of range",
            },
            {
                "id": "episode_capacity_inverted",
                "values": {
                    "commentary.director.active_episode_capacity": 200,
                    "commentary.director.resolved_episode_capacity": 100,
                },
                "errorContains": "active episode capacity",
            },
            {
                "id": "empty_tape_channels",
                "values": {"commentary.tape.enabled": True, "commentary.tape.channels": []},
                "errorContains": "tape channels empty",
            },
            {
                "id": "full_prompt_without_channel",
                "values": {"commentary.tape.llm_eval.capture_prompt": "full"},
                "errorContains": "full prompt requires",
            },
            {
                "id": "public_llm_host",
                "values": {"commentary.llm.base_url": "https://api.example.com/v1"},
                "errorContains": "URL outside local/LAN",
            },
            {
                "id": "unsafe_output_root",
                "values": {"commentary.tape.output_dir": "/"},
                "errorContains": "unsafe root path",
            },
            {
                "id": "duplicate_set_member",
                "values": {"commentary.tape.channels": ["flow", "flow"]},
                "errorContains": "duplicate set member",
            },
        ],
        "legacy": [
            {
                "id": "renamed_legacy_key",
                "sourceKey": "commentary.decision_log_size",
                "reason": "legacy_key",
                "generationInstalled": False,
                "replacementKeys": ["commentary.director.decision_capacity"],
            },
            {
                "id": "removed_legacy_section",
                "sourceKey": "[commentary.graph_runtime]",
                "reason": "legacy_key",
                "generationInstalled": False,
                "replacementKeys": [],
            },
        ],
        "ledgerScenario": _ledger_scenario(contract),
    }


def validate_contract(contract: dict[str, Any], schema: dict[str, Any]) -> None:
    errors = schema_errors(contract, schema, schema)
    if errors:
        raise ValueError(errors[0])
    expected = build_contract()
    if canonical(contract) != canonical(expected):
        raise ValueError("config contract differs from human tables")
    definitions = contract["keyDefinitions"]
    keys = [row["key"] for row in definitions]
    if len(keys) != len(set(keys)):
        raise ValueError("duplicate config key definition")
    counts = {
        kind: sum(row["keyClass"] == kind for row in definitions) for kind in ("static", "template")
    }
    if counts != {"static": EXPECTED_STATIC_KEYS, "template": EXPECTED_TEMPLATE_KEYS}:
        raise ValueError("config key counts differ")
    if set(contract["defaultConfig"]) != {
        row["key"] for row in definitions if row["keyClass"] == "static"
    }:
        raise ValueError("default config key set differs")
    validate_values({}, contract)


def validate_goldens(goldens: dict[str, Any], contract: dict[str, Any]) -> None:
    expected = build_goldens(contract)
    if canonical(goldens) != canonical(expected):
        raise ValueError("config goldens are stale")
    for fixture in goldens["valid"]:
        validate_values(fixture["values"], contract)
    for fixture in goldens["invalid"]:
        try:
            validate_values(fixture["values"], contract)
        except ValueError as exc:
            if fixture["errorContains"] not in str(exc):
                raise ValueError(f"fixture {fixture['id']} failed for wrong reason: {exc}") from exc
        else:
            raise ValueError(f"fixture {fixture['id']} was accepted")
    migrations = {row["source"]: row for row in contract["migrationContract"]["entries"]}
    for fixture in goldens["legacy"]:
        row = migrations[fixture["sourceKey"]]
        if (
            row["diagnosticReason"] != fixture["reason"]
            or row["replacementKeys"] != fixture["replacementKeys"]
            or fixture["generationInstalled"]
        ):
            raise ValueError(f"legacy fixture {fixture['id']} differs")
    scenario = goldens["ledgerScenario"]
    if [row["applySequence"] for row in scenario["appliedTransitions"]] != [21, 22, 23, 24]:
        raise ValueError("ledger apply sequence differs")
    previous_hash = scenario["initialEffectiveHash"]
    for transition in scenario["appliedTransitions"]:
        if transition["oldEffectiveHash"] != previous_hash:
            raise ValueError("ledger effective hash chain differs")
        if transition["changedKeys"] != sorted(transition["changedKeys"]):
            raise ValueError("ledger changed keys are not sorted")
        if [row["key"] for row in transition["effectivePatch"]] != transition["changedKeys"]:
            raise ValueError("ledger patch keys differ from changed keys")
        for patch in transition["effectivePatch"]:
            if (patch["key"] in SENSITIVE_KEYS) != patch.get("redacted", False):
                raise ValueError("ledger sensitive redaction differs")
        previous_hash = transition["newEffectiveHash"]
    if previous_hash != scenario["effectiveAfterAvailableBoundariesHash"]:
        raise ValueError("ledger final effective hash differs")
    if scenario["generation8DesiredHash"] != previous_hash:
        raise ValueError("generation-8 revert did not converge to effective hash")
    if scenario["pendingAfterGeneration8Revert"]:
        raise ValueError("reverted pending key was not removed")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    contract = build_contract()
    schema = build_schema()
    goldens = build_goldens(contract)
    if args.write:
        CONTRACT_PATH.write_text(
            json.dumps(contract, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        SCHEMA_PATH.write_text(
            json.dumps(schema, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        GOLDENS_PATH.write_text(
            json.dumps(goldens, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {CONTRACT_PATH.name}, {SCHEMA_PATH.name} and {GOLDENS_PATH.name}")
        return 0
    checked_contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    checked_schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    checked_goldens = json.loads(GOLDENS_PATH.read_text(encoding="utf-8"))
    if canonical(contract) != canonical(checked_contract) or canonical(schema) != canonical(
        checked_schema
    ):
        print("config contract/schema is stale", file=sys.stderr)
        return 1
    validate_contract(checked_contract, checked_schema)
    validate_goldens(checked_goldens, checked_contract)
    print(
        "Config contract OK: 50 static + 2 template keys, 14 boundaries, 13 migrations, 2 valid + 8 invalid + 2 legacy goldens, mixed-boundary replay"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
