"""RaceContextAnalyzer: TelemetrySnapshot → RaceState."""

from __future__ import annotations

from irswitch.iracing.session_flags import decode_session_flags
from irswitch.overlay.models import OpponentInfo, RaceState, TelemetrySnapshot
from irswitch.overlay.session import overlay_mode_from_session_type
from irswitch.overlay.settings import BattleSettings
from irswitch.race.history import GapHistory
from irswitch.race.opponents import (
    class_position_of,
    estimated_gap_seconds,
    is_active_racer,
    overall_position_of,
    relevant_ahead_behind,
    same_class,
)
from irswitch.race.session_end import SessionEndTracker


class RaceContextAnalyzer:
    """Deterministic race interpretation with bounded gap history."""

    def __init__(self, battle: BattleSettings | None = None) -> None:
        self._battle = battle or BattleSettings()
        window = self._battle.gap_history_seconds
        self._ahead_history = GapHistory(window_seconds=window)
        self._behind_history = GapHistory(window_seconds=window)
        self._last_ahead_idx: int | None = None
        self._last_behind_idx: int | None = None
        self._session_end = SessionEndTracker()

    def reset(self) -> None:
        self._ahead_history.clear()
        self._behind_history.clear()
        self._last_ahead_idx = None
        self._last_behind_idx = None
        self._session_end.reset()

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
        flags = decode_session_flags(snap.session_flags)
        session_checkered, player_finished, mute_field = self._session_end.update(
            session_state=session_state,
            lap_completed=snap.lap_completed,
            on_pit_road=snap.on_pit_road,
            player_track_surface=snap.player_track_surface,
            player_tow_time=snap.player_tow_time,
            player_lap_dist_pct=snap.player_lap_dist_pct,
        )

        standings = _class_standings(snap, player_idx)
        leader = standings[0] if standings else None
        return RaceState(
            connected=True,
            player_car_idx=snap.player_car_idx,
            position=snap.position,
            class_position=snap.class_position,
            class_field_size=len(standings) or None,
            leader_car_idx=leader[1] if leader else None,
            leader_name=leader[2] if leader else None,
            p1_name=standings[0][2] if len(standings) > 0 else None,
            p2_name=standings[1][2] if len(standings) > 1 else None,
            p3_name=standings[2][2] if len(standings) > 2 else None,
            lap=snap.lap,
            lap_completed=snap.lap_completed,
            current_lap_time=snap.current_lap_time,
            last_lap_time=snap.last_lap_time,
            best_lap_time=snap.best_lap_time,
            incidents=snap.incidents,
            on_pit_road=bool(snap.on_pit_road),
            is_final_lap=is_final,
            session_finished=mute_field,
            session_checkered=session_checkered,
            player_finished=player_finished,
            mute_field=mute_field,
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
            speed_mps=snap.speed_mps,
            session_flags=snap.session_flags,
            session_flag_names=flags.names,
            flag_checkered=flags.checkered,
            flag_yellow=flags.yellow,
            flag_green=flags.green,
            car_idx_best_lap_time=snap.car_idx_best_lap_time,
            car_idx_last_lap_time=snap.car_idx_last_lap_time,
        )


def _class_standings(snap: TelemetrySnapshot, player_idx: int) -> list[tuple[int, int, str | None]]:
    n = max(len(snap.car_idx_class_position), len(snap.car_idx_driver_name), 0)
    rows: list[tuple[int, int, str | None]] = []
    for car_idx in range(n):
        if car_idx != player_idx and not same_class(snap, car_idx, player_idx):
            continue
        if car_idx != player_idx and not is_active_racer(snap, car_idx, player_idx):
            continue
        cp = class_position_of(snap, car_idx)
        if cp is None or cp <= 0:
            continue
        rows.append((cp, car_idx, _driver_name(snap, car_idx)))
    rows.sort(key=lambda item: item[0])
    return rows


def _driver_name(snap: TelemetrySnapshot, car_idx: int) -> str | None:
    names = snap.car_idx_driver_name
    if car_idx < 0 or car_idx >= len(names):
        return None
    value = names[car_idx]
    return value if value else None
