#!/usr/bin/env python3
"""Build and validate the frozen v2 BeatDefinition catalog projection."""

from __future__ import annotations

import argparse
import copy
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
FAMILY_DOC = DOCS / "realization-verifier-contract.md"
REGISTRY_PATH = Path(__file__).with_name("freeze-registry.json")
CATALOG_PATH = Path(__file__).with_name("beat-catalog.json")
SCHEMA_PATH = Path(__file__).with_name("beat-catalog.schema.json")
MUTATIONS_PATH = Path(__file__).with_name("beat-catalog-mutations.json")

EXPECTED_GROUPS = {
    "timing": 12,
    "battle": 8,
    "position": 4,
    "incident": 5,
    "pit": 6,
    "stream": 1,
    "session": 21,
    "bio": 1,
    "filler": 6,
}
SUPPORTED_STAGES = ["practice", "qualifying", "race"]
ALLOWLIST_IDS = {
    "W_weather",
    "W_field",
    "W_filler_phase",
    "W_filler_off_track",
    "W_quiet_track",
}
GLOBAL_FORBIDDEN_CLAIM_TYPES = [
    "unbound.cause",
    "unbound.intent",
    "unbound.emotion",
    "unsupported.certainty",
    "unsupported.future_outcome",
    "unsupported.weather_inference",
    "unsupported.medical_inference",
    "unbound.entity",
    "unbound.number",
    "unbound.unit",
]
LIFECYCLE_BEATS = {
    "stream.started",
    "session.intro.practice",
    "session.intro.qualifying",
    "session.intro.race",
    "session.restart",
    "session.wrap.practice",
    "session.wrap.qualifying",
    "session.wrap.race",
    "session.preview.next",
    "session.enter_car.practice",
    "session.enter_car.qualifying",
    "session.enter_car.race",
}


def _clean(cell: str) -> str:
    return cell.strip().replace("`", "")


