"""Exception family extras: link_drop / invalid_lap RaceEvent → EventEnvelope."""

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
from irswitch.events.event_catalog import state_for_event_type
from irswitch.overlay.protocol import RaceEvent


def _exception_envelope(
    event: RaceEvent,
    *,
    event_type: str,
    session_id: str,
    mode: str,
    now: float,
    copy_token: str,
    accent: str,
    default_phase: str,
) -> EventEnvelope | None:
    catalog_state = state_for_event_type(event_type)
    if catalog_state is None:
        return None
    phase = legacy_trigger_to_phase(event.phase, default=default_phase)
    lap = event.data.get("lap")
    return make_envelope(
        event_type=event_type,
        phase=phase,
        mode=normalize_mode(mode),
        session_id=session_id or "session:unknown",
        occurred_at=datetime.fromtimestamp(time.time(), tz=UTC).isoformat(),
        monotonic_ms=int(now * 1000),
        priority=event.priority,
        dedupe_key=f"{normalize_mode(mode)}:{event_type}:{lap}",
        correlation_id=f"exception:{event_type}:{lap}",
        metrics=dict(event.data),
        copy=EventCopy(headline_token=copy_token, status_token=""),
        presentation=EventPresentation(
            widget="exception",
            zone="EVENT",
            variant=catalog_state,
            accent=accent,
            preferred_state=default_phase,
        ),
    )


def link_drop_race_event_to_envelope(
    event: RaceEvent,
    *,
    session_id: str,
    mode: str,
    now: float,
) -> EventEnvelope | None:
    if event.name != "link_drop":
        return None
    return _exception_envelope(
        event,
        event_type="LINK_DROP",
        session_id=session_id,
        mode=mode,
        now=now,
        copy_token="exception.link_drop",
        accent="alert",
        default_phase="ENTER",
    )


def invalid_lap_race_event_to_envelope(
    event: RaceEvent,
    *,
    session_id: str,
    mode: str,
    now: float,
) -> EventEnvelope | None:
    if event.name != "invalid_lap":
        return None
    return _exception_envelope(
        event,
        event_type="INVALID_LAP",
        session_id=session_id,
        mode=mode,
        now=now,
        copy_token="exception.invalid_lap",
        accent="alert",
        default_phase="RESULT",
    )
