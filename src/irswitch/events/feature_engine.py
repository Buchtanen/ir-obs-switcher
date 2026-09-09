"""Typed FeatureEngine: approved algorithms, bounded windows, immutable frames.

Does not import NarrativeRuntime, DetectorBank, overlay tape or commentary.
Catalog definition strings are documentation only.
"""

from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass, field

from irswitch.contracts.feature import FIRST_SLICE_FEATURE_ID, FeatureFrame, FeatureValue
from irswitch.contracts.primitives import ContractViolation, FactQuality, Identifier
from irswitch.contracts.session import SessionRef
from irswitch.events.gap_estimators import (
    EST_TIME_FEATURE_ID,
    HYBRID_FEATURE_ID,
    TREND_COVERAGE_FEATURE_ID,
    TREND_NET_FEATURE_ID,
    TREND_SLOPE_FEATURE_ID,
    GapPoint,
    TrendResult,
    choose_hybrid_v1,
    compute_trend,
    estimate_distance_v1,
    estimate_est_time_v1,
    evidence,
)

WINDOW_CAPACITY = 32
CORRELATION_CAPACITY = 64


@dataclass(frozen=True, slots=True)
class FeatureSample:
    observed_mono_ms: int
    source_snapshot_id: str
    broadcast_epoch: int
    stream_epoch: int
    session_ref: SessionRef | None
    occurrence_id: str | None
    lineage_id: str | None
    closer_id: str
    target_id: str
    relation_epoch: str
    closer_lap_dist: float | None
    target_lap_dist: float | None
    hero_lap_ref_s: float | None
    in_pit: bool = False
    towing: bool = False
    teleport: bool = False
    in_world: bool = True
    closer_est_time_s: float | None = None
    target_est_time_s: float | None = None
    closer_lap: int | None = None
    target_lap: int | None = None


@dataclass(frozen=True, slots=True)
class FeatureStep:
    frame: FeatureFrame | None
    accepted: bool
    diagnostic: str | None = None
    diagnostics: tuple[str, ...] = ()


