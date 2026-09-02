"""Deterministic stateful scoring for the commentary sequence graph.

The runtime owns editorial exposure state only.  It never decides whether an
event is true and it never mutates an :class:`EventEnvelope`.  Callers build
factually valid candidates, score them, and commit exposure only when audible
speech actually starts.
"""

from __future__ import annotations

import math
from collections import OrderedDict, deque
from dataclasses import dataclass
from typing import Any, TypeVar

from irswitch.commentary.graph import (
    Criticality,
    GraphEdge,
    GraphNode,
    MaterialChangePolicy,
    SemanticPolicy,
    SequenceGraph,
)
from irswitch.events.envelope import EventEnvelope

SILENCE_NODE_ID = "__silence__"


@dataclass(frozen=True)
class GraphScoringSettings:
    """Tunable score constants kept outside graph traversal state."""

    selection_threshold: float = 45.0
    max_silence_s: float = 33.0
    max_silence_bonus: float = 30.0
    closure_bonus: float = 15.0
    material_change_bonus: float = 10.0
    node_weight: float = 6.0
    semantic_weight: float = 14.0
    edge_weight: float = 5.0
    path_weight: float = 8.0
    node_half_life_s: float = 90.0
    semantic_half_life_s: float = 120.0
    edge_half_life_s: float = 120.0
    path_half_life_s: float = 180.0
    max_node_stats: int = 128
    max_edge_stats: int = 128
    max_semantic_stats: int = 128
    max_path_stats: int = 64
    max_occurrences: int = 2048

    def __post_init__(self) -> None:
        positive = (
            self.max_silence_s,
            self.node_half_life_s,
            self.semantic_half_life_s,
            self.edge_half_life_s,
            self.path_half_life_s,
        )
        capacities = (
            self.max_node_stats,
            self.max_edge_stats,
            self.max_semantic_stats,
            self.max_path_stats,
            self.max_occurrences,
        )
        if any(value <= 0 for value in positive):
            raise ValueError("graph timing settings must be positive")
        if any(value <= 0 for value in capacities):
            raise ValueError("graph state capacities must be positive")
        if self.selection_threshold < 0 or self.max_silence_bonus < 0:
            raise ValueError("graph score thresholds and bonuses must be non-negative")


@dataclass(frozen=True)
class GraphCandidate:
    node_id: str
    event_id: str
    event_type: str
    story_id: str | None
    correlation_id: str
    run_epoch: int
    source_revision: int
    semantic_key: str
    material_revision: str
    priority: int
    source_sequence: int
    envelope: EventEnvelope


@dataclass(frozen=True)
class ScoreBreakdown:
    base: float
    transition: float
    closure: float
    material_change: float
    silence: float
    node_fatigue: float
    semantic_fatigue: float
    edge_fatigue: float
    path_fatigue: float
    repeat_penalty: float
    final: float
    critical_floor: bool


@dataclass(frozen=True)
class GraphSelection:
    candidate: GraphCandidate
    score: ScoreBreakdown


@dataclass
class _FatigueStat:
    value: float
    last_at: float


@dataclass(frozen=True)
class _PreviousNode:
    node_id: str
    correlation_id: str
    spoken_at: float


_K = TypeVar("_K")


