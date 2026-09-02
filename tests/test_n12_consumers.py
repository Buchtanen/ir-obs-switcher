"""N12 peer consumer domain and failure-isolation tests."""

from __future__ import annotations

import time

import pytest

from irswitch.commentary.consumer import CommentaryConsumer, _spoken_irating
from irswitch.commentary.director import CommentaryDirector
from irswitch.commentary.graph import parse_sequence_graph
from irswitch.commentary.tts import NullTtsSink
from irswitch.events.async_fanout import AsyncEventFanout
from irswitch.events.envelope import make_envelope
from irswitch.events.stream import (
    CONTEXT_SCHEMA_VERSION,
    ConfigUpdate,
    FillerResult,
    FrozenAcceptedEventBatch,
    SessionReset,
    freeze_accepted_event,
    freeze_config,
    freeze_context,
)
from irswitch.overlay.bus import OverlayBus
from irswitch.overlay.consumer import OverlayConsumer
from irswitch.overlay.settings import CommentarySchedulerSettings, CommentarySettings
from irswitch.race.ministory import MiniStoryRegistry


def _graph():
    return parse_sequence_graph(
        {
            "version": 1,
            "locales": ["en"],
            "nodes": {
                "lap": {
                    "family": "lap",
                    "event_types": ["LAP_COMPLETE"],
                    "phases": ["RESULT"],
                    "speak_priority": 50,
                    "cooldown_s": 0,
                    "slots": [],
                    "hr_states": ["unknown"],
                    "variants": {"en": {"neutral": ["A lap is complete."]}},
                }
            },
            "edges": [],
        }
    )


def _context(*, version: int = 1, session_id: str = "session") -> bytes:
    return freeze_context(
        {
            "schema_version": CONTEXT_SCHEMA_VERSION,
            "version": version,
            "session_id": session_id,
            "captured_monotonic_ms": int(time.monotonic() * 1000),
            "identity": {},
            "race": {},
            "bio": {"status": "connected", "connected": True, "hr_state": "focused"},
            "story": {"hero": {"speakable_names": ["Alex"]}},
            "situation": {},
            "config": {},
        }
    )


def _batch(
    *,
    stream_sequence: int = 1,
    event_sequence: int = 1,
    audience: tuple[str, ...] = ("overlay", "commentary"),
    accepted_ms: int | None = None,
    overlay_wire: dict | None = None,
    story_payload: dict | None = None,
    phase: str = "RESULT",
) -> FrozenAcceptedEventBatch:
    envelope = make_envelope(
        event_type="LAP_COMPLETE",
        phase=phase,
        mode="RACE",
        event_id=f"session:LAP_COMPLETE:{event_sequence}",
        sequence=event_sequence,
        session_id="session",
        priority=50,
        monotonic_ms=int(time.monotonic() * 1000),
        dedupe_key="lap",
        correlation_id=f"lap:{event_sequence}",
    )
    accepted = freeze_accepted_event(
        envelope,
        audiences=audience,  # type: ignore[arg-type]
        source="event_engine",
        source_ordinal=0,
        overlay_payload=overlay_wire,
        story_payload=story_payload,
    )
    return FrozenAcceptedEventBatch(
        stream_sequence,
        "session",
        event_sequence,
        accepted_ms if accepted_ms is not None else int(time.monotonic() * 1000),
        1,
        _context(),
        (accepted,),
    )


@pytest.mark.asyncio
async def test_overlay_consumer_uses_frozen_public_wire_and_discards_commentary_only() -> None:
    class _RecordingBus(OverlayBus):
        def __init__(self) -> None:
            super().__init__()
            self.wires: list[dict] = []

        async def publish_event(self, envelope: dict) -> None:
            self.wires.append(envelope)
            await super().publish_event(envelope)

    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("overlay")
    bus = _RecordingBus()
    consumer = OverlayConsumer(subscription, bus)
    custom_wire = {"type": "event", "name": "lap_complete", "format": "legacy"}

    await consumer.handle(_batch(overlay_wire=custom_wire))
    assert bus.wires[-1] == custom_wire

    commentary_only = _batch(
        stream_sequence=2,
        event_sequence=2,
        audience=("commentary",),
    )
    before = len(bus.wires)
    await consumer.handle(commentary_only)
    assert len(bus.wires) == before


