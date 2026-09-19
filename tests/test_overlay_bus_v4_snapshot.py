"""Bus STATE_SNAPSHOT on reconnect when V4 stories active."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from irswitch.events.async_fanout import AsyncEventFanout
from irswitch.events.stream import SessionReset
from irswitch.overlay.bus import OverlayBus
from irswitch.overlay.consumer import OverlayConsumer


@pytest.mark.asyncio
async def test_add_client_sends_state_snapshot_when_v4_stories() -> None:
    bus = OverlayBus()
    bus.active_stories_v4 = [{"eventType": "LAP_COMPLETE", "sequence": 1}]
    ws = AsyncMock()
    await bus.add_client(ws)
    assert ws.send_str.await_count == 2
    second = json.loads(ws.send_str.await_args_list[1].args[0])
    assert second["type"] == "STATE_SNAPSHOT"
    assert second["activeStories"][0]["eventType"] == "LAP_COMPLETE"


@pytest.mark.asyncio
async def test_new_empty_client_gets_authoritative_empty_snapshot() -> None:
    ws = AsyncMock()
    await OverlayBus().add_client(ws)
    assert ws.send_str.await_count == 2
    assert json.loads(ws.send_str.await_args_list[-1].args[0])["activeStories"] == []


@pytest.mark.asyncio
async def test_final_exit_broadcasts_empty_snapshot_and_unchanged_state_is_quiet() -> None:
    bus, ws = OverlayBus(), AsyncMock()
    await bus.add_client(ws)
    ws.send_str.reset_mock()
    stories = [{"eventType": "HUNTING", "metrics": {"gap": 2.0}}]
    bus.set_active_stories_v4(stories)
    await bus.flush_state()
    assert json.loads(ws.send_str.await_args.args[0])["activeStories"] == stories
    ws.send_str.reset_mock()
    bus.set_active_stories_v4(stories)
    await bus.flush_state()
    ws.send_str.assert_not_awaited()
    bus.set_active_stories_v4([])
    await bus.flush_state()
    assert json.loads(ws.send_str.await_args.args[0])["activeStories"] == []


@pytest.mark.asyncio
async def test_story_snapshot_owns_nested_data_for_change_detection() -> None:
    bus, ws = OverlayBus(), AsyncMock()
    await bus.add_client(ws)
    stories = [{"eventType": "HUNTING", "metrics": {"gap": 2.0}}]
    bus.set_active_stories_v4(stories)
    await bus.flush_state()
    ws.send_str.reset_mock()
    stories[0]["metrics"]["gap"] = 1.0
    bus.set_active_stories_v4(stories)
    await bus.flush_state()
    assert ws.send_str.await_count == 1
    assert json.loads(ws.send_str.await_args.args[0])["activeStories"][0]["metrics"]["gap"] == 1.0


@pytest.mark.asyncio
async def test_consumer_reset_clears_the_authoritative_wire_state() -> None:
    bus, ws = OverlayBus(), AsyncMock()
    bus.set_active_stories_v4([{"eventType": "HUNTED"}])
    await bus.add_client(ws)
    await bus.flush_state()
    ws.send_str.reset_mock()
    consumer = OverlayConsumer(AsyncEventFanout().subscribe("overlay"), bus)
    await consumer.handle(SessionReset("old", "new", "session_change", 1))
    snapshots = [json.loads(call.args[0]) for call in ws.send_str.await_args_list]
    assert {"type": "STATE_SNAPSHOT", "activeStories": []} in snapshots
