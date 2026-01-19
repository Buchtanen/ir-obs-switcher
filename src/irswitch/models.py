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
    QUIT = "QUIT"
    RESTART = "RESTART"  # QUIT + hotkey held


@dataclass(frozen=True)
class SwitchState:
    """Immutable state of the scene switcher."""

    connected_iracing: bool
    connected_obs: bool
    autoswitch: bool
    override_scene: Optional[str]
    override_until: Optional[float]  # Monotonic time in milliseconds
    mode: DrivingMode
    target_scene: str
    current_scene: str
    last_switch_ts: Optional[float]  # Monotonic time in milliseconds
    reason: str = ""  # Default empty string to allow optional fields after
    session_type: Optional[str] = None  # Session type: "Practice", "Qualify", "Race", etc.
    session_name: Optional[str] = None  # Session name from iRacing
    session_num: Optional[int] = None  # Session number (0-based)