@pytest.mark.asyncio
async def test_overlay_consumer_reduces_story_lease_until_tts_completion() -> None:
    class _RecordingBus(OverlayBus):
        def __init__(self) -> None:
            super().__init__()
            self.wires: list[dict] = []

        async def publish_event(self, envelope: dict) -> None:
            self.wires.append(envelope)
            await super().publish_event(envelope)

    story = {
        "storyId": "story:0:1",
        "storyRevision": 1,
        "runEpoch": 0,
        "heroOrderRevision": 0,
        "correlationId": "lap:1",
        "eventType": "LAP_COMPLETE",
        "state": "ready",
    }
    wire = {
        "type": "event",
        "format": "v4",
        "eventType": "LAP_COMPLETE",
        "phase": "RESULT",
        "correlationId": "lap:1",
        "metrics": {"lap": 4, "lapTime": 61.2},
        "presentation": {"variant": "lap_complete"},
    }
    bus = _RecordingBus()
    consumer = OverlayConsumer(AsyncEventFanout().subscribe("overlay"), bus)
    await consumer.handle(_batch(overlay_wire=wire, story_payload=story))
    assert bus.wires[-1]["miniStory"]["storyId"] == "story:0:1"

    consumer.enqueue_story_transition({**story, "action": "building", "reason": "tts_queued"})
    await consumer.apply_story_transitions()
    assert bus.active_stories_v4[0]["miniStory"]["state"] == "building"

    consumer.enqueue_story_transition({**story, "action": "speaking", "reason": "tts_started"})
    await consumer.apply_story_transitions()
    assert bus.active_stories_v4[0]["miniStory"]["state"] == "speaking"

    # The latest producer context can still contain the raw source relation.
    # Completion must tombstone that correlation until a genuinely new story arrives.
    consumer._source_stories = [wire]
    consumer.enqueue_story_transition({**story, "action": "completed", "reason": "tts_finished"})
    await consumer.apply_story_transitions()
    assert bus.active_stories_v4 == []


@pytest.mark.asyncio
async def test_source_exit_resolves_but_does_not_remove_building_story_lease() -> None:
    story = {
        "storyId": "story:0:1",
        "storyRevision": 1,
        "runEpoch": 0,
        "heroOrderRevision": 0,
        "correlationId": "lap:1",
        "eventType": "LAP_COMPLETE",
        "state": "ready",
    }
    enter = {
        "type": "event",
        "format": "v4",
        "eventType": "LAP_COMPLETE",
        "phase": "ENTER",
        "correlationId": "lap:1",
        "metrics": {"lap": 4},
        "presentation": {"variant": "lap_complete"},
    }
    bus = OverlayBus()
    consumer = OverlayConsumer(AsyncEventFanout().subscribe("overlay"), bus)
    await consumer.handle(_batch(overlay_wire=enter, story_payload=story, phase="ENTER"))
    consumer.enqueue_story_transition({**story, "action": "building"})
    await consumer.apply_story_transitions()

    resolved = {**story, "storyRevision": 2, "state": "resolved"}
    exit_wire = {**enter, "phase": "EXIT", "metrics": {"lap": 4, "lapTime": 61.2}}
    await consumer.handle(
        _batch(
            stream_sequence=2,
            event_sequence=2,
            overlay_wire=exit_wire,
            story_payload=resolved,
            phase="EXIT",
        )
    )

    assert bus.active_stories_v4[0]["phase"] == "RESULT"
    assert bus.active_stories_v4[0]["miniStory"] == {**resolved, "state": "resolved"}


