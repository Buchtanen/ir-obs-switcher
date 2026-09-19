"""CLOSING temporal detector for battle_ahead_v1.

Projects frozen hysteretic bands onto existing V4 identifiers. Does not
import NarrativeRuntime, overlay tape or commentary. Not live-wired.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from irswitch.contracts.feature import FeatureFrame
from irswitch.contracts.predicate import BindingValue
from irswitch.contracts.resources import packaged_schema_bytes
from irswitch.events.detector_bank import (
    DetectorBank,
    DetectorInstanceKey,
    DetectorTransition,
)

BandState = Literal["closing", "approach", "attack", "overlap"]
GAP_V1 = "gap.relation.seconds.estimated_v1"

_DEFAULT_BAND = {
    "approach_enter_s": 1.50,
    "approach_exit_s": 1.80,
    "attack_enter_s": 0.80,
    "attack_exit_s": 1.10,
    "overlap_enter_s": 0.35,
    "overlap_exit_s": 0.55,
    "overlap_confirm_s": 0.50,
}
_BAND_OUTPUT = {
    "closing": ("HUNTING", "battle.pursuit", "race.battle.closing", "battle.closing"),
    "approach": ("APPROACH", "battle.approach", "race.battle.closing", "battle.approaching"),
    "attack": ("ATTACK_RANGE", "battle.attack_range", "race.battle.attack", "battle.attack_range"),
    "overlap": (
        "SIDE_BY_SIDE",
        "battle.side_by_side",
        "race.battle.side_by_side",
        "battle.side_by_side",
    ),
}
_TRACE_KEYS = (
    "enter_gap_max_s",
    "confirm_s",
    "min_closing_change_s",
    "max_closing_slope",
    "min_coverage",
    "material_change_s",
    "update_min_interval_s",
    "approach_enter_s",
    "approach_exit_s",
    "attack_enter_s",
    "attack_exit_s",
    "overlap_enter_s",
    "overlap_exit_s",
    "overlap_confirm_s",
)


def _catalog_defaults() -> dict[str, float]:
    raw = json.loads(packaged_schema_bytes("detector-catalog.json"))
    detector = next(item for item in raw["definitions"] if item["id"] == "battle_ahead_v1")
    return {str(row["id"]): float(row["default"]) for row in detector.get("parameters") or []}


def reduce_band(
    state: str,
    *,
    gap: float,
    overlap_held: float = 0.0,
    overlap_known: bool = True,
    parameters: Mapping[str, float] | None = None,
) -> BandState:
    """Frozen hysteretic band reducer. Matches machine `reduce_band` goldens."""

    params = {**_DEFAULT_BAND, **dict(parameters or {})}
    overlap_ready = overlap_held >= float(params["overlap_confirm_s"])
    if gap <= float(params["overlap_enter_s"]) and overlap_ready:
        return "overlap"
    if state != "overlap" and gap <= float(params["attack_enter_s"]):
        return "attack"
    if state in {"closing", "approach"} and gap <= float(params["approach_enter_s"]):
        return "approach"
    if state == "overlap" and overlap_known and gap >= float(params["overlap_exit_s"]):
        return "attack"
    if state == "attack" and gap >= float(params["attack_exit_s"]):
        return "approach"
    if state == "approach" and gap >= float(params["approach_exit_s"]):
        return "closing"
    return state  # type: ignore[return-value]


def _feature_number(frame: FeatureFrame, feature_id: str) -> float | None:
    for item in frame.values:
        if item.feature_id == feature_id:
            if isinstance(item.value, bool) or not isinstance(item.value, (int, float)):
                return None
            return float(item.value)
    return None


@dataclass(frozen=True, slots=True)
class ClosingTrace:
    fsm_state: str
    previous_band: str
    band: str
    gap_s: float | None
    slope: float | None
    net_closing_s: float | None
    coverage: float | None
    confidence: float | None
    overlap_held_s: float
    transition_reason: str
    effective_thresholds: dict[str, float]
    evidence_refs: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ClosingCandidate:
    kind: str
    narrative_kind: str
    tape_channel: str
    detector_id: str
    observation_id: str
    material_revision: int
    band: str


@dataclass(frozen=True, slots=True)
class ClosingStep:
    accepted: bool
    diagnostic: str | None = None
    candidates: tuple[ClosingCandidate, ...] = ()
    transitions: tuple[DetectorTransition, ...] = ()
    expired_facts: tuple[str, ...] = ()
    published_facts: tuple[str, ...] = ()
    trace: ClosingTrace | None = None


@dataclass
class _BandInstance:
    key: DetectorInstanceKey
    band: BandState = "closing"
    overlap_since_ms: int | None = None


class ClosingDetector:
    """battle_ahead_v1 product detector: FSM + hysteretic band projection."""

    def __init__(self) -> None:
        self._bank = DetectorBank()
        self._bands: dict[DetectorInstanceKey, _BandInstance] = {}
        self._defaults = _catalog_defaults()

    def observe(
        self,
        frame: FeatureFrame,
        *,
        bindings: Mapping[str, BindingValue] | None = None,
        parameters: Mapping[str, int | float] | None = None,
        overlap_active: bool | None = None,
    ) -> ClosingStep:
        params = {**self._defaults, **dict(parameters or {})}
        bound = dict(bindings or {})
        bank_step = self._bank.step(
            frame,
            bindings=bound,
            parameters=params,
            detector_ids=("battle_ahead_v1",),
        )
        if not bank_step.accepted:
            return ClosingStep(False, bank_step.diagnostic)

        expired: list[str] = list(bank_step.expired_facts)
        published: list[str] = []
        candidates: list[ClosingCandidate] = []
        gap = _feature_number(frame, GAP_V1)

        ended_keys = {
            transition.instance
            for transition in bank_step.transitions
            if transition.kind == "ENDED"
        }
        for ended_key in ended_keys:
            closed = self._bands.pop(ended_key, None)
            if closed is not None and closed.band != "closing":
                expired.append(_BAND_OUTPUT[closed.band][3])

        live_obs = [
            item for item in bank_step.observations if item.detector_id == "battle_ahead_v1"
        ]
        if not live_obs:
            return ClosingStep(
                True,
                transitions=bank_step.transitions,
                expired_facts=tuple(dict.fromkeys(expired)),
                published_facts=(),
                trace=self._trace(
                    fsm_state="inactive",
                    previous_band="closing",
                    band="closing",
                    frame=frame,
                    gap=gap,
                    overlap_held=0.0,
                    reason="inactive",
                    params=params,
                ),
            )

        observation = live_obs[-1]
        key = DetectorInstanceKey(
            detector_id=observation.detector_id,
            detector_version=int(observation.detector_version),
            stream_epoch=int(observation.stream_epoch),
            occurrence_id=observation.occurrence_id or "",
            correlation_key=tuple(observation.correlation_key),
        )
        record = self._bands.get(key)
        if record is None:
            record = _BandInstance(key=key)
            self._bands[key] = record
        previous_band = record.band
        fsm_state = observation.candidate_state
        overlap_held, overlap_known = self._overlap_hold(
            record,
            frame=frame,
            gap=gap,
            overlap_active=overlap_active,
            params=params,
        )
        nxt_band: BandState = previous_band
        if fsm_state == "active" and gap is not None:
            nxt_band = reduce_band(
                previous_band,
                gap=gap,
                overlap_held=overlap_held,
                overlap_known=overlap_known,
                parameters=params,
            )
            record.band = nxt_band
        elif fsm_state == "inactive":
            nxt_band = "closing"
            self._bands.pop(key, None)
        band_changed = fsm_state == "active" and nxt_band != previous_band

        emission = next(
            (item.kind for item in bank_step.transitions if item.instance == key),
            None,
        )
        if fsm_state == "active" and (emission in {"STARTED", "UPDATED"} or band_changed):
            v4, narrative, channel, fact = _BAND_OUTPUT[nxt_band]
            revision = 1
            for candidate in bank_step.candidates:
                if candidate.detector_id == "battle_ahead_v1":
                    revision = candidate.material_revision
            candidates.append(
                ClosingCandidate(
                    kind=v4,
                    narrative_kind=narrative,
                    tape_channel=channel,
                    detector_id="battle_ahead_v1",
                    observation_id=observation.observation_id,
                    material_revision=revision,
                    band=nxt_band,
                )
            )
            if nxt_band != "closing":
                published.append(fact)
            if band_changed and previous_band != "closing":
                expired.append(_BAND_OUTPUT[previous_band][3])

        if fsm_state == "inactive" and previous_band != "closing":
            expired.append(_BAND_OUTPUT[previous_band][3])

        trace = self._trace(
            fsm_state=fsm_state,
            previous_band=previous_band,
            band=nxt_band if fsm_state == "active" else previous_band,
            frame=frame,
            gap=gap,
            overlap_held=overlap_held,
            reason=observation.transition_reason,
            params=params,
        )
        return ClosingStep(
            True,
            candidates=tuple(candidates[:1]),
            transitions=bank_step.transitions,
            expired_facts=tuple(dict.fromkeys(expired)),
            published_facts=tuple(dict.fromkeys(published)),
            trace=trace,
        )

    def _overlap_hold(
        self,
        record: _BandInstance,
        *,
        frame: FeatureFrame,
        gap: float | None,
        overlap_active: bool | None,
        params: Mapping[str, float],
    ) -> tuple[float, bool]:
        now = int(frame.observed_mono_ms)
        enter = float(params["overlap_enter_s"])
        if overlap_active is True and gap is not None and gap <= enter:
            if record.overlap_since_ms is None:
                record.overlap_since_ms = now
            held = max(0.0, (now - record.overlap_since_ms) / 1000.0)
            return held, True
        if overlap_active is False:
            record.overlap_since_ms = None
            return 0.0, True
        if overlap_active is None:
            return (
                (
                    0.0
                    if record.overlap_since_ms is None
                    else max(0.0, (now - record.overlap_since_ms) / 1000.0)
                ),
                False,
            )
        record.overlap_since_ms = None
        return 0.0, True

    @staticmethod
    def _trace(
        *,
        fsm_state: str,
        previous_band: str,
        band: str,
        frame: FeatureFrame,
        gap: float | None,
        overlap_held: float,
        reason: str,
        params: Mapping[str, float],
    ) -> ClosingTrace:
        thresholds = {key: float(params[key]) for key in _TRACE_KEYS if key in params}
        refs = [frame.source_snapshot_id]
        return ClosingTrace(
            fsm_state=fsm_state,
            previous_band=previous_band,
            band=band,
            gap_s=gap,
            slope=_feature_number(frame, "gap.trend.slope"),
            net_closing_s=_feature_number(frame, "gap.trend.net_closing"),
            coverage=_feature_number(frame, "gap.trend.coverage"),
            confidence=_feature_number(frame, "gap.trend.confidence"),
            overlap_held_s=overlap_held,
            transition_reason=reason,
            effective_thresholds=thresholds,
            evidence_refs=tuple(refs),
        )
