"""Incident count edge with configurable minimum delta."""

from __future__ import annotations

from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import EventPrioritySettings, EventSettings


class IncidentEmitter:
    def __init__(self, events: EventSettings, priorities: EventPrioritySettings) -> None:
        self._min_delta = events.incident_min_delta
        self._priorities = priorities
        self._last: int | None = None

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:  # noqa: ARG002
        if not state.connected or state.incidents is None:
            return []
        prev = self._last
        self._last = state.incidents
        if prev is None or state.incidents <= prev:
            return []
        delta = state.incidents - prev
        if delta < self._min_delta:
            return []
        return [
            CandidateEvent(
                name="incident",
                channel="alert",
                priority=self._priorities.incident,
                phase="trigger",
                data={"value": delta, "total": state.incidents},
            )
        ]
