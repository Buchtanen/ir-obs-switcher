"""V4 event envelope types for the overlay WebSocket wire format.

Emitters produce EventEnvelope-shaped payloads. The manager may still stamp
``sequence`` / ``eventId`` and rewrite ``phase`` during arbitration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, fields
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

EventMode = Literal["PRACTICE", "QUALIFYING", "RACE", "GENERIC", "unknown"]

WIRE_MODES: frozenset[str] = frozenset({"PRACTICE", "QUALIFYING", "RACE", "GENERIC", "unknown"})
UNKNOWN_MODE = "unknown"

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


def _snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def _snake_keys(data: dict[str, Any]) -> dict[str, Any]:
    return {_snake(key): value for key, value in data.items()}


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
            "target": self.target.to_dict() if self.target is not None else None,
            "metrics": dict(self.metrics),
            "copy": self.copy.to_dict(),
            "presentation": self.presentation.to_dict(),
            "reason": self.reason.to_dict(),
        }
        return payload

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> EventEnvelope:
        """Rebuild an envelope from its wire form. Unknown keys are ignored."""
        payload = _snake_keys(data)
        known = {f.name for f in fields(cls)}
        return make_envelope(**{key: value for key, value in payload.items() if key in known})

    def stamp(self, event_id: str, sequence: int) -> EventEnvelope:
        """Manager-side identity stamp applied after arbitration. Returns self."""
        self.event_id = event_id
        self.sequence = sequence
        return self


def legacy_trigger_to_phase(phase: str, default: str | None = None) -> str:
    """Map legacy MVP phases (enter/update/exit/trigger) to wire phases.

    Raises ValueError on unknown input so mapping bugs surface in tests. Hot-path
    callers pass ``default`` to stay fail-soft instead.
    """
    key = (phase or "").strip() if isinstance(phase, str) else ""
    if key.upper() in WIRE_PHASES:
        return key.upper()
    mapped = _LEGACY_PHASE_MAP.get(key.lower())
    if mapped is None:
        if default is not None:
            return default
        raise ValueError(f"unknown event phase: {phase!r}")
    return mapped


def normalize_mode(mode: Any) -> str:
    """Map a session mode onto the wire whitelist. Anything else becomes ``unknown``."""
    if not isinstance(mode, str):
        return UNKNOWN_MODE
    candidate = mode.strip().upper()
    return candidate if candidate in WIRE_MODES else UNKNOWN_MODE


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
    mode = data.get("mode")
    if mode is not None and mode not in WIRE_MODES:
        errors.append(f"invalid mode: {mode!r}")
    confidence = data.get("confidence")
    if confidence is not None:
        try:
            conf = float(confidence)
            if conf < 0.0 or conf > 1.0:
                errors.append(f"confidence out of range: {conf}")
        except (TypeError, ValueError):
            errors.append(f"confidence not numeric: {confidence!r}")
    return errors


def _coerce_section(value: Any, section: type) -> Any:
    """Accept a dataclass instance, a snake_case dict or a camelCase wire dict."""
    if isinstance(value, section):
        return value
    payload = _snake_keys(value or {})
    allowed = {f.name for f in fields(section)}
    kept = {key: val for key, val in payload.items() if key in allowed}
    if section is EventReason:
        for key in ("rules", "suppressed_alternatives"):
            if key in kept:
                kept[key] = tuple(kept[key])
    return section(**kept)


def make_envelope(**kwargs: Any) -> EventEnvelope:
    """Test/helper factory with sensible defaults for a valid envelope.

    Accepts camelCase or snake_case keys at the top level and inside the nested
    sections, so a wire dict can be fed straight back in.
    """
    kwargs = _snake_keys(kwargs)
    event_type = str(kwargs.pop("event_type", "LAP_COMPLETE"))
    phase = legacy_trigger_to_phase(str(kwargs.pop("phase", "ENTER")))
    if "mode" in kwargs:
        kwargs["mode"] = normalize_mode(kwargs["mode"])

    target_raw = kwargs.pop("target", None)
    subject = _coerce_section(kwargs.pop("subject", None), EventSubject)
    target = None if target_raw is None else _coerce_section(target_raw, EventSubject)
    copy = _coerce_section(kwargs.pop("copy", None), EventCopy)
    presentation = _coerce_section(kwargs.pop("presentation", None), EventPresentation)
    reason = _coerce_section(kwargs.pop("reason", None), EventReason)

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
