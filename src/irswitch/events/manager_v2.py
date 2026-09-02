"""EventManager v2: sequence stamping + V4 envelopes + S2 arbitration."""

from __future__ import annotations

from dataclasses import replace
from typing import Any, cast

from irswitch.events.adapters import race_event_to_envelope
from irswitch.events.arbitration import (
    PitCycleGuard,
    suppression_reason_for_none,
)
from irswitch.events.decision_log import DecisionLog
from irswitch.events.envelope import EventEnvelope
from irswitch.events.manager import EventManager
from irswitch.events.stream import SessionSequenceAllocator
from irswitch.overlay.protocol import CandidateEvent, RaceEvent
from irswitch.overlay.settings import EventSettings

# Lifecycle identity is fixed at acceptance, not reconstructed from mutable telemetry.
_RELATION_IDENTITY_FIELDS = (
    "heroCarIdx",
    "direction",
    "targetCarIdx",
    "relationEpoch",
    "runEpoch",
    "frontTargetCarIdx",
    "frontRelationEpoch",
    "rearTargetCarIdx",
    "rearRelationEpoch",
)


class EventManagerV2:
    """Wraps MVP manager; publishes V4 envelopes for supported event types."""

    def __init__(
        self,
        settings: EventSettings | None = None,
        session_id: str = "",
        *,
        decision_log: DecisionLog | None = None,
        pit_guard: PitCycleGuard | None = None,
        sequence_allocator: SessionSequenceAllocator | None = None,
    ) -> None:
        self._settings = settings or EventSettings()
        self._inner = EventManager(self._settings)
        self._session_id = session_id
        self._run_epoch = 0
        self._sequence_allocator = sequence_allocator or SessionSequenceAllocator(
            session_id or "session:unknown"
        )
        self._active_v4: list[EventEnvelope] = []
        self._accepted: dict[int, EventEnvelope] = {}
        self.unmatched_exits = 0
        self.decisions = decision_log or DecisionLog()
        self._pit_guard = pit_guard or PitCycleGuard()

    @property
    def session_id(self) -> str:
        return self._session_id

    def set_session_id(self, session_id: str) -> None:
        self._session_id = session_id
        if self._sequence_allocator.session_id != session_id:
            self._sequence_allocator.reset(session_id)

    def set_run_epoch(self, run_epoch: int) -> None:
        """Set the producer run namespace after its coordinated lifecycle reset."""
        self._run_epoch = max(0, int(run_epoch))

    def reset(self) -> None:
        self._inner = EventManager(self._settings)
        self._sequence_allocator.reset(self._session_id or "session:unknown")
        self._active_v4.clear()
        self._accepted.clear()
        self.unmatched_exits = 0
        self.decisions.clear()
        self._pit_guard = PitCycleGuard()

    @property
    def legacy(self) -> EventManager:
        return self._inner

    def active_events(self) -> list[dict[str, Any]]:
        return cast("list[dict[str, Any]]", self._inner.active_events())

    def active_stories_v4(self) -> list[dict]:
        return [env.to_dict() for env in self._active_v4]

    def update_pit_state(self, on_pit_road: bool, now: float) -> None:
        self._pit_guard.update(on_pit_road, now)

    def submit(
        self,
        candidate: CandidateEvent,
        now: float,
        *,
        mode: str = "GENERIC",
    ) -> tuple[RaceEvent | None, list[EventEnvelope]]:
        if self._pit_guard.suppresses(candidate, now):
            self._record(candidate.name, "suppressed", "pit_cycle", now=now)
            return None, []

        before = list(self._inner._active)
        if candidate.phase in {"update", "exit"}:
            resolved = self._resolve_lifecycle_candidate(candidate, before, now=now)
            if resolved is None:
                return None, []
            candidate = resolved
        race_event = self._inner.submit(candidate, now)
        exit_envelopes = self._exit_envelopes_for_evictions(
            before,
            now=now,
            mode=mode,
            explicit_exit=race_event if candidate.phase == "exit" else None,
        )

        if race_event is None:
            reason = suppression_reason_for_none(
                candidate,
                now=now,
                cooldowns=self._inner._cooldowns,
                active=before,
            )
            if reason:
                self._record(candidate.name, "suppressed", reason, now=now)
            return None, exit_envelopes

        new_envelopes = self._envelopes_for_race_event(race_event, now=now, mode=mode)
        return race_event, exit_envelopes + new_envelopes

    def tick(
        self, now: float, *, mode: str = "GENERIC"
    ) -> list[tuple[RaceEvent, list[EventEnvelope]]]:
        expired = self._inner.tick(now)
        out: list[tuple[RaceEvent, list[EventEnvelope]]] = []
        for race_event in expired:
            base = self._accepted.pop(id(race_event), None) or race_event_to_envelope(
                race_event, session_id=self._session_id, mode=mode, now=now
            )
            if base is None:
                out.append((race_event, []))
                continue
            exit_env = self._stamp(replace(base, phase="EXIT", monotonic_ms=int(now * 1000)))
            self._remove_active_v4(exit_env.correlation_id)
            out.append((race_event, [exit_env]))
        return out

    def inject(
        self, name: str, now: float, data: dict | None = None
    ) -> tuple[RaceEvent | None, list[EventEnvelope]]:
        race_event = self._inner.inject(name, now, data=data)
        if race_event is None:
            return None, []
        return race_event, self._envelopes_for_race_event(race_event, now=now, mode="GENERIC")

    def publish_wire(
        self, envelopes: list[EventEnvelope], race_event: RaceEvent | None
    ) -> list[dict]:
        if envelopes:
            return [event_v4_wire(env) for env in envelopes]
        if race_event is not None:
            return [race_event.to_envelope()]
        return []

    def _exit_envelopes_for_evictions(
        self,
        before: list[RaceEvent],
        *,
        now: float,
        mode: str,
        explicit_exit: RaceEvent | None = None,
    ) -> list[EventEnvelope]:
        envelopes: list[EventEnvelope] = []
        remaining_ids = {id(event) for event in self._inner._active}
        for evicted in before:
            if id(evicted) in remaining_ids or evicted is explicit_exit:
                continue
            base = self._accepted.pop(id(evicted), None) or race_event_to_envelope(
                evicted, session_id=self._session_id, mode=mode, now=now
            )
            if base is None:
                continue
            exit_env = self._stamp(replace(base, phase="EXIT", monotonic_ms=int(now * 1000)))
            self._remove_active_v4(exit_env.correlation_id)
            self._record(base.event_type, "preempted", "lower_priority", now=now)
            envelopes.append(exit_env)
        return envelopes

    def _envelopes_for_race_event(
        self, event: RaceEvent, *, now: float, mode: str
    ) -> list[EventEnvelope]:
        base = race_event_to_envelope(
            event,
            session_id=self._session_id,
            mode=mode,
            now=now,
        )
        if base is None:
            return []
        accepted = self._accepted.get(id(event))
        if accepted is not None:
            # Retain accepted subject/target and the exact key even if an adapter's
            # current context differs. Metrics remain live for legitimate updates.
            base = replace(
                base,
                correlation_id=accepted.correlation_id,
                story_key=accepted.story_key,
                dedupe_key=accepted.dedupe_key,
                subject=accepted.subject,
                target=(
                    replace(accepted.target, class_position=base.target.class_position)
                    if accepted.target is not None and base.target is not None
                    else accepted.target
                ),
                metrics={**accepted.metrics, **base.metrics},
            )
        stamped = self._stamp(base)
        envelopes = [stamped]
        if stamped.phase == "EXIT":
            self._accepted.pop(id(event), None)
            self._remove_active_v4(stamped.correlation_id)
        elif stamped.phase == "ENTER" and stamped.presentation.preferred_state == "ACTIVE":
            active = self._stamp(replace(stamped, phase="ACTIVE"))
            envelopes.append(active)
            self._sync_active_v4(active)
        elif stamped.phase not in {"RESULT", "EXIT"}:
            self._sync_active_v4(stamped)
        if stamped.phase != "EXIT":
            self._accepted[id(event)] = stamped
        self._record(stamped.event_type, "emitted", "accepted", now=now)
        return envelopes

    def _resolve_lifecycle_candidate(
        self, candidate: CandidateEvent, active: list[RaceEvent], *, now: float
    ) -> CandidateEvent | None:
        matching = next(
            (
                event
                for event in active
                if event.name == candidate.name
                and event.channel == candidate.channel
                and event.data.get("state") == candidate.data.get("state")
            ),
            None,
        )
        if matching is not None:
            # An old explicit EXIT must not remove a replacement in the same slot.
            mismatch = any(
                key in candidate.data and candidate.data[key] != matching.data.get(key)
                for key in _RELATION_IDENTITY_FIELDS
                if key in matching.data
            )
            if not mismatch:
                return replace(candidate, data={**matching.data, **candidate.data})
        if candidate.phase == "exit":
            self.unmatched_exits += 1
            self._record(candidate.name, "ignored", "unmatched_exit", now=now)
        else:
            self._record(candidate.name, "ignored", "unmatched_update", now=now)
        return None

    def _record(self, event_type: str, action: str, reason: str, *, now: float) -> None:
        self.decisions.record(event_type, action, reason, now=now)

    def _stamp(self, envelope: EventEnvelope) -> EventEnvelope:
        prefix = f"run:{self._run_epoch}:" if self._run_epoch else ""

        def namespaced(key: str) -> str:
            return prefix + key if prefix and key and not key.startswith(prefix) else key

        envelope = replace(
            envelope,
            correlation_id=namespaced(envelope.correlation_id),
            story_key=namespaced(envelope.story_key),
            dedupe_key=namespaced(envelope.dedupe_key),
            metrics={**envelope.metrics, "runEpoch": self._run_epoch},
        )
        return self._sequence_allocator.stamp(envelope)

    def _sync_active_v4(self, envelope: EventEnvelope) -> None:
        if envelope.phase in {"RESULT", "EXIT"}:
            return
        cid = envelope.correlation_id
        self._active_v4 = [e for e in self._active_v4 if e.correlation_id != cid]
        self._active_v4.append(envelope)

    def _remove_active_v4(self, correlation_id: str) -> None:
        self._active_v4 = [e for e in self._active_v4 if e.correlation_id != correlation_id]


def event_v4_wire(envelope: EventEnvelope) -> dict[str, Any]:
    payload = envelope.to_dict()
    payload["type"] = "event"
    payload["format"] = "v4"
    return cast("dict[str, Any]", payload)
