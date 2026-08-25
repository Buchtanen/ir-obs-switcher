"""Fan-out RaceState into MVP emitters."""

from __future__ import annotations

from irswitch.events.battle import BattleEmitter
from irswitch.events.incident import IncidentEmitter
from irswitch.events.lap import LapEmitter
from irswitch.events.pit import PitEmitter
from irswitch.events.position import PositionEmitter
from irswitch.events.session import SessionEmitter
from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import OverlaySettings


class EventEngine:
    def __init__(self, overlay: OverlaySettings) -> None:
        pri = overlay.events.priorities
        self.battle = BattleEmitter(overlay.battle.hunting, overlay.battle.hunted, pri)
        self.lap = LapEmitter(overlay.events, pri)
        self.position = PositionEmitter(overlay.battle, pri)
        self.incident = IncidentEmitter(overlay.events, pri)
        self.pit = PitEmitter(pri)
        self.session = SessionEmitter(overlay.events, pri)

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:
        events: list[CandidateEvent] = []
        events.extend(self.battle.tick(state, now))
        events.extend(self.lap.tick(state, now))
        events.extend(self.position.tick(state, now))
        events.extend(self.incident.tick(state, now))
        events.extend(self.pit.tick(state, now))
        events.extend(self.session.tick(state, now))
        return events
