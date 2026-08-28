"""Invalid lap emitter when incidents invalidate a completed lap."""

from __future__ import annotations

from dataclasses import dataclass, field

from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import EventPrioritySettings, EventSettings


@dataclass
class InvalidLapEmitter:
    events: EventSettings = field(default_factory=EventSettings)
    priorities: EventPrioritySettings = field(default_factory=EventPrioritySettings)
    _last_lap: int | None = None
    _incidents_at_lap_start: int | None = None

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:  # noqa: ARG002
        if not state.connected or state.lap_completed is None:
            return []
        lap = state.lap_completed
        incidents = state.incidents if state.incidents is not None else 0
        if self._last_lap is None:
            self._last_lap = lap
            self._incidents_at_lap_start = incidents
            return []
        if lap <= self._last_lap:
            return []
        start_incidents = (
            self._incidents_at_lap_start if self._incidents_at_lap_start is not None else 0
        )
        self._last_lap = lap
        self._incidents_at_lap_start = incidents
        if incidents <= start_incidents:
            return []
        return [
            CandidateEvent(
                name="invalid_lap",
                channel="alert",
                priority=self.priorities.incident,
                phase="trigger",
                data={"lap": lap, "incidentDelta": incidents - start_incidents},
                duration=self.events.alert_duration,
                cooldown=self.events.lap_cooldown,
            )
        ]

    def reset(self) -> None:
        self._last_lap = None
        self._incidents_at_lap_start = None
