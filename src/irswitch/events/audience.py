"""Audience metadata for the shared accepted stream."""

from __future__ import annotations

from irswitch.events.stream import Audience

# Facts that must receive normal producer identity and reach both subscriptions,
# but have no HUD presentation. Overlay accounts for and discards them.
COMMENTARY_ONLY_EVENTS = frozenset(
    {
        "ENTER_CAR",
        "SESSION_INTRO_PRACTICE",
        "SESSION_INTRO_QUALIFY",
        "SESSION_INTRO_RACE",
        "SOF_BRIEF",
        "WEATHER_BRIEF",
        "WEATHER_CHANGE",
        "FIELD_FACT",
        "INCIDENT_AFTERMATH",
        "BACK_UNDER_WAY",
        "SESSION_WRAP",
        "SESSION_PREVIEW",
        "SESSION_CHECKERED",
        "SESSION_FLAG",
        "STREAM_START",
        "PACE_HUNT",
        "QUALI_RECAP",
        "PARADE_PAD",
    }
)


def audiences_for_event(event_type: str) -> tuple[Audience, ...]:
    if event_type in COMMENTARY_ONLY_EVENTS:
        return ("commentary",)
    return ("overlay", "commentary")
