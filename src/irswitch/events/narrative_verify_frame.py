"""Live #270 verify-frame stash for authored/template realization (#284).

Kept separate from ``narrative_realization_bridge`` / ``narrative_runtime`` to
avoid an import cycle through the shadow consumer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

__all__ = [
    "VerifyFrame",
    "stash_live_verify_frame",
    "take_live_verify_frame",
]


@dataclass(frozen=True, slots=True)
class VerifyFrame:
    """#270 claim frame attached on live authored/template realization."""

    family: str
    subject_surface: str
    required_claim_surface: str
    actor_bindings: tuple[tuple[str, tuple[str, ...]], ...]
    required_actors: frozenset[str]

    def as_payload(self) -> dict[str, Any]:
        return {
            "verifyFamily": self.family,
            "verifySubjectSurface": self.subject_surface,
            "verifyRequiredClaimSurface": self.required_claim_surface,
            "verifyActorBindings": [[name, list(forms)] for name, forms in self.actor_bindings],
            "verifyRequiredActors": sorted(self.required_actors),
        }


_LIVE_VERIFY_FRAMES: dict[tuple[str, int, int], VerifyFrame] = {}


def _frame_key(token: dict[str, Any]) -> tuple[str, int, int]:
    return (
        str(token["requestId"]),
        int(token["requestOrdinal"]),
        int(token["dispatchGeneration"]),
    )


def stash_live_verify_frame(token: dict[str, Any], frame: VerifyFrame) -> None:
    """Remember a live authored/template verify frame until the reducer consumes it."""

    _LIVE_VERIFY_FRAMES[_frame_key(token)] = frame
    if len(_LIVE_VERIFY_FRAMES) > 64:
        for stale in list(_LIVE_VERIFY_FRAMES)[: len(_LIVE_VERIFY_FRAMES) - 64]:
            _LIVE_VERIFY_FRAMES.pop(stale, None)


def take_live_verify_frame(token: dict[str, Any] | None) -> VerifyFrame | None:
    """Pop a stashed live verify frame for the realization token, if present."""

    if not isinstance(token, dict):
        return None
    try:
        key = _frame_key(token)
    except (KeyError, TypeError, ValueError):
        return None
    return _LIVE_VERIFY_FRAMES.pop(key, None)
