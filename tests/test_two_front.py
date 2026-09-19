"""#255 composite two-front detector — battle_two_front_v1."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from irswitch.contracts import SessionRef
from irswitch.contracts.feature import FeatureFrame, FeatureValue
from irswitch.contracts.predicate import BindingValue
from irswitch.contracts.primitives import FactQuality
from irswitch.contracts.resources import packaged_schema_bytes
from irswitch.events.detector_bank import DetectorBank
from irswitch.events.two_front import TwoFrontDetector, TwoFrontStep, reduce_composite

ROOT = Path(__file__).resolve().parents[1]
GOLDENS = json.loads(
    (ROOT / "docs/v2.0.0/machine/detector-catalog-goldens.json").read_text(encoding="utf-8")
)


def _value(
    feature_id: str,
    value: bool | int | float | str,
    unit: str,
    *,
    observed_mono_ms: int = 1_000,
) -> FeatureValue:
    return FeatureValue(
        feature_id=feature_id,
        value=value,
        unit=unit,
        quality=FactQuality("measured"),
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
) -> FeatureFrame:
    values = (
        _value(
            "gap.relation.seconds.estimated_v1",
            1.8,
            "seconds",
            observed_mono_ms=observed_mono_ms,
        ),
    )
    return FeatureFrame(
        frame_sequence=frame_sequence,
        observed_mono_ms=observed_mono_ms,
        source_snapshot_id="snap:1",
        broadcast_epoch=4,
        stream_epoch=stream_epoch,
        session_ref=SessionRef("sub:1", 2),
        occurrence_id=occurrence_id,
        lineage_id="1:practice:0>1:race:0",
        correlation_key=("car:7", "car:12", "car:2"),
        values=values,
    )


def _bound(
    value: bool | int | float | str | None, unit: str, *, unknown: bool = False
) -> BindingValue:
    return BindingValue(value=value, unit=unit, unknown=unknown)


def _enter_bindings(
    *,
    front_active: bool | None = True,
    rear_active: bool | None = True,
    same_hero: bool = True,
    distinct: bool = True,
    front_epoch: str = "rel:front",
    rear_epoch: str = "rel:rear",
    front_target: str = "car:2",
    rear_target: str = "car:7",
    occurrence_id: str = "1:race:0",
    stream_epoch: int = 1,
    unknown_rear: bool = False,
) -> dict[str, BindingValue]:
    return {
        "front.relation_active": (
            _bound(None, "boolean", unknown=True)
            if front_active is None
            else _bound(front_active, "boolean")
        ),
        "rear.relation_active": (
            _bound(None, "boolean", unknown=True)
            if unknown_rear or rear_active is None
            else _bound(rear_active, "boolean")
        ),
        "same_stream_occurrence_hero": _bound(same_hero, "boolean"),
        "distinct_targets": _bound(distinct, "boolean"),
        "front.relation_epoch": _bound(front_epoch, "id"),
        "rear.relation_epoch": _bound(rear_epoch, "id"),
        "front.target_id": _bound(front_target, "id"),
        "rear.target_id": _bound(rear_target, "id"),
        "occurrence_id": _bound(occurrence_id, "id"),
        "stream_epoch": _bound(stream_epoch, "count"),
    }


def _kinds(step: TwoFrontStep) -> list[str]:
    return [item.kind for item in step.candidates]


def _activate(detector: TwoFrontDetector, **bind_kw: object) -> TwoFrontStep:
    bindings = _enter_bindings(**bind_kw)  # type: ignore[arg-type]
    detector.observe(
        _frame(),
        bindings=bindings,
        front_closing=True,
        rear_closing=True,
    )
    return detector.observe(
        _frame(frame_sequence=2, observed_mono_ms=2_000),
        bindings=bindings,
        front_closing=True,
        rear_closing=True,
    )


@pytest.mark.parametrize("fixture", GOLDENS["compositeScenarios"], ids=lambda row: row["id"])
def test_reduce_composite_matches_frozen_goldens(fixture: dict) -> None:
    state, emission = reduce_composite(fixture["initialState"], fixture)
    assert (emission or state) == fixture["result"]


def test_catalog_contract_is_composite_two_front() -> None:
    catalog = json.loads(packaged_schema_bytes("detector-catalog.json"))
    rec = next(item for item in catalog["definitions"] if item["id"] == "battle_two_front_v1")
    assert rec["kind"] == "composite"
    assert rec["orderedActors"] == ["rear", "hero", "front"]
    assert rec["correlationKey"] == [
        "streamEpoch",
        "occurrenceId",
        "frontRelationEpoch",
        "rearRelationEpoch",
    ]
    assert rec["output"]["startEvent"] == "BATTLE_FOR_POSITION"
    assert rec["output"]["internalKind"] == "battle.two_front"
    assert rec["output"]["tapeChannel"] == "race.battle.two_front"
    assert rec["output"]["featureId"] == "battle.two_front_active"
    assert rec["output"]["factPredicate"] is None
    assert rec["output"]["endedEvent"] is None


def test_confirmed_entry_emits_battle_for_position_once() -> None:
    detector = TwoFrontDetector()
    started = _activate(detector)
    assert _kinds(started) == ["BATTLE_FOR_POSITION"]
    assert started.candidates[0].narrative_kind == "battle.two_front"
    assert started.candidates[0].tape_channel == "race.battle.two_front"
    assert started.candidates[0].detector_id == "battle_two_front_v1"
    assert started.published_features == ("battle.two_front_active",)
    assert started.published_facts == ()
    assert started.trace is not None
    assert started.trace.fsm_state == "active"
    assert started.trace.effective_thresholds["two_front_confirm_s"] == 1.0
    assert "snap:1" in started.trace.evidence_refs
    assert started.transitions[-1].instance.correlation_key == (
        "1",
        "1:race:0",
        "rel:front",
        "rel:rear",
    )
    stable = detector.observe(
        _frame(frame_sequence=3, observed_mono_ms=2_250),
        bindings=_enter_bindings(),
        front_closing=True,
        rear_closing=True,
    )
    assert _kinds(stable) == []
    assert "UPDATED" not in {item.kind for item in stable.transitions}


def test_missing_parent_closing_does_not_create_truth() -> None:
    detector = TwoFrontDetector()
    detector.observe(_frame(), bindings=_enter_bindings(), front_closing=True, rear_closing=False)
    step = detector.observe(
        _frame(frame_sequence=2, observed_mono_ms=2_000),
        bindings=_enter_bindings(),
        front_closing=True,
        rear_closing=False,
    )
    assert _kinds(step) == []
    assert step.published_facts == ()
    assert step.published_features == ()
    assert step.trace is not None and step.trace.fsm_state == "inactive"


def test_same_target_does_not_open() -> None:
    detector = TwoFrontDetector()
    step = _activate(detector, distinct=False, front_target="car:7", rear_target="car:7")
    assert _kinds(step) == []
    assert step.trace is not None and step.trace.fsm_state == "inactive"


def test_unknown_relation_does_not_enter() -> None:
    detector = TwoFrontDetector()
    step = _activate(detector, unknown_rear=True)
    assert _kinds(step) == []
    assert step.trace is not None and step.trace.fsm_state == "inactive"


def test_target_swap_is_new_identity_without_v4_end() -> None:
    detector = TwoFrontDetector()
    _activate(detector)
    swapped = detector.observe(
        _frame(frame_sequence=3, observed_mono_ms=2_250),
        bindings=_enter_bindings(front_epoch="rel:front-2", front_target="car:9"),
        front_closing=True,
        rear_closing=True,
    )
    assert "ENDED" in {item.kind for item in swapped.transitions}
    assert not any(kind.endswith("_ENDED") for kind in _kinds(swapped))
    assert "BATTLE_FOR_POSITION_ENDED" not in _kinds(swapped)
    assert "battle.two_front_active" in swapped.cleared_features
    assert swapped.expired_facts == ()
    ended = next(item for item in swapped.transitions if item.kind == "ENDED")
    assert ended.instance.correlation_key == ("1", "1:race:0", "rel:front", "rel:rear")
    live = [item for item in swapped.transitions if item.kind != "ENDED"]
    if live:
        assert live[-1].instance.correlation_key == ("1", "1:race:0", "rel:front-2", "rel:rear")
    assert _kinds(swapped) == []


def test_temporary_one_side_loss_restores_without_new_start() -> None:
    detector = TwoFrontDetector()
    _activate(detector)
    lost = detector.observe(
        _frame(frame_sequence=3, observed_mono_ms=2_250),
        bindings=_enter_bindings(front_active=False),
        front_closing=False,
        rear_closing=True,
    )
    assert _kinds(lost) == []
    assert "ENDED" not in {item.kind for item in lost.transitions}
    restored = detector.observe(
        _frame(frame_sequence=4, observed_mono_ms=3_240),
        bindings=_enter_bindings(),
        front_closing=True,
        rear_closing=True,
    )
    assert restored.trace is not None and restored.trace.fsm_state == "active"
    assert _kinds(restored) == []
    assert "STARTED" not in {item.kind for item in restored.transitions}


def test_one_side_loss_at_clear_closes_without_touching_parent_facts() -> None:
    detector = TwoFrontDetector()
    _activate(detector)
    detector.observe(
        _frame(frame_sequence=3, observed_mono_ms=2_250),
        bindings=_enter_bindings(front_active=False),
        front_closing=False,
        rear_closing=True,
    )
    ended = detector.observe(
        _frame(frame_sequence=4, observed_mono_ms=3_250),
        bindings=_enter_bindings(front_active=False),
        front_closing=False,
        rear_closing=True,
    )
    assert "ENDED" in {item.kind for item in ended.transitions}
    assert _kinds(ended) == []
    assert ended.expired_facts == ()
    assert ended.published_facts == ()
    assert "battle.two_front_active" in ended.cleared_features
    assert "battle.closing" not in ended.expired_facts


def test_duplicate_and_stale_frames_are_audited() -> None:
    detector = TwoFrontDetector()
    detector.observe(_frame(), bindings=_enter_bindings(), front_closing=True, rear_closing=True)
    dup = detector.observe(
        _frame(), bindings=_enter_bindings(), front_closing=True, rear_closing=True
    )
    assert dup.accepted is False
    assert dup.diagnostic == "detector_frame_duplicate"
    detector.observe(
        _frame(frame_sequence=2, observed_mono_ms=2_000),
        bindings=_enter_bindings(),
        front_closing=True,
        rear_closing=True,
    )
    stale = detector.observe(
        _frame(frame_sequence=1, observed_mono_ms=500),
        bindings=_enter_bindings(),
        front_closing=True,
        rear_closing=True,
    )
    assert stale.accepted is False
    assert stale.diagnostic == "detector_frame_stale"


def test_two_front_is_not_exported_and_bank_stays_directional() -> None:
    import irswitch.events as events

    assert not hasattr(events, "TwoFrontDetector")
    assert not hasattr(events, "reduce_composite")
    bank = DetectorBank()
    step = bank.step(
        _frame(),
        bindings=_enter_bindings(),
        detector_ids=("battle_two_front_v1",),
    )
    assert step.observations == ()
    assert step.candidates == ()


def test_bounded_memory() -> None:
    detector = TwoFrontDetector()
    _activate(detector)
    for seq in range(3, 20):
        detector.observe(
            _frame(frame_sequence=seq, observed_mono_ms=2_000 + seq * 250),
            bindings=_enter_bindings(front_epoch=f"rel:front-{seq}"),
            front_closing=True,
            rear_closing=True,
        )
    assert len(detector._instances) <= 1


def test_decision_trace_exposes_guards() -> None:
    detector = TwoFrontDetector()
    started = _activate(detector)
    assert started.trace is not None
    assert started.trace.front_active is True
    assert started.trace.rear_active is True
    assert started.trace.distinct_targets is True
    assert started.trace.front_closing is True
    assert started.trace.rear_closing is True
    assert started.trace.effective_thresholds["two_front_clear_s"] == 1.0
    assert started.trace.transition_reason == "enter_confirmed"
