"""Replay a JSONL overlay stream against the bus."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import fields
from typing import Any

from irswitch.overlay.bus import OverlayBus, load_jsonl
from irswitch.overlay.models import BioState, OpponentInfo, RaceState, SystemState

logger = logging.getLogger(__name__)


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
            t = float(row.get("t", 0.0))
            delay = (origin + t) - time.monotonic()
            if delay > 0:
                await asyncio.sleep(delay)
            await self._apply(row)

    async def _apply(self, row: dict[str, Any]) -> None:
        kind = row.get("type")
        if kind == "snapshot":
            race = row.get("race") or {}
            bio = row.get("bio") or {}
            system = row.get("system") or {}
            if race:
                self._bus.set_race(_race_from_dict(race))
            if bio:
                self._bus.set_bio(_bio_from_dict(bio))
            if system:
                self._bus.set_system(_system_from_dict(system))
            self._bus.set_active_events(list(row.get("activeEvents") or []))
            await self._bus.flush_state()
            return
        if kind == "state":
            domain = row.get("domain")
            data = row.get("data") or {}
            if domain == "race":
                self._bus.set_race(_race_from_dict(data))
            elif domain == "bio":
                self._bus.set_bio(_bio_from_dict(data))
            elif domain == "system":
                self._bus.set_system(_system_from_dict(data))
            await self._bus.flush_state()
            return
        if kind == "event":
            await self._bus.publish_event(row)


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
