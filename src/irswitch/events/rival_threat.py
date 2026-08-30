"""Rival threat: fast car behind closing (position family)."""

from __future__ import annotations

from dataclasses import dataclass, field

from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import EventPrioritySettings, EventSettings

_MIN_CLOSING = 0.25
_MAX_GAP_S = 2.5
_COOLDOWN_S = 12.0


@dataclass
class RivalThreatEmitter:
    events: EventSettings = field(default_factory=EventSettings)
    priorities: EventPrioritySettings = field(default_factory=EventPrioritySettings)
    _active: bool = False
    _cooldown_until: float = 0.0

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:
        if not state.connected or state.overlay_mode not in {"RACE", "QUALIFYING", "PRACTICE"}:
            return self._clear(now)
        if now < self._cooldown_until:
            return []
        closing = state.closing_rate_behind
        gap = state.gap_behind
        opp = state.opponent_behind
        if (
            closing is None
            or gap is None
            or closing < _MIN_CLOSING
            or gap > _MAX_GAP_S
            or opp is None
        ):
            return self._clear(now)
        if self._active:
            return []
        self._active = True
        self._cooldown_until = now + _COOLDOWN_S
        return [
            CandidateEvent(
                name="rival_threat",
                channel="alert",
                priority=self.priorities.position_change,
                phase="enter",
                data={
                    "rivalPosition": opp.position,
                    "gap": gap,
                    "closingRate": closing,
                    "targetCarIdx": opp.car_idx,
                    **({"targetName": opp.display_name} if opp.display_name else {}),
                },
                duration=self.events.alert_duration,
                cooldown=_COOLDOWN_S,
            )
        ]

    def _clear(self, now: float) -> list[CandidateEvent]:
        if not self._active:
            return []
        self._active = False
        return [
            CandidateEvent(
                name="rival_threat",
                channel="alert",
                priority=self.priorities.position_change,
                phase="exit",
                data={},
            )
        ]

    def reset(self) -> None:
        self._active = False
        self._cooldown_until = 0.0
