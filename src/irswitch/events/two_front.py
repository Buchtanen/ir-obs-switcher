"""Composite two-front detector for battle_two_front_v1.

Composes two parent directional relations. Does not invent battle.closing
facts or a V4 end event. Does not import NarrativeRuntime, overlay tape or
commentary. Not live-wired. DetectorBank stays directional-only.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from irswitch.contracts.feature import FeatureFrame
from irswitch.contracts.predicate import (
    BindingValue,
    PredicateEnv,
    load_compiled_detector_catalog,
)
from irswitch.contracts.primitives import Identifier
from irswitch.contracts.resources import packaged_schema_bytes
from irswitch.events.detector_bank import (
    DetectorInstanceKey,
    DetectorState,
    DetectorTransition,
    reduce_lifecycle,
)
from irswitch.events.predicate_ast import PredicateEvaluator, PredicateResult, Verdict

DETECTOR_ID = "battle_two_front_v1"
FEATURE_ID = "battle.two_front_active"
START_EVENT = "BATTLE_FOR_POSITION"
NARRATIVE_KIND = "battle.two_front"
TAPE_CHANNEL = "race.battle.two_front"
CONFIRM_S = 1.0
CLEAR_S = 1.0


def _catalog_defaults() -> dict[str, float]:
    raw = json.loads(packaged_schema_bytes("detector-catalog.json"))
    detector = next(item for item in raw["definitions"] if item["id"] == DETECTOR_ID)
    return {str(row["id"]): float(row["default"]) for row in detector.get("parameters") or []}


def reduce_composite(state: str, row: Mapping[str, object]) -> tuple[str, str | None]:
    """Frozen two-front reducer. Matches machine `compositeScenarios` goldens."""

    if row.get("replacement", False):
        return ("inactive", "ended") if state == "active" else ("inactive", None)
    if state == "active":
        loss = row.get("lossSeconds")
        if isinstance(loss, (int, float)) and not isinstance(loss, bool) and float(loss) >= CLEAR_S:
            return "inactive", "ended"
        return "active", None
    eligible = (
        bool(row.get("sameHero", False))
        and bool(row.get("distinctTargets", False))
        and bool(row.get("relationKnown", True))
    )
    held = row.get("heldSeconds", 0.0)
    held_s = float(held) if isinstance(held, (int, float)) and not isinstance(held, bool) else 0.0
    if eligible and held_s >= CONFIRM_S:
        return "active", "started"
    return "inactive", None


def _verdict_flag(result: PredicateResult) -> bool | None:
    if result.verdict is Verdict.TRUE:
        return True
    if result.verdict is Verdict.UNKNOWN:
        return None
    return False


def _binding_flag(bindings: Mapping[str, BindingValue], name: str) -> bool | None:
    item = bindings.get(name)
    if item is None or item.unknown or not isinstance(item.value, bool):
        return None
    return bool(item.value)


def _binding_text(bindings: Mapping[str, BindingValue], name: str) -> str | None:
    item = bindings.get(name)
    if item is None or item.unknown or not isinstance(item.value, (str, int)):
        return None
    return str(item.value)


def _reason(previous: str, nxt: str, emission: str | None, *, forced: str | None = None) -> str:
    if forced is not None:
        return forced
    if emission == "started":
        return "enter_confirmed"
    if emission == "ended":
        return "clear_confirmed" if previous == "clearing" else "immediate_invalidator"
    if previous == "inactive" and nxt == "candidate":
        return "enter_hold"
    if previous == "candidate" and nxt == "inactive":
        return "enter_broken"
    if previous == "active" and nxt == "clearing":
        return "clear_hold"
    if previous == "clearing" and nxt == "active":
        return "clear_cancelled"
    if nxt == "active":
        return "active_stable"
    if nxt == "candidate":
        return "enter_hold"
    if nxt == "clearing":
        return "clear_hold"
    return "inactive"


@dataclass(frozen=True, slots=True)
class TwoFrontTrace:
    fsm_state: str
    front_active: bool | None
    rear_active: bool | None
    distinct_targets: bool | None
    front_closing: bool
    rear_closing: bool
    front_epoch: str | None
    rear_epoch: str | None
    transition_reason: str
    effective_thresholds: dict[str, float]
    evidence_refs: tuple[str, ...]
    feature_active: bool


@dataclass(frozen=True, slots=True)
class TwoFrontCandidate:
    kind: str
    narrative_kind: str
    tape_channel: str
    detector_id: str
    observation_id: str
    correlation_key: tuple[str, ...]
    band: str = "composite"


@dataclass(frozen=True, slots=True)
class TwoFrontStep:
    accepted: bool
    diagnostic: str | None = None
    candidates: tuple[TwoFrontCandidate, ...] = ()
    transitions: tuple[DetectorTransition, ...] = ()
    expired_facts: tuple[str, ...] = ()
    published_facts: tuple[str, ...] = ()
    published_features: tuple[str, ...] = ()
    cleared_features: tuple[str, ...] = ()
    trace: TwoFrontTrace | None = None


@dataclass
class _Instance:
    key: DetectorInstanceKey
    state: DetectorState = "inactive"
    state_entered_mono_ms: int = 0
    evaluator: PredicateEvaluator = field(default_factory=PredicateEvaluator)
    feature_on: bool = False


class TwoFrontDetector:
    """battle_two_front_v1 product detector: two parent relations, one composite."""

    def __init__(self) -> None:
        self._compiled = load_compiled_detector_catalog().require(DETECTOR_ID)
        self._defaults = _catalog_defaults()
        self._instances: dict[DetectorInstanceKey, _Instance] = {}
        self._last_frame_sequence: int | None = None

    def observe(
        self,
        frame: FeatureFrame,
        *,
        bindings: Mapping[str, BindingValue] | None = None,
        parameters: Mapping[str, int | float] | None = None,
        front_closing: bool = False,
        rear_closing: bool = False,
    ) -> TwoFrontStep:
        if self._last_frame_sequence is not None:
            if int(frame.frame_sequence) < self._last_frame_sequence:
                return TwoFrontStep(False, "detector_frame_stale")
            if int(frame.frame_sequence) == self._last_frame_sequence:
                return TwoFrontStep(False, "detector_frame_duplicate")
        self._last_frame_sequence = int(frame.frame_sequence)

        params = {**self._defaults, **dict(parameters or {})}
        bound = dict(bindings or {})
        key = self._instance_key(frame, bound)
        transitions: list[DetectorTransition] = []
        candidates: list[TwoFrontCandidate] = []
        published_features: list[str] = []
        cleared_features: list[str] = []
        now = int(frame.observed_mono_ms)

        if key is not None:
            for stale in [item for item in self._instances.values() if item.key != key]:
                closed = self._force_close(stale, frame=frame, reason="relation_replaced")
                transitions.extend(closed[0])
                cleared_features.extend(closed[1])
                self._instances.pop(stale.key, None)

        current = None if key is None else self._instances.get(key)
        if current is None and key is not None:
            current = _Instance(key=key, state_entered_mono_ms=now)
            self._instances[key] = current

        enter_flag: bool | None = False
        clear_flag: bool | None = False
        immediate = False
        reason = "inactive"
        fsm_state = "inactive"
        if current is not None:
            env = PredicateEnv(
                now_mono_ms=now,
                parameters=params,
                bindings=bound,
                frame=frame,
            )
            enter_result = current.evaluator.evaluate(self._compiled.enter_signal, env)
            clear_result = current.evaluator.evaluate(self._compiled.clear, env)
            immediate_result = current.evaluator.evaluate(self._compiled.immediate, env)
            enter_flag = _verdict_flag(enter_result)
            if enter_flag is True and not (front_closing and rear_closing):
                enter_flag = False
            clear_flag = _verdict_flag(clear_result)
            immediate = immediate_result.satisfies
            elapsed = max(0.0, (now - current.state_entered_mono_ms) / 1000.0)
            previous = current.state
            nxt, emission = reduce_lifecycle(
                previous,
                enter=enter_flag,
                clear=clear_flag,
                immediate_invalidator=immediate,
                material_change=False,
                elapsed_in_state_s=elapsed,
                seconds_since_update=0.0,
                confirm_s=float(params.get("two_front_confirm_s", CONFIRM_S)),
                clear_s=float(params.get("two_front_clear_s", CLEAR_S)),
            )
            reason = _reason(previous, nxt, emission)
            if nxt != previous:
                current.state = nxt  # type: ignore[assignment]
                current.state_entered_mono_ms = now
            fsm_state = current.state
            observation_id = str(
                Identifier(f"obs:{DETECTOR_ID}:{int(frame.frame_sequence)}:{fsm_state}"[:128])
            )
            if emission == "started":
                current.feature_on = True
                published_features.append(FEATURE_ID)
                transitions.append(
                    DetectorTransition(
                        kind="STARTED",
                        reason=reason,
                        instance=current.key,
                        v4_event_kind=START_EVENT,
                        material_revision=1,
                    )
                )
                candidates.append(
                    TwoFrontCandidate(
                        kind=START_EVENT,
                        narrative_kind=NARRATIVE_KIND,
                        tape_channel=TAPE_CHANNEL,
                        detector_id=DETECTOR_ID,
                        observation_id=observation_id,
                        correlation_key=current.key.correlation_key,
                    )
                )
            elif emission == "ended":
                if current.feature_on:
                    cleared_features.append(FEATURE_ID)
                current.feature_on = False
                transitions.append(
                    DetectorTransition(
                        kind="ENDED",
                        reason=reason,
                        instance=current.key,
                        v4_event_kind=None,
                        material_revision=None,
                    )
                )
            if current.state == "inactive":
                self._instances.pop(current.key, None)

        if key is None:
            fsm_state = "inactive"
            reason = "identity_unavailable"

        return TwoFrontStep(
            True,
            candidates=tuple(candidates[:1]),
            transitions=tuple(transitions),
            expired_facts=(),
            published_facts=(),
            published_features=tuple(dict.fromkeys(published_features)),
            cleared_features=tuple(dict.fromkeys(cleared_features)),
            trace=TwoFrontTrace(
                fsm_state=fsm_state,
                front_active=_binding_flag(bound, "front.relation_active"),
                rear_active=_binding_flag(bound, "rear.relation_active"),
                distinct_targets=_binding_flag(bound, "distinct_targets"),
                front_closing=front_closing,
                rear_closing=rear_closing,
                front_epoch=_binding_text(bound, "front.relation_epoch"),
                rear_epoch=_binding_text(bound, "rear.relation_epoch"),
                transition_reason=reason,
                effective_thresholds={
                    "two_front_confirm_s": float(params.get("two_front_confirm_s", CONFIRM_S)),
                    "two_front_clear_s": float(params.get("two_front_clear_s", CLEAR_S)),
                },
                evidence_refs=(frame.source_snapshot_id,),
                feature_active=any(item.feature_on for item in self._instances.values()),
            ),
        )

    def _instance_key(
        self, frame: FeatureFrame, bindings: Mapping[str, BindingValue]
    ) -> DetectorInstanceKey | None:
        front = _binding_text(bindings, "front.relation_epoch")
        rear = _binding_text(bindings, "rear.relation_epoch")
        if front is None or rear is None:
            return None
        occurrence = "" if frame.occurrence_id is None else str(frame.occurrence_id)
        return DetectorInstanceKey(
            detector_id=DETECTOR_ID,
            detector_version=int(self._compiled.version),
            stream_epoch=int(frame.stream_epoch),
            occurrence_id=occurrence,
            correlation_key=(str(frame.stream_epoch), occurrence, front, rear),
        )

    def _force_close(
        self, item: _Instance, *, frame: FeatureFrame, reason: str
    ) -> tuple[tuple[DetectorTransition, ...], tuple[str, ...]]:
        previous = item.state
        nxt, emission = reduce_lifecycle(
            previous,
            enter=None,
            clear=None,
            immediate_invalidator=True,
            material_change=False,
            elapsed_in_state_s=0.0,
            seconds_since_update=0.0,
        )
        item.state = nxt  # type: ignore[assignment]
        cleared: list[str] = []
        transitions: list[DetectorTransition] = []
        if emission == "ended":
            if item.feature_on:
                cleared.append(FEATURE_ID)
            item.feature_on = False
            transitions.append(
                DetectorTransition(
                    kind="ENDED",
                    reason=reason,
                    instance=item.key,
                    v4_event_kind=None,
                    material_revision=None,
                )
            )
        return tuple(transitions), tuple(cleared)
