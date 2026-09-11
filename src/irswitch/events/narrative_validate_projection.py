"""Commentary-runtime/2 offline validate projection (#273 / #284).

Pure library helper for ``POST /api/commentary/runtime/validate``. Validates
caller-supplied EN text against one beat id and immutable actor/fact bindings.
Does not read live NarrativeRuntime state, roster, or Qwen. Not exported from
``events/__init__.py``.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from irswitch.contracts.primitives import ContractViolation

SCHEMA_VERSION = "commentary-runtime/2"
FACT_SCHEMA = "atomic-fact/2"
_BEAT_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ACTOR_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_ISSUE_MESSAGE_CAP = 256

_ACTOR_REVERSED_MESSAGE = "Actor direction is reversed."


def _normalize_alias(alias: str) -> str:
    return " ".join(alias.split()).casefold()


def _require_mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ContractViolation(f"{label} must be an object")
    return value


def _require_string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise ContractViolation(f"{label} must be a string")
    return value


def _parse_actor_bindings(raw: object) -> list[tuple[str, tuple[str, ...]]]:
    if not isinstance(raw, list):
        raise ContractViolation("actorBindings must be an array")
    if len(raw) > 16:
        raise ContractViolation("actorBindings exceeds capacity")
    seen_actors: set[str] = set()
    seen_aliases: dict[str, str] = {}
    bindings: list[tuple[str, tuple[str, ...]]] = []
    for index, item in enumerate(raw):
        row = _require_mapping(item, f"actorBindings[{index}]")
        actor_id = _require_string(row.get("actorId"), f"actorBindings[{index}].actorId")
        if not _ACTOR_ID.match(actor_id):
            raise ContractViolation(f"actorBindings[{index}].actorId is invalid")
        if actor_id in seen_actors:
            raise ContractViolation("actorBindings actorId values must be unique")
        seen_actors.add(actor_id)
        aliases_raw = row.get("aliases")
        if not isinstance(aliases_raw, list) or not aliases_raw or len(aliases_raw) > 8:
            raise ContractViolation(f"actorBindings[{index}].aliases must contain 1–8 aliases")
        aliases: list[str] = []
        local: set[str] = set()
        for alias in aliases_raw:
            if not isinstance(alias, str):
                raise ContractViolation(f"actorBindings[{index}].aliases must be strings")
            normalized = " ".join(alias.split())
            key = normalized.casefold()
            if not key or len(normalized) > 64 or key in local:
                raise ContractViolation(f"actorBindings[{index}].aliases is invalid")
            previous = seen_aliases.get(key)
            if previous is not None and previous != actor_id:
                raise ContractViolation("actorBindings aliases collide across actorIds")
            seen_aliases[key] = actor_id
            local.add(key)
            aliases.append(normalized)
        bindings.append((actor_id, tuple(aliases)))
    return bindings


def _parse_fact_bindings(raw: object) -> list[dict[str, Any]]:
    if not isinstance(raw, list):
        raise ContractViolation("factBindings must be an array")
    if not raw or len(raw) > 32:
        raise ContractViolation("factBindings must contain 1–32 facts")
    seen_ids: set[str] = set()
    facts: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        row = _require_mapping(item, f"factBindings[{index}]")
        schema = row.get("schemaVersion")
        if schema != FACT_SCHEMA:
            raise ContractViolation(f"factBindings[{index}].schemaVersion must be {FACT_SCHEMA}")
        fact_id = _require_string(row.get("factId"), f"factBindings[{index}].factId")
        if fact_id in seen_ids:
            raise ContractViolation("factBindings factId values must be unique")
        seen_ids.add(fact_id)
        predicate = _require_string(row.get("predicate"), f"factBindings[{index}].predicate")
        if not _ACTOR_ID.match(predicate):
            raise ContractViolation(f"factBindings[{index}].predicate is invalid")
        subject = row.get("subjectId")
        object_id = row.get("objectId")
        if subject is not None:
            subject = _require_string(subject, f"factBindings[{index}].subjectId")
            if not _ACTOR_ID.match(subject):
                raise ContractViolation(f"factBindings[{index}].subjectId is invalid")
        if object_id is not None:
            object_id = _require_string(object_id, f"factBindings[{index}].objectId")
            if not _ACTOR_ID.match(object_id):
                raise ContractViolation(f"factBindings[{index}].objectId is invalid")
        facts.append(
            {
                "factId": fact_id,
                "predicate": predicate,
                "subjectId": subject,
                "objectId": object_id,
            }
        )
    return facts


def _first_alias_hits(
    text: str, actor_bindings: Sequence[tuple[str, tuple[str, ...]]]
) -> list[tuple[int, str]]:
    """Return (start_index, actorId) for each bound actor's earliest alias hit."""

    folded = text.casefold()
    hits: list[tuple[int, str]] = []
    for actor_id, aliases in actor_bindings:
        best: int | None = None
        for alias in sorted(aliases, key=len, reverse=True):
            key = _normalize_alias(alias)
            start = 0
            while True:
                idx = folded.find(key, start)
                if idx < 0:
                    break
                before_ok = idx == 0 or not folded[idx - 1].isalnum()
                end = idx + len(key)
                after_ok = end >= len(folded) or not folded[end].isalnum()
                if before_ok and after_ok:
                    best = idx if best is None else min(best, idx)
                    break
                start = idx + 1
        if best is not None:
            hits.append((best, actor_id))
    hits.sort(key=lambda item: item[0])
    return hits


