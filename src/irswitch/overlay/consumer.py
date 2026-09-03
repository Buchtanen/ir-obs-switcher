"""Overlay peer consumer for the immutable N12 accepted stream."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import OrderedDict
from collections.abc import Callable
from copy import deepcopy
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
    thaw_story_payload,
)
from irswitch.events.worker import StreamWorker
from irswitch.overlay.bus import OverlayBus
from irswitch.overlay.hydrate import bio_from_dict, race_from_dict, system_from_dict

logger = logging.getLogger(__name__)

RecordEvent = Callable[[dict[str, Any], float], None]
_TERMINAL_STORY_ACTIONS = frozenset({"completed", "interrupted", "invalidated", "skipped"})
_ACTIVE_STORY_ACTIONS = frozenset({"building", "committed", "speaking", "resolved"})
_MAX_PENDING_STORY_TRANSITIONS = 64
_MAX_STORY_LIFECYCLES = 128


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
        self._source_stories: list[dict[str, Any]] = []
        self._story_wires: dict[str, dict[str, Any]] = {}
        self._story_leases: dict[str, dict[str, Any]] = {}
        self._story_lifecycle: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._closed_correlations: dict[str, str] = {}
        self._pending_story_transitions: OrderedDict[str, dict[str, Any]] = OrderedDict()
        self._story_transition_ready = asyncio.Event()

    async def run(self) -> None:
        await asyncio.gather(
            self.worker.run(),
            self._presentation_loop(),
            self._story_transition_loop(),
        )

    async def handle(self, item: StreamItem) -> None:
        self.last_stream_sequence = item.stream_sequence
        if isinstance(item, SessionReset):
            self._source_stories.clear()
            self._story_wires.clear()
            self._story_leases.clear()
            self._story_lifecycle.clear()
            self._closed_correlations.clear()
            self._pending_story_transitions.clear()
            self._story_transition_ready.clear()
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

    def enqueue_story_transition(self, entry: dict[str, Any]) -> None:
        """Called on the owning event loop after Runtime.call_soon_threadsafe."""
        story_id = str(entry.get("storyId") or "")
        if not story_id:
            return
        current = self._pending_story_transitions.get(story_id)
        revision = int(entry.get("storyRevision") or 0)
        if current is not None and revision < int(current.get("storyRevision") or 0):
            return
        self._pending_story_transitions[story_id] = deepcopy(entry)
        self._pending_story_transitions.move_to_end(story_id)
        while len(self._pending_story_transitions) > _MAX_PENDING_STORY_TRANSITIONS:
            self._pending_story_transitions.popitem(last=False)
        self._story_transition_ready.set()

    async def _story_transition_loop(self) -> None:
        while True:
            try:
                await self._story_transition_ready.wait()
                await self.apply_story_transitions()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.debug("mini-story overlay transition failed", exc_info=True)

    async def apply_story_transitions(self) -> None:
        pending = list(self._pending_story_transitions.values())
        self._pending_story_transitions.clear()
        self._story_transition_ready.clear()
        changed = False
        for entry in pending:
            story_id = str(entry.get("storyId") or "")
            if not story_id:
                continue
            revision = int(entry.get("storyRevision") or 0)
            current = self._story_lifecycle.get(story_id)
            if current is not None and revision < int(current.get("storyRevision") or 0):
                continue
            action = str(entry.get("action") or entry.get("state") or "").lower()
            lifecycle = deepcopy(entry)
            lifecycle["state"] = action
            self._remember_story_lifecycle(story_id, lifecycle)
            if action in _TERMINAL_STORY_ACTIONS:
                correlation_id = str(entry.get("correlationId") or "")
                if correlation_id:
                    self._closed_correlations[correlation_id] = story_id
                self._story_leases.pop(story_id, None)
                self._story_wires.pop(story_id, None)
                changed = True
                continue
            if action not in _ACTIVE_STORY_ACTIONS:
                continue
            wire = self._story_wires.get(story_id)
            if wire is None:
                continue
            leased = deepcopy(wire)
            leased["miniStory"] = _story_meta(lifecycle, state=action)
            if action == "resolved":
                leased["phase"] = "RESULT"
            self._story_leases[story_id] = leased
            changed = True
        if changed:
            self._sync_story_snapshot()
            await self.bus.flush_state()

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
            self._source_stories = deepcopy(stories)
            self._sync_story_snapshot()
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
            story: dict[str, Any] | None = None
            if accepted.story_payload is not None:
                try:
                    story = thaw_story_payload(accepted.story_payload)
                except Exception:
                    logger.warning(
                        "invalid frozen mini-story event_id=%s", accepted.event_id, exc_info=True
                    )
            recorded = False
            if story is not None:
                wire["miniStory"] = story
                if self._record_event is not None:
                    self._record_event(wire, batch.accepted_monotonic_ms / 1000.0)
                    recorded = True
                story_id = str(story.get("storyId") or "")
                if story_id:
                    correlation_id = str(
                        story.get("correlationId") or wire.get("correlationId") or ""
                    )
                    closed_story_id = self._closed_correlations.get(correlation_id)
                    if closed_story_id and closed_story_id != story_id:
                        self._closed_correlations.pop(correlation_id, None)
                    self._story_wires[story_id] = deepcopy(wire)
                    if story.get("state") == "resolved" and story_id in self._story_leases:
                        resolved = deepcopy(self._story_leases[story_id])
                        for key in (
                            "eventId",
                            "sequence",
                            "sessionId",
                            "eventType",
                            "mode",
                            "priority",
                            "dedupeKey",
                            "correlationId",
                            "occurredAt",
                            "monotonicMs",
                        ):
                            if key in wire:
                                resolved[key] = deepcopy(wire[key])
                        resolved["phase"] = "RESULT"
                        resolved["metrics"] = deepcopy(wire.get("metrics") or {})
                        resolved["miniStory"] = _story_meta(story, state="resolved")
                        self._story_wires[story_id] = deepcopy(resolved)
                        self._story_leases[story_id] = resolved
                        self._remember_story_lifecycle(story_id, deepcopy(resolved["miniStory"]))
                        self._sync_story_snapshot()
                        await self.bus.publish_event(resolved)
                        continue
                    lifecycle = self._story_lifecycle.get(story_id)
                    if lifecycle is not None:
                        action = str(lifecycle.get("state") or lifecycle.get("action") or "")
                        current_revision = int(lifecycle.get("storyRevision") or 0)
                        source_revision = int(story.get("storyRevision") or 0)
                        if current_revision >= source_revision:
                            if action in _TERMINAL_STORY_ACTIONS:
                                continue
                            if action in _ACTIVE_STORY_ACTIONS:
                                leased = deepcopy(wire)
                                leased["miniStory"] = _story_meta(lifecycle, state=action)
                                if story.get("state") == "resolved":
                                    leased["phase"] = "RESULT"
                                self._story_leases[story_id] = leased
                                self._sync_story_snapshot()
                                if accepted.phase == "EXIT":
                                    await self.bus.publish_event(leased)
                                    continue
            if self._record_event is not None and not recorded:
                self._record_event(wire, batch.accepted_monotonic_ms / 1000.0)
            await self.bus.publish_event(wire)

    def _sync_story_snapshot(self) -> None:
        leased_correlations = {
            str(story.get("correlationId") or "")
            for story in self._story_leases.values()
            if story.get("correlationId")
        }
        source = [
            deepcopy(story)
            for story in self._source_stories
            if str(story.get("correlationId") or "")
            not in leased_correlations | self._closed_correlations.keys()
        ]
        self.bus.set_active_stories_v4([*source, *map(deepcopy, self._story_leases.values())])

    def _remember_story_lifecycle(self, story_id: str, lifecycle: dict[str, Any]) -> None:
        self._story_lifecycle[story_id] = lifecycle
        self._story_lifecycle.move_to_end(story_id)
        while len(self._story_lifecycle) > _MAX_STORY_LIFECYCLES:
            expired_id, expired = self._story_lifecycle.popitem(last=False)
            correlation_id = str(expired.get("correlationId") or "")
            if self._closed_correlations.get(correlation_id) == expired_id:
                self._closed_correlations.pop(correlation_id, None)
            self._story_wires.pop(expired_id, None)
            self._story_leases.pop(expired_id, None)

    def status_snapshot(self) -> dict[str, Any]:
        return {
            **self.worker.status_snapshot(),
            "lastStreamSequence": self.last_stream_sequence,
        }


def _story_meta(payload: dict[str, Any], *, state: str) -> dict[str, Any]:
    return {
        "storyId": str(payload.get("storyId") or ""),
        "storyRevision": int(payload.get("storyRevision") or 0),
        "runEpoch": int(payload.get("runEpoch") or 0),
        "heroOrderRevision": int(payload.get("heroOrderRevision") or 0),
        "correlationId": str(payload.get("correlationId") or ""),
        "eventType": str(payload.get("eventType") or ""),
        "state": state,
    }
