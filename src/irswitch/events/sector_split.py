"""S1/S2 split callouts for Practice and Quali (not Race)."""

from __future__ import annotations

from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import EventPrioritySettings, EventSettings
from irswitch.race.timing.store import TimingStore

_TIMING_MODES = frozenset({"PRACTICE", "QUALIFYING"})
_SECTOR_IDS = frozenset({"S1", "S2"})


class SectorSplitEmitter:
    def __init__(
        self,
        store: TimingStore,
        events: EventSettings,
        priorities: EventPrioritySettings,
    ) -> None:
        self._store = store
        self._events = events
        self._priorities = priorities
        self._cursor = 0

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:  # noqa: ARG002
        if not state.connected or state.session_finished:
            return []
        if state.overlay_mode not in _TIMING_MODES:
            return []
        pending = [
            r
            for r in self._store.records_since(self._cursor)
            if r.car_id == "player" and r.valid_at_crossing
        ]
        self._cursor = self._store.append_count
        out: list[CandidateEvent] = []
        for record in pending:
            if record.timing_point_id not in _SECTOR_IDS or record.segment_time is None:
                continue
            data = {
                "sector": record.timing_point_id,
                "timingPointId": record.timing_point_id,
                "segmentTime": record.segment_time,
                "lap": record.lap_number,
            }
            out.append(
                CandidateEvent(
                    name="sector_split",
                    channel="timing",
                    priority=self._priorities.gain_found,
                    phase="trigger",
                    data=data,
                    duration=self._events.lap_duration,
                    cooldown=self._events.lap_cooldown,
                )
            )
        return out
