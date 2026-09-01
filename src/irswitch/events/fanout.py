"""Event fan-out: peer consumers of accepted speech/event envelopes."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Protocol

from irswitch.events.envelope import EventEnvelope

logger = logging.getLogger(__name__)


class EventConsumer(Protocol):
    """Peer sink for accepted envelopes (commentary, future observers, …)."""

    def on_envelopes(self, envelopes: list[EventEnvelope], *, now: float) -> None:
        """Handle a batch of envelopes. Must not raise across the fan-out boundary."""


class EventFanout:
    """Deterministic register → emit to all consumers; isolate per-consumer failures."""

    def __init__(self) -> None:
        self._consumers: list[EventConsumer] = []

    def register(self, consumer: EventConsumer) -> None:
        self._consumers.append(consumer)

    def clear(self) -> None:
        self._consumers.clear()

    @property
    def consumer_count(self) -> int:
        return len(self._consumers)

    def emit(self, envelopes: Sequence[EventEnvelope], *, now: float) -> None:
        if not envelopes:
            return
        batch = list(envelopes)
        for consumer in self._consumers:
            try:
                consumer.on_envelopes(batch, now=now)
            except Exception:
                logger.warning(
                    "event fan-out consumer %s failed",
                    type(consumer).__name__,
                    exc_info=True,
                )
