"""RaceEvent → EventEnvelope adapters."""

from __future__ import annotations

from collections.abc import Callable

from irswitch.events.adapters.battle import battle_race_event_to_envelope
from irswitch.events.adapters.lap import lap_race_event_to_envelope
from irswitch.events.adapters.position import position_race_event_to_envelope
from irswitch.events.envelope import EventEnvelope
from irswitch.overlay.protocol import RaceEvent

AdapterFn = Callable[..., EventEnvelope | None]

_ADAPTERS: tuple[AdapterFn, ...] = (
    lap_race_event_to_envelope,
    battle_race_event_to_envelope,
    position_race_event_to_envelope,
)


def race_event_to_envelope(
    event: RaceEvent,
    *,
    session_id: str,
    mode: str,
    now: float,
) -> EventEnvelope | None:
    for adapter in _ADAPTERS:
        envelope = adapter(event, session_id=session_id, mode=mode, now=now)
        if envelope is not None:
            return envelope
    return None