@dataclass
class FeatureEngine:
    """Process-local typed feature projector. Replay-deterministic for the same samples."""

    window_capacity: int = WINDOW_CAPACITY
    correlation_capacity: int = CORRELATION_CAPACITY
    sample_interval_s: float = 0.25
    bucket_s: float = 1.0
    trend_window_s: float = 12.0
    min_coverage: float = 0.80
    _windows: OrderedDict[tuple[str, ...], deque[FeatureSample]] = field(
        default_factory=OrderedDict
    )
    _last_relation: dict[str, tuple[str, str]] = field(default_factory=dict)
    _last_occurrence_id: str | None = None
    _last_accepted_mono_ms: int | None = None
    _latest_frame: FeatureFrame | None = None
    _frame_sequence: int = 0

    def observe(self, sample: FeatureSample) -> FeatureStep:
        self._validate_sample(sample)
        if self._last_accepted_mono_ms is not None:
            if int(sample.observed_mono_ms) == self._last_accepted_mono_ms:
                return self._noop("feature_frame_duplicate")
            if int(sample.observed_mono_ms) < self._last_accepted_mono_ms:
                return self._noop("feature_frame_stale")

        diagnostics: list[str] = []
        occurrence_id = sample.occurrence_id
        if self._last_occurrence_id is not None and occurrence_id != self._last_occurrence_id:
            self._reset_windows()
            diagnostics.append("occurrence_reset")

        last_relation = self._last_relation.get(sample.closer_id)
        current_relation = (sample.target_id, sample.relation_epoch)
        target_swap = last_relation is not None and last_relation != current_relation
        if target_swap:
            diagnostics.append("target_swap")

        estimated = estimate_distance_v1(
            closer_lap_dist=sample.closer_lap_dist,
            target_lap_dist=sample.target_lap_dist,
            hero_lap_ref_s=sample.hero_lap_ref_s,
            closer_lap=sample.closer_lap,
            target_lap=sample.target_lap,
            target_swap=target_swap,
            in_pit=sample.in_pit,
            towing=sample.towing,
            teleport=sample.teleport,
            in_world=sample.in_world,
        )
        est_time = estimate_est_time_v1(
            closer_est_time_s=sample.closer_est_time_s,
            target_est_time_s=sample.target_est_time_s,
            hero_lap_ref_s=sample.hero_lap_ref_s,
            target_swap=target_swap,
            in_pit=sample.in_pit,
            towing=sample.towing,
            teleport=sample.teleport,
            in_world=sample.in_world,
        )
        hybrid = choose_hybrid_v1(estimated.value, est_time.value)
        diagnostics.extend(estimated.reasons)
        diagnostics.extend(reason for reason in est_time.reasons if reason not in diagnostics)
        diagnostics.extend(reason for reason in hybrid.reasons if reason not in diagnostics)

        key = self._correlation_key(sample)
        if self._hard_invalid(sample):
            self._windows.pop(key, None)
        self._remember(sample, key)
        trend = compute_trend(
            self._gap_points(key),
            sample_interval_s=self.sample_interval_s,
            bucket_s=self.bucket_s,
            trend_window_s=self.trend_window_s,
            min_coverage=self.min_coverage,
        )
        values = self._values(sample, estimated.value, est_time.value, hybrid.value, trend)
        frame = FeatureFrame(
            frame_sequence=self._frame_sequence + 1,
            observed_mono_ms=sample.observed_mono_ms,
            source_snapshot_id=sample.source_snapshot_id,
            broadcast_epoch=sample.broadcast_epoch,
            stream_epoch=sample.stream_epoch,
            session_ref=sample.session_ref,
            occurrence_id=sample.occurrence_id,
            lineage_id=sample.lineage_id,
            correlation_key=key,
            values=values,
        )
        self._last_relation[sample.closer_id] = current_relation
        self._last_occurrence_id = sample.occurrence_id
        self._last_accepted_mono_ms = int(sample.observed_mono_ms)
        self._latest_frame = frame
        self._frame_sequence = frame.frame_sequence
        return FeatureStep(
            frame=frame,
            accepted=True,
            diagnostic=None,
            diagnostics=tuple(diagnostics),
        )

    def latest_frame(self) -> FeatureFrame | None:
        return self._latest_frame

    def window_size(self, *correlation_key: str) -> int:
        window = self._windows.get(tuple(correlation_key))
        return 0 if window is None else len(window)

    def correlation_count(self) -> int:
        return len(self._windows)

    def _noop(self, diagnostic: str) -> FeatureStep:
        return FeatureStep(
            frame=self._latest_frame,
            accepted=False,
            diagnostic=diagnostic,
            diagnostics=(diagnostic,),
        )

    def _remember(self, sample: FeatureSample, key: tuple[str, ...]) -> None:
        window = self._windows.get(key)
        if window is None:
            while len(self._windows) >= self.correlation_capacity:
                self._windows.popitem(last=False)
            window = deque(maxlen=self.window_capacity)
            self._windows[key] = window
        else:
            self._windows.move_to_end(key)
        window.append(sample)

    def _reset_windows(self) -> None:
        self._windows.clear()
        self._last_relation.clear()

    def _gap_points(self, key: tuple[str, ...]) -> tuple[GapPoint, ...]:
        window = self._windows.get(key) or ()
        points: list[GapPoint] = []
        for item in window:
            estimated = estimate_distance_v1(
                closer_lap_dist=item.closer_lap_dist,
                target_lap_dist=item.target_lap_dist,
                hero_lap_ref_s=item.hero_lap_ref_s,
                closer_lap=item.closer_lap,
                target_lap=item.target_lap,
                target_swap=False,
                in_pit=item.in_pit,
                towing=item.towing,
                teleport=item.teleport,
                in_world=item.in_world,
            )
            points.append(GapPoint(item.observed_mono_ms, estimated.value))
        return tuple(points)

    @staticmethod
    def _correlation_key(sample: FeatureSample) -> tuple[str, ...]:
        return (sample.closer_id, sample.target_id, sample.relation_epoch)

    @staticmethod
    def _hard_invalid(sample: FeatureSample) -> bool:
        return (not sample.in_world) or sample.in_pit or sample.towing or sample.teleport

    @staticmethod
    def _validate_sample(sample: FeatureSample) -> None:
        Identifier(sample.source_snapshot_id)
        Identifier(sample.closer_id)
        Identifier(sample.target_id)
        Identifier(sample.relation_epoch)
        present = (
            sample.session_ref is not None,
            sample.occurrence_id is not None,
            sample.lineage_id is not None,
        )
        if any(present) and not all(present):
            raise ContractViolation(
                "sessionRef, occurrenceId and lineageId must be all coherent or all null"
            )
        if sample.session_ref is not None and not isinstance(sample.session_ref, SessionRef):
            raise ContractViolation("sessionRef must be a SessionRef or null")

    @staticmethod
    def _values(
        sample: FeatureSample,
        estimated_s: float | None,
        est_time_s: float | None,
        hybrid_s: float | None,
        trend: TrendResult,
    ) -> tuple[FeatureValue, ...]:
        items: list[FeatureValue] = []
        snapshot = sample.source_snapshot_id
        if estimated_s is not None:
            items.append(
                FeatureValue(
                    feature_id=FIRST_SLICE_FEATURE_ID,
                    value=estimated_s,
                    unit="seconds",
                    quality=FactQuality.ESTIMATED,
                    observed_mono_ms=sample.observed_mono_ms,
                    valid_until_mono_ms=None,
                    evidence_refs=evidence(snapshot, FIRST_SLICE_FEATURE_ID),
                )
            )
        if est_time_s is not None:
            items.append(
                FeatureValue(
                    feature_id=EST_TIME_FEATURE_ID,
                    value=est_time_s,
                    unit="seconds",
                    quality=FactQuality.ESTIMATED,
                    observed_mono_ms=sample.observed_mono_ms,
                    valid_until_mono_ms=None,
                    evidence_refs=evidence(snapshot, EST_TIME_FEATURE_ID),
                )
            )
        if hybrid_s is not None:
            items.append(
                FeatureValue(
                    feature_id=HYBRID_FEATURE_ID,
                    value=hybrid_s,
                    unit="seconds",
                    quality=FactQuality.ESTIMATED,
                    observed_mono_ms=sample.observed_mono_ms,
                    valid_until_mono_ms=None,
                    evidence_refs=evidence(
                        snapshot, HYBRID_FEATURE_ID, FIRST_SLICE_FEATURE_ID, EST_TIME_FEATURE_ID
                    ),
                )
            )
        if trend.coverage is not None:
            items.append(
                FeatureValue(
                    feature_id=TREND_COVERAGE_FEATURE_ID,
                    value=trend.coverage,
                    unit="fraction",
                    quality=FactQuality.DERIVED,
                    observed_mono_ms=sample.observed_mono_ms,
                    valid_until_mono_ms=None,
                    evidence_refs=evidence(snapshot, TREND_COVERAGE_FEATURE_ID),
                )
            )
        if trend.net_closing is not None:
            items.append(
                FeatureValue(
                    feature_id=TREND_NET_FEATURE_ID,
                    value=trend.net_closing,
                    unit="seconds",
                    quality=FactQuality.DERIVED,
                    observed_mono_ms=sample.observed_mono_ms,
                    valid_until_mono_ms=None,
                    evidence_refs=evidence(snapshot, TREND_NET_FEATURE_ID),
                )
            )
        if trend.slope is not None:
            items.append(
                FeatureValue(
                    feature_id=TREND_SLOPE_FEATURE_ID,
                    value=trend.slope,
                    unit="seconds_per_second",
                    quality=FactQuality.DERIVED,
                    observed_mono_ms=sample.observed_mono_ms,
                    valid_until_mono_ms=None,
                    evidence_refs=evidence(snapshot, TREND_SLOPE_FEATURE_ID),
                )
            )
        return tuple(sorted(items, key=lambda item: item.feature_id))
