"""Map accepted RaceEvents to speech envelopes. Overlay path stays unchanged."""

from __future__ import annotations

from irswitch.events.envelope import EventEnvelope, make_envelope
from irswitch.overlay.protocol import RaceEvent

_NAME_TO_EVENT_TYPE = {
    "lap_complete": "LAP_COMPLETE",
    "pit_entry": "PIT_ENTRY",
    "pit_exit": "PIT_EXIT",
}


def speech_envelope_from_race_event(
    event: RaceEvent, *, now: float, mode: str
) -> EventEnvelope | None:
    event_type = _NAME_TO_EVENT_TYPE.get(event.name)
    if event_type is None:
        return None
    metrics = dict(event.data)
    return make_envelope(
        event_type=event_type,
        phase="RESULT",
        mode=mode,
        priority=event.priority,
        monotonic_ms=int(now * 1000),
        metrics=metrics,
        correlation_id=event.name,
    )


def merge_speech_envelopes(
    race_event: RaceEvent | None,
    envelopes: list[EventEnvelope],
    *,
    now: float,
    mode: str,
) -> list[EventEnvelope]:
    """Keep V4 envelopes; add a speech map only when the adapter produced none."""
    merged = list(envelopes)
    if race_event is None:
        return merged
    mapped = speech_envelope_from_race_event(race_event, now=now, mode=mode)
    if mapped is None:
        return merged
    if any(env.event_type == mapped.event_type for env in merged):
        return merged
    merged.append(mapped)
    return merged