def _shape_issues(text: str) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    stripped = text.strip()
    if not stripped:
        issues.append(
            {"code": "empty", "severity": "error", "message": "Text is empty."[:_ISSUE_MESSAGE_CAP]}
        )
        return issues
    if len(stripped) > 512:
        issues.append(
            {
                "code": "too_long",
                "severity": "error",
                "message": "Text exceeds 512 characters."[:_ISSUE_MESSAGE_CAP],
            }
        )
    return issues


def project_validate_response(request: Mapping[str, Any]) -> dict[str, Any]:
    """Project one ValidateRequest into a commentary-runtime/2 ValidateResponse.

    Raises ``ContractViolation`` for malformed requests (HTTP 400). Syntactically
    valid requests always return a response body; ``valid`` is false when any
    issue has severity ``error``.
    """

    body = _require_mapping(request, "ValidateRequest")
    if body.get("schemaVersion") != SCHEMA_VERSION:
        raise ContractViolation("schemaVersion must be commentary-runtime/2")
    text = _require_string(body.get("text"), "text")
    if any(ord(char) < 32 for char in text):
        raise ContractViolation("text must not contain control characters")
    if not 1 <= len(text) <= 512:
        raise ContractViolation("text must be 1–512 characters")
    beat_id = _require_string(body.get("beatId"), "beatId")
    if not _BEAT_ID.match(beat_id):
        raise ContractViolation("beatId is invalid")
    evaluation = body.get("evaluationAtMonoMs")
    if isinstance(evaluation, bool) or not isinstance(evaluation, int) or evaluation < 0:
        raise ContractViolation("evaluationAtMonoMs must be a nonnegative integer")

    actor_bindings = _parse_actor_bindings(body.get("actorBindings"))
    fact_bindings = _parse_fact_bindings(body.get("factBindings"))

    required_actors: set[str] = set()
    for fact in fact_bindings:
        if fact["subjectId"] is not None:
            required_actors.add(str(fact["subjectId"]))
        if fact["objectId"] is not None:
            required_actors.add(str(fact["objectId"]))
    bound_actors = {actor_id for actor_id, _aliases in actor_bindings}
    if bound_actors != required_actors:
        raise ContractViolation("actorBindings must cover fact actors exactly")

    issues = _shape_issues(text)
    claims: list[dict[str, Any]] = []
    if not issues:
        hits = _first_alias_hits(text, actor_bindings)
        ordered_actors = [actor_id for _idx, actor_id in hits]
        for fact in fact_bindings:
            subject = fact["subjectId"]
            object_id = fact["objectId"]
            predicate = str(fact["predicate"])
            if subject is None or object_id is None:
                claims.append(
                    {
                        "predicate": predicate,
                        "subjectId": subject,
                        "objectId": object_id,
                        "verdict": "ambiguous",
                    }
                )
                continue
            if len(ordered_actors) < 2:
                claims.append(
                    {
                        "predicate": predicate,
                        "subjectId": subject,
                        "objectId": object_id,
                        "verdict": "unsupported",
                    }
                )
                issues.append(
                    {
                        "code": "required_missing",
                        "severity": "error",
                        "message": "Required actors were not found in text."[:_ISSUE_MESSAGE_CAP],
                    }
                )
                continue
            parsed_subject, parsed_object = ordered_actors[0], ordered_actors[1]
            if parsed_subject == subject and parsed_object == object_id:
                claims.append(
                    {
                        "predicate": predicate,
                        "subjectId": subject,
                        "objectId": object_id,
                        "verdict": "supported",
                    }
                )
            elif parsed_subject == object_id and parsed_object == subject:
                claims.append(
                    {
                        "predicate": predicate,
                        "subjectId": parsed_subject,
                        "objectId": parsed_object,
                        "verdict": "unsupported",
                    }
                )
                issues.append(
                    {
                        "code": "actor_reversed",
                        "severity": "error",
                        "message": _ACTOR_REVERSED_MESSAGE[:_ISSUE_MESSAGE_CAP],
                    }
                )
            else:
                claims.append(
                    {
                        "predicate": predicate,
                        "subjectId": parsed_subject,
                        "objectId": parsed_object,
                        "verdict": "unsupported",
                    }
                )
                issues.append(
                    {
                        "code": "unknown_entity",
                        "severity": "error",
                        "message": "Bound actors do not match the fact frame."[:_ISSUE_MESSAGE_CAP],
                    }
                )

    valid = not any(issue["severity"] == "error" for issue in issues)
    return {
        "schemaVersion": SCHEMA_VERSION,
        "valid": valid,
        "beatId": beat_id,
        "issues": issues,
        "claims": claims,
    }


__all__ = ["FACT_SCHEMA", "SCHEMA_VERSION", "project_validate_response"]
