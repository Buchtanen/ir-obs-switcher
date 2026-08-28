"""Position / overtake RaceEvent → EventEnvelope adapter."""

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
from irswitch.events.event_catalog import catalog_entries, state_for_event_type
from irswitch.overlay.protocol import RaceEvent

_POSITION_EVENT = "position_change"
_OVERTAKE_EVENT = "overtake"
_RIVAL_THREAT_EVENT = "rival_threat"

_POSITION_METRIC_KEYS = ("direction", "oldPosition", "newPosition", "delta")


def _event_type_for_position_change(direction: str) -> str | None:
    if direction == "gain":
        return "POSITION_GAINED"
    if direction == "loss":
        return "POSITION_LOST"
    return None


def _catalog_family(event_type: str) -> str:
    entry = catalog_entries().get(event_type, {})
    return str(entry.get("family") or "position")


def _copy_token(event_type: str) -> str:
    if event_type == "POSITION_GAINED":
        return "position.gained"
    if event_type == "POSITION_LOST":
        return "position.lost"
    if event_type == "OVERTAKE":
        return "position.overtake"
    if event_type == "RIVAL_THREAT":
        return "position.rival_threat"
    return ""


def _accent_for(event_type: str) -> str:
    if event_type == "POSITION_LOST":
        return "warning"
    return "primary"


def position_race_event_to_envelope(
    event: RaceEvent,
    *,
    session_id: str,
    mode: str,
    now: float,
) -> EventEnvelope | None:
    if event.name == _POSITION_EVENT:
        direction = str(event.data.get("direction") or "").lower()
        event_type = _event_type_for_position_change(direction)
        if event_type is None:
            return None
    elif event.name == _OVERTAKE_EVENT:
        event_type = "OVERTAKE"
    elif event.name == _RIVAL_THREAT_EVENT:
        event_type = "RIVAL_THREAT"
    else:
        return None

    catalog_state = state_for_event_type(event_type)
    if catalog_state is None:
        return None

    phase = legacy_trigger_to_phase(event.phase, default="RESULT")
    new_position = event.data.get("newPosition")
    metrics = {key: event.data[key] for key in _POSITION_METRIC_KEYS if key in event.data}
    return make_envelope(
        event_type=event_type,
        phase=phase,
        mode=normalize_mode(mode),
        session_id=session_id or "session:unknown",
        occurred_at=datetime.fromtimestamp(time.time(), tz=UTC).isoformat(),
        monotonic_ms=int(now * 1000),
        priority=event.priority,
        dedupe_key=f"{normalize_mode(mode)}:{event_type}:{new_position}",
        correlation_id=f"position:{event_type}:{new_position}",
        metrics=metrics,
        copy=EventCopy(headline_token=_copy_token(event_type), status_token=""),
        presentation=EventPresentation(
            widget=_catalog_family(event_type),
            zone="EVENT",
            variant=catalog_state,
            accent=_accent_for(event_type),
            preferred_state="RESULT",
        ),
    )
