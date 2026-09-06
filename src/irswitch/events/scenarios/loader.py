"""Strict standard-library loader for versioned atomic scenario definitions."""

from __future__ import annotations

import json
import math
import re
from collections.abc import Collection
from pathlib import Path
from types import MappingProxyType
from typing import Any

from irswitch.events.audience import COMMENTARY_ONLY_EVENTS
from irswitch.events.envelope import WIRE_MODES, WIRE_PHASES
from irswitch.events.event_catalog import catalog_entries, catalog_fallbacks
from irswitch.events.scenarios.model import (
    ScenarioDefinition,
    ScenarioEmission,
    ScenarioState,
    ScenarioTransition,
    freeze_json,
)
from irswitch.events.scenarios.registry import (
    REGISTERED_ACTION_IDS,
    REGISTERED_ESTIMATOR_IDS,
    REGISTERED_GUARD_IDS,
    REGISTERED_MISSING_POLICIES,
    REGISTERED_RESET_ACTIONS,
    REGISTERED_RESET_REASONS,
    REGISTERED_RESET_SCOPES,
    REGISTERED_UNITS,
)

SCENARIO_SCHEMA_VERSION = 1

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
_STATE_ID = re.compile(r"^[A-Z][A-Z0-9_]*$")
_REQUIRED_IDENTITY_FIELDS = frozenset(
    {"subsession_id", "session_num", "run_epoch", "player_car_idx", "episode_sequence"}
)
_ALLOWED_TOP_LEVEL = frozenset(
    {
        "acceptanceTraces",
        "baseline",
        "coalescing",
        "conflicts",
        "director",
        "emissions",
        "features",
        "identity",
        "observations",
        "parameters",
        "resets",
        "scenarioId",
        "scenarioVersion",
        "schemaVersion",
        "scope",
        "states",
        "status",
        "terminalPolicy",
        "transitions",
    }
)
_REQUIRED_TOP_LEVEL = frozenset(
    {
        "emissions",
        "identity",
        "observations",
        "parameters",
        "scenarioId",
        "scenarioVersion",
        "schemaVersion",
        "scope",
        "states",
        "transitions",
    }
)


class ScenarioDefinitionError(ValueError):
    """Raised when a definition cannot be made safe and deterministic."""

    def __init__(self, errors: list[str]) -> None:
        self.errors = tuple(errors)
        super().__init__("invalid scenario definition: " + "; ".join(errors[:12]))


