"""#284 NarrativeRuntime owned tape flush effect bridge.

Wraps ``commentary.tape_writer.NarrativeTapeWriter.aclose`` as an EffectWorker
so shutdown can flush/close the writer under actor ownership. Not exported from
``events/__init__.py``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from irswitch.commentary.tape_writer import CLOSE_REASONS, NarrativeTapeWriter
from irswitch.contracts.command import NarrativeCommand

EffectWorker = Callable[
    [dict[str, Any]],
    Awaitable[NarrativeCommand | Sequence[NarrativeCommand] | None],
]


def build_tape_flush_effect(writer: NarrativeTapeWriter) -> EffectWorker:
    """Return an effect that fail-soft closes ``writer`` on shutdown flush."""

    async def tape_flush(token: dict[str, Any]) -> NarrativeCommand | None:
        reason = str(token.get("reason") or "shutdown")
        try:
            await writer.aclose(reason if reason in CLOSE_REASONS else "shutdown")
        except Exception:
            # Fail-soft: runtime timeout path reports degraded health separately.
            return None
        return None

    return tape_flush
