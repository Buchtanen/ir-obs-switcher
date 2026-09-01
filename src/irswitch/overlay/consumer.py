"""Overlay peer consumer for the immutable N12 accepted stream."""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

from irswitch.events.async_fanout import EventSubscription
from irswitch.events.manager_v2 import event_v4_wire
from irswitch.events.stream import (
    ConfigUpdate,
    FrozenAcceptedEventBatch,
    SessionReset,
    StreamItem,
    thaw_envelope,
)
from irswitch.events.worker import StreamWorker
from irswitch.overlay.bus import OverlayBus

logger = logging.getLogger(__name__)

RecordEvent = Callable[[dict[str, Any], float], None]


class OverlayConsumer:
    """Own HUD wire publication; discard non-overlay audiences after dequeue."""

    def __init__(
        self,
        subscription: EventSubscription,
        bus: OverlayBus,
        *,
        record_event: RecordEvent | None = None,
    ) -> None:
        self.subscription = subscription
        self.bus = bus
        self._record_event = record_event
        self.worker = StreamWorker("overlay", subscription, self.handle)
        self.last_stream_sequence = 0

    async def run(self) -> None:
        await self.worker.run()

    async def handle(self, item: StreamItem) -> None:
        self.last_stream_sequence = item.stream_sequence
        if isinstance(item, SessionReset):
            self.bus.set_active_events([])
            self.bus.set_active_stories_v4([])
            return
        if isinstance(item, ConfigUpdate):
            return
        await self._publish_batch(item)

    async def _publish_batch(self, batch: FrozenAcceptedEventBatch) -> None:
        for accepted in batch.events:
            if "overlay" not in accepted.audiences:
                continue
            envelope = thaw_envelope(accepted.envelope)
            wire = event_v4_wire(envelope)
            if accepted.overlay_payload is not None:
                try:
                    decoded = json.loads(accepted.overlay_payload.decode("utf-8"))
                    if isinstance(decoded, dict):
                        wire = decoded
                except (UnicodeDecodeError, json.JSONDecodeError):
                    logger.warning("invalid frozen overlay wire event_id=%s", accepted.event_id)
            if self._record_event is not None:
                self._record_event(wire, batch.accepted_monotonic_ms / 1000.0)
            await self.bus.publish_event(wire)

    def status_snapshot(self) -> dict[str, Any]:
        return {
            **self.worker.status_snapshot(),
            "lastStreamSequence": self.last_stream_sequence,
        }
