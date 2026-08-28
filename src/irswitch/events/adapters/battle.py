"""Battle persistent story → EventEnvelope adapter."""

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
from irswitch.overlay.protocol import RaceEvent

_BATTLE_STATES = frozenset({"hunting", "hunted", "approach", "attack_range"})


def battle_race_event_to_envelope(
    event: RaceEvent,
    *,
    session_id: str,
    mode: str,
    now: float,
) -> EventEnvelope | None:
    if event.name != "battle":
        return None
    battle_state = str(event.data.get("state") or "").lower()
    if battle_state not in _BATTLE_STATES:
        return None
    phase = legacy_trigger_to_phase(event.phase, default="ENTER")
    target_idx = event.data.get("targetCarIdx")
    target_pos = event.data.get("targetPosition")
    metrics = {
        key: event.data[key]
        for key in ("gap", "closingRate", "targetCarIdx", "targetPosition")
        if key in event.data
    }
    copy_token = (
        f"battle.{battle_state}" if battle_state in {"hunting", "hunted"} else "battle.closing_in"
    )
    tone = "warning" if battle_state == "hunted" else "primary"
    return make_envelope(
        event_type=battle_state.upper(),
        phase=phase,
        mode=normalize_mode(mode),
        session_id=session_id or "session:unknown",
        occurred_at=datetime.fromtimestamp(time.time(), tz=UTC).isoformat(),
        monotonic_ms=int(now * 1000),
        priority=event.priority,
        dedupe_key=f"{normalize_mode(mode)}:battle:{battle_state}",
        correlation_id=f"battle:{battle_state}",
        story_key=f"battle:{battle_state}",
        subject=EventSubject(car_id="player"),
        target=EventSubject(car_id=str(target_idx or "unknown"), class_position=target_pos),
        metrics=metrics,
        copy=EventCopy(headline_token=copy_token, status_token=""),
        presentation=EventPresentation(
            widget="battle",
            zone="EVENT",
            variant=battle_state,
            accent=tone,
            preferred_state="ACTIVE",
        ),
    )
