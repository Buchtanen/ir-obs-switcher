"""EventManager v2: sequence stamping + V4 envelopes (S1 lap + battle slice)."""

from __future__ import annotations

from dataclasses import replace

from irswitch.events.adapters import race_event_to_envelope
from irswitch.events.envelope import EventEnvelope
from irswitch.events.manager import EventManager
from irswitch.overlay.protocol import CandidateEvent, RaceEvent
from irswitch.overlay.settings import EventSettings


class EventManagerV2:
    """Wraps MVP manager; publishes V4 envelopes for supported event types."""

    def __init__(self, settings: EventSettings | None = None, session_id: str = "") -> None:
        self._settings = settings or EventSettings()
        self._inner = EventManager(self._settings)
        self._session_id = session_id
        self._sequence = 0
        self._active_v4: list[EventEnvelope] = []

    @property
    def session_id(self) -> str:
        return self._session_id

    def set_session_id(self, session_id: str) -> None:
        self._session_id = session_id

    def reset(self) -> None:
        self._inner = EventManager(self._settings)
        self._sequence = 0
        self._active_v4.clear()

    @property
    def legacy(self) -> EventManager:
        return self._inner

    def active_events(self) -> list[dict]:
        return self._inner.active_events()

    def active_stories_v4(self) -> list[dict]:
        return [env.to_dict() for env in self._active_v4]

    def submit(
        self,
        candidate: CandidateEvent,
        now: float,
        *,
        mode: str = "GENERIC",
    ) -> tuple[RaceEvent | None, list[EventEnvelope]]:
        race_event = self._inner.submit(candidate, now)
        if race_event is None:
            return None, []
        return race_event, self._envelopes_for_race_event(race_event, now=now, mode=mode)

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
        return envelopes

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
