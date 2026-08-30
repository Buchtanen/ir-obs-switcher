"""Bounded history of published overlay lifecycle events."""

from __future__ import annotations

import logging
import math
import time
from collections import deque
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any, TypedDict

from irswitch.events.envelope import legacy_trigger_to_phase

logger = logging.getLogger(__name__)

DEFAULT_CAPACITY = 128


class OverlayActivityRow(TypedDict):
    """Admin-ready representation of one published lifecycle transition."""

    occurredAt: float
    monoMs: int
    dedupeKey: str
    source: str
    kind: str
    phase: str
    message: str
    ephemeral: bool


class OverlayActivityLog:
    """FIFO ring populated from event publication, independent of WS clients."""

    def __init__(
        self,
        capacity: int = DEFAULT_CAPACITY,
        *,
        wall_clock: Callable[[], float] = time.time,
        monotonic_clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if capacity <= 0:
            raise ValueError("capacity must be positive")
        self._rows: deque[OverlayActivityRow] = deque(maxlen=capacity)
        self._wall_clock = wall_clock
        self._monotonic_clock = monotonic_clock

    def add(self, envelope: Mapping[str, Any]) -> bool:
        """Append a lifecycle envelope, returning false when it is malformed."""
        try:
            row = self._row_from_envelope(envelope)
        except Exception as exc:
            logger.debug("Skipping overlay lifecycle envelope: %s", exc)
            return False
        self._rows.append(row)
        return True

    def latest(self, n: int) -> list[OverlayActivityRow]:
        """Return up to ``n`` rows, newest first, as defensive copies."""
        limit = max(0, int(n))
        rows = list(self._rows)
        return [row.copy() for row in reversed(rows[-limit:])] if limit else []

    def clear(self) -> None:
        self._rows.clear()

    def _row_from_envelope(self, envelope: Mapping[str, Any]) -> OverlayActivityRow:
        if not isinstance(envelope, Mapping):
            raise TypeError("envelope is not a mapping")
        envelope_type = envelope.get("type")
        if envelope_type is not None and (
            not isinstance(envelope_type, str) or envelope_type.lower() != "event"
        ):
            raise ValueError("envelope is not an event")

        kind = _required_text(envelope.get("eventType") or envelope.get("name"), "event kind")
        phase_raw = _required_text(envelope.get("phase"), "phase")
        phase = legacy_trigger_to_phase(phase_raw)

        wall_now = _finite_float(self._wall_clock(), "wall clock")
        mono_now = _finite_float(self._monotonic_clock(), "monotonic clock")
        mono_ms, has_event_mono = _event_monotonic_ms(envelope, mono_now)
        occurred_at = (
            wall_now - (mono_now - mono_ms / 1000.0)
            if has_event_mono
            else _event_wall_time(envelope, wall_now)
        )
        message_raw = envelope.get("message")
        message = (
            message_raw.strip()
            if isinstance(message_raw, str) and message_raw.strip()
            else f"Widget {kind} ({phase})"
        )

        return {
            "occurredAt": occurred_at,
            "monoMs": mono_ms,
            "dedupeKey": _dedupe_key(envelope, kind, phase, mono_ms),
            "source": "overlay",
            "kind": kind,
            "phase": phase,
            "message": message,
            "ephemeral": False,
        }


def _event_monotonic_ms(envelope: Mapping[str, Any], mono_now: float) -> tuple[int, bool]:
    raw_ms = envelope.get("monotonicMs")
    if raw_ms is not None:
        mono_ms = int(_finite_float(raw_ms, "monotonicMs"))
        if mono_ms < 0:
            raise ValueError("monotonicMs must not be negative")
        if mono_ms > 0:
            return mono_ms, True

    for key in ("timestamp", "at", "ts"):
        raw_seconds = envelope.get(key)
        if raw_seconds is None:
            continue
        seconds = _finite_float(raw_seconds, key)
        if seconds < 0:
            raise ValueError(f"{key} must not be negative")
        if seconds > 0:
            return int(seconds * 1000), True

    return int(mono_now * 1000), False


def _event_wall_time(envelope: Mapping[str, Any], fallback: float) -> float:
    raw = envelope.get("occurredAt")
    if raw is None:
        return fallback
    if isinstance(raw, (int, float)) and not isinstance(raw, bool):
        return _finite_float(raw, "occurredAt")
    if isinstance(raw, str):
        value = raw.strip()
        if value:
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp()
            except ValueError:
                pass
    return fallback


def _dedupe_key(
    envelope: Mapping[str, Any],
    kind: str,
    phase: str,
    mono_ms: int,
) -> str:
    explicit = envelope.get("dedupeKey")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    for key in ("correlationId", "storyKey", "eventId"):
        identity = envelope.get(key)
        if isinstance(identity, str) and identity.strip():
            return f"overlay:{kind}:{phase}:{identity.strip()}"
    return f"overlay:{kind}:{phase}:{mono_ms}"


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"missing {label}")
    return value.strip()


def _finite_float(value: Any, label: str) -> float:
    if isinstance(value, bool):
        raise ValueError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{label} must be finite")
    return number
