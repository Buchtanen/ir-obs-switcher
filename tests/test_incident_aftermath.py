"""Incident aftermath FSM + director template speech."""

from __future__ import annotations

from irswitch.commentary.director import CommentaryDirector
from irswitch.commentary.tts import NullTtsSink
from irswitch.iracing.trk_loc import OFF_TRACK, ON_TRACK
from irswitch.overlay.models import RaceState
from irswitch.overlay.settings import CommentarySettings
from irswitch.race.aftermath import IncidentAftermathFsm
from irswitch.race.observer import RaceObserver


def _state(
    *,
    incidents: int,
    surface: int = ON_TRACK,
    dist: float = 0.50,
    tow: float | None = None,
    connected: bool = True,
    speed_mps: float | None = None,
    overlay_mode: str = "RACE",
) -> RaceState:
    return RaceState(
        connected=connected,
        incidents=incidents,
        player_track_surface=surface,
        player_lap_dist_pct=dist,
        player_tow_time=tow,
        overlay_mode=overlay_mode,
        subsession_id="sub",
        session_num=1,
        class_position=5,
        speed_mps=speed_mps,
    )


def test_rolling_aftermath_after_incident_while_moving() -> None:
    fsm = IncidentAftermathFsm()
    assert fsm.tick(_state(incidents=2, dist=0.50), 1.0) == []
    # Rising edge while on-track; establish motion across ticks.
    fsm.tick(_state(incidents=4, dist=0.50), 1.1)
    assert fsm.take_pending() == []
    assert fsm.tick(_state(incidents=4, dist=0.501), 1.5) == []
    out = fsm.tick(_state(incidents=4, dist=0.503), 1.9)
    assert len(out) == 1
    assert out[0].event_type == "INCIDENT_AFTERMATH"
    assert out[0].metrics["kind"] == "rolling"
    assert fsm._phase == "idle"


def test_stalled_then_back_under_way() -> None:
    fsm = IncidentAftermathFsm()
    fsm.tick(_state(incidents=1, surface=ON_TRACK, dist=0.40), 1.0)
    out = fsm.tick(_state(incidents=3, surface=OFF_TRACK, dist=0.40), 1.1)
    assert len(out) == 1
    assert out[0].metrics["kind"] == "stalled"
    assert fsm._phase == "stalled"

    # Still off-track — no recovery.
    assert fsm.tick(_state(incidents=3, surface=OFF_TRACK, dist=0.40), 2.0) == []

    # On track but not yet held moving.
    fsm.tick(_state(incidents=3, surface=ON_TRACK, dist=0.40), 2.5)
    assert fsm.tick(_state(incidents=3, surface=ON_TRACK, dist=0.401), 2.7) == []

    recovered = fsm.tick(_state(incidents=3, surface=ON_TRACK, dist=0.403), 3.4)
    assert len(recovered) == 1
    assert recovered[0].event_type == "BACK_UNDER_WAY"
    assert fsm._phase == "idle"


def test_tow_counts_as_stalled() -> None:
    fsm = IncidentAftermathFsm()
    fsm.tick(_state(incidents=0, dist=0.2), 1.0)
    out = fsm.tick(_state(incidents=2, surface=ON_TRACK, dist=0.2, tow=8.0), 1.2)
    assert out[0].metrics["kind"] == "stalled"
    assert out[0].metrics["tow"] is True


def test_observer_formatter_and_derived_drain() -> None:
    from irswitch.iracing.telemetry import extract_telemetry

    snap = extract_telemetry(
        {
            "PlayerCarIdx": 0,
            "PlayerCarMyIncidentCount": 2,
            "PlayerTrackSurface": OFF_TRACK,
            "LapDistPct": 0.3,
            "SessionState": 4,
        },
        timestamp=1.0,
    )
    from irswitch.overlay.settings import RaceObserverSettings

    observer = RaceObserver(settings=RaceObserverSettings(scenario_mode="legacy"))
    state = _state(incidents=0, surface=OFF_TRACK, dist=0.3)
    observer.observe(snap, state, now=1.0)
    state2 = _state(incidents=2, surface=OFF_TRACK, dist=0.3)
    observer.observe(snap, state2, now=1.2)
    derived = observer.take_derived_envelopes()
    assert len(derived) == 1
    assert derived[0].event_type == "INCIDENT_AFTERMATH"
    text = observer.format_filler_text(derived[0], locale="en")
    assert text is not None
    assert "stalled" in text.lower() or "waiting" in text.lower()


