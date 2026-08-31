"""Race SESSION_FLAG observer: yellow / green / checkered rising edges."""

from __future__ import annotations

from irswitch.commentary.director import CommentaryDirector
from irswitch.commentary.tts import NullTtsSink
from irswitch.iracing.session_flags import FLAG_BITS, decode_session_flags
from irswitch.iracing.telemetry import extract_telemetry
from irswitch.overlay.models import RaceState
from irswitch.overlay.settings import CommentarySettings, RaceObserverSettings
from irswitch.race.flags import FLAG_COOLDOWN_S, SessionFlagFsm, active_flag_kinds
from irswitch.race.observer import RaceObserver


def _state(*, names: tuple[str, ...] = (), mode: str = "RACE", **overrides: object) -> RaceState:
    raw = 0
    for name in names:
        raw |= FLAG_BITS[name]
    decoded = decode_session_flags(raw)
    payload: dict[str, object] = {
        "connected": True,
        "overlay_mode": mode,
        "session_flags": raw,
        "session_flag_names": decoded.names,
        "flag_checkered": decoded.checkered,
        "flag_yellow": decoded.yellow,
        "flag_green": decoded.green,
        "player_finished": False,
        "session_checkered": False,
        "subsession_id": "sub",
        "session_num": 1,
    }
    payload.update(overrides)
    return RaceState(**payload)  # type: ignore[arg-type]


def test_active_kinds_coalesce_yellow_family() -> None:
    assert active_flag_kinds(("yellow",)) == frozenset({"yellow"})
    assert active_flag_kinds(("cautionWaving", "yellowWaving")) == frozenset({"yellow"})
    assert active_flag_kinds(("startGo", "startSet")) == frozenset()
    assert active_flag_kinds(("greenHeld",)) == frozenset()


def test_rising_yellow_once_then_hold_silent() -> None:
    fsm = SessionFlagFsm()
    assert fsm.tick(_state(), 1.0, enabled=True) == []
    out = fsm.tick(_state(names=("yellow",)), 1.2, enabled=True)
    assert len(out) == 1
    assert out[0].event_type == "SESSION_FLAG"
    assert out[0].metrics["kind"] == "yellow"
    assert out[0].metrics["branch"] == "yellow"
    assert out[0].event_type != "FINISH"
    assert fsm.tick(_state(names=("yellow",)), 1.4, enabled=True) == []
    assert fsm.tick(_state(names=("yellow",)), 2.0, enabled=True) == []


def test_yellow_and_caution_same_tick_one_event() -> None:
    fsm = SessionFlagFsm()
    fsm.tick(_state(), 1.0, enabled=True)
    out = fsm.tick(_state(names=("yellow", "caution")), 1.2, enabled=True)
    assert len(out) == 1
    assert out[0].metrics["kind"] == "yellow"


def test_start_lights_ignored() -> None:
    fsm = SessionFlagFsm()
    fsm.tick(_state(), 1.0, enabled=True)
    assert fsm.tick(_state(names=("startHidden",)), 1.1, enabled=True) == []
    assert fsm.tick(_state(names=("startReady", "startSet")), 1.2, enabled=True) == []
    assert fsm.tick(_state(names=("startGo",)), 1.3, enabled=True) == []


def test_checkered_bit_is_session_flag_not_finish() -> None:
    fsm = SessionFlagFsm()
    fsm.tick(_state(), 1.0, enabled=True)
    out = fsm.tick(_state(names=("checkered",)), 1.2, enabled=True)
    assert out[0].event_type == "SESSION_FLAG"
    assert out[0].metrics["kind"] == "checkered"
    assert out[0].event_type != "FINISH"
    assert out[0].event_type != "SESSION_WRAP"


def test_per_flag_cooldown() -> None:
    fsm = SessionFlagFsm()
    fsm.tick(_state(), 1.0, enabled=True)
    assert fsm.tick(_state(names=("green",)), 1.2, enabled=True)
    fsm.tick(_state(), 1.4, enabled=True)
    assert fsm.tick(_state(names=("green",)), 5.0, enabled=True) == []
    fsm.tick(_state(), 5.2, enabled=True)
    again = fsm.tick(_state(names=("green",)), 1.2 + FLAG_COOLDOWN_S + 0.1, enabled=True)
    assert len(again) == 1
    assert again[0].metrics["kind"] == "green"


def test_disabled_and_non_race_do_not_speak() -> None:
    fsm = SessionFlagFsm()
    fsm.tick(_state(), 1.0, enabled=False)
    assert fsm.tick(_state(names=("yellow",)), 1.2, enabled=False) == []
    other = SessionFlagFsm()
    other.tick(_state(mode="PRACTICE"), 1.0, enabled=True)
    assert other.tick(_state(names=("yellow",), mode="PRACTICE"), 1.2, enabled=True) == []
    assert other.tick(_state(names=("yellow",), mode="QUALIFYING"), 1.4, enabled=True) == []


def test_observer_checkered_does_not_wrap_or_finish() -> None:
    snap = extract_telemetry(
        {
            "PlayerCarIdx": 0,
            "SessionState": 4,
            "SessionNum": 1,
        },
        timestamp=1.0,
    )
    observer = RaceObserver(settings=RaceObserverSettings(flags=True))
    observer.observe(snap, _state(), now=1.0)
    assert observer.take_derived_envelopes() == []
    observer.observe(snap, _state(names=("checkered",)), now=1.2)
    derived = observer.take_derived_envelopes()
    types = [env.event_type for env in derived]
    assert types == ["SESSION_FLAG"]
    assert derived[0].metrics["kind"] == "checkered"
    assert "FINISH" not in types
    assert "SESSION_WRAP" not in types


def test_observer_default_flag_gate_off() -> None:
    snap = extract_telemetry({"PlayerCarIdx": 0, "SessionState": 4}, timestamp=1.0)
    observer = RaceObserver()
    observer.observe(snap, _state(), now=1.0)
    observer.observe(snap, _state(names=("yellow",)), now=1.2)
    assert observer.take_derived_envelopes() == []


def test_formatter_and_director_speak_yellow() -> None:
    observer = RaceObserver(settings=RaceObserverSettings(flags=True))
    director = CommentaryDirector.from_defaults(
        settings=CommentarySettings(enabled=True, cooldown_s=0.1, use_hr_emotion=False),
        sink=NullTtsSink(),
    )
    director.filler_formatter = lambda env: observer.format_filler_text(env, locale="en")
    fsm = SessionFlagFsm()
    fsm.tick(_state(), 1.0, enabled=True)
    env = fsm.tick(_state(names=("yellow",)), 1.2, enabled=True)[0]
    text = observer.format_filler_text(env, locale="en")
    assert text is not None
    assert "Caution" in text
    spoken = director.observe([env], None, 10.0)
    assert spoken is not None
    assert spoken.event_type == "SESSION_FLAG"
    cs = observer.format_filler_text(env, locale="cs")
    assert cs is not None
    assert "žlutá" in cs.lower()
