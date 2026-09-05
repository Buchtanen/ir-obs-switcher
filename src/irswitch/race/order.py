"""Live race order from lap progress. Official CarIdxPosition is S/F timing."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from irswitch.iracing.trk_loc import NOT_IN_WORLD
from irswitch.overlay.models import RaceState, TelemetrySnapshot

IRSDK_STATE_RACING = 4
IRSDK_STATE_CHECKERED = 5
PositionSource = Literal["live", "official", "grid"]


@dataclass(frozen=True)
class RaceOrder:
    """Canonical 1..N ranks keyed by car index. Missing cars stay None."""

    overall: tuple[int | None, ...]
    class_pos: tuple[int | None, ...]
    scores: tuple[float | None, ...]
    source: PositionSource


def is_race_green(snap: TelemetrySnapshot) -> bool:
    return snap.session_type == "Race" and (snap.session_state or 0) >= IRSDK_STATE_RACING


def _get(seq: tuple[object, ...], idx: int) -> object:
    if idx < 0 or idx >= len(seq):
        return None
    return seq[idx]


def _as_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _as_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    return None


def field_length(snap: TelemetrySnapshot) -> int:
    return max(
        len(snap.car_idx_lap_dist_pct),
        len(snap.car_idx_lap_completed),
        len(snap.car_idx_lap),
        len(snap.car_idx_class_position),
        len(snap.car_idx_position),
        len(snap.car_idx_class),
        len(snap.car_idx_driver_name),
        0,
    )


def race_progress(
    snap: TelemetrySnapshot,
    car_idx: int,
    *,
    racing: bool | None = None,
    frozen: dict[int, float] | None = None,
) -> float | None:
    """Fractional race distance for live ranking.

    Official ``CarIdxLapCompleted`` stays ``-1`` (extracted as None) until the
    first S/F. After green, missing completed laps still rank via ``CarIdxLap``
    or lap-0 + ``LapDistPct``. Parade / non-race does not invent a score from
    geometry alone (double-file swaps grid pairs).
    """
    if racing is None:
        racing = is_race_green(snap)
    live = _live_progress(snap, car_idx, racing=racing)
    if live is not None:
        return live
    if frozen is not None:
        return frozen.get(car_idx)
    return None


def _live_progress(snap: TelemetrySnapshot, car_idx: int, *, racing: bool) -> float | None:
    surface = _as_int(_get(snap.car_idx_track_surface, car_idx))
    if surface == NOT_IN_WORLD:
        return None
    pct = _as_float(_get(snap.car_idx_lap_dist_pct, car_idx))
    if pct is None:
        return None
    completed = _as_int(_get(snap.car_idx_lap_completed, car_idx))
    if completed is not None and completed >= 0:
        return float(completed) + pct
    if not racing:
        return None
    started = _as_int(_get(snap.car_idx_lap, car_idx))
    if started is not None and started >= 1:
        return float(started - 1) + pct
    return pct


def calculate_race_order(
    snap: TelemetrySnapshot,
    *,
    frozen_progress: dict[int, float] | None = None,
) -> RaceOrder:
    n = field_length(snap)
    if n <= 0:
        return RaceOrder((), (), (), "official")
    if snap.session_type == "Race" and (snap.session_state or 0) < IRSDK_STATE_RACING:
        return _from_official(snap, n, "grid")
    if not is_race_green(snap):
        return _from_official(snap, n, "official")

    scores: list[float | None] = [
        race_progress(snap, idx, racing=True, frozen=frozen_progress) for idx in range(n)
    ]
    ranked = [(idx, score) for idx, score in enumerate(scores) if score is not None]
    if not ranked:
        return _from_official(snap, n, "grid")

    ranked.sort(key=lambda item: (-item[1], item[0]))
    overall: list[int | None] = [None] * n
    for position, (idx, _) in enumerate(ranked, start=1):
        overall[idx] = position

    by_class: dict[int, list[int]] = {}
    for idx, _score in ranked:
        class_id = _as_int(_get(snap.car_idx_class, idx))
        by_class.setdefault(class_id if class_id is not None else 0, []).append(idx)

    class_pos: list[int | None] = [None] * n
    for idxs in by_class.values():
        idxs.sort(key=lambda idx: (-(scores[idx] or 0.0), idx))
        for position, idx in enumerate(idxs, start=1):
            class_pos[idx] = position

    return RaceOrder(tuple(overall), tuple(class_pos), tuple(scores), "live")


def player_place(order: RaceOrder, player_idx: int | None) -> tuple[int | None, int | None]:
    if player_idx is None:
        return None, None
    overall = _as_int(_get(order.overall, player_idx))
    class_pos = _as_int(_get(order.class_pos, player_idx))
    return overall, class_pos


def order_from_state(state: RaceState) -> RaceOrder | None:
    if not state.car_idx_live_position and not state.car_idx_live_class_position:
        return None
    source: PositionSource
    if state.position_source == "live":
        source = "live"
    elif state.position_source == "grid":
        source = "grid"
    else:
        source = "official"
    return RaceOrder(
        state.car_idx_live_position,
        state.car_idx_live_class_position,
        (),
        source,
    )


def _from_official(snap: TelemetrySnapshot, n: int, source: PositionSource) -> RaceOrder:
    overall = _pad(snap.car_idx_position, n)
    class_pos = _pad(snap.car_idx_class_position, n)
    return RaceOrder(tuple(overall), tuple(class_pos), tuple([None] * n), source)


def _pad(seq: tuple[int | None, ...], n: int) -> list[int | None]:
    items = list(seq)
    if len(items) < n:
        items.extend([None] * (n - len(items)))
    return items[:n]


def _car_has_data(snap: TelemetrySnapshot, idx: int) -> bool:
    name = _get(snap.car_idx_driver_name, idx)
    if isinstance(name, str) and name.strip():
        return True
    if _get(snap.car_idx_lap_dist_pct, idx) is not None:
        return True
    if _get(snap.car_idx_lap_completed, idx) is not None:
        return True
    if _get(snap.car_idx_lap, idx) is not None:
        return True
    if _get(snap.car_idx_position, idx) is not None:
        return True
    if _get(snap.car_idx_class_position, idx) is not None:
        return True
    surface = _as_int(_get(snap.car_idx_track_surface, idx))
    return surface is not None and surface != NOT_IN_WORLD


def _round_pct(value: object) -> float | None:
    number = _as_float(value)
    if number is None:
        return None
    return round(number, 6)


def _round_time(value: object) -> float | None:
    number = _as_float(value)
    if number is None:
        return None
    return round(number, 3)


def field_tape_payload(snap: TelemetrySnapshot, state: RaceState) -> dict[str, Any]:
    """Compact per-tick field dump for overlay tape (official vs live)."""
    n = field_length(snap)
    player_idx = snap.player_car_idx
    cars: list[dict[str, Any]] = []
    for idx in range(n):
        if not _car_has_data(snap, idx):
            continue
        name = _get(snap.car_idx_driver_name, idx)
        cars.append(
            {
                "idx": idx,
                "name": name if isinstance(name, str) and name else None,
                "lap": _as_int(_get(snap.car_idx_lap, idx)),
                "lapDone": _as_int(_get(snap.car_idx_lap_completed, idx)),
                "pct": _round_pct(_get(snap.car_idx_lap_dist_pct, idx)),
                "offP": _as_int(_get(snap.car_idx_position, idx)),
                "offCP": _as_int(_get(snap.car_idx_class_position, idx)),
                "liveP": _as_int(_get(state.car_idx_live_position, idx)),
                "liveCP": _as_int(_get(state.car_idx_live_class_position, idx)),
                "cls": _as_int(_get(snap.car_idx_class, idx)),
                "pit": _get(snap.car_idx_on_pit_road, idx),
                "surf": _as_int(_get(snap.car_idx_track_surface, idx)),
                "est": _round_time(_get(snap.car_idx_est_time, idx)),
                "f2": _round_time(_get(snap.car_idx_f2_time, idx)),
                "paceLine": _as_int(_get(snap.car_idx_pace_line, idx)),
                "paceRow": _as_int(_get(snap.car_idx_pace_row, idx)),
            }
        )
    live_p, live_cp = player_place(
        RaceOrder(
            state.car_idx_live_position,
            state.car_idx_live_class_position,
            (),
            "live" if state.position_source == "live" else "official",
        ),
        player_idx,
    )
    if state.position_source == "live":
        live_p = state.position
        live_cp = state.class_position
    return {
        "type": "field",
        "playerCarIdx": player_idx,
        "sessionState": snap.session_state,
        "sessionType": snap.session_type,
        "positionSource": state.position_source,
        "position": state.position,
        "classPosition": state.class_position,
        "officialPosition": state.official_position,
        "officialClassPosition": state.official_class_position,
        "livePosition": live_p,
        "liveClassPosition": live_cp,
        "cars": cars,
    }
