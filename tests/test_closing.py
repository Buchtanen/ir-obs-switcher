"""#253 CLOSING temporal detector — battle_ahead_v1 band projection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from irswitch.contracts import SessionRef
from irswitch.contracts.feature import FeatureFrame, FeatureValue
from irswitch.contracts.predicate import BindingValue
from irswitch.contracts.primitives import FactQuality
from irswitch.events.closing import ClosingDetector, ClosingStep, reduce_band
from irswitch.events.detector_bank import DetectorBank

ROOT = Path(__file__).resolve().parents[1]
GAP_V1 = "gap.relation.seconds.estimated_v1"
GOLDENS = json.loads(
    (ROOT / "docs/v2.0.0/machine/detector-catalog-goldens.json").read_text(encoding="utf-8")
)


def _value(
    feature_id: str,
    value: bool | int | float | str,
    unit: str,
    *,
    observed_mono_ms: int = 1_000,
    quality: str = "measured",
) -> FeatureValue:
    return FeatureValue(
        feature_id=feature_id,
        value=value,
        unit=unit,
        quality=FactQuality(quality),
        observed_mono_ms=observed_mono_ms,
        valid_until_mono_ms=None,
        evidence_refs=("snap:1",),
    )


def _frame(
    *,
    frame_sequence: int = 1,
    observed_mono_ms: int = 1_000,
    stream_epoch: int = 1,
    occurrence_id: str = "1:race:0",
    correlation_key: tuple[str, ...] = ("car:12", "car:34", "rel:1"),
    omit: frozenset[str] = frozenset(),
    gap: float | None = None,
    **overrides: tuple[object, str] | tuple[object, str, str] | None,
) -> FeatureFrame:
    raw: dict[str, tuple[object, str] | tuple[object, str, str] | None] = {
        GAP_V1: (1.8 if gap is None else gap, "seconds", "estimated"),
        "gap.trend.slope": (-0.08, "seconds_per_second"),
        "gap.trend.net_closing": (0.9, "seconds"),
        "gap.trend.coverage": (0.9, "fraction"),
        "gap.trend.confidence": (0.85, "fraction"),
        "gap.target_stable": (True, "boolean"),
        "vehicle.phase.current": ("racing", "vehicle_phase"),
    }
    raw.update(overrides)
    values = []
    for feature_id, spec in raw.items():
        if spec is None or feature_id in omit:
            continue
        quality = spec[2] if len(spec) == 3 else "measured"
        values.append(
            _value(
                feature_id,
                spec[0],  # type: ignore[arg-type]
                spec[1],
                observed_mono_ms=observed_mono_ms,
                quality=quality,
            )
        )
    values.sort(key=lambda item: item.feature_id)
    return FeatureFrame(
        frame_sequence=frame_sequence,
        observed_mono_ms=observed_mono_ms,
        source_snapshot_id="snap:1",
        broadcast_epoch=4,
        stream_epoch=stream_epoch,
        session_ref=SessionRef("sub:1", 2),
        occurrence_id=occurrence_id,
        lineage_id="1:practice:0>1:race:0",
        correlation_key=correlation_key,
        values=tuple(values),
    )


def _bound(
    value: bool | int | float | str | None, unit: str, *, unknown: bool = False
) -> BindingValue:
    return BindingValue(value=value, unit=unit, unknown=unknown)


def _enter_bindings() -> dict[str, BindingValue]:
    return {
        "stream.confirmed_active": _bound(True, "boolean"),
        "session.stage": _bound("race", "stage"),
        "race.flag": _bound("green", "text"),
        "target.phase": _bound("racing", "vehicle_phase"),
        "target.surface_known": _bound(True, "boolean"),
        "actors.world_valid": _bound(True, "boolean"),
        "session.ended": _bound(False, "boolean"),
        "identity.conflict": _bound(False, "boolean"),
        "occurrence_id": _bound("1:race:0", "id"),
        "stream_epoch": _bound(1, "count"),
        "relation_epoch": _bound("rel:1", "id"),
        "target_id": _bound("car:34", "id"),
        "band": _bound("closing", "text"),
        "front.relation_active": _bound(True, "boolean"),
        "rear.relation_active": _bound(True, "boolean"),
        "same_stream_occurrence_hero": _bound(True, "boolean"),
        "distinct_targets": _bound(True, "boolean"),
        "front.relation_epoch": _bound("rel:front", "id"),
        "rear.relation_epoch": _bound("rel:rear", "id"),
        "front.target_id": _bound("car:2", "id"),
        "rear.target_id": _bound("car:9", "id"),
    }


def _kinds(step: ClosingStep) -> list[str]:
    return [item.kind for item in step.candidates]


def _activate(
    detector: ClosingDetector,
    *,
    gap: float = 1.8,
    overlap_active: bool | None = None,
) -> ClosingStep:
    detector.observe(
        _frame(gap=gap),
        bindings=_enter_bindings(),
        overlap_active=overlap_active,
    )
    return detector.observe(
        _frame(frame_sequence=2, observed_mono_ms=4_000, gap=gap),
        bindings=_enter_bindings(),
        overlap_active=overlap_active,
    )


@pytest.mark.parametrize("fixture", GOLDENS["bandBoundaries"], ids=lambda row: row["id"])
def test_reduce_band_matches_frozen_goldens(fixture: dict) -> None:
    assert (
        reduce_band(
            fixture["from"],
            gap=fixture["gap"],
            overlap_held=float(fixture.get("overlapHeld", 0.0)),
            overlap_known=bool(fixture.get("overlapKnown", True)),
        )
        == fixture["to"]
    )


def test_overlap_without_hold_stays_on_attack() -> None:
    assert reduce_band("attack", gap=0.35, overlap_held=0.0, overlap_known=True) == "attack"


def test_sustained_closing_emits_hunting_once() -> None:
    detector = ClosingDetector()
    started = _activate(detector)
    assert _kinds(started) == ["HUNTING"]
    assert started.candidates[0].narrative_kind == "battle.pursuit"
    assert started.trace is not None
    assert started.trace.band == "closing"
    assert started.trace.fsm_state == "active"
    assert started.trace.effective_thresholds["confirm_s"] == 3.0
    assert "snap:1" in started.trace.evidence_refs
    stable = detector.observe(
        _frame(frame_sequence=3, observed_mono_ms=4_250),
        bindings=_enter_bindings(),
    )
    assert _kinds(stable) == []


def test_one_braking_spike_cannot_activate() -> None:
    detector = ClosingDetector()
    detector.observe(_frame(), bindings=_enter_bindings())
    spike = detector.observe(
        _frame(frame_sequence=2, observed_mono_ms=2_000, gap=5.0),
        bindings=_enter_bindings(),
    )
    assert spike.trace is not None and spike.trace.fsm_state == "inactive"
    assert _kinds(spike) == []
    detector.observe(_frame(frame_sequence=3, observed_mono_ms=2_250), bindings=_enter_bindings())
    again = detector.observe(
        _frame(frame_sequence=4, observed_mono_ms=3_250, gap=5.0),
        bindings=_enter_bindings(),
    )
    assert _kinds(again) == []


def test_approach_band_emits_one_existing_v4_identifier() -> None:
    detector = ClosingDetector()
    _activate(detector, gap=1.8)
    approached = detector.observe(
        _frame(frame_sequence=3, observed_mono_ms=4_250, gap=1.50),
        bindings=_enter_bindings(),
    )
    assert _kinds(approached) == ["APPROACH"]
    assert approached.candidates[0].narrative_kind == "battle.approach"
    assert approached.candidates[0].tape_channel == "race.battle.closing"
    assert approached.trace is not None and approached.trace.band == "approach"
    assert approached.published_facts == ("battle.approaching",)


def test_inward_skip_emits_only_latest_band() -> None:
    detector = ClosingDetector()
    started = _activate(detector, gap=0.30, overlap_active=True)
    assert _kinds(started) == ["SIDE_BY_SIDE"]
    assert started.candidates[0].narrative_kind == "battle.side_by_side"
    assert started.trace is not None
    assert started.trace.band == "overlap"
    assert "HUNTING" not in _kinds(started)
    assert "APPROACH" not in _kinds(started)
    assert "ATTACK_RANGE" not in _kinds(started)


def test_outward_walk_does_not_replay_intermediate_bands() -> None:
    detector = ClosingDetector()
    _activate(detector, gap=0.30, overlap_active=True)
    outward = detector.observe(
        _frame(frame_sequence=3, observed_mono_ms=4_250, gap=0.55),
        bindings=_enter_bindings(),
        overlap_active=True,
    )
    assert _kinds(outward) == ["ATTACK_RANGE"]
    assert outward.trace is not None and outward.trace.band == "attack"
    assert outward.expired_facts == ("battle.side_by_side",)
    assert "APPROACH" not in _kinds(outward)


def test_close_expires_facts_without_new_v4_end() -> None:
    detector = ClosingDetector()
    _activate(detector, gap=1.50)
    ended = detector.observe(
        _frame(
            frame_sequence=3,
            observed_mono_ms=4_250,
            correlation_key=("car:12", "car:99", "rel:2"),
        ),
        bindings=_enter_bindings(),
    )
    assert "ENDED" in {item.kind for item in ended.transitions}
    assert not any(kind.endswith("_ENDED") for kind in _kinds(ended))
    assert "HUNTING_ENDED" not in _kinds(ended)
    assert "battle.closing" in ended.expired_facts
    assert "battle.approaching" in ended.expired_facts


def test_decision_trace_exposes_thresholds_and_evidence() -> None:
    detector = ClosingDetector()
    started = _activate(detector)
    assert started.trace is not None
    thresholds = started.trace.effective_thresholds
    assert thresholds["enter_gap_max_s"] == 3.0
    assert thresholds["min_closing_change_s"] == 0.6
    assert thresholds["max_closing_slope"] == -0.04
    assert thresholds["approach_enter_s"] == 1.5
    assert started.trace.gap_s == 1.8
    assert started.trace.slope == -0.08
    assert started.trace.net_closing_s == 0.9
    assert started.trace.coverage == 0.9
    assert started.trace.transition_reason == "enter_confirmed"


def test_duplicate_and_stale_frames_are_audited() -> None:
    detector = ClosingDetector()
    detector.observe(_frame(), bindings=_enter_bindings())
    dup = detector.observe(_frame(), bindings=_enter_bindings())
    assert dup.accepted is False
    assert dup.diagnostic == "detector_frame_duplicate"
    detector.observe(
        _frame(frame_sequence=2, observed_mono_ms=2_000),
        bindings=_enter_bindings(),
    )
    stale = detector.observe(
        _frame(frame_sequence=1, observed_mono_ms=500),
        bindings=_enter_bindings(),
    )
    assert stale.accepted is False
    assert stale.diagnostic == "detector_frame_stale"


def test_missing_gap_is_fail_soft() -> None:
    detector = ClosingDetector()
    detector.observe(_frame(), bindings=_enter_bindings())
    missing = detector.observe(
        _frame(frame_sequence=2, observed_mono_ms=2_000, omit=frozenset({GAP_V1})),
        bindings=_enter_bindings(),
    )
    assert missing.accepted is True
    assert _kinds(missing) == []
    assert missing.trace is not None and missing.trace.gap_s is None


def test_closing_is_not_exported_and_does_not_drive_composite() -> None:
    import irswitch.events as events

    assert not hasattr(events, "ClosingDetector")
    assert not hasattr(events, "reduce_band")
    bank = DetectorBank()
    step = bank.step(
        _frame(),
        bindings=_enter_bindings(),
        detector_ids=("battle_two_front_v1",),
    )
    assert step.observations == ()
    assert step.candidates == ()
