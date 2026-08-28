"""Time-based sampling scheduler. Never blocks the caller; ticks are awaited."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

logger = logging.getLogger(__name__)

MIN_POLL_HZ = 0.2
MAX_POLL_HZ = 30.0


def clamp_hz(hz: float) -> float:
    """Clamp a poll rate. ``<= 0`` means event-driven / no poll."""
    if hz <= 0:
        return 0.0
    return max(MIN_POLL_HZ, min(MAX_POLL_HZ, float(hz)))


def resolve_component_hz(
    default_hz: float,
    override_hz: float | None,
    *,
    push_when_unset: bool = False,
) -> float:
    """
    Resolve a component sample rate.

    ``None`` override uses ``default_hz``, unless ``push_when_unset`` (BLE default).
    ``0`` always means push / event-driven.
    """
    if override_hz is None:
        if push_when_unset:
            return 0.0
        return clamp_hz(default_hz)
    return clamp_hz(override_hz)


class SamplingScheduler:
    """Run ``tick`` at a live-resolved Hz until cancelled."""

    def __init__(
        self,
        name: str,
        get_hz: Callable[[], float],
        tick: Callable[[], Awaitable[None]],
    ) -> None:
        self._name = name
        self._get_hz = get_hz
        self._tick = tick

    async def run(self) -> None:
        """Loop until the enclosing task is cancelled. Fail-soft on tick errors."""
        while True:
            hz = 0.0
            try:
                hz = clamp_hz(self._get_hz())
            except Exception:
                logger.debug("Sampling %s: failed to resolve hz", self._name, exc_info=True)
                hz = 0.0

            if hz <= 0:
                # Event-driven component: idle until config flips to a poll rate.
                await asyncio.sleep(0.25)
                continue

            try:
                await self._tick()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.warning("Sampling %s tick failed", self._name, exc_info=True)

            await asyncio.sleep(1.0 / hz)