class SequenceGraphRuntime:
    """One run-scoped traversal state and its pure deterministic ranker."""

    def __init__(
        self,
        graph: SequenceGraph,
        *,
        settings: GraphScoringSettings | None = None,
        started_at: float = 0.0,
    ) -> None:
        self.graph = graph
        self.settings = settings or GraphScoringSettings()
        self.run_epoch = 0
        self.current_node_id = SILENCE_NODE_ID
        self._silence_entered_at = started_at
        self._previous: _PreviousNode | None = None
        self._speaking = False
        self._spoken_path: deque[str] = deque(maxlen=3)
        self._node_fatigue: OrderedDict[str, _FatigueStat] = OrderedDict()
        self._edge_fatigue: OrderedDict[tuple[str, str], _FatigueStat] = OrderedDict()
        self._semantic_fatigue: OrderedDict[str, _FatigueStat] = OrderedDict()
        self._path_fatigue: OrderedDict[tuple[str, ...], _FatigueStat] = OrderedDict()
        self._semantic_revision: OrderedDict[str, str] = OrderedDict()
        self._occurrences: OrderedDict[str, None] = OrderedDict()

    @property
    def occurrence_count(self) -> int:
        return len(self._occurrences)

    def fatigue_counts(self) -> dict[str, int]:
        return {
            "node": len(self._node_fatigue),
            "edge": len(self._edge_fatigue),
            "semantic": len(self._semantic_fatigue),
            "path": len(self._path_fatigue),
        }

    def reset(self, *, run_epoch: int, now: float) -> None:
        """Clear all exposure memory at a run boundary and enter silence."""
        self.run_epoch = run_epoch
        self.current_node_id = SILENCE_NODE_ID
        self._silence_entered_at = now
        self._previous = None
        self._speaking = False
        self._spoken_path.clear()
        self._node_fatigue.clear()
        self._edge_fatigue.clear()
        self._semantic_fatigue.clear()
        self._path_fatigue.clear()
        self._semantic_revision.clear()
        self._occurrences.clear()

    def silence_seconds(self, now: float) -> float:
        if self._speaking or self.current_node_id != SILENCE_NODE_ID:
            return 0.0
        return max(0.0, now - self._silence_entered_at)

    def note_completed(self, *, now: float, run_epoch: int) -> bool:
        """Apply an audio completion callback if it belongs to this run."""
        if run_epoch != self.run_epoch:
            return False
        self.current_node_id = SILENCE_NODE_ID
        self._silence_entered_at = now
        self._previous = None
        self._speaking = False
        return True

    def note_interrupted(self, *, now: float, run_epoch: int) -> bool:
        return self.note_completed(now=now, run_epoch=run_epoch)

    def score(self, candidate: GraphCandidate, *, now: float) -> ScoreBreakdown:
        """Calculate a score without mutating traversal state."""
        node = self.graph.nodes.get(candidate.node_id)
        if node is None or candidate.run_epoch != self.run_epoch:
            return _unavailable_score()

        edge = self._matching_edge(candidate, now=now)
        transition = float(edge.editorial.transition_bonus) if edge is not None else 0.0
        closure = self.settings.closure_bonus if edge is not None and edge.editorial.closure else 0.0
        material = self._material_change(candidate)
        silence = self._silence_bonus(node, now=now)

        repeat_weight = node.editorial.repeat_weight
        node_penalty = self._penalty(
            self._node_fatigue.get(candidate.node_id),
            now=now,
            half_life=self.settings.node_half_life_s,
            weight=self.settings.node_weight * repeat_weight,
        )
        semantic_penalty = self._penalty(
            self._semantic_fatigue.get(candidate.semantic_key),
            now=now,
            half_life=self.settings.semantic_half_life_s,
            weight=self.settings.semantic_weight * repeat_weight,
        )
        edge_penalty = 0.0
        if self._previous is not None:
            edge_key = (self._previous.node_id, candidate.node_id)
            edge_repeat_weight = edge.editorial.repeat_weight if edge is not None else 1.0
            edge_penalty = self._penalty(
                self._edge_fatigue.get(edge_key),
                now=now,
                half_life=self.settings.edge_half_life_s,
                weight=self.settings.edge_weight * repeat_weight * edge_repeat_weight,
            )
        path_penalty = sum(
            self._penalty(
                self._path_fatigue.get(path),
                now=now,
                half_life=self.settings.path_half_life_s,
                weight=self.settings.path_weight * repeat_weight,
            )
            for path in self._candidate_paths(candidate.node_id)
        )

        fresh_critical = (
            node.editorial.criticality is Criticality.CRITICAL
            and candidate.event_id not in self._occurrences
        )
        # A new critical occurrence is protected from generic semantic/path
        # suppression, but repeated use of its node still remains observable.
        if fresh_critical:
            semantic_penalty = 0.0
            path_penalty = 0.0

        repeat_penalty = min(
            60.0,
            node_penalty + semantic_penalty + edge_penalty + path_penalty,
        )
        raw = float(node.speak_priority) + transition + closure + material + silence - repeat_penalty
        final = max(raw, self.settings.selection_threshold) if fresh_critical else raw
        return ScoreBreakdown(
            base=float(node.speak_priority),
            transition=transition,
            closure=closure,
            material_change=material,
            silence=silence,
            node_fatigue=-node_penalty,
            semantic_fatigue=-semantic_penalty,
            edge_fatigue=-edge_penalty,
            path_fatigue=-path_penalty,
            repeat_penalty=repeat_penalty,
            final=final,
            critical_floor=fresh_critical,
        )

    def select(
        self,
        candidates: list[GraphCandidate] | tuple[GraphCandidate, ...],
        *,
        now: float,
    ) -> GraphSelection | None:
        ranked: list[GraphSelection] = []
        criticality_rank = {
            Criticality.CRITICAL: 2,
            Criticality.STORY: 1,
            Criticality.CONTEXT: 0,
        }
        for candidate in candidates:
            node = self.graph.nodes.get(candidate.node_id)
            if node is None or candidate.run_epoch != self.run_epoch:
                continue
            ranked.append(GraphSelection(candidate=candidate, score=self.score(candidate, now=now)))
        if not ranked:
            return None
        ranked.sort(
            key=lambda item: (
                -item.score.final,
                -criticality_rank[self.graph.nodes[item.candidate.node_id].editorial.criticality],
                -self.graph.nodes[item.candidate.node_id].speak_priority,
                item.candidate.source_sequence,
                item.candidate.event_id,
                item.candidate.node_id,
            )
        )
        winner = ranked[0]
        if winner.score.final < self.settings.selection_threshold:
            return None
        return winner

    def record_speaking(self, candidate: GraphCandidate, *, now: float) -> bool:
        """Commit one audible occurrence and all traversal fatigue atomically."""
        if candidate.run_epoch != self.run_epoch or candidate.event_id in self._occurrences:
            return False
        node = self.graph.nodes.get(candidate.node_id)
        if node is None:
            return False

        previous = self._previous
        paths = self._candidate_paths(candidate.node_id)
        self._touch(
            self._node_fatigue,
            candidate.node_id,
            now=now,
            half_life=self.settings.node_half_life_s,
            capacity=self.settings.max_node_stats,
        )
        self._touch(
            self._semantic_fatigue,
            candidate.semantic_key,
            now=now,
            half_life=self.settings.semantic_half_life_s,
            capacity=self.settings.max_semantic_stats,
        )
        if previous is not None:
            self._touch(
                self._edge_fatigue,
                (previous.node_id, candidate.node_id),
                now=now,
                half_life=self.settings.edge_half_life_s,
                capacity=self.settings.max_edge_stats,
            )
        for path in paths:
            self._touch(
                self._path_fatigue,
                path,
                now=now,
                half_life=self.settings.path_half_life_s,
                capacity=self.settings.max_path_stats,
            )
        _bounded_put(
            self._semantic_revision,
            candidate.semantic_key,
            candidate.material_revision,
            self.settings.max_semantic_stats,
        )
        _bounded_put(self._occurrences, candidate.event_id, None, self.settings.max_occurrences)

        self._spoken_path.append(candidate.node_id)
        self.current_node_id = candidate.node_id
        self._previous = _PreviousNode(
            node_id=candidate.node_id,
            correlation_id=candidate.correlation_id,
            spoken_at=now,
        )
        self._speaking = True
        return True

    def _matching_edge(self, candidate: GraphCandidate, *, now: float) -> GraphEdge | None:
        previous = self._previous
        if previous is None:
            return None
        gap = max(0.0, now - previous.spoken_at)
        for edge in self.graph.outgoing(previous.node_id):
            if edge.target != candidate.node_id:
                continue
            if edge.same_correlation and previous.correlation_id != candidate.correlation_id:
                continue
            if edge.min_gap_s <= gap <= edge.max_gap_s:
                return edge
        return None

    def _candidate_paths(self, node_id: str) -> tuple[tuple[str, ...], ...]:
        existing = tuple(self._spoken_path)
        paths: list[tuple[str, ...]] = []
        if existing:
            paths.append((existing[-1], node_id))
        if len(existing) >= 2:
            paths.append((existing[-2], existing[-1], node_id))
        return tuple(paths)

    def _silence_bonus(self, node: GraphNode, *, now: float) -> float:
        quiet_s = self.silence_seconds(now)
        soft_s = 0.60 * self.settings.max_silence_s
        progress = (quiet_s - soft_s) / (self.settings.max_silence_s - soft_s)
        bounded_progress = min(1.0, max(0.0, progress))
        return node.editorial.silence_affinity * self.settings.max_silence_bonus * bounded_progress

    def _material_change(self, candidate: GraphCandidate) -> float:
        previous_revision = self._semantic_revision.get(candidate.semantic_key)
        if previous_revision is None or previous_revision == candidate.material_revision:
            return 0.0
        return self.settings.material_change_bonus

    @staticmethod
    def _penalty(
        stat: _FatigueStat | None,
        *,
        now: float,
        half_life: float,
        weight: float,
    ) -> float:
        if stat is None:
            return 0.0
        fatigue = _decayed(stat.value, now - stat.last_at, half_life)
        return weight * math.log2(1.0 + fatigue)

    @staticmethod
    def _touch(
        store: OrderedDict[_K, _FatigueStat],
        key: _K,
        *,
        now: float,
        half_life: float,
        capacity: int,
    ) -> None:
        stat = store.get(key)
        value = 1.0 if stat is None else _decayed(stat.value, now - stat.last_at, half_life) + 1.0
        _bounded_put(store, key, _FatigueStat(value=value, last_at=now), capacity)


