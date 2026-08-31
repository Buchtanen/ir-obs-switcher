"""Stream SESSION_WRAP / SESSION_PREVIEW narrative."""

from __future__ import annotations

from irswitch.commentary.director import CommentaryDirector
from irswitch.commentary.tts import NullTtsSink
from irswitch.iracing.telemetry import extract_telemetry
from irswitch.overlay.models import RaceState
from irswitch.overlay.settings import CommentarySettings
from irswitch.race.narrative import StreamNarrativeFsm
from irswitch.race.observer import RaceObserver


def _snap(*, sub: str = "100", num: int = 0, track: str = "t1") -> object:
    return extract_telemetry(
        {
            "PlayerCarIdx": 0,
            "SubSessionID": sub,
            "SessionNum": num,
            "TrackID": track,
            "SessionState": 4,
            "SessionType": "Race",
        },
        timestamp=1.0,
    )


def _state(
    *,
    mode: str = "PRACTICE",
    finished: bool = False,
    checkered: bool = False,
    position: int = 3,
    sub: str = "100",
    num: int = 0,
) -> RaceState:
    return RaceState(
        connected=True,
        overlay_mode=mode,
        session_finished=finished,
        session_checkered=checkered,
        player_finished=finished,
        mute_field=finished,
        class_position=position,
        subsession_id=sub,
        session_num=num,
        track_id="t1",
    )


def test_first_session_has_no_preview_or_wrap() -> None:
    fsm = StreamNarrativeFsm()
    out = fsm.tick(_state(mode="PRACTICE"), 1.0, session_key="100:0:t1")
    assert out == []


def test_session_change_emits_wrap_then_preview() -> None:
    fsm = StreamNarrativeFsm()
    fsm.tick(_state(mode="PRACTICE", num=0), 1.0, session_key="100:0:t1")
    out = fsm.tick(_state(mode="QUALIFYING", num=1), 2.0, session_key="100:1:t1")
    assert [e.event_type for e in out] == ["SESSION_WRAP", "SESSION_PREVIEW"]
    assert out[0].metrics["mode"] == "PRACTICE"
    assert out[0].metrics["reason"] == "session_change"
    assert out[1].metrics["mode"] == "QUALIFYING"


def test_session_finished_emits_wrap_once() -> None:
    fsm = StreamNarrativeFsm()
    fsm.tick(_state(mode="RACE", finished=False), 1.0, session_key="100:2:t1")
    out = fsm.tick(_state(mode="RACE", finished=True, position=2), 2.0, session_key="100:2:t1")
    assert len(out) == 1
    assert out[0].event_type == "SESSION_WRAP"
    assert out[0].metrics["reason"] == "session_finished"
    assert out[0].metrics["position"] == 2
    # No duplicate wrap.
    assert fsm.tick(_state(mode="RACE", finished=True), 3.0, session_key="100:2:t1") == []


def test_on_track_checkered_does_not_wrap_until_finished() -> None:
    fsm = StreamNarrativeFsm()
    fsm.tick(_state(mode="QUALIFYING"), 1.0, session_key="100:1:t1")
    out = fsm.tick(
        _state(mode="QUALIFYING", checkered=True, finished=False),
        2.0,
        session_key="100:1:t1",
    )
    assert out == []
    wrap = fsm.tick(
        _state(mode="QUALIFYING", checkered=True, finished=True, position=2),
        4.0,
        session_key="100:1:t1",
    )
    assert [e.event_type for e in wrap] == ["SESSION_WRAP"]
    assert wrap[0].metrics["reason"] == "session_finished"


def test_pits_at_checkered_without_player_finished_is_silent() -> None:
    fsm = StreamNarrativeFsm()
    fsm.tick(_state(mode="RACE"), 1.0, session_key="100:2:t1")
    out = fsm.tick(
        _state(mode="RACE", checkered=True, finished=False, position=8),
        2.0,
        session_key="100:2:t1",
    )
    assert out == []


