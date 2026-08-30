"""Final lap and finish session events."""

from __future__ import annotations

from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import EventPrioritySettings, EventSettings


class SessionEmitter:
    def __init__(self, events: EventSettings, priorities: EventPrioritySettings) -> None:
        self._events = events
        self._priorities = priorities
        self._final_emitted = False
        self._finish_emitted = False

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:  # noqa: ARG002
        if not state.connected:
            self._final_emitted = False
            self._finish_emitted = False
            return []
        out: list[CandidateEvent] = []
        if state.is_final_lap and not self._final_emitted:
            self._final_emitted = True
            out.append(
                CandidateEvent(
                    name="final_lap",
                    channel="session",
                    priority=self._priorities.final_lap,
                    phase="trigger",
                    data={
                        "lap": state.lap,
                        "position": state.position,
                        "classPosition": state.class_position,
                    },
                    duration=self._events.session_duration,
                )
            )
        if state.session_finished and not self._finish_emitted:
            self._finish_emitted = True
            out.append(
                CandidateEvent(
                    name="finish",
                    channel="session",
                    priority=self._priorities.finish,
                    phase="trigger",
                    data={
                        "position": state.position,
                        "classPosition": state.class_position,
                    },
                    duration=self._events.session_duration,
                )
            )
        if not state.is_final_lap:
            self._final_emitted = False
        if not state.session_finished:
            self._finish_emitted = False
        return out
