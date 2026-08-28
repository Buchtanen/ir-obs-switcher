"""Event package."""

from irswitch.events.manager import EventManager
from irswitch.overlay.protocol import CandidateEvent, RaceEvent

__all__ = ["CandidateEvent", "EventManager", "RaceEvent"]
