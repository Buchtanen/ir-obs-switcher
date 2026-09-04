"""Strict broadcast priority tiers shared by graph, scheduler and TTS."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

_FINISH = frozenset({"FINISH", "SESSION_WRAP", "SESSION_CHECKERED"})
_START = frozenset({"RACE_START", "SESSION_START", "STREAM_START"})
_INCIDENT = frozenset({"INCIDENT", "INVALID_LAP"})
_POSITION = frozenset(
    {
        "OVERTAKE",
        "OVERTAKEN",
        "POSITION_GAINED",
        "POSITION_LOST",
        "LEADER_CHANGE",
    }
)
_BATTLE = frozenset(
    {
        "BATTLE_FOR_POSITION",
        "POSITION_ATTACK",
        "HUNTED",
        "HUNTING",
        "APPROACH",
        "RIVAL_THREAT",
        "SIDE_BY_SIDE",
    }
)
_SECTOR = frozenset({"SECTOR_BEST", "SECTOR_SPLIT"})
_PIT = frozenset({"PIT_ENTRY", "PIT_EXIT", "PIT_STOP", "PIT_WINDOW"})
_LAP = frozenset({"FINAL_LAP", "PERSONAL_BEST", "HOT_LAP", "LAP_COMPLETE"})
_FLAG_PRIORITY = {
    "red": 890,
    "checkered": 880,
    "chequered": 880,
    "yellow": 870,
    "caution": 870,
    "green": 860,
    "restart": 860,
}


def editorial_priority(event_type: str, metrics: Mapping[str, Any] | None = None) -> int:
    """Return a strict tier; graph scoring is only a tie-break inside a tier."""
    event = str(event_type or "").upper()
    if event in _FINISH:
        return 1000
    if event in _START:
        return 900
    if event == "SESSION_FLAG":
        values = metrics or {}
        kind = str(values.get("branch") or values.get("kind") or "").lower()
        return _FLAG_PRIORITY.get(kind, 850)
    if event in _INCIDENT:
        if event == "INCIDENT" and (metrics or {}).get("branch") == "points":
            return 150
        return 800
    if event == "TRACK_EXCURSION":
        return 800
    if event in _POSITION:
        return 700
    if event in _BATTLE:
        return 600
    if event in _SECTOR:
        return 500
    if event in _PIT:
        return 400
    if event in _LAP:
        return 300
    if event == "INCIDENT_AFTERMATH":
        return 250
    if event.startswith("WEATHER_") or event.startswith("SESSION_"):
        return 200
    return 100
