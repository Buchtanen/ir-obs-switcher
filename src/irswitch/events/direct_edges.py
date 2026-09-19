"""Deterministic S/F and sector crossing edges.

Identity dedupe and lifecycle guards only. Does not reuse DetectorBank
thresholds, and does not import NarrativeRuntime, overlay tape or commentary.
Not live-wired.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Literal

from irswitch.contracts.primitives import ContractViolation, Identifier, LineageId, OccurrenceId
from irswitch.contracts.session import SessionRef

SourceClass = Literal["direct"]
OverlayMode = Literal["PRACTICE", "QUALIFYING", "RACE", "GENERIC"]

LAP_ELIGIBLE_MODES = frozenset({"PRACTICE", "QUALIFYING", "RACE"})
SECTOR_ELIGIBLE_MODES = frozenset({"PRACTICE", "QUALIFYING"})
_V4_NARRATIVE = {
    "LAP_COMPLETE": ("timing.lap_completed", "race.timing.lap"),
    "SECTOR_SPLIT": ("timing.sector_split", "race.timing.sector"),
    "SECTOR_BEST": ("timing.sector_best", "race.timing.sector"),
}
IDENTITY_CAPACITY = 256


def is_sector_point_id(point_id: str) -> bool:
    if len(point_id) < 2 or point_id[0] != "S":
        return False
    return point_id[1:].isdigit()


def _optional_id(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ContractViolation(f"{field} must be an ID or null")
    return str(Identifier(value))


@dataclass(frozen=True, slots=True)
class DirectEdgeIdentity:
    kind: str
    stream_epoch: int
    occurrence_id: str
    hero_id: str
    lap: int
    sector_id: str | None = None

    def candidate_id(self) -> str:
        parts = [
            "direct",
            self.kind,
            str(self.stream_epoch),
            self.occurrence_id,
            self.hero_id,
            str(self.lap),
        ]
        if self.sector_id is not None:
            parts.append(self.sector_id)
        return str(Identifier(":".join(parts)[:128]))


@dataclass(frozen=True, slots=True)
class DirectEdgeSample:
    sample_sequence: int
    observed_mono_ms: int
    source_snapshot_id: str
    broadcast_epoch: int
    stream_epoch: int
    session_ref: SessionRef | None
    occurrence_id: str | None
    lineage_id: str | None
    overlay_mode: str
    hero_id: str
    connected: bool
    lap_completed: int | None
    last_lap_time_s: float | None
    best_lap_time_s: float | None
    incidents: int | None
    session_finished: bool
    player_finished: bool
    sector_id: str | None = None
    sector_lap: int | None = None
    sector_segment_time_s: float | None = None
    sector_valid: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.sample_sequence, bool) or self.sample_sequence < 1:
            raise ContractViolation("sampleSequence must be a positive integer")
        object.__setattr__(self, "source_snapshot_id", str(Identifier(self.source_snapshot_id)))
        object.__setattr__(self, "hero_id", str(Identifier(self.hero_id)))
        if self.overlay_mode not in {"PRACTICE", "QUALIFYING", "RACE", "GENERIC"}:
            raise ContractViolation(f"unknown overlay_mode {self.overlay_mode!r}")
        occurrence = (
            None if self.occurrence_id is None else str(OccurrenceId.parse(self.occurrence_id))
        )
        lineage = None if self.lineage_id is None else str(LineageId.parse(self.lineage_id))
        present = (
            self.session_ref is not None,
            occurrence is not None,
            lineage is not None,
        )
        if any(present) and not all(present):
            raise ContractViolation(
                "sessionRef, occurrenceId and lineageId must be all coherent or all null"
            )
        object.__setattr__(self, "occurrence_id", occurrence)
        object.__setattr__(self, "lineage_id", lineage)
        if self.session_ref is not None and not isinstance(self.session_ref, SessionRef):
            raise ContractViolation("sessionRef must be a SessionRef or null")
        object.__setattr__(self, "sector_id", _optional_id(self.sector_id, "sectorId"))


@dataclass(frozen=True, slots=True)
class DirectEdgeCandidate:
    source_class: SourceClass
    kind: str
    narrative_kind: str
    tape_channel: str
    identity: DirectEdgeIdentity
    observed_mono_ms: int
    broadcast_epoch: int
    stream_epoch: int
    occurrence_id: str
    lineage_id: str | None
    correlation_key: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    detector_observation_id: None = None
    personal_best: bool = False
    lap_time_s: float | None = None
    segment_time_s: float | None = None
    delta_s: float | None = None


@dataclass(frozen=True, slots=True)
class DirectEdgeStep:
    accepted: bool
    diagnostic: str | None = None
    candidates: tuple[DirectEdgeCandidate, ...] = ()


@dataclass
class _HeroState:
    last_lap_completed: int | None = None
    incidents_at_lap_start: int = 0
    sector_bests: dict[str, float] = field(default_factory=dict)


class DirectEdgeBank:
    """Process-local lap/sector edge projector. Replay-deterministic."""

    def __init__(self, identity_capacity: int = IDENTITY_CAPACITY) -> None:
        self._identity_capacity = identity_capacity
        self._seen: OrderedDict[str, None] = OrderedDict()
        self._heroes: dict[tuple[int, str, str], _HeroState] = {}
        self._last_sequence: int | None = None

    def observe(self, sample: DirectEdgeSample) -> DirectEdgeStep:
        if self._last_sequence is not None:
            if int(sample.sample_sequence) < self._last_sequence:
                return DirectEdgeStep(False, "direct_edge_sample_stale")
            if int(sample.sample_sequence) == self._last_sequence:
                return DirectEdgeStep(False, "direct_edge_sample_duplicate")
        self._last_sequence = int(sample.sample_sequence)

        if not sample.connected or sample.occurrence_id is None or sample.stream_epoch < 1:
            return DirectEdgeStep(True)
        scope = (int(sample.stream_epoch), sample.occurrence_id, sample.hero_id)
        state = self._heroes.get(scope)
        if state is None:
            state = _HeroState(
                last_lap_completed=sample.lap_completed,
                incidents_at_lap_start=int(sample.incidents or 0),
            )
            self._heroes[scope] = state
            candidates = self._sector_candidates(sample, state)
            return DirectEdgeStep(True, candidates=candidates)

        candidates = self._lap_candidates(sample, state) + self._sector_candidates(sample, state)
        return DirectEdgeStep(True, candidates=candidates)

    def _lap_candidates(
        self, sample: DirectEdgeSample, state: _HeroState
    ) -> tuple[DirectEdgeCandidate, ...]:
        lap = sample.lap_completed
        incidents = int(sample.incidents or 0)
        prev = state.last_lap_completed
        if lap is None:
            return ()
        if prev is None or lap < prev:
            state.last_lap_completed = lap
            state.incidents_at_lap_start = incidents
            return ()
        if lap == prev:
            return ()
        if sample.overlay_mode not in LAP_ELIGIBLE_MODES:
            return ()
        if sample.session_finished or sample.player_finished:
            state.last_lap_completed = lap
            state.incidents_at_lap_start = incidents
            return ()
        if sample.last_lap_time_s is None or sample.last_lap_time_s <= 0:
            return ()
        if incidents > state.incidents_at_lap_start:
            state.last_lap_completed = lap
            state.incidents_at_lap_start = incidents
            return ()
        identity = DirectEdgeIdentity(
            kind="LAP_COMPLETE",
            stream_epoch=int(sample.stream_epoch),
            occurrence_id=sample.occurrence_id or "",
            hero_id=sample.hero_id,
            lap=lap,
        )
        if not self._claim(identity):
            state.last_lap_completed = lap
            state.incidents_at_lap_start = incidents
            return ()
        personal_best = (
            sample.best_lap_time_s is not None
            and lap > 1
            and abs(sample.last_lap_time_s - sample.best_lap_time_s) < 0.005
        )
        delta = None
        if sample.best_lap_time_s is not None:
            delta = sample.last_lap_time_s - sample.best_lap_time_s
        state.last_lap_completed = lap
        state.incidents_at_lap_start = incidents
        return (
            self._candidate(
                sample,
                identity,
                personal_best=personal_best,
                lap_time_s=sample.last_lap_time_s,
                delta_s=delta,
            ),
        )

    def _sector_candidates(
        self, sample: DirectEdgeSample, state: _HeroState
    ) -> tuple[DirectEdgeCandidate, ...]:
        if sample.overlay_mode not in SECTOR_ELIGIBLE_MODES:
            return ()
        if sample.session_finished or sample.player_finished:
            return ()
        sector_id = sample.sector_id
        lap = sample.sector_lap
        segment = sample.sector_segment_time_s
        if (
            sector_id is None
            or lap is None
            or segment is None
            or segment <= 0
            or not sample.sector_valid
            or not is_sector_point_id(sector_id)
        ):
            return ()
        split = DirectEdgeIdentity(
            kind="SECTOR_SPLIT",
            stream_epoch=int(sample.stream_epoch),
            occurrence_id=sample.occurrence_id or "",
            hero_id=sample.hero_id,
            lap=lap,
            sector_id=sector_id,
        )
        if not self._claim(split):
            return ()
        out = [
            self._candidate(sample, split, segment_time_s=segment),
        ]
        prev = state.sector_bests.get(sector_id)
        improved = prev is not None and segment < prev
        if prev is None or improved:
            state.sector_bests[sector_id] = segment
        if improved:
            best = DirectEdgeIdentity(
                kind="SECTOR_BEST",
                stream_epoch=int(sample.stream_epoch),
                occurrence_id=sample.occurrence_id or "",
                hero_id=sample.hero_id,
                lap=lap,
                sector_id=sector_id,
            )
            if self._claim(best):
                out.append(
                    self._candidate(
                        sample,
                        best,
                        segment_time_s=segment,
                        delta_s=None if prev is None else segment - prev,
                    )
                )
        return tuple(out)

    def _claim(self, identity: DirectEdgeIdentity) -> bool:
        key = identity.candidate_id()
        if key in self._seen:
            return False
        while len(self._seen) >= self._identity_capacity:
            self._seen.popitem(last=False)
        self._seen[key] = None
        return True

    @staticmethod
    def _candidate(
        sample: DirectEdgeSample,
        identity: DirectEdgeIdentity,
        *,
        personal_best: bool = False,
        lap_time_s: float | None = None,
        segment_time_s: float | None = None,
        delta_s: float | None = None,
    ) -> DirectEdgeCandidate:
        narrative, channel = _V4_NARRATIVE[identity.kind]
        parts = [sample.hero_id, f"lap:{identity.lap}"]
        if identity.sector_id is not None:
            parts.append(identity.sector_id)
        correlation = tuple(parts)
        return DirectEdgeCandidate(
            source_class="direct",
            kind=identity.kind,
            narrative_kind=narrative,
            tape_channel=channel,
            identity=identity,
            observed_mono_ms=int(sample.observed_mono_ms),
            broadcast_epoch=int(sample.broadcast_epoch),
            stream_epoch=int(sample.stream_epoch),
            occurrence_id=identity.occurrence_id,
            lineage_id=sample.lineage_id,
            correlation_key=correlation,
            evidence_refs=(sample.source_snapshot_id,),
            personal_best=personal_best,
            lap_time_s=lap_time_s,
            segment_time_s=segment_time_s,
            delta_s=delta_s,
        )
