"""Practice-session timing emitters (gain/lost minisector deltas)."""

from __future__ import annotations

from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import EventPrioritySettings, EventSettings
from irswitch.race.timing.reference import SegmentReferenceTracker
from irswitch.race.timing.store import TimingStore

GAIN_THRESHOLD_S = 0.05
TIME_LOST_THRESHOLD_S = 0.08


class PracticeEmitter:
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

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:  # noqa: ARG002
        if state.overlay_mode != "PRACTICE" or not state.connected:
            return []
        pending = [
            r
            for r in self._store.records_since(self._cursor)
            if r.car_id == "player" and r.valid_at_crossing
        ]
        self._cursor = len(self._store)
        if not pending:
            return []

        out: list[CandidateEvent] = []
        for record in pending:
            if record.timing_point_id == "MS00" or record.segment_time is None:
                continue
            delta = self._reference.compare_segment(record.timing_point_id, record.segment_time)
            if delta is None:
                continue
            data = {
                "timingPointId": record.timing_point_id,
                "segmentTime": record.segment_time,
                "delta": round(delta, 3),
                "lap": record.lap_number,
            }
            if delta <= -GAIN_THRESHOLD_S:
                out.append(
                    CandidateEvent(
                        name="gain_found",
                        channel="timing",
                        priority=self._priorities.gain_found,
                        phase="trigger",
                        data=data,
                        duration=self._events.lap_duration,
                        cooldown=self._events.lap_cooldown,
                    )
                )
            elif delta >= TIME_LOST_THRESHOLD_S:
                out.append(
                    CandidateEvent(
                        name="time_lost",
                        channel="timing",
                        priority=self._priorities.time_lost,
                        phase="trigger",
                        data=data,
                        duration=self._events.lap_duration,
                        cooldown=self._events.lap_cooldown,
                    )
                )
        return out
