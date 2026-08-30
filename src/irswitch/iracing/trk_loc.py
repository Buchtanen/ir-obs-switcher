"""iRSDK irsdk_TrkLoc values (PlayerTrackSurface / CarIdxTrackSurface)."""

from __future__ import annotations

# Official: NotInWorld=-1, OffTrack=0, InPitStall=1, AproachingPits=2, OnTrack=3
NOT_IN_WORLD = -1
OFF_TRACK = 0
IN_PIT_STALL = 1
APPROACHING_PITS = 2
ON_TRACK = 3

# Bigger than a 5 Hz tick into the pits; ESC/tow teleports jump much more.
TELEPORT_DIST_PCT = 0.05


def is_on_track(surface: int | None) -> bool:
    return surface == ON_TRACK


def is_towing(tow_time: float | None) -> bool:
    return tow_time is not None and tow_time > 0.0


def is_esc_teleport(
    prev_surface: int | None,
    curr_surface: int | None,
    prev_dist: float | None = None,
    curr_dist: float | None = None,
) -> bool:
    """OnTrack → pit stall plus a LapDistPct jump is ESC/reset, not a drive-in.

    A missed ApproachingPits sample at 5 Hz still looks like OnTrack → InPitStall;
    only a large distance jump counts as teleport.
    """
    if prev_surface != ON_TRACK or curr_surface != IN_PIT_STALL:
        return False
    if prev_dist is None or curr_dist is None:
        return False
    return abs(curr_dist - prev_dist) >= TELEPORT_DIST_PCT
