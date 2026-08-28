"""V4 event envelope types for the overlay WebSocket wire format.

Emitters produce EventEnvelope-shaped payloads. The manager may still stamp
``sequence`` / ``eventId`` and rewrite ``phase`` during arbitration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

SCHEMA_VERSION = "1.0"

EventPhase = Literal[
    "ENTER",
    "ACTIVE",
    "UPDATE",
    "COMPACT",
    "SUSPEND",
    "RESUME",
    "EXIT",
    "RESULT",
]

WIRE_PHASES: frozenset[str] = frozenset(
    {"ENTER", "ACTIVE", "UPDATE", "COMPACT", "SUSPEND", "RESUME", "EXIT", "RESULT"}
)

_LEGACY_PHASE_MAP: dict[str, str] = {
    "enter": "ENTER",
    "active": "ACTIVE",
    "update": "UPDATE",
    "compact": "COMPACT",
    "suspend": "SUSPEND",
    "resume": "RESUME",
    "exit": "EXIT",
    "result": "RESULT",
    "trigger": "RESULT",
}

_REQUIRED_TOP_LEVEL: tuple[str, ...] = (
    "schemaVersion",
    "eventId",
    "sequence",
    "sessionId",
    "eventType",
    "mode",
    "phase",
    "priority",
    "dedupeKey",
    "correlationId",
)


@dataclass(frozen=True)
class EventSubject:
    car_id: str = "player"
    display_name: str | None = None
    car_number: str | None = None
    class_position: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "carId": self.car_id,
            "displayName": self.display_name,
            "carNumber": self.car_number,
            "classPosition": self.class_position,
        }


@dataclass(frozen=True)
class EventCopy:
    headline_token: str = ""
    status_token: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "headlineToken": self.headline_token,
            "statusToken": self.status_token,
        }


@dataclass(frozen=True)
class EventPresentation:
    widget: str = ""
    zone: str = "EVENT"
    variant: str = ""
    accent: str = "primary"
    preferred_state: str = "ACTIVE"
    min_hold_ms: int = 2500
    max_hold_ms: int = 12000

    def to_dict(self) -> dict[str, Any]:
        return {
            "widget": self.widget,
            "zone": self.zone,
            "variant": self.variant,
            "accent": self.accent,
            "preferredState": self.preferred_state,
            "minHoldMs": self.min_hold_ms,
            "maxHoldMs": self.max_hold_ms,
        }


@dataclass(frozen=True)
class EventReason:
    detector: str = ""
    rules: tuple[str, ...] = ()
    suppressed_alternatives: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "detector": self.detector,
            "rules": list(self.rules),
            "suppressedAlternatives": list(self.suppressed_alternatives),
        }


@dataclass
class EventEnvelope:
    """Published / emitter-shaped V4 event payload."""

    event_type: str
    phase: str = "ENTER"
    mode: str = "GENERIC"
    schema_version: str = SCHEMA_VERSION
    event_id: str = ""
    sequence: int = 0
    session_id: str = ""
    occurred_at: str | None = None
    monotonic_ms: int = 0
    expires_at: str | None = None
    priority: int = 0
    severity: int = 0
    confidence: float = 1.0
    dedupe_key: str = ""
    correlation_id: str = ""
    story_key: str = ""
    subject: EventSubject = field(default_factory=EventSubject)
    target: EventSubject | None = None
    metrics: dict[str, Any] = field(default_factory=dict)
    copy: EventCopy = field(default_factory=EventCopy)
    presentation: EventPresentation = field(default_factory=EventPresentation)
    reason: EventReason = field(default_factory=EventReason)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "schemaVersion": self.schema_version,
            "eventId": self.event_id,
            "sequence": self.sequence,
            "sessionId": self.session_id,
            "eventType": self.event_type,
            "mode": self.mode,
            "phase": self.phase,
            "occurredAt": self.occurred_at,
            "monotonicMs": self.monotonic_ms,
            "expiresAt": self.expires_at,
            "priority": self.priority,
            "severity": self.severity,
            "confidence": self.confidence,
            "dedupeKey": self.dedupe_key,
            "correlationId": self.correlation_id,
            "storyKey": self.story_key or self.correlation_id,
            "subject": self.subject.to_dict(),
            "metrics": dict(self.metrics),
            "copy": self.copy.to_dict(),
            "presentation": self.presentation.to_dict(),
            "reason": self.reason.to_dict(),
        }
        if self.target is not None:
            payload["target"] = self.target.to_dict()
        return payload


def legacy_trigger_to_phase(phase: str) -> str:
    """Map legacy MVP phases (enter/update/exit/trigger) to wire phases."""
    key = (phase or "").strip()
    if key in WIRE_PHASES:
        return key
    mapped = _LEGACY_PHASE_MAP.get(key.lower())
    if mapped is None:
        raise ValueError(f"unknown event phase: {phase!r}")
    return mapped


def validate_envelope(value: EventEnvelope | dict[str, Any]) -> list[str]:
    """Return human-readable validation errors (empty = ok)."""
    data = value.to_dict() if isinstance(value, EventEnvelope) else dict(value)
    errors: list[str] = []
    for key in _REQUIRED_TOP_LEVEL:
        if key == "sequence":
            if "sequence" not in data or data["sequence"] is None:
                errors.append("missing sequence")
            continue
        if key not in data or data[key] in (None, ""):
            errors.append(f"missing {key}")
    phase = data.get("phase")
    if phase is not None and phase not in WIRE_PHASES:
        errors.append(f"invalid phase: {phase!r}")
    confidence = data.get("confidence")
    if confidence is not None:
        try:
            conf = float(confidence)
            if conf < 0.0 or conf > 1.0:
                errors.append(f"confidence out of range: {conf}")
        except (TypeError, ValueError):
            errors.append(f"confidence not numeric: {confidence!r}")
    return errors


def make_envelope(**kwargs: Any) -> EventEnvelope:
    """Test/helper factory with sensible defaults for a valid envelope."""
    if "eventType" in kwargs and "event_type" not in kwargs:
        kwargs["event_type"] = kwargs.pop("eventType")
    event_type = str(kwargs.pop("event_type", "LAP_COMPLETE"))
    phase_raw = kwargs.pop("phase", "ENTER")
    phase = legacy_trigger_to_phase(str(phase_raw))

    subject_raw = kwargs.pop("subject", None)
    target_raw = kwargs.pop("target", None)
    copy_raw = kwargs.pop("copy", None)
    presentation_raw = kwargs.pop("presentation", None)
    reason_raw = kwargs.pop("reason", None)

    subject = (
        subject_raw
        if isinstance(subject_raw, EventSubject)
        else EventSubject(**(subject_raw or {}))
    )
    target: EventSubject | None
    if target_raw is None:
        target = None
    elif isinstance(target_raw, EventSubject):
        target = target_raw
    else:
        target = EventSubject(**target_raw)
    copy = copy_raw if isinstance(copy_raw, EventCopy) else EventCopy(**(copy_raw or {}))
    presentation = (
        presentation_raw
        if isinstance(presentation_raw, EventPresentation)
        else EventPresentation(**(presentation_raw or {}))
    )
    reason = reason_raw if isinstance(reason_raw, EventReason) else EventReason(**(reason_raw or {}))

    env = EventEnvelope(
        event_type=event_type,
        phase=phase,
        subject=subject,
        target=target,
        copy=copy,
        presentation=presentation,
        reason=reason,
        **kwargs,
    )
    if not env.dedupe_key:
        env.dedupe_key = f"{env.mode}:{env.event_type}:{env.subject.car_id}"
    if not env.correlation_id:
        env.correlation_id = env.story_key or env.dedupe_key
    if not env.event_id:
        env.event_id = f"evt-{env.event_type}-{env.monotonic_ms}"
    if not env.session_id:
        env.session_id = "session:unknown"
    return env
