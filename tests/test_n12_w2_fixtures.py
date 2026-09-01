"""W2 fixtures: two-front freshness, situation cadence, RaceRuntime E2E."""

from __future__ import annotations

import asyncio
import time
from dataclasses import replace
from types import SimpleNamespace

import pytest

from irswitch.commentary.consumer import CommentaryConsumer
from irswitch.commentary.director import CommentaryDirector
from irswitch.commentary.graph import load_sequence_graph
from irswitch.commentary.tts import NullTtsSink
from irswitch.events.async_fanout import AsyncEventFanout, EventSubscription
from irswitch.events.battle import BattleEmitter
from irswitch.events.envelope import make_envelope
from irswitch.events.stream import (
    CONTEXT_SCHEMA_VERSION,
    ConfigUpdate,
    FrozenAcceptedEventBatch,
    SessionReset,
    freeze_accepted_event,
    freeze_context,
)
from irswitch.overlay.bus import OverlayBus
from irswitch.overlay.models import OpponentInfo, RaceState
from irswitch.overlay.settings import CommentarySettings, HuntingSettings, OverlaySettings
from irswitch.race.pipeline import AcceptedRecord, build_situation_payload
from irswitch.race.runtime import RaceRuntime


def _battle_state(**overrides: object) -> RaceState:
    values: dict[str, object] = {
        "connected": True,
        "player_car_idx": 5,
        "position": 7,
        "overlay_mode": "RACE",
        "opponent_ahead": OpponentInfo(10, position=6, display_name="Rossi"),
        "opponent_behind": OpponentInfo(20, position=8, display_name="Berg"),
        "gap_ahead": 0.7,
        "gap_behind": 0.5,
        "closing_rate_ahead": 0.4,
        "closing_rate_behind": 0.3,
    }
    values.update(overrides)
    return RaceState(**values)  # type: ignore[arg-type]


def _emitter() -> BattleEmitter:
    settings = HuntingSettings(activation_delay=0.0)
    return BattleEmitter(settings, settings)


def _telemetry(*, laps: object = "10", time_s: object | None = None) -> dict[str, object]:
    session: dict[str, object] = {"SessionNum": 0, "SessionLaps": laps}
    if time_s is not None:
        session["SessionTime"] = time_s
    return {"SessionInfo": {"Sessions": [session]}}


def _runtime(*, language: str = "en") -> tuple[RaceRuntime, dict[str, OverlaySettings]]:
    holder = {
        "overlay": OverlaySettings(
            language=language,
            commentary=CommentarySettings(enabled=True, cooldown_s=0),
        )
    }
    runtime = RaceRuntime(
        lambda: SimpleNamespace(overlay=holder["overlay"]),
        None,
        OverlayBus(),
        mode="mock",
    )
    return runtime, holder


async def _drain(subscription: EventSubscription, *, limit: int = 8) -> list[object]:
    items: list[object] = []
    for _ in range(limit):
        try:
            items.append(await asyncio.wait_for(subscription.get(), timeout=0.02))
        except TimeoutError:
            break
    return items


def test_rear_exit_keeps_front_parent_and_closes_composite() -> None:
    emitter = _emitter()
    emitter.tick(_battle_state(), 10.0)
    lost_rear = _battle_state(
        opponent_behind=None,
        gap_behind=None,
        closing_rate_behind=None,
    )
    events = emitter.tick(lost_rear, 12.0)
    states = [(event.data["state"], event.phase) for event in events]
    assert ("hunted", "exit") in states
    assert ("battle_for_position", "exit") in states
    assert emitter.hunting.state == "ACTIVE"
    assert emitter.hunting.target_car_idx == 10
    assert emitter.hunted.state != "ACTIVE"


def test_pit_and_stale_telemetry_abort_composite() -> None:
    emitter = _emitter()
    emitter.tick(_battle_state(), 10.0)
    pit = emitter.tick(_battle_state(on_pit_road=True), 11.0)
    assert any(event.data.get("reason") == "pit_cycle" for event in pit)
    assert emitter.hunting.state != "ACTIVE"
    assert emitter.hunted.state != "ACTIVE"

    emitter = _emitter()
    emitter.tick(_battle_state(), 10.0)
    stale = emitter.tick(_battle_state(stale_for_ms=4_000), 11.0)
    assert any(event.data.get("reason") == "stale_relation" for event in stale)
    assert emitter.hunting.state != "ACTIVE"