def load_scenario_definition(path: Path) -> ScenarioDefinition:
    """Load and validate one JSON definition.

    Callers at the application boundary own fail-soft logging and legacy fallback.
    This pure loader raises a typed error so that policy stays outside file parsing.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object)
    except (OSError, json.JSONDecodeError) as exc:
        raise ScenarioDefinitionError([f"cannot load {path}: {exc}"]) from exc
    return parse_scenario_definition(raw)


def parse_scenario_definition(raw: object) -> ScenarioDefinition:
    errors = validate_scenario_document(raw)
    if errors:
        raise ScenarioDefinitionError(errors)
    assert isinstance(raw, dict)

    states = tuple(
        ScenarioState(
            id=str(item["id"]),
            initial=bool(item["initial"]),
            terminal=bool(item["terminal"]),
            meaning=str(item["meaning"]),
        )
        for item in raw["states"]
    )
    transitions = tuple(
        sorted(
            (
                ScenarioTransition(
                    id=str(item["id"]),
                    order=int(item["order"]),
                    sources=tuple(str(source) for source in item["from"]),
                    target=str(item["to"]),
                    guard=str(item["guard"]),
                    actions=tuple(str(action) for action in item["actions"]),
                    reason=str(item["reason"]),
                    hold_s=float(item.get("holdS", 0.0)),
                    within_s=_optional_float(item.get("withinS")),
                    after_s=_optional_float(item.get("afterS")),
                    enter_confidence=float(item.get("enterConfidence", 1.0)),
                    clock=str(item.get("clock", "state")),
                )
                for item in raw["transitions"]
            ),
            key=lambda item: (item.order, item.id),
        )
    )
    emissions = {
        str(emission_id): ScenarioEmission(
            id=str(emission_id),
            beat_id=str(payload["beatId"]),
            event_type=str(payload["eventType"]),
            phase=str(payload["phase"]),
            channel=str(payload["channel"]),
            metrics=tuple(str(metric) for metric in payload.get("metrics", [])),
            priority=int(payload["priority"]) if "priority" in payload else None,
            priority_source=str(payload.get("prioritySource", "")),
        )
        for emission_id, payload in raw["emissions"].items()
    }
    initial_state = next(state.id for state in states if state.initial)
    scope = raw["scope"]
    identity = raw["identity"]
    return ScenarioDefinition(
        schema_version=int(raw["schemaVersion"]),
        scenario_id=str(raw["scenarioId"]),
        scenario_version=int(raw["scenarioVersion"]),
        status=str(raw.get("status", "runtime")),
        scope_modes=tuple(str(mode) for mode in scope["overlayModes"]),
        requires_connected=bool(scope.get("requiresConnected", True)),
        identity_fields=tuple(str(field) for field in identity["fields"]),
        initial_state=initial_state,
        states=states,
        transitions=transitions,
        emissions=MappingProxyType(emissions),
        parameters=MappingProxyType(dict(raw["parameters"])),
        document=raw,
    )


def validate_scenario_document(raw: object) -> list[str]:
    """Collect contract errors without interpreting any executable expression."""
    if not isinstance(raw, dict):
        return ["scenario definition must be an object"]
    json_error = ""
    try:
        freeze_json(raw)
    except ValueError as exc:
        # Preserve field-specific errors for non-finite numbers below.
        if any(not isinstance(key, str) for key in raw):
            return [str(exc)]
        json_error = str(exc)

    errors: list[str] = [json_error] if json_error else []
    for key in sorted(set(raw) - _ALLOWED_TOP_LEVEL):
        errors.append(f"unknown top-level field: {key}")
    for key in sorted(_REQUIRED_TOP_LEVEL - set(raw)):
        errors.append(f"missing top-level field: {key}")

    if (
        not _positive_integer(raw.get("schemaVersion"))
        or raw.get("schemaVersion") != SCENARIO_SCHEMA_VERSION
    ):
        errors.append(f"unsupported schemaVersion: {raw.get('schemaVersion')!r}")
    scenario_id = raw.get("scenarioId")
    if not isinstance(scenario_id, str) or not _IDENTIFIER.fullmatch(scenario_id):
        errors.append("scenarioId must be a lowercase snake-case identifier")
    if not _positive_integer(raw.get("scenarioVersion")):
        errors.append("scenarioVersion must be a positive integer")

    _validate_scope(raw.get("scope"), errors)
    _validate_identity(raw.get("identity"), errors)
    _validate_nonnegative_parameters(raw.get("parameters"), errors)
    observations = _validate_observations(raw.get("observations"), errors)
    _validate_features(raw.get("features"), observations, errors)
    state_ids, initial_states = _validate_states(raw.get("states"), errors)
    graph_edges = _validate_transitions(raw.get("transitions"), state_ids, errors)
    _validate_reachability(state_ids, initial_states, graph_edges, errors)
    _validate_emissions(raw.get("emissions"), errors)
    _validate_resets(raw.get("resets"), errors)
    _validate_policy_sections(raw, errors)
    return errors


def _validate_scope(value: object, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("scope must be an object")
        return
    _unknown_fields(value, {"overlayModes", "subject", "requiresConnected"}, "scope", errors)
    if value.get("subject") != "hero":
        errors.append("scope.subject must be hero")
    if not isinstance(value.get("requiresConnected", True), bool):
        errors.append("scope.requiresConnected must be boolean")
    modes = value.get("overlayModes")
    if not isinstance(modes, list) or not modes:
        errors.append("scope.overlayModes must be a non-empty list")
        return
    for mode in modes:
        if not _registered(mode, WIRE_MODES) or mode == "unknown":
            errors.append(f"scope.overlayModes contains unsupported mode: {mode!r}")


def _validate_identity(value: object, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("identity must be an object")
        return
    _unknown_fields(
        value,
        {"fields", "episodeIdTemplate", "parentStoryId", "beatCorrelationTemplate"},
        "identity",
        errors,
    )
    fields = value.get("fields")
    if not isinstance(fields, list):
        errors.append("identity.fields must be a list")
        return
    field_set = {str(field) for field in fields}
    for field in sorted(_REQUIRED_IDENTITY_FIELDS - field_set):
        errors.append(f"missing identity field: {field}")
    for field in sorted(field_set - _REQUIRED_IDENTITY_FIELDS):
        errors.append(f"unknown identity field: {field}")
    if len(fields) != len(field_set):
        errors.append("identity.fields must be unique")
    if value.get("parentStoryId") != "episode_id":
        errors.append("identity.parentStoryId must be episode_id")
    for template_key in ("episodeIdTemplate", "beatCorrelationTemplate"):
        if not isinstance(value.get(template_key), str) or not value[template_key].strip():
            errors.append(f"identity.{template_key} must be a non-empty string")


def _validate_nonnegative_parameters(value: object, errors: list[str]) -> None:
    if not isinstance(value, dict):
        errors.append("parameters must be an object")
        return
    for name, payload in value.items():
        if isinstance(payload, bool):
            errors.append(f"parameters.{name} must not be boolean")
        elif isinstance(payload, (int, float)):
            if not math.isfinite(float(payload)) or float(payload) < 0.0:
                errors.append(f"parameters.{name} must be finite and non-negative")
        elif isinstance(payload, dict):
            _unknown_fields(
                payload,
                {"type", "minimum", "maximum", "default", "configBinding"},
                f"parameters.{name}",
                errors,
            )
            for bound in ("minimum", "maximum", "default"):
                if bound in payload:
                    number = payload[bound]
                    if (
                        isinstance(number, bool)
                        or not isinstance(number, (int, float))
                        or not math.isfinite(float(number))
                        or float(number) < 0.0
                    ):
                        errors.append(f"parameters.{name}.{bound} must be finite and non-negative")
        else:
            errors.append(f"parameters.{name} has unsupported value")


def _validate_observations(value: object, errors: list[str]) -> set[str]:
    if not isinstance(value, dict) or not value:
        errors.append("observations must be a non-empty object")
        return set()
    names = {str(name) for name in value}
    for name, payload in value.items():
        if not isinstance(payload, dict):
            errors.append(f"observations.{name} must be an object")
            continue
        _unknown_fields(
            payload,
            {"field", "fallbackField", "unit", "maxAgeS", "missingPolicy"},
            f"observations.{name}",
            errors,
        )
        unit = payload.get("unit")
        if not _registered(unit, REGISTERED_UNITS):
            errors.append(f"observations.{name} unknown unit: {unit}")
        _validate_nonnegative_number(payload.get("maxAgeS"), f"observations.{name}.maxAgeS", errors)
        missing_policy = payload.get("missingPolicy")
        if not _registered(missing_policy, REGISTERED_MISSING_POLICIES):
            errors.append(f"observations.{name} unknown missing policy: {missing_policy}")
        if not isinstance(payload.get("field"), str) or not payload["field"].strip():
            errors.append(f"observations.{name}.field must be a non-empty string")
    return names


def _validate_features(value: object, observations: set[str], errors: list[str]) -> None:
    if value is None:
        return
    if not isinstance(value, dict):
        errors.append("features must be an object")
        return
    for name, payload in value.items():
        if not isinstance(payload, dict):
            errors.append(f"features.{name} must be an object")
            continue
        _unknown_fields(
            payload,
            {"estimator", "inputs", "resetScope", "historyWindowS"},
            f"features.{name}",
            errors,
        )
        estimator = payload.get("estimator")
        if not _registered(estimator, REGISTERED_ESTIMATOR_IDS):
            errors.append(f"features.{name} unknown estimator: {estimator}")
        inputs = payload.get("inputs")
        if not isinstance(inputs, list) or not inputs:
            errors.append(f"features.{name}.inputs must be a non-empty list")
        else:
            for input_name in inputs:
                if not _registered(input_name, observations):
                    errors.append(f"features.{name} unknown input: {input_name}")
        reset_scope = payload.get("resetScope")
        if not _registered(reset_scope, REGISTERED_RESET_SCOPES):
            errors.append(f"features.{name} unknown reset scope: {reset_scope}")
        if "historyWindowS" in payload:
            _validate_nonnegative_number(
                payload["historyWindowS"], f"features.{name}.historyWindowS", errors
            )


def _validate_states(value: object, errors: list[str]) -> tuple[set[str], set[str]]:
    if not isinstance(value, list) or not value:
        errors.append("states must be a non-empty list")
        return set(), set()
    state_ids: set[str] = set()
    initial_states: set[str] = set()
    for index, payload in enumerate(value):
        if not isinstance(payload, dict):
            errors.append(f"states[{index}] must be an object")
            continue
        _unknown_fields(
            payload, {"id", "initial", "terminal", "meaning"}, f"states[{index}]", errors
        )
        state_id = payload.get("id")
        if not isinstance(state_id, str) or not _STATE_ID.fullmatch(state_id):
            errors.append(f"states[{index}].id must be an uppercase snake-case identifier")
            continue
        if state_id in state_ids:
            errors.append(f"duplicate state id: {state_id}")
        state_ids.add(state_id)
        if payload.get("initial") is True:
            initial_states.add(state_id)
        if not isinstance(payload.get("initial"), bool):
            errors.append(f"states.{state_id}.initial must be boolean")
        if not isinstance(payload.get("terminal"), bool):
            errors.append(f"states.{state_id}.terminal must be boolean")
        if not isinstance(payload.get("meaning"), str) or not payload["meaning"].strip():
            errors.append(f"states.{state_id}.meaning must be a non-empty string")
    if len(initial_states) != 1:
        errors.append(f"states must define exactly one initial state, found {len(initial_states)}")
    return state_ids, initial_states


def _validate_transitions(
    value: object, state_ids: set[str], errors: list[str]
) -> list[tuple[tuple[str, ...], str]]:
    if not isinstance(value, list) or not value:
        errors.append("transitions must be a non-empty list")
        return []
    transition_ids: set[str] = set()
    graph_edges: list[tuple[tuple[str, ...], str]] = []
    for index, payload in enumerate(value):
        if not isinstance(payload, dict):
            errors.append(f"transitions[{index}] must be an object")
            continue
        _unknown_fields(
            payload,
            {
                "id",
                "order",
                "from",
                "to",
                "guard",
                "actions",
                "reason",
                "holdS",
                "withinS",
                "afterS",
                "enterConfidence",
                "clock",
            },
            f"transitions[{index}]",
            errors,
        )
        transition_id = payload.get("id")
        prefix = f"transitions[{index}]"
        if not isinstance(transition_id, str) or not _IDENTIFIER.fullmatch(transition_id):
            errors.append(f"{prefix}.id must be a lowercase snake-case identifier")
        elif transition_id in transition_ids:
            errors.append(f"duplicate transition id: {transition_id}")
        else:
            transition_ids.add(transition_id)
            prefix = f"transitions.{transition_id}"

        sources_raw = payload.get("from")
        sources: tuple[str, ...] = ()
        if not isinstance(sources_raw, list) or not sources_raw:
            errors.append(f"{prefix}.from must be a non-empty list")
        else:
            sources = tuple(str(source) for source in sources_raw)
            for source in sources:
                if source not in state_ids:
                    errors.append(f"{prefix} unknown source state: {source}")
        target = payload.get("to")
        if target != "SAME" and not _registered(target, state_ids):
            errors.append(f"{prefix} unknown target state: {target}")
        if sources and isinstance(target, str):
            graph_edges.append((sources, target))

        order = payload.get("order")
        if not isinstance(order, int) or isinstance(order, bool):
            errors.append(f"{prefix}.order must be an integer")
        guard = payload.get("guard")
        if not _registered(guard, REGISTERED_GUARD_IDS):
            errors.append(f"{prefix} unknown guard: {guard}")
        actions = payload.get("actions")
        if not isinstance(actions, list):
            errors.append(f"{prefix}.actions must be a list")
        else:
            for action in actions:
                if not _registered(action, REGISTERED_ACTION_IDS):
                    errors.append(f"{prefix} unknown action: {action}")
        reason = payload.get("reason")
        if not isinstance(reason, str) or not _IDENTIFIER.fullmatch(reason):
            errors.append(f"{prefix}.reason must be a lowercase snake-case identifier")
        if not _registered(payload.get("clock", "state"), {"state", "episode"}):
            errors.append(f"{prefix}.clock must be state or episode")
        for time_field in ("holdS", "withinS", "afterS"):
            if time_field in payload:
                _validate_nonnegative_number(payload[time_field], f"{prefix}.{time_field}", errors)
        if "enterConfidence" in payload:
            confidence = payload["enterConfidence"]
            if (
                isinstance(confidence, bool)
                or not isinstance(confidence, (int, float))
                or not math.isfinite(float(confidence))
                or not 0.0 <= float(confidence) <= 1.0
            ):
                errors.append(f"{prefix}.enterConfidence must be within [0, 1]")
    return graph_edges


def _validate_reachability(
    state_ids: set[str],
    initial_states: set[str],
    graph_edges: list[tuple[tuple[str, ...], str]],
    errors: list[str],
) -> None:
    if len(initial_states) != 1:
        return
    reachable = set(initial_states)
    changed = True
    while changed:
        changed = False
        for sources, target in graph_edges:
            if target == "SAME" or not any(source in reachable for source in sources):
                continue
            if target not in reachable:
                reachable.add(target)
                changed = True
    for state_id in sorted(state_ids - reachable):
        errors.append(f"unreachable state: {state_id}")


def _validate_emissions(value: object, errors: list[str]) -> None:
    if not isinstance(value, dict) or not value:
        errors.append("emissions must be a non-empty object")
        return
    known_events = set(catalog_entries()) | set(catalog_fallbacks()) | COMMENTARY_ONLY_EVENTS
    for emission_id, payload in value.items():
        prefix = f"emissions.{emission_id}"
        if not isinstance(payload, dict):
            errors.append(f"{prefix} must be an object")
            continue
        _unknown_fields(
            payload,
            {
                "beatId",
                "eventType",
                "phase",
                "channel",
                "priority",
                "prioritySource",
                "metrics",
                "emitWhen",
                "compatibility",
            },
            prefix,
            errors,
        )
        beat_id = payload.get("beatId")
        if not isinstance(beat_id, str) or not _IDENTIFIER.fullmatch(beat_id):
            errors.append(f"{prefix}.beatId must be a lowercase snake-case identifier")
        event_type = payload.get("eventType")
        if not _registered(event_type, known_events):
            errors.append(f"{prefix} unknown event type: {event_type}")
        phase = payload.get("phase")
        if not _registered(phase, WIRE_PHASES):
            errors.append(f"{prefix} unknown phase: {phase}")
        if not isinstance(payload.get("channel"), str) or not payload["channel"].strip():
            errors.append(f"{prefix}.channel must be a non-empty string")
        if "priority" in payload:
            priority = payload["priority"]
            if not isinstance(priority, int) or isinstance(priority, bool):
                errors.append(f"{prefix}.priority must be an integer")
        elif not isinstance(payload.get("prioritySource"), str) or not payload["prioritySource"]:
            errors.append(f"{prefix} requires priority or prioritySource")
        metrics = payload.get("metrics", [])
        if not isinstance(metrics, list) or any(
            not isinstance(item, str) or not item for item in metrics
        ):
            errors.append(f"{prefix}.metrics must be a list of non-empty strings")


def _validate_resets(value: object, errors: list[str]) -> None:
    if value is None:
        return
    if not isinstance(value, list):
        errors.append("resets must be a list")
        return
    for index, payload in enumerate(value):
        if not isinstance(payload, dict):
            errors.append(f"resets[{index}] must be an object")
            continue
        _unknown_fields(payload, {"reason", "action"}, f"resets[{index}]", errors)
        reason = payload.get("reason")
        if not _registered(reason, REGISTERED_RESET_REASONS):
            errors.append(f"resets[{index}] unknown reset reason: {reason}")
        action = payload.get("action")
        if not _registered(action, REGISTERED_RESET_ACTIONS):
            errors.append(f"resets[{index}] unknown reset action: {action}")


def _validate_nonnegative_number(value: object, name: str, errors: list[str]) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or float(value) < 0.0
    ):
        errors.append(f"{name} must be non-negative")


def _positive_integer(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"expected numeric value, got {value!r}")
    return float(value)


def _registered(value: object, allowed: Collection[str]) -> bool:
    return isinstance(value, str) and value in allowed


def _unknown_fields(raw: dict, allowed: Collection[str], path: str, errors: list[str]) -> None:
    for key in sorted(set(raw) - set(allowed), key=str):
        errors.append(f"{path} unknown field: {key}")


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ScenarioDefinitionError([f"duplicate JSON key: {key}"])
        result[key] = value
    return result


def _validate_policy_sections(raw: dict, errors: list[str]) -> None:
    sections = {
        "coalescing": {"key", "windowS", "terminalQuietPeriodS", "policy"},
        "terminalPolicy": {"retainForS", "then", "lateFramesMayReopen"},
        "director": {
            "beatTiers",
            "sameBatchPolicy",
            "closure",
            "directClosureEdge",
            "confidencePolicy",
            "llmMayChangeFacts",
        },
        "conflicts": {
            "nearbyOpponent",
            "pitRoad",
            "playerFinished",
            "newIncidentOutsideCoalesceWindow",
            "sameBatchIncidentAndAftermath",
        },
    }
    for section, allowed in sections.items():
        if section not in raw:
            continue
        payload = raw[section]
        if not isinstance(payload, dict):
            errors.append(f"{section} must be an object")
            continue
        _unknown_fields(payload, allowed, section, errors)
        for key, value in payload.items():
            if key.endswith("S"):
                _validate_nonnegative_number(value, f"{section}.{key}", errors)

    # Policy strings are reviewed IDs, never implicit instructions to the engine.
    policies: dict[str, dict[str, Any]] = {
        "coalescing": {"policy": "update_active_episode_else_start_new"},
        "terminalPolicy": {
            "then": "release_episode_and_return_to_idle",
            "lateFramesMayReopen": False,
        },
        "director": {
            "sameBatchPolicy": "prefer_incident_over_aftermath",
            "directClosureEdge": "allow_incident_to_back_under_way_when_aftermath_was_not_spoken",
            "confidencePolicy": "within_tier_only",
            "llmMayChangeFacts": False,
        },
        "conflicts": {
            "nearbyOpponent": "context_only_never_assign_cause",
            "pitRoad": "do_not_suppress_incident_truth",
            "playerFinished": "allow_detection_director_owns_speech",
            "newIncidentOutsideCoalesceWindow": "start_new_episode_after_current_terminal_or_timeout",
            "sameBatchIncidentAndAftermath": "emit_both_prefer_incident_for_speech",
        },
    }
    for section, fields in policies.items():
        payload = raw.get(section)
        if not isinstance(payload, dict):
            continue
        for key, expected in fields.items():
            if key in payload and (
                type(payload[key]) is not type(expected) or payload[key] != expected
            ):
                errors.append(f"{section}.{key} has unregistered policy: {payload[key]!r}")
    director = raw.get("director")
    if not isinstance(director, dict):
        return
    closure = director.get("closure")
    if closure is not None:
        if not isinstance(closure, dict):
            errors.append("director.closure must be an object")
        else:
            _unknown_fields(
                closure,
                {"eventType", "requiresSameParentStory", "maxGapS"},
                "director.closure",
                errors,
            )
            _validate_nonnegative_number(closure.get("maxGapS"), "director.closure.maxGapS", errors)
            if closure.get("requiresSameParentStory") is not True:
                errors.append("director.closure.requiresSameParentStory must be true")
