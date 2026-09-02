"""Non-blocking bounded broadcast fan-out for the N12 stream."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from irswitch.events.stream import (
    ConfigUpdate,
    FrozenAcceptedEvent,
    FrozenAcceptedEventBatch,
    FrozenContextSnapshot,
    SessionReset,
    StreamItem,
)

logger = logging.getLogger(__name__)


class ConsumerRecoveryRequired(RuntimeError):
    """Queue recovery requested a same-instance worker restart."""


@dataclass(frozen=True)
class QueueStats:
    name: str
    capacity: int
    depth: int
    enqueued: int
    dequeued: int
    coalesced: int
    evicted: int
    recovery_discards: int
    overflows: int
    degraded: bool
    lag_ms: int
    sequence_lag: int
    restart_requests: int


class EventSubscription:
    """One consumer-owned FIFO plus replace-only latest-context slot."""

    def __init__(self, name: str, *, capacity: int = 64) -> None:
        if capacity <= 0:
            raise ValueError("subscription capacity must be positive")
        self.name = name
        self.capacity = capacity
        self._items: deque[StreamItem] = deque()
        self._ready = asyncio.Event()
        self._closed = False
        self._latest_context: FrozenContextSnapshot | None = None
        self._enqueued = 0
        self._dequeued = 0
        self._coalesced = 0
        self._evicted = 0
        self._recovery_discards = 0
        self._overflows = 0
        self._degraded = False
        self._last_dequeued_stream_sequence = 0
        self._restart_requested = False
        self._restart_requests = 0

    @property
    def latest_context(self) -> FrozenContextSnapshot | None:
        return self._latest_context

    def replace_latest_context(self, payload: FrozenContextSnapshot) -> None:
        self._latest_context = payload

    def put_nowait(self, item: StreamItem) -> bool:
        """Admit without awaiting consumer work; return False only on recovery."""
        if self._closed:
            return False
        if isinstance(item, FrozenAcceptedEventBatch) and self._coalesce_into_queue(item):
            return True
        if len(self._items) < self.capacity:
            self._append(item)
            return True
        if self._evict_for(item):
            self._append(item)
            return True
        self._recover_for_protected(item)
        return False

    async def get(self) -> StreamItem:
        while True:
            if self._restart_requested:
                self._restart_requested = False
                raise ConsumerRecoveryRequired(
                    f"subscription {self.name} recovered protected queue overflow"
                )
            if self._items:
                item = self._items.popleft()
                self._dequeued += 1
                self._last_dequeued_stream_sequence = item.stream_sequence
                if not self._items:
                    self._ready.clear()
                return item
            if self._closed:
                raise asyncio.CancelledError
            await self._ready.wait()

    def close(self) -> None:
        self._closed = True
        self._ready.set()

    def clear(self) -> int:
        count = len(self._items)
        self._items.clear()
        self._ready.clear()
        return count

    def snapshot(self, *, producer_stream_sequence: int) -> QueueStats:
        now_ms = int(time.monotonic() * 1000)
        accepted_times = [
            item.accepted_monotonic_ms
            for item in self._items
            if isinstance(item, FrozenAcceptedEventBatch)
        ]
        return QueueStats(
            name=self.name,
            capacity=self.capacity,
            depth=len(self._items),
            enqueued=self._enqueued,
            dequeued=self._dequeued,
            coalesced=self._coalesced,
            evicted=self._evicted,
            recovery_discards=self._recovery_discards,
            overflows=self._overflows,
            degraded=self._degraded,
            lag_ms=max(0, now_ms - min(accepted_times)) if accepted_times else 0,
            sequence_lag=max(0, producer_stream_sequence - self._last_dequeued_stream_sequence),
            restart_requests=self._restart_requests,
        )

    def _append(self, item: StreamItem) -> None:
        self._items.append(item)
        self._enqueued += 1
        self._ready.set()

    def _coalesce_into_queue(self, incoming: FrozenAcceptedEventBatch) -> bool:
        matches: list[tuple[int, int, FrozenAcceptedEvent]] = []
        used: set[tuple[int, int]] = set()
        for event in incoming.events:
            if not event.coalescible:
                return False
            found: tuple[int, int] | None = None
            for item_index, queued in enumerate(self._items):
                if not isinstance(queued, FrozenAcceptedEventBatch):
                    continue
                for event_index, old in enumerate(queued.events):
                    position = (item_index, event_index)
                    if position in used:
                        continue
                    if old.coalescible and old.coalesce_key == event.coalesce_key:
                        found = position
                        break
                if found is not None:
                    break
            if found is None:
                return False
            used.add(found)
            matches.append((*found, event))
        for item_index in {match[0] for match in matches}:
            queued = self._items[item_index]
            assert isinstance(queued, FrozenAcceptedEventBatch)
            replacement = list(queued.events)
            for matched_item_index, event_index, event in matches:
                if matched_item_index == item_index:
                    replacement[event_index] = event
            self._items[item_index] = FrozenAcceptedEventBatch(
                stream_sequence=incoming.stream_sequence,
                session_id=incoming.session_id,
                batch_sequence=incoming.batch_sequence,
                accepted_monotonic_ms=incoming.accepted_monotonic_ms,
                context_version=incoming.context_version,
                context_payload=incoming.context_payload,
                events=tuple(replacement),
            )
        self._coalesced += len(matches)
        return True

    def _evict_for(self, incoming: StreamItem) -> bool:
        incoming_priority = _item_priority(incoming)
        for index, queued in enumerate(self._items):
            if not _item_coalescible(queued):
                continue
            if _item_priority(queued) >= incoming_priority:
                continue
            del self._items[index]
            self._evicted += 1
            self._overflows += 1
            logger.warning(
                "consumer_queue_overflow consumer=%s policy=evict_lower_priority "
                "event_id=%s sequence=%s depth=%s",
                self.name,
                _first_event_id(incoming),
                incoming.stream_sequence,
                len(self._items),
            )
            return True
        return False

    def _recover_for_protected(self, incoming: StreamItem) -> None:
        discarded = self.clear()
        self._recovery_discards += discarded
        self._overflows += 1
        self._degraded = True
        self._restart_requested = True
        self._restart_requests += 1
        self._append(incoming)
        logger.error(
            "consumer_queue_overflow consumer=%s policy=restart_recovery "
            "event_id=%s sequence=%s depth=%s discarded=%s",
            self.name,
            _first_event_id(incoming),
            incoming.stream_sequence,
            len(self._items),
            discarded,
        )


class AsyncEventFanout:
    """Broadcast one immutable stream item to every registered subscription."""

    def __init__(self) -> None:
        self._subscriptions: dict[str, EventSubscription] = {}
        self._stream_sequence = 0
        self._capture: Callable[[StreamItem], None] | None = None

    @property
    def stream_sequence(self) -> int:
        return self._stream_sequence

    def subscribe(self, name: str, *, capacity: int = 64) -> EventSubscription:
        if name in self._subscriptions:
            raise ValueError(f"duplicate subscription: {name}")
        subscription = EventSubscription(name, capacity=capacity)
        self._subscriptions[name] = subscription
        return subscription

    def next_stream_sequence(self) -> int:
        return self._stream_sequence + 1

    def publish(self, item: StreamItem) -> dict[str, bool]:
        if item.stream_sequence <= self._stream_sequence:
            raise ValueError("stream sequence must be strictly increasing")
        self._stream_sequence = item.stream_sequence
        if self._capture is not None:
            try:
                self._capture(item)
            except Exception:
                logger.error("N12 replay capture failed", exc_info=True)
        results: dict[str, bool] = {}
        for name, subscription in self._subscriptions.items():
            results[name] = subscription.put_nowait(item)
        return results

    def set_capture(self, capture: Callable[[StreamItem], None] | None) -> None:
        self._capture = capture

    def publish_context(self, payload: FrozenContextSnapshot) -> None:
        for subscription in self._subscriptions.values():
            subscription.replace_latest_context(payload)

    def close(self) -> None:
        for subscription in self._subscriptions.values():
            subscription.close()

    def status_snapshot(self) -> dict[str, Any]:
        return {
            "streamSequence": self._stream_sequence,
            "consumers": {
                name: stats.__dict__
                for name, subscription in self._subscriptions.items()
                for stats in [subscription.snapshot(producer_stream_sequence=self._stream_sequence)]
            },
        }


def _item_coalescible(item: StreamItem) -> bool:
    return (
        isinstance(item, FrozenAcceptedEventBatch)
        and bool(item.events)
        and all(event.coalescible for event in item.events)
    )


def _item_priority(item: StreamItem) -> int:
    if isinstance(item, (SessionReset, ConfigUpdate)):
        return 10_000
    return max(event.priority for event in item.events)


def _first_event_id(item: StreamItem) -> str:
    if isinstance(item, FrozenAcceptedEventBatch):
        return item.events[0].event_id
    return type(item).__name__
