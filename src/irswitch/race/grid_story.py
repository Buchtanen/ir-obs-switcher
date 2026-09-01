"""Race-start quali recap + ParadeLaps padding (N7).

Commentary-only. One recap from the stream quali bag; missing bag skips.
Parade padding stops on SessionState Racing or a green flag (N5 speaks green).
Not a rolling-start screenplay: at most two pad lines.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from irswitch.events.envelope import EventEnvelope, make_envelope
from irswitch.overlay.models import RaceState
from irswitch.race.story import QualiBag

QUALI_RECAP = "QUALI_RECAP"
PARADE_PAD = "PARADE_PAD"
_RECAP_PRIORITY = 66
_PAD_PRIORITY = 30
PARADE_COOLDOWN_S = 25.0
PARADE_MAX = 2
IRSDK_PARADE_LAPS = 3
IRSDK_RACING = 4


def green_or_racing(state: RaceState) -> bool:
    """True when the race is under green / Racing — padding must stop."""
    if state.session_state == IRSDK_RACING:
        return True
    if state.flag_green:
        return True
    names = state.session_flag_names or ()
    return "green" in names


@dataclass
class GridStoryFsm:
    """At most one QUALI_RECAP per race session, then bounded parade pads."""

    _session_key: str | None = None
    _recap_done: bool = False
    _parade_count: int = 0
    _parade_until: float = 0.0
    _pending: list[EventEnvelope] = field(default_factory=list)

    def reset(self) -> None:
        self._session_key = None
        self._recap_done = False
        self._parade_count = 0
        self._parade_until = 0.0
        self._pending.clear()

    def take_pending(self) -> list[EventEnvelope]:
        out = list(self._pending)
        self._pending.clear()
        return out

    def tick(
        self,
        state: RaceState,
        now: float,
        *,
        enabled: bool,
        bag: QualiBag | None,
        session_key: str | None,
    ) -> list[EventEnvelope]:
        produced: list[EventEnvelope] = []
        if session_key != self._session_key:
            self._session_key = session_key
            self._recap_done = False
            self._parade_count = 0
            self._parade_until = 0.0
            self._pending.clear()

        if not state.connected or not enabled:
            return produced
        if (state.overlay_mode or "") != "RACE":
            return produced
        if state.mute_field or state.player_finished or state.session_finished:
            return produced
        if green_or_racing(state):
            self._recap_done = True
            return produced

        mode = state.overlay_mode or "RACE"
        if not self._recap_done:
            self._recap_done = True
            if bag is None:
                return produced
            env = make_envelope(
                event_type=QUALI_RECAP,
                phase="RESULT",
                mode=mode,
                priority=_RECAP_PRIORITY,
                monotonic_ms=int(now * 1000),
                metrics={
                    "kind": "quali_recap",
                    "position": bag.class_position,
                    "lapTime": bag.best_lap_s,
                },
                correlation_id=f"quali_recap:{session_key or 'na'}",
                dedupe_key=f"{mode}:QUALI_RECAP",
            )
            produced.append(env)
            self._pending.extend(produced)
            return produced

        if state.session_state != IRSDK_PARADE_LAPS:
            return produced
        if self._parade_count >= PARADE_MAX:
            return produced
        if now < self._parade_until:
            return produced
        env = make_envelope(
            event_type=PARADE_PAD,
            phase="RESULT",
            mode=mode,
            priority=_PAD_PRIORITY,
            monotonic_ms=int(now * 1000),
            metrics={"kind": "parade_pad"},
            correlation_id=f"parade_pad:{session_key or 'na'}:{self._parade_count}",
            dedupe_key=f"{mode}:PARADE_PAD:{self._parade_count}",
        )
        self._parade_count += 1
        self._parade_until = now + PARADE_COOLDOWN_S
        produced.append(env)
        self._pending.extend(produced)
        return produced
