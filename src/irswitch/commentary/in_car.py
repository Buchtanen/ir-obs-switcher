"""Once-per-stint in-car line. Not pit entry."""

from __future__ import annotations

from irswitch.events.envelope import make_envelope
from irswitch.overlay.models import RaceState


class InCarDetector:
    """Rising seated session → ENTER_CAR. Reset on disconnect / session change."""

    def __init__(self) -> None:
        self._announced = False

    def reset(self) -> None:
        self._announced = False

    def tick(self, state: RaceState, now: float):
        if not state.connected:
            self._announced = False
            return None
        if self._announced or state.player_car_idx is None:
            return None
        self._announced = True
        return make_envelope(
            event_type="ENTER_CAR",
            phase="RESULT",
            mode=state.overlay_mode,
            priority=38,
            monotonic_ms=int(now * 1000),
            dedupe_key=f"{state.overlay_mode}:ENTER_CAR",
            correlation_id="in_car",
            metrics={
                "position": state.class_position or state.position,
                "sessionType": state.session_type,
            },
        )
