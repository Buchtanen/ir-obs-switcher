"""Owned async stream consumer worker and per-session idempotence ledger."""

from __future__ import annotations

import asyncio
import inspect
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from irswitch.events.async_fanout import EventSubscription
from irswitch.events.stream import FrozenAcceptedEventBatch, SessionReset, StreamItem

logger = logging.getLogger(__name__)

HandleItem = Callable[[StreamItem], Awaitable[None] | None]
RunWorker = Callable[[], Awaitable[None]]


@dataclass
class ProcessedEventLedger:
    capacity: int = 2_048
    session_id: str = ""
    _ids: set[str] = field(default_factory=set)
    _order: deque[str] = field(default_factory=deque)

    def reset(self, session_id: str) -> None:
        self.session_id = session_id
        self._ids.clear()
        self._order.clear()

    def contains(self, event_id: str) -> bool:
        return event_id in self._ids

    def add(self, event_id: str) -> None:
        if event_id in self._ids:
            return
        self._ids.add(event_id)
        self._order.append(event_id)
        while len(self._order) > max(1, self.capacity):
            self._ids.discard(self._order.popleft())


class StreamWorker:
    """Consume one subscription forever; isolate domain errors per stream item."""

    def __init__(
        self,
        name: str,
        subscription: EventSubscription,
        handle_item: HandleItem,
    ) -> None:
        self.name = name
        self.subscription = subscription
        self._handle_item = handle_item
        self.ledger = ProcessedEventLedger()
        self.running = False
        self.failures = 0
        self.processed = 0
        self.duplicates = 0
        self.last_error: str | None = None

    async def run(self) -> None:
        self.running = True
        try:
            while True:
                item = await self.subscription.get()
                try:
                    filtered = self._filter_duplicates(item)
                    if filtered is None:
                        continue
                    result = self._handle_item(filtered)
                    if inspect.isawaitable(result):
                        await result
                    self._commit_item(filtered)
                    self.processed += 1
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.failures += 1
                    self.last_error = f"{type(exc).__name__}: {exc}"
                    logger.warning(
                        "stream consumer %s failed for one item",
                        self.name,
                        exc_info=True,
                    )
        finally:
            self.running = False

    def status_snapshot(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "processed": self.processed,
            "duplicates": self.duplicates,
            "failures": self.failures,
            "lastError": self.last_error,
        }

    def _filter_duplicates(self, item: StreamItem) -> StreamItem | None:
        if isinstance(item, SessionReset):
            return item
        if not isinstance(item, FrozenAcceptedEventBatch):
            return item
        fresh = tuple(event for event in item.events if not self.ledger.contains(event.event_id))
        duplicates = len(item.events) - len(fresh)
        self.duplicates += duplicates
        if duplicates:
            logger.info(
                "duplicate_event consumer=%s count=%s stream_sequence=%s",
                self.name,
                duplicates,
                item.stream_sequence,
            )
        if not fresh:
            return None
        if len(fresh) == len(item.events):
            return item
        return FrozenAcceptedEventBatch(
            stream_sequence=item.stream_sequence,
            session_id=item.session_id,
            batch_sequence=item.batch_sequence,
            accepted_monotonic_ms=item.accepted_monotonic_ms,
            context_version=item.context_version,
            context_payload=item.context_payload,
            events=fresh,
        )

    def _commit_item(self, item: StreamItem) -> None:
        if isinstance(item, SessionReset):
            self.ledger.reset(item.new_session_id)
            return
        if isinstance(item, FrozenAcceptedEventBatch):
            if self.ledger.session_id != item.session_id:
                self.ledger.reset(item.session_id)
            for event in item.events:
                self.ledger.add(event.event_id)


class WorkerSupervisor:
    """Restart one worker coroutine around the same consumer instance."""

    def __init__(
        self,
        name: str,
        run_worker: RunWorker,
        *,
        initial_backoff_s: float = 0.05,
        max_backoff_s: float = 1.0,
    ) -> None:
        self.name = name
        self._run_worker = run_worker
        self.initial_backoff_s = max(0.0, initial_backoff_s)
        self.max_backoff_s = max(self.initial_backoff_s, max_backoff_s)
        self.running = False
        self.restarts = 0
        self.last_error: str | None = None

    async def run(self) -> None:
        self.running = True
        backoff = self.initial_backoff_s
        try:
            while True:
                try:
                    await self._run_worker()
                    self.last_error = "worker returned unexpectedly"
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    self.last_error = f"{type(exc).__name__}: {exc}"
                    logger.error("worker %s crashed; restarting", self.name, exc_info=True)
                self.restarts += 1
                await asyncio.sleep(backoff)
                backoff = min(self.max_backoff_s, max(self.initial_backoff_s, backoff * 2))
        finally:
            self.running = False

    def status_snapshot(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "restarts": self.restarts,
            "lastError": self.last_error,
        }
