"""Rival threat: fast car behind closing (position family)."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import isfinite

from irswitch.overlay.models import OpponentInfo, RaceState
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
        closing = state.closing_rate_behind
        gap = state.gap_behind
        opp = state.opponent_behind
        if not _valid_relation(state, gap, closing, opp):
            return self._clear(now)
        assert opp is not None
        if self._active:
            return []
        if now < self._cooldown_until:
            return []
        self._active = True
        self._cooldown_until = now + _COOLDOWN_S
        rival_pos = opp.class_position if opp.class_position is not None else opp.position
        return [
            CandidateEvent(
                name="rival_threat",
                channel="alert",
                priority=self.priorities.position_change,
                phase="enter",
                data={
                    "rivalPosition": rival_pos,
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


def _valid_relation(
    state: RaceState,
    gap: float | None,
    closing: float | None,
    opponent: OpponentInfo | None,
) -> bool:
    if opponent is None or isinstance(gap, bool) or isinstance(closing, bool):
        return False
    if not isinstance(gap, (int, float)) or not isfinite(gap) or not 0 <= gap <= _MAX_GAP_S:
        return False
    if not isinstance(closing, (int, float)) or not isfinite(closing) or closing < _MIN_CLOSING:
        return False
    hero = state.class_position
    rival = getattr(opponent, "class_position", None)
    if hero is None or rival is None:
        hero, rival = state.position, getattr(opponent, "position", None)
    return (
        isinstance(hero, int)
        and not isinstance(hero, bool)
        and isinstance(rival, int)
        and not isinstance(rival, bool)
        and rival > hero > 0
    )
