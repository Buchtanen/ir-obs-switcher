"""One-winner mutex for stream / intro / in-car / preview openers."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_OPENER_HOLD_S = 120.0

STREAM_START = "STREAM_START"
ENTER_CAR = "ENTER_CAR"
SESSION_PREVIEW = "SESSION_PREVIEW"
SESSION_INTROS = frozenset(
    {
        "SESSION_INTRO_PRACTICE",
        "SESSION_INTRO_QUALIFY",
        "SESSION_INTRO_RACE",
    }
)
OPENER_EVENTS = frozenset({STREAM_START, ENTER_CAR, SESSION_PREVIEW}) | SESSION_INTROS


@dataclass
class OpenerMutex:
    """At most one opener family speaks inside ``hold_s``.

    STREAM_START always wins the window (welcome, no replay in-car).
    ENTER_CAR and session intro/preview share the same lock.
    SESSION_WRAP is not an opener.
    """

    hold_s: float = DEFAULT_OPENER_HOLD_S
    _kind: str | None = None
    _until: float = 0.0

    def reset(self) -> None:
        self._kind = None
        self._until = 0.0

    def skip_reason(self, event_type: str, now: float) -> str | None:
        if event_type not in OPENER_EVENTS:
            return None
        if event_type == STREAM_START:
            return None
        if self._kind is None or now >= self._until:
            return None
        return "opener_mutex"

    def note(self, event_type: str, now: float) -> None:
        if event_type not in OPENER_EVENTS:
            return
        self._kind = event_type
        self._until = now + max(0.0, float(self.hold_s))
