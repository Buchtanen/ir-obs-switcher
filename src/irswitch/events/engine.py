"""Fan-out RaceState into MVP emitters."""

from __future__ import annotations

import logging
from typing import Any

from irswitch.events.battle import BattleEmitter
from irswitch.events.incident import IncidentEmitter
from irswitch.events.lap import LapEmitter
from irswitch.events.pit import PitEmitter
from irswitch.events.position import PositionEmitter
from irswitch.events.session import SessionEmitter
from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import OverlaySettings

logger = logging.getLogger(__name__)


class EventEngine:
    def __init__(self, overlay: OverlaySettings) -> None:
        pri = overlay.events.priorities
        self.battle = BattleEmitter(overlay.battle.hunting, overlay.battle.hunted, pri)
        self.lap = LapEmitter(overlay.events, pri)
        self.position = PositionEmitter(overlay.battle, pri)
        self.incident = IncidentEmitter(overlay.events, pri)
        self.pit = PitEmitter(pri)
        self.session = SessionEmitter(overlay.events, pri)
        self._emitters: list[Any] = [
            self.battle,
            self.lap,
            self.position,
            self.incident,
            self.pit,
            self.session,
        ]

    def register(self, emitter: Any) -> None:
        """Append an emitter to the deterministic fan-out order."""
        self._emitters.append(emitter)

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:
        events: list[CandidateEvent] = []
        for emitter in self._emitters:
            try:
                events.extend(emitter.tick(state, now))
            except Exception:
                logger.warning(
                    "%s tick failed",
                    type(emitter).__name__,
                    exc_info=True,
                )
        return events
