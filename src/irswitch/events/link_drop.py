"""Telemetry link-drop emitter (stale / degraded data quality)."""

from __future__ import annotations

from dataclasses import dataclass, field

from irswitch.overlay.models import RaceState
from irswitch.overlay.protocol import CandidateEvent
from irswitch.overlay.settings import EventPrioritySettings

_STALE_QUALITIES = frozenset({"stale", "degraded"})


@dataclass
class LinkDropEmitter:
    priorities: EventPrioritySettings = field(default_factory=EventPrioritySettings)
    _active: bool = False

    def tick(self, state: RaceState, now: float) -> list[CandidateEvent]:  # noqa: ARG002
        quality = (state.data_quality or "ok").lower()
        stale = quality in _STALE_QUALITIES or not state.connected
        if stale:
            if self._active:
                return []
            self._active = True
            return [
                CandidateEvent(
                    name="link_drop",
                    channel="alert",
                    priority=self.priorities.incident,
                    phase="enter",
                    data={
                        "quality": quality,
                        "staleForMs": state.stale_for_ms,
                    },
                    duration=6.0,
                    cooldown=8.0,
                )
            ]
        if self._active:
            self._active = False
            return [
                CandidateEvent(
                    name="link_drop",
                    channel="alert",
                    priority=self.priorities.incident,
                    phase="exit",
                    data={"quality": "ok"},
                )
            ]
        return []

    def reset(self) -> None:
        self._active = False
