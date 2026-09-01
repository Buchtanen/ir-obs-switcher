"""N7 quali recap + ParadeLaps padding (race_observer.grid_story)."""

from __future__ import annotations

from types import SimpleNamespace

from irswitch.commentary.director import CommentaryDirector
from irswitch.commentary.opener import OpenerMutex
from irswitch.commentary.tts import NullTtsSink
from irswitch.events.envelope import make_envelope
from irswitch.iracing.telemetry import extract_telemetry
from irswitch.overlay.bus import OverlayBus
from irswitch.overlay.models import RaceState
from irswitch.overlay.runtime import OverlayRuntime
from irswitch.overlay.settings import CommentarySettings, OverlaySettings, RaceObserverSettings
from irswitch.race.grid_story import (
    IRSDK_PARADE_LAPS,
    IRSDK_RACING,
    PARADE_COOLDOWN_S,
    PARADE_MAX,
    GridStoryFsm,
)
from irswitch.race.observer import RaceObserver
from irswitch.race.story import QualiBag, StreamMemory


def _state(
    *,
    mode: str = "RACE",
    session_state: int | None = IRSDK_PARADE_LAPS,
    **overrides: object,
) -> RaceState:
    payload: dict[str, object] = {
        "connected": True,
        "overlay_mode": mode,
        "session_state": session_state,
        "player_finished": False,
        "session_checkered": False,
        "mute_field": False,
        "subsession_id": "sub",
        "session_num": 2,
    }
    payload.update(overrides)
    return RaceState(**payload)  # type: ignore[arg-type]


def _bag(*, position: int = 4, best: float | None = 91.234) -> QualiBag:
    return QualiBag(class_position=position, best_lap_s=best)


def test_missing_bag_skips_recap_once() -> None:
    fsm = GridStoryFsm()
    assert fsm.tick(_state(), 1.0, enabled=True, bag=None, session_key="race") == []
    again = fsm.tick(_state(), 1.2, enabled=True, bag=_bag(), session_key="race")
    assert again == [] or again[0].event_type != "QUALI_RECAP"


def test_one_quali_recap_from_bag() -> None:
    fsm = GridStoryFsm()
    out = fsm.tick(_state(), 1.0, enabled=True, bag=_bag(), session_key="race")
    assert len(out) == 1
    assert out[0].event_type == "QUALI_RECAP"
    assert out[0].metrics["position"] == 4
    assert out[0].metrics["lapTime"] == 91.234
    assert fsm.tick(_state(), 1.2, enabled=True, bag=_bag(), session_key="race")[0].event_type != (
        "QUALI_RECAP"
    )


def test_recap_skipped_when_already_racing() -> None:
    fsm = GridStoryFsm()
    assert (
        fsm.tick(
            _state(session_state=IRSDK_RACING),
            1.0,
            enabled=True,
            bag=_bag(),
            session_key="race",
        )
        == []
    )


def test_recap_skipped_on_green_flag() -> None:
    fsm = GridStoryFsm()
    assert (
        fsm.tick(
            _state(session_state=IRSDK_PARADE_LAPS, flag_green=True),
            1.0,
            enabled=True,
            bag=_bag(),
            session_key="race",
        )
        == []
    )


def test_parade_pad_cooldown_and_cap() -> None:
    fsm = GridStoryFsm()
    recap = fsm.tick(_state(), 1.0, enabled=True, bag=_bag(), session_key="race")
    assert recap[0].event_type == "QUALI_RECAP"
    first = fsm.tick(_state(), 2.0, enabled=True, bag=_bag(), session_key="race")
    assert first[0].event_type == "PARADE_PAD"
    assert fsm.tick(_state(), 3.0, enabled=True, bag=_bag(), session_key="race") == []
    second = fsm.tick(
        _state(), 2.0 + PARADE_COOLDOWN_S + 0.1, enabled=True, bag=_bag(), session_key="race"
    )
    assert second[0].event_type == "PARADE_PAD"
    now = 2.0 + PARADE_COOLDOWN_S + 0.1
    while fsm._parade_count < PARADE_MAX:
        now += PARADE_COOLDOWN_S + 0.1
        later = fsm.tick(_state(), now, enabled=True, bag=_bag(), session_key="race")
        assert later and later[0].event_type == "PARADE_PAD"
    assert (
        fsm.tick(
            _state(), now + PARADE_COOLDOWN_S + 0.1, enabled=True, bag=_bag(), session_key="race"
        )
        == []
    )
    assert fsm._parade_count == PARADE_MAX


