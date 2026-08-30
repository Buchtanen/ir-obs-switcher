"""Bounded overlay lifecycle activity history."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from irswitch.overlay.activity import OverlayActivityLog
from irswitch.overlay.bus import OverlayBus


@pytest.fixture
def clocks() -> tuple[Callable[[], float], Callable[[], float]]:
    return (lambda: 1_800_000_000.0, lambda: 500.0)


@pytest.fixture
def v4_event() -> dict[str, Any]:
    return {
        "type": "event",
        "format": "v4",
        "eventType": "HUNTING",
        "phase": "ENTER",
        "monotonicMs": 499_000,
        "dedupeKey": "RACE:HUNTING:player",
    }


def test_add_records_v4_lifecycle_with_wall_and_monotonic_clocks(
    clocks: tuple[Callable[[], float], Callable[[], float]],
    v4_event: dict[str, Any],
) -> None:
    wall_clock, mono_clock = clocks
    activity = OverlayActivityLog(
        capacity=64,
        wall_clock=wall_clock,
        monotonic_clock=mono_clock,
    )

    assert activity.add(v4_event) is True

    assert activity.latest(1) == [
        {
            "occurredAt": 1_799_999_999.0,
            "monoMs": 499_000,
            "dedupeKey": "RACE:HUNTING:player",
            "source": "overlay",
            "kind": "HUNTING",
            "phase": "ENTER",
            "message": "Widget HUNTING (ENTER)",
            "ephemeral": False,
        }
    ]


def test_ring_is_fifo_bounded_and_latest_is_newest_first(
    clocks: tuple[Callable[[], float], Callable[[], float]],
) -> None:
    wall_clock, mono_clock = clocks
    activity = OverlayActivityLog(
        capacity=2,
        wall_clock=wall_clock,
        monotonic_clock=mono_clock,
    )

    for sequence, phase in enumerate(("ENTER", "UPDATE", "EXIT"), start=1):
        assert activity.add(
            {
                "type": "event",
                "eventType": "BATTLE",
                "phase": phase,
                "monotonicMs": 499_000 + sequence,
                "dedupeKey": f"battle:{sequence}",
            }
        )

    assert [row["phase"] for row in activity.latest(10)] == ["EXIT", "UPDATE"]
    activity.clear()
    assert activity.latest(10) == []


def test_legacy_trigger_is_stored_as_result_with_fallback_identity(
    clocks: tuple[Callable[[], float], Callable[[], float]],
) -> None:
    wall_clock, mono_clock = clocks
    activity = OverlayActivityLog(
        wall_clock=wall_clock,
        monotonic_clock=mono_clock,
    )

    assert activity.add(
        {
            "type": "event",
            "name": "lap_complete",
            "phase": "trigger",
            "timestamp": 499.0,
            "message": "Lap complete",
        }
    )

    row = activity.latest(1)[0]
    assert row["kind"] == "lap_complete"
    assert row["phase"] == "RESULT"
    assert row["dedupeKey"] == "overlay:lap_complete:RESULT:499000"
    assert row["message"] == "Lap complete"


def test_bad_envelopes_are_skipped_with_debug_log(
    caplog: pytest.LogCaptureFixture,
    clocks: tuple[Callable[[], float], Callable[[], float]],
) -> None:
    wall_clock, mono_clock = clocks
    activity = OverlayActivityLog(
        wall_clock=wall_clock,
        monotonic_clock=mono_clock,
    )

    with caplog.at_level(logging.DEBUG, logger="irswitch.overlay.activity"):
        assert activity.add({"type": "state", "phase": "ENTER"}) is False
        assert activity.add({"type": "event", "name": "battle", "phase": "unknown"}) is False

    assert activity.latest(10) == []
    assert "Skipping overlay lifecycle envelope" in caplog.text


@pytest.mark.asyncio
async def test_bus_records_events_without_websocket_clients(v4_event: dict[str, Any]) -> None:
    bus = OverlayBus()

    await bus.publish_event(v4_event)

    rows = bus.activity_log.latest(1)
    assert len(rows) == 1
    assert rows[0]["kind"] == "HUNTING"
    assert rows[0]["ephemeral"] is False
    assert bus.client_count == 0


@pytest.mark.asyncio
async def test_bus_broadcast_survives_activity_append_failure(
    v4_event: dict[str, Any],
) -> None:
    bus = OverlayBus()
    ws = AsyncMock()
    await bus.add_client(ws)
    ws.send_str.reset_mock()
    bus.activity_log.add = MagicMock(side_effect=RuntimeError("broken activity log"))

    await bus.publish_event(v4_event)

    ws.send_str.assert_awaited_once()
