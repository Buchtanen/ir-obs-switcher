"""W1 close-out: HUD ownership, frozen story flags, stale-at-accept, replay path."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from irswitch.commentary.consumer import CommentaryConsumer
from irswitch.commentary.director import CommentaryDirector
from irswitch.commentary.graph import parse_sequence_graph
from irswitch.commentary.tts import NullTtsSink
from irswitch.events.async_fanout import AsyncEventFanout
from irswitch.events.envelope import make_envelope
from irswitch.events.replay import N12ReplayWriter, is_n12_replay
from irswitch.events.stream import (
    CONTEXT_SCHEMA_VERSION,
    FrozenAcceptedEventBatch,
    SessionReset,
    freeze_accepted_event,
    freeze_context,
)
from irswitch.events.worker import StreamWorker
from irswitch.overlay.bus import OverlayBus
from irswitch.overlay.consumer import OverlayConsumer
from irswitch.overlay.models import BioState, RaceState, SystemState
from irswitch.overlay.settings import CommentarySettings
from irswitch.race.pipeline import (
    RacePipeline,
    build_context_payload,
    context_stale_at_accept,
)
from irswitch.race.story import HeroSnapshot, QualiBag, StoryContext


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


def _full_context(
    *,
    version: int = 1,
    captured_ms: int | None = None,
    quali_bag: dict | None = None,
    grid_story: bool = False,
) -> bytes:
    return freeze_context(
        {
            "schema_version": CONTEXT_SCHEMA_VERSION,
            "version": version,
            "session_id": "session",
            "captured_monotonic_ms": captured_ms if captured_ms is not None else 1_000,
            "identity": {},
            "race": RaceState(connected=True, lap=4, overlay_mode="RACE", fps=90.0).to_dict(),
            "bio": {
                "status": "connected",
                "connected": True,
                "bpm": 150,
                "hr_state": "pushing",
                "device_name": "strap",
                "baseline_bpm": None,
                "delta_bpm": None,
                "sample_monotonic_ms": 1_000,
            },
            "system": SystemState().to_dict(),
            "hud": {
                "active_events": [{"id": "evt-1", "name": "lap_complete"}],
                "active_stories_v4": [{"eventType": "LAP_COMPLETE", "phase": "RESULT"}],
            },
            "story": {
                "hero": {"speakable_names": ["Alex"]},
                "quali_bag": quali_bag,
                "grid_story": grid_story,
            },
            "situation": {},
            "config": {"generation": 1, "language": "en", "grid_story": grid_story},
        }
    )


def _batch(context: bytes, *, stream_sequence: int = 1) -> FrozenAcceptedEventBatch:
    envelope = make_envelope(
        event_type="LAP_COMPLETE",
        phase="RESULT",
        mode="RACE",
        event_id=f"session:LAP_COMPLETE:{stream_sequence}",
        sequence=stream_sequence,
        session_id="session",
        priority=50,
        monotonic_ms=1_000,
        dedupe_key="lap",
        correlation_id=f"lap:{stream_sequence}",
    )
    accepted = freeze_accepted_event(
        envelope,
        audiences=("overlay", "commentary"),
        source="event_engine",
        source_ordinal=0,
        overlay_payload={"type": "event", "name": "lap_complete"},
    )
    return FrozenAcceptedEventBatch(
        stream_sequence,
        "session",
        stream_sequence,
        1_200,
        1,
        context,
        (accepted,),
    )


@pytest.mark.asyncio
async def test_overlay_consumer_applies_frozen_hud_presentation() -> None:
    fanout = AsyncEventFanout()
    bus = OverlayBus()
    consumer = OverlayConsumer(fanout.subscribe("overlay"), bus)

    await consumer.handle(_batch(_full_context()))

    assert bus.race.lap == 4
    assert bus.race.fps == 90.0
    assert bus.bio.bpm == 150
    assert bus.active_events == [{"id": "evt-1", "name": "lap_complete"}]
    assert bus.active_stories_v4 == [{"eventType": "LAP_COMPLETE", "phase": "RESULT"}]


@pytest.mark.asyncio
async def test_overlay_consumer_applies_latest_context_without_waiting_for_events() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("overlay")
    bus = OverlayBus()
    consumer = OverlayConsumer(subscription, bus)
    subscription.replace_latest_context(_full_context(version=2, captured_ms=2_000))

    await consumer.apply_latest_presentation()

    assert bus.race.lap == 4
    assert bus.bio.connected is True


@pytest.mark.asyncio
async def test_session_reset_clears_hud_presentation() -> None:
    fanout = AsyncEventFanout()
    bus = OverlayBus()
    consumer = OverlayConsumer(fanout.subscribe("overlay"), bus)
    await consumer.handle(_batch(_full_context()))

    await consumer.handle(SessionReset("session", "next", "session_changed", 2))

    assert bus.active_events == []
    assert bus.active_stories_v4 == []


def test_pipeline_context_includes_quali_bag_grid_story_system_and_hud() -> None:
    story = StoryContext(
        session_key="99:0",
        overlay_mode="RACE",
        hero=HeroSnapshot(car_idx=7, class_position=4, overall_position=4, lap=1),
        quali_bag=QualiBag(4, 90.0),
    )
    payload = build_context_payload(
        version=1,
        session_id="99:0",
        captured_monotonic_ms=1_000,
        race=RaceState(connected=True, overlay_mode="RACE"),
        bio=BioState(connected=True, status="connected", bpm=120),
        story=story,
        telemetry_data=None,
        language="en",
        commentary_enabled=True,
        config_generation=1,
        driver_profiles=None,
        system=SystemState(),
        hud={
            "active_events": [{"id": "a"}],
            "active_stories_v4": [{"eventType": "HUNTING"}],
        },
        grid_story=True,
    )

    assert payload["story"]["quali_bag"] == {"class_position": 4, "best_lap_s": 90.0}
    assert payload["config"]["grid_story"] is True
    assert payload["system"]["cpu"]["load"] is None
    assert payload["hud"]["active_events"] == [{"id": "a"}]


@pytest.mark.asyncio
async def test_commentary_reads_quali_bag_and_grid_story_from_frozen_context() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("commentary")
    context = _full_context(quali_bag={"class_position": 3, "best_lap_s": 88.1}, grid_story=True)
    subscription.replace_latest_context(context)
    settings = CommentarySettings(enabled=True, cooldown_s=0)
    director = CommentaryDirector(graph=_graph(), settings=settings, sink=NullTtsSink())
    consumer = CommentaryConsumer(subscription, director, lambda: (settings, "en"))

    await consumer.handle(_batch(context))

    assert director.grid_story is True
    assert director.quali_bag_ready is True


def test_context_stale_at_accept_uses_publish_minus_capture() -> None:
    assert (
        context_stale_at_accept(captured_ms=1_000, accepted_ms=1_000, poll_interval_ms=200) is False
    )
    assert (
        context_stale_at_accept(captured_ms=1_000, accepted_ms=1_150, poll_interval_ms=200) is False
    )
    assert (
        context_stale_at_accept(captured_ms=1_000, accepted_ms=1_250, poll_interval_ms=200) is True
    )


def test_pipeline_logs_stale_accept_when_publish_clock_lags_capture(
    caplog: pytest.LogCaptureFixture,
) -> None:
    fanout = AsyncEventFanout()
    fanout.subscribe("overlay")
    pipeline = RacePipeline(fanout)
    pipeline.reset_session("99:0", reason="session_changed")
    pipeline.capture_context(
        race=RaceState(connected=True, overlay_mode="RACE", session_num=0, subsession_id="99"),
        bio=BioState(),
        story=None,
        telemetry_data=None,
        captured_monotonic_ms=1_000,
        language="en",
        commentary_enabled=True,
    )
    envelope = make_envelope(
        event_type="LAP_COMPLETE",
        phase="RESULT",
        mode="RACE",
        priority=50,
        monotonic_ms=1_000,
    )

    with caplog.at_level("WARNING"):
        pipeline.publish_envelopes(
            [envelope],
            source="event_engine",
            accepted_monotonic_ms=1_400,
            poll_interval_ms=200,
        )

    assert any("context_stale_at_accept" in record.message for record in caplog.records)


def test_n12_replay_file_is_detected(tmp_path: Path) -> None:
    n12 = tmp_path / "n12.jsonl"
    overlay_tape = tmp_path / "overlay.jsonl"
    with N12ReplayWriter(
        n12,
        source_commit="abc",
        config_generation=1,
        config_digest="d",
        locale="en",
        monotonic_origin_ms=10_000,
    ):
        pass
    overlay_tape.write_text(json.dumps({"type": "snapshot", "t": 0}) + "\n", encoding="utf-8")

    assert is_n12_replay(n12) is True
    assert is_n12_replay(overlay_tape) is False


def test_runtime_does_not_write_overlay_bus_or_share_live_observer() -> None:
    runtime = (Path(__file__).parents[1] / "src" / "irswitch" / "race" / "runtime.py").read_text(
        encoding="utf-8"
    )
    assert "self.bus.set_race(" not in runtime
    assert "self.bus.set_bio(" not in runtime
    assert "self.bus.set_system(" not in runtime
    assert "self.bus.set_active_events(" not in runtime
    assert "self.bus.set_active_stories_v4(" not in runtime
    assert "self.bus.flush_state(" not in runtime
    assert "director.watcher_log = self.race_observer.watches" not in runtime
    assert "self.commentary.grid_story =" not in runtime
    assert "self.commentary.quali_bag_ready =" not in runtime
    assert "is_n12_replay(" in runtime
    assert "load_n12_replay(" in runtime


@pytest.mark.asyncio
async def test_slow_overlay_does_not_delay_commentary_worker() -> None:
    fanout = AsyncEventFanout()
    overlay_sub = fanout.subscribe("overlay", capacity=8)
    commentary_sub = fanout.subscribe("commentary", capacity=8)
    commentary_seen = asyncio.Event()
    overlay_release = asyncio.Event()

    async def overlay_handle(item) -> None:
        await overlay_release.wait()

    async def commentary_handle(item) -> None:
        commentary_seen.set()

    overlay_worker = StreamWorker("overlay", overlay_sub, overlay_handle)
    commentary_worker = StreamWorker("commentary", commentary_sub, commentary_handle)
    tasks = [
        asyncio.create_task(overlay_worker.run()),
        asyncio.create_task(commentary_worker.run()),
    ]
    try:
        context = freeze_context(
            {
                "schema_version": CONTEXT_SCHEMA_VERSION,
                "version": 1,
                "session_id": "session",
                "captured_monotonic_ms": 1,
                "identity": {},
                "race": {},
                "bio": {},
                "story": {},
                "situation": {},
                "config": {},
            }
        )
        envelope = make_envelope(
            event_type="LAP_COMPLETE",
            phase="RESULT",
            mode="RACE",
            event_id="session:event:1",
            sequence=1,
            session_id="session",
            priority=50,
            monotonic_ms=1,
        )
        accepted = freeze_accepted_event(
            envelope,
            audiences=("overlay", "commentary"),
            source="event_engine",
            source_ordinal=0,
        )
        fanout.publish(FrozenAcceptedEventBatch(1, "session", 1, 1, 1, context, (accepted,)))
        await asyncio.wait_for(commentary_seen.wait(), timeout=0.2)
        assert not overlay_release.is_set()
        assert commentary_worker.processed == 1
    finally:
        overlay_release.set()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
