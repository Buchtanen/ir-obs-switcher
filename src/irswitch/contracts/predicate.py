"""Typed predicate AST: compile catalog guards without executing catalog text."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from typing import Any

from .feature import (
    FIRST_SLICE_FEATURE_ID,
    FeatureFrame,
    FeatureRegistry,
    load_feature_registry,
    validate_detector_feature_units,
)
from .primitives import ContractViolation, Identifier, ScalarType
from .resources import packaged_schema_bytes

MAX_DEPTH = 16
MAX_NODES = 128
MAX_EVAL_STEPS = 512

_GAP_FEATURE_ID = FIRST_SLICE_FEATURE_ID
_PHASE_FEATURE_ID = "vehicle.phase.current"
_SLOPE_FEATURE_ID = "gap.trend.slope"
_NET_FEATURE_ID = "gap.trend.net_closing"
_COVERAGE_FEATURE_ID = "gap.trend.coverage"
_CONFIDENCE_FEATURE_ID = "gap.trend.confidence"
_STABLE_FEATURE_ID = "gap.target_stable"

_COMPATIBLE_UNITS = {
    "gap_seconds": ScalarType.SECONDS.value,
}

BINDING_UNITS: dict[str, str] = {
    "stream.confirmed_active": ScalarType.BOOLEAN.value,
    "session.stage": ScalarType.STAGE.value,
    "race.flag": ScalarType.TEXT.value,
    "target.phase": ScalarType.VEHICLE_PHASE.value,
    "target.surface_known": ScalarType.BOOLEAN.value,
    "actors.world_valid": ScalarType.BOOLEAN.value,
    "session.ended": ScalarType.BOOLEAN.value,
    "identity.conflict": ScalarType.BOOLEAN.value,
    "occurrence_id": ScalarType.ID.value,
    "stream_epoch": ScalarType.COUNT.value,
    "relation_epoch": ScalarType.ID.value,
    "target_id": ScalarType.ID.value,
    "band": ScalarType.TEXT.value,
    "front.relation_active": ScalarType.BOOLEAN.value,
    "rear.relation_active": ScalarType.BOOLEAN.value,
    "same_stream_occurrence_hero": ScalarType.BOOLEAN.value,
    "distinct_targets": ScalarType.BOOLEAN.value,
    "front.relation_epoch": ScalarType.ID.value,
    "rear.relation_epoch": ScalarType.ID.value,
    "front.target_id": ScalarType.ID.value,
    "rear.target_id": ScalarType.ID.value,
}


class Verdict(StrEnum):
    TRUE = "true"
    FALSE = "false"
    UNKNOWN = "unknown"


class CompareOp(StrEnum):
    EQ = "eq"
    NE = "ne"
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"
    IN = "in"
    NOT_IN = "not_in"
    BETWEEN = "between"


def canonical_unit(unit: str) -> str:
    return _COMPATIBLE_UNITS.get(unit, unit)


def units_compatible(left: str, right: str) -> bool:
    return canonical_unit(left) == canonical_unit(right)


def product_unit(left: str, right: str) -> str:
    pair = (canonical_unit(left), canonical_unit(right))
    if pair in {("count", "seconds"), ("seconds", "count")}:
        return ScalarType.SECONDS.value
    raise ContractViolation(f"incompatible product units {left} * {right}")


@dataclass(frozen=True, slots=True)
class FeatureRef:
    feature_id: str
    unit: str


@dataclass(frozen=True, slots=True)
class ParameterRef:
    parameter_id: str
    unit: str


@dataclass(frozen=True, slots=True)
class BindingRef:
    name: str
    unit: str


@dataclass(frozen=True, slots=True)
class LiteralValue:
    value: bool | int | float | str
    unit: str


@dataclass(frozen=True, slots=True)
class FeatureAgeRef:
    feature_id: str
    unit: str = ScalarType.SECONDS.value


@dataclass(frozen=True, slots=True)
class ProductRef:
    left: ValueExpr
    right: ValueExpr
    unit: str


ValueExpr = FeatureRef | ParameterRef | BindingRef | LiteralValue | FeatureAgeRef | ProductRef


@dataclass(frozen=True, slots=True)
class AllNode:
    children: tuple[PredicateNode, ...]
    atom_id: str | None = None


@dataclass(frozen=True, slots=True)
class AnyNode:
    children: tuple[PredicateNode, ...]
    atom_id: str | None = None


@dataclass(frozen=True, slots=True)
class NotNode:
    child: PredicateNode
    atom_id: str | None = None


@dataclass(frozen=True, slots=True)
class CompareNode:
    op: CompareOp
    left: ValueExpr
    right: ValueExpr | tuple[ValueExpr, ...]
    atom_id: str | None = None


@dataclass(frozen=True, slots=True)
class ChangedNode:
    target: ValueExpr
    atom_id: str | None = None


@dataclass(frozen=True, slots=True)
class ChangedByNode:
    target: ValueExpr
    amount: ValueExpr
    atom_id: str | None = None


@dataclass(frozen=True, slots=True)
class CrossedNode:
    target: ValueExpr
    threshold: ValueExpr
    direction: str = "any"
    atom_id: str | None = None


@dataclass(frozen=True, slots=True)
class RisingEdgeNode:
    child: PredicateNode
    atom_id: str | None = None


@dataclass(frozen=True, slots=True)
class FallingEdgeNode:
    child: PredicateNode
    atom_id: str | None = None


@dataclass(frozen=True, slots=True)
class HeldForNode:
    seconds: ValueExpr
    condition: PredicateNode
    atom_id: str | None = None


@dataclass(frozen=True, slots=True)
class WithinNode:
    seconds: ValueExpr
    condition: PredicateNode
    atom_id: str | None = None


@dataclass(frozen=True, slots=True)
class SinceNode:
    condition: PredicateNode
    atom_id: str | None = None


@dataclass(frozen=True, slots=True)
class CountNode:
    seconds: ValueExpr
    minimum: ValueExpr
    condition: PredicateNode
    atom_id: str | None = None


@dataclass(frozen=True, slots=True)
class SequenceNode:
    seconds: ValueExpr
    steps: tuple[PredicateNode, ...]
    atom_id: str | None = None


@dataclass(frozen=True, slots=True)
class UnknownCheckNode:
    target: ValueExpr
    atom_id: str | None = None


@dataclass(frozen=True, slots=True)
class FeatureUnusableNode:
    feature_id: str
    stale_after: ParameterRef
    atom_id: str | None = None


PredicateNode = (
    AllNode
    | AnyNode
    | NotNode
    | CompareNode
    | ChangedNode
    | ChangedByNode
    | CrossedNode
    | RisingEdgeNode
    | FallingEdgeNode
    | HeldForNode
    | WithinNode
    | SinceNode
    | CountNode
    | SequenceNode
    | UnknownCheckNode
    | FeatureUnusableNode
)


@dataclass(frozen=True, slots=True)
class CompileContext:
    detector_id: str
    features: frozenset[str]
    parameters: Mapping[str, str]
    registry: FeatureRegistry


@dataclass(frozen=True, slots=True)
class BindingValue:
    value: bool | int | float | str | None = None
    unit: str = ScalarType.BOOLEAN.value
    unknown: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "unit", str(self.unit))
        if self.unknown:
            object.__setattr__(self, "value", None)
            return
        if self.value is None or isinstance(self.value, (list, dict)):
            raise ContractViolation("BindingValue.value must be boolean, number, or string")


@dataclass(frozen=True, slots=True)
class PredicateEnv:
    now_mono_ms: int
    parameters: Mapping[str, int | float]
    bindings: Mapping[str, BindingValue]
    frame: FeatureFrame | None = None


@dataclass(frozen=True, slots=True)
class ReasonNode:
    node: str
    verdict: Verdict
    detail: str
    children: tuple[ReasonNode, ...] = ()


@dataclass(frozen=True, slots=True)
class PredicateResult:
    verdict: Verdict
    reason: ReasonNode

    @property
    def satisfies(self) -> bool:
        return self.verdict is Verdict.TRUE


@dataclass(frozen=True, slots=True)
class CompiledDetector:
    detector_id: str
    version: int
    enter: PredicateNode
    enter_signal: PredicateNode
    clear: PredicateNode
    immediate: PredicateNode
    material_update: PredicateNode | None
    invariants: PredicateNode | None
    invariant_ids: tuple[str, ...]
    context: CompileContext
    hold_parameter: str
    clear_hold_parameter: str


@dataclass(frozen=True, slots=True)
class CompiledDetectorCatalog:
    detectors: tuple[CompiledDetector, ...]

    def require(self, detector_id: str) -> CompiledDetector:
        for item in self.detectors:
            if item.detector_id == detector_id:
                return item
        raise ContractViolation(f"unknown detector: {detector_id!r}")


def _require_id(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise ContractViolation(f"{field} must be a string")
    return str(Identifier(value))


def _feature(ctx: CompileContext, feature_id: object) -> FeatureRef:
    ident = _require_id(feature_id, "feature")
    spec = ctx.registry.require(ident)
    if ident not in ctx.features:
        raise ContractViolation(f"undeclared feature {ident!r} on detector {ctx.detector_id!r}")
    return FeatureRef(ident, spec.unit)


def _parameter(ctx: CompileContext, parameter_id: object) -> ParameterRef:
    ident = _require_id(parameter_id, "parameter")
    if ident not in ctx.parameters:
        raise ContractViolation(f"undeclared parameter {ident!r} on detector {ctx.detector_id!r}")
    return ParameterRef(ident, str(ctx.parameters[ident]))


def _binding(name: object) -> BindingRef:
    ident = _require_id(name, "binding")
    if ident not in BINDING_UNITS:
        raise ContractViolation(f"undeclared binding {ident!r}")
    return BindingRef(ident, BINDING_UNITS[ident])


def _literal(value: object, unit: object) -> LiteralValue:
    if value is None or isinstance(value, (list, dict)):
        raise ContractViolation("literal must be boolean, number, or string")
    if not isinstance(value, (bool, int, float, str)):
        raise ContractViolation("literal must be boolean, number, or string")
    return LiteralValue(value, canonical_unit(str(unit)))


def _value_unit(expr: ValueExpr) -> str:
    return expr.unit


def _check_compare_units(
    op: CompareOp, left: ValueExpr, right: ValueExpr | tuple[ValueExpr, ...]
) -> None:
    if isinstance(right, tuple):
        for item in right:
            if not units_compatible(_value_unit(left), _value_unit(item)):
                raise ContractViolation(
                    f"incompatible units {left.unit} {op.value} {_value_unit(item)}"
                )
        return
    if not units_compatible(_value_unit(left), _value_unit(right)):
        raise ContractViolation(f"incompatible units {left.unit} {op.value} {right.unit}")


def _compile_value(raw: object, ctx: CompileContext) -> ValueExpr:
    if not isinstance(raw, dict) or any(not isinstance(key, str) for key in raw):
        raise ContractViolation("value must be a JSON object")
    if "feature" in raw:
        return _feature(ctx, raw["feature"])
    if "parameter" in raw:
        return _parameter(ctx, raw["parameter"])
    if "binding" in raw:
        return _binding(raw["binding"])
    if "age" in raw:
        return FeatureAgeRef(_feature(ctx, raw["age"]).feature_id)
    if "product" in raw:
        parts = raw["product"]
        if not isinstance(parts, (list, tuple)) or len(parts) != 2:
            raise ContractViolation("product must contain two values")
        left = _compile_value(parts[0], ctx)
        right = _compile_value(parts[1], ctx)
        return ProductRef(left, right, product_unit(left.unit, right.unit))
    if "literal" in raw:
        literal = raw["literal"]
        if isinstance(literal, list) and len(literal) == 2:
            return _literal(literal[0], literal[1])
        if "unit" in raw:
            return _literal(literal, raw["unit"])
        raise ContractViolation("literal requires a unit")
    if "seconds" in raw and set(raw) == {"seconds"}:
        return _literal(raw["seconds"], ScalarType.SECONDS.value)
    raise ContractViolation(f"unknown value fields: {sorted(raw)}")


def _single_key(raw: dict[str, Any]) -> tuple[str, Any]:
    if len(raw) != 1:
        raise ContractViolation("predicate must be a single-key object")
    key, body = next(iter(raw.items()))
    return key, body


def compile_predicate(
    raw: object,
    ctx: CompileContext,
    *,
    _depth: int = 1,
    _count: list[int] | None = None,
) -> PredicateNode:
    """Compile one named atom or structured node. Catalog strings are never executed."""

    if _depth > MAX_DEPTH:
        raise ContractViolation("predicate recursion exceeds bound")
    counter = _count if _count is not None else [0]
    counter[0] += 1
    if counter[0] > MAX_NODES:
        raise ContractViolation("predicate node count exceeds bound")

    def child(node: object) -> PredicateNode:
        return compile_predicate(node, ctx, _depth=_depth + 1, _count=counter)

    if isinstance(raw, str):
        return _compile_atom(raw, ctx, _depth=_depth, _count=counter)
    if not isinstance(raw, dict) or any(not isinstance(key, str) for key in raw):
        raise ContractViolation("predicate must be an atom id or a single-key object")
    kind, body = _single_key(raw)
    if kind == "all":
        if not isinstance(body, list) or not body:
            raise ContractViolation("all requires a nonempty list")
        return AllNode(children=tuple(child(item) for item in body))
    if kind == "any":
        if not isinstance(body, list) or not body:
            raise ContractViolation("any requires a nonempty list")
        return AnyNode(children=tuple(child(item) for item in body))
    if kind == "not":
        return NotNode(child=child(body))
    if kind in {item.value for item in CompareOp}:
        if not isinstance(body, dict):
            raise ContractViolation(f"{kind} requires an object")
        op = CompareOp(kind)
        if op is CompareOp.BETWEEN:
            left = _compile_value(body["left"], ctx)
            low = _compile_value(body["low"], ctx)
            high = _compile_value(body["high"], ctx)
            _check_compare_units(op, left, (low, high))
            return CompareNode(op, left, (low, high))
        if op in {CompareOp.IN, CompareOp.NOT_IN}:
            left = _compile_value(body["left"], ctx)
            raw_right = body["right"]
            if not isinstance(raw_right, list) or not raw_right:
                raise ContractViolation(f"{kind} right must be a nonempty list")
            members = tuple(_compile_value(item, ctx) for item in raw_right)
            _check_compare_units(op, left, members)
            return CompareNode(op, left, members)
        left = _compile_value(body["left"], ctx)
        other = _compile_value(body["right"], ctx)
        _check_compare_units(op, left, other)
        return CompareNode(op, left, other)
    if kind == "changed":
        return ChangedNode(target=_compile_value(body, ctx))
    if kind == "changed_by":
        if not isinstance(body, dict):
            raise ContractViolation("changed_by requires an object")
        target = _compile_value(body["target"], ctx)
        amount = _compile_value(body["amount"], ctx)
        _check_compare_units(CompareOp.GTE, target, amount)
        return ChangedByNode(target=target, amount=amount)
    if kind == "crossed":
        if not isinstance(body, dict):
            raise ContractViolation("crossed requires an object")
        target = _compile_value(body["target"], ctx)
        threshold = _compile_value(body["threshold"], ctx)
        direction = str(body.get("direction", "any"))
        if direction not in {"any", "rising", "falling"}:
            raise ContractViolation(f"unknown crossed direction {direction!r}")
        _check_compare_units(CompareOp.EQ, target, threshold)
        return CrossedNode(target=target, threshold=threshold, direction=direction)
    if kind == "rising_edge":
        return RisingEdgeNode(child=child(body))
    if kind == "falling_edge":
        return FallingEdgeNode(child=child(body))
    if kind == "held_for":
        if not isinstance(body, dict):
            raise ContractViolation("held_for requires an object")
        seconds = _compile_value(body["seconds"], ctx)
        if canonical_unit(seconds.unit) != ScalarType.SECONDS.value:
            raise ContractViolation("held_for seconds must use seconds")
        return HeldForNode(seconds=seconds, condition=child(body["condition"]))
    if kind == "within":
        if not isinstance(body, dict):
            raise ContractViolation("within requires an object")
        seconds = _compile_value(body["seconds"], ctx)
        if canonical_unit(seconds.unit) != ScalarType.SECONDS.value:
            raise ContractViolation("within seconds must use seconds")
        return WithinNode(seconds=seconds, condition=child(body["condition"]))
    if kind == "since":
        return SinceNode(condition=child(body))
    if kind == "count":
        if not isinstance(body, dict):
            raise ContractViolation("count requires an object")
        seconds = _compile_value(body["seconds"], ctx)
        minimum = _compile_value(body["minimum"], ctx)
        if canonical_unit(seconds.unit) != ScalarType.SECONDS.value:
            raise ContractViolation("count seconds must use seconds")
        if canonical_unit(minimum.unit) != ScalarType.COUNT.value:
            raise ContractViolation("count minimum must use count")
        return CountNode(seconds=seconds, minimum=minimum, condition=child(body["condition"]))
    if kind == "sequence":
        if not isinstance(body, dict):
            raise ContractViolation("sequence requires an object")
        seconds = _compile_value(body["seconds"], ctx)
        steps = body.get("steps")
        if canonical_unit(seconds.unit) != ScalarType.SECONDS.value:
            raise ContractViolation("sequence seconds must use seconds")
        if not isinstance(steps, list) or not steps:
            raise ContractViolation("sequence requires a nonempty steps list")
        return SequenceNode(seconds=seconds, steps=tuple(child(item) for item in steps))
    if kind == "unknown":
        return UnknownCheckNode(target=_compile_value(body, ctx))
    if kind == "unusable":
        if not isinstance(body, dict):
            raise ContractViolation("unusable requires an object")
        feature = _feature(ctx, body["feature"])
        return FeatureUnusableNode(feature.feature_id, _parameter(ctx, body["stale_after"]))
    raise ContractViolation(f"unknown predicate kind {kind!r}")


def _cmp(
    op: CompareOp, left: ValueExpr, right: ValueExpr, *, atom_id: str | None = None
) -> CompareNode:
    _check_compare_units(op, left, right)
    return CompareNode(op, left, right, atom_id=atom_id)


def _eq_binding(name: str, value: bool | str, unit: str, atom_id: str) -> CompareNode:
    return _cmp(CompareOp.EQ, _binding(name), _literal(value, unit), atom_id=atom_id)


def _compile_atom(
    atom_id: str,
    ctx: CompileContext,
    *,
    _depth: int,
    _count: list[int],
) -> PredicateNode:
    ident = str(Identifier(atom_id))
    builder = _ATOM_BUILDERS.get(ident)
    if builder is None:
        raise ContractViolation(f"undeclared predicate {ident!r}")
    node = builder(ctx)
    if getattr(node, "atom_id", None) is None:
        object.__setattr__(node, "atom_id", ident)
    return node


def _both_actors(ctx: CompileContext) -> PredicateNode:
    racing = _literal("racing", ScalarType.VEHICLE_PHASE.value)
    return AllNode(
        children=(
            _cmp(CompareOp.EQ, _feature(ctx, _PHASE_FEATURE_ID), racing),
            AnyNode(
                children=(
                    _cmp(CompareOp.EQ, _binding("target.phase"), racing),
                    AllNode(
                        children=(
                            UnknownCheckNode(_binding("target.phase")),
                            _cmp(
                                CompareOp.EQ,
                                _binding("target.surface_known"),
                                _literal(True, ScalarType.BOOLEAN.value),
                            ),
                        )
                    ),
                )
            ),
        ),
        atom_id="both_actors_racing_or_target_surface_known",
    )


def _feature_age(ctx: CompileContext) -> PredicateNode:
    return _cmp(
        CompareOp.LTE,
        FeatureAgeRef(_feature(ctx, _GAP_FEATURE_ID).feature_id),
        _parameter(ctx, "stale_after_s"),
        atom_id="feature_age_lte_stale_after_s",
    )


_ATOM_BUILDERS: dict[str, Callable[[CompileContext], PredicateNode]] = {
    "stream_confirmed_active": lambda ctx: _eq_binding(
        "stream.confirmed_active", True, "boolean", "stream_confirmed_active"
    ),
    "stage_race": lambda ctx: _eq_binding("session.stage", "race", "stage", "stage_race"),
    "both_actors_racing_or_target_surface_known": _both_actors,
    "race_flag_green": lambda ctx: _eq_binding("race.flag", "green", "text", "race_flag_green"),
    "ordered_relation_stable": lambda ctx: _cmp(
        CompareOp.EQ,
        _feature(ctx, _STABLE_FEATURE_ID),
        _literal(True, "boolean"),
        atom_id="ordered_relation_stable",
    ),
    "feature_age_lte_stale_after_s": _feature_age,
    "gap_lte_enter_gap_max_s": lambda ctx: _cmp(
        CompareOp.LTE,
        _feature(ctx, _GAP_FEATURE_ID),
        _parameter(ctx, "enter_gap_max_s"),
        atom_id="gap_lte_enter_gap_max_s",
    ),
    "net_closing_gte_min_closing_change_s": lambda ctx: _cmp(
        CompareOp.GTE,
        _feature(ctx, _NET_FEATURE_ID),
        _parameter(ctx, "min_closing_change_s"),
        atom_id="net_closing_gte_min_closing_change_s",
    ),
    "slope_lte_max_closing_slope": lambda ctx: _cmp(
        CompareOp.LTE,
        _feature(ctx, _SLOPE_FEATURE_ID),
        _parameter(ctx, "max_closing_slope"),
        atom_id="slope_lte_max_closing_slope",
    ),
    "coverage_gte_min_coverage": lambda ctx: _cmp(
        CompareOp.GTE,
        _feature(ctx, _COVERAGE_FEATURE_ID),
        _parameter(ctx, "min_coverage"),
        atom_id="coverage_gte_min_coverage",
    ),
    "confidence_gte_min_confidence": lambda ctx: _cmp(
        CompareOp.GTE,
        _feature(ctx, _CONFIDENCE_FEATURE_ID),
        _parameter(ctx, "min_confidence"),
        atom_id="confidence_gte_min_confidence",
    ),
    "actors_world_valid": lambda ctx: _eq_binding(
        "actors.world_valid", True, "boolean", "actors_world_valid"
    ),
    "gap_gte_exit_gap_min_s": lambda ctx: _cmp(
        CompareOp.GTE,
        _feature(ctx, _GAP_FEATURE_ID),
        _parameter(ctx, "exit_gap_min_s"),
        atom_id="gap_gte_exit_gap_min_s",
    ),
    "slope_gte_clear_slope": lambda ctx: _cmp(
        CompareOp.GTE,
        _feature(ctx, _SLOPE_FEATURE_ID),
        _parameter(ctx, "clear_slope"),
        atom_id="slope_gte_clear_slope",
    ),
    "coverage_lt_min_coverage": lambda ctx: _cmp(
        CompareOp.LT,
        _feature(ctx, _COVERAGE_FEATURE_ID),
        _parameter(ctx, "min_coverage"),
        atom_id="coverage_lt_min_coverage",
    ),
    "confidence_lt_min_confidence": lambda ctx: _cmp(
        CompareOp.LT,
        _feature(ctx, _CONFIDENCE_FEATURE_ID),
        _parameter(ctx, "min_confidence"),
        atom_id="confidence_lt_min_confidence",
    ),
    "feature_stale_or_unknown": lambda ctx: FeatureUnusableNode(
        _feature(ctx, _GAP_FEATURE_ID).feature_id,
        _parameter(ctx, "stale_after_s"),
        atom_id="feature_stale_or_unknown",
    ),
    "race_flag_not_green": lambda ctx: _cmp(
        CompareOp.NE,
        _binding("race.flag"),
        _literal("green", "text"),
        atom_id="race_flag_not_green",
    ),
    "occurrence_or_stream_change": lambda ctx: AnyNode(
        children=(
            ChangedNode(_binding("occurrence_id")),
            ChangedNode(_binding("stream_epoch")),
        ),
        atom_id="occurrence_or_stream_change",
    ),
    "ordered_target_or_relation_change": lambda ctx: AnyNode(
        children=(
            ChangedNode(_binding("target_id")),
            ChangedNode(_binding("relation_epoch")),
        ),
        atom_id="ordered_target_or_relation_change",
    ),
    "pit_tow_teleport_or_not_in_world": lambda ctx: _eq_binding(
        "actors.world_valid", False, "boolean", "pit_tow_teleport_or_not_in_world"
    ),
    "unsupported_stage": lambda ctx: _cmp(
        CompareOp.NE,
        _binding("session.stage"),
        _literal("race", "stage"),
        atom_id="unsupported_stage",
    ),
    "checkered_or_session_end": lambda ctx: AnyNode(
        children=(
            _cmp(CompareOp.EQ, _binding("race.flag"), _literal("checkered", "text")),
            _cmp(CompareOp.EQ, _binding("session.ended"), _literal(True, "boolean")),
        ),
        atom_id="checkered_or_session_end",
    ),
    "identity_conflict": lambda ctx: _eq_binding(
        "identity.conflict", True, "boolean", "identity_conflict"
    ),
    "hysteretic_band_changed": lambda ctx: ChangedNode(
        _binding("band"), atom_id="hysteretic_band_changed"
    ),
    "net_closing_delta_gte_material_change_s": lambda ctx: ChangedByNode(
        _feature(ctx, _NET_FEATURE_ID),
        _parameter(ctx, "material_change_s"),
        atom_id="net_closing_delta_gte_material_change_s",
    ),
    "front_relation_active": lambda ctx: _eq_binding(
        "front.relation_active", True, "boolean", "front_relation_active"
    ),
    "rear_relation_active": lambda ctx: _eq_binding(
        "rear.relation_active", True, "boolean", "rear_relation_active"
    ),
    "same_stream_occurrence_hero": lambda ctx: _eq_binding(
        "same_stream_occurrence_hero", True, "boolean", "same_stream_occurrence_hero"
    ),
    "distinct_targets": lambda ctx: _eq_binding(
        "distinct_targets", True, "boolean", "distinct_targets"
    ),
    "either_relation_inactive": lambda ctx: AnyNode(
        children=(
            _cmp(CompareOp.EQ, _binding("front.relation_active"), _literal(False, "boolean")),
            _cmp(CompareOp.EQ, _binding("rear.relation_active"), _literal(False, "boolean")),
        ),
        atom_id="either_relation_inactive",
    ),
    "target_or_relation_epoch_replaced": lambda ctx: AnyNode(
        children=(
            ChangedNode(_binding("front.relation_epoch")),
            ChangedNode(_binding("rear.relation_epoch")),
            ChangedNode(_binding("front.target_id")),
            ChangedNode(_binding("rear.target_id")),
        ),
        atom_id="target_or_relation_epoch_replaced",
    ),
}


def _invariant_sample_interval(ctx: CompileContext) -> PredicateNode:
    return AllNode(
        children=(
            _cmp(CompareOp.LT, _parameter(ctx, "sample_interval_s"), _parameter(ctx, "bucket_s")),
            _cmp(CompareOp.LTE, _parameter(ctx, "bucket_s"), _parameter(ctx, "trend_window_s")),
        )
    )


def _invariant_min_samples(ctx: CompileContext) -> PredicateNode:
    product = ProductRef(
        _parameter(ctx, "min_samples"),
        _parameter(ctx, "sample_interval_s"),
        product_unit(ScalarType.COUNT.value, ScalarType.SECONDS.value),
    )
    return _cmp(CompareOp.LTE, product, _parameter(ctx, "trend_window_s"))


_INVARIANT_BUILDERS: dict[str, Callable[[CompileContext], PredicateNode]] = {
    "sample_interval_s < bucket_s <= trend_window_s": _invariant_sample_interval,
    "min_samples * sample_interval_s <= trend_window_s": _invariant_min_samples,
    "confirm_s <= trend_window_s": lambda ctx: _cmp(
        CompareOp.LTE, _parameter(ctx, "confirm_s"), _parameter(ctx, "trend_window_s")
    ),
    "enter_gap_max_s < exit_gap_min_s": lambda ctx: _cmp(
        CompareOp.LT, _parameter(ctx, "enter_gap_max_s"), _parameter(ctx, "exit_gap_min_s")
    ),
    "overlap_enter_s < overlap_exit_s <= attack_enter_s < attack_exit_s": lambda ctx: AllNode(
        children=(
            _cmp(
                CompareOp.LT, _parameter(ctx, "overlap_enter_s"), _parameter(ctx, "overlap_exit_s")
            ),
            _cmp(
                CompareOp.LTE, _parameter(ctx, "overlap_exit_s"), _parameter(ctx, "attack_enter_s")
            ),
            _cmp(CompareOp.LT, _parameter(ctx, "attack_enter_s"), _parameter(ctx, "attack_exit_s")),
        )
    ),
    "attack_exit_s <= approach_enter_s < approach_exit_s <= enter_gap_max_s": lambda ctx: AllNode(
        children=(
            _cmp(
                CompareOp.LTE, _parameter(ctx, "attack_exit_s"), _parameter(ctx, "approach_enter_s")
            ),
            _cmp(
                CompareOp.LT,
                _parameter(ctx, "approach_enter_s"),
                _parameter(ctx, "approach_exit_s"),
            ),
            _cmp(
                CompareOp.LTE,
                _parameter(ctx, "approach_exit_s"),
                _parameter(ctx, "enter_gap_max_s"),
            ),
        )
    ),
    "update_min_interval_s >= clear_s": lambda ctx: _cmp(
        CompareOp.GTE, _parameter(ctx, "update_min_interval_s"), _parameter(ctx, "clear_s")
    ),
    "stale_after_s <= trend_window_s": lambda ctx: _cmp(
        CompareOp.LTE, _parameter(ctx, "stale_after_s"), _parameter(ctx, "trend_window_s")
    ),
}


def _context_from_definition(
    definition: Mapping[str, Any], registry: FeatureRegistry
) -> CompileContext:
    features = frozenset(str(Identifier(item)) for item in definition.get("features") or [])
    parameters = {
        str(Identifier(item["id"])): canonical_unit(str(item["unit"]))
        for item in definition.get("parameters") or []
    }
    return CompileContext(
        detector_id=str(Identifier(definition["id"])),
        features=features,
        parameters=parameters,
        registry=registry,
    )


def _compile_named_list(
    items: object, ctx: CompileContext, *, kind: type[AllNode] | type[AnyNode]
) -> PredicateNode:
    if not isinstance(items, list) or not items:
        raise ContractViolation(f"{ctx.detector_id} requires a nonempty predicate list")
    children = tuple(compile_predicate(item, ctx) for item in items)
    return kind(children=children)


def _param_number(expr: ValueExpr, parameters: Mapping[str, int | float]) -> float:
    if isinstance(expr, ParameterRef):
        if expr.parameter_id not in parameters:
            raise ContractViolation(f"missing parameter {expr.parameter_id!r}")
        return float(parameters[expr.parameter_id])
    if isinstance(expr, LiteralValue):
        if isinstance(expr.value, bool) or not isinstance(expr.value, (int, float)):
            raise ContractViolation("parameter invariant literal must be numeric")
        return float(expr.value)
    if isinstance(expr, ProductRef):
        return _param_number(expr.left, parameters) * _param_number(expr.right, parameters)
    raise ContractViolation("invariants may only compare parameters")


def _eval_param_node(node: PredicateNode, parameters: Mapping[str, int | float]) -> bool:
    if isinstance(node, AllNode):
        return all(_eval_param_node(child, parameters) for child in node.children)
    if isinstance(node, CompareNode) and not isinstance(node.right, tuple):
        left = _param_number(node.left, parameters)
        right = _param_number(node.right, parameters)
        if node.op is CompareOp.LT:
            return left < right
        if node.op is CompareOp.LTE:
            return left <= right
        if node.op is CompareOp.GT:
            return left > right
        if node.op is CompareOp.GTE:
            return left >= right
        if node.op is CompareOp.EQ:
            return left == right
        if node.op is CompareOp.NE:
            return left != right
    raise ContractViolation("invariants must be parameter comparisons")


def _defaults(definition: Mapping[str, Any]) -> dict[str, int | float]:
    values: dict[str, int | float] = {}
    for item in definition.get("parameters") or []:
        default = item["default"]
        if isinstance(default, bool) or not isinstance(default, (int, float)):
            raise ContractViolation(f"parameter {item['id']!r} default must be numeric")
        values[str(item["id"])] = default
    return values


def compile_detector_catalog(raw: object | None = None) -> CompiledDetectorCatalog:
    """Compile packaged or supplied detector-catalog JSON into typed ASTs."""

    if raw is None:
        validate_detector_feature_units()
        payload: object = json.loads(packaged_schema_bytes("detector-catalog.json"))
    else:
        payload = raw
    if not isinstance(payload, dict):
        raise ContractViolation("detector catalog must be a JSON object")
    registry = load_feature_registry()
    compiled: list[CompiledDetector] = []
    for definition in payload.get("definitions") or []:
        if not isinstance(definition, dict):
            raise ContractViolation("detector definition must be a JSON object")
        ctx = _context_from_definition(definition, registry)
        entry = definition.get("entry") or {}
        if entry.get("unknownSatisfies") is not False:
            raise ContractViolation(f"detector {ctx.detector_id!r} unknownSatisfies must be false")
        hold = str(entry.get("holdParameter") or "")
        if hold not in ctx.parameters:
            raise ContractViolation(f"detector {ctx.detector_id!r} missing hold parameter")
        enter_signal = _compile_named_list(entry.get("allPredicates"), ctx, kind=AllNode)
        enter = HeldForNode(seconds=_parameter(ctx, hold), condition=enter_signal)
        clear_spec = definition.get("clear") or {}
        clear_hold = str(clear_spec.get("holdParameter") or "")
        if clear_hold not in ctx.parameters:
            raise ContractViolation(f"detector {ctx.detector_id!r} missing clear hold parameter")
        clear = _compile_named_list(clear_spec.get("anyPredicates"), ctx, kind=AnyNode)
        immediate = _compile_named_list(clear_spec.get("immediateInvalidators"), ctx, kind=AnyNode)
        material = definition.get("materialUpdate")
        material_node: PredicateNode | None = None
        if material is not None:
            material_node = _compile_named_list(material.get("conditions"), ctx, kind=AnyNode)
        invariant_ids = tuple(str(item) for item in definition.get("crossFieldInvariants") or [])
        invariant_nodes = []
        for item in invariant_ids:
            builder = _INVARIANT_BUILDERS.get(item)
            if builder is None:
                raise ContractViolation(f"undeclared invariant {item!r}")
            invariant_nodes.append(builder(ctx))
        invariants: PredicateNode | None = (
            AllNode(tuple(invariant_nodes)) if invariant_nodes else None
        )
        if invariants is not None and not _eval_param_node(invariants, _defaults(definition)):
            raise ContractViolation(f"detector {ctx.detector_id!r} invariant is not satisfied")
        compiled.append(
            CompiledDetector(
                detector_id=ctx.detector_id,
                version=int(definition.get("version") or 1),
                enter=enter,
                enter_signal=enter_signal,
                clear=clear,
                immediate=immediate,
                material_update=material_node,
                invariants=invariants,
                invariant_ids=invariant_ids,
                context=ctx,
                hold_parameter=hold,
                clear_hold_parameter=clear_hold,
            )
        )
    if not compiled:
        raise ContractViolation("detector catalog must contain definitions")
    return CompiledDetectorCatalog(tuple(compiled))


@lru_cache(maxsize=1)
def load_compiled_detector_catalog() -> CompiledDetectorCatalog:
    return compile_detector_catalog()
