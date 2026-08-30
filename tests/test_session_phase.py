"""Post-race mute and pit-entry gates."""

from __future__ import annotations

from irswitch.events.engine import EventEngine
from irswitch.events.session_phase import filter_post_race, should_begin_pit_cycle
from irswitch.iracing.trk_loc import IN_PIT_STALL, NOT_IN_WORLD, ON_TRACK
from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import OverlaySettings


def _state(**overrides: object) -> RaceState:
    base: dict[str, object] = {
        "connected": True,
        "player_track_surface": ON_TRACK,
        "on_pit_road": True,
        "player_lap_dist_pct": 0.12,
    }
    base.update(overrides)
    return RaceState(**base)  # type: ignore[arg-type]


def test_filter_post_race_keeps_finish_and_exits() -> None:
    events = [
        CandidateEvent(name="finish", channel="session", priority=90, phase="trigger"),
        CandidateEvent(name="lap_complete", channel="lap", priority=40, phase="trigger"),
        CandidateEvent(name="battle", channel="battle", priority=20, phase="exit"),
        CandidateEvent(name="pit_entry", channel="session", priority=50, phase="trigger"),
    ]
    kept = filter_post_race(events, session_finished=True)
    assert [e.name for e in kept] == ["finish", "battle"]
    assert filter_post_race(events, session_finished=False) == events


def test_engine_checkered_keeps_finish_drops_lap() -> None:
    engine = EventEngine(OverlaySettings())
    engine.tick(_state(on_pit_road=False, lap_completed=10, last_lap_time=95.0), 1.0)
    out = engine.tick(
        _state(
            on_pit_road=False,
            lap_completed=11,
            last_lap_time=94.0,
            best_lap_time=94.0,
            session_finished=True,
        ),
        2.0,
    )
    names = {e.name for e in out}
    assert "finish" in names
    assert "lap_complete" not in names
    assert "personal_best" not in names


def test_should_begin_pit_rejects_lobby_and_esc_and_tow() -> None:
    lobby = _state(player_track_surface=IN_PIT_STALL)
    assert should_begin_pit_cycle(lobby, seen_on_track=False, prev_surface=NOT_IN_WORLD) is False

    esc = _state(player_track_surface=IN_PIT_STALL, player_lap_dist_pct=0.02)
    assert (
        should_begin_pit_cycle(
            esc,
            seen_on_track=True,
            prev_surface=ON_TRACK,
            prev_dist=0.55,
        )
        is False
    )

    tow = _state(player_track_surface=IN_PIT_STALL, player_tow_time=4.0)
    assert should_begin_pit_cycle(tow, seen_on_track=True, prev_surface=ON_TRACK) is False


def test_should_begin_pit_driven_entry() -> None:
    state = _state(player_track_surface=IN_PIT_STALL, player_lap_dist_pct=0.13)
    assert (
        should_begin_pit_cycle(
            state,
            seen_on_track=True,
            prev_surface=ON_TRACK,
            prev_dist=0.12,
        )
        is True
    )
    assert (
        should_begin_pit_cycle(
            _state(session_finished=True), seen_on_track=True, prev_surface=ON_TRACK
        )
        is False
    )
