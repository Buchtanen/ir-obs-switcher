"""#248 versioned gap estimators, validity rules and bucket coverage."""

from __future__ import annotations

import pytest

from irswitch.contracts import FactQuality, SessionRef
from irswitch.contracts.feature import FIRST_SLICE_FEATURE_ID
from irswitch.events.feature_engine import FeatureEngine, FeatureSample

EST_TIME_V1 = "gap.relation.seconds.est_time_v1"
HYBRID_V1 = "gap.relation.seconds.hybrid_v1"
TREND_SLOPE = "gap.trend.slope"
TREND_NET = "gap.trend.net_closing"
TREND_COVERAGE = "gap.trend.coverage"


def _sample(**overrides: object) -> FeatureSample:
    payload: dict[str, object] = {
        "observed_mono_ms": 1_000,
        "source_snapshot_id": "snap:1",
        "broadcast_epoch": 4,
        "stream_epoch": 1,
        "session_ref": SessionRef("sub:1", 2),
        "occurrence_id": "1:race:0",
        "lineage_id": "1:practice:0>1:race:0",
        "closer_id": "car:12",
        "target_id": "car:34",
        "relation_epoch": "rel:1",
        "closer_lap_dist": 0.10,
        "target_lap_dist": 0.12,
        "hero_lap_ref_s": 90.0,
    }
    payload.update(overrides)
    return FeatureSample(**payload)  # type: ignore[arg-type]


def _value(frame: object, feature_id: str) -> object:
    assert frame is not None
    for item in frame.values:  # type: ignore[attr-defined]
        if item.feature_id == feature_id:
            return item
    raise AssertionError(f"missing {feature_id}")


def test_estimated_v1_evidence_names_the_algorithm_version() -> None:
    step = FeatureEngine().observe(_sample())
    assert step.frame is not None
    value = _value(step.frame, FIRST_SLICE_FEATURE_ID)
    assert FIRST_SLICE_FEATURE_ID in value.evidence_refs
    assert "snap:1" in value.evidence_refs


def test_start_finish_wrap_is_valid_when_target_just_crossed() -> None:
    step = FeatureEngine().observe(
        _sample(
            closer_lap_dist=0.98,
            target_lap_dist=0.02,
            source_snapshot_id="snap:sf",
        )
    )
    assert step.frame is not None
    assert "wrap_ambiguity" not in step.diagnostics
    assert _value(step.frame, FIRST_SLICE_FEATURE_ID).value == pytest.approx(3.6)


def test_lap_down_ambiguity_is_unknown() -> None:
    step = FeatureEngine().observe(
        _sample(closer_lap=5, target_lap=6, source_snapshot_id="snap:lap")
    )
    assert step.frame is not None
    ids = [item.feature_id for item in step.frame.values]
    assert FIRST_SLICE_FEATURE_ID not in ids
    assert "lap_down_ambiguity" in step.diagnostics


def test_not_in_world_invalidates_like_pit() -> None:
    step = FeatureEngine().observe(_sample(in_world=False, source_snapshot_id="snap:world"))
    assert step.frame is not None
    assert step.frame.values == ()
    assert "not_in_world" in step.diagnostics or "pit_tow_teleport" in step.diagnostics


def test_est_time_v1_is_a_distinct_compatible_difference() -> None:
    step = FeatureEngine().observe(
        _sample(
            closer_est_time_s=9.0,
            target_est_time_s=10.8,
            source_snapshot_id="snap:est",
        )
    )
    assert step.frame is not None
    estimated = _value(step.frame, FIRST_SLICE_FEATURE_ID)
    est_time = _value(step.frame, EST_TIME_V1)
    assert estimated.value == pytest.approx(1.8)
    assert est_time.value == pytest.approx(1.8)
    assert est_time.unit == "seconds"
    assert est_time.quality is FactQuality.ESTIMATED
    assert EST_TIME_V1 in est_time.evidence_refs
    assert EST_TIME_V1 != FIRST_SLICE_FEATURE_ID


def test_est_time_wraps_with_lap_reference() -> None:
    step = FeatureEngine().observe(
        _sample(
            closer_lap_dist=0.98,
            target_lap_dist=0.02,
            closer_est_time_s=88.0,
            target_est_time_s=2.0,
            source_snapshot_id="snap:est-wrap",
        )
    )
    assert step.frame is not None
    assert _value(step.frame, EST_TIME_V1).value == pytest.approx(4.0)


def test_missing_est_time_does_not_replace_estimated_v1() -> None:
    step = FeatureEngine().observe(_sample())
    assert step.frame is not None
    ids = [item.feature_id for item in step.frame.values]
    assert FIRST_SLICE_FEATURE_ID in ids
    assert EST_TIME_V1 not in ids
    assert HYBRID_V1 not in ids


