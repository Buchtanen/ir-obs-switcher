"""#247 typed FeatureEngine registry and bounded windows."""

from __future__ import annotations

from pathlib import Path

import pytest

from irswitch.contracts import ContractViolation, FactQuality, SessionRef
from irswitch.contracts.feature import (
    FIRST_SLICE_FEATURE_ID,
    FeatureFrame,
    FeatureValue,
    load_feature_registry,
    validate_detector_feature_units,
)
from irswitch.events.feature_engine import FeatureEngine, FeatureSample, FeatureStep

ROOT = Path(__file__).resolve().parents[1]


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


def test_registry_exposes_exactly_the_frozen_21_feature_ids() -> None:
    registry = load_feature_registry()
    assert len(registry.features) == 21
    assert FIRST_SLICE_FEATURE_ID == "gap.relation.seconds.estimated_v1"
    spec = registry.require(FIRST_SLICE_FEATURE_ID)
    assert spec.unit == "seconds"
    assert spec.algorithm_id == FIRST_SLICE_FEATURE_ID
    later = registry.require("gap.relation.seconds.est_time_v1")
    assert later.algorithm_id != FIRST_SLICE_FEATURE_ID
    with pytest.raises(ContractViolation, match="unregistered"):
        registry.require("gap.relation.seconds.estimated_v2")


def test_feature_frame_round_trip_and_sorted_values() -> None:
    value = FeatureValue(
        feature_id=FIRST_SLICE_FEATURE_ID,
        value=1.8,
        unit="seconds",
        quality="estimated",
        observed_mono_ms=1_000,
        valid_until_mono_ms=None,
        evidence_refs=("snap:1",),
    )
    frame = FeatureFrame(
        frame_sequence=1,
        observed_mono_ms=1_000,
        source_snapshot_id="snap:1",
        broadcast_epoch=4,
        stream_epoch=1,
        session_ref=SessionRef("sub:1", 2),
        occurrence_id="1:race:0",
        lineage_id="1:practice:0>1:race:0",
        correlation_key=("car:12", "car:34", "rel:1"),
        values=(value,),
    )
    payload = frame.to_dict()
    assert payload["schemaVersion"] == "feature-frame/2"
    assert FeatureFrame.from_dict(payload) == frame
    late = FeatureValue(
        feature_id="gap.target_stable",
        value=True,
        unit="boolean",
        quality="derived",
        observed_mono_ms=1_000,
        valid_until_mono_ms=None,
        evidence_refs=("snap:1",),
    )
    with pytest.raises(ContractViolation, match="sorted"):
        FeatureFrame(
            frame_sequence=2,
            observed_mono_ms=1_000,
            source_snapshot_id="snap:2",
            broadcast_epoch=4,
            stream_epoch=1,
            session_ref=SessionRef("sub:1", 2),
            occurrence_id="1:race:0",
            lineage_id="1:practice:0>1:race:0",
            correlation_key=("car:12",),
            values=(value, late) if str(value.feature_id) > str(late.feature_id) else (late, value),
        )


def test_identity_is_all_or_none() -> None:
    value = FeatureValue(
        feature_id=FIRST_SLICE_FEATURE_ID,
        value=1.0,
        unit="seconds",
        quality="estimated",
        observed_mono_ms=1_000,
        valid_until_mono_ms=None,
        evidence_refs=("snap:1",),
    )
    with pytest.raises(ContractViolation, match="all coherent or all null"):
        FeatureFrame(
            frame_sequence=1,
            observed_mono_ms=1_000,
            source_snapshot_id="snap:1",
            broadcast_epoch=4,
            stream_epoch=1,
            session_ref=SessionRef("sub:1", 2),
            occurrence_id=None,
            lineage_id="1:race:0",
            correlation_key=("car:12",),
            values=(value,),
        )


def test_estimated_v1_is_deterministic_and_uses_lap_distance_times_reference() -> None:
    engine = FeatureEngine()
    first = engine.observe(_sample())
    second = FeatureEngine().observe(_sample())
    assert first.frame == second.frame
    assert first.frame is not None
    values = first.frame.values
    assert len(values) == 1
    assert values[0].feature_id == FIRST_SLICE_FEATURE_ID
    assert values[0].value == pytest.approx(1.8)
    assert values[0].unit == "seconds"
    assert values[0].quality is FactQuality.ESTIMATED
    assert first.frame.frame_sequence == 1


