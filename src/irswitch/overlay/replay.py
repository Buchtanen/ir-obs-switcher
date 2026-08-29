"""Replay a JSONL overlay stream against the bus."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import fields
from typing import Any

from irswitch.overlay.bus import OverlayBus, load_jsonl
from irswitch.overlay.models import BioState, OpponentInfo, RaceState, SystemState
from irswitch.overlay.tape import playback_offset, strip_tape_clocks

logger = logging.getLogger(__name__)

_SKIP_TYPES = frozenset({"header", "decision", "green", "stream_origin", "scene", "footer"})


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
                self._bus.set_race(_race_from_dict(race))
            if bio:
                self._bus.set_bio(_bio_from_dict(bio))
            if system:
                self._bus.set_system(_system_from_dict(system))
            self._bus.set_active_events(list(payload.get("activeEvents") or []))
            await self._bus.flush_state()
            return
        if kind == "state":
            domain = payload.get("domain")
            data = payload.get("data") or {}
            if domain == "race":
                self._bus.set_race(_race_from_dict(data))
            elif domain == "bio":
                self._bus.set_bio(_bio_from_dict(data))
            elif domain == "system":
                self._bus.set_system(_system_from_dict(data))
            await self._bus.flush_state()
            return
        if kind in {"stories", "STATE_SNAPSHOT"}:
            self._bus.set_active_stories_v4(list(payload.get("activeStories") or []))
            return
        if kind == "event":
            await self._bus.publish_event(payload)


def _race_from_dict(data: dict[str, Any]) -> RaceState:
    # Opponent dicts need OpponentInfo; RaceState(**) will fail on nested dicts.
    ahead = data.get("opponent_ahead")
    behind = data.get("opponent_behind")
    clean = dict(data)
    clean["opponent_ahead"] = OpponentInfo(**ahead) if isinstance(ahead, dict) else ahead
    clean["opponent_behind"] = OpponentInfo(**behind) if isinstance(behind, dict) else behind
    allowed = {item.name for item in fields(RaceState)}
    return RaceState(**{k: v for k, v in clean.items() if k in allowed})


def _bio_from_dict(data: dict[str, Any]) -> BioState:
    allowed = {item.name for item in fields(BioState)}
    if "rr_intervals" in data and isinstance(data["rr_intervals"], list):
        data = {**data, "rr_intervals": tuple(data["rr_intervals"])}
    return BioState(**{k: v for k, v in data.items() if k in allowed})


def _system_from_dict(data: dict[str, Any]) -> SystemState:
    from irswitch.overlay.models import (
        CPUState,
        GPUState,
        MemoryState,
        PerformanceState,
        SystemHistory,
    )

    def _sub(cls: Any, payload: Any) -> Any:
        if not isinstance(payload, dict):
            return cls()
        allowed = {item.name for item in fields(cls)}
        clean = dict(payload)
        if "per_core_load" in clean and isinstance(clean["per_core_load"], list):
            clean["per_core_load"] = tuple(clean["per_core_load"])
        return cls(**{k: v for k, v in clean.items() if k in allowed})

    return SystemState(
        cpu=_sub(CPUState, data.get("cpu")),
        gpu=_sub(GPUState, data.get("gpu")),
        memory=_sub(MemoryState, data.get("memory")),
        performance=_sub(PerformanceState, data.get("performance")),
        history=_sub(SystemHistory, data.get("history")),
    )
