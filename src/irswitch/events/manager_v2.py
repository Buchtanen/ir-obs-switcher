"""EventManager v2: sequence stamping + V4 envelopes + S2 arbitration."""

from __future__ import annotations

from dataclasses import replace

from irswitch.events.adapters import race_event_to_envelope
from irswitch.events.arbitration import (
    PitCycleGuard,
    evicted_race_events,
    suppression_reason_for_none,
)
from irswitch.events.decision_log import DecisionLog
from irswitch.events.envelope import EventEnvelope
from irswitch.events.manager import EventManager
from irswitch.overlay.protocol import CandidateEvent, RaceEvent
from irswitch.overlay.settings import EventSettings


class EventManagerV2:
    """Wraps MVP manager; publishes V4 envelopes for supported event types."""

    def __init__(
        self,
        settings: EventSettings | None = None,
        session_id: str = "",
        *,
        decision_log: DecisionLog | None = None,
        pit_guard: PitCycleGuard | None = None,
    ) -> None:
        self._settings = settings or EventSettings()
        self._inner = EventManager(self._settings)
        self._session_id = session_id
        self._sequence = 0
        self._active_v4: list[EventEnvelope] = []
        self.decisions = decision_log or DecisionLog()
        self._pit_guard = pit_guard or PitCycleGuard()

    @property
    def session_id(self) -> str:
        return self._session_id

    def set_session_id(self, session_id: str) -> None:
        self._session_id = session_id

    def reset(self) -> None:
        self._inner = EventManager(self._settings)
        self._sequence = 0
        self._active_v4.clear()
        self.decisions.clear()
        self._pit_guard = PitCycleGuard()

    @property
    def legacy(self) -> EventManager:
        return self._inner

    def active_events(self) -> list[dict]:
        return self._inner.active_events()

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
        race_event = self._inner.submit(candidate, now)
        exit_envelopes = self._exit_envelopes_for_evictions(before, now=now, mode=mode)

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
            base = race_event_to_envelope(
                race_event,
                session_id=self._session_id,
                mode=mode,
                now=now,
            )
            if base is None:
                out.append((race_event, []))
                continue
            exit_env = self._stamp(replace(base, phase="EXIT"))
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
    ) -> list[EventEnvelope]:
        envelopes: list[EventEnvelope] = []
        for evicted in evicted_race_events(before, self._inner._active):
            base = race_event_to_envelope(
                evicted,
                session_id=self._session_id,
                mode=mode,
                now=now,
            )
            if base is None:
                continue
            exit_env = self._stamp(replace(base, phase="EXIT"))
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
        stamped = self._stamp(base)
        envelopes = [stamped]
        if stamped.phase == "ENTER" and stamped.presentation.preferred_state == "ACTIVE":
            active = self._stamp(replace(stamped, phase="ACTIVE"))
            envelopes.append(active)
            self._sync_active_v4(active)
        elif stamped.phase not in {"RESULT", "EXIT"}:
            self._sync_active_v4(stamped)
        self._record(stamped.event_type, "emitted", "accepted", now=now)
        return envelopes

    def _record(self, event_type: str, action: str, reason: str, *, now: float) -> None:
        self.decisions.record(event_type, action, reason, now=now)

    def _stamp(self, envelope: EventEnvelope) -> EventEnvelope:
        self._sequence += 1
        envelope.stamp(
            f"{self._session_id}:{envelope.event_type}:{self._sequence}",
            self._sequence,
        )
        return envelope

    def _sync_active_v4(self, envelope: EventEnvelope) -> None:
        if envelope.phase in {"RESULT", "EXIT"}:
            return
        cid = envelope.correlation_id
        self._active_v4 = [e for e in self._active_v4 if e.correlation_id != cid]
        self._active_v4.append(envelope)

    def _remove_active_v4(self, correlation_id: str) -> None:
        self._active_v4 = [e for e in self._active_v4 if e.correlation_id != correlation_id]


def event_v4_wire(envelope: EventEnvelope) -> dict:
    payload = envelope.to_dict()
    payload["type"] = "event"
    payload["format"] = "v4"
    return payload
