"""Bio / HR pressure RaceEvent → EventEnvelope adapter."""

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
from irswitch.events.event_catalog import catalog_entries, state_for_event_type
from irswitch.overlay.protocol import RaceEvent

_HR_EVENTS = frozenset({"hr_pressure", "heart_rate"})


def _catalog_family(event_type: str) -> str:
    entry = catalog_entries().get(event_type, {})
    return str(entry.get("family") or "bio")


def bio_race_event_to_envelope(
    event: RaceEvent,
    *,
    session_id: str,
    mode: str,
    now: float,
) -> EventEnvelope | None:
    if event.name not in _HR_EVENTS:
        return None
    event_type = "HR_PRESSURE_RISING"
    catalog_state = state_for_event_type(event_type)
    if catalog_state is None:
        return None

    phase = legacy_trigger_to_phase(event.phase, default="ENTER")
    metrics = {
        key: event.data[key]
        for key in ("bpm", "baselineBpm", "deltaBpm", "hrState")
        if key in event.data
    }
    return make_envelope(
        event_type=event_type,
        phase=phase,
        mode=normalize_mode(mode),
        session_id=session_id or "session:unknown",
        occurred_at=datetime.fromtimestamp(time.time(), tz=UTC).isoformat(),
        monotonic_ms=int(now * 1000),
        priority=event.priority,
        dedupe_key=f"{normalize_mode(mode)}:HR_PRESSURE_RISING",
        correlation_id="bio:hr_pressure",
        story_key="bio:hr_pressure",
        subject=EventSubject(car_id="player"),
        metrics=metrics,
        copy=EventCopy(headline_token="bio.hr_high", status_token=""),
        presentation=EventPresentation(
            widget=_catalog_family(event_type),
            zone="EVENT",
            variant=catalog_state,
            accent="warning",
            preferred_state="ACTIVE",
        ),
    )
