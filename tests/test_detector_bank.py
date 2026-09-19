"""#250 generic correlated detector lifecycle FSM."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from irswitch.contracts import SessionRef
from irswitch.contracts.feature import FeatureFrame, FeatureValue
from irswitch.contracts.predicate import BindingValue, load_compiled_detector_catalog
from irswitch.contracts.resources import packaged_schema_bytes
from irswitch.events.detector_bank import (
    DetectorBank,
    DetectorInstanceKey,
    reduce_lifecycle,
)

ROOT = Path(__file__).resolve().parents[1]
GAP_V1 = "gap.relation.seconds.estimated_v1"
GOLDENS = json.loads(
    (ROOT / "docs/v2.0.0/machine/detector-catalog-goldens.json").read_text(encoding="utf-8")
)


def _catalog() -> dict:
    return json.loads(packaged_schema_bytes("detector-catalog.json"))


def _defaults(detector_id: str = "battle_ahead_v1") -> dict[str, float | int]:
    detector = next(item for item in _catalog()["definitions"] if item["id"] == detector_id)
    return {str(item["id"]): item["default"] for item in detector["parameters"]}


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
        quality=quality,
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
    **overrides: tuple[object, str] | tuple[object, str, str] | None,
) -> FeatureFrame:
    raw: dict[str, tuple[object, str] | tuple[object, str, str] | None] = {
        GAP_V1: (1.8, "seconds", "estimated"),
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


def _bank() -> DetectorBank:
    return DetectorBank()


def _step(
    bank: DetectorBank,
    frame: FeatureFrame,
    bindings: dict[str, BindingValue] | None = None,
    *,
    detector_ids: tuple[str, ...] = ("battle_ahead_v1",),
):
    return bank.step(
        frame,
        bindings=bindings if bindings is not None else _enter_bindings(),
        parameters=_defaults(),
        detector_ids=detector_ids,
    )


def _kinds(step: object) -> list[str]:
    return [item.kind for item in step.transitions]


@pytest.mark.parametrize("fixture", GOLDENS["directionalTraces"], ids=lambda row: row["id"])
def test_reduce_lifecycle_matches_directional_goldens(fixture: dict) -> None:
    state = "inactive"
    emissions: list[str | None] = []
    for row in fixture["steps"]:
        next_state, emission = reduce_lifecycle(
            state,
            enter=row["enter"],
            clear=row["clear"],
            immediate_invalidator=row["immediateInvalidator"],
            material_change=row["materialChange"],
            elapsed_in_state_s=row["elapsedInStateSeconds"],
            seconds_since_update=row["secondsSinceUpdate"],
        )
        assert next_state == row["stateAfter"]
        assert emission == row["emission"]
        assert state == row["stateBefore"]
        emissions.append(emission)
        state = next_state
    started = emissions.count("started")
    ended = emissions.count("ended")
    updated = emissions.count("updated")
    assertions = set(fixture["assertions"])
    if "one_started" in assertions:
        assert started == 1
    if "no_started" in assertions:
        assert started == 0
    if "no_second_started" in assertions:
        assert started == 1
    if "one_ended" in assertions:
        assert ended == 1
    if "one_updated" in assertions:
        assert updated == 1
    if "unknown_never_satisfies_enter" in assertions:
        assert started == 0
        assert state == "inactive"


def test_sustained_enter_starts_once_and_submits_hunting() -> None:
    bank = _bank()
    first = _step(bank, _frame())
    assert first.observations[0].previous_state == "inactive"
    assert first.observations[0].candidate_state == "candidate"
    assert _kinds(first) == []
    assert first.candidates == ()

    held = _step(bank, _frame(frame_sequence=2, observed_mono_ms=3_999))
    assert held.observations[0].candidate_state == "candidate"
    assert _kinds(held) == []

    started = _step(bank, _frame(frame_sequence=3, observed_mono_ms=4_000))
    assert started.observations[0].candidate_state == "active"
    assert _kinds(started) == ["STARTED"]
    assert started.transitions[0].reason == "enter_confirmed"
    assert started.candidates[0].kind == "HUNTING"
    assert started.observations[0].would_emit_event_kind == "HUNTING"
    assert "HUNTING_ENDED" not in {item.kind for item in started.candidates}

    stable = _step(bank, _frame(frame_sequence=4, observed_mono_ms=4_250))
    assert _kinds(stable) == []
    assert stable.candidates == ()
    assert stable.observations[0].candidate_state == "active"


def test_active_ticks_do_not_storm() -> None:
    bank = _bank()
    _step(bank, _frame())
    _step(bank, _frame(frame_sequence=2, observed_mono_ms=4_000))
    kinds: list[str] = []
    for index in range(3, 13):
        step = _step(bank, _frame(frame_sequence=index, observed_mono_ms=4_000 + index * 250))
        kinds.extend(_kinds(step))
        assert step.candidates == ()
    assert kinds == []


def test_braking_oscillation_does_not_enter() -> None:
    bank = _bank()
    _step(bank, _frame())
    broken = _step(
        bank,
        _frame(frame_sequence=2, observed_mono_ms=2_000, **{GAP_V1: (5.0, "seconds", "estimated")}),
    )
    assert broken.observations[0].candidate_state == "inactive"
    assert _kinds(broken) == []
    _step(bank, _frame(frame_sequence=3, observed_mono_ms=2_250))
    again = _step(
        bank,
        _frame(frame_sequence=4, observed_mono_ms=3_250, **{GAP_V1: (5.0, "seconds", "estimated")}),
    )
    assert _kinds(again) == []
    assert again.candidates == ()


def test_unknown_enter_breaks_confirmation() -> None:
    bank = _bank()
    _step(bank, _frame())
    unknown = _step(
        bank, _frame(frame_sequence=2, observed_mono_ms=2_000, omit=frozenset({GAP_V1}))
    )
    assert unknown.observations[0].previous_state == "candidate"
    assert unknown.observations[0].candidate_state == "inactive"
    assert _kinds(unknown) == []
    assert unknown.candidates == ()


def test_stale_clears_after_hold_without_v4_ended() -> None:
    bank = _bank()
    _step(bank, _frame())
    started = _step(bank, _frame(frame_sequence=2, observed_mono_ms=4_000))
    assert _kinds(started) == ["STARTED"]
    clearing = _step(
        bank,
        _frame(frame_sequence=3, observed_mono_ms=4_250, omit=frozenset({GAP_V1})),
    )
    assert clearing.observations[0].candidate_state == "clearing"
    assert _kinds(clearing) == []
    held = _step(
        bank,
        _frame(frame_sequence=4, observed_mono_ms=6_240, omit=frozenset({GAP_V1})),
    )
    assert held.observations[0].candidate_state == "clearing"
    ended = _step(
        bank,
        _frame(frame_sequence=5, observed_mono_ms=6_250, omit=frozenset({GAP_V1})),
    )
    assert ended.observations[0].candidate_state == "inactive"
    assert _kinds(ended) == ["ENDED"]
    assert ended.transitions[0].v4_event_kind is None
    assert ended.observations[0].would_emit_event_kind is None
    assert ended.candidates == ()
    assert ended.expired_facts == ("battle.closing",)
    assert "HUNTING_ENDED" not in {item.kind for item in ended.candidates}


def test_target_swap_ends_only_the_old_instance() -> None:
    bank = _bank()
    _step(bank, _frame())
    _step(bank, _frame(frame_sequence=2, observed_mono_ms=4_000))
    swapped = _step(
        bank,
        _frame(
            frame_sequence=3,
            observed_mono_ms=4_250,
            correlation_key=("car:12", "car:99", "rel:2"),
        ),
        {
            **_enter_bindings(),
            "target_id": _bound("car:99", "id"),
            "relation_epoch": _bound("rel:2", "id"),
        },
    )
    assert _kinds(swapped) == ["ENDED"]
    assert swapped.transitions[0].reason == "immediate_invalidator"
    assert swapped.transitions[0].instance.correlation_key == ("car:12", "car:34", "rel:1")
    assert swapped.observations[-1].candidate_state == "candidate"
    assert swapped.observations[-1].correlation_key == ("car:12", "car:99", "rel:2")
    assert swapped.candidates == ()
    assert any(item.expire_facts == ("battle.closing",) for item in swapped.transitions)


def test_material_update_is_rate_limited_and_maps_v4() -> None:
    bank = _bank()
    _step(bank, _frame())
    _step(bank, _frame(frame_sequence=2, observed_mono_ms=4_000))
    early = _step(
        bank,
        _frame(
            frame_sequence=3,
            observed_mono_ms=9_990,
            **{"gap.trend.net_closing": (1.4, "seconds")},
        ),
    )
    assert _kinds(early) == []
    updated = _step(
        bank,
        _frame(
            frame_sequence=4,
            observed_mono_ms=10_000,
            **{"gap.trend.net_closing": (1.4, "seconds")},
        ),
    )
    assert _kinds(updated) == ["UPDATED"]
    assert updated.transitions[0].reason == "material_updated"
    assert updated.candidates[0].kind == "HUNTING"
    assert updated.observations[0].would_emit_event_kind == "HUNTING"
    assert updated.transitions[0].material_revision == 2


def test_clear_cancelled_by_full_enter_has_no_second_started() -> None:
    bank = _bank()
    _step(bank, _frame())
    _step(bank, _frame(frame_sequence=2, observed_mono_ms=4_000))
    clearing = _step(
        bank,
        _frame(frame_sequence=3, observed_mono_ms=4_250, **{GAP_V1: (5.0, "seconds", "estimated")}),
    )
    assert clearing.observations[0].candidate_state == "clearing"
    restored = _step(bank, _frame(frame_sequence=4, observed_mono_ms=5_250))
    assert restored.observations[0].candidate_state == "active"
    assert _kinds(restored) == []
    assert restored.candidates == ()


def test_duplicate_and_older_frames_are_audited_noops() -> None:
    bank = _bank()
    _step(bank, _frame())
    started = _step(bank, _frame(frame_sequence=2, observed_mono_ms=4_000))
    assert _kinds(started) == ["STARTED"]
    duplicate = _step(bank, _frame(frame_sequence=2, observed_mono_ms=4_000))
    assert duplicate.accepted is False
    assert duplicate.diagnostic == "detector_frame_duplicate"
    assert _kinds(duplicate) == []
    older = _step(bank, _frame(frame_sequence=1, observed_mono_ms=3_000))
    assert older.accepted is False
    assert older.diagnostic == "detector_frame_stale"
    assert _kinds(older) == []
    later = _step(bank, _frame(frame_sequence=3, observed_mono_ms=4_250))
    assert later.accepted is True
    assert later.observations[0].candidate_state == "active"
    assert _kinds(later) == []


def test_instance_keys_keep_detectors_independent() -> None:
    bank = _bank()
    step = _step(
        bank,
        _frame(),
        detector_ids=("battle_ahead_v1", "battle_behind_v1"),
    )
    keys = {item.detector_id for item in step.observations}
    assert keys == {"battle_ahead_v1", "battle_behind_v1"}
    _step(
        bank,
        _frame(frame_sequence=2, observed_mono_ms=4_000),
        detector_ids=("battle_ahead_v1", "battle_behind_v1"),
    )
    ahead = bank.instance(
        DetectorInstanceKey("battle_ahead_v1", 1, 1, "1:race:0", ("car:12", "car:34", "rel:1"))
    )
    behind = bank.instance(
        DetectorInstanceKey("battle_behind_v1", 1, 1, "1:race:0", ("car:12", "car:34", "rel:1"))
    )
    assert ahead is not None and ahead.state == "active"
    assert behind is not None and behind.state == "active"
    kinds = {
        item.kind
        for item in bank.step(
            _frame(frame_sequence=3, observed_mono_ms=4_250),
            bindings=_enter_bindings(),
            parameters=_defaults(),
            detector_ids=("battle_ahead_v1", "battle_behind_v1"),
        ).candidates
    }
    assert kinds == set()


def test_required_capture_loss_ends_and_stays_disabled() -> None:
    bank = _bank()
    _step(bank, _frame())
    _step(bank, _frame(frame_sequence=2, observed_mono_ms=4_000))
    closed = bank.disable_for_run(("battle_ahead_v1",), "required_capture_lost")
    assert _kinds(closed) == ["ENDED"]
    assert closed.transitions[0].reason == "required_capture_lost"
    assert closed.candidates == ()
    assert closed.expired_facts == ("battle.closing",)
    later = _step(bank, _frame(frame_sequence=3, observed_mono_ms=7_000))
    assert later.observations == ()
    assert _kinds(later) == []
    assert later.candidates == ()


def test_composite_is_not_driven_and_bank_stays_isolated() -> None:
    bank = _bank()
    step = bank.step(
        _frame(),
        bindings=_enter_bindings(),
        parameters=_defaults(),
        detector_ids=None,
    )
    assert all(item.detector_id != "battle_two_front_v1" for item in step.observations)
    assert "BATTLE_FOR_POSITION" not in {item.kind for item in step.candidates}
    compiled = load_compiled_detector_catalog()
    assert compiled.require("battle_ahead_v1").hold_parameter == "confirm_s"
    source = (ROOT / "src/irswitch/events/detector_bank.py").read_text(encoding="utf-8")
    assert "eval(" not in source
    assert "exec(" not in source
    assert "compile(" not in source
    imports = [
        line
        for line in source.splitlines()
        if line.startswith("from ") or line.startswith("import ")
    ]
    joined = "\n".join(imports)
    assert "NarrativeRuntime" not in joined
    assert "irswitch.commentary" not in joined
    assert "overlay.tape" not in joined
    init = (ROOT / "src/irswitch/events/__init__.py").read_text(encoding="utf-8")
    assert "detector_bank" not in init
    assert "DetectorBank" not in init
