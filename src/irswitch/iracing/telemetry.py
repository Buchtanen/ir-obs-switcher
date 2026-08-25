"""iRacing telemetry extraction. No race interpretation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from irswitch.iracing.extractors import as_bool, as_int
from irswitch.overlay.models import TelemetrySnapshot

TELEMETRY_VARS: tuple[str, ...] = (
    "PlayerCarIdx",
    "PlayerCarPosition",
    "PlayerCarClassPosition",
    "PlayerCarClass",
    "Lap",
    "LapCompleted",
    "LapCurrentLapTime",
    "LapLastLapTime",
    "LapBestLapTime",
    "PlayerCarMyIncidentCount",
    "OnPitRoad",
    "SessionLapsRemain",
    "SessionState",
    "FrameRate",
    "CarDistAhead",
    "CarDistBehind",
    "CarIdxLapDistPct",
    "CarIdxLapCompleted",
    "CarIdxClass",
    "CarIdxClassPosition",
    "CarIdxPosition",
    "CarIdxOnPitRoad",
    "CarIdxEstTime",
    "CarIdxTrackSurface",
)


def as_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return float(int(value))
    if isinstance(value, (int, float)):
        number = float(value)
        # iRacing uses large sentinels for "not available"
        if number <= -10000 or number >= 1e10:
            return None
        return number
    try:
        return float(str(value))
    except ValueError:
        return None


def _as_sequence(value: object) -> Sequence[object]:
    if value is None:
        return ()
    if isinstance(value, (str, bytes)):
        return ()
    if isinstance(value, Sequence):
        return value
    return ()


def _float_tuple(value: object) -> tuple[float | None, ...]:
    return tuple(as_float(item) for item in _as_sequence(value))


def _int_tuple(value: object) -> tuple[int | None, ...]:
    return tuple(as_int(item) for item in _as_sequence(value))


def _bool_tuple(value: object) -> tuple[bool | None, ...]:
    items: list[bool | None] = []
    for item in _as_sequence(value):
        if item is None:
            items.append(None)
        else:
            items.append(as_bool(item))
    return tuple(items)


def extract_telemetry(data: Mapping[str, object], timestamp: float) -> TelemetrySnapshot:
    """Build a TelemetrySnapshot from SDK var dict. Missing keys stay None."""
    fps = as_float(data.get("FrameRate"))
    frametime = (1000.0 / fps) if fps and fps > 0 else None
    return TelemetrySnapshot(
        connected=True,
        timestamp=timestamp,
        player_car_idx=as_int(data.get("PlayerCarIdx")),
        position=as_int(data.get("PlayerCarPosition")),
        class_position=as_int(data.get("PlayerCarClassPosition")),
        lap=as_int(data.get("Lap")),
        lap_completed=as_int(data.get("LapCompleted")),
        current_lap_time=as_float(data.get("LapCurrentLapTime")),
        last_lap_time=as_float(data.get("LapLastLapTime")),
        best_lap_time=as_float(data.get("LapBestLapTime")),
        incidents=as_int(data.get("PlayerCarMyIncidentCount")),
        on_pit_road=as_bool(data.get("OnPitRoad")) if "OnPitRoad" in data else None,
        session_laps_remain=as_float(data.get("SessionLapsRemain")),
        session_state=as_int(data.get("SessionState")),
        fps=fps,
        frametime_ms=frametime,
        car_dist_ahead=as_float(data.get("CarDistAhead")),
        car_dist_behind=as_float(data.get("CarDistBehind")),
        player_car_class=as_int(data.get("PlayerCarClass")),
        car_idx_lap_dist_pct=_float_tuple(data.get("CarIdxLapDistPct")),
        car_idx_lap_completed=_int_tuple(data.get("CarIdxLapCompleted")),
        car_idx_class=_int_tuple(data.get("CarIdxClass")),
        car_idx_class_position=_int_tuple(data.get("CarIdxClassPosition")),
        car_idx_position=_int_tuple(data.get("CarIdxPosition")),
        car_idx_on_pit_road=_bool_tuple(data.get("CarIdxOnPitRoad")),
        car_idx_est_time=_float_tuple(data.get("CarIdxEstTime")),
        car_idx_track_surface=_int_tuple(data.get("CarIdxTrackSurface")),
    )
