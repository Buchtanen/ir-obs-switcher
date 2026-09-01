"""Class-leader change. Commentary + overlay; priority 75."""

from __future__ import annotations

from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import EventPrioritySettings

_STABLE_S = 0.35


class LeaderChangeEmitter:
    """Emit when the same-class P1 car_idx changes after a short hold."""

    def __init__(self, priorities: EventPrioritySettings) -> None:
        self._priority = int(getattr(priorities, "leader_change", 75) or 75)
        self._confirmed: int | None = None
        self._confirmed_name: str | None = None
        self._pending: int | None = None
        self._pending_name: str | None = None
        self._pending_since: float | None = None

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:
        if not state.connected:
            self._confirmed = None
            self._pending = None
            return []
        if (state.overlay_mode or "") not in {"RACE", "QUALIFYING", "PRACTICE"}:
            return []
        current = state.leader_car_idx
        name = state.leader_name or state.p1_name
        if current is None:
            return []
        if self._confirmed is None:
            self._confirmed = current
            self._confirmed_name = name
            return []
        if current == self._confirmed:
            self._pending = None
            self._pending_since = None
            self._confirmed_name = name or self._confirmed_name
            return []
        if self._pending != current:
            self._pending = current
            self._pending_name = name
            self._pending_since = now
            return []
        if self._pending_since is None or now - self._pending_since < _STABLE_S:
            return []
        old_idx = self._confirmed
        old_name = self._confirmed_name
        self._confirmed = current
        self._confirmed_name = name
        self._pending = None
        hero_is_leader = state.player_car_idx == current
        return [
            CandidateEvent(
                name="leader_change",
                channel="alert",
                priority=self._priority,
                phase="trigger",
                data={
                    "oldLeaderCarIdx": old_idx,
                    "oldLeaderName": old_name,
                    "targetCarIdx": current,
                    "targetName": name,
                    "heroIsLeader": hero_is_leader,
                    "position": state.class_position or state.position,
                    "p1Name": state.p1_name,
                },
            )
        ]
