"""Session identity, mode routing, warm-up, and atomic reset coordination.

Spec §21 failure modes. Does not own iRacing SDK reads — callers feed ids.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Overlay event-engine modes (envelope `mode` field).
MODE_PRACTICE = "PRACTICE"
MODE_QUALIFYING = "QUALIFYING"
MODE_RACE = "RACE"
MODE_GENERIC = "GENERIC"

_SESSION_TYPE_TO_MODE: dict[str, str] = {
    "practice": MODE_PRACTICE,
    "practise": MODE_PRACTICE,
    "qualify": MODE_QUALIFYING,
    "qualifying": MODE_QUALIFYING,
    "race": MODE_RACE,
    "warmup": MODE_GENERIC,
    "test": MODE_GENERIC,
}

DEFAULT_WARMUP_SEC = 4.0


def overlay_mode_from_session_type(session_type: str | None) -> str:
    """Map iRacing session type string to envelope mode. Unknown → GENERIC."""
    if not session_type:
        return MODE_GENERIC
    return _SESSION_TYPE_TO_MODE.get(session_type.strip().lower(), MODE_GENERIC)


def build_session_key(
    *,
    subsession_id: str | int | None,
    session_num: int | None,
    track_id: str | int | None,
) -> str | None:
    """Stable session key for reset detection. None if not enough identity yet."""
    if subsession_id is None and session_num is None and track_id is None:
        return None
    return f"{subsession_id or '-'}:{session_num if session_num is not None else '-'}:{track_id or '-'}"


ResetHook = Callable[[], None]


@dataclass
class SessionCoordinator:
    """Tracks session key changes, warm-up after reconnect, and reset hooks."""

    warmup_sec: float = DEFAULT_WARMUP_SEC
    _session_key: str | None = None
    _connected: bool = False
    _warmup_until: float = 0.0
    _hooks: list[ResetHook] | None = None

    def __post_init__(self) -> None:
        if self._hooks is None:
            self._hooks = []

    @property
    def session_key(self) -> str | None:
        return self._session_key

    def add_reset_hook(self, hook: ResetHook) -> None:
        assert self._hooks is not None
        self._hooks.append(hook)

    def clear_hooks(self) -> None:
        self._hooks = []

    def in_warmup(self, now: float) -> bool:
        return now < self._warmup_until

    def note_connection(self, connected: bool, now: float) -> None:
        """Start warm-up only when telemetry returns after a drop (not first connect)."""
        if connected and not self._connected and self._session_key is not None:
            self._warmup_until = now + self.warmup_sec
            logger.info("Telemetry reconnect warm-up until +%.1fs", self.warmup_sec)
        if not connected:
            self._warmup_until = 0.0
        self._connected = connected

    def observe(
        self,
        *,
        session_key: str | None,
        connected: bool,
        now: float,
    ) -> bool:
        """Update connection/session. Returns True if an atomic reset ran."""
        self.note_connection(connected, now)
        if not connected or session_key is None:
            return False
        if session_key == self._session_key:
            return False
        prev = self._session_key
        self._session_key = session_key
        self._run_reset()
        logger.info("Session key changed %s -> %s; stores reset", prev, session_key)
        return True

    def force_reset(self) -> None:
        self._run_reset()

    def _run_reset(self) -> None:
        assert self._hooks is not None
        for hook in self._hooks:
            try:
                hook()
            except Exception:
                logger.warning("Session reset hook failed", exc_info=True)
