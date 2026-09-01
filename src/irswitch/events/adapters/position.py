"""Position / overtake / rival_threat RaceEvent → EventEnvelope adapter."""

from __future__ import annotations

import time
from datetime import UTC, datetime
from typing import Any

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

_POSITION_EVENT = "position_change"
_OVERTAKE_EVENT = "overtake"
_RIVAL_THREAT_EVENT = "rival_threat"
_LEADER_CHANGE_EVENT = "leader_change"

_POSITION_METRIC_KEYS = ("direction", "oldPosition", "newPosition", "delta")
_RIVAL_METRIC_KEYS = ("gap", "closingRate", "targetCarIdx", "rivalPosition", "targetName")
_OVERTAKE_METRIC_KEYS = (
    "direction",
    "oldPosition",
    "newPosition",
    "delta",
    "targetCarIdx",
    "targetPosition",
    "targetName",
)


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
    if event_type == "LEADER_CHANGE":
        return "position.leader_change"
    return ""


def _accent_for(event_type: str) -> str:
    if event_type in {"POSITION_LOST", "RIVAL_THREAT"}:
        return "warning"
    return "primary"


def _rival_metrics(data: dict[str, Any]) -> dict[str, Any]:
    """Keep emitter gap/target fields; prefer real names / P# over fake copy."""
    metrics = {key: data[key] for key in _RIVAL_METRIC_KEYS if key in data}
    rival_pos = data.get("rivalPosition")
    if metrics.get("targetName") in (None, ""):
        if rival_pos is not None:
            metrics["targetName"] = f"P{rival_pos}"
        # No invented "the car behind" — leave unnamed when DriverInfo is missing.
    # Widget historically read metrics.position (manifest sample is P8).
    if "position" not in metrics and rival_pos is not None:
        metrics["position"] = rival_pos
    return metrics


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
    elif event.name == _LEADER_CHANGE_EVENT:
        event_type = "LEADER_CHANGE"
    else:
        return None

    catalog_state = state_for_event_type(event_type)
    if catalog_state is None:
        return None

    if event_type == "LEADER_CHANGE":
        phase = legacy_trigger_to_phase(event.phase, default="RESULT")
        metrics = {
            key: event.data[key]
            for key in (
                "oldLeaderCarIdx",
                "oldLeaderName",
                "targetCarIdx",
                "targetName",
                "heroIsLeader",
                "position",
                "p1Name",
            )
            if key in event.data
        }
        target_idx = event.data.get("targetCarIdx")
        return make_envelope(
            event_type=event_type,
            phase=phase,
            mode=normalize_mode(mode),
            session_id=session_id or "session:unknown",
            occurred_at=datetime.fromtimestamp(time.time(), tz=UTC).isoformat(),
            monotonic_ms=int(now * 1000),
            priority=event.priority,
            dedupe_key=f"{normalize_mode(mode)}:LEADER_CHANGE:{target_idx}",
            correlation_id=f"leader:{target_idx}",
            subject=EventSubject(car_id="player"),
            target=EventSubject(
                car_id=str(target_idx if target_idx is not None else "unknown"),
                class_position=1,
                display_name=str(event.data.get("targetName") or "") or None,
            ),
            metrics=metrics,
            copy=EventCopy(headline_token=_copy_token(event_type), status_token=""),
            presentation=EventPresentation(
                widget=_catalog_family(event_type),
                zone="EVENT",
                variant=catalog_state,
                accent="primary",
                preferred_state="RESULT",
            ),
        )

    if event_type == "RIVAL_THREAT":
        default_phase = "ENTER"
        phase = legacy_trigger_to_phase(event.phase, default=default_phase)
        metrics = _rival_metrics(event.data)
        target_idx = event.data.get("targetCarIdx")
        rival_pos = event.data.get("rivalPosition")
        label = metrics.get("targetName")
        return make_envelope(
            event_type=event_type,
            phase=phase,
            mode=normalize_mode(mode),
            session_id=session_id or "session:unknown",
            occurred_at=datetime.fromtimestamp(time.time(), tz=UTC).isoformat(),
            monotonic_ms=int(now * 1000),
            priority=event.priority,
            dedupe_key=f"{normalize_mode(mode)}:RIVAL_THREAT:{target_idx}",
            correlation_id=f"rival:{target_idx}",
            subject=EventSubject(car_id="player"),
            target=EventSubject(
                car_id=str(target_idx if target_idx is not None else "unknown"),
                class_position=rival_pos if isinstance(rival_pos, int) else None,
                display_name=str(label) if label else None,
            ),
            metrics=metrics,
            copy=EventCopy(headline_token=_copy_token(event_type), status_token=""),
            presentation=EventPresentation(
                widget=_catalog_family(event_type),
                zone="EVENT",
                variant=catalog_state,
                accent=_accent_for(event_type),
                preferred_state="ACTIVE",
                # Sticky ACTIVE without EXIT was blocking POSITION_GAINED (family cap 1).
                max_hold_ms=8000,
            ),
        )

    phase = legacy_trigger_to_phase(event.phase, default="RESULT")
    new_position = event.data.get("newPosition")
    metric_keys = _OVERTAKE_METRIC_KEYS if event_type == "OVERTAKE" else _POSITION_METRIC_KEYS
    metrics = {key: event.data[key] for key in metric_keys if key in event.data}
    target = None
    if event_type == "OVERTAKE":
        target_idx = event.data.get("targetCarIdx")
        target_pos = event.data.get("targetPosition")
        target_name = event.data.get("targetName")
        if target_idx is not None or target_name:
            target = EventSubject(
                car_id=str(target_idx if target_idx is not None else "unknown"),
                class_position=target_pos if isinstance(target_pos, int) else None,
                display_name=str(target_name) if target_name else None,
            )
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
        target=target,
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
