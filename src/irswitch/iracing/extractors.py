"""Extraction helpers for iRacing telemetry data."""
from __future__ import annotations

import logging
from typing import Mapping

from irswitch.models import DrivingMode

logger = logging.getLogger(__name__)


def _as_bool(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).lower() in {"1", "true", "yes", "on"}


def extract_mode(data: Mapping[str, object]) -> DrivingMode:
    """
    Extract driving mode from iRacing SDK data.
    
    Priority order: GARAGE > REPLAY > RACE > IDLE
    Note: SETTINGS detection was removed - iRacing SDK doesn't report it reliably.
    """
    # Get all relevant variables
    is_replay = _as_bool(data.get("IsReplay"))
    player_car_idx = data.get("PlayerCarIdx")
    cam_car_idx = data.get("CamCarIdx")
    cam_camera_state = data.get("CamCameraState")
    is_on_track = _as_bool(data.get("IsOnTrack")) or _as_bool(data.get("IsOnTrackCar"))
    is_in_garage = _as_bool(data.get("PlayerCarInGarage")) or _as_bool(data.get("IsInGarage"))
    
    # Determine if player is in car based on CamCameraState
    is_in_car = False
    if cam_camera_state is not None:
        try:
            cam_state = int(cam_camera_state)
            # Bit 0: session screen (menu/UI) - if set, not in car
            is_session_screen = (cam_state & 0x01) != 0
            is_in_car = not is_session_screen
        except (ValueError, TypeError):
            pass
    elif player_car_idx is not None:
        try:
            car_idx = int(player_car_idx)
            is_in_car = car_idx >= 0
        except (ValueError, TypeError):
            pass
    
    # Check camera mismatch (watching replay of other car)
    cam_mismatch = False
    if cam_car_idx is not None and player_car_idx is not None:
        try:
            cam_idx = int(cam_car_idx)
            player_idx = int(player_car_idx)
            cam_mismatch = cam_idx != player_idx
        except (ValueError, TypeError):
            pass

    # Decide mode - Priority order: GARAGE > REPLAY > RACE > IDLE
    mode = DrivingMode.IDLE
    if is_in_garage:
        mode = DrivingMode.GARAGE
    elif is_replay:
        mode = DrivingMode.REPLAY
    elif cam_mismatch:
        mode = DrivingMode.REPLAY
    elif is_on_track and not is_in_car:
        mode = DrivingMode.REPLAY
    elif is_on_track and is_in_car:
        mode = DrivingMode.RACE
    
    return mode
