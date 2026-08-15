"""Shared models for state and events."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class DrivingMode(StrEnum):
    CONNECTING = "CONNECTING"  # Waiting for OBS and iRacing connection
    LOADING = "LOADING"  # After connecting, waiting for iRacing lobby
    LOBBY = "LOBBY"  # iRacing lobby (replaces IDLE for active game)
    IDLE = "IDLE"  # Deprecated, use LOBBY instead (kept for compatibility)
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
    override_scene: str | None
    override_until: float | None  # Monotonic time in milliseconds
    mode: DrivingMode
    target_scene: str
    current_scene: str
    last_switch_ts: float | None  # Monotonic time in milliseconds
    reason: str
    session_type: str | None = None  # Session type: "Practice", "Qualify", "Race", etc.
    session_name: str | None = None  # Session name from iRacing
    session_num: int | None = None  # Session number (0-based)
    total_sessions: int | None = None  # Total number of sessions (for "x of y" display)
    stream_extended_info: dict | None = (
        None  # Extended stream info from YouTube API (viewers, status, etc.)
    )
