"""Lap complete and personal-best emitters."""

from __future__ import annotations

from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import EventPrioritySettings, EventSettings


class LapEmitter:
    def __init__(self, events: EventSettings, priorities: EventPrioritySettings) -> None:
        self._events = events
        self._priorities = priorities
        self._last_completed: int | None = None
        self._incidents_at_lap_start: int | None = None

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:  # noqa: ARG002
        if not state.connected or state.lap_completed is None:
            return []
        prev = self._last_completed
        incidents = state.incidents if state.incidents is not None else 0
        if prev is None or state.lap_completed < prev:
            self._last_completed = state.lap_completed
            self._incidents_at_lap_start = incidents
            return []
        if state.lap_completed == prev:
            return []
        # iRSDK often holds LapLastLapTime at -1 until the lap is scored.
        if state.last_lap_time is None or state.last_lap_time <= 0:
            return []
        start_incidents = (
            self._incidents_at_lap_start if self._incidents_at_lap_start is not None else 0
        )
        # Incident during the just-finished lap → INVALID_LAP owns the story.
        if incidents > start_incidents:
            self._last_completed = state.lap_completed
            self._incidents_at_lap_start = incidents
            return []

        self._last_completed = state.lap_completed
        self._incidents_at_lap_start = incidents

        personal_best = False
        if (
            state.last_lap_time is not None
            and state.best_lap_time is not None
            and state.lap_completed > 1
            and abs(state.last_lap_time - state.best_lap_time) < 0.005
        ):
            personal_best = True

        delta = None
        if state.last_lap_time is not None and state.best_lap_time is not None:
            delta = state.last_lap_time - state.best_lap_time

        data = {
            "lap": state.lap_completed,
            "lapTime": state.last_lap_time,
            "bestLap": state.best_lap_time,
            "deltaToBest": delta,
            "personalBest": personal_best,
        }
        if personal_best:
            return [
                CandidateEvent(
                    name="personal_best",
                    channel="lap",
                    priority=self._priorities.personal_best,
                    phase="trigger",
                    data=data,
                    duration=self._events.lap_duration,
                    cooldown=self._events.lap_cooldown,
                )
            ]
        return [
            CandidateEvent(
                name="lap_complete",
                channel="lap",
                priority=self._priorities.lap_complete,
                phase="trigger",
                data=data,
                duration=self._events.lap_duration,
                cooldown=self._events.lap_cooldown,
            )
        ]

    def reset(self) -> None:
        self._last_completed = None
        self._incidents_at_lap_start = None
