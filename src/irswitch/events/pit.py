"""Pit entry / exit edges."""

from __future__ import annotations

from irswitch.events.session_phase import should_begin_pit_cycle
from irswitch.iracing.trk_loc import is_on_track
from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import EventPrioritySettings


class PitEmitter:
    def __init__(self, priorities: EventPrioritySettings) -> None:
        self._priorities = priorities
        self._on_pit: bool | None = None
        self._seen_on_track = False
        self._prev_surface: int | None = None
        self._prev_dist: float | None = None
        self._in_cycle = False

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:  # noqa: ARG002
        if not state.connected:
            self._on_pit = None
            self._seen_on_track = False
            self._prev_surface = None
            self._prev_dist = None
            self._in_cycle = False
            return []
        if is_on_track(state.player_track_surface):
            self._seen_on_track = True
        prev = self._on_pit
        prev_surface = self._prev_surface
        prev_dist = self._prev_dist
        self._on_pit = state.on_pit_road
        self._prev_surface = state.player_track_surface
        self._prev_dist = state.player_lap_dist_pct
        if prev is None or prev == state.on_pit_road:
            return []
        if state.on_pit_road:
            if not should_begin_pit_cycle(
                state,
                seen_on_track=self._seen_on_track,
                prev_surface=prev_surface,
                prev_dist=prev_dist,
            ):
                return []
            self._in_cycle = True
            return [
                CandidateEvent(
                    name="pit_entry",
                    channel="session",
                    priority=self._priorities.pit,
                    phase="trigger",
                    data={"onPitRoad": True},
                )
            ]
        if not self._in_cycle:
            return []
        self._in_cycle = False
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
