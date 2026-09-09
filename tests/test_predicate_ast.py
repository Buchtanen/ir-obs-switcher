"""#249 safe typed predicate AST: catalog compile, ternary unknown, temporal nodes."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from irswitch.contracts import ContractViolation, SessionRef
from irswitch.contracts.feature import FeatureFrame, FeatureValue
from irswitch.contracts.predicate import (
    MAX_DEPTH,
    BindingValue,
    CompiledDetectorCatalog,
    PredicateEnv,
    Verdict,
    compile_detector_catalog,
    compile_predicate,
    load_compiled_detector_catalog,
)
from irswitch.contracts.resources import packaged_schema_bytes
from irswitch.events.predicate_ast import PredicateEvaluator

ROOT = Path(__file__).resolve().parents[1]
GAP_V1 = "gap.relation.seconds.estimated_v1"


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
    observed_mono_ms: int = 1_000,
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
        frame_sequence=1,
        observed_mono_ms=observed_mono_ms,
        source_snapshot_id="snap:1",
        broadcast_epoch=4,
        stream_epoch=1,
        session_ref=SessionRef("sub:1", 2),
        occurrence_id="1:race:0",
        lineage_id="1:practice:0>1:race:0",
        correlation_key=("car:12", "car:34", "rel:1"),
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


def _env(
    now_mono_ms: int = 1_000,
    frame: FeatureFrame | None = None,
    bindings: dict[str, BindingValue] | None = None,
    parameters: dict[str, float | int] | None = None,
) -> PredicateEnv:
    return PredicateEnv(
        now_mono_ms=now_mono_ms,
        frame=_frame(now_mono_ms) if frame is None else frame,
        parameters=parameters if parameters is not None else _defaults(),
        bindings=bindings if bindings is not None else _enter_bindings(),
    )


def _atom_ids(node: object) -> set[str]:
    found: set[str] = set()
    stack = [node]
    while stack:
        current = stack.pop()
        atom_id = getattr(current, "atom_id", None)
        if isinstance(atom_id, str):
            found.add(atom_id)
        children = getattr(current, "children", None)
        if children:
            stack.extend(children)
        for name in ("body", "child", "condition"):
            nested = getattr(current, name, None)
            if nested is not None and nested is not current:
                stack.append(nested)
        steps = getattr(current, "steps", None)
        if steps:
            stack.extend(steps)
    return found


def test_packaged_catalog_compiles_frozen_predicates_and_invariants() -> None:
    catalog = load_compiled_detector_catalog()
    assert isinstance(catalog, CompiledDetectorCatalog)
    ahead = catalog.require("battle_ahead_v1")
    behind = catalog.require("battle_behind_v1")
    two_front = catalog.require("battle_two_front_v1")
    assert ahead.enter.atom_id is None
    assert _atom_ids(ahead.enter_signal) == {
        "stream_confirmed_active",
        "stage_race",
        "both_actors_racing_or_target_surface_known",
        "race_flag_green",
        "ordered_relation_stable",
        "feature_age_lte_stale_after_s",
        "gap_lte_enter_gap_max_s",
        "net_closing_gte_min_closing_change_s",
        "slope_lte_max_closing_slope",
        "coverage_gte_min_coverage",
        "confidence_gte_min_confidence",
        "actors_world_valid",
    }
    assert _atom_ids(ahead.clear) == {
        "gap_gte_exit_gap_min_s",
        "slope_gte_clear_slope",
        "coverage_lt_min_coverage",
        "confidence_lt_min_confidence",
        "feature_stale_or_unknown",
        "race_flag_not_green",
    }
    assert _atom_ids(ahead.immediate) == {
        "occurrence_or_stream_change",
        "ordered_target_or_relation_change",
        "pit_tow_teleport_or_not_in_world",
        "unsupported_stage",
        "checkered_or_session_end",
        "identity_conflict",
    }
    assert _atom_ids(ahead.material_update) == {
        "hysteretic_band_changed",
        "net_closing_delta_gte_material_change_s",
    }
    assert behind.enter_signal == ahead.enter_signal
    assert _atom_ids(two_front.enter_signal) == {
        "front_relation_active",
        "rear_relation_active",
        "same_stream_occurrence_hero",
        "distinct_targets",
    }
    assert ahead.invariants is not None
    assert two_front.invariants is None
    raw = _catalog()
    assert set(ahead.invariant_ids) == set(raw["definitions"][0]["crossFieldInvariants"])
    evaluator = PredicateEvaluator()
    assert evaluator.evaluate(ahead.enter_signal, _env()).verdict is Verdict.TRUE
    assert evaluator.evaluate(ahead.invariants, _env(frame=None)).verdict is Verdict.TRUE


def test_unknown_as_true_and_unknown_invariant_fail_catalog_load() -> None:
    raw = _catalog()
    raw["definitions"][0]["entry"]["unknownSatisfies"] = True
    with pytest.raises(ContractViolation, match="unknownSatisfies"):
        compile_detector_catalog(raw)
    raw = _catalog()
    raw["definitions"][0]["crossFieldInvariants"].append("eval('1+1') == 2")
    with pytest.raises(ContractViolation, match="undeclared invariant"):
        compile_detector_catalog(raw)


def test_undeclared_feature_or_parameter_fails_catalog_load() -> None:
    raw = _catalog()
    raw["definitions"][0]["features"] = [
        item for item in raw["definitions"][0]["features"] if item != "gap.trend.confidence"
    ]
    with pytest.raises(ContractViolation, match="undeclared feature"):
        compile_detector_catalog(raw)
    raw = _catalog()
    raw["definitions"][0]["parameters"] = [
        item for item in raw["definitions"][0]["parameters"] if item["id"] != "enter_gap_max_s"
    ]
    with pytest.raises(ContractViolation, match="undeclared parameter"):
        compile_detector_catalog(raw)


def test_incompatible_units_fail_compile() -> None:
    ahead = load_compiled_detector_catalog().require("battle_ahead_v1")
    with pytest.raises(ContractViolation, match="unit"):
        compile_predicate(
            {
                "lte": {
                    "left": {"feature": GAP_V1},
                    "right": {"parameter": "min_coverage"},
                }
            },
            ahead.context,
        )
    with pytest.raises(ContractViolation, match="unregistered feature"):
        compile_predicate(
            {"eq": {"left": {"feature": "gap.invented"}, "right": {"literal": [True, "boolean"]}}},
            ahead.context,
        )


def test_unknown_feature_does_not_satisfy_enter() -> None:
    compiled = load_compiled_detector_catalog().require("battle_ahead_v1")
    evaluator = PredicateEvaluator()
    missing = evaluator.evaluate(
        compiled.enter_signal, _env(frame=_frame(omit=frozenset({GAP_V1})))
    )
    stale = evaluator.evaluate(
        compiled.enter_signal, _env(now_mono_ms=3_500, frame=_frame(observed_mono_ms=1_000))
    )
    quality = evaluator.evaluate(
        compiled.enter_signal,
        _env(frame=_frame(**{GAP_V1: (1.8, "seconds", "unknown")})),
    )
    assert missing.verdict is Verdict.UNKNOWN
    assert stale.verdict is Verdict.FALSE
    assert quality.verdict is Verdict.UNKNOWN
    assert missing.satisfies is False
    held = evaluator.evaluate(compiled.enter, _env())
    assert held.verdict is Verdict.FALSE
    assert held.satisfies is False


def test_ternary_all_any_not_is_conservative() -> None:
    ahead = load_compiled_detector_catalog().require("battle_ahead_v1")
    env = _env(
        bindings={
            **_enter_bindings(),
            "stream.confirmed_active": _bound(None, "boolean", unknown=True),
        }
    )
    evaluator = PredicateEvaluator()
    all_mixed = compile_predicate(
        {
            "all": [
                {
                    "eq": {
                        "left": {"binding": "session.ended"},
                        "right": {"literal": [False, "boolean"]},
                    }
                },
                {
                    "eq": {
                        "left": {"binding": "stream.confirmed_active"},
                        "right": {"literal": [True, "boolean"]},
                    }
                },
            ]
        },
        ahead.context,
    )
    any_mixed = compile_predicate(
        {
            "any": [
                {
                    "eq": {
                        "left": {"binding": "session.ended"},
                        "right": {"literal": [True, "boolean"]},
                    }
                },
                {
                    "eq": {
                        "left": {"binding": "stream.confirmed_active"},
                        "right": {"literal": [True, "boolean"]},
                    }
                },
            ]
        },
        ahead.context,
    )
    not_unknown = compile_predicate(
        {
            "not": {
                "eq": {
                    "left": {"binding": "stream.confirmed_active"},
                    "right": {"literal": [True, "boolean"]},
                }
            }
        },
        ahead.context,
    )
    assert evaluator.evaluate(all_mixed, env).verdict is Verdict.UNKNOWN
    assert evaluator.evaluate(any_mixed, env).verdict is Verdict.UNKNOWN
    assert evaluator.evaluate(not_unknown, env).verdict is Verdict.UNKNOWN
    any_true = compile_predicate(
        {
            "any": [
                {
                    "eq": {
                        "left": {"binding": "session.ended"},
                        "right": {"literal": [False, "boolean"]},
                    }
                },
                {
                    "eq": {
                        "left": {"binding": "stream.confirmed_active"},
                        "right": {"literal": [True, "boolean"]},
                    }
                },
            ]
        },
        ahead.context,
    )
    assert evaluator.evaluate(any_true, env).verdict is Verdict.TRUE
    all_false = compile_predicate(
        {
            "all": [
                {
                    "eq": {
                        "left": {"binding": "session.ended"},
                        "right": {"literal": [True, "boolean"]},
                    }
                },
                {
                    "eq": {
                        "left": {"binding": "stream.confirmed_active"},
                        "right": {"literal": [True, "boolean"]},
                    }
                },
            ]
        },
        ahead.context,
    )
    assert evaluator.evaluate(all_false, env).verdict is Verdict.FALSE


def test_held_for_ignores_unknown_and_needs_continuous_true() -> None:
    compiled = load_compiled_detector_catalog().require("battle_ahead_v1")
    evaluator = PredicateEvaluator()
    first = evaluator.evaluate(compiled.enter, _env(now_mono_ms=1_000))
    mid = evaluator.evaluate(compiled.enter, _env(now_mono_ms=2_500))
    done = evaluator.evaluate(compiled.enter, _env(now_mono_ms=4_000))
    assert first.verdict is Verdict.FALSE
    assert mid.verdict is Verdict.FALSE
    assert done.verdict is Verdict.TRUE
    reset = PredicateEvaluator()
    reset.evaluate(compiled.enter, _env(now_mono_ms=1_000))
    reset.evaluate(
        compiled.enter,
        _env(now_mono_ms=2_000, frame=_frame(observed_mono_ms=2_000, omit=frozenset({GAP_V1}))),
    )
    again = reset.evaluate(
        compiled.enter, _env(now_mono_ms=4_000, frame=_frame(observed_mono_ms=4_000))
    )
    assert again.verdict is Verdict.FALSE
    held = reset.evaluate(
        compiled.enter, _env(now_mono_ms=7_000, frame=_frame(observed_mono_ms=7_000))
    )
    assert held.verdict is Verdict.TRUE


def test_changed_and_crossed_are_edges() -> None:
    ahead = load_compiled_detector_catalog().require("battle_ahead_v1")
    changed = compile_predicate({"changed": {"binding": "band"}}, ahead.context)
    crossed = compile_predicate(
        {
            "crossed": {
                "target": {"feature": GAP_V1},
                "threshold": {"parameter": "approach_enter_s"},
                "direction": "falling",
            }
        },
        ahead.context,
    )
    evaluator = PredicateEvaluator()
    first = evaluator.evaluate(
        changed, _env(bindings={**_enter_bindings(), "band": _bound("closing", "text")})
    )
    second = evaluator.evaluate(
        changed, _env(bindings={**_enter_bindings(), "band": _bound("approach", "text")})
    )
    third = evaluator.evaluate(
        changed, _env(bindings={**_enter_bindings(), "band": _bound("approach", "text")})
    )
    assert first.verdict is Verdict.FALSE
    assert second.verdict is Verdict.TRUE
    assert third.verdict is Verdict.FALSE
    wide = _frame(**{GAP_V1: (2.4, "seconds", "estimated")})
    inside = _frame(**{GAP_V1: (1.2, "seconds", "estimated")})
    edge = PredicateEvaluator()
    assert edge.evaluate(crossed, _env(frame=wide)).verdict is Verdict.FALSE
    assert edge.evaluate(crossed, _env(frame=inside)).verdict is Verdict.TRUE
    assert edge.evaluate(crossed, _env(frame=inside)).verdict is Verdict.FALSE


def test_within_since_count_sequence() -> None:
    ahead = load_compiled_detector_catalog().require("battle_ahead_v1")
    within = compile_predicate(
        {
            "within": {
                "seconds": {"literal": [1.0, "seconds"]},
                "condition": {
                    "eq": {
                        "left": {"binding": "identity.conflict"},
                        "right": {"literal": [True, "boolean"]},
                    }
                },
            }
        },
        ahead.context,
    )
    since = compile_predicate(
        {
            "since": {
                "eq": {
                    "left": {"binding": "session.ended"},
                    "right": {"literal": [True, "boolean"]},
                }
            }
        },
        ahead.context,
    )
    count = compile_predicate(
        {
            "count": {
                "seconds": {"literal": [2.0, "seconds"]},
                "minimum": {"literal": [2, "count"]},
                "condition": {
                    "eq": {
                        "left": {"binding": "identity.conflict"},
                        "right": {"literal": [True, "boolean"]},
                    }
                },
            }
        },
        ahead.context,
    )
    sequence = compile_predicate(
        {
            "sequence": {
                "seconds": {"literal": [3.0, "seconds"]},
                "steps": [
                    {
                        "eq": {
                            "left": {"binding": "band"},
                            "right": {"literal": ["approach", "text"]},
                        }
                    },
                    {"eq": {"left": {"binding": "band"}, "right": {"literal": ["attack", "text"]}}},
                ],
            }
        },
        ahead.context,
    )
    ev = PredicateEvaluator()
    off = {**_enter_bindings(), "identity.conflict": _bound(False, "boolean")}
    on = {**_enter_bindings(), "identity.conflict": _bound(True, "boolean")}
    assert ev.evaluate(within, _env(now_mono_ms=1_000, bindings=off)).verdict is Verdict.FALSE
    assert ev.evaluate(within, _env(now_mono_ms=1_200, bindings=on)).verdict is Verdict.TRUE
    assert ev.evaluate(within, _env(now_mono_ms=1_800, bindings=off)).verdict is Verdict.TRUE
    assert ev.evaluate(within, _env(now_mono_ms=2_400, bindings=off)).verdict is Verdict.FALSE
    sticky = PredicateEvaluator()
    ended_off = {**_enter_bindings(), "session.ended": _bound(False, "boolean")}
    ended_on = {**_enter_bindings(), "session.ended": _bound(True, "boolean")}
    assert sticky.evaluate(since, _env(bindings=ended_off)).verdict is Verdict.FALSE
    assert sticky.evaluate(since, _env(bindings=ended_on)).verdict is Verdict.TRUE
    assert sticky.evaluate(since, _env(bindings=ended_off)).verdict is Verdict.TRUE
    counter = PredicateEvaluator()
    assert counter.evaluate(count, _env(now_mono_ms=1_000, bindings=on)).verdict is Verdict.FALSE
    assert counter.evaluate(count, _env(now_mono_ms=1_400, bindings=off)).verdict is Verdict.FALSE
    assert counter.evaluate(count, _env(now_mono_ms=1_800, bindings=on)).verdict is Verdict.TRUE
    seq = PredicateEvaluator()
    closing = {**_enter_bindings(), "band": _bound("closing", "text")}
    approach = {**_enter_bindings(), "band": _bound("approach", "text")}
    attack = {**_enter_bindings(), "band": _bound("attack", "text")}
    assert (
        seq.evaluate(sequence, _env(now_mono_ms=1_000, bindings=closing)).verdict is Verdict.FALSE
    )
    assert (
        seq.evaluate(sequence, _env(now_mono_ms=1_500, bindings=approach)).verdict is Verdict.FALSE
    )
    assert seq.evaluate(sequence, _env(now_mono_ms=2_000, bindings=attack)).verdict is Verdict.TRUE


def test_equivalent_ast_and_state_are_deterministic() -> None:
    compiled = load_compiled_detector_catalog().require("battle_ahead_v1")
    first = PredicateEvaluator()
    second = PredicateEvaluator()
    times = (1_000, 2_000, 4_000)
    left = [first.evaluate(compiled.enter, _env(now_mono_ms=now)) for now in times]
    right = [second.evaluate(compiled.enter, _env(now_mono_ms=now)) for now in times]
    assert [item.verdict for item in left] == [item.verdict for item in right]
    assert [item.reason for item in left] == [item.reason for item in right]
    assert [item.verdict for item in left] == [Verdict.FALSE, Verdict.FALSE, Verdict.TRUE]


def test_recursion_and_eval_cost_are_bounded() -> None:
    ahead = load_compiled_detector_catalog().require("battle_ahead_v1")
    leaf = {"eq": {"left": {"binding": "session.ended"}, "right": {"literal": [False, "boolean"]}}}
    nested: object = leaf
    for _ in range(MAX_DEPTH + 2):
        nested = {"all": [nested]}
    with pytest.raises(ContractViolation, match="recursion"):
        compile_predicate(nested, ahead.context)
    with pytest.raises(ContractViolation, match="node count"):
        compile_predicate({"all": [leaf] * 200}, ahead.context)


def test_catalog_invariants_reject_bad_parameters() -> None:
    compiled = load_compiled_detector_catalog().require("battle_ahead_v1")
    assert compiled.invariants is not None
    bad = dict(_defaults())
    bad["enter_gap_max_s"] = 10.0
    result = PredicateEvaluator().evaluate(compiled.invariants, _env(frame=None, parameters=bad))
    assert result.verdict is Verdict.FALSE
    raw = _catalog()
    for item in raw["definitions"][0]["parameters"]:
        if item["id"] == "enter_gap_max_s":
            item["default"] = 10.0
    with pytest.raises(ContractViolation, match="invariant"):
        compile_detector_catalog(raw)


def test_clear_unknown_feature_is_true_and_never_uses_eval() -> None:
    compiled = load_compiled_detector_catalog().require("battle_ahead_v1")
    evaluator = PredicateEvaluator()
    missing = evaluator.evaluate(compiled.clear, _env(frame=_frame(omit=frozenset({GAP_V1}))))
    assert missing.verdict is Verdict.TRUE
    assert "feature_stale_or_unknown" in _atom_ids(compiled.clear)
    for path in (
        ROOT / "src/irswitch/contracts/predicate.py",
        ROOT / "src/irswitch/events/predicate_ast.py",
    ):
        source = path.read_text(encoding="utf-8")
        assert "eval(" not in source
        assert "exec(" not in source
        assert "compile(" not in source
    imports = [
        line
        for line in (ROOT / "src/irswitch/events/predicate_ast.py")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.startswith("from ") or line.startswith("import ")
    ]
    joined = "\n".join(imports)
    assert "NarrativeRuntime" not in joined
    assert "DetectorBank" not in joined
    assert "overlay.tape" not in joined
    assert "irswitch.commentary" not in joined
    assert "predicate_ast" not in Path(ROOT / "src/irswitch/events/__init__.py").read_text(
        encoding="utf-8"
    )


def test_two_front_unknown_relation_does_not_enter() -> None:
    compiled = load_compiled_detector_catalog().require("battle_two_front_v1")
    bindings = _enter_bindings()
    bindings["rear.relation_active"] = _bound(None, "boolean", unknown=True)
    result = PredicateEvaluator().evaluate(
        compiled.enter_signal,
        _env(frame=None, parameters=_defaults("battle_two_front_v1"), bindings=bindings),
    )
    assert result.verdict is Verdict.UNKNOWN
    assert result.satisfies is False
