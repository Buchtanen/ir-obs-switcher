"""Timing infrastructure: minisectors, crossings, and bounded store."""

from irswitch.race.timing.crossing import CrossingDetector, CrossingEvent
from irswitch.race.timing.points import TimingPoint, default_minisectors
from irswitch.race.timing.store import TimingRecord, TimingStore

__all__ = [
    "CrossingDetector",
    "CrossingEvent",
    "TimingPoint",
    "TimingRecord",
    "TimingStore",
    "default_minisectors",
]
