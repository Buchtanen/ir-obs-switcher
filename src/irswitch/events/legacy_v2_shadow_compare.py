"""#272 legacy↔v2 shadow comparison — first observational slice.

Observation-only director decision compare for one family (`lap`) behind a
private in-module route table. Never admits speech, never mutates mailbox /
TTS, and never owns StreamTimeline / FactView truth.

Not exported from ``events/__init__.py``. Temporary branch harness — must not
survive the final v2 cutover PR (see ``docs/v2.0.0/final-pr-exclusion-manifest.md``).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

from irswitch.events.story_director import (
    DirectorCandidate,
    DirectorWorld,
    StoryDirector,
)

Route = Literal["legacy", "v2", "shadow"]
Aspect = Literal["event", "episode", "director"]

# Private development control — not CONFIG.md / not public API.
FAMILY_ROUTE: Mapping[str, Route] = {
    "lap": "shadow",
}


@dataclass(frozen=True, slots=True)
class DivergenceRecord:
    family: str
    aspect: Aspect
    reason: str
    legacy_fingerprint: str
    v2_fingerprint: str


@dataclass(frozen=True, slots=True)
class ShadowCompareResult:
    family: str
    route: Route
    matched: bool
    divergences: tuple[DivergenceRecord, ...]
    speech_effects: tuple[()] = ()


def route_for_family(family: str) -> Route:
    """Return the private route for ``family``; unlisted families stay ``legacy``."""

    return FAMILY_ROUTE.get(family, "legacy")


def compare_director_decisions(
    *,
    family: str,
    legacy_selected_beat_id: str | None,
    legacy_reason: str,
    world: DirectorWorld,
    candidates: Sequence[DirectorCandidate],
    director: StoryDirector | None = None,
) -> ShadowCompareResult:
    """Compare a legacy director pick to a fresh v2 ``StoryDirector.evaluate``.

    Returns an observation-only result. Callers must not treat ``speech_effects``
    as a dispatch signal — it is always empty.
    """

    del legacy_reason  # retained for future episode/event aspect fingerprints
    route = route_for_family(family)
    engine = director if director is not None else StoryDirector()
    decision = engine.evaluate(world, tuple(candidates))
    v2_beat = None if decision.selected is None else decision.selected.beat_id
    legacy_fp = "" if legacy_selected_beat_id is None else str(legacy_selected_beat_id)
    v2_fp = "" if v2_beat is None else str(v2_beat)
    if legacy_fp == v2_fp:
        return ShadowCompareResult(
            family=family,
            route=route,
            matched=True,
            divergences=(),
            speech_effects=(),
        )
    divergence = DivergenceRecord(
        family=family,
        aspect="director",
        reason="selected_beat_mismatch",
        legacy_fingerprint=legacy_fp,
        v2_fingerprint=v2_fp,
    )
    return ShadowCompareResult(
        family=family,
        route=route,
        matched=False,
        divergences=(divergence,),
        speech_effects=(),
    )
