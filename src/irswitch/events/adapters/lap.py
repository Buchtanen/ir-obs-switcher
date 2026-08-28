"""Candidate / RaceEvent → EventEnvelope adapters (S1: lap slice)."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from irswitch.events.envelope import (
    EventCopy,
    EventEnvelope,
    EventPresentation,
    legacy_trigger_to_phase,
    make_envelope,
    normalize_mode,
)
from irswitch.overlay.protocol import RaceEvent

_LAP_EVENT_TYPES = frozenset({"lap_complete", "personal_best"})


def lap_race_event_to_envelope(
    event: RaceEvent,
    *,
    session_id: str,
    mode: str,
    now: float,
) -> EventEnvelope | None:
    if event.name not in _LAP_EVENT_TYPES:
        return None
    event_type = "PERSONAL_BEST" if event.name == "personal_best" else "LAP_COMPLETE"
    phase = legacy_trigger_to_phase(event.phase, default="RESULT")
    lap = event.data.get("lap")
    lap_time = event.data.get("lapTime")
    best = event.data.get("bestLap")
    delta = event.data.get("deltaToBest")
    copy_token = "lap.personal_best" if event_type == "PERSONAL_BEST" else "lap.complete"
    metrics: dict[str, object] = {}
    if lap is not None:
        metrics["lap"] = lap
    if lap_time is not None:
        metrics["lapTime"] = lap_time
    if best is not None:
        metrics["bestLap"] = best
    if delta is not None:
        metrics["deltaToBest"] = delta
    return make_envelope(
        event_type=event_type,
        phase=phase,
        mode=normalize_mode(mode),
        session_id=session_id or "session:unknown",
        occurred_at=datetime.fromtimestamp(time.time(), tz=UTC).isoformat(),
        monotonic_ms=int(now * 1000),
        priority=event.priority,
        dedupe_key=f"{normalize_mode(mode)}:{event_type}:{lap}",
        correlation_id=f"lap:{lap}",
        metrics=metrics,
        copy=EventCopy(headline_token=copy_token, status_token=""),
        presentation=EventPresentation(
            widget="timing",
            zone="EVENT",
            variant=event.name,
            accent="primary",
            preferred_state="RESULT",
        ),
    )