def _table(path: Path, heading: str) -> list[list[str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    start = lines.index(heading) + 1
    rows: list[list[str]] = []
    entered = False
    for line in lines[start:]:
        if line.startswith("|"):
            entered = True
            cells = [_clean(cell) for cell in line.strip().strip("|").split("|")]
            if cells and not all(re.fullmatch(r":?-+:?", cell) for cell in cells):
                rows.append(cells)
        elif entered:
            break
    if len(rows) < 2:
        raise ValueError(f"table not found after {heading!r} in {path}")
    return rows[1:]


def _beat_ids(raw: str) -> list[str]:
    if raw == "—":
        return []
    result: list[str] = []
    prefix = ""
    for item in (part.strip() for part in raw.split(",")):
        if item.startswith("."):
            item = prefix + item
        else:
            prefix = item.rsplit(".", 1)[0]
        result.append(item)
    return result


def _policy_rows() -> list[dict[str, Any]]:
    result = []
    for row in _table(EVENT_DOC, "## Frozen policy profiles"):
        ttl = int(row[3].removesuffix(" s"))
        cadence_match = re.search(r"/ (\d+) s$", row[5])
        result.append(
            {
                "id": row[0],
                "basePriority": int(row[1]),
                "urgency": row[2],
                "ttlMs": ttl * 1000,
                "penaltyCoefficient": float(row[4]),
                "cadenceRule": row[5],
                "cadenceMinimumMs": int(cadence_match.group(1)) * 1000 if cadence_match else None,
            }
        )
    return result


def _family_rows() -> list[dict[str, Any]]:
    return [
        {
            "id": row[0],
            "requiredParseFrame": row[1],
            "additionalHardRejects": row[2],
            "promotedMaxFreedom": "tight",
            "preferredFreedom": "tight",
        }
        for row in _table(FAMILY_DOC, "## Family coverage matrix")
    ]


def _stages(beat_id: str, hard_context: str) -> list[str]:
    if beat_id == "stream.started":
        return []
    if beat_id.endswith(".practice"):
        return ["practice"]
    if beat_id.endswith(".qualifying") or beat_id == "session.qualifying_recap":
        return ["qualifying"]
    if beat_id.endswith(".race"):
        return ["race"]
    if "practice or qualifying" in hard_context:
        return ["practice", "qualifying"]
    if hard_context.startswith("qualifying"):
        return ["qualifying"]
    if hard_context.startswith("race"):
        return ["race"]
    return SUPPORTED_STAGES.copy()


def _scope_modes(beat_id: str) -> list[str]:
    if beat_id == "stream.started":
        return ["stream"]
    if beat_id == "filler.lobby":
        return ["occurrence", "stream"]
    return ["occurrence"]


def _broadcast_guard(beat_id: str) -> dict[str, Any]:
    required = {
        "battle.side_by_side": "on_track",
        "filler.garage": "garage",
        "filler.lobby": "lobby",
        "filler.quiet_track": "on_track",
    }
    preferred = {
        "battle.pursuit": "on_track",
        "battle.approach": "on_track",
        "battle.attack_range": "on_track",
    }
    if beat_id in required:
        return {"mode": "require", "values": [required[beat_id]]}
    if beat_id in preferred:
        return {"mode": "prefer", "values": [preferred[beat_id]]}
    return {"mode": "ignore", "values": []}


def _vehicle_phases(beat_id: str) -> list[str]:
    suffix = beat_id.removeprefix("filler.")
    if suffix in {"out_lap", "in_lap", "parade_lap"}:
        return [suffix]
    if beat_id == "battle.pursuit":
        return ["racing"]
    return []


def _story_routes(beat_id: str) -> list[str]:
    if beat_id.startswith("timing."):
        return ["timing_attempt", "single_result"]
    if beat_id in {
        "battle.pursuit",
        "battle.approach",
        "battle.attack_range",
        "battle.side_by_side",
        "battle.won",
    }:
        return ["battle_ahead", "single_result"]
    if beat_id in {"battle.pressure_behind", "battle.rival_threat"}:
        return ["battle_behind", "single_result"]
    if beat_id == "battle.two_front":
        return ["battle_two_front", "single_result"]
    if beat_id == "position.pass":
        return ["battle_ahead", "battle_two_front", "single_result"]
    if beat_id == "position.lost":
        return ["battle_behind", "battle_two_front", "single_result"]
    if beat_id.startswith("position."):
        return ["single_result"]
    if beat_id.startswith("incident."):
        return ["incident", "single_result"]
    if beat_id.startswith("pit."):
        return ["pit_cycle", "single_result"]
    if beat_id == "stream.started":
        return ["stream_lifecycle"]
    if beat_id.startswith("session."):
        return ["session_occurrence", "single_result"]
    if beat_id == "bio.pressure":
        return ["bio_pressure", "single_result"]
    if beat_id.startswith("filler."):
        return ["filler_single"]
    raise ValueError(f"no story route for {beat_id}")


def _tape_channel(beat_id: str) -> str:
    exact = {
        "timing.lap.completed": "race.timing.lap",
        "timing.lap.personal_best": "race.timing.lap",
        "timing.pace.gain": "race.timing.delta",
        "timing.pace.loss": "race.timing.delta",
        "timing.target.locked": "race.timing.target",
        "timing.pace.hunt": "race.timing.target",
        "timing.clean_streak": "race.timing.consistency",
        "battle.attack_range": "race.battle.attack",
        "battle.side_by_side": "race.battle.side_by_side",
        "battle.two_front": "race.battle.two_front",
        "battle.won": "race.battle.outcome",
        "position.pass": "race.position.pass",
        "position.leader_change": "race.position.leader",
        "incident.invalid_lap": "race.incident.invalid_lap",
        "incident.aftermath": "race.incident.aftermath",
        "incident.recovery": "race.incident.recovery",
        "pit.outcome": "race.pit.outcome",
        "stream.started": "stream.lifecycle",
        "session.checkered": "race.control.flag",
        "session.flag.yellow": "race.control.flag",
        "session.flag.green": "race.control.flag",
        "session.final_lap": "race.session.final_lap",
        "session.hero_finish": "race.session.finish",
        "session.qualifying_recap": "session.qualifying.recap",
        "session.sof_brief": "session.context.field",
        "session.field_fact": "session.context.field",
        "session.weather_brief": "session.context.weather",
        "session.weather_change": "session.context.weather",
        "bio.pressure": "bio.pressure",
    }
    if beat_id in exact:
        return exact[beat_id]
    if beat_id.startswith("timing.sector."):
        return "race.timing.sector"
    if beat_id in {"timing.lap.projected", "timing.lap.hot", "timing.position.attack"}:
        return "race.timing.attempt"
    if beat_id in {"battle.pursuit", "battle.approach"}:
        return "race.battle.closing"
    if beat_id in {"battle.pressure_behind", "battle.rival_threat"}:
        return "race.battle.pressure"
    if beat_id in {"position.gained", "position.lost"}:
        return "race.position.change"
    if beat_id in {"incident.off_track", "incident.unclassified"}:
        return "race.incident.event"
    if beat_id.startswith("pit."):
        return "race.pit.cycle"
    if beat_id.startswith("session.enter_car."):
        return "session.vehicle"
    if beat_id.startswith("session."):
        return "session.lifecycle"
    if beat_id.startswith("filler."):
        return "filler.track_state"
    raise ValueError(f"no tape channel for {beat_id}")


def _claim_requirements(
    signature: str, predicate_registry: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[str]]:
    requirements: list[dict[str, Any]] = []
    for match in re.finditer(r"\b((?:[a-z][a-z0-9_]*\.)+[a-z][a-z0-9_]*)\(([^)]*)\)", signature):
        predicate_id, body = match.groups()
        predicate = predicate_registry.get(predicate_id)
        if predicate is None:
            requirements.append(
                {
                    "kind": "predicate",
                    "id": predicate_id,
                    "actorFrame": "unresolved",
                    "requiredAttributes": [],
                    "optionalAttributes": [],
                    "attributeEquals": {},
                    "minClaims": 1,
                    "maxClaims": 1,
                }
            )
            continue
        actor_count = 0 if predicate["actors"] == "—" else 2 if "→" in predicate["actors"] else 1
        if ";" in body:
            actor_frame, attribute_text = (part.strip() for part in body.split(";", 1))
        elif actor_count:
            actor_frame, attribute_text = body.strip(), ""
        else:
            actor_frame, attribute_text = "none", body.strip()
        registry_attributes = {item["id"]: item for item in predicate["attributes"]}
        if "…" in attribute_text:
            required_attributes = [
                item["id"] for item in predicate["attributes"] if item["required"]
            ]
            optional_attributes = [
                item["id"] for item in predicate["attributes"] if not item["required"]
            ]
            attribute_equals: dict[str, str] = {}
        else:
            optional_attributes = re.findall(r"\[,\s*([A-Za-z][A-Za-z0-9]*)\]", attribute_text)
            normalized = re.sub(r"\[,\s*[A-Za-z][A-Za-z0-9]*\]", "", attribute_text)
            tokens = re.findall(r"\b([A-Za-z][A-Za-z0-9]*)(?:=([a-z][a-z0-9_]*))?", normalized)
            required_attributes = [name for name, _ in tokens]
            attribute_equals = {name: value for name, value in tokens if value}
        unknown_attributes = (
            set(required_attributes) | set(optional_attributes)
        ) - registry_attributes.keys()
        if unknown_attributes:
            raise ValueError(
                f"{predicate_id}: signature has unknown attributes {sorted(unknown_attributes)}"
            )
        requirements.append(
            {
                "kind": "predicate",
                "id": predicate_id,
                "actorFrame": actor_frame,
                "requiredAttributes": required_attributes,
                "optionalAttributes": optional_attributes,
                "attributeEquals": attribute_equals,
                "minClaims": 1,
                "maxClaims": 1,
            }
        )
    allowlist_bounds = {"W_weather": (1, 3)}
    for item in re.findall(r"\bW_[A-Za-z0-9_]+\b", signature):
        lower, upper = allowlist_bounds.get(item, (1, 1))
        requirements.append(
            {
                "kind": "allowlist",
                "id": item,
                "actorFrame": "defined_by_allowlist",
                "requiredAttributes": [],
                "optionalAttributes": [],
                "attributeEquals": {},
                "minClaims": lower,
                "maxClaims": upper,
            }
        )
    references: list[str] = []
    if "referenced new weather fact" in signature:
        references.append("weather.changed.newFactId")
    return requirements, references


def _event_triggers() -> dict[str, list[dict[str, str]]]:
    triggers: dict[str, list[dict[str, str]]] = defaultdict(list)
    replaced_inputs = {
        "STREAM_START",
        "SESSION_INTRO_PRACTICE",
        "SESSION_INTRO_QUALIFY",
        "SESSION_INTRO_RACE",
        "SESSION_WRAP",
    }
    for row in _table(EVENT_DOC, "## Identifier disposition"):
        if row[0] in replaced_inputs:
            continue
        for beat_id in _beat_ids(row[4]):
            triggers[beat_id].append({"kind": "accepted_event", "id": row[0]})
    lifecycle = {
        "stream.started": "STREAM_STARTED",
        "session.intro.practice": "SESSION_STARTED",
        "session.intro.qualifying": "SESSION_STARTED",
        "session.intro.race": "SESSION_STARTED",
        "session.restart": "SESSION_RESTARTED",
        "session.wrap.practice": "SESSION_ENDED",
        "session.wrap.qualifying": "SESSION_ENDED",
        "session.wrap.race": "SESSION_ENDED",
        "session.preview.next": "SESSION_ENDED",
        "session.qualifying_recap": "SESSION_ENDED",
    }
    for beat_id, event_id in lifecycle.items():
        trigger = {"kind": "lifecycle_event", "id": event_id}
        if trigger not in triggers[beat_id]:
            triggers[beat_id].append(trigger)
    for beat_id in [
        "session.sof_brief",
        "session.weather_brief",
        "session.field_fact",
        "filler.out_lap",
        "filler.in_lap",
        "filler.parade_lap",
        "filler.garage",
        "filler.lobby",
        "filler.quiet_track",
    ]:
        triggers[beat_id].append({"kind": "silence", "id": "LONG_SILENCE_ELAPSED"})
    return triggers


def _backend(beat_id: str, policy_id: str) -> str:
    if policy_id in {"critical", "result"} or beat_id in LIFECYCLE_BEATS:
        return "authored"
    return "qwen_compiled"


def build_catalog() -> dict[str, Any]:
    inventory_rows = _table(EVENT_DOC, "## Beat inventory")
    claim_rows = _table(EVENT_DOC, "## Claim and realization mapping")
    claims = {row[0]: row for row in claim_rows}
    triggers = _event_triggers()
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    predicate_registry = {row["id"]: row for row in registry["factPredicates"]}
    beats = []
    for row in inventory_rows:
        beat_id, story_role, policy_id, hard_context, lifecycle = row
        if beat_id not in claims:
            raise ValueError(f"{beat_id}: missing claim row")
        claim_row = claims[beat_id]
        group, role = story_role.split("/", 1)
        requirements, references = _claim_requirements(claim_row[1], predicate_registry)
        beats.append(
            {
                "id": beat_id,
                "group": group,
                "role": role,
                "storyRoutes": _story_routes(beat_id),
                "policyId": policy_id,
                "tapeChannel": _tape_channel(beat_id),
                "triggers": triggers[beat_id],
                "hardContext": {
                    "normativeText": hard_context,
                    "scopeModes": _scope_modes(beat_id),
                    "stageAnyOf": _stages(beat_id, hard_context),
                    "broadcastContext": _broadcast_guard(beat_id),
                    "vehiclePhaseAnyOf": _vehicle_phases(beat_id),
                },
                "lifecycleText": lifecycle,
                "claims": {
                    "normativeSignature": claim_row[1],
                    "required": requirements,
                    "referenceRequirements": references,
                    "globalForbiddenClaimTypes": GLOBAL_FORBIDDEN_CLAIM_TYPES,
                    "forbiddenAddition": claim_row[2],
                },
                "realization": {
                    "family": claim_row[3],
                    "backend": _backend(beat_id, policy_id),
                    "maxFreedom": "tight",
                    "requiredPatternCardCount": 4,
                },
            }
        )
    return {
        "schemaVersion": "narrative-catalog/2",
        "catalogProjectionVersion": "beat-catalog-freeze/1",
        "sourceBaseline": "master@0ce75d4",
        "language": "en",
        "globalForbiddenClaimTypes": GLOBAL_FORBIDDEN_CLAIM_TYPES,
        "policies": _policy_rows(),
        "realizationFamilies": _family_rows(),
        "beats": beats,
    }


def build_schema() -> dict[str, Any]:
    identifier = {"type": "string", "pattern": r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$"}
    text = {"type": "string", "minLength": 1, "maxLength": 512}

    def string_list(lo: int, hi: int) -> dict[str, Any]:
        return {
            "type": "array",
            "items": identifier,
            "minItems": lo,
            "maxItems": hi,
            "uniqueItems": True,
        }

    def closed(fields: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "object",
            "additionalProperties": False,
            "properties": fields,
            "required": list(fields),
        }

    trigger = closed(
        {
            "kind": {"enum": ["accepted_event", "lifecycle_event", "silence"]},
            "id": identifier,
        }
    )
    requirement = closed(
        {
            "kind": {"enum": ["predicate", "allowlist"]},
            "id": identifier,
            "actorFrame": text,
            "requiredAttributes": string_list(0, 16),
            "optionalAttributes": string_list(0, 16),
            "attributeEquals": {
                "type": "object",
                "propertyNames": identifier,
                "additionalProperties": identifier,
                "maxProperties": 16,
            },
            "minClaims": {"type": "integer", "minimum": 1, "maximum": 3},
            "maxClaims": {"type": "integer", "minimum": 1, "maximum": 3},
        }
    )
    beat = closed(
        {
            "id": identifier,
            "group": {"enum": list(EXPECTED_GROUPS)},
            "role": {
                "enum": [
                    "opening",
                    "update",
                    "result",
                    "context",
                    "escalation",
                    "climax",
                    "composite",
                    "outcome",
                    "closure",
                    "bridge",
                    "control",
                    "vehicle",
                    "single",
                ]
            },
            "storyRoutes": string_list(1, 4),
            "policyId": identifier,
            "tapeChannel": identifier,
            "triggers": {
                "type": "array",
                "items": trigger,
                "minItems": 1,
                "maxItems": 8,
                "uniqueItems": True,
            },
            "hardContext": closed(
                {
                    "normativeText": text,
                    "scopeModes": {
                        "type": "array",
                        "items": {"enum": ["occurrence", "stream"]},
                        "minItems": 1,
                        "maxItems": 2,
                        "uniqueItems": True,
                    },
                    "stageAnyOf": {
                        "type": "array",
                        "items": {"enum": SUPPORTED_STAGES},
                        "minItems": 0,
                        "maxItems": 3,
                        "uniqueItems": True,
                    },
                    "broadcastContext": closed(
                        {
                            "mode": {"enum": ["ignore", "prefer", "require"]},
                            "values": {
                                "type": "array",
                                "items": {
                                    "enum": ["on_track", "garage", "lobby", "replay", "transition"]
                                },
                                "minItems": 0,
                                "maxItems": 5,
                                "uniqueItems": True,
                            },
                        }
                    ),
                    "vehiclePhaseAnyOf": {
                        "type": "array",
                        "items": {
                            "enum": [
                                "garage",
                                "pit_lane",
                                "out_lap",
                                "timed_lap",
                                "in_lap",
                                "parade_lap",
                                "racing",
                            ]
                        },
                        "minItems": 0,
                        "maxItems": 7,
                        "uniqueItems": True,
                    },
                }
            ),
            "lifecycleText": text,
            "claims": closed(
                {
                    "normativeSignature": text,
                    "required": {
                        "type": "array",
                        "items": requirement,
                        "minItems": 1,
                        "maxItems": 4,
                        "uniqueItems": True,
                    },
                    "referenceRequirements": string_list(0, 4),
                    "globalForbiddenClaimTypes": string_list(10, 10),
                    "forbiddenAddition": text,
                }
            ),
            "realization": closed(
                {
                    "family": identifier,
                    "backend": {"enum": ["authored", "qwen_compiled"]},
                    "maxFreedom": {"const": "tight"},
                    "requiredPatternCardCount": {"const": 4},
                }
            ),
        }
    )
    policy = closed(
        {
            "id": identifier,
            "basePriority": {"type": "integer", "minimum": 0, "maximum": 100},
            "urgency": {"enum": ["background", "context", "story", "critical"]},
            "ttlMs": {"type": "integer", "minimum": 1000, "maximum": 120000},
            "penaltyCoefficient": {"type": "number", "minimum": 0, "maximum": 4},
            "cadenceRule": text,
            "cadenceMinimumMs": {"type": ["integer", "null"], "minimum": 0, "maximum": 300000},
        }
    )
    family = closed(
        {
            "id": identifier,
            "requiredParseFrame": text,
            "additionalHardRejects": text,
            "promotedMaxFreedom": {"const": "tight"},
            "preferredFreedom": {"const": "tight"},
        }
    )
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": "https://irswitch.local/schema/v2/beat-catalog.schema.json",
        "title": "iRSwitch v2 frozen BeatDefinition catalog projection",
        **closed(
            {
                "schemaVersion": {"const": "narrative-catalog/2"},
                "catalogProjectionVersion": {"const": "beat-catalog-freeze/1"},
                "sourceBaseline": {"const": "master@0ce75d4"},
                "language": {"const": "en"},
                "globalForbiddenClaimTypes": string_list(10, 10),
                "policies": {
                    "type": "array",
                    "items": policy,
                    "minItems": 6,
                    "maxItems": 6,
                    "uniqueItems": True,
                },
                "realizationFamilies": {
                    "type": "array",
                    "items": family,
                    "minItems": 37,
                    "maxItems": 37,
                    "uniqueItems": True,
                },
                "beats": {
                    "type": "array",
                    "items": beat,
                    "minItems": 64,
                    "maxItems": 64,
                    "uniqueItems": True,
                },
            }
        ),
        "x-irswitch-invariants": [
            "unique_ids_and_exact_group_counts",
            "claims_resolve_fact_registry",
            "families_policies_channels_resolve",
            "speakable_dispositions_resolve_beats",
            "nonspeakable_dispositions_have_no_beats",
            "trigger_and_context_axes_are_coherent",
            "baseline_realization_routing",
        ],
    }


def validate_catalog(catalog: dict[str, Any], schema: dict[str, Any]) -> None:
    errors = schema_errors(catalog, schema, schema)
    if errors:
        raise ValueError(errors[0])
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    beats = catalog["beats"]
    beat_ids = [beat["id"] for beat in beats]
    if len(beat_ids) != len(set(beat_ids)):
        raise ValueError("duplicate beat ID")
    if Counter(beat["group"] for beat in beats) != Counter(EXPECTED_GROUPS):
        raise ValueError("beat group counts differ from frozen 64-beat inventory")
    policy_ids = {row["id"] for row in catalog["policies"]}
    family_ids = {row["id"] for row in catalog["realizationFamilies"]}
    channel_ids = set(registry["tapeChannels"])
    predicate_ids = {row["id"] for row in registry["factPredicates"]}
    predicate_registry = {row["id"]: row for row in registry["factPredicates"]}
    used_families: set[str] = set()
    expected_triggers = _event_triggers()
    for beat in beats:
        if beat["policyId"] not in policy_ids:
            raise ValueError(f"{beat['id']}: unknown policy")
        if beat["tapeChannel"] not in channel_ids:
            raise ValueError(f"{beat['id']}: unknown tape channel")
        family_id = beat["realization"]["family"]
        if family_id not in family_ids:
            raise ValueError(f"{beat['id']}: unknown realization family")
        used_families.add(family_id)
        expected_backend = _backend(beat["id"], beat["policyId"])
        if beat["realization"]["backend"] != expected_backend:
            raise ValueError(f"{beat['id']}: invalid baseline backend")
        if beat["triggers"] != expected_triggers[beat["id"]]:
            raise ValueError(f"{beat['id']}: trigger routing differs from frozen disposition")
        if beat["claims"]["globalForbiddenClaimTypes"] != catalog["globalForbiddenClaimTypes"]:
            raise ValueError(f"{beat['id']}: global forbidden claims differ")
        for requirement in beat["claims"]["required"]:
            known = predicate_ids if requirement["kind"] == "predicate" else ALLOWLIST_IDS
            if requirement["id"] not in known:
                raise ValueError(f"{beat['id']}: unresolved claim {requirement['id']}")
            if requirement["minClaims"] > requirement["maxClaims"]:
                raise ValueError(f"{beat['id']}: inverted claim cardinality")
            if requirement["kind"] == "predicate":
                predicate = predicate_registry[requirement["id"]]
                actor_count = (
                    0 if predicate["actors"] == "—" else 2 if "→" in predicate["actors"] else 1
                )
                actual_actor_count = (
                    0
                    if requirement["actorFrame"] == "none"
                    else 2
                    if "→" in requirement["actorFrame"]
                    else 1
                )
                if actual_actor_count != actor_count:
                    raise ValueError(f"{beat['id']}: actor arity differs from predicate")
                attributes = {row["id"]: row for row in predicate["attributes"]}
                named_attributes = set(requirement["requiredAttributes"]) | set(
                    requirement["optionalAttributes"]
                )
                if set(requirement["requiredAttributes"]) & set(requirement["optionalAttributes"]):
                    raise ValueError(f"{beat['id']}: required/optional attributes overlap")
                missing_required = {
                    row["id"] for row in predicate["attributes"] if row["required"]
                } - named_attributes
                if missing_required:
                    raise ValueError(
                        f"{beat['id']}: missing required attributes {sorted(missing_required)}"
                    )
                for attribute_id, value in requirement["attributeEquals"].items():
                    attribute = attributes.get(attribute_id)
                    if attribute is None:
                        raise ValueError(f"{beat['id']}: constraint on unknown attribute")
                    enum_values = registry["enums"].get(attribute["scalarType"])
                    if enum_values is not None and value not in enum_values:
                        raise ValueError(f"{beat['id']}: constraint value outside enum")
        guard = beat["hardContext"]["broadcastContext"]
        if (guard["mode"] == "ignore") != (not guard["values"]):
            raise ValueError(f"{beat['id']}: incoherent broadcast-context guard")
        if "scene" in beat["hardContext"]["normativeText"].lower():
            raise ValueError(f"{beat['id']}: raw scene reference is forbidden")
        if beat["id"] == "stream.started" and beat["hardContext"]["stageAnyOf"]:
            raise ValueError("stream.started cannot require a session stage")
    if used_families != family_ids:
        raise ValueError(f"unused realization families: {sorted(family_ids - used_families)}")
    known_beats = set(beat_ids)
    for event in registry["eventIdentifiers"]:
        refs = set(event["beatDefinitions"])
        if event["eventClass"] == "speakable" and not refs:
            raise ValueError(f"{event['id']}: speakable disposition has no beat")
        if event["eventClass"] != "speakable" and refs:
            raise ValueError(f"{event['id']}: nonspeakable disposition has a beat")
        missing = refs - known_beats
        if missing:
            raise ValueError(f"{event['id']}: unknown beats {sorted(missing)}")


def _set_path(value: Any, path: list[Any], replacement: Any) -> None:
    target = value
    for part in path[:-1]:
        target = target[part]
    target[path[-1]] = replacement


def validate_mutations(catalog: dict[str, Any], schema: dict[str, Any]) -> int:
    fixtures = json.loads(MUTATIONS_PATH.read_text(encoding="utf-8"))
    for fixture in fixtures["invalid"]:
        mutated = copy.deepcopy(catalog)
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
            validate_catalog(mutated, schema)
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
    parser.add_argument("--emit", choices=["catalog", "schema"])
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    generated_catalog = build_catalog()
    generated_schema = build_schema()
    if args.emit == "catalog":
        print(json.dumps(generated_catalog, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    if args.emit == "schema":
        print(json.dumps(generated_schema, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    if args.write:
        CATALOG_PATH.write_text(
            json.dumps(generated_catalog, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        SCHEMA_PATH.write_text(
            json.dumps(generated_schema, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {CATALOG_PATH.name} and {SCHEMA_PATH.name}")
        return 0
    checked_catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    checked_schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    if canonical(generated_catalog) != canonical(checked_catalog):
        print("beat-catalog.json is stale", file=sys.stderr)
        return 1
    if canonical(generated_schema) != canonical(checked_schema):
        print("beat-catalog.schema.json is stale", file=sys.stderr)
        return 1
    validate_catalog(checked_catalog, checked_schema)
    mutation_count = validate_mutations(checked_catalog, checked_schema)
    print(
        "Beat catalog OK: "
        f"{len(checked_catalog['beats'])} beats, "
        f"{len(checked_catalog['realizationFamilies'])} families, "
        f"{mutation_count} rejected mutations"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
