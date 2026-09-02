"""Immutable N12 accepted-event stream contracts.

Mutable :class:`EventEnvelope` values end at ``freeze_envelope``.  Everything
past this boundary is composed only of frozen dataclasses, primitives, tuples,
and canonical UTF-8 JSON bytes so the in-process V2a transport is also safe for
deterministic replay and a possible Windows-spawned V2b transport.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal, TypeAlias

from irswitch.events.envelope import EventEnvelope, validate_envelope

FrozenEnvelope: TypeAlias = bytes
FrozenContextSnapshot: TypeAlias = bytes
FrozenConfigSnapshot: TypeAlias = bytes
Audience: TypeAlias = Literal["overlay", "commentary"]

CONTEXT_SCHEMA_VERSION = "n12-context/1"


class StreamContractError(ValueError):
    """A producer tried to publish data outside the frozen stream contract."""


@dataclass
class SessionSequenceAllocator:
    """The sole event-id/sequence allocator for one producer session."""

    session_id: str = "session:unknown"
    sequence: int = 0

    def reset(self, session_id: str) -> None:
        self.session_id = session_id or "session:unknown"
        self.sequence = 0

    def stamp(self, envelope: EventEnvelope) -> EventEnvelope:
        self.sequence += 1
        envelope.session_id = self.session_id
        return envelope.stamp(
            f"{self.session_id}:{envelope.event_type}:{self.sequence}",
            self.sequence,
        )


def canonical_json_bytes(value: object) -> bytes:
    """Encode JSON deterministically and reject NaN/non-JSON values."""
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise StreamContractError(f"value is not canonical JSON: {exc}") from exc


def decode_canonical_json(payload: bytes, *, label: str) -> dict[str, Any]:
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StreamContractError(f"invalid frozen {label}: {exc}") from exc
    if not isinstance(decoded, dict):
        raise StreamContractError(f"frozen {label} must decode to an object")
    return decoded


def freeze_envelope(envelope: EventEnvelope) -> FrozenEnvelope:
    """Validate and encode one already-stamped envelope as canonical JSON."""
    if not envelope.event_id:
        raise StreamContractError("event_id must be assigned before freeze")
    if envelope.sequence <= 0:
        raise StreamContractError("sequence must be positive before freeze")
    errors = validate_envelope(envelope)
    if errors:
        raise StreamContractError("invalid envelope: " + "; ".join(errors))
    return canonical_json_bytes(envelope.to_dict())


def thaw_envelope(payload: FrozenEnvelope) -> EventEnvelope:
    """Return a new consumer-owned envelope from canonical JSON."""
    envelope = EventEnvelope.from_dict(decode_canonical_json(payload, label="envelope"))
    errors = validate_envelope(envelope)
    if errors:
        raise StreamContractError("invalid thawed envelope: " + "; ".join(errors))
    return envelope


def freeze_context(payload: dict[str, Any]) -> FrozenContextSnapshot:
    """Validate the minimal A3 identity and freeze a complete context mapping."""
    if payload.get("schema_version") != CONTEXT_SCHEMA_VERSION:
        raise StreamContractError(f"context schema_version must be {CONTEXT_SCHEMA_VERSION!r}")
    if int(payload.get("version") or 0) <= 0:
        raise StreamContractError("context version must be positive")
    if not str(payload.get("session_id") or ""):
        raise StreamContractError("context session_id must be non-empty")
    if int(payload.get("captured_monotonic_ms") or -1) < 0:
        raise StreamContractError("context captured_monotonic_ms must be non-negative")
    return canonical_json_bytes(payload)


def thaw_context(payload: FrozenContextSnapshot) -> dict[str, Any]:
    context = decode_canonical_json(payload, label="context")
    # Reuse the validation without retaining the second encoded result.
    freeze_context(context)
    return context


def freeze_config(payload: dict[str, Any]) -> FrozenConfigSnapshot:
    if int(payload.get("generation") or 0) < 0:
        raise StreamContractError("config generation must be non-negative")
    return canonical_json_bytes(payload)


def thaw_config(payload: FrozenConfigSnapshot) -> dict[str, Any]:
    return decode_canonical_json(payload, label="config")


@dataclass(frozen=True)
class FrozenAcceptedEvent:
    envelope: FrozenEnvelope
    audiences: tuple[Audience, ...]
    source: str
    source_ordinal: int
    coalesce_key: tuple[str, ...] | None
    event_id: str
    sequence: int
    phase: str
    priority: int
    overlay_payload: bytes | None = None
    story_payload: bytes | None = None

    def __post_init__(self) -> None:
        if not self.audiences:
            raise StreamContractError("accepted event must have at least one audience")
        if any(item not in {"overlay", "commentary"} for item in self.audiences):
            raise StreamContractError("accepted event has an unknown audience")
        if not self.source:
            raise StreamContractError("accepted event source must be non-empty")
        if self.source_ordinal < 0:
            raise StreamContractError("source_ordinal must be non-negative")
        if not self.event_id or self.sequence <= 0:
            raise StreamContractError("accepted event identity must be stamped")

    @property
    def coalescible(self) -> bool:
        return self.phase in {"ACTIVE", "UPDATE"} and self.coalesce_key is not None


def freeze_accepted_event(
    envelope: EventEnvelope,
    *,
    audiences: tuple[Audience, ...],
    source: str,
    source_ordinal: int,
    coalesce_key: tuple[str, ...] | None = None,
    overlay_payload: dict[str, Any] | None = None,
    story_payload: dict[str, Any] | None = None,
) -> FrozenAcceptedEvent:
    return FrozenAcceptedEvent(
        envelope=freeze_envelope(envelope),
        audiences=tuple(dict.fromkeys(audiences)),
        source=source,
        source_ordinal=source_ordinal,
        coalesce_key=coalesce_key,
        event_id=envelope.event_id,
        sequence=envelope.sequence,
        phase=envelope.phase,
        priority=int(envelope.priority),
        overlay_payload=(
            canonical_json_bytes(overlay_payload) if overlay_payload is not None else None
        ),
        story_payload=(canonical_json_bytes(story_payload) if story_payload is not None else None),
    )


def thaw_story_payload(payload: bytes) -> dict[str, Any]:
    return decode_canonical_json(payload, label="mini-story")


@dataclass(frozen=True)
class FrozenAcceptedEventBatch:
    stream_sequence: int
    session_id: str
    batch_sequence: int
    accepted_monotonic_ms: int
    context_version: int
    context_payload: FrozenContextSnapshot
    events: tuple[FrozenAcceptedEvent, ...]

    def __post_init__(self) -> None:
        if self.stream_sequence <= 0 or self.batch_sequence <= 0:
            raise StreamContractError("stream and batch sequence must be positive")
        if not self.session_id:
            raise StreamContractError("batch session_id must be non-empty")
        if self.accepted_monotonic_ms < 0:
            raise StreamContractError("accepted_monotonic_ms must be non-negative")
        if self.context_version <= 0:
            raise StreamContractError("context_version must be positive")
        if not self.events:
            raise StreamContractError("empty accepted event batches are forbidden")
        context = thaw_context(self.context_payload)
        if context["version"] != self.context_version:
            raise StreamContractError("batch context version does not match payload")
        if context["session_id"] != self.session_id:
            raise StreamContractError("batch session id does not match context")


@dataclass(frozen=True)
class SessionReset:
    old_session_id: str
    new_session_id: str
    reason: str
    stream_sequence: int

    def __post_init__(self) -> None:
        if not self.new_session_id or self.stream_sequence <= 0:
            raise StreamContractError("invalid SessionReset identity")


@dataclass(frozen=True)
class ConfigUpdate:
    generation: int
    frozen_config: FrozenConfigSnapshot
    stream_sequence: int

    def __post_init__(self) -> None:
        if self.generation < 0 or self.stream_sequence <= 0:
            raise StreamContractError("invalid ConfigUpdate identity")


StreamItem: TypeAlias = FrozenAcceptedEventBatch | SessionReset | ConfigUpdate


@dataclass(frozen=True)
class FillerRequest:
    request_id: str
    session_id: str
    requested_monotonic_ms: int
    locale: str
    last_spoken_event_id: str | None = None


@dataclass(frozen=True)
class FillerResult:
    request_id: str
    status: Literal["no_fact", "stale", "disabled"]


def event_ids(item: StreamItem) -> tuple[str, ...]:
    if isinstance(item, FrozenAcceptedEventBatch):
        return tuple(event.event_id for event in item.events)
    return ()