def test_estimated_v1_unknown_on_missing_reference_pit_or_wrap_ambiguity() -> None:
    engine = FeatureEngine()
    missing = engine.observe(_sample(hero_lap_ref_s=None))
    assert missing.frame is not None
    assert missing.frame.values == ()
    assert "missing_lap_reference" in missing.diagnostics
    pit = FeatureEngine().observe(_sample(in_pit=True, source_snapshot_id="snap:pit"))
    assert pit.frame is not None
    assert pit.frame.values == ()
    assert "pit_tow_teleport" in pit.diagnostics
    wrap = FeatureEngine().observe(
        _sample(
            closer_lap_dist=0.02,
            target_lap_dist=0.98,
            source_snapshot_id="snap:wrap",
        )
    )
    assert wrap.frame is not None
    assert wrap.frame.values == ()
    assert "wrap_ambiguity" in wrap.diagnostics


def test_target_swap_and_occurrence_change_reset_windows() -> None:
    engine = FeatureEngine()
    first = engine.observe(_sample())
    swapped = engine.observe(
        _sample(
            observed_mono_ms=1_100,
            source_snapshot_id="snap:2",
            target_id="car:99",
            relation_epoch="rel:2",
        )
    )
    assert first.frame is not None and swapped.frame is not None
    assert swapped.frame.frame_sequence == 2
    assert "target_swap" in swapped.diagnostics
    assert swapped.frame.values == ()
    later = engine.observe(
        _sample(
            observed_mono_ms=1_200,
            source_snapshot_id="snap:3",
            target_id="car:99",
            relation_epoch="rel:2",
            closer_lap_dist=0.20,
            target_lap_dist=0.23,
        )
    )
    assert later.frame is not None
    assert later.frame.values[0].value == pytest.approx(2.7)
    reset = engine.observe(
        _sample(
            observed_mono_ms=1_300,
            source_snapshot_id="snap:4",
            occurrence_id="1:race:1",
            lineage_id="1:practice:0>1:race:1",
            target_id="car:99",
            relation_epoch="rel:2",
        )
    )
    assert reset.frame is not None
    assert "occurrence_reset" in reset.diagnostics
    assert engine.window_size("car:12", "car:99", "rel:2") == 1


def test_duplicate_or_older_samples_are_noop() -> None:
    engine = FeatureEngine()
    first = engine.observe(_sample())
    dup = engine.observe(_sample())
    older = engine.observe(_sample(observed_mono_ms=900, source_snapshot_id="snap:old"))
    assert first.accepted is True
    assert dup.accepted is False
    assert older.accepted is False
    assert dup.diagnostic == "feature_frame_duplicate"
    assert older.diagnostic == "feature_frame_stale"
    assert dup.frame == first.frame
    assert engine.latest_frame() == first.frame
    assert first.frame is not None
    assert first.frame.frame_sequence == 1


def test_windows_are_bounded_and_catalog_text_is_not_executed() -> None:
    engine = FeatureEngine(window_capacity=4, correlation_capacity=2)
    for index in range(8):
        engine.observe(
            _sample(
                observed_mono_ms=1_000 + index,
                source_snapshot_id=f"snap:{index}",
                closer_lap_dist=0.10 + index * 0.01,
                target_lap_dist=0.14 + index * 0.01,
            )
        )
    assert engine.window_size("car:12", "car:34", "rel:1") == 4
    engine.observe(
        _sample(
            observed_mono_ms=2_000,
            source_snapshot_id="snap:other",
            closer_id="car:1",
            target_id="car:2",
            relation_epoch="rel:x",
        )
    )
    engine.observe(
        _sample(
            observed_mono_ms=2_100,
            source_snapshot_id="snap:third",
            closer_id="car:8",
            target_id="car:9",
            relation_epoch="rel:y",
        )
    )
    assert engine.correlation_count() <= 2
    source = (ROOT / "src/irswitch/events/feature_engine.py").read_text(encoding="utf-8")
    assert "eval(" not in source
    assert "exec(" not in source
    assert "compile(" not in source


def test_detector_feature_units_match_the_registry() -> None:
    validate_detector_feature_units()
    imports = [
        line
        for line in (ROOT / "src/irswitch/events/feature_engine.py")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.startswith("from ") or line.startswith("import ")
    ]
    joined = "\n".join(imports)
    assert "NarrativeRuntime" not in joined
    assert "DetectorBank" not in joined
    assert "overlay.tape" not in joined


def test_later_estimators_are_registered_not_silently_substituted() -> None:
    engine = FeatureEngine()
    step: FeatureStep = engine.observe(_sample())
    assert step.frame is not None
    ids = [value.feature_id for value in step.frame.values]
    assert ids == [FIRST_SLICE_FEATURE_ID]
    assert "gap.relation.seconds.est_time_v1" not in ids
    assert "gap.relation.seconds.hybrid_v1" not in ids
