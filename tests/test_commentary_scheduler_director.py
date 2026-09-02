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


def _position(*, now_ms: int = 10100) -> object:
    return make_envelope(
        event_type="POSITION_GAINED",
        phase="RESULT",
        mode="RACE",
        priority=95,
        monotonic_ms=now_ms,
        metrics={"position": 4},
    )


def test_busy_defers_instead_of_drop() -> None:
    director = _director(defer=True)
    first = director.observe([_overtake()], None, 10.0)
    assert first is not None
    assert director.observe([_overtake(now_ms=10100)], None, 10.1) is None
    assert director.decisions(1)[-1]["reason"] == "deferred"
    # Still busy or still in global cooldown — no flush yet.
    mid = min(director._busy_until, director._global_ready_at) - 0.01
    if mid > 10.0:
        assert director.tick(mid) is None
    flush_at = max(director._busy_until, director._global_ready_at) + 0.05
    spoken = director.tick(flush_at)
    assert spoken is not None
    assert director.decisions(1)[-1]["reason"] == "spoken_deferred"
    assert spoken.past_framing is True


def test_busy_without_defer_still_skips() -> None:
    director = _director(defer=False)
    assert director.observe([_overtake()], None, 10.0) is not None
    assert director.observe([_overtake(now_ms=10100)], None, 10.1) is None
    assert director.decisions(1)[-1]["reason"] == "busy"


def test_hero_order_change_interrupts_but_incident_does_not() -> None:
    director = _director(defer=True, hard_interrupt=True)
    assert director.observe([_overtake()], None, 10.0) is not None
    assert director.observe([_incident()], None, 10.1) is None
    assert director.decisions(1)[-1]["reason"] == "deferred"
    spoken = director.observe([_position()], None, 10.2)
    assert spoken is not None
    assert spoken.event_type == "POSITION_GAINED"
    reasons = [d["reason"] for d in director.decisions(5)]
    assert "interrupted" in reasons


def test_observed_busy_defers_after_estimate_expires() -> None:
    """#180: sink.is_busy keeps director busy even when estimate elapsed."""
    director = _director(defer=True)
    sink = director.sink
    assert isinstance(sink, NullTtsSink)
    first = director.observe([_overtake()], None, 10.0)
    assert first is not None
    sink.force_busy = True
    later = max(director._busy_until, director._global_ready_at) + 1.0
    assert director.observe([_overtake(now_ms=20000)], None, later) is None
    assert director.decisions(1)[-1]["reason"] == "deferred"
    assert director.tick(later) is None
    sink.force_busy = False
    spoken = director.tick(later + 0.01)
    assert spoken is not None
    assert director.decisions(1)[-1]["reason"] == "spoken_deferred"
    assert spoken.past_framing is True


def test_deferred_flush_speaks_one_not_whole_queue() -> None:
    director = _director(defer=True)
    first = director.observe([_overtake()], None, 10.0)
    assert first is not None
    # Two busy arrivals: lower then higher — only best stays parked.
    assert (
        director.observe(
            [
                make_envelope(
                    event_type="HUNTING",
                    phase="ENTER",
                    mode="RACE",
                    priority=40,
                    monotonic_ms=10100,
                    metrics={},
                )
            ],
            None,
            10.1,
        )
        is None
    )
    assert director.decisions(1)[-1]["reason"] in {"deferred", "deferred_dropped"}
    assert director.observe([_incident(now_ms=10200)], None, 10.2) is None
    assert director.decisions(1)[-1]["reason"] == "deferred"
    flush_at = max(director._busy_until, director._global_ready_at) + 0.05
    spoken = director.tick(flush_at)
    assert spoken is not None
    assert spoken.event_type == "INCIDENT"
    assert director.decisions(1)[-1]["reason"] == "spoken_deferred"
    # No second deferred flush — queue must be empty.
    assert director.tick(flush_at + 5.0) is None
    assert len(director._scheduler) == 0
