"""Typed overlay WebSocket envelopes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from irswitch.overlay.models import BioState, RaceState, SystemState


@dataclass(frozen=True)
class CandidateEvent:
    """Emitter output. Manager owns duration/cooldown/lifecycle."""

    name: str
    channel: str
    priority: int
    phase: str = "trigger"  # enter/update/exit/trigger
    data: dict[str, Any] = field(default_factory=dict)
    duration: float | None = None
    cooldown: float | None = None
    overlay: bool = True


@dataclass
class RaceEvent:
    name: str
    channel: str
    priority: int
    phase: str
    timestamp: float
    data: dict[str, Any] = field(default_factory=dict)
    duration: float = 4.0
    cooldown: float = 0.0
    expires_at: float = 0.0
    overlay: bool = True

    def to_envelope(self) -> dict[str, Any]:
        return {
            "type": "event",
            "name": self.name,
            "phase": self.phase,
            "channel": self.channel,
            "priority": self.priority,
            "timestamp": self.timestamp,
            "data": self.data,
        }

    def to_active_dict(self) -> dict[str, Any]:
        env = self.to_envelope()
        env["expires_at"] = self.expires_at
        return env


def state_envelope(domain: str, data: dict[str, Any]) -> dict[str, Any]:
    return {"type": "state", "domain": domain, "data": data}


def snapshot_envelope(
    race: RaceState | dict[str, Any] | None,
    bio: BioState | dict[str, Any] | None,
    system: SystemState | dict[str, Any] | None,
    active_events: list[dict[str, Any]],
) -> dict[str, Any]:
    def _dump(value: RaceState | BioState | SystemState | dict[str, Any] | None) -> dict[str, Any]:
        if value is None:
            return {}
        if isinstance(value, dict):
            return dict(value)
        return value.to_dict()

    return {
        "type": "snapshot",
        "race": _dump(race),
        "bio": _dump(bio),
        "system": _dump(system),
        "activeEvents": list(active_events),
    }