def test_latest_context_vetoes_stale_two_front_and_keeps_parents() -> None:
    settings = CommentarySettings(enabled=True, cooldown_s=0)
    consumer = CommentaryConsumer(
        AsyncEventFanout().subscribe("commentary"),
        CommentaryDirector(graph=load_sequence_graph(), settings=settings, sink=NullTtsSink()),
        lambda: (settings, "en"),
    )
    front = make_envelope(event_type="HUNTING", phase="ENTER", priority=20)
    rear = make_envelope(event_type="HUNTED", phase="ENTER", priority=20)
    composite = make_envelope(
        event_type="BATTLE_FOR_POSITION",
        phase="ENTER",
        priority=30,
        metrics={"frontTargetCarIdx": 10, "rearTargetCarIdx": 20},
    )
    latest = {"race": {"opponent_ahead": {"car_idx": 10}, "opponent_behind": None}}

    selected = consumer._prefer_two_front([front, rear, composite], latest, 10.0)

    assert composite not in selected
    assert front in selected and rear in selected
    assert consumer.director.decisions()[-1]["reason"] == "stale_two_front_relation"


def test_missing_two_front_names_still_prefer_composite() -> None:
    settings = CommentarySettings(enabled=True, cooldown_s=0)
    consumer = CommentaryConsumer(
        AsyncEventFanout().subscribe("commentary"),
        CommentaryDirector(graph=load_sequence_graph(), settings=settings, sink=NullTtsSink()),
        lambda: (settings, "en"),
    )
    front = make_envelope(event_type="HUNTING", phase="ENTER", priority=20)
    composite = make_envelope(
        event_type="BATTLE_FOR_POSITION",
        phase="ENTER",
        priority=30,
        metrics={"frontTargetCarIdx": 10, "rearTargetCarIdx": 20},
    )
    latest = {
        "race": {
            "opponent_ahead": {"car_idx": 10},
            "opponent_behind": {"car_idx": 20},
        }
    }

    selected = consumer._prefer_two_front([front, composite], latest, 10.0)

    assert selected == [composite]
    assert consumer.director.decisions()[-1]["reason"] == "covered_by_two_front"


def test_situation_phase_boundaries_and_progress_sources() -> None:
    lap_limited = build_situation_payload(
        RaceState(connected=True, overlay_mode="RACE", lap=3, lap_completed=1, session_num=0),
        _telemetry(laps="10"),
        1_000,
    )
    assert lap_limited["progress_source"] == "laps"
    assert lap_limited["race_phase"] == "opening"

    at_twenty = build_situation_payload(
        RaceState(connected=True, overlay_mode="RACE", lap=3, lap_completed=2, session_num=0),
        _telemetry(laps="10"),
        1_000,
    )
    assert at_twenty["progress_ratio"] == 0.2
    assert at_twenty["race_phase"] == "middle"

    at_seventy = build_situation_payload(
        RaceState(connected=True, overlay_mode="RACE", lap=8, lap_completed=7, session_num=0),
        _telemetry(laps="10"),
        1_000,
    )
    assert at_seventy["progress_ratio"] == 0.7
    assert at_seventy["race_phase"] == "closing"

    timed = build_situation_payload(
        RaceState(
            connected=True,
            overlay_mode="RACE",
            session_num=0,
            session_time=600.0,
        ),
        _telemetry(laps="unlimited", time_s="1200.0 sec"),
        1_000,
    )
    assert timed["progress_source"] == "time"
    assert timed["race_phase"] == "middle"

    unlimited = build_situation_payload(
        RaceState(connected=True, overlay_mode="RACE", lap=4, lap_completed=3, session_num=0),
        _telemetry(laps="unlimited"),
        1_000,
    )
    assert unlimited["total_laps"] is None
    assert unlimited["race_phase"] == "unknown"


def test_situation_cadence_phase_change_interval_and_suppression() -> None:
    runtime, _holder = _runtime()
    runtime._session_brief_data = lambda: _telemetry(laps="10")  # type: ignore[method-assign]
    opening = RaceState(
        connected=True,
        overlay_mode="RACE",
        lap=2,
        lap_completed=1,
        session_num=0,
    )
    middle = RaceState(
        connected=True,
        overlay_mode="RACE",
        lap=4,
        lap_completed=3,
        session_num=0,
    )

    first = runtime._collect_situation_fact(opening, 10.0, [])
    assert first is not None
    assert first.envelope.metrics["situationPhase"] == "opening"

    assert runtime._collect_situation_fact(opening, 70.0, []) is None
    later = runtime._collect_situation_fact(opening, 130.0, [])
    assert later is not None

    phase = runtime._collect_situation_fact(middle, 131.0, [])
    assert phase is not None
    assert phase.envelope.metrics["situationPhase"] == "middle"

    hunting = AcceptedRecord(
        make_envelope(event_type="HUNTING", phase="ENTER", mode="RACE", priority=20),
        "event_engine",
    )
    assert runtime._collect_situation_fact(middle, 260.0, [hunting]) is None
    incident = AcceptedRecord(
        make_envelope(event_type="INCIDENT", phase="RESULT", mode="RACE", priority=90),
        "event_engine",
    )
    assert runtime._collect_situation_fact(middle, 261.0, [incident]) is None
    assert (
        runtime._collect_situation_fact(
            RaceState(connected=True, overlay_mode="PRACTICE", lap=4, lap_completed=3),
            400.0,
            [],
        )
        is None
    )


