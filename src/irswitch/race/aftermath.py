"""Incident aftermath FSM: stalled vs rolling, then BACK_UNDER_WAY."""

from __future__ import annotations

from dataclasses import dataclass, field

from irswitch.events.envelope import EventEnvelope, make_envelope
from irswitch.iracing.trk_loc import OFF_TRACK, is_on_track, is_towing
from irswitch.overlay.models import RaceState

_AFTERMATH_PRIORITY = 72
_BACK_UNDER_WAY_PRIORITY = 68
_CLASSIFY_WINDOW_S = 1.2
_MOVING_DIST_EPS = 0.0008
_ROLLING_HOLD_S = 0.35
_RECOVERY_HOLD_S = 0.6


@dataclass
class IncidentAftermathFsm:
    """Watch incident count rises → classify stalled/rolling → optional recovery.

    Deterministic, fail-soft. Uses track surface, tow time, and LapDistPct
    motion (Speed is not on RaceState yet).
    """

    _phase: str = "idle"  # idle | classify | stalled
    _last_incidents: int | None = None
    _classify_deadline: float = 0.0
    _incident_total: int | None = None
    _incident_delta: int = 0
    _last_dist: float | None = None
    _moving_since: float | None = None
    _cycle: int = 0
    _correlation_id: str = ""
    _mode: str = "GENERIC"
    _pending: list[EventEnvelope] = field(default_factory=list)

    def reset(self) -> None:
        self._phase = "idle"
        self._last_incidents = None
        self._classify_deadline = 0.0
        self._incident_total = None
        self._incident_delta = 0
        self._last_dist = None
        self._moving_since = None
        self._correlation_id = ""
        self._pending.clear()

    def take_pending(self) -> list[EventEnvelope]:
        out = list(self._pending)
        self._pending.clear()
        return out

    def tick(self, state: RaceState, now: float) -> list[EventEnvelope]:
        """Advance FSM; return newly produced derived envelopes."""
        produced: list[EventEnvelope] = []
        if not state.connected:
            self.reset()
            return produced

        self._mode = state.overlay_mode or "GENERIC"
        incidents = state.incidents
        if incidents is None:
            return produced

        prev = self._last_incidents
        self._last_incidents = incidents
        moving = self._update_motion(state, now)

        if prev is None:
            return produced

        if incidents > prev and self._phase == "idle":
            self._begin_classify(state, now, prev=prev, total=incidents)

        if self._phase == "classify":
            produced.extend(self._tick_classify(state, now, moving=moving))
        elif self._phase == "stalled":
            produced.extend(self._tick_stalled(state, now, moving=moving))

        if produced:
            self._pending.extend(produced)
        return produced

    def _begin_classify(self, state: RaceState, now: float, *, prev: int, total: int) -> None:
        self._cycle += 1
        sid = state.subsession_id or "unknown"
        num = state.session_num if state.session_num is not None else 0
        self._correlation_id = f"aftermath:{sid}:{num}:{self._cycle}"
        self._incident_total = total
        self._incident_delta = max(0, total - prev)
        self._phase = "classify"
        self._classify_deadline = now + _CLASSIFY_WINDOW_S
        self._moving_since = now if self._moving_since is not None else None

    def _tick_classify(self, state: RaceState, now: float, *, moving: bool) -> list[EventEnvelope]:
        if self._looks_stalled(state):
            return self._emit_aftermath(state, now, kind="stalled")
        if self._looks_rolling(state, now, moving=moving):
            return self._emit_aftermath(state, now, kind="rolling")
        if now >= self._classify_deadline:
            kind = "stalled" if self._looks_stalled(state) else "rolling"
            return self._emit_aftermath(state, now, kind=kind)
        return []

    def _tick_stalled(self, state: RaceState, now: float, *, moving: bool) -> list[EventEnvelope]:
        if is_towing(state.player_tow_time) or not is_on_track(state.player_track_surface):
            self._moving_since = None
            return []
        if moving and self._moving_since is not None:
            if (now - self._moving_since) >= _RECOVERY_HOLD_S:
                return self._emit_back_under_way(state, now)
            return []
        if not moving:
            self._moving_since = None
        return []

    def _emit_aftermath(self, state: RaceState, now: float, *, kind: str) -> list[EventEnvelope]:
        metrics = {
            "kind": kind,
            "value": self._incident_delta,
            "total": self._incident_total,
            "surface": state.player_track_surface,
            "tow": bool(is_towing(state.player_tow_time)),
        }
        env = make_envelope(
            event_type="INCIDENT_AFTERMATH",
            phase="RESULT",
            mode=self._mode,
            priority=_AFTERMATH_PRIORITY,
            monotonic_ms=int(now * 1000),
            metrics=metrics,
            correlation_id=self._correlation_id,
        )
        if kind == "stalled":
            self._phase = "stalled"
            self._moving_since = None
        else:
            self._phase = "idle"
        return [env]

    def _emit_back_under_way(self, state: RaceState, now: float) -> list[EventEnvelope]:
        metrics = {
            "kind": "back_under_way",
            "total": self._incident_total,
            "position": state.class_position or state.position,
        }
        env = make_envelope(
            event_type="BACK_UNDER_WAY",
            phase="RESULT",
            mode=self._mode,
            priority=_BACK_UNDER_WAY_PRIORITY,
            monotonic_ms=int(now * 1000),
            metrics=metrics,
            correlation_id=self._correlation_id,
        )
        self._phase = "idle"
        self._moving_since = None
        return [env]

    def _looks_stalled(self, state: RaceState) -> bool:
        if is_towing(state.player_tow_time):
            return True
        surface = state.player_track_surface
        if surface is None:
            return False
        if surface == OFF_TRACK or not is_on_track(surface):
            return True
        return False

    def _looks_rolling(self, state: RaceState, now: float, *, moving: bool) -> bool:
        if is_towing(state.player_tow_time):
            return False
        if not is_on_track(state.player_track_surface):
            return False
        if not moving or self._moving_since is None:
            return False
        return (now - self._moving_since) >= _ROLLING_HOLD_S

    def _update_motion(self, state: RaceState, now: float) -> bool:
        """Sample LapDistPct once per tick. Returns whether the car moved."""
        dist = state.player_lap_dist_pct
        prev = self._last_dist
        self._last_dist = dist
        if dist is None or prev is None:
            return False
        delta = abs(float(dist) - float(prev))
        if delta > 0.5:
            delta = 1.0 - delta
        moving = delta >= _MOVING_DIST_EPS
        if moving:
            if self._moving_since is None:
                self._moving_since = now
        else:
            self._moving_since = None
        return moving
