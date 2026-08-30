"""W4/H4 session intro / SoF / weather commentary sidecars."""

from __future__ import annotations

from irswitch.commentary.director import CommentaryDirector, slot_bindings
from irswitch.commentary.graph import COMMENTARY_ONLY_EVENTS, load_sequence_graph
from irswitch.commentary.session_briefs import SessionBriefsDetector, build_session_data_view
from irswitch.commentary.tts import NullTtsSink
from irswitch.events.envelope import make_envelope
from irswitch.overlay.models import RaceState
from irswitch.overlay.settings import CommentarySettings


def _racing_driver(car_idx: int, irating: int, class_id: int = 1) -> dict[str, object]:
    return {
        "CarIdx": car_idx,
        "IRating": irating,
        "CarClassID": class_id,
        "CarIsPaceCar": 0,
        "IsSpectator": 0,
        "UserName": f"Driver{car_idx}",
    }


def _session_data(
    *,
    sub: int = 100,
    num: int = 0,
    track: str = "Spa-Francorchamps",
    drivers: list[dict[str, object]] | None = None,
    weather: dict[str, object] | None = None,
) -> dict[str, object]:
    weekend: dict[str, object] = {
        "TrackDisplayName": track,
        "TrackConfigName": "",
        "SubSessionID": sub,
    }
    extra = dict(weather or {})
    return build_session_data_view(
        weekend_info=weekend,
        driver_info={
            "DriverCarIdx": 0,
            "Drivers": drivers
            if drivers is not None
            else [
                _racing_driver(0, 2400),
                _racing_driver(1, 2600),
            ],
        },
        subsession_id=sub,
        session_num=num,
        extra=extra,
    )


def _state(**overrides: object) -> RaceState:
    base: dict[str, object] = {
        "connected": True,
        "session_type": "Race",
        "subsession_id": "100",
        "session_num": 0,
        "overlay_mode": "RACE",
    }
    base.update(overrides)
    return RaceState(**base)  # type: ignore[arg-type]


def _director(*, session_briefs: bool = True, enabled: bool = True) -> CommentaryDirector:
    return CommentaryDirector(
        graph=load_sequence_graph(),
        settings=CommentarySettings(
            enabled=enabled,
            session_briefs=session_briefs,
            use_hr_emotion=False,
            cooldown_s=0.0,
        ),
        sink=NullTtsSink(),
        language="en",
    )


def _clear_locks(director: CommentaryDirector) -> None:
    director._busy_until = 0.0
    director._global_ready_at = 0.0


def test_commentary_only_events_include_session_briefs() -> None:
    assert {
        "SESSION_INTRO_PRACTICE",
        "SESSION_INTRO_QUALIFY",
        "SESSION_INTRO_RACE",
        "SOF_BRIEF",
        "WEATHER_BRIEF",
    } <= COMMENTARY_ONLY_EVENTS
    graph = load_sequence_graph()
    assert "session_intro_race" in graph.nodes
    assert "sof_brief" in graph.nodes
    assert "weather_brief" in graph.nodes


def test_once_per_session_intro_and_reset_on_key_change() -> None:
    det = SessionBriefsDetector()
    data = _session_data(num=0)
    first = det.tick(_state(session_type="Practice", session_num=0), data, 1.0)
    assert first is not None
    assert first.event_type == "SESSION_INTRO_PRACTICE"
    det.acknowledge(first.event_type)
    assert det.tick(_state(session_type="Practice", session_num=0), data, 2.0) is not None
    # After intro ack, practice has no SoF — weather next
    weather = det.tick(_state(session_type="Practice", session_num=0), data, 2.0)
    assert weather is not None
    assert weather.event_type == "WEATHER_BRIEF"
    det.acknowledge(weather.event_type)
    assert det.tick(_state(session_type="Practice", session_num=0), data, 3.0) is None

    # New SessionNum resets
    data2 = _session_data(num=1)
    again = det.tick(_state(session_type="Practice", session_num=1), data2, 4.0)
    assert again is not None
    assert again.event_type == "SESSION_INTRO_PRACTICE"


def test_disconnect_resets_briefs() -> None:
    det = SessionBriefsDetector()
    data = _session_data()
    env = det.tick(_state(), data, 1.0)
    assert env is not None
    det.acknowledge(env.event_type)
    assert det.tick(_state(connected=False), data, 2.0) is None
    restart = det.tick(_state(), data, 3.0)
    assert restart is not None
    assert restart.event_type == "SESSION_INTRO_RACE"