def test_finished_then_change_does_not_double_wrap() -> None:
    fsm = StreamNarrativeFsm()
    fsm.tick(_state(mode="PRACTICE", num=0), 1.0, session_key="100:0:t1")
    fsm.tick(_state(mode="PRACTICE", num=0, finished=True), 2.0, session_key="100:0:t1")
    out = fsm.tick(_state(mode="RACE", num=1), 3.0, session_key="100:1:t1")
    types = [e.event_type for e in out]
    assert types.count("SESSION_WRAP") == 0
    assert types == ["SESSION_PREVIEW"]


def test_observer_formats_and_drains_narrative() -> None:
    observer = RaceObserver()
    snap0 = _snap(num=0)
    observer.observe(snap0, _state(mode="PRACTICE", num=0), now=1.0)
    assert observer.take_derived_envelopes() == []
    snap1 = _snap(num=1)
    observer.observe(snap1, _state(mode="QUALIFYING", num=1), now=2.0)
    derived = observer.take_derived_envelopes()
    assert [e.event_type for e in derived] == ["SESSION_WRAP", "SESSION_PREVIEW"]
    wrap_text = observer.format_filler_text(derived[0], locale="en")
    preview_text = observer.format_filler_text(derived[1], locale="en")
    assert wrap_text is not None and "wrap" in wrap_text.lower()
    assert preview_text is not None and "next" in preview_text.lower()


def test_observer_formats_checkered_fallback() -> None:
    observer = RaceObserver()
    from irswitch.events.envelope import make_envelope

    env = make_envelope(
        event_type="SESSION_CHECKERED",
        phase="RESULT",
        mode="QUALIFYING",
        priority=56,
        monotonic_ms=1,
        metrics={
            "kind": "session_checkered",
            "modeLabel": "Qualifying",
            "modeLabelCs": "kvalifikace",
        },
    )
    en = observer.format_filler_text(env, locale="en")
    cs = observer.format_filler_text(env, locale="cs")
    assert en is not None and "Checkered" in en
    assert cs is not None and "Šachovnice" in cs


def test_director_gates_narrative_when_session_briefs_off() -> None:
    observer = RaceObserver()
    director = CommentaryDirector.from_defaults(
        settings=CommentarySettings(enabled=True, session_briefs=False, use_hr_emotion=False),
        sink=NullTtsSink(),
    )
    director.filler_formatter = lambda env: observer.format_filler_text(env, locale="en")
    from irswitch.events.envelope import make_envelope

    env = make_envelope(
        event_type="SESSION_PREVIEW",
        phase="RESULT",
        mode="RACE",
        priority=52,
        monotonic_ms=1000,
        metrics={"kind": "session_preview", "mode": "RACE", "modeLabel": "Race"},
    )
    assert director.observe([env], None, 1.0) is None
    assert director.decisions(1)[-1]["reason"] == "session_briefs_disabled"


def test_director_speaks_preview_when_session_briefs_on() -> None:
    observer = RaceObserver()
    director = CommentaryDirector.from_defaults(
        settings=CommentarySettings(enabled=True, session_briefs=True, use_hr_emotion=False),
        sink=NullTtsSink(),
    )
    director.filler_formatter = lambda env: observer.format_filler_text(env, locale="en")
    from irswitch.events.envelope import make_envelope

    env = make_envelope(
        event_type="SESSION_PREVIEW",
        phase="RESULT",
        mode="QUALIFYING",
        priority=52,
        monotonic_ms=1000,
        metrics={"kind": "session_preview", "mode": "QUALIFYING", "modeLabel": "Qualifying"},
    )
    spoken = director.observe([env], None, 1.0)
    assert spoken is not None
    assert spoken.event_type == "SESSION_PREVIEW"
    # Some graph variants are slot-light (no {mode}); never invent Race here.
    assert "Race" not in spoken.text
    if "{mode}" in spoken.text or "Qualifying" in spoken.text:
        assert "Qualifying" in spoken.text
