"""N12 peer consumer domain and failure-isolation tests."""

from __future__ import annotations

import time
from dataclasses import asdict

import pytest

from irswitch.commentary.consumer import CommentaryConsumer, _spoken_irating
from irswitch.commentary.director import CommentaryDirector
from irswitch.commentary.graph import load_sequence_graph, parse_sequence_graph
from irswitch.commentary.prepared_filler import (
    PreparedFillerHealth,
    build_prepared_filler_plans,
)
from irswitch.commentary.tts import NullTtsSink
from irswitch.events.async_fanout import AsyncEventFanout
from irswitch.events.envelope import make_envelope
from irswitch.events.stream import (
    CONTEXT_SCHEMA_VERSION,
    ConfigUpdate,
    FillerResult,
    FrozenAcceptedEventBatch,
    SessionReset,
    SessionSequenceAllocator,
    freeze_accepted_event,
    freeze_config,
    freeze_context,
    thaw_context,
)
from irswitch.overlay.bus import OverlayBus
from irswitch.overlay.consumer import OverlayConsumer
from irswitch.overlay.settings import (
    CommentarySchedulerSettings,
    CommentarySettings,
    PreparedFillerSettings,
)
from irswitch.race.editorial_stage import EditorialStage, EditorialStageFeedback
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


