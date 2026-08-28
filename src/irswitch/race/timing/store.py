"""Timing record storage with dedupe and bounded memory."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from irswitch.race.timing.crossing import CrossingEvent

DEFAULT_MAX_RECORDS = 5000


@dataclass(frozen=True)
class TimingRecord:
    car_id: str
    lap_number: int
    timing_point_id: str
    crossing_timestamp: float
    segment_time: float | None = None
    cumulative_lap_time: float | None = None
    valid_at_crossing: bool = True
    data_quality: str = "ok"

    @property
    def dedupe_key(self) -> str:
        return f"{self.car_id}:{self.lap_number}:{self.timing_point_id}"


@dataclass
class TimingStore:
    """Append-only timing records with dedupe and hard cap."""

    max_records: int = DEFAULT_MAX_RECORDS
    _records: deque[TimingRecord] = field(default_factory=deque, repr=False)
    _seen_keys: set[str] = field(default_factory=set, repr=False)
    _last_crossing: dict[str, TimingRecord] = field(default_factory=dict, repr=False)

    def reset(self) -> None:
        self._records.clear()
        self._seen_keys.clear()
        self._last_crossing.clear()

    def __len__(self) -> int:
        return len(self._records)

    def ingest_crossing(
        self,
        event: CrossingEvent,
        *,
        cumulative_lap_time: float | None = None,
        valid_at_crossing: bool = True,
        data_quality: str = "ok",
        segment_eligible: bool = True,
    ) -> TimingRecord | None:
        """Store a crossing if dedupe key is new. Returns None on duplicate."""
        segment_time: float | None = None
        last = self._last_crossing.get(event.car_id)
        if last is not None and segment_eligible:
            segment_time = event.crossing_timestamp - last.crossing_timestamp
            if segment_time < 0:
                segment_time = None

        record = TimingRecord(
            car_id=event.car_id,
            lap_number=event.lap_number,
            timing_point_id=event.timing_point_id,
            crossing_timestamp=event.crossing_timestamp,
            segment_time=segment_time,
            cumulative_lap_time=cumulative_lap_time,
            valid_at_crossing=valid_at_crossing,
            data_quality=data_quality,
        )
        if record.dedupe_key in self._seen_keys:
            return None
        self._append(record)
        self._last_crossing[event.car_id] = record
        return record

    def records_for_car(self, car_id: str) -> list[TimingRecord]:
        return [r for r in self._records if r.car_id == car_id]

    def latest_for_car(self, car_id: str) -> TimingRecord | None:
        for record in reversed(self._records):
            if record.car_id == car_id:
                return record
        return None

    def _append(self, record: TimingRecord) -> None:
        self._seen_keys.add(record.dedupe_key)
        self._records.append(record)
        while len(self._records) > self.max_records:
            evicted = self._records.popleft()
            self._seen_keys.discard(evicted.dedupe_key)
