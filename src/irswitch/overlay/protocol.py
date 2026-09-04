"""Typed overlay WebSocket envelopes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from irswitch.events.envelope import EventEnvelope, legacy_trigger_to_phase
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
    confidence: float = 1.0
    reason: str = ""
    scenario_id: str = ""
    episode_id: str = ""
    parent_story_id: str = ""


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


def state_snapshot_envelope(active_stories: list[dict[str, Any]]) -> dict[str, Any]:
    """Authoritative active V4 stories for reconnect (Spec §0.5.1)."""
    return {
        "type": "STATE_SNAPSHOT",
        "activeStories": list(active_stories),
    }


def legacy_from_envelope(envelope: EventEnvelope | dict[str, Any]) -> dict[str, Any]:
    """Down-convert V4 envelope to legacy MVP WS event shape for V3 renderer."""
    data = envelope.to_dict() if hasattr(envelope, "to_dict") else dict(envelope)
    event_type = str(data.get("eventType", "")).lower()
    name = event_type.replace("_", " ")
    if event_type == "lap_complete":
        name = "lap_complete"
    elif event_type == "personal_best":
        name = "personal_best"
    phase_raw = data.get("phase", "RESULT")
    phase = "trigger"
    mapped = legacy_trigger_to_phase(str(phase_raw), default="RESULT")
    phase = mapped.lower() if mapped != "RESULT" else "trigger"
    metrics = data.get("metrics") or {}
    return {
        "type": "event",
        "name": name,
        "phase": phase,
        "channel": "lap" if "lap" in name or name == "personal_best" else "alert",
        "priority": data.get("priority", 0),
        "timestamp": (data.get("monotonicMs") or 0) / 1000.0,
        "data": dict(metrics),
    }
