"""EventManager v2: sequence stamping + V4 envelopes (S1 lap slice)."""

from __future__ import annotations

from irswitch.events.adapters.lap import lap_race_event_to_envelope
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
    ) -> tuple[RaceEvent | None, EventEnvelope | None]:
        race_event = self._inner.submit(candidate, now)
        if race_event is None:
            return None, None
        envelope = self._to_envelope(race_event, now=now, mode=mode)
        if envelope is not None:
            self._sequence += 1
            envelope.stamp(
                f"{self._session_id}:{envelope.event_type}:{self._sequence}",
                self._sequence,
            )
            self._sync_active_v4(envelope)
        return race_event, envelope

    def tick(
        self, now: float, *, mode: str = "GENERIC"
    ) -> list[tuple[RaceEvent, EventEnvelope | None]]:
        expired = self._inner.tick(now)
        out: list[tuple[RaceEvent, EventEnvelope | None]] = []
        for race_event in expired:
            envelope = self._to_envelope(race_event, now=now, mode=mode)
            if envelope is not None:
                envelope.phase = "EXIT"
                self._sequence += 1
                envelope.stamp(
                    f"{self._session_id}:{envelope.event_type}:{self._sequence}",
                    self._sequence,
                )
                self._remove_active_v4(envelope.correlation_id)
            out.append((race_event, envelope))
        return out

    def inject(
        self, name: str, now: float, data: dict | None = None
    ) -> tuple[RaceEvent | None, EventEnvelope | None]:
        race_event = self._inner.inject(name, now, data=data)
        if race_event is None:
            return None, None
        envelope = self._to_envelope(race_event, now=now, mode="GENERIC")
        if envelope is not None:
            self._sequence += 1
            envelope.stamp(
                f"{self._session_id}:{envelope.event_type}:{self._sequence}",
                self._sequence,
            )
            self._sync_active_v4(envelope)
        return race_event, envelope

    def publish_wire(
        self, envelope: EventEnvelope | None, race_event: RaceEvent | None
    ) -> dict | None:
        if envelope is not None:
            return event_v4_wire(envelope)
        if race_event is not None:
            return race_event.to_envelope()
        return None

    def _to_envelope(self, event: RaceEvent, *, now: float, mode: str) -> EventEnvelope | None:
        return lap_race_event_to_envelope(
            event,
            session_id=self._session_id,
            mode=mode,
            now=now,
        )

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


def wire_event_from_v2(
    race_event: RaceEvent | None,
    envelope: EventEnvelope | None,
) -> dict | None:
    if envelope is not None:
        return event_v4_wire(envelope)
    if race_event is not None:
        return race_event.to_envelope()
    return None
