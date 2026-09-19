"""Long-silence clock and fact-grounded filler opportunities (v2 issue #260).

Deterministic rearm of ``LONG_SILENCE_ELAPSED``. The clock is not live-wired
and is not exported from ``events/__init__.py``. It stays inside events and
does not import commentary or overlay packages.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

LONG_SILENCE_MS = 33_000
_BUSY_LANES = frozenset({"building", "committed", "speaking", "stopping"})
_PHASE_BEATS = {
    "out_lap": "filler.out_lap",
    "in_lap": "filler.in_lap",
    "parade_lap": "filler.parade_lap",
}
_W_WEATHER = frozenset(
    {
        "weather.air_temperature",
        "weather.track_temperature",
        "weather.skies",
        "weather.wind_speed",
        "weather.precipitation",
        "weather.track_wetness",
    }
)
_W_FIELD = frozenset(
    {
        "context.hero_position",
        "context.field_size",
        "context.track_identity",
        "context.nearby_gap",
        "context.session_progress",
        "context.leader_identity",
        "field.strength",
    }
)
_W_FILLER_PHASE = _W_FIELD | _W_WEATHER
_W_FILLER_OFF_TRACK = (
    frozenset({"context.track_identity", "context.field_size", "context.session_progress"})
    | _W_WEATHER
)
_W_QUIET_TRACK = (
    frozenset(
        {
            "context.hero_position",
            "context.leader_identity",
            "context.session_progress",
            "field.strength",
            "context.field_size",
            "context.track_identity",
        }
    )
    | _W_WEATHER
)
_RACE_PREDICATES = frozenset({"position.passed"})


def _audience_window_open(window: Mapping[str, Any]) -> bool:
    return (
        str(window.get("runtime_status") or "") in {"ready", "degraded"}
        and bool(window.get("commentary_enabled"))
        and bool(window.get("narrative_run_active"))
        and str(window.get("obs_state") or "") == "active"
    )


@dataclass(frozen=True)
class SilenceImpulse:
    kind: str
    generation: int
    deadline_mono_ms: int


@dataclass(frozen=True)
class ClockStep:
    reason: str
    generation: int
    deadline_mono_ms: int | None
    impulse: SilenceImpulse | None = None
    filler: Any | None = None


@dataclass(frozen=True)
class FillerFact:
    predicate: str
    scope: str
    fresh: bool = True
    weather_source: str | None = None


@dataclass(frozen=True)
class FillerContext:
    broadcast_context: str
    vehicle_phase: str | None
    has_session_ref: bool
    occurrence_id: str | None
    lineage_id: str | None
    has_live_race_opportunity: bool
    facts: tuple[FillerFact, ...]


@dataclass(frozen=True)
class FillerOpportunity:
    beat_id: str | None
    reason: str
    scope: str | None = None
    story_id: str | None = None
    occurrence_id: str | None = None
    lineage_id: str | None = None


class SilenceClock:
    """One-shot silence deadline with full-interval rearm and no busy-loop."""

    def __init__(self, interval_ms: int = LONG_SILENCE_MS) -> None:
        self._interval_ms = int(interval_ms)
        self._generation = 0
        self._deadline_mono_ms: int | None = None
        self._paused = False
        self.pending_filler: FillerOpportunity | None = None

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def deadline_mono_ms(self) -> int | None:
        return self._deadline_mono_ms

    @property
    def interval_ms(self) -> int:
        return self._interval_ms

    def set_interval_ms(self, interval_ms: int) -> None:
        """Next arm/rearm uses this interval. An already armed deadline stays."""
        self._interval_ms = int(interval_ms)

    def after_lifecycle(
        self,
        now_ms: int,
        window: Mapping[str, Any],
        speech_accepted: bool,
    ) -> ClockStep:
        if self._deadline_mono_ms is not None:
            return self._step("origin_unchanged")
        if speech_accepted or not _audience_window_open(window) or self._paused:
            return self._step("not_armed")
        return self._arm(now_ms, "armed")

    def on_elapsed(
        self,
        generation: int,
        deadline_mono_ms: int,
        now_ms: int,
        lane: str = "idle",
    ) -> ClockStep:
        if generation != self._generation or self._deadline_mono_ms is None:
            return self._step("stale_token")
        if int(deadline_mono_ms) != int(self._deadline_mono_ms):
            return self._step("stale_token")
        if now_ms < self._deadline_mono_ms:
            return self._step("deadline_pending")
        fired = SilenceImpulse(
            kind="LONG_SILENCE_ELAPSED",
            generation=self._generation,
            deadline_mono_ms=int(self._deadline_mono_ms),
        )
        filler = None if lane in _BUSY_LANES else self.pending_filler
        self._arm_inplace(now_ms)
        return ClockStep(
            reason="rearmed",
            generation=self._generation,
            deadline_mono_ms=self._deadline_mono_ms,
            impulse=fired,
            filler=filler,
        )

    def on_playback_accepted(self, now_ms: int) -> ClockStep:
        _ = now_ms
        return self._cancel("cancelled_playback_accepted")

    def on_speech_terminal(self, now_ms: int, window: Mapping[str, Any]) -> ClockStep:
        if not _audience_window_open(window) or self._paused:
            return self._cancel("cancelled_window_closed")
        return self._arm(now_ms, "armed")

    def on_obs_unknown(self, now_ms: int) -> ClockStep:
        _ = now_ms
        self._paused = True
        self._deadline_mono_ms = None
        return self._step("paused_obs_unknown")

    def on_audience_resume(self, now_ms: int, window: Mapping[str, Any]) -> ClockStep:
        if not _audience_window_open(window):
            return self._step("paused_obs_unknown")
        self._paused = False
        return self._arm(now_ms, "armed")

    def on_commentary_disabled(self, now_ms: int) -> ClockStep:
        _ = now_ms
        self._paused = False
        return self._cancel("cancelled_commentary_disabled")

    def on_shutdown(self, now_ms: int) -> ClockStep:
        _ = now_ms
        self._paused = False
        return self._cancel("cancelled_shutdown")

    def on_race_event(self, now_ms: int) -> ClockStep:
        _ = now_ms
        if self.pending_filler is not None:
            self.pending_filler = None
            return self._step("race_replaces_uncommitted_filler")
        return self._step("origin_unchanged")

    def _arm(self, now_ms: int, reason: str) -> ClockStep:
        self._arm_inplace(now_ms)
        return self._step(reason)

    def _arm_inplace(self, now_ms: int) -> None:
        self._generation += 1
        self._deadline_mono_ms = int(now_ms) + self._interval_ms
        self._paused = False

    def _cancel(self, reason: str) -> ClockStep:
        self._deadline_mono_ms = None
        return self._step(reason)

    def _step(self, reason: str) -> ClockStep:
        return ClockStep(
            reason=reason,
            generation=self._generation,
            deadline_mono_ms=self._deadline_mono_ms,
        )


def evaluate_filler(ctx: FillerContext) -> FillerOpportunity:
    """Phase-specific filler guards. Empty or invented facts stay silent."""
    failed = FillerOpportunity(beat_id=None, reason="source_guard_failed")
    silent = FillerOpportunity(beat_id=None, reason="no_candidate")
    if ctx.has_live_race_opportunity:
        return silent
    for fact in ctx.facts:
        if fact.predicate in _RACE_PREDICATES:
            return failed
        if fact.weather_source == "forecast" or fact.predicate == "weather.forecast":
            return failed

    if not ctx.has_session_ref:
        return _evaluate_pre_session(ctx, failed)
    return _evaluate_session(ctx, failed, silent)


def _fresh(ctx: FillerContext, predicate: str, scope: str | None = None) -> bool:
    return any(
        fact.predicate == predicate and fact.fresh and (scope is None or fact.scope == scope)
        for fact in ctx.facts
    )


def _fresh_from(
    ctx: FillerContext,
    allowlist: frozenset[str],
    scope: str | None = None,
) -> tuple[FillerFact, ...]:
    return tuple(
        fact
        for fact in ctx.facts
        if fact.predicate in allowlist and fact.fresh and (scope is None or fact.scope == scope)
    )


def _selected(
    beat_id: str,
    scope: str,
    ctx: FillerContext,
    occurrence_id: str | None,
) -> FillerOpportunity:
    return FillerOpportunity(
        beat_id=beat_id,
        reason="selected",
        scope=scope,
        story_id="filler_single",
        occurrence_id=occurrence_id,
        lineage_id=None if occurrence_id is None else ctx.lineage_id,
    )


def _evaluate_pre_session(
    ctx: FillerContext,
    failed: FillerOpportunity,
) -> FillerOpportunity:
    if ctx.broadcast_context != "lobby":
        return failed
    if _fresh(ctx, "context.track_identity", "stream"):
        return _selected("filler.lobby", "stream", ctx, None)
    return failed


def _evaluate_session(
    ctx: FillerContext,
    failed: FillerOpportunity,
    silent: FillerOpportunity,
) -> FillerOpportunity:
    phase = ctx.vehicle_phase
    if phase in _PHASE_BEATS:
        companions = _fresh_from(ctx, _W_FILLER_PHASE)
        if not _fresh(ctx, "vehicle.phase") or len(companions) != 1:
            return failed
        if ctx.occurrence_id is None:
            return failed
        return _selected(_PHASE_BEATS[phase], "occurrence", ctx, ctx.occurrence_id)

    if ctx.broadcast_context == "garage":
        companions = _fresh_from(ctx, _W_FILLER_OFF_TRACK)
        if len(companions) != 1 or ctx.occurrence_id is None:
            return failed
        return _selected("filler.garage", "occurrence", ctx, ctx.occurrence_id)

    if ctx.broadcast_context == "lobby":
        companions = _fresh_from(ctx, _W_FILLER_OFF_TRACK)
        if len(companions) != 1 or ctx.occurrence_id is None:
            return failed
        return _selected("filler.lobby", "occurrence", ctx, ctx.occurrence_id)

    if ctx.broadcast_context == "on_track":
        companions = _fresh_from(ctx, _W_QUIET_TRACK)
        if len(companions) != 1 or ctx.occurrence_id is None:
            return failed
        return _selected("filler.quiet_track", "occurrence", ctx, ctx.occurrence_id)
    return silent
