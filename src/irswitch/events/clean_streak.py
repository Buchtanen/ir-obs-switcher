"""Consecutive clean lap streak emitter."""

from __future__ import annotations

from dataclasses import dataclass, field

from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import EventPrioritySettings, EventSettings

_MIN_STREAK = 3


@dataclass
class CleanStreakEmitter:
    events: EventSettings = field(default_factory=EventSettings)
    priorities: EventPrioritySettings = field(default_factory=EventPrioritySettings)
    _last_lap: int | None = None
    _last_incidents: int | None = None
    _streak: int = 0

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:  # noqa: ARG002
        if not state.connected or state.lap_completed is None:
            return []
        lap = state.lap_completed
        if self._last_lap is None or lap <= self._last_lap:
            return []
        incidents = state.incidents if state.incidents is not None else 0
        prev_incidents = self._last_incidents if self._last_incidents is not None else incidents
        self._last_lap = lap
        self._last_incidents = incidents
        if incidents > prev_incidents:
            self._streak = 0
            return []
        self._streak += 1
        if self._streak < _MIN_STREAK:
            return []
        return [
            CandidateEvent(
                name="clean_streak",
                channel="timing",
                priority=self.priorities.gain_found,
                phase="trigger",
                data={"streak": self._streak, "lap": lap},
                duration=self.events.lap_duration,
                cooldown=self.events.lap_cooldown,
            )
        ]

    def reset(self) -> None:
        self._last_lap = None
        self._last_incidents = None
        self._streak = 0
