"""Tests for event log system."""

from __future__ import annotations

import pytest

from irswitch.server.event_log import Event, EventLog, get_event_log, set_event_log


@pytest.fixture
def event_log() -> EventLog:
    """Create event log instance for testing."""
    return EventLog(max_size=10)


@pytest.mark.asyncio
async def test_add_event(event_log: EventLog) -> None:
    """Test adding event to log."""
    await event_log.add_event("test_event", "Test message", {"key": "value"})

    events = await event_log.get_all_events()
    assert len(events) == 1
    assert events[0].type == "test_event"
    assert events[0].message == "Test message"
    assert events[0].data == {"key": "value"}


@pytest.mark.asyncio
async def test_get_recent_events(event_log: EventLog) -> None:
    """Test getting recent events."""
    # Add multiple events
    for i in range(5):
        await event_log.add_event(f"event_{i}", f"Message {i}")

    # Get last 3
    recent = await event_log.get_recent_events(3)
    assert len(recent) == 3
    assert recent[0].type == "event_2"
    assert recent[-1].type == "event_4"


@pytest.mark.asyncio
async def test_get_all_events(event_log: EventLog) -> None:
    """Test getting all events."""
    for i in range(5):
        await event_log.add_event(f"event_{i}", f"Message {i}")

    all_events = await event_log.get_all_events()
    assert len(all_events) == 5


@pytest.mark.asyncio
async def test_event_log_max_size(event_log: EventLog) -> None:
    """Test that event log respects max_size (FIFO)."""
    # Add more events than max_size
    for i in range(15):
        await event_log.add_event(f"event_{i}", f"Message {i}")

    all_events = await event_log.get_all_events()
    assert len(all_events) == 10  # max_size
    # Should keep last 10
    assert all_events[0].type == "event_5"
    assert all_events[-1].type == "event_14"


@pytest.mark.asyncio
async def test_event_timestamp(event_log: EventLog) -> None:
    """Test that events have timestamps."""
    await event_log.add_event("test", "Test")

    events = await event_log.get_all_events()
    assert len(events) == 1
    assert events[0].timestamp > 0
    assert isinstance(events[0].timestamp, int)


@pytest.mark.asyncio
async def test_get_recent_events_zero_count(event_log: EventLog) -> None:
    """Test getting recent events with count=0 returns all."""
    for i in range(5):
        await event_log.add_event(f"event_{i}", f"Message {i}")

    recent = await event_log.get_recent_events(0)
    assert len(recent) == 5


@pytest.mark.asyncio
async def test_get_recent_events_more_than_available(event_log: EventLog) -> None:
    """Test getting more events than available."""
    for i in range(3):
        await event_log.add_event(f"event_{i}", f"Message {i}")

    recent = await event_log.get_recent_events(10)
    assert len(recent) == 3


def test_clear_events(event_log: EventLog) -> None:
    """Test clearing events."""
    # Note: clear() is not async, but we need to add events first
    import asyncio

    async def _test():
        await event_log.add_event("test", "Test")
        assert len(await event_log.get_all_events()) == 1

        event_log.clear()
        assert len(await event_log.get_all_events()) == 0

    asyncio.run(_test())


def test_global_event_log() -> None:
    """Test global event log instance."""
    # Get default instance
    log1 = get_event_log()
    assert log1 is not None

    # Set custom instance
    custom_log = EventLog(max_size=20)
    set_event_log(custom_log)

    log2 = get_event_log()
    assert log2 is custom_log
    assert log2.max_size == 20
