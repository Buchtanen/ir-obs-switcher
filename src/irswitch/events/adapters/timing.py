"""Practice / quali timing RaceEvent → EventEnvelope adapter."""

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

_TIMING_EVENT_NAMES = frozenset(
    {
        "gain_found",
        "time_lost",
        "projected_lap",
        "position_attack",
        "sector_best",
        "target_locked",
        "hot_lap",
        "clean_streak",
        "sector_split",
    }
)

_NAME_TO_EVENT_TYPE = {
    "gain_found": "GAIN_FOUND",
    "time_lost": "TIME_LOST",
    "projected_lap": "PROJECTED_LAP",
    "position_attack": "POSITION_ATTACK",
    "sector_best": "SECTOR_BEST",
    "target_locked": "TARGET_LOCKED",
    "hot_lap": "HOT_LAP",
    "clean_streak": "CLEAN_STREAK",
    "sector_split": "SECTOR_SPLIT",
}


def _catalog_family(event_type: str) -> str:
    entry = catalog_entries().get(event_type, {})
    return str(entry.get("family") or "timing")


def _copy_token(event_type: str) -> str:
    mapping = {
        "GAIN_FOUND": "timing.gain_found",
        "TIME_LOST": "timing.time_lost",
        "PROJECTED_LAP": "timing.projected_lap",
        "POSITION_ATTACK": "timing.position_attack",
        "SECTOR_BEST": "timing.sector_best",
        "TARGET_LOCKED": "timing.target",
        "HOT_LAP": "timing.hot_lap",
        "CLEAN_STREAK": "timing.clean_streak",
        "SECTOR_SPLIT": "timing.sector_split",
    }
    return mapping.get(event_type, "")


def _default_phase(event_type: str, phase: str) -> str:
    mapped = legacy_trigger_to_phase(phase, default="")
    if mapped:
        return mapped
    if event_type in {"GAIN_FOUND", "TIME_LOST", "SECTOR_BEST", "SECTOR_SPLIT"}:
        return "RESULT"
    if phase in {"enter", "update"}:
        return "ACTIVE" if phase == "update" else "ENTER"
    return "RESULT"


def timing_race_event_to_envelope(
    event: RaceEvent,
    *,
    session_id: str,
    mode: str,
    now: float,
) -> EventEnvelope | None:
    if event.name not in _TIMING_EVENT_NAMES:
        return None
    event_type = _NAME_TO_EVENT_TYPE[event.name]
    catalog_state = state_for_event_type(event_type)
    if catalog_state is None:
        return None
    phase = _default_phase(event_type, event.phase)
    metrics = dict(event.data)
    lap = metrics.get("lap")
    return make_envelope(
        event_type=event_type,
        phase=phase,
        mode=normalize_mode(mode),
        session_id=session_id or "session:unknown",
        occurred_at=datetime.fromtimestamp(time.time(), tz=UTC).isoformat(),
        monotonic_ms=int(now * 1000),
        priority=event.priority,
        dedupe_key=f"{normalize_mode(mode)}:{event_type}:{lap}:{metrics.get('timingPointId', '')}",
        correlation_id=f"timing:{event_type}:{lap}",
        metrics=metrics,
        copy=EventCopy(headline_token=_copy_token(event_type), status_token=""),
        presentation=EventPresentation(
            widget=_catalog_family(event_type),
            zone="EVENT",
            variant=catalog_state,
            accent="primary",
            preferred_state="ACTIVE" if phase == "ENTER" else phase,
        ),
    )
