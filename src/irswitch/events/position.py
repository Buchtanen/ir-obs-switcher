"""Position gain/loss with stability delay and end-of-swing debounce."""

from __future__ import annotations

from dataclasses import dataclass

from irswitch.iracing.trk_loc import OFF_TRACK
from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import BattleSettings, EventPrioritySettings

IRSDK_STATE_RACING = 4


def place_of(state: RaceState) -> int | None:
    return state.class_position if state.class_position is not None else state.position


def should_seed_place(state: RaceState, last_source: str | None) -> tuple[str, bool]:
    """Return (source, seed_without_emit).

    Pre-green Race and official→live switches reseed so parade/grid jumps
    do not fire POSITION_GAINED/LOST.
    """
    source = state.position_source or "official"
    if (state.overlay_mode or "") == "RACE" and (state.session_state or 0) < IRSDK_STATE_RACING:
        return source, True
    if last_source is not None and last_source != source:
        return source, True
    return source, False


@dataclass(frozen=True)
class PositionSwing:
    """One settled gain/loss from episode start to the last accepted place."""

    old: int
    new: int
    delta: int  # old - new; positive = gained places (P8 → P7)

    @property
    def places(self) -> int:
        return abs(self.delta)

    @property
    def direction(self) -> str:
        return "gain" if self.delta > 0 else "loss"


class PositionSwingTracker:
    """Hold until the place stops changing, then emit one cumulative swing.

    Single-place changes use ``position_stable_seconds``. After an incident or
    when two or more places moved, wait ``position_swing_debounce_s`` from the
    last change so a pile-up or multi-car pass becomes one event.
    """

    def __init__(self, battle: BattleSettings) -> None:
        self._stable_s = battle.position_stable_seconds
        self._swing_s = battle.position_swing_debounce_s
        self._incident_window_s = battle.position_incident_window_s
        self._confirmed: int | None = None
        self._pending: int | None = None
        self._pending_since: float | None = None
        self._source: str | None = None
        self._last_incidents: int | None = None
        self._post_incident_until: float = 0.0

    @property
    def confirmed(self) -> int | None:
        return self._confirmed

    def reset(self) -> None:
        self._confirmed = None
        self._pending = None
        self._pending_since = None
        self._source = None
        self._last_incidents = None
        self._post_incident_until = 0.0

    def tick(self, state: RaceState, now: float) -> PositionSwing | None:
        if not state.connected:
            self.reset()
            return None
        self._note_incident(state, now)
        current = place_of(state)
        if current is None:
            return None
        source, seed = should_seed_place(state, self._source)
        self._source = source
        if seed:
            self._confirmed = current
            self._clear_pending()
            return None
        if self._confirmed is None:
            self._confirmed = current
            return None
        if current == self._confirmed:
            self._clear_pending()
            return None
        if self._pending != current:
            self._pending = current
            self._pending_since = now
            return None
        if self._pending_since is None:
            return None
        needed = self._debounce_s(self._confirmed, current, now)
        if now - self._pending_since < needed:
            return None
        old = self._confirmed
        self._confirmed = current
        self._clear_pending()
        return PositionSwing(old=old, new=current, delta=old - current)

    def _note_incident(self, state: RaceState, now: float) -> None:
        incidents = state.incidents
        if incidents is not None:
            if self._last_incidents is not None and incidents > self._last_incidents:
                self._post_incident_until = now + self._incident_window_s
            self._last_incidents = incidents
        if state.player_track_surface == OFF_TRACK:
            self._post_incident_until = now + self._incident_window_s

    def _debounce_s(self, start: int, end: int, now: float) -> float:
        multi = abs(start - end) >= 2
        post_incident = now < self._post_incident_until
        if multi or post_incident:
            return max(self._stable_s, self._swing_s)
        return self._stable_s

    def _clear_pending(self) -> None:
        self._pending = None
        self._pending_since = None


def _position_change_event(swing: PositionSwing, priority: int) -> CandidateEvent:
    return CandidateEvent(
        name="position_change",
        channel="alert",
        priority=priority,
        phase="trigger",
        data={
            "direction": swing.direction,
            "oldPosition": swing.old,
            "newPosition": swing.new,
            "delta": swing.delta,
            "places": swing.places,
        },
    )


class PositionEmitter:
    def __init__(self, battle: BattleSettings, priorities: EventPrioritySettings) -> None:
        self._tracker = PositionSwingTracker(battle)
        self._priorities = priorities

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:
        swing = self._tracker.tick(state, now)
        if swing is None:
            return []
        return [_position_change_event(swing, self._priorities.position_change)]