def test_parade_stops_on_session_state_racing() -> None:
    fsm = GridStoryFsm()
    fsm.tick(_state(), 1.0, enabled=True, bag=_bag(), session_key="race")
    fsm.tick(_state(), 2.0, enabled=True, bag=_bag(), session_key="race")
    assert (
        fsm.tick(
            _state(session_state=IRSDK_RACING),
            30.0,
            enabled=True,
            bag=_bag(),
            session_key="race",
        )
        == []
    )


def test_parade_stops_on_green_without_state_4() -> None:
    fsm = GridStoryFsm()
    fsm.tick(_state(), 1.0, enabled=True, bag=_bag(), session_key="race")
    fsm.tick(_state(), 2.0, enabled=True, bag=_bag(), session_key="race")
    assert (
        fsm.tick(
            _state(flag_green=True),
            30.0,
            enabled=True,
            bag=_bag(),
            session_key="race",
        )
        == []
    )


def test_disabled_and_non_race_silent() -> None:
    fsm = GridStoryFsm()
    assert fsm.tick(_state(), 1.0, enabled=False, bag=_bag(), session_key="race") == []
    other = GridStoryFsm()
    assert (
        other.tick(
            _state(mode="QUALIFYING"),
            1.0,
            enabled=True,
            bag=_bag(),
            session_key="q",
        )
        == []
    )


def test_stream_memory_bag_survives_session_reset() -> None:
    mem = StreamMemory()
    mem.note_quali(7, 88.1)
    mem.note_session("sub:1:track")
    assert mem.quali_bag() is not None
    assert mem.quali_bag().class_position == 7
    assert mem.quali_bag().best_lap_s == 88.1
    mem.note_session("sub:2:track")
    assert mem.quali_bag() is not None
    mem.reset_stream()
    assert mem.quali_bag() is None


def test_observer_captures_quali_then_recaps_in_race() -> None:
    observer = RaceObserver(settings=RaceObserverSettings(grid_story=True))
    quali_snap = extract_telemetry(
        {
            "PlayerCarIdx": 0,
            "PlayerCarClassPosition": 5,
            "LapBestLapTime": 90.5,
            "SessionState": 4,
            "SessionNum": 1,
            "SessionType": "Qualify",
        },
        timestamp=1.0,
    )
    observer.observe(
        quali_snap,
        _state(mode="QUALIFYING", session_state=4, session_num=1, class_position=5),
        now=1.0,
    )
    assert observer.take_derived_envelopes() == []
    assert observer.stream.quali_bag() is not None

    race_snap = extract_telemetry(
        {
            "PlayerCarIdx": 0,
            "SessionState": IRSDK_PARADE_LAPS,
            "SessionNum": 2,
            "SessionType": "Race",
        },
        timestamp=2.0,
    )
    observer.observe(
        race_snap,
        _state(session_num=2, session_state=IRSDK_PARADE_LAPS),
        now=2.0,
    )
    derived = observer.take_derived_envelopes()
    types = [env.event_type for env in derived]
    assert types.count("QUALI_RECAP") == 1
    recap = next(env for env in derived if env.event_type == "QUALI_RECAP")
    assert recap.metrics["position"] == 5


def test_observer_default_grid_story_off() -> None:
    observer = RaceObserver()
    observer.stream.note_quali(3, 90.0)
    snap = extract_telemetry({"PlayerCarIdx": 0, "SessionState": IRSDK_PARADE_LAPS}, timestamp=1.0)
    observer.observe(snap, _state(), now=1.0)
    assert observer.take_derived_envelopes() == []


