"""Typed FeatureEngine: approved algorithms, bounded windows, immutable frames.

Does not import NarrativeRuntime, DetectorBank, overlay tape or commentary.
Catalog definition strings are documentation only.
"""

from __future__ import annotations

from collections import OrderedDict, deque
from dataclasses import dataclass, field
from math import isfinite

from irswitch.contracts.feature import FIRST_SLICE_FEATURE_ID, FeatureFrame, FeatureValue
from irswitch.contracts.primitives import ContractViolation, FactQuality, Identifier
from irswitch.contracts.session import SessionRef

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


@dataclass(frozen=True, slots=True)
class FeatureStep:
    frame: FeatureFrame | None
    accepted: bool
    diagnostic: str | None = None
    diagnostics: tuple[str, ...] = ()


def _finite_fraction(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not isfinite(number) or not 0.0 <= number < 1.0:
        return None
    return number


def _forward_gap(closer: float, target: float) -> float:
    return (target - closer) % 1.0


def _wrap_ambiguous(closer: float, target: float) -> bool:
    return _forward_gap(closer, target) > 0.5


@dataclass
class FeatureEngine:
    """Process-local typed feature projector. Replay-deterministic for the same samples."""

    window_capacity: int = WINDOW_CAPACITY
    correlation_capacity: int = CORRELATION_CAPACITY
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

        values, reasons = self._first_slice_values(sample, target_swap=target_swap)
        diagnostics.extend(reasons)
        frame = FeatureFrame(
            frame_sequence=self._frame_sequence + 1,
            observed_mono_ms=sample.observed_mono_ms,
            source_snapshot_id=sample.source_snapshot_id,
            broadcast_epoch=sample.broadcast_epoch,
            stream_epoch=sample.stream_epoch,
            session_ref=sample.session_ref,
            occurrence_id=sample.occurrence_id,
            lineage_id=sample.lineage_id,
            correlation_key=self._correlation_key(sample),
            values=values,
        )
        self._publish(sample, frame)
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

    def _publish(self, sample: FeatureSample, frame: FeatureFrame) -> None:
        key = tuple(frame.correlation_key)
        window = self._windows.get(key)
        if window is None:
            while len(self._windows) >= self.correlation_capacity:
                self._windows.popitem(last=False)
            window = deque(maxlen=self.window_capacity)
            self._windows[key] = window
        else:
            self._windows.move_to_end(key)
        window.append(sample)
        self._last_relation[sample.closer_id] = (sample.target_id, sample.relation_epoch)
        self._last_occurrence_id = sample.occurrence_id
        self._last_accepted_mono_ms = int(sample.observed_mono_ms)
        self._latest_frame = frame
        self._frame_sequence = frame.frame_sequence

    def _reset_windows(self) -> None:
        self._windows.clear()
        self._last_relation.clear()

    @staticmethod
    def _correlation_key(sample: FeatureSample) -> tuple[str, ...]:
        return (sample.closer_id, sample.target_id, sample.relation_epoch)

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
    def _first_slice_values(
        sample: FeatureSample, *, target_swap: bool
    ) -> tuple[tuple[FeatureValue, ...], tuple[str, ...]]:
        reasons: list[str] = []
        unknown = target_swap
        if sample.in_pit or sample.towing or sample.teleport:
            reasons.append("pit_tow_teleport")
            unknown = True
        reference = sample.hero_lap_ref_s
        if (
            reference is None
            or isinstance(reference, bool)
            or not isinstance(reference, (int, float))
            or not isfinite(float(reference))
            or float(reference) <= 0.0
        ):
            reasons.append("missing_lap_reference")
            unknown = True
            reference = None
        closer = _finite_fraction(sample.closer_lap_dist)
        target = _finite_fraction(sample.target_lap_dist)
        if closer is None or target is None:
            if "missing_lap_reference" not in reasons:
                reasons.append("missing_lap_reference")
            unknown = True
        elif _wrap_ambiguous(closer, target):
            reasons.append("wrap_ambiguity")
            unknown = True
        if unknown or reference is None or closer is None or target is None:
            return (), tuple(reasons)
        value = FeatureValue(
            feature_id=FIRST_SLICE_FEATURE_ID,
            value=_forward_gap(closer, target) * float(reference),
            unit="seconds",
            quality=FactQuality.ESTIMATED,
            observed_mono_ms=sample.observed_mono_ms,
            valid_until_mono_ms=None,
            evidence_refs=(sample.source_snapshot_id,),
        )
        return (value,), tuple(reasons)
