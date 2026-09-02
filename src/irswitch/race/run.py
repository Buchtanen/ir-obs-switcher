"""Producer-owned racing-run clock, independent of the OBS broadcast clock."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Literal

from irswitch.iracing.sdk_units import as_elapsed_seconds
from irswitch.overlay.models import RaceState

RunObservation = Literal["accepted", "pending", "restarted"]


@dataclass
class RunClock:
    """Confirm a material rewind for 100 ms before resetting run-scoped truth.

    One stale sample cannot reset a run. While a rewind is pending the producer
    must not feed that sample to stateful observers. Small SDK jitter is ignored.
    """

    run_epoch: int = 0
    _key: str | None = None
    _last_time: float | None = None
    _rewind_since: float | None = None
    _rewind_time: float | None = None
    _green_time: float | None = None
    _green_lap: int | None = None
    _saw_pre_green: bool = False

    def observe(
        self, key: str | None, session_time: float | None, *, now: float, connected: bool
    ) -> RunObservation:
        if not connected or key is None:
            self._rewind_since = None
            return "accepted"
        if key != self._key:
            self._key = key
            self.run_epoch = 0
            self._last_time = None
            self._rewind_since = None
            self._green_time = None
            self._green_lap = None
            self._saw_pre_green = False
        current = as_elapsed_seconds(session_time)
        if current is None:
            self._rewind_since = None
            return "accepted"
        if self._last_time is not None and self._last_time - current > 5.0:
            if (
                self._rewind_since is None
                or self._rewind_time is None
                or current < self._rewind_time - 0.25
            ):
                self._rewind_since = now
                self._rewind_time = current
                return "pending"
            if now - self._rewind_since < 0.1:
                return "pending"
            self.run_epoch += 1
            self._last_time = current
            self._rewind_since = None
            self._green_time = None
            self._green_lap = None
            self._saw_pre_green = False
            return "restarted"
        self._rewind_since = None
        self._last_time = max(self._last_time or 0.0, current)
        return "accepted"

    def apply(self, state: RaceState) -> RaceState:
        """Annotate a witnessed green transition, never invent an origin on late join."""
        current = as_elapsed_seconds(state.session_time)
        racing = state.session_state == 4 or state.flag_green
        if (
            state.connected
            and state.overlay_mode == "RACE"
            and state.session_state in {1, 2, 3}
            and self._green_time is None
        ):
            self._saw_pre_green = True
        if state.connected and state.overlay_mode == "RACE" and racing:
            if self._saw_pre_green and self._green_time is None and current is not None:
                self._green_time = current
            if self._green_lap is None and state.lap_completed is not None:
                self._green_lap = max(0, state.lap_completed) if self._saw_pre_green else 0
        return replace(
            state,
            run_epoch=self.run_epoch,
            green_session_time=self._green_time,
            green_lap_completed=self._green_lap,
        )