def candidate_from_envelope(
    node: GraphNode,
    envelope: EventEnvelope,
    *,
    run_epoch: int,
    story_id: str | None,
    source_revision: int,
) -> GraphCandidate:
    """Build stable semantic identity and material revision from typed policy."""
    semantic, material = _semantic_parts(
        node,
        envelope,
        run_epoch=run_epoch,
        story_id=story_id,
    )
    return GraphCandidate(
        node_id=node.id,
        event_id=envelope.event_id,
        event_type=envelope.event_type,
        story_id=story_id,
        correlation_id=envelope.correlation_id,
        run_epoch=run_epoch,
        source_revision=source_revision,
        semantic_key="|".join(semantic),
        material_revision="|".join(material),
        priority=envelope.priority,
        source_sequence=envelope.sequence,
        envelope=envelope,
    )


def _semantic_parts(
    node: GraphNode,
    envelope: EventEnvelope,
    *,
    run_epoch: int,
    story_id: str | None,
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    metrics = envelope.metrics
    policy = node.editorial.semantic_policy
    base = (str(run_epoch), policy.value)
    target_id = _target_id(envelope)
    hero_id = envelope.subject.car_id or "player"
    semantic: tuple[str, ...]

    if policy is SemanticPolicy.UNIQUE_RESULT:
        semantic = base + (envelope.event_type, envelope.event_id)
    elif policy is SemanticPolicy.POSITION_RESULT:
        old = _metric(metrics, "oldPosition", "old_position", default="?")
        new = _metric(metrics, "newPosition", "new_position", "position", default="?")
        semantic = base + (hero_id, _stable(old), _stable(new))
    elif policy is SemanticPolicy.BATTLE_RELATION:
        relation = envelope.event_type
        relation_epoch = story_id or envelope.correlation_id
        semantic = base + (relation, hero_id, target_id, relation_epoch)
    elif policy is SemanticPolicy.PIT_STORY:
        semantic = base + (story_id or envelope.correlation_id or node.id,)
    elif policy is SemanticPolicy.LAP_RESULT:
        lap = _metric(metrics, "lap", "lapNumber", "lap_number", default="?")
        semantic = base + (envelope.event_type, _stable(lap))
    elif policy is SemanticPolicy.WEATHER_FACT:
        semantic = base + (node.id,)
    elif policy is SemanticPolicy.ONCE_SCOPE:
        semantic = base + (node.id,)
    else:
        fact_kind = _metric(metrics, "fact", "kind", default=envelope.event_type)
        semantic = base + (_stable(fact_kind), target_id)
    material = _material_parts(node, envelope)
    return semantic, material


def _material_parts(node: GraphNode, envelope: EventEnvelope) -> tuple[str, ...]:
    metrics = envelope.metrics
    policy = node.editorial.material_change_policy
    if policy is MaterialChangePolicy.OCCURRENCE:
        return (envelope.event_id,)
    if policy is MaterialChangePolicy.POSITION_CHANGE:
        old = _metric(metrics, "oldPosition", "old_position", default="?")
        new = _metric(metrics, "newPosition", "new_position", "position", default="?")
        return (_stable(old), _stable(new), envelope.phase)
    if policy is MaterialChangePolicy.GAP_INTENSITY:
        return (
            _gap_band(_metric(metrics, "gap", "gapSeconds", "gap_seconds")),
            _trend_band(_metric(metrics, "closingRate", "closing_rate", "trend")),
            envelope.phase,
        )
    if policy is MaterialChangePolicy.STORY_PHASE:
        return (envelope.event_type, envelope.phase)
    if policy is MaterialChangePolicy.LAP_RESULT:
        lap = _metric(metrics, "lap", "lapNumber", "lap_number", default="?")
        return (
            _stable(lap),
            _delta_band(_metric(metrics, "delta", "lapDelta", "lap_delta")),
            _stable(_metric(metrics, "personalBest", "personal_best", default=False)),
        )
    if policy is MaterialChangePolicy.WEATHER_THRESHOLD:
        return (
            _weather_band(_metric(metrics, "trackTemp", "track_temp")),
            _weather_band(_metric(metrics, "airTemp", "air_temp")),
            _weather_band(_metric(metrics, "rain", "rainLevel", "rain_level")),
        )
    if policy is MaterialChangePolicy.ONCE:
        return ("once",)
    return _context_revision(metrics, envelope.phase)


def _target_id(envelope: EventEnvelope) -> str:
    metrics = envelope.metrics
    metric_target = _metric(metrics, "targetCarIdx", "target_car_idx", default=None)
    if metric_target is not None:
        return _stable(metric_target)
    if envelope.target is not None:
        return envelope.target.car_id
    return envelope.subject.car_id or "player"


def _context_revision(metrics: dict[str, Any], phase: str) -> tuple[str, ...]:
    fact = _stable(_metric(metrics, "fact", "kind", default="context"))
    if fact == "gap":
        value = _gap_band(_metric(metrics, "gap", "gapSeconds", "gap_seconds"))
    else:
        value = _stable(
            _metric(
                metrics,
                "position",
                "leaderCarIdx",
                "leader_car_idx",
                "value",
                default="?",
            )
        )
    return (fact, value, phase)


def _metric(metrics: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in metrics:
            return metrics[key]
    return default


def _stable(value: Any) -> str:
    if value is None:
        return "none"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float):
        return f"{value:.3f}"
    if isinstance(value, (str, int)):
        return str(value).strip().lower()
    return type(value).__name__.lower()


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _gap_band(value: Any) -> str:
    gap = _as_float(value)
    if gap is None:
        return "unknown"
    if gap <= 0.35:
        return "side_by_side"
    if gap <= 0.8:
        return "attack"
    if gap <= 1.5:
        return "close"
    if gap <= 3.0:
        return "hunting"
    return "distant"


def _trend_band(value: Any) -> str:
    trend = _as_float(value)
    if trend is None:
        return _stable(value)
    if trend > 0.05:
        return "closing"
    if trend < -0.05:
        return "opening"
    return "steady"


def _delta_band(value: Any) -> str:
    delta = _as_float(value)
    if delta is None:
        return "unknown"
    if delta <= -0.5:
        return "large_gain"
    if delta < -0.05:
        return "gain"
    if delta < 0.05:
        return "even"
    if delta < 0.5:
        return "loss"
    return "large_loss"


def _weather_band(value: Any) -> str:
    number = _as_float(value)
    if number is None:
        return "unknown"
    return str(math.floor(number * 2.0) / 2.0)


def _decayed(value: float, elapsed: float, half_life: float) -> float:
    return value * math.exp(-max(0.0, elapsed) / half_life)


def _bounded_put(
    store: OrderedDict[_K, Any],
    key: _K,
    value: Any,
    capacity: int,
) -> None:
    if key in store:
        del store[key]
    store[key] = value
    while len(store) > capacity:
        store.popitem(last=False)


def _unavailable_score() -> ScoreBreakdown:
    return ScoreBreakdown(
        base=0.0,
        transition=0.0,
        closure=0.0,
        material_change=0.0,
        silence=0.0,
        node_fatigue=0.0,
        semantic_fatigue=0.0,
        edge_fatigue=0.0,
        path_fatigue=0.0,
        repeat_penalty=0.0,
        final=float("-inf"),
        critical_floor=False,
    )
