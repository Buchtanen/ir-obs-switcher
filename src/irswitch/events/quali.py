"""Qualifying projection emitters (projected lap + soft position range)."""

from __future__ import annotations

from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import EventPrioritySettings, EventSettings
from irswitch.race.timing.reference import SegmentReferenceTracker
from irswitch.race.timing.store import TimingRecord, TimingStore

MIN_DIST_PCT = 0.15
PROJECTED_DELTA_S = 0.05
MIN_CONFIDENCE = 0.35
POSITION_ATTACK_CONFIDENCE = 0.7


class QualiEmitter:
    def __init__(
        self,
        store: TimingStore,
        reference: SegmentReferenceTracker,
        events: EventSettings,
        priorities: EventPrioritySettings,
    ) -> None:
        self._store = store
        self._reference = reference
        self._events = events
        self._priorities = priorities
        self._cursor = 0
        self._active = False
        self._last_projected: float | None = None

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:  # noqa: ARG002
        if state.overlay_mode != "QUALIFYING" or not state.connected:
            return []
        pending = [
            r
            for r in self._store.records_since(self._cursor)
            if r.car_id == "player" and r.valid_at_crossing
        ]
        self._cursor = len(self._store)

        out: list[CandidateEvent] = []
        if pending:
            out.extend(self._from_crossings(pending, state))
        out.extend(self._from_lap_progress(state))
        return out

    def _from_crossings(
        self, pending: list[TimingRecord], state: RaceState
    ) -> list[CandidateEvent]:
        events: list[CandidateEvent] = []
        segment_sum = 0.0
        segments_seen = 0
        for record in pending:
            if record.segment_time is None or record.timing_point_id == "MS00":
                continue
            self._reference.compare_segment(record.timing_point_id, record.segment_time)
            segment_sum += record.segment_time
            segments_seen += 1
        projected = self._reference.projected_lap_from_segments(segment_sum, segments_seen, 20)
        if projected is None:
            return events
        confidence = min(1.0, max(segments_seen, len(pending)) / 8.0)
        return self._emit_projection(projected, confidence, state)

    def _from_lap_progress(self, state: RaceState) -> list[CandidateEvent]:
        dist = state.player_lap_dist_pct
        lap_time = state.current_lap_time
        if dist is None or lap_time is None or dist < MIN_DIST_PCT:
            return []
        projected = lap_time / dist
        confidence = min(1.0, dist / 0.5)
        return self._emit_projection(projected, confidence, state)

    def _emit_projection(
        self, projected: float, confidence: float, state: RaceState
    ) -> list[CandidateEvent]:
        if confidence < MIN_CONFIDENCE:
            return []
        if (
            self._last_projected is not None
            and abs(projected - self._last_projected) < PROJECTED_DELTA_S
            and self._active
        ):
            return []

        self._last_projected = projected
        data = {
            "projectedTime": round(projected, 3),
            "confidence": round(confidence, 2),
            "bestLap": state.best_lap_time,
            "position": state.position,
        }
        phase = "enter" if not self._active else "update"
        self._active = True
        out = [
            CandidateEvent(
                name="projected_lap",
                channel="timing",
                priority=self._priorities.projected_lap,
                phase=phase,
                data=data,
                duration=self._events.lap_duration,
                cooldown=self._events.lap_cooldown,
            )
        ]
        if (
            confidence >= POSITION_ATTACK_CONFIDENCE
            and state.best_lap_time is not None
            and projected < state.best_lap_time - 0.05
            and state.position is not None
        ):
            out.append(
                CandidateEvent(
                    name="position_attack",
                    channel="timing",
                    priority=self._priorities.position_attack,
                    phase="trigger",
                    data={
                        **data,
                        "targetPosition": max(1, state.position - 1),
                    },
                    duration=self._events.lap_duration,
                    cooldown=self._events.lap_cooldown,
                )
            )
        return out
