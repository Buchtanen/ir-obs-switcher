"""Pit story RaceEvent → EventEnvelope adapter."""

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

_PIT_EVENT = "pit_story"
_PHASE_TO_EVENT_TYPE: dict[str, str] = {
    "entry": "PIT_ENTRY",
    "lane": "PIT_LANE",
    "stopped": "PIT_STOPPED",
    "released": "PIT_RELEASED",
    "exit": "PIT_EXIT",
    "outcome": "PIT_OUTCOME",
}

_COPY_TOKENS: dict[str, str] = {
    "entry": "pit.entry",
    "exit": "pit.exit",
    "outcome": "pit.exit",
}


def _event_type_for_pit_phase(pit_phase: str) -> str | None:
    return _PHASE_TO_EVENT_TYPE.get(pit_phase.lower())


def _catalog_family(event_type: str) -> str:
    entry = catalog_entries().get(event_type, {})
    return str(entry.get("family") or "pit")


def pit_race_event_to_envelope(
    event: RaceEvent,
    *,
    session_id: str,
    mode: str,
    now: float,
) -> EventEnvelope | None:
    if event.name != _PIT_EVENT:
        return None
    pit_phase = str(event.data.get("state") or "").lower()
    event_type = _event_type_for_pit_phase(pit_phase)
    if event_type is None:
        return None
    catalog_state = state_for_event_type(event_type)
    if catalog_state is None:
        return None

    default_phase = "RESULT" if pit_phase == "outcome" else "ENTER"
    phase = legacy_trigger_to_phase(event.phase, default=default_phase)
    correlation_id = str(event.data.get("correlationId") or f"pit:{pit_phase}")
    metrics = {
        key: event.data[key]
        for key in (
            "onPitRoad",
            "position",
            "lapDistPct",
            "entryPosition",
            "exitPosition",
            "positionDelta",
            "pitDurationProxy",
        )
        if key in event.data
    }
    preferred = "RESULT" if pit_phase == "outcome" else "ACTIVE"
    return make_envelope(
        event_type=event_type,
        phase=phase,
        mode=normalize_mode(mode),
        session_id=session_id or "session:unknown",
        occurred_at=datetime.fromtimestamp(time.time(), tz=UTC).isoformat(),
        monotonic_ms=int(now * 1000),
        priority=event.priority,
        dedupe_key=f"{normalize_mode(mode)}:{event_type}:{correlation_id}",
        correlation_id=correlation_id,
        story_key=correlation_id,
        subject=EventSubject(
            car_id="player",
            class_position=event.data.get("position"),
        ),
        metrics=metrics,
        copy=EventCopy(
            headline_token=_COPY_TOKENS.get(pit_phase, "pit.entry"),
            status_token="",
        ),
        presentation=EventPresentation(
            widget=_catalog_family(event_type),
            zone="EVENT",
            variant=catalog_state,
            accent="warning" if pit_phase in {"entry", "lane", "stopped"} else "primary",
            preferred_state=preferred,
        ),
    )
