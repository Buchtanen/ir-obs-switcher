"""Race SESSION_FLAG FSM: yellow / green / checkered rising edges.

Commentary-only. Does not finish the player or fire SESSION_WRAP.
Start lights are ignored (N7). Yellow family coalesces to one kind.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from irswitch.events.envelope import EventEnvelope, make_envelope
from irswitch.overlay.models import RaceState
from irswitch.race.watcher_log import WatcherLog, note

logger = logging.getLogger(__name__)

SESSION_FLAG = "SESSION_FLAG"
_SESSION_FLAG_PRIORITY = 78
FLAG_COOLDOWN_S = 12.0

YELLOW_FAMILY = frozenset({"yellow", "yellowWaving", "caution", "cautionWaving"})
START_FAMILY = frozenset({"startHidden", "startReady", "startSet", "startGo"})
# Same-tick pick when more than one v1 kind rises.
_KIND_ORDER = ("checkered", "yellow", "green")


def active_flag_kinds(names: tuple[str, ...] | list[str]) -> frozenset[str]:
    """Map raw irsdk names onto v1 speak kinds. Start family is dropped."""
    present = set(names) - START_FAMILY
    kinds: set[str] = set()
    if present & YELLOW_FAMILY:
        kinds.add("yellow")
    if "green" in present:
        kinds.add("green")
    if "checkered" in present:
        kinds.add("checkered")
    return frozenset(kinds)


@dataclass
class SessionFlagFsm:
    """Rising-edge SESSION_FLAG for race yellow / green / checkered."""

    _held: frozenset[str] = field(default_factory=frozenset)
    _cooldown_until: dict[str, float] = field(default_factory=dict)
    _pending: list[EventEnvelope] = field(default_factory=list)

    def reset(self) -> None:
        self._held = frozenset()
        self._cooldown_until.clear()
        self._pending.clear()

    def take_pending(self) -> list[EventEnvelope]:
        out = list(self._pending)
        self._pending.clear()
        return out

    def tick(
        self,
        state: RaceState,
        now: float,
        *,
        enabled: bool,
        log: WatcherLog | None = None,
    ) -> list[EventEnvelope]:
        """Advance FSM. Emit at most one SESSION_FLAG per tick when enabled in RACE."""
        produced: list[EventEnvelope] = []
        if not state.connected:
            self.reset()
            return produced

        kinds = active_flag_kinds(state.session_flag_names)
        rising = kinds - self._held
        self._held = kinds
        if not rising:
            return produced

        kind = next((item for item in _KIND_ORDER if item in rising), None)
        if kind is None:
            return produced

        mode = state.overlay_mode or "GENERIC"
        if mode != "RACE":
            logger.debug("SESSION_FLAG %s ignored outside race (mode=%s)", kind, mode)
            note(
                log,
                watch="flags",
                kind=SESSION_FLAG,
                emitted=False,
                reason="not_race",
                now=now,
            )
            return produced
        if not enabled:
            note(
                log,
                watch="flags",
                kind=SESSION_FLAG,
                emitted=False,
                reason="disabled",
                now=now,
            )
            return produced
        ready_at = self._cooldown_until.get(kind, 0.0)
        if now < ready_at:
            note(
                log,
                watch="flags",
                kind=SESSION_FLAG,
                emitted=False,
                reason="cooldown",
                now=now,
            )
            return produced

        metrics = {
            "kind": kind,
            "branch": kind,
        }
        env = make_envelope(
            event_type=SESSION_FLAG,
            phase="RESULT",
            mode=mode,
            priority=_SESSION_FLAG_PRIORITY,
            monotonic_ms=int(now * 1000),
            metrics=metrics,
            correlation_id=f"session_flag:{kind}",
            dedupe_key=f"{mode}:SESSION_FLAG:{kind}",
        )
        self._cooldown_until[kind] = now + FLAG_COOLDOWN_S
        produced.append(env)
        self._pending.extend(produced)
        note(
            log,
            watch="flags",
            kind=SESSION_FLAG,
            emitted=True,
            reason="rising",
            confidence=1.0,
            now=now,
        )
        return produced
