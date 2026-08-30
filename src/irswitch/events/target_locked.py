"""Practice target-lock emitter (session reference lap)."""

from __future__ import annotations

from dataclasses import dataclass, field

from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import EventPrioritySettings, EventSettings


@dataclass
class TargetLockedEmitter:
    events: EventSettings = field(default_factory=EventSettings)
    priorities: EventPrioritySettings = field(default_factory=EventPrioritySettings)
    _locked: bool = False
    _target_time: float | None = None

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:  # noqa: ARG002
        if state.overlay_mode != "PRACTICE" or not state.connected or state.session_finished:
            return []
        target = state.best_lap_time
        if target is None or target <= 0:
            return []
        if self._locked and self._target_time == target:
            return []
        self._locked = True
        self._target_time = target
        return [
            CandidateEvent(
                name="target_locked",
                channel="timing",
                priority=self.priorities.projected_lap,
                phase="enter",
                data={"targetTime": round(target, 3), "lap": state.lap_completed},
                duration=self.events.lap_duration,
                cooldown=self.events.lap_cooldown,
            )
        ]

    def reset(self) -> None:
        self._locked = False
        self._target_time = None
