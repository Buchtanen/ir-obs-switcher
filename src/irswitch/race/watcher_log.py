"""N10: bounded watcher decision ring (debug only, no public API).

Keep INFO quiet: emit DEBUG on each record. Size is a code constant.
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

WATCHER_LOG_SIZE = 64

WATCH_BY_EVENT: dict[str, str] = {
    "SESSION_FLAG": "flags",
    "INCIDENT": "incidents",
    "INCIDENT_AFTERMATH": "aftermath",
    "BACK_UNDER_WAY": "aftermath",
    "PACE_HUNT": "hunt",
    "QUALI_RECAP": "grid_story",
    "PARADE_PAD": "grid_story",
    "FIELD_FACT": "briefs",
    "WEATHER_CHANGE": "briefs",
    "SESSION_WRAP": "briefs",
    "LEADER_CHANGE": "briefs",
    "SESSION_PREVIEW": "briefs",
}

WATCHER_EVENT_TYPES = frozenset(WATCH_BY_EVENT)


def watch_name_for(event_type: str) -> str | None:
    return WATCH_BY_EVENT.get(str(event_type))


def note(
    log: WatcherLog | None,
    *,
    watch: str,
    kind: str,
    emitted: bool,
    reason: str,
    confidence: float | None = None,
    now: float | None = None,
) -> None:
    if log is None:
        return
    log.record(
        watch=watch,
        kind=kind,
        emitted=emitted,
        reason=reason,
        confidence=confidence,
        now=now,
    )


@dataclass(frozen=True, slots=True)
class WatcherEntry:
    watch: str
    kind: str
    emitted: bool
    reason: str
    confidence: float | None
    mono_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "watch": self.watch,
            "kind": self.kind,
            "emitted": self.emitted,
            "reason": self.reason,
            "confidence": self.confidence,
            "mono_ms": self.mono_ms,
        }


class WatcherLog:
    """Last N watcher decisions. Survives session reset; clear on stream reset."""

    def __init__(self, *, size: int = WATCHER_LOG_SIZE) -> None:
        self._size = max(1, int(size))
        self._ring: deque[WatcherEntry] = deque(maxlen=self._size)

    def record(
        self,
        *,
        watch: str,
        kind: str,
        emitted: bool,
        reason: str,
        confidence: float | None = None,
        now: float | None = None,
    ) -> WatcherEntry:
        ts = time.monotonic() if now is None else now
        entry = WatcherEntry(
            watch=str(watch),
            kind=str(kind),
            emitted=bool(emitted),
            reason=str(reason),
            confidence=confidence,
            mono_ms=int(ts * 1000.0),
        )
        self._ring.append(entry)
        logger.debug(
            "watcher %s %s emitted=%s reason=%s",
            entry.watch,
            entry.kind,
            entry.emitted,
            entry.reason,
        )
        return entry

    def latest(self, n: int | None = None) -> list[WatcherEntry]:
        if n is None or n >= len(self._ring):
            return list(self._ring)
        take = max(0, int(n))
        if take == 0:
            return []
        return list(self._ring)[-take:]

    def clear(self) -> None:
        self._ring.clear()

    def __len__(self) -> int:
        return len(self._ring)
