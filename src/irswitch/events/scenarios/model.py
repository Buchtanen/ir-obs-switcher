"""Immutable contracts shared by scenario guards, engines, and event adapters."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType

from irswitch.events.envelope import WIRE_PHASES

_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]*$")
_EVENT_TYPE = re.compile(r"^[A-Z][A-Z0-9_]*$")


def _bounded_probability(value: float, *, field_name: str) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0.0 <= value <= 1.0
    ):
        raise ValueError(f"{field_name} must be finite and within [0, 1]")


def _stable_identifier(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"{field_name} must be a lowercase snake-case identifier")


@dataclass(frozen=True)
class EvidenceValue:
    """One normalized observation or feature with explicit freshness and quality."""

    value: object | None
    observed_at: float
    age_s: float
    valid: bool
    quality: float
    uncertainty: float | None
    source: str

    def __post_init__(self) -> None:
        if not math.isfinite(self.observed_at) or self.observed_at < 0.0:
            raise ValueError("observed_at must be finite and non-negative")
        if not math.isfinite(self.age_s) or self.age_s < 0.0:
            raise ValueError("age_s must be finite and non-negative")
        _bounded_probability(self.quality, field_name="quality")
        if self.uncertainty is not None and (
            not math.isfinite(self.uncertainty) or self.uncertainty < 0.0
        ):
            raise ValueError("uncertainty must be finite and non-negative")
        if not self.source.strip():
            raise ValueError("source must not be empty")
        if self.valid and self.value is None:
            raise ValueError("valid evidence must contain a value")
        if isinstance(self.value, float) and not math.isfinite(self.value):
            raise ValueError("evidence value must not be NaN or infinity")
        object.__setattr__(self, "value", freeze_json(self.value))


class GuardDecision(StrEnum):
    """Tri-state result; missing evidence is not equivalent to a false guard."""

    MATCH = "match"
    NO_MATCH = "no_match"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class GuardResult:
    """Pure guard result with a stable diagnostic reason and evidence references."""

    decision: GuardDecision
    confidence: float
    reason: str
    evidence: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.decision, GuardDecision):
            raise ValueError("decision must be a GuardDecision")
        _bounded_probability(self.confidence, field_name="confidence")
        _stable_identifier(self.reason, field_name="reason")
        if self.decision is GuardDecision.UNKNOWN and self.confidence != 0.0:
            raise ValueError("unknown guard result must use zero confidence")
        if any(not item.strip() for item in self.evidence):
            raise ValueError("evidence references must not be empty")
        object.__setattr__(self, "evidence", tuple(self.evidence))

    @property
    def matched(self) -> bool:
        return self.decision is GuardDecision.MATCH

    @property
    def unknown(self) -> bool:
        return self.decision is GuardDecision.UNKNOWN


@dataclass(frozen=True)
class EpisodeScope:
    """Identity namespace that prevents stories crossing session/run/hero boundaries."""

    scenario_id: str
    subsession_id: str
    session_num: int
    run_epoch: int
    player_car_idx: int

    def __post_init__(self) -> None:
        _stable_identifier(self.scenario_id, field_name="scenario_id")
        if not self.subsession_id.strip():
            raise ValueError("subsession_id must not be empty")
        for field_name in ("session_num", "run_epoch", "player_car_idx"):
            value = getattr(self, field_name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ValueError(f"{field_name} must be a non-negative integer")

    def episode_id(self, episode_sequence: int) -> str:
        if (
            not isinstance(episode_sequence, int)
            or isinstance(episode_sequence, bool)
            or episode_sequence < 1
        ):
            raise ValueError("episode_sequence must be a positive integer")
        return (
            f"scenario:{self.scenario_id}:session:{self.subsession_id}:{self.session_num}:"
            f"run:{self.run_epoch}:hero:{self.player_car_idx}:episode:{episode_sequence}"
        )


@dataclass(frozen=True)
class ScenarioBeat:
    """One immutable factual beat emitted by a scenario episode."""

    scenario_id: str
    scenario_version: int
    episode_id: str
    parent_story_id: str
    beat_id: str
    event_type: str
    phase: str
    priority: int
    confidence: float
    reason: str
    metrics: Mapping[str, object]

    def __post_init__(self) -> None:
        _stable_identifier(self.scenario_id, field_name="scenario_id")
        _stable_identifier(self.beat_id, field_name="beat_id")
        _stable_identifier(self.reason, field_name="reason")
        if (
            not isinstance(self.scenario_version, int)
            or isinstance(self.scenario_version, bool)
            or self.scenario_version < 1
        ):
            raise ValueError("scenario_version must be a positive integer")
        if not self.episode_id.strip():
            raise ValueError("episode_id must not be empty")
        if not self.parent_story_id.strip():
            raise ValueError("parent_story_id must not be empty")
        if not _EVENT_TYPE.fullmatch(self.event_type):
            raise ValueError("event_type must be an uppercase snake-case identifier")
        if self.phase not in WIRE_PHASES:
            raise ValueError(f"unsupported event phase: {self.phase!r}")
        if not isinstance(self.priority, int) or isinstance(self.priority, bool):
            raise ValueError("priority must be an integer")
        _bounded_probability(self.confidence, field_name="confidence")
        if any(not isinstance(key, str) or not key for key in self.metrics):
            raise ValueError("metric keys must be non-empty strings")
        frozen_metrics = freeze_mapping(self.metrics)
        object.__setattr__(self, "metrics", frozen_metrics)

    @property
    def correlation_id(self) -> str:
        return f"{self.episode_id}:beat:{self.beat_id}"

    def to_dict(self) -> dict[str, object]:
        """Stable internal representation before EventManager sequence stamping."""
        return {
            "scenario_id": self.scenario_id,
            "scenario_version": self.scenario_version,
            "episode_id": self.episode_id,
            "parent_story_id": self.parent_story_id,
            "beat_id": self.beat_id,
            "correlation_id": self.correlation_id,
            "event_type": self.event_type,
            "phase": self.phase,
            "priority": self.priority,
            "confidence": self.confidence,
            "reason": self.reason,
            "metrics": thaw_json(self.metrics),
        }


@dataclass(frozen=True)
class ScenarioState:
    id: str
    initial: bool
    terminal: bool
    meaning: str


@dataclass(frozen=True)
class ScenarioTransition:
    id: str
    order: int
    sources: tuple[str, ...]
    target: str
    guard: str
    actions: tuple[str, ...]
    reason: str
    hold_s: float = 0.0
    within_s: float | None = None
    after_s: float | None = None
    enter_confidence: float = 1.0
    clock: str = "state"


@dataclass(frozen=True)
class ScenarioEmission:
    id: str
    beat_id: str
    event_type: str
    phase: str
    channel: str
    metrics: tuple[str, ...]
    priority: int | None = None
    priority_source: str = ""


@dataclass(frozen=True)
class ScenarioDefinition:
    schema_version: int
    scenario_id: str
    scenario_version: int
    status: str
    scope_modes: tuple[str, ...]
    requires_connected: bool
    identity_fields: tuple[str, ...]
    initial_state: str
    states: tuple[ScenarioState, ...]
    transitions: tuple[ScenarioTransition, ...]
    emissions: Mapping[str, ScenarioEmission]
    parameters: Mapping[str, object]
    document: Mapping[str, object]

    def __post_init__(self) -> None:
        object.__setattr__(self, "emissions", MappingProxyType(dict(self.emissions)))
        object.__setattr__(self, "parameters", freeze_mapping(self.parameters))
        object.__setattr__(self, "document", freeze_mapping(self.document))


def freeze_mapping(value: Mapping[str, object]) -> Mapping[str, object]:
    if any(not isinstance(key, str) or not key for key in value):
        raise ValueError("JSON keys must be non-empty strings")
    return MappingProxyType({key: freeze_json(item) for key, item in sorted(value.items())})


def freeze_json(value: object) -> object:
    """Snapshot a JSON-shaped value without nested mutable aliases."""
    if isinstance(value, Mapping):
        return freeze_mapping(value)
    if isinstance(value, (list, tuple)):
        return tuple(freeze_json(item) for item in value)
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and math.isfinite(value):
        return value
    raise ValueError("scenario data must contain finite JSON values only")


def thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [thaw_json(item) for item in value]
    return value
