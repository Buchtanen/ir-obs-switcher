"""Position gain/loss with stability delay. Prefers class position."""

from __future__ import annotations

from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import BattleSettings, EventPrioritySettings


class PositionEmitter:
    def __init__(self, battle: BattleSettings, priorities: EventPrioritySettings) -> None:
        self._stable_s = battle.position_stable_seconds
        self._priorities = priorities
        self._confirmed: int | None = None
        self._pending: int | None = None
        self._pending_since: float | None = None

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:
        if not state.connected:
            self._confirmed = None
            self._pending = None
            return []
        current = state.class_position if state.class_position is not None else state.position
        if current is None:
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
