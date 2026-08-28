"""Event package."""

from irswitch.events.decision_log import DecisionLog
from irswitch.events.engine import EventEngine
from irswitch.events.envelope import EventEnvelope, make_envelope, validate_envelope
from irswitch.events.manager import EventManager
from irswitch.overlay.protocol import CandidateEvent, RaceEvent

__all__ = [
    "CandidateEvent",
    "DecisionLog",
    "EventEngine",
    "EventEnvelope",
    "EventManager",
    "RaceEvent",
    "make_envelope",
    "validate_envelope",
]
