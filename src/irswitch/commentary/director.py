"""Post-arbitration commentary director: envelope → graph node → TTS sink."""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field

from irswitch.commentary.graph import GraphEdge, GraphNode, SequenceGraph, load_sequence_graph
from irswitch.commentary.tts import CommentaryUtterance, NullTtsSink, TtsSink, build_tts_sink
from irswitch.commentary.validator import (
    estimate_seconds,
    fill_slots,
    leftover_slots,
    validate_utterance,
)
from irswitch.events.envelope import EventEnvelope
from irswitch.overlay.i18n import normalize_language
from irswitch.overlay.models import BioState
from irswitch.overlay.settings import CommentarySettings

logger = logging.getLogger(__name__)

_SPEAK_PHASES = frozenset({"ENTER", "RESULT", "EXIT"})


@dataclass
class _LastSpoken:
    node_id: str
    correlation_id: str
    at: float


@dataclass
class CommentaryDirector:
    """Selects one graph node after EventManager accepts an envelope.

    Fail-soft: unexpected errors are logged by the caller. Empty variants
    (structure waiting for authored text) produce silence.
    """

    graph: SequenceGraph
    settings: CommentarySettings = field(default_factory=CommentarySettings)
    sink: TtsSink = field(default_factory=NullTtsSink)
    language: str = "en"
    rng: random.Random = field(default_factory=random.Random)
    _cooldowns: dict[str, float] = field(default_factory=dict)
    _busy_until: float = 0.0
    _last: _LastSpoken | None = None
    _global_ready_at: float = 0.0

    @classmethod
    def from_defaults(
        cls,
        settings: CommentarySettings | None = None,
        *,
        language: str = "en",
        sink: TtsSink | None = None,
    ) -> CommentaryDirector:
        return cls(
            graph=load_sequence_graph(),
            settings=settings or CommentarySettings(),
            sink=sink or build_tts_sink(settings or CommentarySettings()),
            language=normalize_language(language),
        )

    def reset(self) -> None:
        self._cooldowns.clear()
        self._busy_until = 0.0
        self._last = None
        self._global_ready_at = 0.0

    def observe(
        self,
        envelopes: list[EventEnvelope],
        bio: BioState | None,
        now: float,
        *,
        enabled: bool | None = None,
        language: str | None = None,
    ) -> CommentaryUtterance | None:
        if not (self.settings.enabled if enabled is None else enabled):
            return None
        if language is not None:
            self.language = normalize_language(language)
        if now < self._busy_until or now < self._global_ready_at:
            return None

        ranked = sorted(
            (env for env in envelopes if env.phase in _SPEAK_PHASES),
            key=lambda env: env.priority,
            reverse=True,
        )
        emotion = resolve_emotion(bio, self.settings.use_hr_emotion)
        for envelope in ranked:
            utterance = self._consider(envelope, emotion, now)
            if utterance is not None:
                self.sink.enqueue(utterance)
                return utterance
        return None

    def _consider(
        self,
        envelope: EventEnvelope,
        emotion: str,
        now: float,
    ) -> CommentaryUtterance | None:
        node = self._pick_node(envelope, now)
        if node is None:
            return None
        if now < self._cooldowns.get(node.id, 0.0):
            return None
        if emotion not in node.hr_states and emotion != "unknown":
            if "unknown" not in node.hr_states:
                return None
            emotion = "unknown"
        texts = node.variant_bucket(self.language, emotion)
        if not texts:
            return None
        bindings = slot_bindings(envelope, emotion)
        spoken = choose_filled_line(texts, bindings, self.rng)
        if spoken is None:
            return None
        issues = validate_utterance(spoken, node)
        if issues:
            logger.info(
                "commentary rejected node=%s codes=%s",
                node.id,
                [item.code for item in issues],
            )
            return None
        duration = min(
            node.tts.max_seconds,
            max(estimate_seconds(spoken, ssml=spoken if "<" in spoken else None), 0.6),
        )
        self._cooldowns[node.id] = now + node.cooldown_s
        self._busy_until = now + duration
        self._global_ready_at = now + self.settings.cooldown_s
        self._last = _LastSpoken(node.id, envelope.correlation_id, now)
        return CommentaryUtterance(
            node_id=node.id,
            locale=self.language,
            emotion=emotion,
            text=spoken,
            event_type=envelope.event_type,
            event_id=envelope.event_id,
            correlation_id=envelope.correlation_id,
            estimated_seconds=duration,
            node=node,
        )

    def _pick_node(self, envelope: EventEnvelope, now: float) -> GraphNode | None:
        candidates = self.graph.nodes_for(envelope.event_type, envelope.phase)
        if not candidates:
            return None
        if self._last is not None:
            followed = self._follow_edge(candidates, envelope, now)
            if followed is not None:
                return followed
        return candidates[0]

    def _follow_edge(
        self,
        candidates: list[GraphNode],
        envelope: EventEnvelope,
        now: float,
    ) -> GraphNode | None:
        last = self._last
        if last is None:
            return None
        wanted = {node.id: node for node in candidates}
        gap = now - last.at
        for edge in self.graph.outgoing(last.node_id):
            node = wanted.get(edge.target)
            if node is None:
                continue
            if not _edge_matches(edge, last.correlation_id, envelope.correlation_id, gap):
                continue
            return node
        return None


def _edge_matches(edge: GraphEdge, last_corr: str, incoming_corr: str, gap: float) -> bool:
    if gap < edge.min_gap_s or gap > edge.max_gap_s:
        return False
    if edge.same_correlation and last_corr and incoming_corr and last_corr != incoming_corr:
        return False
    return True


def choose_filled_line(
    texts: tuple[str, ...],
    bindings: dict[str, object],
    rng: random.Random,
) -> str | None:
    """Pick one fully-bound line at random. Leftover {slots} are skipped."""
    ready = [fill_slots(text, bindings) for text in texts]
    ready = [line for line in ready if line.strip() and not leftover_slots(line)]
    if not ready:
        return None
    return rng.choice(ready)


def resolve_emotion(bio: BioState | None, use_hr: bool) -> str:
    if not use_hr or bio is None or not bio.connected:
        return "unknown"
    if bio.state in {"calm", "focused", "pushing", "high"}:
        return bio.state
    return "unknown"


def slot_bindings(envelope: EventEnvelope, emotion: str) -> dict[str, object]:
    metrics = envelope.metrics
    subject = envelope.subject
    target = envelope.target
    return {
        "position": _first(metrics, "newPosition", "position", "classPosition")
        or subject.class_position,
        "old_position": _first(metrics, "oldPosition"),
        "target_name": (target.display_name if target is not None else None)
        or _first(metrics, "targetName"),
        "lap": _first(metrics, "lap"),
        "lap_time": _first(metrics, "lapTime"),
        "delta": _first(metrics, "delta", "deltaToBest"),
        "gap": _first(metrics, "gap"),
        "bpm": _first(metrics, "bpm"),
        "streak": _first(metrics, "streak"),
        "value": _first(metrics, "value"),
        "segment": _first(metrics, "timingPointId", "segment"),
        "target_time": _first(metrics, "targetTime"),
        "projected_time": _first(metrics, "projectedTime"),
        "confidence": _first(metrics, "confidence"),
        "emotion": emotion,
    }


def _first(metrics: dict[str, object], *keys: str) -> object | None:
    for key in keys:
        if key in metrics and metrics[key] not in (None, ""):
            return metrics[key]
    return None
