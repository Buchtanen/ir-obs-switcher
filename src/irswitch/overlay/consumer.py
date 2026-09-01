"""Overlay peer consumer for the immutable N12 accepted stream."""

from __future__ import annotations

import asyncio
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
    thaw_context,
    thaw_envelope,
)
from irswitch.events.worker import StreamWorker
from irswitch.overlay.bus import OverlayBus
from irswitch.overlay.hydrate import bio_from_dict, race_from_dict, system_from_dict

logger = logging.getLogger(__name__)

RecordEvent = Callable[[dict[str, Any], float], None]


class OverlayConsumer:
    """Own HUD presentation and event wire; discard non-overlay audiences after dequeue."""

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
        self._last_context_version = 0

    async def run(self) -> None:
        await asyncio.gather(self.worker.run(), self._presentation_loop())

    async def handle(self, item: StreamItem) -> None:
        self.last_stream_sequence = item.stream_sequence
        if isinstance(item, SessionReset):
            self.bus.set_active_events([])
            self.bus.set_active_stories_v4([])
            await self.bus.flush_state()
            return
        if isinstance(item, ConfigUpdate):
            return
        await self._apply_context(item.context_payload)
        await self._publish_batch(item)
        await self.bus.flush_state()

    async def apply_latest_presentation(self) -> None:
        payload = self.subscription.latest_context
        if payload is None:
            return
        await self._apply_context(payload)
        await self.bus.flush_state()

    async def _presentation_loop(self) -> None:
        while True:
            try:
                await self.apply_latest_presentation()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.debug("overlay presentation apply failed", exc_info=True)
            await asyncio.sleep(0.15)

    async def _apply_context(self, payload: bytes) -> None:
        try:
            context = thaw_context(payload)
        except Exception:
            logger.warning("invalid frozen overlay context", exc_info=True)
            return
        version = int(context.get("version") or 0)
        race = context.get("race")
        if isinstance(race, dict):
            self.bus.set_race(race_from_dict(race))
        bio = context.get("bio")
        if isinstance(bio, dict):
            self.bus.set_bio(bio_from_dict(bio))
        system = context.get("system")
        if isinstance(system, dict) and system:
            self.bus.set_system(system_from_dict(system))
        hud = context.get("hud")
        hud = hud if isinstance(hud, dict) else {}
        events = hud.get("active_events")
        if isinstance(events, list):
            self.bus.set_active_events(events)
        stories = hud.get("active_stories_v4")
        if isinstance(stories, list):
            self.bus.set_active_stories_v4(stories)
        self._last_context_version = version

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
