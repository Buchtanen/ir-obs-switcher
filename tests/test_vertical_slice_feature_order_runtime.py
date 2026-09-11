"""#278 Slice 14 — offline F28 feature-order + bucket-coverage drivers.

Consumes frozen machine rows and proves FeatureEngine upstream ownership of
frame ordering and bucket coverage (reduce 10→12, older/duplicate noop,
lone-sample coverage capped/invalid for trend, OLS needs three buckets,
identity match). Does not rewrite ``docs/v2.0.0/machine/*`` hashes and does
not claim live §24.9 GO.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from test_feature_engine import _sample
from test_gap_estimators import TREND_COVERAGE, TREND_NET, TREND_SLOPE, _value

from irswitch.events.feature_engine import FeatureEngine

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
FIXTURES_PATH = MACHINE / "vertical-slice-fixtures.json"
BUILDER_PATH = MACHINE / "build_vertical_slice_fixtures.py"
ENGINE_SOURCE = ROOT / "src" / "irswitch" / "events" / "feature_engine.py"

SLICE14_IDS = ("F28",)


def _load_builder() -> Any:
    module_name = "irswitch_vertical_slice_feature_order_builder_under_test"
    if module_name in sys.modules:
        return sys.modules[module_name]
    machine_path = str(MACHINE)
    if machine_path not in sys.path:
        sys.path.insert(0, machine_path)
    spec = importlib.util.spec_from_file_location(module_name, BUILDER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


builder = _load_builder()


@pytest.fixture(scope="module")
def fixtures_by_id() -> dict[str, dict[str, Any]]:
    bundle = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    return {row["id"]: row for row in bundle["fixtures"]}


@pytest.mark.parametrize("fixture_id", SLICE14_IDS)
def test_slice14_machine_projection_and_calculations(
    fixtures_by_id: dict[str, dict[str, Any]], fixture_id: str
) -> None:
    row = fixtures_by_id[fixture_id]
    assert builder.execute_model(row) == row["expectations"]
    for calculation in row.get("calculations") or ():
        assert builder.evaluate(calculation) == calculation["expected"]


def test_f28_feature_ordering_and_bucket_coverage_are_upstream_owned(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F28: FeatureEngine owns order + coverage; narrative reducer is never consulted."""

    expected = set(fixtures_by_id["F28"]["expectations"])
    observed: set[str] = set()

    imports = [
        line
        for line in ENGINE_SOURCE.read_text(encoding="utf-8").splitlines()
        if line.startswith("from ") or line.startswith("import ")
    ]
    joined = "\n".join(imports)
    assert "NarrativeRuntime" not in joined
    assert "DetectorBank" not in joined

    # Upstream frames 10 then 12 reduce; duplicate/older 12/11 are audited no-ops.
    engine = FeatureEngine()
    frame_10 = engine.observe(_sample(observed_mono_ms=10_000, source_snapshot_id="snap:10"))
    frame_12 = engine.observe(_sample(observed_mono_ms=12_000, source_snapshot_id="snap:12"))
    dup_12 = engine.observe(_sample(observed_mono_ms=12_000, source_snapshot_id="snap:12-dup"))
    older_11 = engine.observe(_sample(observed_mono_ms=11_000, source_snapshot_id="snap:11"))
    assert frame_10.accepted is True and frame_10.frame is not None
    assert frame_12.accepted is True and frame_12.frame is not None
    assert frame_10.frame.frame_sequence == 1
    assert frame_12.frame.frame_sequence == 2
    assert dup_12.accepted is False
    assert older_11.accepted is False
    assert dup_12.diagnostic == "feature_frame_duplicate"
    assert older_11.diagnostic == "feature_frame_stale"
    assert engine.latest_frame() == frame_12.frame
    observed.add("reduce_10_12")
    observed.add("older_noop")

    # Lone sample: coverage capped to sample_interval; cannot validate trend.
    lone_engine = FeatureEngine(
        sample_interval_s=0.25,
        bucket_s=1.0,
        trend_window_s=6.0,
        min_coverage=0.8,
    )
    lone = lone_engine.observe(_sample(observed_mono_ms=1_000, source_snapshot_id="snap:lone"))
    assert lone.accepted is True and lone.frame is not None
    lone_ids = [item.feature_id for item in lone.frame.values]
    assert TREND_SLOPE not in lone_ids
    assert TREND_NET not in lone_ids
    assert TREND_COVERAGE not in lone_ids
    observed.add("coverage_capped")
    observed.add("invalid_lone_sample")

    # Covered window: OLS slope/net/coverage after >=3 usable buckets; identity holds.
    trend_engine = FeatureEngine(
        sample_interval_s=0.25,
        bucket_s=1.0,
        trend_window_s=6.0,
        min_coverage=0.5,
    )
    closer = 0.10
    step = None
    for index in range(17):
        gap_fraction = 0.04 - (index / 16.0) * 0.02
        step = trend_engine.observe(
            _sample(
                observed_mono_ms=1_000 + index * 250,
                source_snapshot_id=f"snap:trend:{index}",
                closer_lap_dist=closer,
                target_lap_dist=closer + gap_fraction,
            )
        )
    assert step is not None and step.frame is not None
    ids = [item.feature_id for item in step.frame.values]
    assert TREND_SLOPE in ids
    assert TREND_NET in ids
    assert TREND_COVERAGE in ids
    slope = _value(step.frame, TREND_SLOPE)
    net = _value(step.frame, TREND_NET)
    coverage = _value(step.frame, TREND_COVERAGE)
    assert slope.value < 0
    assert net.value > 0
    assert 0.0 < float(coverage.value) <= 1.0
    assert step.frame.stream_epoch == 1
    assert step.frame.occurrence_id is not None
    assert step.frame.lineage_id is not None
    assert step.frame.correlation_key == ("car:12", "car:34", "rel:1")
    observed.add("ols_three_buckets")
    observed.add("identity_match")

    assert observed == expected
