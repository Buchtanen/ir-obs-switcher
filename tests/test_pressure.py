"""#254 UNDER_PRESSURE temporal detector — battle_behind_v1 band projection."""

from __future__ import annotations

import json

from irswitch.contracts import SessionRef
from irswitch.contracts.feature import FeatureFrame, FeatureValue
from irswitch.contracts.predicate import BindingValue
from irswitch.contracts.primitives import FactQuality
from irswitch.contracts.resources import packaged_schema_bytes
from irswitch.events.closing import reduce_band as closing_reduce_band
from irswitch.events.detector_bank import DetectorBank
from irswitch.events.pressure import PressureDetector, PressureStep, reduce_band

GAP_V1 = "gap.relation.seconds.estimated_v1"
REAR_KEY = ("car:7", "car:12", "rel:rear")


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
    correlation_key: tuple[str, ...] = REAR_KEY,
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
        "relation_epoch": _bound("rel:rear", "id"),
        "target_id": _bound("car:7", "id"),
        "band": _bound("closing", "text"),
        "front.relation_active": _bound(True, "boolean"),
        "rear.relation_active": _bound(True, "boolean"),
        "same_stream_occurrence_hero": _bound(True, "boolean"),
        "distinct_targets": _bound(True, "boolean"),
        "front.relation_epoch": _bound("rel:front", "id"),
        "rear.relation_epoch": _bound("rel:rear", "id"),
        "front.target_id": _bound("car:2", "id"),
        "rear.target_id": _bound("car:7", "id"),
    }


def _kinds(step: PressureStep) -> list[str]:
    return [item.kind for item in step.candidates]


def _activate(
    detector: PressureDetector,
    *,
    gap: float = 1.8,
    overlap_active: bool | None = None,
) -> PressureStep:
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


def test_catalog_contract_is_rear_pressure() -> None:
    catalog = json.loads(packaged_schema_bytes("detector-catalog.json"))
    rec = next(item for item in catalog["definitions"] if item["id"] == "battle_behind_v1")
    assert rec["orderedActors"] == ["challengerBehind", "hero"]
    assert rec["output"]["startEvent"] == "HUNTED"
    assert rec["output"]["internalKind"] == "battle.pressure_behind"
    assert rec["output"]["tapeChannel"] == "race.battle.pressure"
    assert rec["output"]["factPredicate"] == "battle.closing"
    assert rec["output"]["endedEvent"] is None


def test_reuses_shared_reduce_band() -> None:
    assert reduce_band is closing_reduce_band
    assert reduce_band("closing", gap=1.80) == "closing"
    assert reduce_band("closing", gap=0.95) == "approach"


def test_sustained_pressure_emits_hunted_once() -> None:
    detector = PressureDetector()
    started = _activate(detector)
    assert _kinds(started) == ["HUNTED"]
    assert started.candidates[0].narrative_kind == "battle.pressure_behind"
    assert started.candidates[0].tape_channel == "race.battle.pressure"
    assert started.candidates[0].detector_id == "battle_behind_v1"
    assert started.trace is not None
    assert started.trace.band == "closing"
    assert started.trace.fsm_state == "active"
    assert started.trace.effective_thresholds["confirm_s"] == 3.0
    assert "snap:1" in started.trace.evidence_refs
    assert started.transitions[-1].instance.correlation_key == REAR_KEY
    stable = detector.observe(
        _frame(frame_sequence=3, observed_mono_ms=4_250),
        bindings=_enter_bindings(),
    )
    assert _kinds(stable) == []


def test_one_braking_spike_cannot_activate() -> None:
    detector = PressureDetector()
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


