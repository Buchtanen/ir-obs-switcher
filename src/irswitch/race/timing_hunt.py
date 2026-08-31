"""P/Q hunt-by-time: hero pace vs CarIdxBestLapTime of class P{n}.

Uses telemetry lap-time arrays only. Never the driver roster for names or times.
Silence when the array is missing or all unset.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from irswitch.events.envelope import EventEnvelope, make_envelope
from irswitch.overlay.models import RaceState, TelemetrySnapshot

PACE_HUNT = "PACE_HUNT"
_PACE_HUNT_PRIORITY = 32
_MATCH_WINDOW_S = 0.05
_COOLDOWN_S = 20.0
_MIN_DIST_PCT = 0.15
_PQ_MODES = frozenset({"PRACTICE", "QUALIFYING"})


def hero_pace_s(snap: TelemetrySnapshot, state: RaceState) -> float | None:
    """Projected lap from current lap time / dist, else hero best. None if unknown."""
    dist = state.player_lap_dist_pct
    if dist is None:
        dist = snap.player_lap_dist_pct
    lap_time = state.current_lap_time
    if lap_time is None:
        lap_time = snap.current_lap_time
    if dist is not None and lap_time is not None and dist >= _MIN_DIST_PCT:
        projected = lap_time / dist
        if projected > 0:
            return projected
    best = state.best_lap_time
    if best is None:
        best = snap.best_lap_time
    return best


def rival_best_for_class_position(snap: TelemetrySnapshot, class_position: int) -> float | None:
    """Best lap of the other car holding class P{n}. None if missing."""
    positions = snap.car_idx_class_position
    times = snap.car_idx_best_lap_time
    if not times or all(item is None for item in times):
        return None
    classes = snap.car_idx_class
    player_class = snap.player_car_class
    player_idx = snap.player_car_idx
    n = min(len(positions), len(times))
    for idx in range(n):
        if player_idx is not None and idx == player_idx:
            continue
        if positions[idx] != class_position:
            continue
        if (
            player_class is not None
            and idx < len(classes)
            and classes[idx] is not None
            and classes[idx] != player_class
        ):
            continue
        return times[idx]
    return None


@dataclass
class TimingHuntFsm:
    """Emit at most one PACE_HUNT while hero pace matches the P{n} time."""

    _until: float = 0.0
    _pending: list[EventEnvelope] = field(default_factory=list)

    def reset(self) -> None:
        self._until = 0.0
        self._pending.clear()

    def take_pending(self) -> list[EventEnvelope]:
        out = list(self._pending)
        self._pending.clear()
        return out

    def tick(self, snap: TelemetrySnapshot, state: RaceState, now: float) -> list[EventEnvelope]:
        produced: list[EventEnvelope] = []
        if not state.connected or state.overlay_mode not in _PQ_MODES:
            return produced
        times = snap.car_idx_best_lap_time
        if not times or all(item is None for item in times):
            return produced
        hero_class = state.class_position or snap.class_position
        if hero_class is None or hero_class <= 1:
            return produced
        target_pos = hero_class - 1
        rival = rival_best_for_class_position(snap, target_pos)
        if rival is None:
            return produced
        hero = hero_pace_s(snap, state)
        if hero is None:
            return produced
        if abs(hero - rival) > _MATCH_WINDOW_S:
            return produced
        if now < self._until:
            return produced
        env = make_envelope(
            event_type=PACE_HUNT,
            phase="RESULT",
            mode=state.overlay_mode,
            priority=_PACE_HUNT_PRIORITY,
            monotonic_ms=int(now * 1000),
            metrics={
                "kind": "pace_hunt",
                "position": target_pos,
                "heroTime": round(hero, 3),
                "rivalTime": round(rival, 3),
            },
            correlation_id=f"pace_hunt:{target_pos}",
            dedupe_key=f"{state.overlay_mode}:PACE_HUNT:{target_pos}",
        )
        self._until = now + _COOLDOWN_S
        produced.append(env)
        self._pending.extend(produced)
        return produced
