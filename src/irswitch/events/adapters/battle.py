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

_BATTLE_STATES = frozenset(
    {
        "hunting",
        "hunted",
        "approach",
        "attack_range",
        "side_by_side",
        "battle_for_position",
        "battle_won",
    }
)

_EVENT_TYPE_FOR_STATE = {
    "battle_for_position": "BATTLE_FOR_POSITION",
    "battle_won": "BATTLE_WON",
}


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
    event_type = _EVENT_TYPE_FOR_STATE.get(battle_state, battle_state.upper())
    default_phase = "RESULT" if battle_state == "battle_won" else "ENTER"
    phase = legacy_trigger_to_phase(event.phase, default=default_phase)
    target_idx = event.data.get("targetCarIdx")
    target_pos = event.data.get("targetPosition")
    metrics = {
        key: event.data[key]
        for key in (
            "gap",
            "closingRate",
            "direction",
            "heroCarIdx",
            "targetCarIdx",
            "targetPosition",
            "position",
            "targetName",
            "relationEpoch",
            "heroPosition",
            "frontTargetCarIdx",
            "frontTargetName",
            "frontTargetPosition",
            "frontGap",
            "frontRelationEpoch",
            "rearTargetCarIdx",
            "rearTargetName",
            "rearTargetPosition",
            "rearGap",
            "rearRelationEpoch",
        )
        if key in event.data
    }
    copy_token = (
        f"battle.{battle_state}"
        if battle_state
        in {"hunting", "hunted", "approach", "attack_range", "side_by_side", "battle_for_position"}
        else "battle.won" if battle_state == "battle_won" else "battle.closing_in"
    )
    tone = "warning" if battle_state in {"hunted", "battle_for_position"} else "primary"
    preferred = "RESULT" if battle_state == "battle_won" else "ACTIVE"
    # Meta duel plate: cap client hold so it cannot stick after EXIT is missed.
    max_hold_ms = 8000 if battle_state == "battle_for_position" else 0
    target_name = event.data.get("targetName")
    hero_idx = event.data.get("heroCarIdx", "player")
    relation_epoch = event.data.get("relationEpoch", 0)
    if battle_state == "battle_for_position":
        front = event.data.get("frontTargetCarIdx", "unknown")
        rear = event.data.get("rearTargetCarIdx", "unknown")
        correlation_id = (
            f"battle:two-front:{hero_idx}:{front}:{rear}:"
            f"{event.data.get('frontRelationEpoch', 0)}:"
            f"{event.data.get('rearRelationEpoch', 0)}"
        )
    else:
        direction = event.data.get("direction") or ("rear" if battle_state == "hunted" else "front")
        correlation_id = f"battle:{direction}:{hero_idx}:{target_idx or 'unknown'}:{relation_epoch}"
    return make_envelope(
        event_type=event_type,
        phase=phase,
        mode=normalize_mode(mode),
        session_id=session_id or "session:unknown",
        occurred_at=datetime.fromtimestamp(time.time(), tz=UTC).isoformat(),
        monotonic_ms=int(now * 1000),
        priority=event.priority,
        dedupe_key=f"{normalize_mode(mode)}:{correlation_id}:{battle_state}",
        correlation_id=correlation_id,
        story_key=correlation_id,
        subject=EventSubject(car_id=str(hero_idx)),
        target=EventSubject(
            car_id=str(target_idx or "unknown"),
            class_position=target_pos if isinstance(target_pos, int) else None,
            display_name=str(target_name) if target_name else None,
        ),
        metrics=metrics,
        copy=EventCopy(headline_token=copy_token, status_token=""),
        presentation=EventPresentation(
            widget="battle",
            zone="EVENT",
            variant=battle_state,
            accent=tone,
            preferred_state=preferred,
            max_hold_ms=max_hold_ms,
        ),
    )
