"""Commentary as an EventFanout peer consumer."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from irswitch.events.envelope import EventEnvelope

ObserveFn = Callable[[list[EventEnvelope], float], Any]


class CommentaryEventConsumer:
    """Adapts OverlayRuntime commentary observe into the EventConsumer protocol."""

    def __init__(self, observe: ObserveFn) -> None:
        self._observe = observe

    def on_envelopes(self, envelopes: list[EventEnvelope], *, now: float) -> None:
        self._observe(envelopes, now)