def test_race_sof_once_when_roster_ready_then_weather() -> None:
    det = SessionBriefsDetector()
    data = _session_data(
        weather={"Skies": 1, "AirTemp": 22.0, "WindVel": 3.0, "Precipitation": 0.0}
    )
    intro = det.tick(_state(), data, 1.0)
    assert intro is not None and intro.event_type == "SESSION_INTRO_RACE"
    det.acknowledge(intro.event_type)

    sof = det.tick(_state(), data, 2.0)
    assert sof is not None
    assert sof.event_type == "SOF_BRIEF"
    assert sof.metrics.get("sof") == "2,500"
    assert sof.metrics.get("field_size") == 2
    assert sof.metrics.get("sofOfficial") is False
    det.acknowledge(sof.event_type)

    weather = det.tick(_state(), data, 3.0)
    assert weather is not None
    assert weather.event_type == "WEATHER_BRIEF"
    assert weather.metrics.get("skies") == "partly cloudy"
    assert weather.metrics.get("air_temp") == "22 C"
    det.acknowledge(weather.event_type)
    assert det.tick(_state(), data, 4.0) is None


def test_flag_off_director_skips_with_reason() -> None:
    director = _director(session_briefs=False)
    env = make_envelope(
        event_type="SESSION_INTRO_PRACTICE",
        phase="RESULT",
        priority=36,
        metrics={"track": "Monza"},
    )
    assert director.observe([env], None, 10.0) is None
    assert director.decisions()[-1]["reason"] == "session_briefs_disabled"


def test_flag_default_off() -> None:
    assert CommentarySettings().session_briefs is False
    director = CommentaryDirector.from_defaults()
    assert director.settings.session_briefs is False


def test_missing_optional_weather_and_sof_still_speak_slot_light() -> None:
    director = _director(session_briefs=True)
    # Weather with no metrics — slot-light lines have no required slots.
    weather = make_envelope(
        event_type="WEATHER_BRIEF",
        phase="RESULT",
        priority=34,
        metrics={},
    )
    spoken = director.observe([weather], None, 10.0)
    assert spoken is not None
    assert spoken.node_id == "weather_brief"
    assert "{" not in spoken.text

    _clear_locks(director)
    sof = make_envelope(
        event_type="SOF_BRIEF",
        phase="RESULT",
        priority=46,
        metrics={},
    )
    spoken2 = director.observe([sof], None, 20.0)
    assert spoken2 is not None
    assert spoken2.node_id == "sof_brief"
    assert "{" not in spoken2.text


def test_slot_bindings_session_brief_fields() -> None:
    env = make_envelope(
        event_type="SOF_BRIEF",
        phase="RESULT",
        priority=46,
        metrics={
            "track": "Spa-Francorchamps",
            "field_size": 32,
            "sof": "2,450",
            "sof_class": "2,520",
            "skies": "clear",
            "air_temp": "23 C",
            "track_temp": "31 C",
            "wind_speed": "4 m/s",
            "precipitation": "dry",
        },
    )
    bindings = slot_bindings(env, "unknown")
    assert bindings["track"] == "Spa-Francorchamps"
    assert bindings["field_size"] == 32
    assert bindings["sof"] == "2,450"
    assert bindings["sof_class"] == "2,520"
    assert bindings["skies"] == "clear"
    assert bindings["air_temp"] == "23 C"
    assert bindings["track_temp"] == "31 C"
    assert bindings["wind_speed"] == "4 m/s"
    assert bindings["precipitation"] == "dry"


def test_qualify_intro_binds_track_and_field_size() -> None:
    det = SessionBriefsDetector()
    data = _session_data(track="Monza")
    env = det.tick(_state(session_type="Qualify", overlay_mode="QUALIFYING"), data, 1.0)
    assert env is not None
    assert env.event_type == "SESSION_INTRO_QUALIFY"
    assert env.metrics.get("track") == "Monza"
    assert env.metrics.get("field_size") == 2

    director = _director(session_briefs=True)
    spoken = director.observe([env], None, 5.0)
    assert spoken is not None
    assert spoken.node_id == "session_intro_qualify"
