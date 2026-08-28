"""S2 arbitration helpers: pit-cycle suppression and eviction detection."""

from __future__ import annotations

from dataclasses import dataclass

from irswitch.events.manager import EventManager
from irswitch.overlay.protocol import CandidateEvent, RaceEvent

_PIT_SUPPRESSED = frozenset({"position_change", "overtake"})


@dataclass
class PitCycleGuard:
    """Suppress position/overtake semantics while the player is on pit road."""

    post_exit_grace_s: float = 3.0
    on_pit_road: bool = False
    suppress_until: float = 0.0

    def update(self, on_pit_road: bool, now: float) -> None:
        if on_pit_road:
            self.on_pit_road = True
            self.suppress_until = max(self.suppress_until, now + self.post_exit_grace_s)
            return
        if self.on_pit_road and not on_pit_road:
            self.on_pit_road = False
            self.suppress_until = max(self.suppress_until, now + self.post_exit_grace_s)
            return
        self.on_pit_road = on_pit_road

    def active(self, now: float) -> bool:
        return self.on_pit_road or now < self.suppress_until

    def suppresses(self, candidate: CandidateEvent, now: float) -> bool:
        if candidate.name not in _PIT_SUPPRESSED:
            return False
        if candidate.phase not in {"trigger", "enter"}:
            return False
        return self.active(now)


def slot_key_for_race_event(event: RaceEvent) -> str:
    return EventManager._slot_key(event)


def slot_key_for_candidate(candidate: CandidateEvent) -> str:
    return EventManager._slot_key_candidate(candidate)


def evicted_race_events(before: list[RaceEvent], after: list[RaceEvent]) -> list[RaceEvent]:
    """Return events present before submit but removed afterward (preemption/expiry)."""
    after_keys = {slot_key_for_race_event(event) for event in after}
    return [event for event in before if slot_key_for_race_event(event) not in after_keys]


def suppression_reason_for_none(
    candidate: CandidateEvent,
    *,
    now: float,
    cooldowns: dict[str, float],
    active: list[RaceEvent],
) -> str | None:
    """Best-effort reason when MVP manager rejects a candidate."""
    if candidate.phase in {"update", "exit"}:
        return None
    ready_at = cooldowns.get(candidate.name, 0.0)
    if now < ready_at and candidate.phase == "trigger":
        return "cooldown"
    from irswitch.overlay.display import ActiveSlot, place

    slots = [
        ActiveSlot(channel=e.channel, name=slot_key_for_race_event(e), priority=e.priority)
        for e in active
    ]
    incoming = ActiveSlot(
        channel=candidate.channel,
        name=slot_key_for_candidate(candidate),
        priority=candidate.priority,
    )
    placed = place(slots, incoming)
    if incoming not in placed and not any(
        slot.name == incoming.name and slot.channel == incoming.channel for slot in placed
    ):
        return "lower_priority"
    return None
