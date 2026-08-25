"""Pick relevant race opponents (not merely the nearest physical car)."""

from __future__ import annotations

from irswitch.overlay.models import TelemetrySnapshot

# irsdk_TrkLoc: 0 NotInWorld, 1 OffTrack, 2 InPitStall, 3 AproachingPits, 4 OnTrack
ON_TRACK = 4


def _get(seq: tuple[object, ...], idx: int) -> object:
    if idx < 0 or idx >= len(seq):
        return None
    return seq[idx]


def _as_float(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def race_distance(snap: TelemetrySnapshot, car_idx: int) -> float | None:
    """Fractional laps completed (lap + dist pct)."""
    lap = _as_float(_get(snap.car_idx_lap_completed, car_idx))
    pct = _as_float(_get(snap.car_idx_lap_dist_pct, car_idx))
    if lap is None or pct is None:
        return None
    return lap + pct


def is_active_racer(snap: TelemetrySnapshot, car_idx: int, player_idx: int) -> bool:
    if car_idx == player_idx:
        return False
    surface = _get(snap.car_idx_track_surface, car_idx)
    if isinstance(surface, (int, float)) and int(surface) == 0:
        return False
    on_pit = _get(snap.car_idx_on_pit_road, car_idx)
    if on_pit is True:
        return False
    dist = race_distance(snap, car_idx)
    return dist is not None


def same_class(snap: TelemetrySnapshot, car_idx: int, player_idx: int) -> bool:
    raw_class: object = snap.player_car_class
    if raw_class is None:
        raw_class = _get(snap.car_idx_class, player_idx)
    other = _get(snap.car_idx_class, car_idx)
    player_num = _as_float(raw_class)
    other_num = _as_float(other)
    if player_num is None or other_num is None:
        return True
    return int(player_num) == int(other_num)


def estimated_gap_seconds(snap: TelemetrySnapshot, player_idx: int, other_idx: int) -> float | None:
    """Positive gap means ``other`` is ahead of the player."""
    p_dist = race_distance(snap, player_idx)
    o_dist = race_distance(snap, other_idx)
    if p_dist is None or o_dist is None:
        return None
    delta_laps = o_dist - p_dist
    lap_time = snap.last_lap_time or snap.best_lap_time or 90.0
    if lap_time <= 0:
        lap_time = 90.0
    return delta_laps * lap_time


def class_position_of(snap: TelemetrySnapshot, car_idx: int) -> int | None:
    value = _get(snap.car_idx_class_position, car_idx)
    return int(value) if isinstance(value, (int, float)) else None


def overall_position_of(snap: TelemetrySnapshot, car_idx: int) -> int | None:
    value = _get(snap.car_idx_position, car_idx)
    return int(value) if isinstance(value, (int, float)) else None


def relevant_ahead_behind(
    snap: TelemetrySnapshot,
) -> tuple[int | None, int | None]:
    """
    Return (ahead_idx, behind_idx) for the relevant same-class race opponents.

    Ignores pit, not-in-world, and cars a lap down/up when a closer class
    neighbour exists.
    """
    player_idx = snap.player_car_idx
    if player_idx is None:
        return None, None
    player_dist = race_distance(snap, player_idx)
    if player_dist is None:
        return None, None

    n = max(
        len(snap.car_idx_lap_dist_pct),
        len(snap.car_idx_class_position),
        len(snap.car_idx_position),
        0,
    )
    ahead_idx: int | None = None
    ahead_gap = 1e9
    behind_idx: int | None = None
    behind_gap = 1e9

    player_cp = snap.class_position or class_position_of(snap, player_idx)

    for car_idx in range(n):
        if not is_active_racer(snap, car_idx, player_idx):
            continue
        if not same_class(snap, car_idx, player_idx):
            continue
        gap = estimated_gap_seconds(snap, player_idx, car_idx)
        if gap is None:
            continue
        # Skip cars more than ~0.7 laps away (lapped traffic) unless they
        # are the immediate class-position neighbour.
        other_cp = class_position_of(snap, car_idx)
        neighbour = (
            player_cp is not None and other_cp is not None and abs(other_cp - player_cp) == 1
        )
        if abs(gap) > 0.7 * (snap.last_lap_time or 90.0) and not neighbour:
            continue
        if gap > 0 and gap < ahead_gap:
            ahead_gap = gap
            ahead_idx = car_idx
        elif gap < 0 and -gap < behind_gap:
            behind_gap = -gap
            behind_idx = car_idx

    return ahead_idx, behind_idx
