"""RaceObserver MVP: near-field 2+2, weather watch, silence fillers."""

from __future__ import annotations

from irswitch.commentary.director import CommentaryDirector
from irswitch.commentary.tts import NullTtsSink
from irswitch.events.envelope import make_envelope
from irswitch.iracing.telemetry import extract_telemetry
from irswitch.iracing.weather import WeatherSnapshot
from irswitch.overlay.models import RaceState
from irswitch.overlay.settings import CommentarySchedulerSettings, CommentarySettings
from irswitch.race.observer import RaceObserver, _weather_changed
from irswitch.race.opponents import relevant_ahead_behind, relevant_near_field


def _snap_field(
    *,
    names: list[str | None] | None = None,
    pct: list[float] | None = None,
    laps: list[int] | None = None,
) -> object:
    n = 5
    zeros_b = [False] * n
    zeros_s = [3] * n
    data: dict[str, object] = {
        "PlayerCarIdx": 2,
        "PlayerCarPosition": 3,
        "PlayerCarClassPosition": 3,
        "PlayerCarClass": 1,
        "LapCompleted": 10,
        "LapLastLapTime": 90.0,
        "OnPitRoad": False,
        "SessionState": 4,
        "SessionNum": 1,
        "CarIdxLapDistPct": pct or [0.54, 0.52, 0.50, 0.48, 0.46],
        "CarIdxLapCompleted": laps or [10, 10, 10, 10, 10],
        "CarIdxClass": [1, 1, 1, 1, 1],
        "CarIdxClassPosition": [1, 2, 3, 4, 5],
        "CarIdxPosition": [1, 2, 3, 4, 5],
        "CarIdxOnPitRoad": zeros_b,
        "CarIdxTrackSurface": zeros_s,
    }
    if names is not None:
        data["DriverInfo"] = {
            "Drivers": [
                {"CarIdx": i, "UserName": name or f"Car{i}"} for i, name in enumerate(names)
            ]
        }
    return extract_telemetry(data, timestamp=1.0)


def test_relevant_near_field_returns_two_ahead_and_behind() -> None:
    snap = _snap_field(
        names=["A", "B", "Hero", "D", "E"],
    )
    ahead, behind = relevant_near_field(snap, ahead_n=2, behind_n=2)
    assert [c.car_idx for c in ahead] == [1, 0]
    assert [c.display_name for c in ahead] == ["B", "A"]
    assert [c.car_idx for c in behind] == [3, 4]
    assert [c.display_name for c in behind] == ["D", "E"]


def test_relevant_ahead_behind_still_one_plus_one() -> None:
    snap = _snap_field()
    ahead, behind = relevant_ahead_behind(snap)
    assert ahead == 1
    assert behind == 3


def test_observe_builds_story_context_with_near_field() -> None:
    snap = _snap_field(names=["A", "B", "Hero", "D", "E"])
    observer = RaceObserver()
    state = RaceState(
        connected=True,
        overlay_mode="RACE",
        class_position=3,
        position=3,
        lap=10,
    )
    ctx = observer.observe(snap, state, now=1.0)
    assert ctx.hero.class_position == 3
    assert len(ctx.ahead) == 2
    assert len(ctx.behind) == 2
    assert ctx.leader_name == "A"
    slots = ctx.slot_bindings()
    assert slots["position"] == 3
    assert slots["target_name"] == "B"
    assert slots["aheadCount"] == 2


def test_weather_change_queues_filler_envelope() -> None:
    observer = RaceObserver()
    snap = _snap_field(names=["A", "B", "Hero", "D", "E"])
    state = RaceState(connected=True, overlay_mode="RACE", class_position=3)
    observer.observe(
        snap,
        state,
        now=1.0,
        telemetry_data={"AirTemp": 20.0, "Skies": 0, "WindVel": 2.0},
    )
    observer.observe(
        snap,
        state,
        now=2.0,
        telemetry_data={"AirTemp": 22.0, "Skies": 3, "WindVel": 2.0},
    )
    env = observer.next_filler_envelope(10.0, locale="en")
    assert env is not None
    assert env.event_type == "WEATHER_CHANGE"
    assert env.metrics.get("kind") == "weather_change"
    text = observer.format_filler_text(env, locale="en")
    assert text is not None
    assert "Weather update" in text


def test_field_fact_filler_rotates() -> None:
    observer = RaceObserver()
    snap = _snap_field(names=["Leader", "B", "Hero", "D", "E"])
    state = RaceState(connected=True, overlay_mode="RACE", class_position=3, position=3)
    observer.observe(snap, state, now=1.0)
    first = observer.next_filler_envelope(5.0, locale="en")
    assert first is not None
    assert first.event_type == "FIELD_FACT"
    second = observer.next_filler_envelope(25.0, locale="en")
    assert second is not None
    assert second.metrics.get("fact") != first.metrics.get("fact")


def test_filler_skips_after_checkered_and_after_session() -> None:
    observer = RaceObserver()
    snap = _snap_field(names=["Leader", "B", "Hero", "D", "E"])
    observer.observe(
        snap,
        RaceState(
            connected=True,
            overlay_mode="RACE",
            class_position=3,
            session_checkered=True,
            session_finished=False,
        ),
        now=1.0,
    )
    assert observer.next_filler_envelope(5.0, locale="en") is None
    observer.observe(
        snap,
        RaceState(
            connected=True,
            overlay_mode="RACE",
            class_position=3,
            session_checkered=True,
            session_finished=True,
        ),
        now=2.0,
    )
    assert observer.next_filler_envelope(30.0, locale="en") is None


def test_director_silence_fill_uses_observer_formatter() -> None:
    observer = RaceObserver()
    snap = _snap_field(names=["Leader", "B", "Hero", "D", "E"])
    state = RaceState(connected=True, overlay_mode="RACE", class_position=3, position=3)
    observer.observe(snap, state, now=1.0)

    settings = CommentarySettings(
        enabled=True,
        cooldown_s=0.1,
        use_hr_emotion=False,
        scheduler=CommentarySchedulerSettings(
            defer_enabled=True,
            max_silence_s=1.0,
        ),
    )
    director = CommentaryDirector.from_defaults(settings=settings, sink=NullTtsSink())
    director.filler_provider = lambda now: observer.next_filler_envelope(now, locale="en")
    director.filler_formatter = lambda env: observer.format_filler_text(env, locale="en")
    spoken = director.observe(
        [
            make_envelope(
                event_type="OVERTAKE",
                phase="RESULT",
                mode="RACE",
                priority=80,
                monotonic_ms=1000,
                metrics={"position": 3},
            )
        ],
        None,
        1.0,
    )
    assert spoken is not None
    after = 1.0 + max(float(spoken.estimated_seconds), 1.05) + 0.05
    director._busy_until = 0.0
    director._global_ready_at = 0.0
    filled = director.tick(after)
    assert filled is not None
    assert director.decisions(1)[-1]["reason"] == "silence_fill"


def test_weather_threshold_helpers() -> None:
    a = WeatherSnapshot(skies="clear", air_temp_c=20.0, track_temp_c=30.0, wind_speed_mps=2.0)
    b = WeatherSnapshot(skies="clear", air_temp_c=20.5, track_temp_c=30.0, wind_speed_mps=2.0)
    assert _weather_changed(a, b) is False
    c = WeatherSnapshot(skies="overcast", air_temp_c=20.0, track_temp_c=30.0, wind_speed_mps=2.0)
    assert _weather_changed(a, c) is True