@pytest.mark.asyncio
async def test_overlay_consumer_ignores_stale_story_revision_and_reset_clears_lease() -> None:
    story = {
        "storyId": "story:2:7",
        "storyRevision": 3,
        "runEpoch": 2,
        "heroOrderRevision": 1,
        "correlationId": "lap:1",
        "eventType": "LAP_COMPLETE",
        "state": "ready",
    }
    wire = {
        "type": "event",
        "format": "v4",
        "eventType": "LAP_COMPLETE",
        "phase": "RESULT",
        "correlationId": "lap:1",
        "metrics": {},
        "presentation": {"variant": "lap_complete"},
    }
    bus = OverlayBus()
    consumer = OverlayConsumer(AsyncEventFanout().subscribe("overlay"), bus)
    await consumer.handle(_batch(overlay_wire=wire, story_payload=story))
    consumer.enqueue_story_transition({**story, "action": "speaking"})
    consumer.enqueue_story_transition({**story, "storyRevision": 2, "action": "completed"})
    await consumer.apply_story_transitions()
    assert bus.active_stories_v4[0]["miniStory"]["state"] == "speaking"

    await consumer.handle(SessionReset("session", "next", "session_changed", 9))
    assert bus.active_stories_v4 == []


@pytest.mark.asyncio
async def test_commentary_consumer_thaws_and_speaks_without_overlay_bus() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("commentary")
    subscription.replace_latest_context(_context())
    sink = NullTtsSink()
    settings = CommentarySettings(enabled=True, cooldown_s=0)
    director = CommentaryDirector(graph=_graph(), settings=settings, sink=sink)
    consumer = CommentaryConsumer(subscription, director, lambda: (settings, "en"))

    await consumer.handle(_batch())

    assert [item.text for item in sink.spoken] == ["A lap is complete."]
    assert director.hero_names() == ("Alex",)


@pytest.mark.asyncio
async def test_commentary_consumer_adopts_producer_assigned_story_token() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("commentary")
    subscription.replace_latest_context(_context())
    sink = NullTtsSink()
    settings = CommentarySettings(enabled=True, cooldown_s=0)
    director = CommentaryDirector(graph=_graph(), settings=settings, sink=sink)
    consumer = CommentaryConsumer(subscription, director, lambda: (settings, "en"))
    story = {
        "storyId": "story:0:41",
        "storyRevision": 1,
        "runEpoch": 0,
        "heroOrderRevision": 0,
        "correlationId": "lap:1",
        "eventType": "LAP_COMPLETE",
        "state": "ready",
    }

    await consumer.handle(_batch(audience=("commentary",), story_payload=story))

    assert sink.spoken[0].story_token is not None
    assert sink.spoken[0].story_token.story_id == "story:0:41"


def test_shared_producer_order_revision_still_interrupts_commentary_consumer() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("commentary")
    subscription.replace_latest_context(_context())
    sink = NullTtsSink(force_busy=True)
    settings = CommentarySettings(enabled=True, cooldown_s=0)
    director = CommentaryDirector(graph=_graph(), settings=settings, sink=sink)
    registry = MiniStoryRegistry()
    consumer = CommentaryConsumer(
        subscription,
        director,
        lambda: (settings, "en"),
        story_registry=registry,
    )
    registry.observe_context({"session_id": "session", "race": {"class_position": 5}})
    registry.observe_context({"session_id": "session", "race": {"class_position": 4}})

    consumer._idle_tick()

    assert sink.interrupted == 1


def test_context_bindings_require_exact_driver_identity_and_localize_situation() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("commentary")
    settings = CommentarySettings(enabled=True)
    consumer = CommentaryConsumer(
        subscription,
        CommentaryDirector(graph=_graph(), settings=settings, sink=NullTtsSink()),
        lambda: (settings, "en"),
    )
    envelope = make_envelope(
        event_type="HUNTING",
        target={"carId": "8"},
        metrics={"targetCarIdx": 8},
    )
    profile = {
        "session_id": "session",
        "car_idx": 8,
        "user_id": 80,
        "identity_epoch": 2,
        "i_rating": 2345,
        "safety_rating": "A 3.42",
        "car_name": "GT3",
        "nationality": None,
        "start_position": 4,
    }
    context = {
        "race": {"player_car_idx": 7},
        "story": {"driver_profiles": {"8": profile}},
        "situation": {
            "current_lap": 12,
            "total_laps": 30,
            "laps_remaining": 18,
            "race_phase": "middle",
        },
    }

    consumer._apply_context_bindings(envelope, context, context)

    assert envelope.metrics["target_irating"] == "2.3 thousand"
    assert envelope.metrics["target_car"] == "GT3"
    assert envelope.metrics["target_nationality"] is None
    assert envelope.metrics["lap_context"] == "lap 12 of 30"
    assert envelope.metrics["race_phase"] == "middle phase"

    changed = {
        **context,
        "story": {"driver_profiles": {"8": {**profile, "user_id": 81, "identity_epoch": 3}}},
    }
    rejected = make_envelope(event_type="HUNTING", target={"carId": "8"})
    consumer._apply_context_bindings(rejected, context, changed)
    assert "target_car" not in rejected.metrics
    assert _spoken_irating(2345, "cs") == "2,3 tisíce"