def test_director_speaks_aftermath_via_formatter() -> None:
    observer = RaceObserver()
    director = CommentaryDirector.from_defaults(
        settings=CommentarySettings(enabled=True, cooldown_s=0.1, use_hr_emotion=False),
        sink=NullTtsSink(),
    )
    director.filler_formatter = lambda env: observer.format_filler_text(env, locale="en")
    from irswitch.events.envelope import make_envelope

    env = make_envelope(
        event_type="INCIDENT_AFTERMATH",
        phase="RESULT",
        mode="RACE",
        priority=72,
        monotonic_ms=1000,
        metrics={"kind": "rolling", "value": 2},
    )
    spoken = director.observe([env], None, 10.0)
    assert spoken is not None
    assert spoken.event_type == "INCIDENT_AFTERMATH"
    # Prefer authored graph node; formatter remains fallback when no node matches.
    assert spoken.node_id in {"incident_aftermath", "fmt:incident_aftermath"}
    assert spoken.text.strip().endswith((".", "!", "?"))
    assert "{" not in spoken.text


def test_reset_clears_aftermath_phase() -> None:
    fsm = IncidentAftermathFsm()
    fsm.tick(_state(incidents=1), 1.0)
    fsm.tick(_state(incidents=3, surface=OFF_TRACK), 1.1)
    assert fsm._phase == "stalled"
    fsm.reset()
    assert fsm._phase == "idle"
    assert fsm.take_pending() == []


def test_on_track_speed_zero_stalled_then_back_under_way() -> None:
    fsm = IncidentAftermathFsm()
    fsm.tick(_state(incidents=1, dist=0.40, speed_mps=0.0), 1.0)
    assert fsm.tick(_state(incidents=3, dist=0.40, speed_mps=0.0), 1.1) == []
    assert fsm.tick(_state(incidents=3, dist=0.40, speed_mps=0.0), 1.8) == []
    stalled = fsm.tick(_state(incidents=3, dist=0.40, speed_mps=0.0), 2.4)
    assert len(stalled) == 1
    assert stalled[0].metrics["kind"] == "stalled"
    assert fsm._phase == "stalled"

    fsm.tick(_state(incidents=3, dist=0.40, speed_mps=15.0), 2.5)
    recovered = fsm.tick(_state(incidents=3, dist=0.40, speed_mps=15.0), 3.2)
    assert len(recovered) == 1
    assert recovered[0].event_type == "BACK_UNDER_WAY"
    assert fsm._phase == "idle"


def test_off_track_with_speed_stays_stalled_then_one_back_under_way() -> None:
    fsm = IncidentAftermathFsm()
    fsm.tick(_state(incidents=1, dist=0.40, speed_mps=15.0), 1.0)
    out = fsm.tick(_state(incidents=3, surface=OFF_TRACK, dist=0.40, speed_mps=15.0), 1.1)
    assert len(out) == 1
    assert out[0].metrics["kind"] == "stalled"
    assert fsm._phase == "stalled"
    assert fsm.tick(_state(incidents=3, surface=OFF_TRACK, dist=0.41, speed_mps=15.0), 2.0) == []

    fsm.tick(_state(incidents=3, surface=ON_TRACK, dist=0.40, speed_mps=15.0), 2.5)
    recovered = fsm.tick(_state(incidents=3, surface=ON_TRACK, dist=0.40, speed_mps=15.0), 3.2)
    assert len(recovered) == 1
    assert recovered[0].event_type == "BACK_UNDER_WAY"


