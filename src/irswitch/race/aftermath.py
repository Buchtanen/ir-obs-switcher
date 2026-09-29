"""Evidence-based incident aftermath, recovery, tow, and repair facts."""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from irswitch.events.envelope import EventEnvelope, make_envelope
from irswitch.iracing.trk_loc import OFF_TRACK, ON_TRACK, is_on_track, is_towing
from irswitch.overlay.models import RaceState
from irswitch.race.watcher_log import WatcherLog, note

_AFTERMATH_PRIORITY = 72
_BACK_UNDER_WAY_PRIORITY = 68
_CLASSIFY_WINDOW_S = 1.2
_MOVING_DIST_EPS = 0.0008
_ROLLING_HOLD_S = 0.35
_RECOVERY_HOLD_S = 0.6
# Motion hysteresis; surface and tow are separate evidence.
_STALLED_SPEED_MPS = 1.0
_ROLLING_SPEED_MPS = 2.5


@dataclass
class IncidentAftermathFsm:
    """Classify motion, surface and tow independently from current SDK evidence."""

    _phase: str = "idle"  # idle | classify | stopped | off_track | towing
    _stopped_since: float | None = None
    _on_track_since: float | None = None
    _identity: tuple[object, ...] | None = None
    _last_now: float | None = None
    _repair_signature: tuple[object, ...] | None = None
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
        self._stopped_since = None
        self._on_track_since = None
        self._identity = None
        self._last_now = None
        self._repair_signature = None
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

    def tick(
        self, state: RaceState, now: float, *, log: WatcherLog | None = None
    ) -> list[EventEnvelope]:
        """Advance FSM; return newly produced derived envelopes."""
        produced: list[EventEnvelope] = []
        if (
            not state.connected
            or state.data_quality != "ok"
            or (state.stale_for_ms is not None and state.stale_for_ms > 2000)
        ):
            self.reset()
            return produced

        identity = (state.subsession_id, state.session_num, state.run_epoch)
        if (
            self._identity != identity
            or (self._last_now is not None and (now < self._last_now or now - self._last_now > 2.0))
            or (
                state.incidents is not None
                and self._last_incidents is not None
                and state.incidents < self._last_incidents
            )
        ):
            self.reset()
        self._identity = identity
        self._last_now = now
        self._mode = state.overlay_mode or "GENERIC"
        produced.extend(self._repair_update(state, now))
        incidents = state.incidents
        if incidents is None:
            self._phase = "idle"
            self._last_incidents = None
            self._moving_since = self._stopped_since = self._on_track_since = None
            self._pending.extend(produced)
            return produced

        prev = self._last_incidents
        self._last_incidents = incidents
        moving = self._update_motion(state, now)

        if prev is None:
            self._pending.extend(produced)
            return produced

        if incidents > prev and self._phase == "idle":
            self._begin_classify(state, now, prev=prev, total=incidents)

        if self._phase == "classify":
            produced.extend(self._tick_classify(state, now, moving=moving))
        elif self._phase in {"stopped", "off_track", "towing"}:
            produced.extend(self._tick_stalled(state, now, moving=moving))

        if produced:
            self._pending.extend(produced)
            for env in produced:
                note(
                    log,
                    watch="aftermath",
                    kind=env.event_type,
                    emitted=True,
                    reason=str((env.metrics or {}).get("kind") or "emit"),
                    confidence=1.0,
                    now=now,
                )
        return produced

    def _repair_update(self, state: RaceState, now: float) -> list[EventEnvelope]:
        warnings = state.engine_warnings
        mandatory = None if warnings is None else bool(warnings & 0x80)
        optional = None if warnings is None else bool(warnings & 0x100)
        service_active = state.player_in_pit_stall is True and state.pit_service_status == 1
        required_s = state.pit_repair_left if service_active else None
        optional_s = state.pit_opt_repair_left if service_active else None
        signature = (
            mandatory,
            optional,
            bool(required_s and required_s > 0),
            bool(optional_s and optional_s > 0),
        )
        if signature == self._repair_signature:
            return []
        self._repair_signature = signature
        if not any(value is True for value in signature):
            return []  # Cleared flags do not prove a completely undamaged car.
        metrics = {"fact": "repairs", "repairServiceActive": service_active}
        if mandatory is not None:
            metrics["mandatoryRepairRequired"] = mandatory
            metrics["optionalRepairRequired"] = optional
        if required_s is not None and required_s > 0:
            metrics["mandatoryRepairSeconds"] = round(required_s, 3)
        if optional_s is not None and optional_s > 0:
            metrics["optionalRepairSeconds"] = round(optional_s, 3)
        self._cycle += 1
        return [
            make_envelope(
                event_type="FIELD_FACT",
                phase="RESULT",
                mode=self._mode,
                priority=60,
                monotonic_ms=int(now * 1000),
                metrics=metrics,
                correlation_id=f"repairs:{state.subsession_id}:{state.session_num}:{self._cycle}",
            )
        ]

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
        if is_towing(state.player_tow_time):
            return self._emit_aftermath(state, now, kind="towing")
        if self._stopped_since is not None and now - self._stopped_since >= _RECOVERY_HOLD_S:
            return self._emit_aftermath(state, now, kind="stopped")
        if state.player_track_surface == OFF_TRACK:
            return self._emit_aftermath(state, now, kind="off_track")
        if self._looks_rolling(state, now, moving=moving):
            return self._emit_aftermath(state, now, kind="rolling")
        if now >= self._classify_deadline:
            self._phase = "idle"  # Unknown movement is not evidence of a stop.
        return []

    def _tick_stalled(self, state: RaceState, now: float, *, moving: bool) -> list[EventEnvelope]:
        if is_towing(state.player_tow_time):
            if self._phase != "towing":
                return self._emit_aftermath(state, now, kind="towing")
            return []
        if self._phase == "towing":
            # Tow completion/teleport never implies driving recovery.
            self._phase = "idle"
            self._moving_since = None
            return []
        if self._phase == "off_track":
            if self._stopped_since is not None and now - self._stopped_since >= _RECOVERY_HOLD_S:
                return self._emit_aftermath(state, now, kind="stopped")
            if (
                is_on_track(state.player_track_surface)
                and self._on_track_since is not None
                and now - self._on_track_since >= _RECOVERY_HOLD_S
                and moving
            ):
                return self._emit_aftermath(state, now, kind="rejoined")
            return []
        if (
            moving
            and self._moving_since is not None
            and now - self._moving_since >= _RECOVERY_HOLD_S
        ):
            if state.player_track_surface in {OFF_TRACK, ON_TRACK}:
                return self._emit_back_under_way(state, now)
        return []

    def _emit_aftermath(self, state: RaceState, now: float, *, kind: str) -> list[EventEnvelope]:
        metrics = {
            "kind": kind,
            "value": self._incident_delta,
            "total": self._incident_total,
            "surface": state.player_track_surface,
            "tow": bool(is_towing(state.player_tow_time)),
            "motionVerified": kind in {"stopped", "rolling"},
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
        if kind in {"stopped", "off_track", "towing"}:
            self._phase = kind
            if kind == "stopped":
                self._moving_since = None
        else:
            self._phase = "idle"
        return [env]

    def _emit_back_under_way(self, state: RaceState, now: float) -> list[EventEnvelope]:
        metrics = {
            "kind": "back_under_way",
            "previouslyStopped": True,
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

    def _looks_rolling(self, state: RaceState, now: float, *, moving: bool) -> bool:
        if is_towing(state.player_tow_time):
            return False
        if not is_on_track(state.player_track_surface):
            return False
        if not moving or self._moving_since is None:
            return False
        return (now - self._moving_since) >= _ROLLING_HOLD_S

    def _update_motion(self, state: RaceState, now: float) -> bool:
        """Sample Speed (when set) and LapDistPct. Returns whether the car moved.

        Missing or low-resolution distance alone cannot establish a stop.
        """
        dist_moving = self._dist_moved(state)
        speed = state.speed_mps
        stopped = (
            speed is not None
            and math.isfinite(speed)
            and 0 <= speed <= _STALLED_SPEED_MPS
            and not dist_moving
            and state.player_track_surface in {OFF_TRACK, ON_TRACK}
            and not is_towing(state.player_tow_time)
        )
        if stopped:
            if self._stopped_since is None:
                self._stopped_since = now
        else:
            self._stopped_since = None
        if is_on_track(state.player_track_surface):
            if self._on_track_since is None:
                self._on_track_since = now
        else:
            self._on_track_since = None
        speed_moving = _speed_moving(state.speed_mps)
        moving = dist_moving if speed_moving is None else speed_moving
        if moving:
            if self._moving_since is None:
                self._moving_since = now
        else:
            self._moving_since = None
        return moving

    def _dist_moved(self, state: RaceState) -> bool:
        dist = state.player_lap_dist_pct
        prev = self._last_dist
        self._last_dist = dist
        if dist is None or prev is None:
            return False
        delta = abs(float(dist) - float(prev))
        if delta > 0.5:
            delta = 1.0 - delta
        return delta >= _MOVING_DIST_EPS


def _speed_moving(speed_mps: float | None) -> bool | None:
    """True/False from Speed; None = missing or hysteresis band (use LapDistPct)."""
    if speed_mps is None or not math.isfinite(speed_mps) or speed_mps < 0:
        return None
    if speed_mps <= _STALLED_SPEED_MPS:
        return False
    if speed_mps >= _ROLLING_SPEED_MPS:
        return True
    return None
