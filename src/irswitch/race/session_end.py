"""Checkered is the session clock; player_finished is this driver done."""

from __future__ import annotations

from dataclasses import dataclass

from irswitch.iracing.trk_loc import (
    APPROACHING_PITS,
    IN_PIT_STALL,
    NOT_IN_WORLD,
    is_esc_teleport,
    is_towing,
)

# iRacing SessionState: 4 Racing, 5 Checkered, 6 CoolDown
IRSDK_CHECKERED = 5
IRSDK_COOLDOWN = 6


def still_on_out_lap(
    *,
    on_pit_road: bool | None,
    surface: int | None,
    tow_time: float | None,
) -> bool:
    """True when the driver may still complete the lap after checkered.

    Informational only — mute/FINISH follow ``player_finished``, not this helper.
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
    """Maps iRacing checkered/cooldown onto N4 finish booleans.

    ``session_checkered`` is ``SessionState == 5`` only (not the client flag bit,
    not CoolDown). ``player_finished`` / ``mute_field`` rise on S/F or eligible
    pit-rise after checkered, or CoolDown fallback. Already in pits at checkered
    is not finish. ``on_pit_road is None`` is unknown (does not arm pit-rise).
    """

    _saw_checkered: bool = False
    _on_pit_at_checkered: bool | None = None
    _player_finished: bool = False
    _prev_lap_completed: int | None = None
    _prev_lap_dist: float | None = None
    _prev_on_pit: bool | None = None
    _prev_surface: int | None = None

    def reset(self) -> None:
        self._saw_checkered = False
        self._on_pit_at_checkered = None
        self._player_finished = False
        self._prev_lap_completed = None
        self._prev_lap_dist = None
        self._prev_on_pit = None
        self._prev_surface = None

    def update(
        self,
        *,
        session_state: int | None,
        lap_completed: int | None,
        on_pit_road: bool | None,
        player_track_surface: int | None,
        player_tow_time: float | None = None,
        player_lap_dist_pct: float | None = None,
    ) -> tuple[bool, bool, bool]:
        """Return ``(session_checkered, player_finished, mute_field)``.

        ``player_tow_time`` is unused for finish; kept so call sites can pass the snapshot field.
        """
        del player_tow_time
        ss = session_state if session_state is not None else 0
        session_checkered = ss == IRSDK_CHECKERED
        if ss not in (IRSDK_CHECKERED, IRSDK_COOLDOWN):
            self._saw_checkered = False
            self._on_pit_at_checkered = None
            self._player_finished = False
            self._store(lap_completed, on_pit_road, player_track_surface, player_lap_dist_pct)
            return False, False, False

        if session_checkered and not self._saw_checkered:
            self._saw_checkered = True
            self._on_pit_at_checkered = on_pit_road

        if not self._player_finished:
            if session_checkered and self._crossed_start_finish(lap_completed, player_lap_dist_pct):
                self._player_finished = True
            elif session_checkered and self._eligible_pit_rise(
                on_pit_road, player_track_surface, player_lap_dist_pct
            ):
                self._player_finished = True
            elif ss == IRSDK_COOLDOWN:
                self._player_finished = True

        self._store(lap_completed, on_pit_road, player_track_surface, player_lap_dist_pct)
        mute = self._player_finished
        return session_checkered, self._player_finished, mute

    def _crossed_start_finish(
        self, lap_completed: int | None, player_lap_dist_pct: float | None
    ) -> bool:
        prev_lap = self._prev_lap_completed
        if prev_lap is not None and lap_completed is not None and lap_completed > prev_lap:
            return True
        prev_dist = self._prev_lap_dist
        dist = player_lap_dist_pct
        if prev_dist is None or dist is None:
            return False
        return prev_dist > 0.85 and dist < 0.15

    def _eligible_pit_rise(
        self,
        on_pit_road: bool | None,
        player_track_surface: int | None,
        player_lap_dist_pct: float | None,
    ) -> bool:
        if self._on_pit_at_checkered is not False:
            return False
        if self._prev_on_pit is not False or on_pit_road is not True:
            return False
        if is_esc_teleport(
            self._prev_surface,
            player_track_surface,
            self._prev_lap_dist,
            player_lap_dist_pct,
        ):
            return False
        return True

    def _store(
        self,
        lap_completed: int | None,
        on_pit_road: bool | None,
        player_track_surface: int | None,
        player_lap_dist_pct: float | None,
    ) -> None:
        self._prev_lap_completed = lap_completed
        self._prev_lap_dist = player_lap_dist_pct
        self._prev_on_pit = on_pit_road
        self._prev_surface = player_track_surface
