"""Replay a JSONL overlay stream against the bus."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from irswitch.overlay.bus import OverlayBus, load_jsonl
from irswitch.overlay.hydrate import bio_from_dict, race_from_dict, system_from_dict
from irswitch.overlay.tape import playback_offset, strip_tape_clocks

_bio_from_dict = bio_from_dict
_race_from_dict = race_from_dict
_system_from_dict = system_from_dict

logger = logging.getLogger(__name__)

_SKIP_TYPES = frozenset(
    {"header", "decision", "commentary", "llm_polish", "green", "stream_origin", "scene", "footer"}
)


class OverlayReplayer:
    def __init__(self, path: str, bus: OverlayBus) -> None:
        self._path = path
        self._bus = bus
        self._rows = load_jsonl(path)

    async def run(self) -> None:
        if not self._rows:
            logger.warning("Replay file empty: %s", self._path)
            return
        origin = time.monotonic()
        for row in self._rows:
            t = playback_offset(row)
            delay = (origin + t) - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            await self._apply(row)

    async def _apply(self, row: dict[str, Any]) -> None:
        kind = row.get("type")
        if kind in _SKIP_TYPES:
            return
        payload = strip_tape_clocks(row)
        if kind == "snapshot":
            race = payload.get("race") or {}
            bio = payload.get("bio") or {}
            system = payload.get("system") or {}
            if race:
                self._bus.set_race(race_from_dict(race))
            if bio:
                self._bus.set_bio(bio_from_dict(bio))
            if system:
                self._bus.set_system(system_from_dict(system))
            self._bus.set_active_events(list(payload.get("activeEvents") or []))
            await self._bus.flush_state()
            return
        if kind == "state":
            domain = payload.get("domain")
            data = payload.get("data") or {}
            if domain == "race":
                self._bus.set_race(race_from_dict(data))
            elif domain == "bio":
                self._bus.set_bio(bio_from_dict(data))
            elif domain == "system":
                self._bus.set_system(system_from_dict(data))
            await self._bus.flush_state()
            return
        if kind in {"stories", "STATE_SNAPSHOT"}:
            self._bus.set_active_stories_v4(list(payload.get("activeStories") or []))
            return
        if kind == "event":
            await self._bus.publish_event(payload)
