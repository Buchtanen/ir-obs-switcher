"""UNDER_PRESSURE temporal detector for battle_behind_v1.

Projects frozen hysteretic bands onto existing V4 identifiers. Reuses
`reduce_band` from the CLOSING detector. Does not import NarrativeRuntime,
overlay tape or commentary. Not live-wired.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass

from irswitch.contracts.feature import FeatureFrame
from irswitch.contracts.predicate import BindingValue
from irswitch.contracts.resources import packaged_schema_bytes
from irswitch.events.closing import BandState, reduce_band
from irswitch.events.detector_bank import (
    DetectorBank,
    DetectorInstanceKey,
    DetectorTransition,
)

GAP_V1 = "gap.relation.seconds.estimated_v1"
DETECTOR_ID = "battle_behind_v1"
_BAND_OUTPUT = {
    "closing": ("HUNTED", "battle.pressure_behind", "race.battle.pressure", "battle.closing"),
    "approach": (
        "RIVAL_THREAT",
        "battle.rival_threat",
        "race.battle.pressure",
        "battle.position_threat",
    ),
    "attack": (
        "RIVAL_THREAT",
        "battle.rival_threat",
        "race.battle.pressure",
        "battle.position_threat",
    ),
    "overlap": (
        "RIVAL_THREAT",
        "battle.rival_threat",
        "race.battle.pressure",
        "battle.position_threat",
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
    detector = next(item for item in raw["definitions"] if item["id"] == DETECTOR_ID)
    return {str(row["id"]): float(row["default"]) for row in detector.get("parameters") or []}


def _feature_number(frame: FeatureFrame, feature_id: str) -> float | None:
    for item in frame.values:
        if item.feature_id == feature_id:
            if isinstance(item.value, bool) or not isinstance(item.value, (int, float)):
                return None
            return float(item.value)
    return None


@dataclass(frozen=True, slots=True)
class PressureTrace:
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
class PressureCandidate:
    kind: str
    narrative_kind: str
    tape_channel: str
    detector_id: str
    observation_id: str
    material_revision: int
    band: str


@dataclass(frozen=True, slots=True)
class PressureStep:
    accepted: bool
    diagnostic: str | None = None
    candidates: tuple[PressureCandidate, ...] = ()
    transitions: tuple[DetectorTransition, ...] = ()
    expired_facts: tuple[str, ...] = ()
    published_facts: tuple[str, ...] = ()
    trace: PressureTrace | None = None


@dataclass
class _BandInstance:
    key: DetectorInstanceKey
    band: BandState = "closing"
    overlap_since_ms: int | None = None


class PressureDetector:
    """battle_behind_v1 product detector: FSM + hysteretic band projection."""

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
    ) -> PressureStep:
        params = {**self._defaults, **dict(parameters or {})}
        bound = dict(bindings or {})
        bank_step = self._bank.step(
            frame,
            bindings=bound,
            parameters=params,
            detector_ids=(DETECTOR_ID,),
        )
        if not bank_step.accepted:
            return PressureStep(False, bank_step.diagnostic)

        expired: list[str] = list(bank_step.expired_facts)
        published: list[str] = []
        candidates: list[PressureCandidate] = []
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

        live_obs = [item for item in bank_step.observations if item.detector_id == DETECTOR_ID]
        if not live_obs:
            return PressureStep(
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
                if candidate.detector_id == DETECTOR_ID:
                    revision = candidate.material_revision
            candidates.append(
                PressureCandidate(
                    kind=v4,
                    narrative_kind=narrative,
                    tape_channel=channel,
                    detector_id=DETECTOR_ID,
                    observation_id=observation.observation_id,
                    material_revision=revision,
                    band=nxt_band,
                )
            )
            if nxt_band != "closing":
                published.append(fact)
            if band_changed and previous_band != "closing":
                previous_fact = _BAND_OUTPUT[previous_band][3]
                if previous_fact != fact:
                    expired.append(previous_fact)

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
        return PressureStep(
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
    ) -> PressureTrace:
        thresholds = {key: float(params[key]) for key in _TRACE_KEYS if key in params}
        refs = [frame.source_snapshot_id]
        return PressureTrace(
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