def test_inward_band_emits_rival_threat_not_ahead_kinds() -> None:
    detector = PressureDetector()
    _activate(detector, gap=1.8)
    approached = detector.observe(
        _frame(frame_sequence=3, observed_mono_ms=4_250, gap=1.50),
        bindings=_enter_bindings(),
    )
    assert _kinds(approached) == ["RIVAL_THREAT"]
    assert approached.candidates[0].narrative_kind == "battle.rival_threat"
    assert approached.candidates[0].tape_channel == "race.battle.pressure"
    assert approached.trace is not None and approached.trace.band == "approach"
    assert approached.published_facts == ("battle.position_threat",)
    assert "APPROACH" not in _kinds(approached)
    assert "HUNTING" not in _kinds(approached)


def test_inward_skip_emits_only_latest_rival_threat() -> None:
    detector = PressureDetector()
    started = _activate(detector, gap=0.30, overlap_active=True)
    assert _kinds(started) == ["RIVAL_THREAT"]
    assert started.candidates[0].narrative_kind == "battle.rival_threat"
    assert started.trace is not None
    assert started.trace.band == "overlap"
    assert "HUNTED" not in _kinds(started)
    assert "SIDE_BY_SIDE" not in _kinds(started)
    assert "APPROACH" not in _kinds(started)
    assert "ATTACK_RANGE" not in _kinds(started)


def test_outward_walk_stays_on_rival_threat() -> None:
    detector = PressureDetector()
    _activate(detector, gap=0.30, overlap_active=True)
    outward = detector.observe(
        _frame(frame_sequence=3, observed_mono_ms=4_250, gap=0.55),
        bindings=_enter_bindings(),
        overlap_active=True,
    )
    assert _kinds(outward) == ["RIVAL_THREAT"]
    assert outward.trace is not None and outward.trace.band == "attack"
    assert "SIDE_BY_SIDE" not in _kinds(outward)
    assert "APPROACH" not in _kinds(outward)


def test_target_change_closes_old_instance_without_v4_end() -> None:
    detector = PressureDetector()
    _activate(detector, gap=1.50)
    ended = detector.observe(
        _frame(
            frame_sequence=3,
            observed_mono_ms=4_250,
            correlation_key=("car:11", "car:12", "rel:2"),
        ),
        bindings=_enter_bindings(),
    )
    assert "ENDED" in {item.kind for item in ended.transitions}
    assert not any(kind.endswith("_ENDED") for kind in _kinds(ended))
    assert "HUNTED_ENDED" not in _kinds(ended)
    assert "battle.closing" in ended.expired_facts
    assert "battle.position_threat" in ended.expired_facts


def test_decision_trace_exposes_thresholds_and_evidence() -> None:
    detector = PressureDetector()
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
    detector = PressureDetector()
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
    detector = PressureDetector()
    detector.observe(_frame(), bindings=_enter_bindings())
    missing = detector.observe(
        _frame(frame_sequence=2, observed_mono_ms=2_000, omit=frozenset({GAP_V1})),
        bindings=_enter_bindings(),
    )
    assert missing.accepted is True
    assert _kinds(missing) == []
    assert missing.trace is not None and missing.trace.gap_s is None


def test_pressure_is_not_exported_and_does_not_drive_composite() -> None:
    import irswitch.events as events

    assert not hasattr(events, "PressureDetector")
    assert not hasattr(events, "reduce_band")
    bank = DetectorBank()
    step = bank.step(
        _frame(),
        bindings=_enter_bindings(),
        detector_ids=("battle_two_front_v1",),
    )
    assert step.observations == ()
    assert step.candidates == ()


def test_pressure_uses_only_behind_catalog_row() -> None:
    detector = PressureDetector()
    started = _activate(detector)
    assert started.candidates[0].detector_id == "battle_behind_v1"
    assert all(item.instance.detector_id == "battle_behind_v1" for item in started.transitions)
    assert started.candidates[0].kind == "HUNTED"


def test_pressure_bounded_memory() -> None:
    detector = PressureDetector()
    _activate(detector)
    for seq in range(3, 40):
        detector.observe(
            _frame(frame_sequence=seq, observed_mono_ms=4_000 + seq * 250),
            bindings=_enter_bindings(),
        )
    assert len(detector._bands) <= 1