def _prepared_context(*, stage: str = "STREAM_LOBBY_INTRO") -> bytes:
    return freeze_context(
        {
            "schema_version": CONTEXT_SCHEMA_VERSION,
            "version": 1,
            "session_id": "session",
            "captured_monotonic_ms": int(time.monotonic() * 1000),
            "identity": {"overlay_mode": "RACE"},
            "race": {},
            "bio": {"status": "connected", "connected": True, "hr_state": "focused"},
            "story": {},
            "situation": {},
            "editorial": {
                "stage": stage,
                "stage_epoch": 1,
                "stream_epoch": 1,
                "track_name": "Spa",
            },
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
    exit_wire = {
        **enter,
        "eventId": "session:LAP_COMPLETE:2",
        "sequence": 2,
        "phase": "EXIT",
        "metrics": {"lap": 4, "lapTime": 61.2},
    }
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
    assert bus.active_stories_v4[0]["sequence"] == 2
    assert bus.active_stories_v4[0]["eventId"] == "session:LAP_COMPLETE:2"


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
async def test_active_prepared_filler_reaches_tts_and_records_exposure() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("commentary")
    subscription.replace_latest_context(_prepared_context())
    sink = NullTtsSink()
    settings = CommentarySettings(
        enabled=True,
        cooldown_s=0,
        graph_runtime_mode="active",
        prepared_filler=PreparedFillerSettings(mode="active"),
    )
    stages: list[EditorialStageFeedback] = []
    director = CommentaryDirector(graph=load_sequence_graph(), settings=settings, sink=sink)
    consumer = CommentaryConsumer(
        subscription,
        director,
        lambda: (settings, "en"),
        prepared_stage_hook=stages.append,
    )
    context = thaw_context(_prepared_context())
    plan = build_prepared_filler_plans(context, "en")[0]
    consumer.prepared_filler.buffer.reconcile([plan])
    consumer.prepared_filler.buffer.merge(
        plan,
        [
            "Spa hosts this race. The stream is ready.",
            "This race comes from Spa. We are ready to go.",
            "Welcome to Spa for the race. The broadcast is live.",
        ],
    )
    consumer.graph_runtime.reset(
        run_epoch=0, now=time.monotonic() - settings.scheduler.max_silence_s
    )

    envelope = consumer._request_filler(time.monotonic())
    assert envelope is not None
    utterance = director._utterance_from_formatter(envelope)
    assert utterance is not None and utterance.prepared
    sink.enqueue(utterance)
    consumer._drain_prepared_lifecycle()

    next_envelope = consumer._request_filler(time.monotonic())
    assert next_envelope is not None
    assert next_envelope.metrics["preparedVariantId"] != envelope.metrics["preparedVariantId"]
    assert [item.stage for item in stages] == [EditorialStage.STREAM_LOBBY_INTRO]
    assert stages[0].stream_epoch == 1
    assert stages[0].stage_epoch == 1
    assert consumer.take_filler_request() is None
    await consumer.prepared_filler.close()


@pytest.mark.asyncio
async def test_active_prepared_filler_uses_existing_graph_runtime() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("commentary")
    subscription.replace_latest_context(_prepared_context())
    sink = NullTtsSink()
    settings = CommentarySettings(
        enabled=True,
        cooldown_s=0,
        graph_runtime_mode="active",
        prepared_filler=PreparedFillerSettings(mode="active"),
    )
    director = CommentaryDirector(graph=load_sequence_graph(), settings=settings, sink=sink)
    consumer = CommentaryConsumer(subscription, director, lambda: (settings, "en"))
    plan = build_prepared_filler_plans(thaw_context(_prepared_context()), "en")[0]
    consumer.prepared_filler.buffer.reconcile([plan])
    consumer.prepared_filler.buffer.merge(
        plan,
        [
            "Spa is our venue. The broadcast is live.",
            "We are at Spa. The session is ready.",
            "Welcome to Spa. We are set to begin.",
        ],
    )
    now = time.monotonic()
    consumer.graph_runtime.reset(run_epoch=0, now=now - settings.scheduler.max_silence_s)

    utterance = director.tick(now)
    assert utterance is not None
    assert sink.spoken == [utterance]
    assert utterance.node_id == "stream_intro_venue"
    assert utterance.graph_candidate is not None
    assert utterance.graph_candidate.node_id == "stream_intro_venue"
    consumer._drain_graph_lifecycle()
    consumer._drain_prepared_lifecycle()

    assert consumer.graph_runtime.fatigue_counts()["semantic"] == 1
    await consumer.prepared_filler.close()


def test_missing_prepared_graph_contract_fails_soft_with_diagnostic() -> None:
    settings = CommentarySettings(
        enabled=True,
        graph_runtime_mode="active",
        prepared_filler=PreparedFillerSettings(mode="active"),
    )
    director = CommentaryDirector(
        graph=load_sequence_graph(), settings=settings, sink=NullTtsSink()
    )
    envelope = make_envelope(
        event_type="PREPARED_FILLER",
        phase="RESULT",
        mode="RACE",
        metrics={"preparedText": "Grounded text.", "preparedNodeId": "missing_node"},
    )

    assert director.rank_prepared_fillers([envelope], now=time.monotonic()) is None
    assert director.decisions(1)[0]["reason"] == "graph_contract_missing"
    assert director.decisions(1)[0]["nodeId"] == "missing_node"


@pytest.mark.asyncio
async def test_active_fatal_notice_is_acknowledged_only_by_tts_lifecycle() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("commentary")
    subscription.replace_latest_context(_prepared_context())
    sink = NullTtsSink()
    settings = CommentarySettings(
        enabled=True,
        cooldown_s=0,
        graph_runtime_mode="active",
        prepared_filler=PreparedFillerSettings(mode="active"),
    )
    director = CommentaryDirector(graph=load_sequence_graph(), settings=settings, sink=sink)
    consumer = CommentaryConsumer(subscription, director, lambda: (settings, "cs"))
    consumer.prepared_filler.health = PreparedFillerHealth.FATAL
    consumer.prepared_filler.fatal_episode = 1

    first = consumer._request_filler(time.monotonic())
    assert first is not None
    assert first.metrics["preparedText"] == "LLM fatal error, nemám texty."
    assert consumer._request_filler(time.monotonic()) is not None

    now = time.monotonic()
    consumer.graph_runtime.reset(run_epoch=0, now=now - settings.scheduler.max_silence_s)
    utterance = director.tick(now)
    assert utterance is not None
    assert utterance.node_id == "prepared_filler_fatal_notice"
    assert utterance.graph_candidate is None
    assert sink.spoken == [utterance]
    consumer._drain_prepared_lifecycle()

    assert consumer._request_filler(time.monotonic()) is None
    assert consumer.take_filler_request() is None
    await consumer.prepared_filler.close()


@pytest.mark.asyncio
async def test_prepared_tts_commit_rejects_stale_stage() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("commentary")
    subscription.replace_latest_context(_prepared_context())
    sink = NullTtsSink()
    settings = CommentarySettings(
        enabled=True,
        prepared_filler=PreparedFillerSettings(mode="active"),
    )
    director = CommentaryDirector(graph=load_sequence_graph(), settings=settings, sink=sink)
    consumer = CommentaryConsumer(subscription, director, lambda: (settings, "en"))
    context = thaw_context(_prepared_context())
    plan = build_prepared_filler_plans(context, "en")[0]
    consumer.prepared_filler.buffer.reconcile([plan])
    consumer.prepared_filler.buffer.merge(
        plan,
        [
            "Spa is our venue. The broadcast is live.",
            "We are at Spa. The session is ready.",
            "Welcome to Spa. We are set to begin.",
        ],
    )
    consumer.graph_runtime.reset(
        run_epoch=0, now=time.monotonic() - settings.scheduler.max_silence_s
    )
    envelope = consumer._request_filler(time.monotonic())
    assert envelope is not None
    utterance = director._utterance_from_formatter(envelope)
    assert utterance is not None

    subscription.replace_latest_context(_prepared_context(stage="LIVE_SESSION"))
    sink.enqueue(utterance)

    assert sink.spoken == []
    assert sink.dropped == [utterance]
    await consumer.prepared_filler.close()


@pytest.mark.asyncio
async def test_shadow_graph_scores_without_changing_legacy_speech_and_records_exposure() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("commentary")
    subscription.replace_latest_context(_context())
    sink = NullTtsSink()
    settings = CommentarySettings(
        enabled=True,
        cooldown_s=0,
        graph_runtime_mode="shadow",
    )
    director = CommentaryDirector(graph=_graph(), settings=settings, sink=sink)
    graph_rows: list[dict] = []
    consumer = CommentaryConsumer(
        subscription,
        director,
        lambda: (settings, "en"),
        decision_hook=lambda entry, _now: graph_rows.append(entry),
    )

    await consumer.handle(_batch())

    assert [item.text for item in sink.spoken] == ["A lap is complete."]
    assert sink.spoken[0].graph_candidate is not None
    assert consumer.graph_runtime.fatigue_counts()["semantic"] == 1
    assert consumer.graph_runtime.current_node_id == "__silence__"
    graph_score = next(row for row in graph_rows if row["action"] == "graph_score")
    assert graph_score["graphMode"] == "shadow"
    assert graph_score["decision"] == "selected"
    assert graph_score["components"]["base"] == 50.0
    status = consumer.status_snapshot()
    assert status["graph"]["mode"] == "shadow"
    assert status["graph"]["fatigueEntries"]["semantic"] == 1


@pytest.mark.asyncio
async def test_legacy_mode_does_not_activate_graph_runtime() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("commentary")
    subscription.replace_latest_context(_context())
    sink = NullTtsSink()
    settings = CommentarySettings(enabled=True, cooldown_s=0, graph_runtime_mode="legacy")
    director = CommentaryDirector(graph=_graph(), settings=settings, sink=sink)
    consumer = CommentaryConsumer(subscription, director, lambda: (settings, "en"))

    await consumer.handle(_batch())

    assert sink.spoken[0].graph_candidate is None
    assert consumer.graph_runtime.fatigue_counts() == {
        "node": 0,
        "edge": 0,
        "semantic": 0,
        "path": 0,
    }


@pytest.mark.asyncio
async def test_active_filler_batch_gets_unique_ids_and_speaks_one_graph_winner() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("commentary")
    subscription.replace_latest_context(_context())
    sink = NullTtsSink()
    settings = CommentarySettings(
        enabled=True,
        cooldown_s=0,
        use_hr_emotion=False,
        graph_runtime_mode="active",
    )
    director = CommentaryDirector(graph=load_sequence_graph(), settings=settings, sink=sink)
    consumer = CommentaryConsumer(subscription, director, lambda: (settings, "en"))
    now = time.monotonic()
    consumer.graph_runtime.reset(run_epoch=0, now=now - settings.scheduler.max_silence_s)
    consumer._request_filler(now - 0.1)

    allocator = SessionSequenceAllocator(session_id="session")
    envelopes = [
        make_envelope(
            event_type="FIELD_FACT",
            phase="RESULT",
            mode="RACE",
            priority=28,
            correlation_id="field:position",
            metrics={"kind": "field_fact", "fact": "position", "position": 5},
        ),
        make_envelope(
            event_type="FIELD_FACT",
            phase="RESULT",
            mode="RACE",
            priority=28,
            correlation_id="field:leader",
            metrics={"kind": "field_fact", "fact": "leader", "leaderName": "Rossi"},
        ),
        make_envelope(
            event_type="WEATHER_CHANGE",
            phase="RESULT",
            mode="RACE",
            priority=34,
            correlation_id="weather:session",
            metrics={"kind": "weather_change", "skies": "overcast", "air_temp": "22 C"},
        ),
    ]
    accepted = tuple(
        freeze_accepted_event(
            allocator.stamp(envelope),
            audiences=("commentary",),
            source="filler",
            source_ordinal=index,
        )
        for index, envelope in enumerate(envelopes)
    )
    batch = FrozenAcceptedEventBatch(
        1,
        "session",
        1,
        int(now * 1000),
        1,
        _context(),
        accepted,
    )

    await consumer.handle(batch)

    assert len({event.event_id for event in accepted}) == 3
    assert len(sink.spoken) == 1
    assert sink.spoken[0].event_type == "WEATHER_CHANGE"
    assert consumer.status_snapshot()["fillerOutstanding"] is False


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
        CommentaryDirector(graph=load_sequence_graph(), settings=settings, sink=NullTtsSink()),
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
                **asdict(initial),
                "enabled": True,
                "cooldown_s": 1.5,
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


@pytest.mark.asyncio
async def test_session_reset_discards_waiter_without_interrupting_current_tts() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("commentary")
    sink = NullTtsSink(force_busy=True)
    settings = CommentarySettings(
        enabled=True,
        prepared_filler=PreparedFillerSettings(mode="active"),
    )
    consumer = CommentaryConsumer(
        subscription,
        CommentaryDirector(graph=_graph(), settings=settings, sink=sink),
        lambda: (settings, "en"),
    )

    await consumer.handle(SessionReset("session", "session", "run_epoch_changed", 2))

    assert sink.interrupted == 0
    assert sink.force_busy is False
    assert consumer.prepared_filler.buffer.desired == ()


def test_prepared_shadow_records_reconstructable_legacy_comparison() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("commentary")
    subscription.replace_latest_context(_prepared_context())
    rows: list[dict[str, object]] = []
    settings = CommentarySettings(
        enabled=True,
        cooldown_s=0,
        prepared_filler=PreparedFillerSettings(mode="shadow"),
    )
    consumer = CommentaryConsumer(
        subscription,
        CommentaryDirector(graph=load_sequence_graph(), settings=settings, sink=NullTtsSink()),
        lambda: (settings, "en"),
        decision_hook=lambda entry, _now: rows.append(entry),
    )
    context = thaw_context(_prepared_context())
    plan = build_prepared_filler_plans(context, "en")[0]
    consumer.prepared_filler.buffer.reconcile([plan], current_stage="STREAM_LOBBY_INTRO")
    consumer.prepared_filler.buffer.merge(
        plan,
        [
            "Spa hosts this race. The stream is ready.",
            "This race comes from Spa. We are ready to go.",
            "Welcome to Spa for the race. The broadcast is live.",
        ],
    )
    consumer.graph_runtime.reset(
        run_epoch=0, now=time.monotonic() - settings.scheduler.max_silence_s
    )

    assert consumer._request_filler(time.monotonic()) is None
    request = consumer.take_filler_request()
    assert request is not None
    consumer.complete_filler(FillerResult(request.request_id, "no_fact"))
    consumer._drain_filler_results(time.monotonic())

    compared = next(row for row in rows if row.get("action") == "shadow_compared")
    assert compared["semanticKey"] == plan.semantic_key
    assert compared["legacySemanticKey"] is None
    assert compared["divergence"] == "shadow_only"
    assert compared["comparisonReason"] == "no_fact"


def test_filler_request_is_bounded_and_completed_by_typed_result() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("commentary")
    subscription.replace_latest_context(_context())
    settings = CommentarySettings(
        enabled=True,
        graph_runtime_mode="legacy",
        prepared_filler=PreparedFillerSettings(mode="legacy"),
    )
    director = CommentaryDirector(graph=_graph(), settings=settings, sink=NullTtsSink())
    consumer = CommentaryConsumer(subscription, director, lambda: (settings, "en"))

    assert consumer._request_filler(time.monotonic()) is None
    assert consumer._request_filler(time.monotonic()) is None
    request = consumer.take_filler_request()
    assert request is not None
    consumer.complete_filler(FillerResult(request.request_id, "no_fact"))
    assert consumer.status_snapshot()["fillerOutstanding"] is False
