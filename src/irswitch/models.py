"""Shared models for state and events."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class DrivingMode(str, Enum):
    IDLE = "IDLE"
    GARAGE = "GARAGE"
    RACE = "RACE"
    REPLAY = "REPLAY"


@dataclass(frozen=True)
class SwitchState:
    connected_iracing: bool
    connected_obs: bool
    autoswitch: bool
    override_scene: Optional[str]
    mode: DrivingMode
    target_scene: str
    current_scene: str
    reason: str
