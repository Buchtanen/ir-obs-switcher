"""Deferred speech queue for commentary (busy park → idle replay)."""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field

from irswitch.commentary.tts import CommentaryUtterance
from irswitch.overlay.settings import CommentarySchedulerSettings

_INCIDENT_TYPES = frozenset({"INCIDENT", "INVALID_LAP"})
_NO_INTERRUPT_TYPES = frozenset({"FINISH", "FINAL_LAP"})


@dataclass(order=True)
class _HeapItem:
    """Max-heap via negated priority; stable with seq."""

    sort_key: tuple[int, float, int]
    item: DeferredSpeech = field(compare=False)


@dataclass(frozen=True)
class DeferredSpeech:
    utterance: CommentaryUtterance
    priority: int
    expires_at: float
    parked_at: float


@dataclass
class SpeechScheduler:
    """Park utterances while TTS is busy; flush by priority when idle."""

    settings: CommentarySchedulerSettings = field(default_factory=CommentarySchedulerSettings)
    _heap: list[_HeapItem] = field(default_factory=list)
    _seq: int = 0

    def reset(self) -> None:
        self._heap.clear()
        self._seq = 0

    def __len__(self) -> int:
        return len(self._heap)

    def ttl_for(self, event_type: str) -> float:
        if event_type in _INCIDENT_TYPES:
            return float(self.settings.incident_ttl_s)
        return float(self.settings.default_ttl_s)

    def should_hard_interrupt(self, event_type: str, *, current_event_type: str | None) -> bool:
        if not self.settings.hard_interrupt:
            return False
        if event_type not in _INCIDENT_TYPES:
            return False
        if current_event_type in _NO_INTERRUPT_TYPES:
            return False
        return True

    def park(self, utterance: CommentaryUtterance, *, priority: int, now: float) -> bool:
        """Queue utterance. Returns False if dropped (full / disabled)."""
        if not self.settings.defer_enabled:
            return False
        self.expire(now)
        if len(self._heap) >= max(1, int(self.settings.max_deferred)):
            if not self._evict_lowest(priority):
                return False
        expires = now + self.ttl_for(utterance.event_type)
        self._seq += 1
        heapq.heappush(
            self._heap,
            _HeapItem(
                sort_key=(-int(priority), float(expires), self._seq),
                item=DeferredSpeech(
                    utterance=utterance,
                    priority=int(priority),
                    expires_at=expires,
                    parked_at=now,
                ),
            ),
        )
        return True

    def expire(self, now: float) -> list[DeferredSpeech]:
        """Drop expired entries; return them for decision logging."""
        kept: list[_HeapItem] = []
        expired: list[DeferredSpeech] = []
        for entry in self._heap:
            if entry.item.expires_at <= now:
                expired.append(entry.item)
            else:
                kept.append(entry)
        if expired:
            heapq.heapify(kept)
            self._heap = kept
        return expired

    def pop_ready(self, now: float) -> DeferredSpeech | None:
        """Best non-expired deferred item, or None."""
        self.expire(now)
        if not self._heap:
            return None
        entry = heapq.heappop(self._heap)
        return entry.item

    def silence_due(self, *, last_spoke_at: float | None, now: float) -> bool:
        if last_spoke_at is None:
            return False
        return (now - last_spoke_at) >= float(self.settings.max_silence_s)

    def _evict_lowest(self, incoming_priority: int) -> bool:
        """Evict lowest-priority parked item if incoming is higher-or-equal. Else reject."""
        if not self._heap:
            return True
        lowest = min(self._heap, key=lambda e: (e.item.priority, e.item.parked_at))
        if incoming_priority < lowest.item.priority:
            return False
        self._heap.remove(lowest)
        heapq.heapify(self._heap)
        return True
