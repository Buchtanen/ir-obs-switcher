"""Process-local one-shot ManualAdmissionLatch (#273 / #284).

Rendezvous only: not a speech waiter, prepared-text queue, actor input, or
replayed DTO. States ``pending | actor_claimed | caller_abandoned``. Not
exported from ``events/__init__.py``.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from irswitch.events.narrative_runtime import ManualSpeakOutcome

LatchState = Literal["pending", "actor_claimed", "caller_abandoned"]

ADMISSION_TIMEOUT_S = 1.0


@dataclass(slots=True)
class ManualAdmissionLatch:
    """One-shot pending → actor_claimed | caller_abandoned rendezvous."""

    state: LatchState = "pending"
    _outcome: ManualSpeakOutcome | None = None
    _done: asyncio.Event = field(default_factory=asyncio.Event)

    def claim_actor(self) -> bool:
        """Atomically ``pending → actor_claimed``. False if already left pending."""

        if self.state != "pending":
            return False
        self.state = "actor_claimed"
        return True

    def abandon_caller(self) -> bool:
        """Atomically ``pending → caller_abandoned``. False if actor already claimed."""

        if self.state != "pending":
            return False
        self.state = "caller_abandoned"
        return True

    def resolve(self, outcome: ManualSpeakOutcome) -> None:
        """Publish the actor's admission decision (only after ``claim_actor``)."""

        self._outcome = outcome
        self._done.set()

    @property
    def outcome(self) -> ManualSpeakOutcome | None:
        return self._outcome

    async def wait(self, timeout_s: float = ADMISSION_TIMEOUT_S) -> ManualSpeakOutcome | None:
        """Wait for ``resolve``. Returns ``None`` on timeout (caller may abandon)."""

        try:
            await asyncio.wait_for(self._done.wait(), timeout=timeout_s)
        except TimeoutError:
            return None
        return self._outcome


__all__ = ["ADMISSION_TIMEOUT_S", "LatchState", "ManualAdmissionLatch"]
