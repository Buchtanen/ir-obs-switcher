"""Pit entry / exit edges."""

from __future__ import annotations

from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import EventPrioritySettings


class PitEmitter:
    def __init__(self, priorities: EventPrioritySettings) -> None:
        self._priorities = priorities
        self._on_pit: bool | None = None

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:  # noqa: ARG002
        if not state.connected:
            self._on_pit = None
            return []
        prev = self._on_pit
        self._on_pit = state.on_pit_road
        if prev is None or prev == state.on_pit_road:
            return []
        if state.on_pit_road:
            return [
                CandidateEvent(
                    name="pit_entry",
                    channel="session",
                    priority=self._priorities.pit,
                    phase="trigger",
                    data={"onPitRoad": True},
                )
            ]
        return [
            CandidateEvent(
                name="pit_exit",
                channel="session",
                priority=self._priorities.pit,
                phase="trigger",
                data={
                    "onPitRoad": False,
                    "position": state.class_position or state.position,
                },
            )
        ]
