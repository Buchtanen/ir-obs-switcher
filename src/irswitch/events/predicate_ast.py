"""Evaluate compiled predicate ASTs with conservative unknown and temporal memory.

Does not import NarrativeRuntime, DetectorBank, overlay tape or commentary.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from irswitch.contracts.feature import FeatureFrame, FeatureValue
from irswitch.contracts.predicate import (
    MAX_EVAL_STEPS,
    AllNode,
    AnyNode,
    BindingRef,
    ChangedByNode,
    ChangedNode,
    CompareNode,
    CompareOp,
    CountNode,
    CrossedNode,
    FallingEdgeNode,
    FeatureAgeRef,
    FeatureRef,
    FeatureUnusableNode,
    HeldForNode,
    LiteralValue,
    NotNode,
    ParameterRef,
    PredicateEnv,
    PredicateNode,
    PredicateResult,
    ProductRef,
    ReasonNode,
    RisingEdgeNode,
    SequenceNode,
    SinceNode,
    UnknownCheckNode,
    ValueExpr,
    Verdict,
    WithinNode,
    canonical_unit,
    units_compatible,
)
from irswitch.contracts.primitives import ContractViolation, FactQuality


@dataclass
class _Resolved:
    value: bool | int | float | str | None
    unit: str
    unknown: bool
    detail: str


@dataclass
class _Memory:
    values: dict[str, tuple[object, bool]] = field(default_factory=dict)
    verdicts: dict[str, Verdict] = field(default_factory=dict)
    hold_start: dict[str, int | None] = field(default_factory=dict)
    events: dict[str, list[int]] = field(default_factory=dict)
    since_latched: dict[str, bool] = field(default_factory=dict)
    sequence_times: dict[str, list[int]] = field(default_factory=dict)


def _result(node: str, verdict: Verdict, detail: str, *children: ReasonNode) -> PredicateResult:
    return PredicateResult(verdict, ReasonNode(node, verdict, detail, children))


def _value_key(expr: ValueExpr) -> str:
    if isinstance(expr, FeatureRef):
        return f"feature:{expr.feature_id}"
    if isinstance(expr, ParameterRef):
        return f"param:{expr.parameter_id}"
    if isinstance(expr, BindingRef):
        return f"binding:{expr.name}"
    if isinstance(expr, FeatureAgeRef):
        return f"age:{expr.feature_id}"
    if isinstance(expr, LiteralValue):
        return f"lit:{expr.unit}:{expr.value!r}"
    if isinstance(expr, ProductRef):
        return f"prod:{_value_key(expr.left)}*{_value_key(expr.right)}"
    raise ContractViolation("unknown value expression")


def _lookup_feature(frame: FeatureFrame | None, feature_id: str) -> FeatureValue | None:
    if frame is None:
        return None
    for item in frame.values:
        if item.feature_id == feature_id:
            return item
    return None


def _feature_unusable(item: FeatureValue | None, now_mono_ms: int, stale_after_s: float) -> bool:
    if item is None:
        return True
    if item.quality is FactQuality.UNKNOWN:
        return True
    if item.valid_until_mono_ms is not None and now_mono_ms > item.valid_until_mono_ms:
        return True
    age_s = max(0, now_mono_ms - item.observed_mono_ms) / 1000.0
    return age_s > stale_after_s


def _as_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


class PredicateEvaluator:
    """Replay-deterministic evaluator. Unknown never satisfies enter or held_for."""

    def __init__(self) -> None:
        self._memory = _Memory()
        self._steps = 0

    def reset(self) -> None:
        self._memory = _Memory()
        self._steps = 0

    def evaluate(self, node: PredicateNode, env: PredicateEnv) -> PredicateResult:
        self._steps = 0
        return self._eval_node(node, env, "")

    def _eval_node(self, node: PredicateNode, env: PredicateEnv, path: str) -> PredicateResult:
        self._steps += 1
        if self._steps > MAX_EVAL_STEPS:
            raise ContractViolation("predicate evaluation exceeds cost bound")
        if isinstance(node, AllNode):
            return self._eval_all(node, env, path)
        if isinstance(node, AnyNode):
            return self._eval_any(node, env, path)
        if isinstance(node, NotNode):
            child = self._eval_node(node.child, env, f"{path}/n")
            if child.verdict is Verdict.TRUE:
                verdict = Verdict.FALSE
            elif child.verdict is Verdict.FALSE:
                verdict = Verdict.TRUE
            else:
                verdict = Verdict.UNKNOWN
            return _result(node.atom_id or "not", verdict, verdict.value, child.reason)
        if isinstance(node, CompareNode):
            return self._eval_compare(node, env)
        if isinstance(node, UnknownCheckNode):
            resolved = self._resolve(node.target, env)
            verdict = Verdict.TRUE if resolved.unknown else Verdict.FALSE
            return _result(node.atom_id or "unknown", verdict, resolved.detail)
        if isinstance(node, FeatureUnusableNode):
            return self._eval_unusable(node, env)
        if isinstance(node, ChangedNode):
            return self._eval_changed(node, env, path)
        if isinstance(node, ChangedByNode):
            return self._eval_changed_by(node, env, path)
        if isinstance(node, CrossedNode):
            return self._eval_crossed(node, env, path)
        if isinstance(node, RisingEdgeNode):
            child, rising = self._edge(node.child, env, f"{path}/e")
            verdict = Verdict.TRUE if rising else Verdict.FALSE
            if child.verdict is Verdict.UNKNOWN:
                verdict = Verdict.UNKNOWN
            return _result(node.atom_id or "rising_edge", verdict, verdict.value, child.reason)
        if isinstance(node, FallingEdgeNode):
            previous = self._memory.verdicts.get(f"{path}/e")
            child = self._eval_node(node.child, env, f"{path}/e")
            self._memory.verdicts[f"{path}/e"] = child.verdict
            falling = previous is Verdict.TRUE and child.verdict is Verdict.FALSE
            verdict = Verdict.TRUE if falling else Verdict.FALSE
            if child.verdict is Verdict.UNKNOWN or previous is Verdict.UNKNOWN:
                verdict = Verdict.UNKNOWN
            return _result(node.atom_id or "falling_edge", verdict, verdict.value, child.reason)
        if isinstance(node, HeldForNode):
            return self._eval_held_for(node, env, path)
        if isinstance(node, WithinNode):
            return self._eval_within(node, env, path)
        if isinstance(node, SinceNode):
            return self._eval_since(node, env, path)
        if isinstance(node, CountNode):
            return self._eval_count(node, env, path)
        if isinstance(node, SequenceNode):
            return self._eval_sequence(node, env, path)
        raise ContractViolation(f"unsupported predicate node {type(node).__name__}")

    def _eval_all(self, node: AllNode, env: PredicateEnv, path: str) -> PredicateResult:
        children = [
            self._eval_node(child, env, f"{path}/a{index}")
            for index, child in enumerate(node.children)
        ]
        if any(item.verdict is Verdict.FALSE for item in children):
            verdict = Verdict.FALSE
        elif any(item.verdict is Verdict.UNKNOWN for item in children):
            verdict = Verdict.UNKNOWN
        else:
            verdict = Verdict.TRUE
        return _result(
            node.atom_id or "all", verdict, verdict.value, *(item.reason for item in children)
        )

    def _eval_any(self, node: AnyNode, env: PredicateEnv, path: str) -> PredicateResult:
        children = [
            self._eval_node(child, env, f"{path}/o{index}")
            for index, child in enumerate(node.children)
        ]
        if any(item.verdict is Verdict.TRUE for item in children):
            verdict = Verdict.TRUE
        elif any(item.verdict is Verdict.UNKNOWN for item in children):
            verdict = Verdict.UNKNOWN
        else:
            verdict = Verdict.FALSE
        return _result(
            node.atom_id or "any", verdict, verdict.value, *(item.reason for item in children)
        )

    def _eval_unusable(self, node: FeatureUnusableNode, env: PredicateEnv) -> PredicateResult:
        stale = self._resolve(node.stale_after, env)
        if stale.unknown:
            return _result(node.atom_id or "unusable", Verdict.UNKNOWN, "stale_after unknown")
        limit = _as_number(stale.value)
        if limit is None:
            raise ContractViolation("stale_after must be numeric")
        item = _lookup_feature(env.frame, node.feature_id)
        verdict = Verdict.TRUE if _feature_unusable(item, env.now_mono_ms, limit) else Verdict.FALSE
        return _result(node.atom_id or "unusable", verdict, f"{node.feature_id}:{verdict.value}")

    def _eval_compare(self, node: CompareNode, env: PredicateEnv) -> PredicateResult:
        left = self._resolve(node.left, env)
        if isinstance(node.right, tuple):
            rights = tuple(self._resolve(item, env) for item in node.right)
            if left.unknown or any(item.unknown for item in rights):
                return _result(node.atom_id or node.op.value, Verdict.UNKNOWN, left.detail)
            verdict = _compare_many(node.op, left, rights)
            return _result(node.atom_id or node.op.value, verdict, f"{left.detail} {node.op.value}")
        right = self._resolve(node.right, env)
        if left.unknown or right.unknown:
            return _result(node.atom_id or node.op.value, Verdict.UNKNOWN, left.detail)
        if not units_compatible(left.unit, right.unit):
            raise ContractViolation(f"incompatible units {left.unit} {node.op.value} {right.unit}")
        verdict = _compare_pair(node.op, left.value, right.value)
        return _result(
            node.atom_id or node.op.value,
            verdict,
            f"{left.detail} {node.op.value} {right.detail}",
        )

    def _eval_changed(self, node: ChangedNode, env: PredicateEnv, path: str) -> PredicateResult:
        current = self._resolve(node.target, env)
        key = f"{path}:{_value_key(node.target)}"
        previous = self._memory.values.get(key)
        self._memory.values[key] = (current.value, current.unknown)
        if current.unknown or (previous is not None and previous[1]):
            return _result(node.atom_id or "changed", Verdict.UNKNOWN, current.detail)
        if previous is None:
            return _result(node.atom_id or "changed", Verdict.FALSE, "first")
        verdict = Verdict.TRUE if previous[0] != current.value else Verdict.FALSE
        return _result(node.atom_id or "changed", verdict, current.detail)

    def _eval_changed_by(
        self, node: ChangedByNode, env: PredicateEnv, path: str
    ) -> PredicateResult:
        current = self._resolve(node.target, env)
        amount = self._resolve(node.amount, env)
        key = f"{path}:{_value_key(node.target)}"
        previous = self._memory.values.get(key)
        self._memory.values[key] = (current.value, current.unknown)
        if current.unknown or amount.unknown or (previous is not None and previous[1]):
            return _result(node.atom_id or "changed_by", Verdict.UNKNOWN, current.detail)
        if previous is None:
            return _result(node.atom_id or "changed_by", Verdict.FALSE, "first")
        left = _as_number(previous[0])
        right = _as_number(current.value)
        need = _as_number(amount.value)
        if left is None or right is None or need is None:
            return _result(node.atom_id or "changed_by", Verdict.UNKNOWN, "non-numeric")
        verdict = Verdict.TRUE if abs(right - left) >= need else Verdict.FALSE
        return _result(node.atom_id or "changed_by", verdict, current.detail)

    def _eval_crossed(self, node: CrossedNode, env: PredicateEnv, path: str) -> PredicateResult:
        current = self._resolve(node.target, env)
        threshold = self._resolve(node.threshold, env)
        key = f"{path}:{_value_key(node.target)}"
        previous = self._memory.values.get(key)
        self._memory.values[key] = (current.value, current.unknown)
        if current.unknown or threshold.unknown or (previous is not None and previous[1]):
            return _result(node.atom_id or "crossed", Verdict.UNKNOWN, current.detail)
        if previous is None:
            return _result(node.atom_id or "crossed", Verdict.FALSE, "first")
        prev = _as_number(previous[0])
        curr = _as_number(current.value)
        limit = _as_number(threshold.value)
        if prev is None or curr is None or limit is None:
            return _result(node.atom_id or "crossed", Verdict.UNKNOWN, "non-numeric")
        falling = prev > limit and curr <= limit
        rising = prev < limit and curr >= limit
        if node.direction == "falling":
            hit = falling
        elif node.direction == "rising":
            hit = rising
        else:
            hit = falling or rising
        verdict = Verdict.TRUE if hit else Verdict.FALSE
        return _result(node.atom_id or "crossed", verdict, current.detail)

    def _eval_held_for(self, node: HeldForNode, env: PredicateEnv, path: str) -> PredicateResult:
        inner = self._eval_node(node.condition, env, f"{path}/c")
        seconds = self._resolve(node.seconds, env)
        if seconds.unknown:
            self._memory.hold_start[path] = None
            return _result("held_for", Verdict.FALSE, "seconds unknown", inner.reason)
        need = _as_number(seconds.value)
        if need is None:
            raise ContractViolation("held_for seconds must be numeric")
        if inner.verdict is not Verdict.TRUE:
            self._memory.hold_start[path] = None
            return _result("held_for", Verdict.FALSE, "unknown_does_not_hold", inner.reason)
        start = self._memory.hold_start.get(path)
        if start is None:
            start = env.now_mono_ms
            self._memory.hold_start[path] = start
        elapsed = (env.now_mono_ms - start) / 1000.0
        verdict = Verdict.TRUE if elapsed >= need else Verdict.FALSE
        return _result("held_for", verdict, f"{elapsed:.3f}/{need}", inner.reason)

    def _eval_within(self, node: WithinNode, env: PredicateEnv, path: str) -> PredicateResult:
        inner = self._eval_node(node.condition, env, f"{path}/c")
        seconds = self._resolve(node.seconds, env)
        if seconds.unknown:
            return _result("within", Verdict.UNKNOWN, "seconds unknown", inner.reason)
        window = _as_number(seconds.value)
        if window is None:
            raise ContractViolation("within seconds must be numeric")
        events = self._memory.events.setdefault(path, [])
        if inner.verdict is Verdict.TRUE:
            events.append(env.now_mono_ms)
        cutoff = env.now_mono_ms - int(window * 1000)
        events[:] = [stamp for stamp in events if stamp >= cutoff]
        verdict = Verdict.TRUE if events else Verdict.FALSE
        return _result("within", verdict, f"count={len(events)}", inner.reason)

    def _eval_since(self, node: SinceNode, env: PredicateEnv, path: str) -> PredicateResult:
        inner = self._eval_node(node.condition, env, f"{path}/c")
        if inner.verdict is Verdict.TRUE:
            self._memory.since_latched[path] = True
        verdict = Verdict.TRUE if self._memory.since_latched.get(path) else Verdict.FALSE
        return _result("since", verdict, verdict.value, inner.reason)

    def _eval_count(self, node: CountNode, env: PredicateEnv, path: str) -> PredicateResult:
        inner, rising = self._edge(node.condition, env, f"{path}/c")
        seconds = self._resolve(node.seconds, env)
        minimum = self._resolve(node.minimum, env)
        if seconds.unknown or minimum.unknown:
            return _result("count", Verdict.UNKNOWN, "window unknown", inner.reason)
        window = _as_number(seconds.value)
        need = _as_number(minimum.value)
        if window is None or need is None:
            raise ContractViolation("count window and minimum must be numeric")
        events = self._memory.events.setdefault(path, [])
        if rising:
            events.append(env.now_mono_ms)
        cutoff = env.now_mono_ms - int(window * 1000)
        events[:] = [stamp for stamp in events if stamp >= cutoff]
        verdict = Verdict.TRUE if len(events) >= need else Verdict.FALSE
        return _result("count", verdict, f"count={len(events)}", inner.reason)

    def _eval_sequence(self, node: SequenceNode, env: PredicateEnv, path: str) -> PredicateResult:
        seconds = self._resolve(node.seconds, env)
        if seconds.unknown:
            return _result("sequence", Verdict.UNKNOWN, "seconds unknown")
        window = _as_number(seconds.value)
        if window is None:
            raise ContractViolation("sequence seconds must be numeric")
        times = self._memory.sequence_times.setdefault(path, [])
        reasons: list[ReasonNode] = []
        for index, step in enumerate(node.steps):
            child, rising = self._edge(step, env, f"{path}/s{index}")
            reasons.append(child.reason)
            if len(times) == index and rising:
                times.append(env.now_mono_ms)
        if times and env.now_mono_ms - times[0] > int(window * 1000):
            times.clear()
        verdict = Verdict.TRUE if len(times) >= len(node.steps) else Verdict.FALSE
        return _result("sequence", verdict, f"steps={len(times)}", *reasons)

    def _edge(
        self, node: PredicateNode, env: PredicateEnv, path: str
    ) -> tuple[PredicateResult, bool]:
        result = self._eval_node(node, env, path)
        previous = self._memory.verdicts.get(path)
        self._memory.verdicts[path] = result.verdict
        rising = previous is not Verdict.TRUE and result.verdict is Verdict.TRUE
        return result, rising

    def _resolve(self, expr: ValueExpr, env: PredicateEnv) -> _Resolved:
        if isinstance(expr, LiteralValue):
            return _Resolved(expr.value, expr.unit, False, repr(expr.value))
        if isinstance(expr, ParameterRef):
            if expr.parameter_id not in env.parameters:
                raise ContractViolation(f"missing parameter {expr.parameter_id!r}")
            value = env.parameters[expr.parameter_id]
            return _Resolved(value, expr.unit, False, f"{expr.parameter_id}={value}")
        if isinstance(expr, BindingRef):
            binding = env.bindings.get(expr.name)
            if binding is None or binding.unknown:
                return _Resolved(None, expr.unit, True, f"{expr.name}:unknown")
            if canonical_unit(binding.unit) != canonical_unit(expr.unit):
                raise ContractViolation(f"binding {expr.name} unit {binding.unit} != {expr.unit}")
            return _Resolved(binding.value, expr.unit, False, f"{expr.name}={binding.value!r}")
        if isinstance(expr, FeatureRef):
            item = _lookup_feature(env.frame, expr.feature_id)
            if item is None:
                return _Resolved(None, expr.unit, True, f"{expr.feature_id}:unknown")
            if item.quality is FactQuality.UNKNOWN:
                return _Resolved(None, expr.unit, True, f"{expr.feature_id}:unknown")
            if item.valid_until_mono_ms is not None and env.now_mono_ms > item.valid_until_mono_ms:
                return _Resolved(None, expr.unit, True, f"{expr.feature_id}:expired")
            return _Resolved(item.value, expr.unit, False, f"{expr.feature_id}={item.value!r}")
        if isinstance(expr, FeatureAgeRef):
            item = _lookup_feature(env.frame, expr.feature_id)
            if item is None:
                return _Resolved(None, expr.unit, True, f"{expr.feature_id}:unknown")
            age = max(0, env.now_mono_ms - item.observed_mono_ms) / 1000.0
            return _Resolved(age, expr.unit, False, f"age={age:.3f}")
        if isinstance(expr, ProductRef):
            left = self._resolve(expr.left, env)
            right = self._resolve(expr.right, env)
            if left.unknown or right.unknown:
                return _Resolved(None, expr.unit, True, "product:unknown")
            first = _as_number(left.value)
            second = _as_number(right.value)
            if first is None or second is None:
                return _Resolved(None, expr.unit, True, "product:non-numeric")
            return _Resolved(first * second, expr.unit, False, f"{first}*{second}")
        raise ContractViolation("unknown value expression")


def _compare_pair(op: CompareOp, left: object, right: object) -> Verdict:
    if op is CompareOp.IN:
        return Verdict.TRUE if left == right else Verdict.FALSE
    if op is CompareOp.NOT_IN:
        return Verdict.TRUE if left != right else Verdict.FALSE
    if op in {CompareOp.EQ, CompareOp.NE}:
        matched = left == right
        return Verdict.TRUE if (matched if op is CompareOp.EQ else not matched) else Verdict.FALSE
    first = _as_number(left)
    second = _as_number(right)
    if first is None or second is None:
        return Verdict.UNKNOWN
    if op is CompareOp.LT:
        hit = first < second
    elif op is CompareOp.LTE:
        hit = first <= second
    elif op is CompareOp.GT:
        hit = first > second
    elif op is CompareOp.GTE:
        hit = first >= second
    else:
        return Verdict.UNKNOWN
    return Verdict.TRUE if hit else Verdict.FALSE


def _compare_many(op: CompareOp, left: _Resolved, rights: tuple[_Resolved, ...]) -> Verdict:
    values = [item.value for item in rights]
    if op is CompareOp.IN:
        return Verdict.TRUE if left.value in values else Verdict.FALSE
    if op is CompareOp.NOT_IN:
        return Verdict.TRUE if left.value not in values else Verdict.FALSE
    if op is CompareOp.BETWEEN and len(rights) == 2:
        low = _compare_pair(CompareOp.GTE, left.value, rights[0].value)
        high = _compare_pair(CompareOp.LTE, left.value, rights[1].value)
        if low is Verdict.UNKNOWN or high is Verdict.UNKNOWN:
            return Verdict.UNKNOWN
        return Verdict.TRUE if low is Verdict.TRUE and high is Verdict.TRUE else Verdict.FALSE
    return Verdict.UNKNOWN