@pytest.mark.asyncio
async def test_config_update_uses_frozen_snapshot_not_live_runtime_lookup() -> None:
    fanout = AsyncEventFanout()
    initial = CommentarySettings(enabled=False)
    live = {"settings": initial, "language": "en", "reads": 0}

    def get_settings():
        live["reads"] += 1
        return live["settings"], live["language"]

    director = CommentaryDirector(graph=_graph(), settings=initial, sink=NullTtsSink())
    consumer = CommentaryConsumer(fanout.subscribe("commentary"), director, get_settings)
    live["settings"] = CommentarySettings(enabled=False, cooldown_s=99)
    live["language"] = "en"
    frozen = freeze_config(
        {
            "generation": 2,
            "language": "cs",
            "commentary": {
                **initial.__dict__,
                "enabled": True,
                "cooldown_s": 1.5,
                "scheduler": initial.scheduler.__dict__,
            },
        }
    )

    await consumer.handle(ConfigUpdate(2, frozen, 1))

    assert live["reads"] == 1
    assert director.settings.enabled is True
    assert director.settings.cooldown_s == 1.5
    assert director.language == "cs"


@pytest.mark.asyncio
async def test_commentary_consumer_uses_event_time_ttl_and_is_idempotent() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("commentary")
    subscription.replace_latest_context(_context())
    sink = NullTtsSink()
    settings = CommentarySettings(
        enabled=True,
        cooldown_s=0,
        scheduler=CommentarySchedulerSettings(default_ttl_s=1.0),
    )
    director = CommentaryDirector(graph=_graph(), settings=settings, sink=sink)
    consumer = CommentaryConsumer(subscription, director, lambda: (settings, "en"))
    expired = _batch(accepted_ms=int((time.monotonic() - 2.0) * 1000))

    await consumer.handle(expired)
    await consumer.handle(expired)

    assert sink.spoken == []
    assert consumer.expired == 1
    assert consumer.duplicates == 1
    assert [item["reason"] for item in director.decisions()[-2:]] == [
        "event_expired",
        "duplicate_event",
    ]


@pytest.mark.asyncio
async def test_reset_clears_duplicate_ledger() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("commentary")
    subscription.replace_latest_context(_context())
    sink = NullTtsSink()
    settings = CommentarySettings(enabled=True, cooldown_s=0)
    director = CommentaryDirector(graph=_graph(), settings=settings, sink=sink)
    consumer = CommentaryConsumer(subscription, director, lambda: (settings, "en"))
    batch = _batch()

    await consumer.handle(batch)
    await consumer.handle(SessionReset("session", "session", "test", 2))
    await consumer.handle(
        FrozenAcceptedEventBatch(
            3,
            batch.session_id,
            2,
            batch.accepted_monotonic_ms,
            batch.context_version,
            batch.context_payload,
            batch.events,
        )
    )

    assert len(sink.spoken) == 2


def test_filler_request_is_bounded_and_completed_by_typed_result() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("commentary")
    subscription.replace_latest_context(_context())
    settings = CommentarySettings(enabled=True)
    director = CommentaryDirector(graph=_graph(), settings=settings, sink=NullTtsSink())
    consumer = CommentaryConsumer(subscription, director, lambda: (settings, "en"))

    assert consumer._request_filler(time.monotonic()) is None
    assert consumer._request_filler(time.monotonic()) is None
    request = consumer.take_filler_request()
    assert request is not None
    consumer.complete_filler(FillerResult(request.request_id, "no_fact"))
    assert consumer.status_snapshot()["fillerOutstanding"] is False
