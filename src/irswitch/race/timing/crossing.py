"""Forward crossing detection with lap-wrap and reverse-motion guards."""

from __future__ import annotations

from dataclasses import dataclass, field

from irswitch.race.timing.points import TimingPoint, default_minisectors, start_finish_point

# Ignore jitter / standing still.
MIN_FORWARD_DELTA = 0.0005
# Treat backward jump as reverse/tow — no crossings.
MAX_REVERSE_DELTA = 0.002
# Lap-wrap without lap increment yet (telemetry lag).
WRAP_DROP_THRESHOLD = 0.5


@dataclass(frozen=True)
class CrossingEvent:
    car_id: str
    lap_number: int
    timing_point_id: str
    crossing_timestamp: float
    lap_dist_pct: float


@dataclass
class _CarTrackState:
    lap: int | None = None
    pct: float | None = None


@dataclass
class CrossingDetector:
    """Detect timing-point crossings from sequential lapDistPct samples."""

    points: tuple[TimingPoint, ...] = field(default_factory=default_minisectors)
    min_forward_delta: float = MIN_FORWARD_DELTA
    _state: dict[str, _CarTrackState] = field(default_factory=dict, repr=False)

    def reset(self) -> None:
        self._state.clear()

    def update(
        self,
        *,
        car_id: str,
        lap_number: int | None,
        lap_dist_pct: float | None,
        timestamp: float,
    ) -> list[CrossingEvent]:
        if lap_number is None or lap_dist_pct is None:
            return []
        prev = self._state.get(car_id)
        if prev is None or prev.lap is None or prev.pct is None:
            self._state[car_id] = _CarTrackState(lap=lap_number, pct=lap_dist_pct)
            return []

        events: list[CrossingEvent] = []
        prev_lap, prev_pct = prev.lap, prev.pct
        curr_lap, curr_pct = lap_number, lap_dist_pct

        if curr_lap > prev_lap:
            sf = start_finish_point()
            events.append(
                CrossingEvent(
                    car_id=car_id,
                    lap_number=curr_lap,
                    timing_point_id=sf.id,
                    crossing_timestamp=timestamp,
                    lap_dist_pct=sf.lap_dist_pct,
                )
            )
            self._state[car_id] = _CarTrackState(lap=curr_lap, pct=curr_pct)
            return events

        if curr_lap < prev_lap:
            self._state[car_id] = _CarTrackState(lap=curr_lap, pct=curr_pct)
            return []

        delta = curr_pct - prev_pct
        if delta < -MAX_REVERSE_DELTA:
            if prev_pct - curr_pct >= WRAP_DROP_THRESHOLD:
                self._state[car_id] = _CarTrackState(lap=curr_lap, pct=curr_pct)
            return []

        if delta < self.min_forward_delta:
            return []

        for point in self._points_between(prev_pct, curr_pct):
            events.append(
                CrossingEvent(
                    car_id=car_id,
                    lap_number=curr_lap,
                    timing_point_id=point.id,
                    crossing_timestamp=timestamp,
                    lap_dist_pct=point.lap_dist_pct,
                )
            )

        self._state[car_id] = _CarTrackState(lap=curr_lap, pct=curr_pct)
        return events

    def _points_between(self, prev_pct: float, curr_pct: float) -> list[TimingPoint]:
        crossed: list[TimingPoint] = []
        for point in self.points:
            if point.lap_dist_pct == 0.0:
                continue
            if prev_pct < point.lap_dist_pct <= curr_pct:
                crossed.append(point)
        return crossed
