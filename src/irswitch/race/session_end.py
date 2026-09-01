"""Checkered = session clock expired; after_session = this driver is done."""

from __future__ import annotations

from dataclasses import dataclass

from irswitch.iracing.trk_loc import APPROACHING_PITS, IN_PIT_STALL, NOT_IN_WORLD, is_towing

# iRacing SessionState: 4 Racing, 5 Checkered, 6 CoolDown
IRSDK_CHECKERED = 5
IRSDK_COOLDOWN = 6


def still_on_out_lap(
    *,
    on_pit_road: bool,
    surface: int | None,
    tow_time: float | None,
) -> bool:
    """True when the driver may still complete the lap after checkered.

    Pits / garage / tow / not-in-world: stay in. Off-track grass still counts
    as the flying lap until they box or take the line.
    """
    if is_towing(tow_time):
        return False
    if on_pit_road:
        return False
    if surface in (NOT_IN_WORLD, IN_PIT_STALL, APPROACHING_PITS):
        return False
    return True


@dataclass
class SessionEndTracker:
    """Maps iRacing checkered/cooldown onto overlay after_session.

    Checkered means the session clock ended. Quali and Race (and Practice)
    still allow finishing the lap already started. ``session_finished`` rises
    on S/F after checkered, or immediately when not on a flying lap.
    """

    _armed: bool = False
    _lap_at_checkered: int | None = None
    _after: bool = False

    def reset(self) -> None:
        self._armed = False
        self._lap_at_checkered = None
        self._after = False

    def update(
        self,
        *,
        session_state: int | None,
        lap_completed: int | None,
        on_pit_road: bool,
        player_track_surface: int | None,
        player_tow_time: float | None,
    ) -> tuple[bool, bool]:
        """Return ``(session_checkered, session_finished)``."""
        ss = session_state if session_state is not None else 0
        if ss not in (IRSDK_CHECKERED, IRSDK_COOLDOWN):
            self.reset()
            return False, False

        if ss == IRSDK_COOLDOWN:
            self._after = True
            return True, True

        flying = still_on_out_lap(
            on_pit_road=on_pit_road,
            surface=player_track_surface,
            tow_time=player_tow_time,
        )
        if not self._armed:
            self._armed = True
            self._lap_at_checkered = lap_completed
            if not flying:
                self._after = True
        elif not self._after:
            if (
                lap_completed is not None
                and self._lap_at_checkered is not None
                and lap_completed > self._lap_at_checkered
            ):
                self._after = True
            elif not flying:
                self._after = True
        return True, self._after