def test_director_same_tick_speaks_incident_not_aftermath() -> None:
    observer = RaceObserver()
    director = CommentaryDirector.from_defaults(
        settings=CommentarySettings(enabled=True, cooldown_s=0.0, use_hr_emotion=False),
        sink=NullTtsSink(),
    )
    director.filler_formatter = lambda env: observer.format_filler_text(env, locale="en")
    from irswitch.events.envelope import make_envelope

    incident = make_envelope(
        event_type="INCIDENT",
        phase="RESULT",
        mode="RACE",
        priority=90,
        monotonic_ms=10000,
        metrics={"value": 2, "branch": "unknown"},
    )
    aftermath = make_envelope(
        event_type="INCIDENT_AFTERMATH",
        phase="RESULT",
        mode="RACE",
        priority=72,
        monotonic_ms=10000,
        metrics={"kind": "stalled", "value": 2},
    )
    spoken = director.observe([aftermath, incident], None, 10.0)
    assert spoken is not None
    assert spoken.event_type == "INCIDENT"
    second = director.observe([aftermath], None, 10.0)
    assert second is None


def test_practice_recovery_keeps_back_under_way_name() -> None:
    fsm = IncidentAftermathFsm()
    fsm.tick(_state(incidents=1, overlay_mode="PRACTICE"), 1.0)
    fsm.tick(_state(incidents=3, surface=OFF_TRACK, overlay_mode="PRACTICE"), 1.1)
    fsm.tick(_state(incidents=3, surface=ON_TRACK, dist=0.40, overlay_mode="PRACTICE"), 2.5)
    recovered = fsm.tick(
        _state(incidents=3, surface=ON_TRACK, dist=0.403, overlay_mode="PRACTICE"),
        3.4,
    )
    assert recovered[0].event_type == "BACK_UNDER_WAY"
    assert recovered[0].mode == "PRACTICE"


def test_delta_one_is_aftermath_only() -> None:
    from irswitch.events.incident import IncidentEmitter
    from irswitch.overlay.settings import EventPrioritySettings, EventSettings

    emitter = IncidentEmitter(EventSettings(incident_min_delta=2), EventPrioritySettings())
    emitter.tick(_state(incidents=2, surface=OFF_TRACK), 0.0)
    assert emitter.tick(_state(incidents=3, surface=OFF_TRACK), 1.0) == []

    fsm = IncidentAftermathFsm()
    fsm.tick(_state(incidents=2, surface=OFF_TRACK), 0.0)
    out = fsm.tick(_state(incidents=3, surface=OFF_TRACK), 1.0)
    assert len(out) == 1
    assert out[0].event_type == "INCIDENT_AFTERMATH"


def test_design_reference_off_track_then_recovery_timing_and_identity() -> None:
    """Synthetic spec trace inspired by Test 7; not a replay of the original tape."""
    fsm = IncidentAftermathFsm()
    assert (
        fsm.tick(
            _state(incidents=0, surface=ON_TRACK, dist=0.4000, speed_mps=42.0),
            0.0,
        )
        == []
    )

    aftermath = fsm.tick(
        _state(incidents=2, surface=OFF_TRACK, dist=0.4010, speed_mps=18.0),
        0.05,
    )
    assert [env.event_type for env in aftermath] == ["INCIDENT_AFTERMATH"]
    assert aftermath[0].metrics["kind"] == "stalled"

    # Still moving off track is not misclassified as an on-track recovery.
    assert (
        fsm.tick(
            _state(incidents=2, surface=OFF_TRACK, dist=0.4011, speed_mps=0.4),
            0.26,
        )
        == []
    )

    assert (
        fsm.tick(
            _state(incidents=2, surface=ON_TRACK, dist=0.4013, speed_mps=3.0),
            7.50,
        )
        == []
    )
    recovery = fsm.tick(
        _state(incidents=2, surface=ON_TRACK, dist=0.4024, speed_mps=8.0),
        8.15,
    )

    assert [env.event_type for env in recovery] == ["BACK_UNDER_WAY"]
    assert recovery[0].monotonic_ms == 8150
    assert recovery[0].correlation_id == aftermath[0].correlation_id
