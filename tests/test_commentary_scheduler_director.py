"""Director + SpeechScheduler integration (defer while busy)."""

from __future__ import annotations

from irswitch.commentary.director import CommentaryDirector
from irswitch.commentary.tts import NullTtsSink
from irswitch.events.envelope import make_envelope
from irswitch.overlay.settings import CommentarySchedulerSettings, CommentarySettings


def _director(*, defer: bool = True, hard_interrupt: bool = False) -> CommentaryDirector:
    sink = NullTtsSink()
    settings = CommentarySettings(
        enabled=True,
        cooldown_s=4.0,
        use_hr_emotion=False,
        scheduler=CommentarySchedulerSettings(
            defer_enabled=defer,
            hard_interrupt=hard_interrupt,
            default_ttl_s=30.0,
            incident_ttl_s=45.0,
            max_silence_s=33.0,
        ),
    )
    return CommentaryDirector.from_defaults(settings=settings, sink=sink)


def _overtake(*, now_ms: int = 10000) -> object:
    return make_envelope(
        event_type="OVERTAKE",
        phase="RESULT",
        mode="RACE",
        priority=80,
        monotonic_ms=now_ms,
        metrics={"position": 5},
    )


def _incident(*, now_ms: int = 10100) -> object:
    return make_envelope(
        event_type="INCIDENT",
        phase="RESULT",
        mode="RACE",
        priority=90,
        monotonic_ms=now_ms,
        metrics={"value": 2},
    )


def test_busy_defers_instead_of_drop() -> None:
    director = _director(defer=True)
    first = director.observe([_overtake()], None, 10.0)
    assert first is not None
    assert director.observe([_overtake(now_ms=10100)], None, 10.1) is None
    assert director.decisions(1)[-1]["reason"] == "deferred"
    # After busy window, tick/observe flushes deferred.
    after = 10.0 + first.estimated_seconds + 0.05
    # Still inside global cooldown — should not flush yet.
    assert director.tick(after) is None
    after_cd = 10.0 + 4.0 + 0.05
    spoken = director.tick(after_cd)
    assert spoken is not None
    assert director.decisions(1)[-1]["reason"] == "spoken_deferred"
    assert spoken.past_framing is True


def test_busy_without_defer_still_skips() -> None:
    director = _director(defer=False)
    assert director.observe([_overtake()], None, 10.0) is not None
    assert director.observe([_overtake(now_ms=10100)], None, 10.1) is None
    assert director.decisions(1)[-1]["reason"] == "busy"


def test_hard_interrupt_clears_busy_for_incident() -> None:
    director = _director(defer=True, hard_interrupt=True)
    assert director.observe([_overtake()], None, 10.0) is not None
    spoken = director.observe([_incident()], None, 10.2)
    assert spoken is not None
    assert spoken.event_type == "INCIDENT"
    reasons = [d["reason"] for d in director.decisions(5)]
    assert "interrupted" in reasons
