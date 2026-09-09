"""Generic correlated detector lifecycle FSM.

Consumes FeatureFrames and compiled catalog trees. Does not import
NarrativeRuntime, overlay tape or commentary. Not live-wired.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Literal

from irswitch.contracts.feature import FeatureFrame
from irswitch.contracts.predicate import (
    BindingValue,
    CompiledDetector,
    CompiledDetectorCatalog,
    PredicateEnv,
    PredicateResult,
    Verdict,
    load_compiled_detector_catalog,
)
from irswitch.contracts.primitives import Identifier
from irswitch.contracts.resources import packaged_schema_bytes
from irswitch.events.predicate_ast import PredicateEvaluator

DetectorState = Literal["inactive", "candidate", "active", "clearing"]
Emission = Literal["started", "updated", "ended"]
TransitionKind = Literal["STARTED", "UPDATED", "ENDED"]

_DIRECTIONAL_START_EVENTS = {
    "battle_ahead_v1": "HUNTING",
    "battle_behind_v1": "HUNTED",
}
_DIRECTIONAL_CHANNELS = {
    "battle_ahead_v1": "race.battle.closing",
    "battle_behind_v1": "race.battle.pressure",
}
_CLOSING_FACT = "battle.closing"
_TRANSITION = {"started": "STARTED", "updated": "UPDATED", "ended": "ENDED"}


def reduce_lifecycle(
    state: str,
    *,
    enter: bool | None,
    clear: bool | None,
    immediate_invalidator: bool,
    material_change: bool,
    elapsed_in_state_s: float,
    seconds_since_update: float,
    confirm_s: float = 3.0,
    clear_s: float = 2.0,
    update_min_interval_s: float = 6.0,
) -> tuple[str, str | None]:
    """Frozen directional reducer. Matches machine `reduce_directional` goldens."""

    if immediate_invalidator:
        return "inactive", "ended" if state in {"active", "clearing"} else None
    if state == "inactive":
        return ("candidate", None) if enter is True else ("inactive", None)
    if state == "candidate":
        if enter is not True:
            return "inactive", None
        return ("active", "started") if elapsed_in_state_s >= confirm_s else ("candidate", None)
    if state == "active":
        if clear is True or clear is None:
            return "clearing", None
        if material_change and seconds_since_update >= update_min_interval_s:
            return "active", "updated"
        return "active", None
    if enter is True:
        return "active", None
    if (clear is True or clear is None) and elapsed_in_state_s >= clear_s:
        return "inactive", "ended"
    return "clearing", None


def _verdict_flag(result: PredicateResult) -> bool | None:
    if result.verdict is Verdict.TRUE:
        return True
    if result.verdict is Verdict.UNKNOWN:
        return None
    return False


def _feature_number(frame: FeatureFrame, feature_id: str) -> float | None:
    for item in frame.values:
        if item.feature_id == feature_id:
            if isinstance(item.value, bool) or not isinstance(item.value, (int, float)):
                return None
            return float(item.value)
    return None


def _band_value(bindings: Mapping[str, BindingValue]) -> str | None:
    band = bindings.get("band")
    if band is None or band.unknown or not isinstance(band.value, str):
        return None
    return band.value


def _material_since_emit(
    item: _Instance,
    frame: FeatureFrame,
    bindings: Mapping[str, BindingValue],
    parameters: Mapping[str, int | float],
) -> bool:
    if item.last_update_mono_ms is None:
        return False
    net = _feature_number(frame, "gap.trend.net_closing")
    band = _band_value(bindings)
    band_changed = (
        item.last_emit_band is not None and band is not None and band != item.last_emit_band
    )
    need = float(parameters.get("material_change_s", 0.40))
    net_changed = (
        item.last_emit_net_closing is not None
        and net is not None
        and abs(net - item.last_emit_net_closing) >= need
    )
    return band_changed or net_changed


def _remember_emit(
    item: _Instance, frame: FeatureFrame, bindings: Mapping[str, BindingValue]
) -> None:
    item.last_emit_net_closing = _feature_number(frame, "gap.trend.net_closing")
    item.last_emit_band = _band_value(bindings)


def _catalog_hash() -> str:
    return "sha256:" + sha256(packaged_schema_bytes("detector-catalog.json")).hexdigest()


def _occurrence_text(frame: FeatureFrame) -> str:
    return "" if frame.occurrence_id is None else str(frame.occurrence_id)


def _instance_key(detector: CompiledDetector, frame: FeatureFrame) -> DetectorInstanceKey:
    return DetectorInstanceKey(
        detector_id=detector.detector_id,
        detector_version=detector.version,
        stream_epoch=int(frame.stream_epoch),
        occurrence_id=_occurrence_text(frame),
        correlation_key=tuple(frame.correlation_key),
    )


@dataclass(frozen=True, slots=True)
class DetectorInstanceKey:
    detector_id: str
    detector_version: int
    stream_epoch: int
    occurrence_id: str
    correlation_key: tuple[str, ...]

    @property
    def ordered_correlation_key(self) -> str:
        return "|".join(self.correlation_key)


@dataclass(frozen=True, slots=True)
class DetectorTransition:
    kind: TransitionKind
    reason: str
    instance: DetectorInstanceKey
    v4_event_kind: str | None
    material_revision: int | None
    expire_facts: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class DetectorCandidate:
    kind: str
    detector_id: str
    observation_id: str
    material_revision: int
    tape_channel: str


@dataclass(frozen=True, slots=True)
class DetectorObservation:
    observation_id: str
    detector_id: str
    detector_version: str
    detector_config_hash: str
    parameter_snapshot_id: str
    observed_mono_ms: int
    broadcast_epoch: int
    stream_epoch: int
    occurrence_id: str | None
    correlation_key: tuple[str, ...]
    previous_state: DetectorState
    candidate_state: DetectorState
    transition_reason: str
    would_emit_event_kind: str | None
    tape_channel: str
    predicate_results: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class DetectorInstanceView:
    key: DetectorInstanceKey
    state: DetectorState


@dataclass(frozen=True, slots=True)
class DetectorBankStep:
    accepted: bool
    diagnostic: str | None = None
    observations: tuple[DetectorObservation, ...] = ()
    transitions: tuple[DetectorTransition, ...] = ()
    candidates: tuple[DetectorCandidate, ...] = ()
    expired_facts: tuple[str, ...] = ()


@dataclass
class _Instance:
    key: DetectorInstanceKey
    compiled: CompiledDetector
    start_event: str
    tape_channel: str
    state: DetectorState = "inactive"
    state_entered_mono_ms: int = 0
    last_update_mono_ms: int | None = None
    last_emit_net_closing: float | None = None
    last_emit_band: str | None = None
    material_revision: int = 0
    evaluator: PredicateEvaluator = field(default_factory=PredicateEvaluator)


def _reason(previous: str, nxt: str, emission: str | None, *, forced: str | None = None) -> str:
    if forced is not None:
        return forced
    if emission == "started":
        return "enter_confirmed"
    if emission == "updated":
        return "material_updated"
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


def _observation_id(key: DetectorInstanceKey, frame_sequence: int, suffix: str) -> str:
    raw = f"obs:{key.detector_id}:{frame_sequence}:{suffix}"
    return str(Identifier(raw[:128]))


class DetectorBank:
    """Process-local directional detector FSM. Replay-deterministic for the same frames."""

    def __init__(
        self,
        catalog: CompiledDetectorCatalog | None = None,
        *,
        parameter_snapshot_id: str = "param:default",
        detector_config_hash: str | None = None,
    ) -> None:
        self._catalog = catalog or load_compiled_detector_catalog()
        raw = json.loads(packaged_schema_bytes("detector-catalog.json"))
        kinds = {
            str(item["id"]): str(item.get("kind") or "")
            for item in raw.get("definitions") or []
            if isinstance(item, dict)
        }
        self._directional = tuple(
            item for item in self._catalog.detectors if kinds.get(item.detector_id) == "directional"
        )
        self._instances: dict[DetectorInstanceKey, _Instance] = {}
        self._disabled: set[str] = set()
        self._last_frame_sequence: int | None = None
        self._parameter_snapshot_id = str(Identifier(parameter_snapshot_id))
        self._detector_config_hash = detector_config_hash or _catalog_hash()

    def instance(self, key: DetectorInstanceKey) -> DetectorInstanceView | None:
        current = self._instances.get(key)
        if current is None:
            return None
        return DetectorInstanceView(current.key, current.state)

    def disable_for_run(
        self, detector_ids: tuple[str, ...], reason: str = "required_capture_lost"
    ) -> DetectorBankStep:
        observations: list[DetectorObservation] = []
        transitions: list[DetectorTransition] = []
        expired: list[str] = []
        for detector_id in detector_ids:
            self._disabled.add(detector_id)
            live = [
                item for item in self._instances.values() if item.key.detector_id == detector_id
            ]
            for item in live:
                closed = self._force_close(item, reason=reason, frame_sequence=0, now_mono_ms=0)
                observations.extend(closed[0])
                transitions.extend(closed[1])
                expired.extend(closed[2])
                self._instances.pop(item.key, None)
        return DetectorBankStep(
            accepted=True,
            observations=tuple(observations),
            transitions=tuple(transitions),
            expired_facts=tuple(dict.fromkeys(expired)),
        )

    def step(
        self,
        frame: FeatureFrame,
        *,
        bindings: Mapping[str, BindingValue],
        parameters: Mapping[str, int | float] | None = None,
        detector_ids: tuple[str, ...] | None = ("battle_ahead_v1",),
        coverage: tuple[object, ...] = (),
    ) -> DetectorBankStep:
        del coverage
        if self._last_frame_sequence is not None:
            if int(frame.frame_sequence) < self._last_frame_sequence:
                return DetectorBankStep(False, "detector_frame_stale")
            if int(frame.frame_sequence) == self._last_frame_sequence:
                return DetectorBankStep(False, "detector_frame_duplicate")
        self._last_frame_sequence = int(frame.frame_sequence)

        selected = self._selected(detector_ids)
        observations: list[DetectorObservation] = []
        transitions: list[DetectorTransition] = []
        candidates: list[DetectorCandidate] = []
        expired: list[str] = []
        params = dict(parameters or {})

        for compiled in selected:
            if compiled.detector_id in self._disabled:
                continue
            if not params:
                params = self._defaults(compiled)
            key = _instance_key(compiled, frame)
            stale = self._stale_instances(compiled, key)
            for item in stale:
                forced = "immediate_invalidator"
                closed = self._force_close(
                    item,
                    reason=forced,
                    frame_sequence=int(frame.frame_sequence),
                    now_mono_ms=int(frame.observed_mono_ms),
                    frame=frame,
                )
                observations.extend(closed[0])
                transitions.extend(closed[1])
                expired.extend(closed[2])
                self._instances.pop(item.key, None)

            current = self._instances.get(key)
            if current is None:
                current = _Instance(
                    key=key,
                    compiled=compiled,
                    start_event=_DIRECTIONAL_START_EVENTS[compiled.detector_id],
                    tape_channel=_DIRECTIONAL_CHANNELS[compiled.detector_id],
                    state_entered_mono_ms=int(frame.observed_mono_ms),
                )
                self._instances[key] = current

            env = PredicateEnv(
                now_mono_ms=int(frame.observed_mono_ms),
                parameters=params,
                bindings=bindings,
                frame=frame,
            )
            enter_result = current.evaluator.evaluate(compiled.enter_signal, env)
            clear_result = current.evaluator.evaluate(compiled.clear, env)
            immediate_result = current.evaluator.evaluate(compiled.immediate, env)
            if compiled.material_update is None:
                material_result: PredicateResult | None = None
                catalog_material = False
            else:
                material_result = current.evaluator.evaluate(compiled.material_update, env)
                catalog_material = material_result.satisfies
            material_flag = catalog_material or _material_since_emit(
                current, frame, bindings, params
            )

            now = int(frame.observed_mono_ms)
            elapsed = max(0.0, (now - current.state_entered_mono_ms) / 1000.0)
            since_update = (
                0.0
                if current.last_update_mono_ms is None
                else max(0.0, (now - current.last_update_mono_ms) / 1000.0)
            )
            previous = current.state
            nxt, emission = reduce_lifecycle(
                previous,
                enter=_verdict_flag(enter_result),
                clear=_verdict_flag(clear_result),
                immediate_invalidator=immediate_result.satisfies,
                material_change=material_flag,
                elapsed_in_state_s=elapsed,
                seconds_since_update=since_update,
                confirm_s=float(params[compiled.hold_parameter]),
                clear_s=float(params[compiled.clear_hold_parameter]),
                update_min_interval_s=float(params["update_min_interval_s"]),
            )
            reason = _reason(previous, nxt, emission)
            obs, trans, cands, facts = self._apply(
                current,
                frame=frame,
                previous=previous,
                nxt=nxt,  # type: ignore[arg-type]
                emission=emission,
                reason=reason,
                predicates=(
                    ("enter_signal", enter_result.verdict.value),
                    ("clear", clear_result.verdict.value),
                    ("immediate", immediate_result.verdict.value),
                    (
                        "material_update",
                        "false" if material_result is None else material_result.verdict.value,
                    ),
                ),
            )
            observations.append(obs)
            transitions.extend(trans)
            candidates.extend(cands)
            expired.extend(facts)
            if emission in {"started", "updated"}:
                _remember_emit(current, frame, bindings)
            if current.state == "inactive":
                self._instances.pop(current.key, None)

        return DetectorBankStep(
            accepted=True,
            observations=tuple(observations),
            transitions=tuple(transitions),
            candidates=tuple(candidates),
            expired_facts=tuple(dict.fromkeys(expired)),
        )

    def _selected(self, detector_ids: tuple[str, ...] | None) -> tuple[CompiledDetector, ...]:
        if detector_ids is None:
            return self._directional
        wanted = set(detector_ids)
        return tuple(item for item in self._directional if item.detector_id in wanted)

    def _stale_instances(
        self, compiled: CompiledDetector, key: DetectorInstanceKey
    ) -> list[_Instance]:
        found: list[_Instance] = []
        for item in self._instances.values():
            if item.compiled.detector_id != compiled.detector_id:
                continue
            if item.compiled.version != compiled.version:
                continue
            if item.key == key:
                continue
            found.append(item)
        return found

    def _force_close(
        self,
        item: _Instance,
        *,
        reason: str,
        frame_sequence: int,
        now_mono_ms: int,
        frame: FeatureFrame | None = None,
    ) -> tuple[tuple[DetectorObservation, ...], tuple[DetectorTransition, ...], tuple[str, ...]]:
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
        obs, trans, _cands, facts = self._apply(
            item,
            frame=frame,
            previous=previous,
            nxt=nxt,  # type: ignore[arg-type]
            emission=emission,
            reason=reason,
            predicates=(("immediate", "true"),),
            frame_sequence=frame_sequence,
            now_mono_ms=now_mono_ms,
        )
        return (obs,), trans, facts

    def _apply(
        self,
        item: _Instance,
        *,
        frame: FeatureFrame | None,
        previous: str,
        nxt: DetectorState,
        emission: str | None,
        reason: str,
        predicates: tuple[tuple[str, str], ...],
        frame_sequence: int | None = None,
        now_mono_ms: int | None = None,
    ) -> tuple[
        DetectorObservation,
        tuple[DetectorTransition, ...],
        tuple[DetectorCandidate, ...],
        tuple[str, ...],
    ]:
        seq = int(frame.frame_sequence) if frame is not None else int(frame_sequence or 0)
        now = int(frame.observed_mono_ms) if frame is not None else int(now_mono_ms or 0)
        if nxt != previous:
            item.state = nxt
            item.state_entered_mono_ms = now
        v4: str | None = None
        revision: int | None = None
        expire: tuple[str, ...] = ()
        candidates: list[DetectorCandidate] = []
        transitions: list[DetectorTransition] = []
        if emission == "started":
            item.material_revision = 1
            item.last_update_mono_ms = now
            revision = 1
            v4 = item.start_event
        elif emission == "updated":
            item.material_revision += 1
            item.last_update_mono_ms = now
            revision = item.material_revision
            v4 = item.start_event
        elif emission == "ended":
            expire = (_CLOSING_FACT,)
            item.material_revision = 0
            item.last_update_mono_ms = None
        observation_id = _observation_id(item.key, seq, nxt)
        if emission is not None:
            kind: TransitionKind = _TRANSITION[emission]  # type: ignore[assignment]
            transitions.append(
                DetectorTransition(
                    kind=kind,
                    reason=reason,
                    instance=item.key,
                    v4_event_kind=v4,
                    material_revision=revision,
                    expire_facts=expire,
                )
            )
        if v4 is not None:
            candidates.append(
                DetectorCandidate(
                    kind=v4,
                    detector_id=item.key.detector_id,
                    observation_id=observation_id,
                    material_revision=int(revision or 1),
                    tape_channel=item.tape_channel,
                )
            )
        occurrence = None
        stream_epoch = item.key.stream_epoch
        broadcast_epoch = 0
        if frame is not None:
            occurrence = _occurrence_text(frame) or None
            stream_epoch = int(frame.stream_epoch)
            broadcast_epoch = int(frame.broadcast_epoch)
        elif item.key.occurrence_id:
            occurrence = item.key.occurrence_id
        observation = DetectorObservation(
            observation_id=observation_id,
            detector_id=item.key.detector_id,
            detector_version=str(item.key.detector_version),
            detector_config_hash=self._detector_config_hash,
            parameter_snapshot_id=self._parameter_snapshot_id,
            observed_mono_ms=now,
            broadcast_epoch=broadcast_epoch,
            stream_epoch=stream_epoch,
            occurrence_id=occurrence,
            correlation_key=item.key.correlation_key,
            previous_state=previous,  # type: ignore[arg-type]
            candidate_state=nxt,
            transition_reason=reason,
            would_emit_event_kind=v4,
            tape_channel=item.tape_channel,
            predicate_results=predicates,
        )
        return observation, tuple(transitions), tuple(candidates), expire

    @staticmethod
    def _defaults(compiled: CompiledDetector) -> dict[str, int | float]:
        raw = json.loads(packaged_schema_bytes("detector-catalog.json"))
        for item in raw.get("definitions") or []:
            if item.get("id") == compiled.detector_id:
                return {str(row["id"]): row["default"] for row in item.get("parameters") or []}
        return {}
