"""Current-signal excursion reducer. No incident-counter, dynamics or damage guesses.

This native, bounded reducer is the executable subset of the composite story spec;
the design JSON is not loaded/executed. All time is supplied by the caller.
"""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from irswitch.events.envelope import EventEnvelope, make_envelope
from irswitch.events.scenarios.model import EpisodeScope, ScenarioBeat, thaw_json
from irswitch.iracing.trk_loc import APPROACHING_PITS, IN_PIT_STALL, OFF_TRACK, ON_TRACK
from irswitch.overlay.models import RaceState

SCENARIO_ID = "track_excursion"
EVENT_TYPE = "TRACK_EXCURSION"
MAX_SAMPLE_GAP_S = 1.0
MAX_EPISODE_S = 90.0
ENTRY_HOLD_S = 0.2
REJOIN_HOLD_S = 0.2
STOP_HOLD_S = 0.35
MOTION_HOLD_S = 0.6


@dataclass
class TrackExcursionDetector:
    """Independent surface/motion holds with one bounded session/run/hero episode."""

    _scope: EpisodeScope | None = None
    _track_id: str | None = None
    _mode: str = ""
    _sequence: int = 0
    _last_at: float | None = None
    _armed: bool = False
    _episode: str = ""
    _started_at: float = 0.0
    _holds: dict[str, float] = field(default_factory=dict)
    _emitted: set[str] = field(default_factory=set)
    _evidence_sig: tuple[object, ...] | None = None
    _trace: deque[dict[str, Any]] = field(default_factory=lambda: deque(maxlen=128))

    def reset(self, *, reason: str = "reset", now: float | None = None) -> None:
        if self._episode:
            self._trace.append(
                {
                    "action": "invalidated",
                    "reason": reason,
                    "parentStoryId": self._episode,
                    "at": now,
                }
            )
        self._episode = ""
        self._armed = False
        self._holds.clear()
        self._emitted.clear()
        self._last_at = None

    def take_trace(self) -> list[dict[str, Any]]:
        out = list(self._trace)
        self._trace.clear()
        return out

    def tick(self, state: RaceState, now: float) -> list[EventEnvelope]:
        if not math.isfinite(now) or now < 0:
            return []
        scope = _scope(state)
        if (
            scope != self._scope
            or state.track_id != self._track_id
            or state.overlay_mode != self._mode
        ):
            self.reset(reason="scope_changed", now=now)
            self._scope, self._track_id, self._mode = scope, state.track_id, state.overlay_mode
        if self._last_at is not None and now <= self._last_at:
            return []
        speed_value, tow_value = _number(state.speed_mps), _number(state.player_tow_time)
        speed_band = (
            "unknown"
            if speed_value is None
            else "stopped" if speed_value <= 1 else "moving" if speed_value >= 2.5 else "transition"
        )
        tow_band = "unknown" if tow_value is None else "active" if tow_value > 0 else "clear"
        sig = (
            scope,
            state.connected,
            state.data_quality,
            state.overlay_mode,
            state.player_track_surface,
            state.on_pit_road,
            speed_band,
            tow_band,
        )
        if sig != self._evidence_sig:
            self._evidence_sig = sig
            self._trace.append(
                {
                    "action": "observation_changed",
                    "at": now,
                    "parentStoryId": self._episode,
                    "scenarioId": SCENARIO_ID,
                    "reason": "evidence_changed",
                    "connected": state.connected,
                    "dataQuality": state.data_quality,
                    "surface": state.player_track_surface,
                    "onPitRoad": state.on_pit_road,
                    "speedBand": speed_band,
                    "speedMps": speed_value,
                    "towTime": tow_value,
                    "towEvidence": tow_band,
                    "runEpoch": state.run_epoch,
                    "heroCarIdx": state.player_car_idx,
                }
            )
        if (
            not state.connected
            or scope is None
            or state.overlay_mode not in {"RACE", "PRACTICE", "QUALIFYING"}
            or state.data_quality != "ok"
            or (
                state.stale_for_ms is not None
                and (not math.isfinite(state.stale_for_ms) or state.stale_for_ms > 500)
            )
        ):
            self.reset(reason="evidence_unavailable", now=now)
            return []
        if self._last_at is not None and now - self._last_at > MAX_SAMPLE_GAP_S:
            self.reset(reason="sample_gap", now=now)
        self._last_at = now
        if self._episode and now - self._started_at >= MAX_EPISODE_S:
            self.reset(reason="episode_timeout", now=now)
            self._last_at = now
            return []

        surface = state.player_track_surface
        tow = _number(state.player_tow_time)
        speed = _number(state.speed_mps)
        on_track = surface == ON_TRACK and not state.on_pit_road and tow == 0
        off_track = surface == OFF_TRACK and not state.on_pit_road and tow == 0
        # Requiring a preceding valid on-track sample avoids narrating parked cars
        # or loading into an already off-track snapshot as a new excursion.
        if not self._episode and on_track:
            self._armed = True
        if not self._episode:
            if not self._held("offtrack", self._armed and off_track, ENTRY_HOLD_S, now):
                return []
            return self._open_episode(scope, state, now)

        # Terminal evidence wins over simultaneous surface/motion development.
        if tow is not None and tow > 0:
            if state.overlay_mode == "RACE":
                return self._terminal(
                    state, now, "tow_started_race", "tow_started", "tow_timer_positive"
                )
            # Tow in Practice/Quali is not proof of an ESC reset or of damage.
            self.reset(reason="nonrace_tow_unclassified", now=now)
            return []
        if self._held(
            "surface_unknown",
            surface not in {OFF_TRACK, ON_TRACK, APPROACHING_PITS, IN_PIT_STALL},
            MAX_SAMPLE_GAP_S,
            now,
        ):
            self.reset(reason="surface_unavailable", now=now)
            return []
        if self._held(
            "renewed_offtrack", "track_rejoined" in self._emitted and off_track, ENTRY_HOLD_S, now
        ):
            self.reset(reason="renewed_excursion", now=now)
            self._last_at = now
            return self._open_episode(scope, state, now)
        in_pits = state.on_pit_road and surface in {APPROACHING_PITS, IN_PIT_STALL}
        if self._held("pit", in_pits, REJOIN_HOLD_S, now):
            return self._terminal(
                state,
                now,
                "pit_return_observed",
                "pit_return_observed",
                "pit_road_and_surface_held",
            )
        produced = []
        stopped = surface in {OFF_TRACK, ON_TRACK} and tow == 0 and speed is not None and speed <= 1
        if self._held("stopped", stopped, STOP_HOLD_S, now) and "stopped" not in self._emitted:
            produced.append(
                self._emit(
                    state,
                    now,
                    "stopped",
                    "development",
                    "stopped_after_excursion",
                    "speed_below_stop_held",
                )
            )
        rejoined = self._held("rejoined", on_track, REJOIN_HOLD_S, now)
        moving = self._held(
            "moving", on_track and speed is not None and speed >= 2.5, MOTION_HOLD_S, now
        )
        if rejoined and "track_rejoined" not in self._emitted:
            produced.append(
                self._emit(
                    state, now, "track_rejoined", "closure", "back_on_track", "surface_ontrack_held"
                )
            )
        if moving and "track_rejoined" in self._emitted:
            produced.extend(
                self._terminal(
                    state, now, "motion_restored", "motion_restored", "ontrack_speed_moving_held"
                )
            )
        return produced

    def _open_episode(
        self, scope: EpisodeScope, state: RaceState, now: float
    ) -> list[EventEnvelope]:
        self._sequence += 1
        self._episode = scope.episode_id(self._sequence)
        self._started_at = now
        self._emitted.clear()
        self._holds.clear()
        self._armed = False
        return [self._emit(state, now, "offtrack", "root", "unknown", "surface_offtrack_held")]

    def _held(self, key: str, matched: bool, duration: float, now: float) -> bool:
        if not matched:
            self._holds.pop(key, None)
            return False
        start = self._holds.setdefault(key, now)
        return now - start >= duration - 1e-9

    def _terminal(
        self, state: RaceState, now: float, beat: str, outcome: str, reason: str
    ) -> list[EventEnvelope]:
        event = self._emit(state, now, beat, "terminal", outcome, reason)
        self._episode = ""
        self._holds.clear()
        self._emitted.clear()
        self._armed = False
        return [event]

    def _emit(
        self, state: RaceState, now: float, beat_id: str, role: str, outcome: str, reason: str
    ) -> EventEnvelope:
        metrics: dict[str, object] = {
            "scenarioId": SCENARIO_ID,
            "scenarioVersion": 1,
            "episodeId": self._episode,
            "parentStoryId": self._episode,
            "beatId": beat_id,
            "beatRole": role,
            "branch": beat_id,
            "primaryRelation": "track_excursion",
            "cause": "unknown",
            "outcome": outcome,
            "damage": "unknown",
            "evidenceLevel": "CONFIRMED",
            "runEpoch": state.run_epoch,
            "heroCarIdx": state.player_car_idx,
            "reason": reason,
            "observedAt": now,
            "episodeStartedAt": self._started_at,
            "surface": state.player_track_surface,
            "speedMps": _number(state.speed_mps),
            "towTime": _number(state.player_tow_time),
            "onPitRoad": state.on_pit_road,
            "staleForMs": _number(state.stale_for_ms),
        }
        beat = ScenarioBeat(
            SCENARIO_ID,
            1,
            self._episode,
            self._episode,
            beat_id,
            EVENT_TYPE,
            "RESULT",
            90,
            1.0,
            reason,
            metrics,
        )
        event = make_envelope(
            event_type=beat.event_type,
            phase=beat.phase,
            mode=state.overlay_mode,
            session_id=f"{state.subsession_id}:{state.session_num}",
            monotonic_ms=int(now * 1000),
            priority=beat.priority,
            confidence=beat.confidence,
            correlation_id=beat.correlation_id,
            metrics=thaw_json(beat.metrics),
            subject={"car_id": str(state.player_car_idx)},
            reason={"detector": SCENARIO_ID, "rules": [reason]},
        )
        self._emitted.add(beat_id)
        self._trace.append({"action": "detected", "at": now, **event.metrics})
        return event


def _number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and value >= 0 else None


def _scope(state: RaceState) -> EpisodeScope | None:
    if state.subsession_id is None or state.session_num is None or state.player_car_idx is None:
        return None
    try:
        return EpisodeScope(
            SCENARIO_ID,
            str(state.subsession_id),
            state.session_num,
            state.run_epoch,
            state.player_car_idx,
        )
    except ValueError:
        return None
