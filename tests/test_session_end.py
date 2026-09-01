"""Checkered is clock end; player_finished waits for S/F, pit-rise, or CoolDown."""

from __future__ import annotations

from irswitch.events.engine import EventEngine
from irswitch.events.invalid_lap import InvalidLapEmitter
from irswitch.iracing.trk_loc import IN_PIT_STALL, ON_TRACK
from irswitch.overlay.models import RaceState
from irswitch.overlay.settings import OverlaySettings
from irswitch.race.session_end import SessionEndTracker, still_on_out_lap


def test_still_on_out_lap_track_yes_pits_tow_no() -> None:
    assert still_on_out_lap(on_pit_road=False, surface=ON_TRACK, tow_time=None) is True
    assert still_on_out_lap(on_pit_road=True, surface=ON_TRACK, tow_time=None) is False
    assert still_on_out_lap(on_pit_road=False, surface=IN_PIT_STALL, tow_time=None) is False
    assert still_on_out_lap(on_pit_road=False, surface=ON_TRACK, tow_time=2.0) is False


def test_checkered_on_track_waits_for_sf() -> None:
    tracker = SessionEndTracker()
    checkered, finished, mute = tracker.update(
        session_state=5,
        lap_completed=11,
        on_pit_road=False,
        player_track_surface=ON_TRACK,
        player_lap_dist_pct=0.4,
    )
    assert checkered is True
    assert finished is False
    assert mute is False
    checkered, finished, mute = tracker.update(
        session_state=5,
        lap_completed=11,
        on_pit_road=False,
        player_track_surface=ON_TRACK,
        player_lap_dist_pct=0.5,
    )
    assert finished is False
    checkered, finished, mute = tracker.update(
        session_state=5,
        lap_completed=12,
        on_pit_road=False,
        player_track_surface=ON_TRACK,
        player_lap_dist_pct=0.05,
    )
    assert checkered is True
    assert finished is True
    assert mute is True


def test_checkered_in_pits_is_not_finish() -> None:
    tracker = SessionEndTracker()
    checkered, finished, mute = tracker.update(
        session_state=5,
        lap_completed=4,
        on_pit_road=True,
        player_track_surface=IN_PIT_STALL,
    )
    assert checkered is True
    assert finished is False
    assert mute is False


def test_checkered_then_box_without_sf_ends_session() -> None:
    tracker = SessionEndTracker()
    tracker.update(
        session_state=5,
        lap_completed=8,
        on_pit_road=False,
        player_track_surface=ON_TRACK,
        player_lap_dist_pct=0.4,
    )
    _, finished, mute = tracker.update(
        session_state=5,
        lap_completed=8,
        on_pit_road=True,
        player_track_surface=IN_PIT_STALL,
        player_lap_dist_pct=0.41,
    )
    assert finished is True
    assert mute is True


def test_cooldown_is_player_finished_not_checkered() -> None:
    tracker = SessionEndTracker()
    checkered, finished, mute = tracker.update(
        session_state=6,
        lap_completed=20,
        on_pit_road=False,
        player_track_surface=ON_TRACK,
    )
    assert checkered is False
    assert finished is True
    assert mute is True


def test_racing_resets_tracker() -> None:
    tracker = SessionEndTracker()
    tracker.update(
        session_state=5,
        lap_completed=1,
        on_pit_road=True,
        player_track_surface=IN_PIT_STALL,
    )
    checkered, finished, mute = tracker.update(
        session_state=4,
        lap_completed=0,
        on_pit_road=False,
        player_track_surface=ON_TRACK,
    )
    assert checkered is False
    assert finished is False
    assert mute is False


def test_invalid_lap_skips_race_emits_practice() -> None:
    race = InvalidLapEmitter()
    assert (
        race.tick(
            RaceState(connected=True, overlay_mode="RACE", lap_completed=3, incidents=1),
            0.0,
        )
        == []
    )
    assert (
        race.tick(
            RaceState(connected=True, overlay_mode="RACE", lap_completed=4, incidents=2),
            1.0,
        )
        == []
    )

    practice = InvalidLapEmitter()
    practice.tick(
        RaceState(connected=True, overlay_mode="PRACTICE", lap_completed=3, incidents=1),
        0.0,
    )
    out = practice.tick(
        RaceState(connected=True, overlay_mode="PRACTICE", lap_completed=4, incidents=2),
        1.0,
    )
    assert len(out) == 1
    assert out[0].name == "invalid_lap"

    quali = InvalidLapEmitter()
    quali.tick(
        RaceState(connected=True, overlay_mode="QUALIFYING", lap_completed=1, incidents=0),
        0.0,
    )
    q_out = quali.tick(
        RaceState(connected=True, overlay_mode="QUALIFYING", lap_completed=2, incidents=1),
        1.0,
    )
    assert q_out[0].name == "invalid_lap"


def test_engine_out_lap_keeps_lap_until_after_session() -> None:
    engine = EventEngine(OverlaySettings())
    engine.tick(
        RaceState(
            connected=True,
            on_pit_road=False,
            lap_completed=10,
            last_lap_time=95.0,
            session_checkered=True,
            session_finished=False,
        ),
        1.0,
    )
    out = engine.tick(
        RaceState(
            connected=True,
            on_pit_road=False,
            lap_completed=11,
            last_lap_time=94.0,
            best_lap_time=94.0,
            session_checkered=True,
            session_finished=False,
        ),
        2.0,
    )
    names = {e.name for e in out}
    assert "lap_complete" in names or "personal_best" in names
    assert "finish" not in names


def test_engine_after_session_keeps_finish_drops_lap() -> None:
    engine = EventEngine(OverlaySettings())
    engine.tick(
        RaceState(
            connected=True,
            on_pit_road=False,
            lap_completed=11,
            last_lap_time=94.0,
            session_checkered=True,
            session_finished=False,
        ),
        1.0,
    )
    out = engine.tick(
        RaceState(
            connected=True,
            on_pit_road=False,
            lap_completed=12,
            last_lap_time=93.0,
            session_checkered=True,
            session_finished=True,
        ),
        2.0,
    )
    names = {e.name for e in out}
    assert "finish" in names
    assert "lap_complete" not in names
    assert "personal_best" not in names
