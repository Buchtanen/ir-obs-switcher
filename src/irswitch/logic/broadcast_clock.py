"""Pure broadcast clock shared by metrics and chapter tracking.

OBS output counters describe one output connection, not necessarily one VOD.
Keep a segment offset through output restarts and use monotonic time only when
OBS has no usable counter. No getter mutates lifecycle state.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

STREAM_FLICKER_DEBOUNCE_S = 2.0


@dataclass(frozen=True)
class BroadcastClockSnapshot:
    epoch: int
    active: bool
    offset_seconds: float
    total_seconds: float


class BroadcastClock:
    def __init__(self) -> None:
        self._epoch = 0
        self._broadcast_id: str | None = None
        self._output_active = False
        self._stop_mono: float | None = None
        self._sample_mono: float | None = None
        self._offset = 0.0
        self._completed_total = 0.0
        self._segment_base = 0.0
        self._last_output_duration: float | None = None
        self._resume_offset: float | None = None
        self._resume_counter_limit: float | None = None
        self._using_monotonic = True

    def snapshot(self, now: float) -> BroadcastClockSnapshot:
        offset = self._offset
        if self._output_active and self._using_monotonic and self._sample_mono is not None:
            offset += max(0.0, now - self._sample_mono)
        active = self._output_active or (
            self._stop_mono is not None and now - self._stop_mono < STREAM_FLICKER_DEBOUNCE_S
        )
        return BroadcastClockSnapshot(self._epoch, active, offset, self._completed_total + offset)

    def update(
        self,
        *,
        now: float,
        streaming: bool | None,
        output_duration_seconds: float | None = None,
        broadcast_id: str | None = None,
    ) -> BroadcastClockSnapshot:
        # Missing transport status is not proof that OBS stopped the output.
        if streaming is None:
            return self.snapshot(now)
        duration = _valid_duration(output_duration_seconds)
        known_id = broadcast_id.strip() if isinstance(broadcast_id, str) else None
        known_id = known_id or None
        previous = self.snapshot(now)
        if streaming:
            same_id = known_id is not None and known_id == self._broadcast_id
            changed_id = known_id is not None and self._broadcast_id is not None and not same_id
            confirmed_stop = (
                self._stop_mono is not None and now - self._stop_mono >= STREAM_FLICKER_DEBOUNCE_S
            )
            new_broadcast = self._epoch == 0 or changed_id or (confirmed_stop and not same_id)
            if new_broadcast:
                self._completed_total += previous.offset_seconds
                self._epoch += 1
                self._offset = 0.0
                self._segment_base = 0.0
                self._last_output_duration = None
                self._resume_offset = None
                self._resume_counter_limit = None
                self._broadcast_id = known_id
            else:
                self._offset = previous.offset_seconds
                if duration is None and self._output_active and not self._using_monotonic:
                    if self._sample_mono is not None:
                        self._offset += max(0.0, now - self._sample_mono)
                if not self._output_active:
                    self._resume_offset = self._offset
                    stopped_at = self._stop_mono if self._stop_mono is not None else now
                    self._resume_counter_limit = now - stopped_at + STREAM_FLICKER_DEBOUNCE_S
                if known_id is not None:
                    self._broadcast_id = known_id
            if duration is not None:
                if self._resume_offset is not None:
                    if self._last_output_duration is None or (
                        duration < self._last_output_duration
                        and duration <= (self._resume_counter_limit or 0.0)
                    ):
                        self._segment_base = self._resume_offset
                    self._resume_offset = None
                    self._resume_counter_limit = None
                self._offset = max(self._offset, self._segment_base + duration)
                self._last_output_duration = duration
            self._using_monotonic = duration is None
            self._output_active = True
            self._stop_mono = None
            self._sample_mono = now
        elif self._output_active:
            self._offset = previous.offset_seconds
            self._output_active = False
            self._stop_mono = now
            self._sample_mono = now
        return self.snapshot(now)


def _valid_duration(value: float | None) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        duration = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return duration if math.isfinite(duration) and duration >= 0 else None
