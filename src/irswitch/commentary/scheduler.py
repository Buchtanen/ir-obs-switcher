"""Deferred speech queue for commentary (busy park → idle replay)."""

from __future__ import annotations

import heapq
from dataclasses import dataclass, field

from irswitch.commentary.tts import CommentaryUtterance
from irswitch.overlay.settings import CommentarySchedulerSettings

_INCIDENT_TYPES = frozenset({"INCIDENT", "INVALID_LAP"})
_HOLD_TYPES = frozenset({"INCIDENT", "TRACK_EXCURSION", "INVALID_LAP", "STREAM_END"})
_ALWAYS_PARK = frozenset({"TRACK_EXCURSION", "STREAM_END"})


@dataclass(order=True)
class _HeapItem:
    """Max-heap via negated priority; stable with seq."""

    sort_key: tuple[float, float, int]
    item: DeferredSpeech = field(compare=False)


@dataclass(frozen=True)
class DeferredSpeech:
    utterance: CommentaryUtterance
    priority: float
    expires_at: float
    parked_at: float


@dataclass
class SpeechScheduler:
    """Park one ordinary line plus one incident/excursion hold while TTS is busy.

    Same-class arrivals replace only when priority is higher. After a deferred
    line is spoken, ordinary leftovers are dropped; hold types stay parked.
    """

    settings: CommentarySchedulerSettings = field(default_factory=CommentarySchedulerSettings)
    _heap: list[_HeapItem] = field(default_factory=list)
    _seq: int = 0

    def reset(self) -> None:
        self._heap.clear()
        self._seq = 0

    def __len__(self) -> int:
        return len(self._heap)

    def peek(self) -> DeferredSpeech | None:
        """Inspect the one pending candidate without changing its lifetime."""
        return self._heap[0].item if self._heap else None

    def ttl_for(self, event_type: str) -> float:
        if event_type in _INCIDENT_TYPES:
            return float(self.settings.incident_ttl_s)
        return float(self.settings.default_ttl_s)

    def should_park_while_busy(self, event_type: str) -> bool:
        return bool(self.settings.defer_enabled) or event_type in _ALWAYS_PARK

    def should_hard_interrupt(self, event_type: str, *, current_event_type: str | None) -> bool:
        # Started speech finishes. Stale facts get a same-scenario revision plus
        # apology after the line ends; they do not tear down the audible beat.
        return False

    def park(self, utterance: CommentaryUtterance, *, priority: float, now: float) -> bool:
        """Queue best utterance only. Returns False if dropped (lower prio / disabled)."""
        if not self.should_park_while_busy(utterance.event_type):
            return False
        self.expire(now)
        incoming = float(priority)
        hold = utterance.event_type in _HOLD_TYPES
        same = [
            entry
            for entry in self._heap
            if (entry.item.utterance.event_type in _HOLD_TYPES) == hold
        ]
        other = [
            entry
            for entry in self._heap
            if (entry.item.utterance.event_type in _HOLD_TYPES) != hold
        ]
        if same:
            best_prio = max(entry.item.priority for entry in same)
            if incoming < best_prio:
                return False
        self._heap = other
        expires = now + self.ttl_for(utterance.event_type)
        self._seq += 1
        heapq.heappush(
            self._heap,
            _HeapItem(
                sort_key=(-incoming, float(expires), self._seq),
                item=DeferredSpeech(
                    utterance=utterance,
                    priority=incoming,
                    expires_at=expires,
                    parked_at=now,
                ),
            ),
        )
        # One hold + one ordinary line; config cap is a floor, not a single slot.
        max_n = max(2, int(self.settings.max_deferred))
        while len(self._heap) > max_n:
            if not self._evict_lowest(incoming):
                break
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

    def clear(self) -> list[DeferredSpeech]:
        """Drop all parked items (after one deferred speak — no sequential drain)."""
        dropped = [entry.item for entry in self._heap]
        self._heap.clear()
        return dropped

    def clear_non_hold(self) -> list[DeferredSpeech]:
        """Drop ordinary parked lines; keep incident / excursion for later."""
        dropped: list[DeferredSpeech] = []
        kept: list[_HeapItem] = []
        for entry in self._heap:
            if entry.item.utterance.event_type in _HOLD_TYPES:
                kept.append(entry)
            else:
                dropped.append(entry.item)
        heapq.heapify(kept)
        self._heap = kept
        return dropped

    def silence_due(self, *, last_spoke_at: float | None, now: float) -> bool:
        if last_spoke_at is None:
            return False
        return (now - last_spoke_at) >= float(self.settings.max_silence_s)

    def _evict_lowest(self, incoming_priority: float) -> bool:
        """Evict lowest-priority parked item if incoming is higher-or-equal. Else reject."""
        if not self._heap:
            return True
        lowest = min(self._heap, key=lambda e: (e.item.priority, e.item.parked_at))
        if incoming_priority < lowest.item.priority:
            return False
        self._heap.remove(lowest)
        heapq.heapify(self._heap)
        return True
