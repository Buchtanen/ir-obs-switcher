"""Bus STATE_SNAPSHOT on reconnect when V4 stories active."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from irswitch.overlay.bus import OverlayBus


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
