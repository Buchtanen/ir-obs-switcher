"""SpeechScheduler defer / TTL / interrupt policy unit tests."""

from __future__ import annotations

from irswitch.commentary.graph import load_sequence_graph
from irswitch.commentary.priorities import editorial_priority
from irswitch.commentary.scheduler import SpeechScheduler
from irswitch.commentary.tts import CommentaryUtterance
from irswitch.overlay.settings import CommentarySchedulerSettings


def _utt(event_type: str = "OVERTAKE", node_id: str = "overtake") -> CommentaryUtterance:
    graph = load_sequence_graph()
    node = graph.nodes.get(node_id) or next(iter(graph.nodes.values()))
    return CommentaryUtterance(
        node_id=node.id,
        locale="en",
        emotion="unknown",
        text="He takes the spot.",
        event_type=event_type,
        event_id="e1",
        correlation_id="c1",
        estimated_seconds=2.0,
        node=node,
        priority=80,
    )


def test_park_and_pop_by_priority() -> None:
    sched = SpeechScheduler(
        settings=CommentarySchedulerSettings(defer_enabled=True, max_deferred=8)
    )
    assert sched.park(_utt("HUNTING"), priority=20, now=1.0)
    # Lower-than-best is dropped; higher replaces the parked line.
    assert sched.park(_utt("OVERTAKE"), priority=80, now=1.1) is True
    assert len(sched) == 1
    assert sched.park(_utt("HUNTING"), priority=20, now=1.2) is False
    assert len(sched) == 1
    best = sched.pop_ready(2.0)
    assert best is not None
    assert best.utterance.event_type == "OVERTAKE"
    assert len(sched) == 0


def test_clear_drops_remainder_without_sequential_drain() -> None:
    sched = SpeechScheduler(
        settings=CommentarySchedulerSettings(defer_enabled=True, max_deferred=8)
    )
    # Force two items via internal heap (park itself keeps ≤1).
    assert sched.park(_utt("OVERTAKE"), priority=80, now=1.0)
    # Simulate a stale second entry still on the heap after pop.
    import heapq

    from irswitch.commentary.scheduler import DeferredSpeech, _HeapItem

    leftover = _utt("HUNTING")
    heapq.heappush(
        sched._heap,
        _HeapItem(
            sort_key=(-20, 99.0, 9),
            item=DeferredSpeech(utterance=leftover, priority=20, expires_at=99.0, parked_at=1.0),
        ),
    )
    best = sched.pop_ready(2.0)
    assert best is not None
    dropped = sched.clear()
    assert len(dropped) == 1
    assert dropped[0].utterance.event_type == "HUNTING"
    assert sched.pop_ready(3.0) is None


def test_ttl_expiry() -> None:
    sched = SpeechScheduler(
        settings=CommentarySchedulerSettings(defer_enabled=True, default_ttl_s=5.0)
    )
    sched.park(_utt(), priority=50, now=10.0)
    expired = sched.expire(16.0)
    assert len(expired) == 1
    assert sched.pop_ready(16.0) is None


def test_hard_interrupt_only_for_hero_order_change() -> None:
    off = SpeechScheduler(settings=CommentarySchedulerSettings(hard_interrupt=False))
    assert off.should_hard_interrupt("INCIDENT", current_event_type="HUNTING") is False
    assert off.should_hard_interrupt("POSITION_GAINED", current_event_type="HUNTING") is True
    on = SpeechScheduler(settings=CommentarySchedulerSettings(hard_interrupt=True))
    assert on.should_hard_interrupt("INCIDENT", current_event_type="FINISH") is False
    assert on.should_hard_interrupt("OVERTAKE", current_event_type="HUNTING") is False
    assert on.should_hard_interrupt("POSITION_LOST", current_event_type="HUNTING") is True
    assert on.should_hard_interrupt("POSITION_LOST", current_event_type="POSITION_LOST") is False
    assert on.should_hard_interrupt("POSITION_LOST", current_event_type="FINISH") is False


def test_editorial_priority_is_strict_and_orders_flags() -> None:
    assert editorial_priority("FINISH") > editorial_priority("STREAM_START")
    assert editorial_priority("STREAM_START") > editorial_priority(
        "SESSION_FLAG", {"branch": "red"}
    )
    assert editorial_priority("SESSION_FLAG", {"branch": "red"}) > editorial_priority(
        "SESSION_FLAG", {"branch": "checkered"}
    )
    assert editorial_priority("SESSION_FLAG", {"branch": "checkered"}) > editorial_priority(
        "SESSION_FLAG", {"branch": "yellow"}
    )
    assert editorial_priority("SESSION_FLAG", {"branch": "yellow"}) > editorial_priority(
        "SESSION_FLAG", {"branch": "green"}
    )
    assert editorial_priority("SESSION_FLAG", {"branch": "green"}) > editorial_priority("INCIDENT")
    assert editorial_priority("INCIDENT") > editorial_priority("OVERTAKE")
    assert editorial_priority("POSITION_LOST") > editorial_priority("HUNTED")
    assert editorial_priority("HUNTING") > editorial_priority("SECTOR_BEST")
    assert editorial_priority("SECTOR_SPLIT") > editorial_priority("LAP_COMPLETE")


def test_silence_due() -> None:
    sched = SpeechScheduler(settings=CommentarySchedulerSettings(max_silence_s=33.0))
    assert sched.silence_due(last_spoke_at=None, now=100.0) is False
    assert sched.silence_due(last_spoke_at=50.0, now=82.0) is False
    assert sched.silence_due(last_spoke_at=50.0, now=83.0) is True


def test_park_disabled_noop() -> None:
    sched = SpeechScheduler(settings=CommentarySchedulerSettings(defer_enabled=False))
    assert sched.park(_utt(), priority=80, now=1.0) is False
    assert len(sched) == 0