def test_formatter_and_director_speak_recap() -> None:
    observer = RaceObserver(settings=RaceObserverSettings(grid_story=True))
    director = CommentaryDirector.from_defaults(
        settings=CommentarySettings(enabled=True, cooldown_s=0.1, use_hr_emotion=False),
        sink=NullTtsSink(),
    )
    director.filler_formatter = lambda env: observer.format_filler_text(env, locale="en")
    fsm = GridStoryFsm()
    env = fsm.tick(_state(), 1.0, enabled=True, bag=_bag(), session_key="race")[0]
    text = observer.format_filler_text(env, locale="en")
    assert text is not None
    assert "P4" in text
    spoken = director.observe([env], None, 10.0)
    assert spoken is not None
    assert spoken.event_type == "QUALI_RECAP"
    cs = observer.format_filler_text(env, locale="cs")
    assert cs is not None
    assert "Kvalifikoval" in cs
    pad = make_envelope(
        event_type="PARADE_PAD",
        phase="RESULT",
        mode="RACE",
        priority=30,
        metrics={"kind": "parade_pad"},
    )
    assert "formation" in (observer.format_filler_text(pad, locale="en") or "")


def test_director_replaces_race_intro_when_bag_ready() -> None:
    director = CommentaryDirector.from_defaults(
        settings=CommentarySettings(
            enabled=True,
            session_briefs=True,
            cooldown_s=0.0,
            use_hr_emotion=False,
        ),
        sink=NullTtsSink(),
    )
    director.grid_story = True
    director.quali_bag_ready = True
    intro = make_envelope(
        event_type="SESSION_INTRO_RACE",
        phase="RESULT",
        mode="RACE",
        priority=64,
        metrics={"track": "Spa-Francorchamps", "field_size": 20},
    )
    assert director.observe([intro], None, 1.0) is None
    assert director.decisions(1)[-1]["reason"] == "grid_story_replaces_intro"


def test_director_keeps_race_intro_without_bag() -> None:
    director = CommentaryDirector.from_defaults(
        settings=CommentarySettings(
            enabled=True,
            session_briefs=True,
            cooldown_s=0.0,
            use_hr_emotion=False,
        ),
        sink=NullTtsSink(),
    )
    director.grid_story = True
    director.quali_bag_ready = False
    intro = make_envelope(
        event_type="SESSION_INTRO_RACE",
        phase="RESULT",
        mode="RACE",
        priority=64,
        metrics={"track": "Spa-Francorchamps", "field_size": 20},
    )
    spoken = director.observe([intro], None, 1.0)
    assert spoken is not None
    assert spoken.event_type == "SESSION_INTRO_RACE"


def test_quali_recap_is_opener() -> None:
    lock = OpenerMutex(hold_s=10.0)
    lock.note("QUALI_RECAP", 1.0)
    assert lock.skip_reason("SESSION_INTRO_RACE", 2.0) == "opener_mutex"
    assert lock.skip_reason("ENTER_CAR", 2.0) == "opener_mutex"
    assert lock.skip_reason("PARADE_PAD", 2.0) is None


def test_runtime_skips_sidecars_when_recap_pending() -> None:
    overlay = OverlaySettings(
        commentary=CommentarySettings(enabled=True, session_briefs=True),
        race_observer=RaceObserverSettings(grid_story=True),
    )
    runtime = OverlayRuntime(lambda: SimpleNamespace(overlay=overlay), None, OverlayBus())
    runtime.race_observer.stream.note_quali(4, 90.0)
    runtime._pending_derived_speech = [
        make_envelope(
            event_type="QUALI_RECAP",
            phase="RESULT",
            mode="RACE",
            priority=66,
        )
    ]
    calls: list[str] = []

    def _tick(*_args: object, **_kwargs: object) -> None:
        calls.append("brief")
        return None

    runtime.session_briefs.tick = _tick  # type: ignore[method-assign]
    runtime._collect_commentary_sidecars(_state(), 1.0)
    assert calls == []
    assert runtime.commentary is not None