def test_est_time_unknown_on_missing_values_or_target_swap() -> None:
    missing = FeatureEngine().observe(
        _sample(closer_est_time_s=9.0, target_est_time_s=None, source_snapshot_id="snap:e0")
    )
    assert missing.frame is not None
    assert EST_TIME_V1 not in [item.feature_id for item in missing.frame.values]
    assert "missing_est_time" in missing.diagnostics
    engine = FeatureEngine()
    engine.observe(_sample(closer_est_time_s=9.0, target_est_time_s=10.8))
    swapped = engine.observe(
        _sample(
            observed_mono_ms=1_100,
            source_snapshot_id="snap:e1",
            target_id="car:99",
            relation_epoch="rel:2",
            closer_est_time_s=9.0,
            target_est_time_s=10.8,
        )
    )
    assert swapped.frame is not None
    assert "target_swap" in swapped.diagnostics
    assert EST_TIME_V1 not in [item.feature_id for item in swapped.frame.values]


def test_hybrid_chooses_estimated_when_estimators_agree() -> None:
    step = FeatureEngine().observe(
        _sample(
            closer_est_time_s=9.0,
            target_est_time_s=10.8,
            source_snapshot_id="snap:hy",
        )
    )
    assert step.frame is not None
    hybrid = _value(step.frame, HYBRID_V1)
    assert hybrid.value == pytest.approx(1.8)
    assert FIRST_SLICE_FEATURE_ID in hybrid.evidence_refs
    assert HYBRID_V1 in hybrid.evidence_refs


def test_hybrid_unknown_when_estimators_disagree() -> None:
    step = FeatureEngine().observe(
        _sample(
            closer_est_time_s=9.0,
            target_est_time_s=20.0,
            source_snapshot_id="snap:dis",
        )
    )
    assert step.frame is not None
    ids = [item.feature_id for item in step.frame.values]
    assert FIRST_SLICE_FEATURE_ID in ids
    assert EST_TIME_V1 in ids
    assert HYBRID_V1 not in ids
    assert "estimator_disagreement" in step.diagnostics


def test_lone_sample_cannot_fill_a_bucket_or_emit_trend() -> None:
    engine = FeatureEngine(sample_interval_s=0.25, bucket_s=1.0, trend_window_s=6.0)
    step = engine.observe(_sample())
    assert step.frame is not None
    ids = [item.feature_id for item in step.frame.values]
    assert TREND_SLOPE not in ids
    assert TREND_NET not in ids
    assert TREND_COVERAGE not in ids


def test_trend_requires_three_usable_bucket_medians() -> None:
    engine = FeatureEngine(
        sample_interval_s=0.25,
        bucket_s=1.0,
        trend_window_s=6.0,
        min_coverage=0.50,
    )
    closer = 0.10
    for index in range(17):
        gap_fraction = 0.04 - (index / 16.0) * 0.02
        step = engine.observe(
            _sample(
                observed_mono_ms=1_000 + index * 250,
                source_snapshot_id=f"snap:t{index}",
                closer_lap_dist=closer,
                target_lap_dist=closer + gap_fraction,
            )
        )
    assert step.frame is not None
    ids = [item.feature_id for item in step.frame.values]
    assert TREND_COVERAGE in ids
    slope = _value(step.frame, TREND_SLOPE)
    net = _value(step.frame, TREND_NET)
    coverage = _value(step.frame, TREND_COVERAGE)
    assert slope.unit == "seconds_per_second"
    assert net.unit == "seconds"
    assert coverage.unit == "fraction"
    assert slope.value < 0
    assert net.value > 0
    assert 0.0 < float(coverage.value) <= 1.0
    assert TREND_SLOPE in slope.evidence_refs


def test_target_swap_cannot_reuse_prior_trend_window() -> None:
    engine = FeatureEngine(
        sample_interval_s=0.25,
        bucket_s=1.0,
        trend_window_s=6.0,
        min_coverage=0.50,
    )
    closer = 0.10
    for index in range(17):
        gap_fraction = 0.04 - (index / 16.0) * 0.02
        engine.observe(
            _sample(
                observed_mono_ms=1_000 + index * 250,
                source_snapshot_id=f"snap:w{index}",
                closer_lap_dist=closer,
                target_lap_dist=closer + gap_fraction,
            )
        )
    swapped = engine.observe(
        _sample(
            observed_mono_ms=6_000,
            source_snapshot_id="snap:swap",
            target_id="car:99",
            relation_epoch="rel:2",
            closer_lap_dist=0.20,
            target_lap_dist=0.24,
        )
    )
    assert swapped.frame is not None
    ids = [item.feature_id for item in swapped.frame.values]
    assert "target_swap" in swapped.diagnostics
    assert TREND_SLOPE not in ids
    assert TREND_NET not in ids
    assert engine.window_size("car:12", "car:99", "rel:2") == 1
