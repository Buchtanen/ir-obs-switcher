"""Overtake classifier: position gain vs on-track overtake (flagged)."""

from __future__ import annotations

from dataclasses import dataclass

from irswitch.overlay.models import OpponentInfo, RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import BattleSettings, EventPrioritySettings


def _car_on_pit_road(state: RaceState, car_idx: int | None) -> bool:
    if car_idx is None:
        return False
    arr = state.car_idx_on_pit_road
    if car_idx < 0 or car_idx >= len(arr):
        return False
    return arr[car_idx] is True


@dataclass
class _TrackedAhead:
    opponent: OpponentInfo
    gap: float | None
    closing: float | None


class OvertakeClassifierEmitter:
    """Position stability + overtake classification when flag is enabled."""

    def __init__(self, battle: BattleSettings, priorities: EventPrioritySettings) -> None:
        self._stable_s = battle.position_stable_seconds
        self._classifier = battle.overtake
        self._priorities = priorities
        self._confirmed: int | None = None
        self._pending: int | None = None
        self._pending_since: float | None = None
        self._tracked_ahead: _TrackedAhead | None = None

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:
        if not state.connected:
            self._confirmed = None
            self._pending = None
            self._tracked_ahead = None
            return []

        current = state.class_position if state.class_position is not None else state.position
        if current is None:
            return []

        if self._confirmed is None:
            self._confirmed = current
            self._track_ahead(state)
            return []

        if current == self._confirmed:
            self._pending = None
            self._pending_since = None
            self._track_ahead(state)
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
        delta = old - current
        direction = "gain" if delta > 0 else "loss"

        if direction == "gain" and self._is_confident_overtake(state):
            passed = self._tracked_ahead.opponent if self._tracked_ahead else None
            return [
                CandidateEvent(
                    name="overtake",
                    channel="alert",
                    priority=self._priorities.overtake,
                    phase="trigger",
                    data={
                        "oldPosition": old,
                        "newPosition": current,
                        "delta": delta,
                        "targetCarIdx": passed.car_idx if passed else None,
                        "targetPosition": passed.position if passed else None,
                    },
                )
            ]

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

    def _track_ahead(self, state: RaceState) -> None:
        opp = state.opponent_ahead
        if opp is None:
            return
        self._tracked_ahead = _TrackedAhead(
            opponent=opp,
            gap=state.gap_ahead,
            closing=state.closing_rate_ahead,
        )

    def _is_confident_overtake(self, state: RaceState) -> bool:
        tracked = self._tracked_ahead
        if tracked is None:
            return False

        passed_idx = tracked.opponent.car_idx
        if _car_on_pit_road(state, passed_idx):
            return False

        behind = state.opponent_behind
        if behind is not None and behind.car_idx == passed_idx:
            if behind.gap is not None and behind.gap <= self._classifier.max_gap:
                return True

        gap = tracked.gap
        closing = tracked.closing
        if gap is None or closing is None:
            return False
        if gap > self._classifier.max_gap:
            return False
        if closing < self._classifier.min_closing_rate:
            return False
        return not _car_on_pit_road(state, passed_idx)
