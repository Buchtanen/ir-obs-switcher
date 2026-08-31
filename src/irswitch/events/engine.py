"""Fan-out RaceState into MVP emitters."""

from __future__ import annotations

import inspect
import logging
from typing import Any, cast

from irswitch.events.battle import BattleEmitter
from irswitch.events.clean_streak import CleanStreakEmitter
from irswitch.events.incident import IncidentEmitter
from irswitch.events.invalid_lap import InvalidLapEmitter
from irswitch.events.lap import LapEmitter
from irswitch.events.link_drop import LinkDropEmitter
from irswitch.events.overtake import OvertakeClassifierEmitter
from irswitch.events.pit import PitEmitter
from irswitch.events.position import PositionEmitter
from irswitch.events.rival_threat import RivalThreatEmitter
from irswitch.events.session import SessionEmitter
from irswitch.events.session_phase import filter_post_race
from irswitch.overlay.models import BioState, RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import OverlaySettings

logger = logging.getLogger(__name__)


class EventEngine:
    def __init__(self, overlay: OverlaySettings) -> None:
        pri = overlay.events.priorities
        self.battle = BattleEmitter(overlay.battle.hunting, overlay.battle.hunted, pri)
        self.lap = LapEmitter(overlay.events, pri)
        position_emitter: PositionEmitter | OvertakeClassifierEmitter
        if overlay.event_engine.overtake_classifier:
            position_emitter = OvertakeClassifierEmitter(overlay.battle, pri)
        else:
            position_emitter = PositionEmitter(overlay.battle, pri)
        self.position = position_emitter
        self.incident = IncidentEmitter(overlay.events, pri)
        self.pit: PitEmitter | None
        self.session = SessionEmitter(overlay.events, pri)
        self._emitters: list[Any] = [
            self.battle,
            self.lap,
            self.position,
            self.incident,
            self.session,
            LinkDropEmitter(pri),
            InvalidLapEmitter(overlay.events, pri),
            CleanStreakEmitter(overlay.events, pri),
            RivalThreatEmitter(overlay.events, pri),
        ]
        if not overlay.event_engine.pit_story:
            self.pit = PitEmitter(pri)
            self._emitters.insert(4, self.pit)
        else:
            self.pit = None

    def register(self, emitter: Any) -> None:
        """Append an emitter to the deterministic fan-out order."""
        self._emitters.append(emitter)

    def tick(
        self,
        state: RaceState,
        now: float,
        bio: BioState | None = None,
    ) -> list[CandidateEvent]:
        events: list[CandidateEvent] = []
        for emitter in self._emitters:
            try:
                events.extend(self._tick_emitter(emitter, state, now, bio))
            except Exception:
                logger.warning(
                    "%s tick failed",
                    type(emitter).__name__,
                    exc_info=True,
                )
        return filter_post_race(events, session_finished=bool(state.mute_field or state.session_finished))

    @staticmethod
    def _tick_emitter(
        emitter: Any,
        state: RaceState,
        now: float,
        bio: BioState | None,
    ) -> list[CandidateEvent]:
        tick = emitter.tick
        try:
            params = inspect.signature(tick).parameters
        except (TypeError, ValueError):
            return cast(list[CandidateEvent], tick(state, now))
        if "bio" in params:
            return cast(list[CandidateEvent], tick(state, now, bio))
        if len(params) >= 3:
            return cast(list[CandidateEvent], tick(state, now, bio))
        return cast(list[CandidateEvent], tick(state, now))
