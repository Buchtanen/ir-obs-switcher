"""Event log system for dashboard events."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from irswitch.util.clock import now_ms

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """Single event entry."""

    timestamp: int  # Monotonic time in milliseconds
    type: str  # Event type: connection_lost, connection_restored, scene_switch, etc.
    message: str  # Human-readable message
    data: dict = field(default_factory=dict)  # Additional event data


class EventLog:
    """Thread-safe event log for storing recent events."""

    def __init__(self, max_size: int = 50) -> None:
        """
        Initialize event log.

        Args:
            max_size: Maximum number of events to keep (FIFO)
        """
        self.max_size = max_size
        self._events: list[Event] = []
        self._lock = asyncio.Lock()

    async def add_event(
        self,
        event_type: str,
        message: str,
        data: dict | None = None,
    ) -> None:
        """
        Add an event to the log (thread-safe).

        Automatically rotates (FIFO) - when log is full, oldest events are removed.

        Args:
            event_type: Type of event (e.g., "connection_lost", "scene_switch")
            message: Human-readable message
            data: Optional additional data
        """
        async with self._lock:
            event = Event(
                timestamp=now_ms(),
                type=event_type,
                message=message,
                data=data or {},
            )
            self._events.append(event)

            # Rotate: Keep only last max_size events (FIFO - oldest removed first)
            if len(self._events) > self.max_size:
                self._events = self._events[-self.max_size :]
                logger.debug(f"Event log rotated: kept last {self.max_size} events")

            # Log event to logger
            logger.info(f"Event: {event_type} - {message}")

            logger.debug(f"Event logged: {event_type} - {message} (total: {len(self._events)})")

    async def get_recent_events(self, count: int) -> list[Event]:
        """
        Get recent events (thread-safe).

        Args:
            count: Number of recent events to return

        Returns:
            List of recent events (most recent last)
        """
        async with self._lock:
            return self._events[-count:] if count > 0 else self._events.copy()

    async def get_all_events(self) -> list[Event]:
        """
        Get all events (thread-safe).

        Returns:
            List of all events
        """
        async with self._lock:
            return self._events.copy()

    def clear(self) -> None:
        """Clear all events (not thread-safe, use with caution)."""
        self._events.clear()


# Global event log instance
_event_log: EventLog | None = None


def get_event_log() -> EventLog:
    """Get global event log instance."""
    global _event_log
    if _event_log is None:
        _event_log = EventLog()
    return _event_log


def set_event_log(event_log: EventLog) -> None:
    """Set global event log instance."""
    global _event_log
    _event_log = event_log
