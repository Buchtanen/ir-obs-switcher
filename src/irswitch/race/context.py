"""RaceContextAnalyzer: TelemetrySnapshot → RaceState."""

from __future__ import annotations

from irswitch.overlay.models import OpponentInfo, RaceState, TelemetrySnapshot
from irswitch.overlay.session import overlay_mode_from_session_type
from irswitch.overlay.settings import BattleSettings
from irswitch.race.history import GapHistory
from irswitch.race.opponents import (
    class_position_of,
    estimated_gap_seconds,
    overall_position_of,
    relevant_ahead_behind,
)

# iRacing SessionState: 4 Racing, 5 Checkered, 6 CoolDown
_SESSION_CHECKERED = 5
_SESSION_COOLDOWN = 6


class RaceContextAnalyzer:
    """Deterministic race interpretation with bounded gap history."""

    def __init__(self, battle: BattleSettings | None = None) -> None:
        self._battle = battle or BattleSettings()
        window = self._battle.gap_history_seconds
        self._ahead_history = GapHistory(window_seconds=window)
        self._behind_history = GapHistory(window_seconds=window)
        self._last_ahead_idx: int | None = None
        self._last_behind_idx: int | None = None

    def reset(self) -> None:
        self._ahead_history.clear()
        self._behind_history.clear()
        self._last_ahead_idx = None
        self._last_behind_idx = None

    def analyze(self, snap: TelemetrySnapshot) -> RaceState:
        player_idx = snap.player_car_idx
        if not snap.connected or player_idx is None:
            self.reset()
            return RaceState(connected=False)
        ahead_idx, behind_idx = relevant_ahead_behind(snap)
        if ahead_idx != self._last_ahead_idx:
            self._ahead_history.clear()
            self._last_ahead_idx = ahead_idx
        if behind_idx != self._last_behind_idx:
            self._behind_history.clear()
            self._last_behind_idx = behind_idx

        gap_ahead = (
            estimated_gap_seconds(snap, player_idx, ahead_idx) if ahead_idx is not None else None
        )
        gap_behind = None
        if behind_idx is not None:
            raw = estimated_gap_seconds(snap, player_idx, behind_idx)
            gap_behind = -raw if raw is not None else None

        self._ahead_history.add(snap.timestamp, gap_ahead)
        self._behind_history.add(snap.timestamp, gap_behind)
        close_ahead = self._ahead_history.closing_rate()
        close_behind = self._behind_history.closing_rate()

        opponent_ahead = None
        if ahead_idx is not None:
            opponent_ahead = OpponentInfo(
                car_idx=ahead_idx,
                position=overall_position_of(snap, ahead_idx),
                class_position=class_position_of(snap, ahead_idx),
                gap=gap_ahead,
                closing_rate=close_ahead,
                display_name=_driver_name(snap, ahead_idx),
            )
        opponent_behind = None
        if behind_idx is not None:
            opponent_behind = OpponentInfo(
                car_idx=behind_idx,
                position=overall_position_of(snap, behind_idx),
                class_position=class_position_of(snap, behind_idx),
                gap=gap_behind,
                closing_rate=close_behind,
                display_name=_driver_name(snap, behind_idx),
            )

        remain = snap.session_laps_remain
        session_state = snap.session_state or 0
        is_final = bool(remain is not None and 0 < remain <= 1.05 and session_state == 4)
        finished = session_state in {_SESSION_CHECKERED, _SESSION_COOLDOWN}

        return RaceState(
            connected=True,
            player_car_idx=snap.player_car_idx,
            position=snap.position,
            class_position=snap.class_position,
            lap=snap.lap,
            lap_completed=snap.lap_completed,
            current_lap_time=snap.current_lap_time,
            last_lap_time=snap.last_lap_time,
            best_lap_time=snap.best_lap_time,
            incidents=snap.incidents,
            on_pit_road=bool(snap.on_pit_road),
            is_final_lap=is_final,
            session_finished=finished,
            opponent_ahead=opponent_ahead,
            opponent_behind=opponent_behind,
            gap_ahead=gap_ahead,
            gap_behind=gap_behind,
            closing_rate_ahead=close_ahead,
            closing_rate_behind=close_behind,
            car_idx_on_pit_road=snap.car_idx_on_pit_road,
            fps=snap.fps,
            frametime_ms=snap.frametime_ms,
            session_num=snap.session_num,
            subsession_id=snap.subsession_id,
            session_type=snap.session_type,
            track_id=snap.track_id,
            session_time=snap.session_time,
            session_state=snap.session_state,
            overlay_mode=overlay_mode_from_session_type(snap.session_type),
            player_lap_dist_pct=snap.player_lap_dist_pct,
            stale_for_ms=snap.stale_for_ms,
            data_quality=snap.data_quality,
            player_track_surface=snap.player_track_surface,
            player_tow_time=snap.player_tow_time,
        )


def _driver_name(snap: TelemetrySnapshot, car_idx: int) -> str | None:
    names = snap.car_idx_driver_name
    if car_idx < 0 or car_idx >= len(names):
        return None
    value = names[car_idx]
    return value if value else None
