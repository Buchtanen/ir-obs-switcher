"""Extraction helpers for iRacing telemetry data."""
from __future__ import annotations

from typing import Mapping

from irswitch.models import DrivingMode


def _as_bool(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).lower() in {"1", "true", "yes", "on"}


def extract_mode(data: Mapping[str, object]) -> DrivingMode:
    is_replay = _as_bool(data.get("IsReplay"))
    if is_replay:
        return DrivingMode.REPLAY

    is_on_track = _as_bool(data.get("IsOnTrack")) or _as_bool(data.get("IsOnTrackCar"))
    if is_on_track:
        return DrivingMode.RACE

    is_in_garage = _as_bool(data.get("PlayerCarInGarage")) or _as_bool(data.get("IsInGarage"))
    if is_in_garage:
        return DrivingMode.GARAGE

    return DrivingMode.IDLE
