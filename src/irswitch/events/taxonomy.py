"""Immutable event-type policy derived from the packaged v2 freeze registry."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from irswitch.contracts import Identifier, Sha256Hash, packaged_schema_bytes


class NarrativeAdmissionError(ValueError):
    """An accepted V4 identifier has no valid narrative route."""


@dataclass(frozen=True, slots=True)
class NarrativeEventPolicy:
    event_type: Identifier
    event_class: str
    narrative_kind: Identifier
    tape_channel: Identifier


@lru_cache(maxsize=1)
def _registry() -> dict[str, Any]:
    value = json.loads(packaged_schema_bytes("freeze-registry.json"))
    if not isinstance(value, dict):
        raise NarrativeAdmissionError("packaged taxonomy registry must be an object")
    return value


@lru_cache(maxsize=1)
def narrative_taxonomy_hash() -> str:
    digest = hashlib.sha256(packaged_schema_bytes("freeze-registry.json")).hexdigest()
    return str(Sha256Hash(f"sha256:{digest}"))


@lru_cache(maxsize=1)
def _policies() -> dict[str, NarrativeEventPolicy]:
    registry = _registry()
    channels = registry.get("tapeChannels")
    entries = registry.get("eventIdentifiers")
    if not isinstance(channels, list) or not isinstance(entries, list):
        raise NarrativeAdmissionError("packaged taxonomy registry is incomplete")
    allowed_channels = frozenset(channels)
    result: dict[str, NarrativeEventPolicy] = {}
    for raw in entries:
        if not isinstance(raw, dict):
            raise NarrativeAdmissionError("event taxonomy entry must be an object")
        event_type = raw.get("id")
        event_class = raw.get("eventClass")
        narrative_kind = raw.get("narrativeKind")
        tape_channel = raw.get("tapeChannel")
        if (
            not isinstance(event_type, str)
            or not isinstance(event_class, str)
            or not isinstance(tape_channel, str)
        ):
            raise NarrativeAdmissionError("event taxonomy entry has invalid identity")
        if tape_channel not in allowed_channels:
            raise NarrativeAdmissionError(f"event {event_type!r} has an unknown tape channel")
        if event_type in result:
            raise NarrativeAdmissionError(f"duplicate event taxonomy entry: {event_type}")
        if event_class == "speakable":
            if not isinstance(narrative_kind, str):
                raise NarrativeAdmissionError(
                    f"speakable event {event_type!r} has no narrative kind"
                )
            result[event_type] = NarrativeEventPolicy(
                Identifier(event_type),
                event_class,
                Identifier(narrative_kind),
                Identifier(tape_channel),
            )
        elif event_class not in {"visual_only", "compatibility_alias"}:
            raise NarrativeAdmissionError(f"event {event_type!r} has invalid event class")
    return result


def validate_narrative_taxonomy() -> None:
    registry = _registry()
    entries = registry.get("eventIdentifiers")
    assert isinstance(entries, list)
    policies = _policies()
    expected = sum(
        1 for entry in entries if isinstance(entry, dict) and entry.get("eventClass") == "speakable"
    )
    if len(policies) != expected:
        raise NarrativeAdmissionError("narrative taxonomy lost a speakable event")


def narrative_policy_for_event_type(event_type: str) -> NarrativeEventPolicy:
    normalized = event_type.strip().upper() if isinstance(event_type, str) else ""
    policy = _policies().get(normalized)
    if policy is not None:
        return policy
    entries = _registry().get("eventIdentifiers")
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and entry.get("id") == normalized:
                raise NarrativeAdmissionError(
                    f"event {normalized!r} is {entry.get('eventClass')} and cannot enter narrative"
                )
    raise NarrativeAdmissionError(f"unregistered narrative event type: {event_type!r}")
