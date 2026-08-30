"""iRacing telemetry extraction. No race interpretation."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from irswitch.iracing.drivers import driver_names_by_car_idx
from irswitch.iracing.extractors import as_bool, as_int, extract_session_type
from irswitch.iracing.sdk_units import (
    as_completed_lap_time,
    as_current_lap_time,
    as_elapsed_seconds,
    as_est_time,
    as_grid_position,
    as_lap_dist_pct,
    as_non_negative_int,
    as_session_laps_remain,
)
from irswitch.iracing.sectors import sector_start_pcts
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
    "SessionTime",
    "SessionFlags",
    "SessionNum",
    "SessionType",
    "SessionName",
    "SubSessionID",
    "TrackID",
    "WeekendInfo",
    "FrameRate",
    "CarDistAhead",
    "CarDistBehind",
    "LapDistPct",
    "CarIdxLapDistPct",
    "CarIdxLapCompleted",
    "CarIdxClass",
    "CarIdxClassPosition",
    "CarIdxPosition",
    "CarIdxOnPitRoad",
    "CarIdxEstTime",
    "CarIdxTrackSurface",
    "DriverInfo",
    "SplitTimeInfo",
    "PlayerTrackSurface",
    "PlayerCarTowTime",
    # Live weather for commentary session briefs (H3/H4).
    "Skies",
    "AirTemp",
    "TrackTempCrew",
    "TrackTemp",
    "WindVel",
    "Precipitation",
    "TrackWetness",
    "WeatherDeclaredWet",
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


def _pct_tuple(value: object) -> tuple[float | None, ...]:
    return tuple(as_lap_dist_pct(item) for item in _as_sequence(value))


def _est_time_tuple(value: object) -> tuple[float | None, ...]:
    return tuple(as_est_time(item) for item in _as_sequence(value))


def _int_tuple(value: object) -> tuple[int | None, ...]:
    return tuple(as_int(item) for item in _as_sequence(value))


def _lap_count_tuple(value: object) -> tuple[int | None, ...]:
    return tuple(as_non_negative_int(item) for item in _as_sequence(value))


def _position_tuple(value: object) -> tuple[int | None, ...]:
    return tuple(as_grid_position(item) for item in _as_sequence(value))


def _bool_tuple(value: object) -> tuple[bool | None, ...]:
    items: list[bool | None] = []
    for item in _as_sequence(value):
        if item is None:
            items.append(None)
        else:
            items.append(as_bool(item))
    return tuple(items)


def _player_track_surface(data: Mapping[str, object], player_idx: int | None) -> int | None:
    direct = as_int(data.get("PlayerTrackSurface"))
    if direct is not None:
        return direct
    surfaces = _int_tuple(data.get("CarIdxTrackSurface"))
    if player_idx is None or player_idx < 0 or player_idx >= len(surfaces):
        return None
    return surfaces[player_idx]


def _weekend_value(data: Mapping[str, object], key: str) -> object:
    weekend = data.get("WeekendInfo")
    if isinstance(weekend, dict):
        return weekend.get(key)
    if weekend is None:
        return None
    if hasattr(weekend, "__dict__"):
        return weekend.__dict__.get(key)
    return getattr(weekend, key, None)


def extract_telemetry(data: Mapping[str, object], timestamp: float) -> TelemetrySnapshot:
    """Build a TelemetrySnapshot from SDK var dict. Missing keys stay None."""
    fps = as_float(data.get("FrameRate"))
    frametime = (1000.0 / fps) if fps and fps > 0 else None
    player_idx = as_int(data.get("PlayerCarIdx"))
    lap_dist_pcts = _pct_tuple(data.get("CarIdxLapDistPct"))
    player_lap_dist = as_lap_dist_pct(data.get("LapDistPct"))
    if player_lap_dist is None and player_idx is not None and 0 <= player_idx < len(lap_dist_pcts):
        player_lap_dist = lap_dist_pcts[player_idx]
    subsession = data.get("SubSessionID")
    if subsession is None:
        subsession = data.get("subsession_id")
    if subsession is None:
        subsession = _weekend_value(data, "SubSessionID")
    track = data.get("TrackID")
    if track is None:
        track = data.get("track_id")
    if track is None:
        track = _weekend_value(data, "TrackID")
    session_type_str = extract_session_type(data)
    return TelemetrySnapshot(
        connected=True,
        timestamp=timestamp,
        player_car_idx=player_idx,
        position=as_grid_position(data.get("PlayerCarPosition")),
        class_position=as_grid_position(data.get("PlayerCarClassPosition")),
        lap=as_non_negative_int(data.get("Lap")),
        lap_completed=as_non_negative_int(data.get("LapCompleted")),
        current_lap_time=as_current_lap_time(data.get("LapCurrentLapTime")),
        last_lap_time=as_completed_lap_time(data.get("LapLastLapTime")),
        best_lap_time=as_completed_lap_time(data.get("LapBestLapTime")),
        incidents=as_int(data.get("PlayerCarMyIncidentCount")),
        on_pit_road=as_bool(data.get("OnPitRoad")) if "OnPitRoad" in data else None,
        session_laps_remain=as_session_laps_remain(data.get("SessionLapsRemain")),
        session_state=as_int(data.get("SessionState")),
        fps=fps,
        frametime_ms=frametime,
        car_dist_ahead=as_float(data.get("CarDistAhead")),
        car_dist_behind=as_float(data.get("CarDistBehind")),
        player_car_class=as_int(data.get("PlayerCarClass")),
        car_idx_lap_dist_pct=lap_dist_pcts,
        car_idx_lap_completed=_lap_count_tuple(data.get("CarIdxLapCompleted")),
        car_idx_class=_int_tuple(data.get("CarIdxClass")),
        car_idx_class_position=_position_tuple(data.get("CarIdxClassPosition")),
        car_idx_position=_position_tuple(data.get("CarIdxPosition")),
        car_idx_on_pit_road=_bool_tuple(data.get("CarIdxOnPitRoad")),
        car_idx_est_time=_est_time_tuple(data.get("CarIdxEstTime")),
        car_idx_track_surface=_int_tuple(data.get("CarIdxTrackSurface")),
        car_idx_driver_name=driver_names_by_car_idx(data.get("DriverInfo")),
        session_num=as_int(data.get("SessionNum")),
        subsession_id=str(subsession) if subsession is not None else None,
        session_type=session_type_str,
        track_id=str(track) if track is not None else None,
        session_time=as_elapsed_seconds(data.get("SessionTime")),
        session_flags=as_int(data.get("SessionFlags")),
        player_lap_dist_pct=player_lap_dist,
        stale_for_ms=as_float(data.get("stale_for_ms")),
        data_quality=str(data.get("data_quality") or "ok"),
        player_track_surface=_player_track_surface(data, player_idx),
        player_tow_time=as_float(data.get("PlayerCarTowTime")),
        sector_start_pcts=sector_start_pcts(data.get("SplitTimeInfo")),
    )