@pytest.mark.asyncio
async def test_situation_mismatch_or_age_strips_slots() -> None:
    fanout = AsyncEventFanout()
    subscription = fanout.subscribe("commentary")
    settings = CommentarySettings(enabled=True, cooldown_s=0)
    consumer = CommentaryConsumer(
        subscription,
        CommentaryDirector(graph=load_sequence_graph(), settings=settings, sink=NullTtsSink()),
        lambda: (settings, "en"),
    )
    embedded = {
        "schema_version": CONTEXT_SCHEMA_VERSION,
        "version": 1,
        "session_id": "session",
        "captured_monotonic_ms": 1_000,
        "identity": {},
        "race": {"player_car_idx": 5},
        "bio": {},
        "story": {},
        "situation": {"current_lap": 12, "total_laps": 30, "race_phase": "middle"},
        "config": {},
    }
    latest = freeze_context(
        {
            **embedded,
            "version": 2,
            "situation": {"current_lap": 13, "total_laps": 30, "race_phase": "closing"},
        }
    )
    subscription.replace_latest_context(latest)
    envelope = make_envelope(
        event_type="HUNTING",
        phase="UPDATE",
        mode="RACE",
        event_id="session:HUNTING:1",
        sequence=1,
        session_id="session",
        priority=20,
        monotonic_ms=1_000,
    )
    accepted = freeze_accepted_event(
        envelope,
        audiences=("commentary",),
        source="event_engine",
        source_ordinal=0,
    )
    batch = FrozenAcceptedEventBatch(
        1,
        "session",
        1,
        int(time.monotonic() * 1000),
        1,
        freeze_context(embedded),
        (accepted,),
    )

    await consumer.handle(batch)

    reasons = [item["reason"] for item in consumer.director.decisions()]
    assert "situation_context_stale" in reasons


@pytest.mark.asyncio
async def test_runtime_reset_and_config_reach_both_consumers() -> None:
    runtime, holder = _runtime()
    runtime._publish_config_update_if_changed()
    reset = runtime.pipeline.reset_session("99:0", reason="session_changed")
    assert reset is not None

    overlay_items = await _drain(runtime._overlay_subscription)
    commentary_items = await _drain(runtime._commentary_subscription)
    overlay_resets = [item for item in overlay_items if isinstance(item, SessionReset)]
    commentary_resets = [item for item in commentary_items if isinstance(item, SessionReset)]
    overlay_configs = [item for item in overlay_items if isinstance(item, ConfigUpdate)]
    commentary_configs = [item for item in commentary_items if isinstance(item, ConfigUpdate)]
    assert len(overlay_resets) == 1
    assert len(commentary_resets) == 1
    assert overlay_resets[0].stream_sequence == commentary_resets[0].stream_sequence
    assert overlay_resets[0].reason == "session_changed"
    assert overlay_configs and commentary_configs
    assert overlay_configs[0].generation == commentary_configs[0].generation

    runtime.bus.set_active_events([{"id": "stale"}])
    runtime.bus.set_active_stories_v4([{"eventType": "HUNTING"}])
    await runtime.overlay_consumer.handle(overlay_resets[0])
    assert runtime.bus.active_events == []
    assert runtime.bus.active_stories_v4 == []

    holder["overlay"] = replace(holder["overlay"], language="cs")
    runtime._publish_config_update_if_changed()
    config_items = [
        item
        for item in await _drain(runtime._commentary_subscription)
        if isinstance(item, ConfigUpdate)
    ]
    assert config_items
    await runtime.commentary_consumer.handle(config_items[-1])
    assert runtime.commentary_consumer.director.language == "cs"


@pytest.mark.asyncio
async def test_runtime_mock_tick_applies_hud_only_through_overlay_consumer() -> None:
    runtime, _holder = _runtime()
    await runtime._tick_race()
    assert runtime.bus.race.lap is None
    await runtime.overlay_consumer.apply_latest_presentation()
    assert runtime.bus.race.connected is True
    assert runtime.bus.race.lap == 12
