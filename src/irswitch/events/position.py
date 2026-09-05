"""Position gain/loss with stability delay. Prefers class position."""

from __future__ import annotations

from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import BattleSettings, EventPrioritySettings

IRSDK_STATE_RACING = 4


def place_of(state: RaceState) -> int | None:
    return state.class_position if state.class_position is not None else state.position


def should_seed_place(state: RaceState, last_source: str | None) -> tuple[str, bool]:
    """Return (source, seed_without_emit).

    Pre-green Race and official→live switches reseed so parade/grid jumps
    do not fire POSITION_GAINED/LOST.
    """
    source = state.position_source or "official"
    if (state.overlay_mode or "") == "RACE" and (state.session_state or 0) < IRSDK_STATE_RACING:
        return source, True
    if last_source is not None and last_source != source:
        return source, True
    return source, False


class PositionEmitter:
    def __init__(self, battle: BattleSettings, priorities: EventPrioritySettings) -> None:
        self._stable_s = battle.position_stable_seconds
        self._priorities = priorities
        self._confirmed: int | None = None
        self._pending: int | None = None
        self._pending_since: float | None = None
        self._source: str | None = None

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:
        if not state.connected:
            self._confirmed = None
            self._pending = None
            self._source = None
            return []
        current = place_of(state)
        if current is None:
            return []
        source, seed = should_seed_place(state, self._source)
        self._source = source
        if seed:
            self._confirmed = current
            self._pending = None
            self._pending_since = None
            return []
        if self._confirmed is None:
            self._confirmed = current
            return []
        if current == self._confirmed:
            self._pending = None
            self._pending_since = None
            return []
        if self._pending != current:
            self._pending = current
            self._pending_since = now
            return []
        if self._pending_since is None or now - self._pending_since < self._stable_s:
            return []
        old = self._confirmed
        self._confirmed = current
        self._pending = None
        delta = old - current  # positive = gained places (P8 → P7)
        direction = "gain" if delta > 0 else "loss"
        return [
            CandidateEvent(
                name="position_change",
                channel="alert",
                priority=self._priorities.position_change,
                phase="trigger",
                data={
                    "direction": direction,
                    "oldPosition": old,
                    "newPosition": current,
                    "delta": delta,
                },
            )
        ]
