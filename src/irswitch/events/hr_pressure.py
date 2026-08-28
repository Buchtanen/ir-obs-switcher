"""HR pressure rising emitter with hysteresis (V4 bio track)."""

from __future__ import annotations

from dataclasses import dataclass, field

from irswitch.overlay.models import BioState, RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import EventPrioritySettings

_PRESSURE_STATES = frozenset({"pushing", "high"})
_EXIT_DELAY_S = 3.0


@dataclass
class HrPressureEmitter:
    priorities: EventPrioritySettings = field(default_factory=EventPrioritySettings)
    exit_delay_s: float = _EXIT_DELAY_S
    _active: bool = False
    _clear_since: float | None = None

    def tick(
        self,
        state: RaceState,
        now: float,
        bio: BioState | None = None,
    ) -> list[CandidateEvent]:
        if not state.connected:
            return self._maybe_exit(now, bio)

        if bio is None or not bio.connected or bio.bpm is None:
            return self._maybe_exit(now, bio)

        pressure = bio.state in _PRESSURE_STATES
        if not self._active:
            if not pressure:
                return []
            self._active = True
            self._clear_since = None
            return [self._event(phase="enter", bio=bio, now=now)]

        if pressure:
            self._clear_since = None
            return [self._event(phase="update", bio=bio, now=now)]

        if self._clear_since is None:
            self._clear_since = now
            return []

        if (now - self._clear_since) < self.exit_delay_s:
            return []

        self._active = False
        self._clear_since = None
        return [self._event(phase="exit", bio=bio, now=now)]

    def _maybe_exit(self, now: float, bio: BioState | None) -> list[CandidateEvent]:
        if not self._active:
            self._clear_since = None
            return []
        self._active = False
        self._clear_since = None
        payload = bio if bio is not None else BioState()
        return [self._event(phase="exit", bio=payload, now=now)]

    def _event(self, *, phase: str, bio: BioState, now: float) -> CandidateEvent:
        data: dict[str, object] = {
            "state": "hr_pressure",
            "bpm": bio.bpm,
            "baselineBpm": bio.baseline_bpm,
            "deltaBpm": bio.delta_bpm,
            "hrState": bio.state,
        }
        return CandidateEvent(
            name="hr_pressure",
            channel="bio",
            priority=self.priorities.bio,
            phase=phase,
            data=data,
        )
