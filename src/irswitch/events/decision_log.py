"""Bounded explainability log for event-engine decisions."""

from __future__ import annotations

from collections import deque
from typing import Any

from irswitch.util.clock import now_ms


class DecisionLog:
    """In-memory FIFO of event decisions.

    Like the rest of the overlay event pipeline, this class is intended for
    single-threaded use and does not provide synchronization.
    """

    def __init__(self, max_size: int = 500) -> None:
        if max_size <= 0:
            raise ValueError("max_size must be greater than zero")
        self.max_size = max_size
        self._entries: deque[dict[str, Any]] = deque(maxlen=max_size)

    def record(
        self,
        event_type: str,
        action: str,
        reason: str,
        details: dict[str, Any] | None = None,
        monotonic_ms: int | None = None,
        *,
        now: float | None = None,
    ) -> None:
        """Record a decision, using monotonic time when no timestamp is supplied.

        ``now`` accepts the event pipeline's monotonic seconds and converts it
        to milliseconds. It is mutually exclusive with ``monotonic_ms``.
        """
        if monotonic_ms is not None and now is not None:
            raise ValueError("provide either monotonic_ms or now, not both")
        timestamp = (
            int(monotonic_ms)
            if monotonic_ms is not None
            else int(now * 1000)
            if now is not None
            else now_ms()
        )
        self._entries.append(
            {
                "event_type": event_type,
                "action": action,
                "reason": reason,
                "details": dict(details or {}),
                "monotonic_ms": timestamp,
            }
        )

    def latest(self, n: int) -> list[dict[str, Any]]:
        """Return up to ``n`` newest entries, in chronological order."""
        if n <= 0:
            return []
        entries = list(self._entries)[-n:]
        return [self._copy_entry(entry) for entry in entries]

    def clear(self) -> None:
        """Remove all recorded decisions."""
        self._entries.clear()

    def to_list(self) -> list[dict[str, Any]]:
        """Return all entries in chronological order."""
        return [self._copy_entry(entry) for entry in self._entries]

    @staticmethod
    def _copy_entry(entry: dict[str, Any]) -> dict[str, Any]:
        copied = dict(entry)
        copied["details"] = dict(entry["details"])
        return copied
