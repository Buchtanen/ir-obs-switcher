"""Versioned gap algorithms for FeatureEngine. Catalog text is never evaluated."""

from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from statistics import median

EST_TIME_FEATURE_ID = "gap.relation.seconds.est_time_v1"
HYBRID_FEATURE_ID = "gap.relation.seconds.hybrid_v1"
TREND_SLOPE_FEATURE_ID = "gap.trend.slope"
TREND_NET_FEATURE_ID = "gap.trend.net_closing"
TREND_COVERAGE_FEATURE_ID = "gap.trend.coverage"

HYBRID_MAX_DISAGREEMENT_S = 0.5


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    if not isfinite(number):
        return None
    return number


def finite_fraction(value: object) -> float | None:
    number = _finite_number(value)
    if number is None or not 0.0 <= number < 1.0:
        return None
    return number


def finite_seconds(value: object) -> float | None:
    number = _finite_number(value)
    if number is None or number < 0.0:
        return None
    return number


def forward_gap_fraction(closer: float, target: float) -> float:
    return (target - closer) % 1.0


def wrap_ambiguous(closer: float, target: float) -> bool:
    return forward_gap_fraction(closer, target) > 0.5


def wrap_aware_seconds(closer: float, target: float, lap_ref_s: float) -> float:
    return (target - closer) % lap_ref_s


@dataclass(frozen=True, slots=True)
class EstimatorResult:
    value: float | None
    reasons: tuple[str, ...]


def estimate_distance_v1(
    *,
    closer_lap_dist: float | None,
    target_lap_dist: float | None,
    hero_lap_ref_s: float | None,
    closer_lap: int | None,
    target_lap: int | None,
    target_swap: bool,
    in_pit: bool,
    towing: bool,
    teleport: bool,
    in_world: bool,
) -> EstimatorResult:
    reasons: list[str] = []
    unknown = target_swap
    if not in_world:
        reasons.append("not_in_world")
        unknown = True
    if in_pit or towing or teleport:
        reasons.append("pit_tow_teleport")
        unknown = True
    if closer_lap is not None and target_lap is not None and int(closer_lap) != int(target_lap):
        reasons.append("lap_down_ambiguity")
        unknown = True
    reference = finite_seconds(hero_lap_ref_s)
    if reference is None or reference <= 0.0:
        reasons.append("missing_lap_reference")
        unknown = True
        reference = None
    closer = finite_fraction(closer_lap_dist)
    target = finite_fraction(target_lap_dist)
    if closer is None or target is None:
        if "missing_lap_reference" not in reasons:
            reasons.append("missing_lap_reference")
        unknown = True
    elif wrap_ambiguous(closer, target):
        reasons.append("wrap_ambiguity")
        unknown = True
    if unknown or reference is None or closer is None or target is None:
        return EstimatorResult(None, tuple(reasons))
    return EstimatorResult(forward_gap_fraction(closer, target) * reference, tuple(reasons))


def estimate_est_time_v1(
    *,
    closer_est_time_s: float | None,
    target_est_time_s: float | None,
    hero_lap_ref_s: float | None,
    target_swap: bool,
    in_pit: bool,
    towing: bool,
    teleport: bool,
    in_world: bool,
) -> EstimatorResult:
    provided = closer_est_time_s is not None or target_est_time_s is not None
    if not provided:
        return EstimatorResult(None, ())
    reasons: list[str] = []
    unknown = target_swap
    if not in_world:
        reasons.append("not_in_world")
        unknown = True
    if in_pit or towing or teleport:
        reasons.append("pit_tow_teleport")
        unknown = True
    closer = finite_seconds(closer_est_time_s)
    target = finite_seconds(target_est_time_s)
    if closer is None or target is None:
        reasons.append("missing_est_time")
        unknown = True
    reference = finite_seconds(hero_lap_ref_s)
    if unknown or closer is None or target is None:
        return EstimatorResult(None, tuple(reasons))
    if reference is not None and reference > 0.0:
        return EstimatorResult(wrap_aware_seconds(closer, target, reference), tuple(reasons))
    if target < closer:
        reasons.append("missing_est_time")
        return EstimatorResult(None, tuple(reasons))
    return EstimatorResult(target - closer, tuple(reasons))


def choose_hybrid_v1(estimated_s: float | None, est_time_s: float | None) -> EstimatorResult:
    if estimated_s is None or est_time_s is None:
        return EstimatorResult(None, ())
    if abs(estimated_s - est_time_s) > HYBRID_MAX_DISAGREEMENT_S:
        return EstimatorResult(None, ("estimator_disagreement",))
    return EstimatorResult(estimated_s, ())


@dataclass(frozen=True, slots=True)
class GapPoint:
    observed_mono_ms: int
    gap_s: float | None


@dataclass(frozen=True, slots=True)
class TrendResult:
    coverage: float | None
    slope: float | None
    net_closing: float | None


def _bucket_start_ms(mono_ms: int, bucket_ms: int) -> int:
    return (mono_ms // bucket_ms) * bucket_ms


def compute_trend(
    points: tuple[GapPoint, ...],
    *,
    sample_interval_s: float,
    bucket_s: float,
    trend_window_s: float,
    min_coverage: float,
) -> TrendResult:
    if len(points) < 2:
        return TrendResult(None, None, None)
    latest = points[-1].observed_mono_ms
    window_ms = int(trend_window_s * 1000)
    windowed = tuple(point for point in points if 0 <= latest - point.observed_mono_ms <= window_ms)
    if len(windowed) < 2:
        return TrendResult(None, None, None)
    bucket_ms = max(1, int(bucket_s * 1000))
    covered: dict[int, float] = {}
    gaps: dict[int, list[float]] = {}
    for index, point in enumerate(windowed):
        start = _bucket_start_ms(point.observed_mono_ms, bucket_ms)
        covered[start] = covered.get(start, 0.0)
        if point.gap_s is not None:
            gaps.setdefault(start, []).append(point.gap_s)
        if index + 1 >= len(windowed):
            continue
        elapsed_s = (windowed[index + 1].observed_mono_ms - point.observed_mono_ms) / 1000.0
        covered[start] += min(max(elapsed_s, 0.0), sample_interval_s)
    coverage = min(1.0, sum(covered.values()) / trend_window_s) if trend_window_s > 0 else None
    usable: list[tuple[float, float]] = []
    threshold = bucket_s * min_coverage
    for start in sorted(covered):
        if covered[start] < threshold or start not in gaps:
            continue
        midpoint_s = (start + bucket_s * 500) / 1000.0
        usable.append((midpoint_s, float(median(gaps[start]))))
    if len(usable) < 3:
        return TrendResult(coverage, None, None)
    times = [item[0] for item in usable]
    values = [item[1] for item in usable]
    mean_t = sum(times) / len(times)
    mean_v = sum(values) / len(values)
    var_t = sum((item - mean_t) ** 2 for item in times)
    if var_t <= 0.0:
        return TrendResult(coverage, None, None)
    cov_tv = sum((time - mean_t) * (value - mean_v) for time, value in usable)
    slope = cov_tv / var_t
    third = max(1, len(values) // 3)
    net_closing = float(median(values[:third]) - median(values[-third:]))
    return TrendResult(coverage, slope, net_closing)


def evidence(*parts: str) -> tuple[str, ...]:
    items = tuple(part for part in parts if part)
    seen: list[str] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return tuple(seen)
