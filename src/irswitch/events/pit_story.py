"""Pit cycle FSM with shared correlationId (V4 pit story track)."""

from __future__ import annotations

from dataclasses import dataclass, field

from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import EventPrioritySettings

_PIT_PHASES = ("entry", "lane", "stopped", "released", "exit", "outcome")
_STOPPED_DIST_EPS = 0.0004
_MOVING_DIST_EPS = 0.0008
_STOPPED_HOLD_S = 1.5


@dataclass
class PitStoryEmitter:
    """Persistent pit story: ENTRY → LANE → STOPPED → RELEASED → EXIT → OUTCOME."""

    priorities: EventPrioritySettings = field(default_factory=EventPrioritySettings)
    _fsm: str = "idle"
    _cycle: int = 0
    _correlation_id: str = ""
    _entry_position: int | None = None
    _exit_position: int | None = None
    _last_dist: float | None = None
    _dist_stable_since: float | None = None
    _on_pit: bool | None = None

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:
        if not state.connected:
            return self._reset(now)

        events: list[CandidateEvent] = []
        prev_on_pit = self._on_pit
        self._on_pit = state.on_pit_road

        if prev_on_pit is None:
            if state.on_pit_road:
                events.extend(self._begin_cycle(state, now))
            return events

        if not prev_on_pit and state.on_pit_road:
            events.extend(self._begin_cycle(state, now))

        if self._fsm in _PIT_PHASES and self._fsm != "outcome":
            events.extend(self._advance_in_pit(state, now))

        if prev_on_pit and not state.on_pit_road:
            events.extend(self._leave_pit(state, now))

        return events

    def _reset(self, now: float) -> list[CandidateEvent]:
        events: list[CandidateEvent] = []
        if self._fsm not in {"idle", "outcome"}:
            events.extend(self._exit_phase(self._fsm, now))
        self._fsm = "idle"
        self._on_pit = None
        self._last_dist = None
        self._dist_stable_since = None
        return events

    def _session_key(self, state: RaceState) -> str:
        sid = state.subsession_id or "unknown"
        num = state.session_num if state.session_num is not None else 0
        return f"{sid}:{num}"

    def _begin_cycle(self, state: RaceState, now: float) -> list[CandidateEvent]:
        self._cycle += 1
        session = self._session_key(state)
        self._correlation_id = f"pit:{session}:{self._cycle}"
        self._entry_position = state.class_position or state.position
        self._exit_position = None
        self._last_dist = state.player_lap_dist_pct
        self._dist_stable_since = now
        self._fsm = "entry"
        return [
            self._event(
                phase="enter",
                pit_phase="entry",
                state=state,
                now=now,
            )
        ]

    def _advance_in_pit(self, state: RaceState, now: float) -> list[CandidateEvent]:
        events: list[CandidateEvent] = []
        dist = state.player_lap_dist_pct
        moving = self._is_moving(dist, now)
        stationary = self._is_stationary(dist, now)

        if self._fsm == "entry":
            events.extend(self._transition("entry", "lane", state, now))
        elif self._fsm == "lane":
            if stationary:
                events.extend(self._transition("lane", "stopped", state, now))
            else:
                events.append(
                    self._event(
                        phase="update",
                        pit_phase="lane",
                        state=state,
                        now=now,
                    )
                )
        elif self._fsm == "stopped":
            if moving:
                events.extend(self._transition("stopped", "released", state, now))
            else:
                events.append(
                    self._event(
                        phase="update",
                        pit_phase="stopped",
                        state=state,
                        now=now,
                    )
                )
        elif self._fsm == "released":
            events.append(
                self._event(
                    phase="update",
                    pit_phase="released",
                    state=state,
                    now=now,
                )
            )
        return events

    def _leave_pit(self, state: RaceState, now: float) -> list[CandidateEvent]:
        events: list[CandidateEvent] = []
        self._exit_position = state.class_position or state.position
        if self._fsm not in {"exit", "outcome", "idle"}:
            if self._fsm != "released":
                events.extend(self._transition(self._fsm, "exit", state, now))
            else:
                events.extend(self._transition("released", "exit", state, now))
        events.extend(self._transition("exit", "outcome", state, now, result=True))
        self._fsm = "idle"
        self._last_dist = None
        self._dist_stable_since = None
        return events

    def _transition(
        self,
        from_phase: str,
        to_phase: str,
        state: RaceState,
        now: float,
        *,
        result: bool = False,
    ) -> list[CandidateEvent]:
        events: list[CandidateEvent] = []
        if from_phase != to_phase:
            events.append(
                self._event(
                    phase="exit",
                    pit_phase=from_phase,
                    state=state,
                    now=now,
                )
            )
        events.append(
            self._event(
                phase="trigger" if result else "enter",
                pit_phase=to_phase,
                state=state,
                now=now,
            )
        )
        self._fsm = to_phase
        return events

    def _exit_phase(self, pit_phase: str, now: float) -> list[CandidateEvent]:
        return [
            CandidateEvent(
                name="pit_story",
                channel="session",
                priority=self.priorities.pit,
                phase="exit",
                data={
                    "state": pit_phase,
                    "correlationId": self._correlation_id,
                },
            )
        ]

    def _is_moving(self, dist: float | None, now: float) -> bool:
        if dist is None or self._last_dist is None:
            return False
        if abs(dist - self._last_dist) >= _MOVING_DIST_EPS:
            self._last_dist = dist
            self._dist_stable_since = now
            return True
        return False

    def _is_stationary(self, dist: float | None, now: float) -> bool:
        if dist is None:
            return False
        if self._last_dist is None:
            self._last_dist = dist
            self._dist_stable_since = now
            return False
        if abs(dist - self._last_dist) >= _STOPPED_DIST_EPS:
            self._last_dist = dist
            self._dist_stable_since = now
            return False
        if self._dist_stable_since is None:
            self._dist_stable_since = now
        return (now - self._dist_stable_since) >= _STOPPED_HOLD_S

    def _event(
        self,
        *,
        phase: str,
        pit_phase: str,
        state: RaceState,
        now: float,
    ) -> CandidateEvent:
        position = state.class_position or state.position
        pit_duration = None
        if self._fsm not in {"idle", "outcome"} and pit_phase != "entry":
            pit_duration = round(now - (self._dist_stable_since or now), 1)
        data: dict[str, object] = {
            "state": pit_phase,
            "correlationId": self._correlation_id,
            "onPitRoad": state.on_pit_road,
            "position": position,
            "lapDistPct": state.player_lap_dist_pct,
        }
        if self._entry_position is not None:
            data["entryPosition"] = self._entry_position
        if self._exit_position is not None:
            data["exitPosition"] = self._exit_position
        if (
            pit_phase == "outcome"
            and self._entry_position is not None
            and self._exit_position is not None
        ):
            data["positionDelta"] = self._entry_position - self._exit_position
        if pit_duration is not None:
            data["pitDurationProxy"] = pit_duration
        return CandidateEvent(
            name="pit_story",
            channel="session",
            priority=self.priorities.pit,
            phase=phase,
            data=data,
        )
