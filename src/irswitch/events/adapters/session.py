"""Session RaceEvent → EventEnvelope: final_lap / finish."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from irswitch.events.envelope import (
    EventCopy,
    EventEnvelope,
    EventPresentation,
    EventSubject,
    legacy_trigger_to_phase,
    make_envelope,
    normalize_mode,
)
from irswitch.events.event_catalog import state_for_event_type
from irswitch.overlay.protocol import RaceEvent

_SESSION_EVENTS = {
    "final_lap": ("FINAL_LAP", "session.final_lap", "ENTER"),
    "finish": ("FINISH", "session.finish", "RESULT"),
}


def session_race_event_to_envelope(
    event: RaceEvent,
    *,
    session_id: str,
    mode: str,
    now: float,
) -> EventEnvelope | None:
    mapped = _SESSION_EVENTS.get(event.name)
    if mapped is None:
        return None
    event_type, copy_token, default_phase = mapped
    catalog_state = state_for_event_type(event_type)
    if catalog_state is None:
        return None

    phase = legacy_trigger_to_phase(event.phase, default=default_phase)
    metrics = {
        key: event.data[key]
        for key in ("lap", "position", "classPosition")
        if key in event.data and event.data[key] is not None
    }
    position = metrics.get("position")
    if position is None:
        position = metrics.get("classPosition")
    return make_envelope(
        event_type=event_type,
        phase=phase,
        mode=normalize_mode(mode),
        session_id=session_id or "session:unknown",
        occurred_at=datetime.fromtimestamp(time.time(), tz=UTC).isoformat(),
        monotonic_ms=int(now * 1000),
        priority=event.priority,
        dedupe_key=f"{normalize_mode(mode)}:{event_type}:{position}",
        correlation_id=f"session:{event_type}",
        subject=EventSubject(car_id="player", class_position=position),
        metrics=metrics,
        copy=EventCopy(headline_token=copy_token, status_token=""),
        presentation=EventPresentation(
            widget="session",
            zone="EVENT",
            variant=catalog_state,
            accent="primary",
            preferred_state=default_phase,
        ),
    )
