"""#272 legacy↔v2 shadow comparison — observational harness.

Observation-only compare of event / episode / director decisions behind a
private in-module ``FAMILY_ROUTE`` table. Adapts ``RaceState`` and
``EventEnvelope`` into v2 fingerprint projections for shadow checks.

Never admits speech, never mutates mailbox / TTS, never owns StreamTimeline /
FactView truth. Failures in observation stay fail-soft (swallowed into a
divergence / empty result) so the master loop and legacy families keep running.

Not exported from ``events/__init__.py``. Temporary branch harness — listed in
``docs/v2.0.0/final-pr-exclusion-manifest.md`` and must not survive the final
v2 cutover PR.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from irswitch.events.envelope import EventEnvelope
from irswitch.events.story_director import (
    DirectorCandidate,
    DirectorWorld,
    StoryDirector,
)
from irswitch.overlay.models import RaceState

Route = Literal["legacy", "v2", "shadow"]
Aspect = Literal["event", "episode", "director"]

# Private development control — not CONFIG.md / not public API.
# ``shadow`` = observational compare; ``legacy`` = unmigrated family stays on
# legacy owner inside the branch; ``v2`` reserved for cutover checkpoints.
FAMILY_ROUTE: Mapping[str, Route] = {
    "lap": "shadow",
    "timing": "legacy",
    "battle": "legacy",
    "position": "legacy",
    "pit": "legacy",
    "bio": "legacy",
    "incident": "legacy",
    "session": "legacy",
}

# Paths that must be absent from the final master cutover diff (#279/#282).
REMOVAL_MANIFEST_ENTRIES: tuple[str, ...] = (
    "src/irswitch/events/legacy_v2_shadow_compare.py",
    "tests/test_legacy_v2_shadow_compare.py",
    "FAMILY_ROUTE",
    "compare_director_decisions",
    "compare_event_decisions",
    "compare_episode_decisions",
    "observe_family_safely",
)


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
    latency_ms: float | None = None
    evidence: Mapping[str, str] | None = None


@dataclass(frozen=True, slots=True)
class V2RaceProjection:
    """Immutable v2-facing projection adapted from overlay ``RaceState``."""

    session_num: int | None
    subsession_id: str | None
    track_id: str | None
    lap: int | None
    lap_completed: int | None
    overlay_mode: str
    run_epoch: int
    data_quality: str
    stale_for_ms: float | None
    fingerprint: str


@dataclass(frozen=True, slots=True)
class V2EventProjection:
    """Immutable v2-facing event fingerprint adapted from ``EventEnvelope``."""

    event_type: str
    phase: str
    family: str
    fingerprint: str


def route_for_family(family: str) -> Route:
    """Return the private route for ``family``; unlisted families stay ``legacy``."""

    return FAMILY_ROUTE.get(family, "legacy")


def unmigrated_families() -> tuple[str, ...]:
    """Families kept on temporary legacy comparison inside the branch."""

    return tuple(sorted(name for name, route in FAMILY_ROUTE.items() if route == "legacy"))


def family_for_event_type(event_type: str) -> str:
    """Map a wire ``event_type`` onto a private family key."""

    token = str(event_type or "").strip().upper()
    if token.startswith("LAP") or token in {"LAP_COMPLETE", "LAP_STARTED"}:
        return "lap"
    if token.startswith("SECTOR") or token.startswith("TIMING") or "SPLIT" in token:
        return "timing"
    if token.startswith("BATTLE") or "OVERTAKE" in token:
        return "battle"
    if token.startswith("POS") or "POSITION" in token:
        return "position"
    if token.startswith("PIT"):
        return "pit"
    if token.startswith("BIO") or "DRIVER" in token:
        return "bio"
    if "INCIDENT" in token or "FLAG" in token or "INVALID_LAP" in token:
        return "incident"
    if token.startswith("SESSION") or token.startswith("TOW"):
        return "session"
    return "unknown"


def adapt_race_state_to_v2(race_state: RaceState) -> V2RaceProjection:
    """Adapt overlay ``RaceState`` into an immutable v2 projection fingerprint."""

    if not isinstance(race_state, RaceState):
        raise TypeError("adapt_race_state_to_v2 requires RaceState")
    fingerprint = "|".join(
        (
            str(race_state.session_num),
            str(race_state.subsession_id),
            str(race_state.track_id),
            str(race_state.lap),
            str(race_state.lap_completed),
            str(race_state.overlay_mode),
            str(race_state.run_epoch),
            str(race_state.data_quality),
            str(race_state.stale_for_ms),
        )
    )
    return V2RaceProjection(
        session_num=race_state.session_num,
        subsession_id=race_state.subsession_id,
        track_id=race_state.track_id,
        lap=race_state.lap,
        lap_completed=race_state.lap_completed,
        overlay_mode=str(race_state.overlay_mode),
        run_epoch=int(race_state.run_epoch),
        data_quality=str(race_state.data_quality),
        stale_for_ms=race_state.stale_for_ms,
        fingerprint=fingerprint,
    )


def adapt_event_envelope_to_v2(envelope: EventEnvelope) -> V2EventProjection:
    """Adapt ``EventEnvelope`` into an immutable v2 event fingerprint."""

    if not isinstance(envelope, EventEnvelope):
        raise TypeError("adapt_event_envelope_to_v2 requires EventEnvelope")
    family = family_for_event_type(envelope.event_type)
    fingerprint = f"{envelope.event_type}|{envelope.phase}|{family}"
    return V2EventProjection(
        event_type=str(envelope.event_type),
        phase=str(envelope.phase),
        family=family,
        fingerprint=fingerprint,
    )


def compare_event_decisions(
    *,
    family: str,
    legacy_event_type: str,
    legacy_phase: str,
    envelope: EventEnvelope,
) -> ShadowCompareResult:
    """Compare a legacy event decision fingerprint to an adapted envelope."""

    started = time.perf_counter()
    route = route_for_family(family)
    projection = adapt_event_envelope_to_v2(envelope)
    legacy_fp = f"{legacy_event_type}|{legacy_phase}|{family}"
    v2_fp = projection.fingerprint
    latency_ms = (time.perf_counter() - started) * 1000.0
    evidence = {
        "aspect": "event",
        "v2_family": projection.family,
        "route": route,
    }
    if legacy_fp == v2_fp:
        return ShadowCompareResult(
            family=family,
            route=route,
            matched=True,
            divergences=(),
            speech_effects=(),
            latency_ms=latency_ms,
            evidence=evidence,
        )
    return ShadowCompareResult(
        family=family,
        route=route,
        matched=False,
        divergences=(
            DivergenceRecord(
                family=family,
                aspect="event",
                reason="event_fingerprint_mismatch",
                legacy_fingerprint=legacy_fp,
                v2_fingerprint=v2_fp,
            ),
        ),
        speech_effects=(),
        latency_ms=latency_ms,
        evidence=evidence,
    )


def compare_episode_decisions(
    *,
    family: str,
    legacy_episode_id: str | None,
    legacy_state: str,
    v2_episode_id: str | None,
    v2_state: str,
) -> ShadowCompareResult:
    """Compare legacy vs v2 episode identity/state fingerprints."""

    started = time.perf_counter()
    route = route_for_family(family)
    legacy_fp = f"{legacy_episode_id or ''}|{legacy_state}"
    v2_fp = f"{v2_episode_id or ''}|{v2_state}"
    latency_ms = (time.perf_counter() - started) * 1000.0
    evidence = {"aspect": "episode", "route": route}
    if legacy_fp == v2_fp:
        return ShadowCompareResult(
            family=family,
            route=route,
            matched=True,
            divergences=(),
            speech_effects=(),
            latency_ms=latency_ms,
            evidence=evidence,
        )
    return ShadowCompareResult(
        family=family,
        route=route,
        matched=False,
        divergences=(
            DivergenceRecord(
                family=family,
                aspect="episode",
                reason="episode_fingerprint_mismatch",
                legacy_fingerprint=legacy_fp,
                v2_fingerprint=v2_fp,
            ),
        ),
        speech_effects=(),
        latency_ms=latency_ms,
        evidence=evidence,
    )


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

    started = time.perf_counter()
    del legacy_reason  # retained for future richer fingerprints
    route = route_for_family(family)
    engine = director if director is not None else StoryDirector()
    decision = engine.evaluate(world, tuple(candidates))
    v2_beat = None if decision.selected is None else decision.selected.beat_id
    legacy_fp = "" if legacy_selected_beat_id is None else str(legacy_selected_beat_id)
    v2_fp = "" if v2_beat is None else str(v2_beat)
    latency_ms = (time.perf_counter() - started) * 1000.0
    evidence = {
        "aspect": "director",
        "v2_reason": str(decision.reason),
        "route": route,
    }
    if legacy_fp == v2_fp:
        return ShadowCompareResult(
            family=family,
            route=route,
            matched=True,
            divergences=(),
            speech_effects=(),
            latency_ms=latency_ms,
            evidence=evidence,
        )
    return ShadowCompareResult(
        family=family,
        route=route,
        matched=False,
        divergences=(
            DivergenceRecord(
                family=family,
                aspect="director",
                reason="selected_beat_mismatch",
                legacy_fingerprint=legacy_fp,
                v2_fingerprint=v2_fp,
            ),
        ),
        speech_effects=(),
        latency_ms=latency_ms,
        evidence=evidence,
    )


def observe_family_safely(
    *,
    family: str,
    observer: Any,
) -> ShadowCompareResult:
    """Run an observational compare callable fail-soft.

    Any exception becomes a recorded divergence with empty ``speech_effects`` so
    the master loop / legacy families stay operational.
    """

    route = route_for_family(family)
    started = time.perf_counter()
    try:
        result = observer()
    except BaseException as exc:  # noqa: BLE001 — observation must never raise outward
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        latency_ms = (time.perf_counter() - started) * 1000.0
        reason = "observation_failed"
        if isinstance(exc, TimeoutError):
            reason = "observation_timeout"
        elif isinstance(exc, asyncio.CancelledError):
            reason = "observation_cancelled"
        return ShadowCompareResult(
            family=family,
            route=route,
            matched=False,
            divergences=(
                DivergenceRecord(
                    family=family,
                    aspect="event",
                    reason=reason,
                    legacy_fingerprint="",
                    v2_fingerprint=type(exc).__name__,
                ),
            ),
            speech_effects=(),
            latency_ms=latency_ms,
            evidence={"error": str(exc)[:200]},
        )
    if not isinstance(result, ShadowCompareResult):
        latency_ms = (time.perf_counter() - started) * 1000.0
        return ShadowCompareResult(
            family=family,
            route=route,
            matched=False,
            divergences=(
                DivergenceRecord(
                    family=family,
                    aspect="event",
                    reason="observation_invalid_result",
                    legacy_fingerprint="",
                    v2_fingerprint=type(result).__name__,
                ),
            ),
            speech_effects=(),
            latency_ms=latency_ms,
            evidence=None,
        )
    return result
