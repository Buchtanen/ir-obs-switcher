"""Post-arbitration commentary director: envelope → graph node → TTS sink."""

from __future__ import annotations

import logging
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from irswitch.commentary.anti_repeat import (
    DEFAULT_HISTORY_SIZE,
    RecentUtteranceHistory,
    prefer_fresh_candidates,
)
from irswitch.commentary.graph import GraphEdge, GraphNode, SequenceGraph, load_sequence_graph
from irswitch.commentary.slot_format import format_spoken_bindings
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
_SECTOR_SPEAK_EVENTS = frozenset({"SECTOR_SPLIT", "SECTOR_BEST"})
DEFAULT_DECISION_LOG_SIZE = 32


@dataclass(frozen=True)
class SpeakDecision:
    """One explainability row for why commentary spoke or stayed quiet."""

    action: str  # spoken | skipped
    reason: str
    event_type: str = ""
    node_id: str = ""
    emotion: str = ""
    text: str = ""
    at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reason": self.reason,
            "eventType": self.event_type,
            "nodeId": self.node_id,
            "emotion": self.emotion,
            "text": self.text,
            "at": self.at,
        }


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
    decision_log_size: int = DEFAULT_DECISION_LOG_SIZE
    _cooldowns: dict[str, float] = field(default_factory=dict)
    _busy_until: float = 0.0
    _last: _LastSpoken | None = None
    _global_ready_at: float = 0.0
    _decisions: deque[SpeakDecision] = field(default_factory=deque)
    _recent: RecentUtteranceHistory = field(
        default_factory=lambda: RecentUtteranceHistory(size=DEFAULT_HISTORY_SIZE)
    )
    _sector_speaks_by_lap: dict[int, int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        size = max(1, int(self.decision_log_size))
        self._decisions = deque(maxlen=size)
        if not isinstance(self._recent, RecentUtteranceHistory):
            self._recent = RecentUtteranceHistory(size=DEFAULT_HISTORY_SIZE)
        if not isinstance(self._sector_speaks_by_lap, dict):
            self._sector_speaks_by_lap = {}

    @classmethod
    def from_defaults(
        cls,
        settings: CommentarySettings | None = None,
        *,
        language: str = "en",
        sink: TtsSink | None = None,
    ) -> CommentaryDirector:
        cfg = settings or CommentarySettings()
        return cls(
            graph=load_sequence_graph(),
            settings=cfg,
            sink=sink or build_tts_sink(cfg),
            language=normalize_language(language),
            decision_log_size=getattr(cfg, "decision_log_size", DEFAULT_DECISION_LOG_SIZE),
        )

    def reset(self) -> None:
        self._cooldowns.clear()
        self._busy_until = 0.0
        self._last = None
        self._global_ready_at = 0.0
        size = max(1, int(getattr(self.settings, "decision_log_size", self.decision_log_size)))
        self.decision_log_size = size
        self._decisions = deque(maxlen=size)
        self._recent.clear()
        self._sector_speaks_by_lap.clear()

    def decisions(self, n: int = 20) -> list[dict[str, Any]]:
        """Newest-last chronological slice for HTTP/UI."""
        if n <= 0:
            return []
        items = list(self._decisions)[-n:]
        return [item.to_dict() for item in items]

    def _record(
        self,
        *,
        action: str,
        reason: str,
        now: float,
        event_type: str = "",
        node_id: str = "",
        emotion: str = "",
        text: str = "",
    ) -> None:
        self._decisions.append(
            SpeakDecision(
                action=action,
                reason=reason,
                event_type=event_type,
                node_id=node_id,
                emotion=emotion,
                text=text,
                at=now,
            )
        )

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
            if envelopes:
                self._record(action="skipped", reason="disabled", now=now)
            return None
        if language is not None:
            self.language = normalize_language(language)
        if now < self._busy_until:
            if envelopes:
                self._record(action="skipped", reason="busy", now=now)
            return None
        if now < self._global_ready_at:
            if envelopes:
                self._record(action="skipped", reason="global_cooldown", now=now)
            return None

        ranked = sorted(
            (env for env in envelopes if env.phase in _SPEAK_PHASES),
            key=lambda env: env.priority,
            reverse=True,
        )
        if envelopes and not ranked:
            self._record(
                action="skipped",
                reason="no_speak_phase",
                now=now,
                event_type=envelopes[0].event_type,
            )
            return None
        emotion = resolve_emotion(bio, self.settings.use_hr_emotion)
        for envelope in ranked:
            utterance = self._consider(envelope, emotion, now)
            if utterance is not None:
                self.sink.enqueue(utterance)
                self._record(
                    action="spoken",
                    reason="spoken",
                    now=now,
                    event_type=envelope.event_type,
                    node_id=utterance.node_id,
                    emotion=utterance.emotion,
                    text=utterance.text,
                )
                return utterance
        return None

    def _consider(
        self,
        envelope: EventEnvelope,
        emotion: str,
        now: float,
    ) -> CommentaryUtterance | None:
        sector_gate = self._sector_speak_gate(envelope, now)
        if sector_gate is not None:
            return None
        node = self._pick_node(envelope, now)
        if node is None:
            self._record(
                action="skipped",
                reason="no_node",
                now=now,
                event_type=envelope.event_type,
            )
            return None
        if now < self._cooldowns.get(node.id, 0.0):
            self._record(
                action="skipped",
                reason="node_cooldown",
                now=now,
                event_type=envelope.event_type,
                node_id=node.id,
            )
            return None
        resolved = emotion
        if resolved not in node.hr_states and resolved != "unknown":
            if "unknown" not in node.hr_states:
                self._record(
                    action="skipped",
                    reason="hr_gate",
                    now=now,
                    event_type=envelope.event_type,
                    node_id=node.id,
                    emotion=resolved,
                )
                return None
            resolved = "unknown"
        texts = node.variant_bucket(self.language, resolved)
        if not texts:
            self._record(
                action="skipped",
                reason="no_variant",
                now=now,
                event_type=envelope.event_type,
                node_id=node.id,
                emotion=resolved,
            )
            return None
        bindings = slot_bindings(envelope, resolved)
        spoken = choose_filled_line(texts, bindings, self.rng, history=self._recent)
        if spoken is None:
            self._record(
                action="skipped",
                reason="slot_unbound",
                now=now,
                event_type=envelope.event_type,
                node_id=node.id,
                emotion=resolved,
            )
            return None
        issues = validate_utterance(spoken, node)
        if issues:
            logger.info(
                "commentary rejected node=%s codes=%s",
                node.id,
                [item.code for item in issues],
            )
            self._record(
                action="skipped",
                reason="validator_reject",
                now=now,
                event_type=envelope.event_type,
                node_id=node.id,
                emotion=resolved,
                text=spoken,
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
        self._recent.remember(spoken)
        self._note_sector_spoken(envelope)
        return CommentaryUtterance(
            node_id=node.id,
            locale=self.language,
            emotion=resolved,
            text=spoken,
            event_type=envelope.event_type,
            event_id=envelope.event_id,
            correlation_id=envelope.correlation_id,
            estimated_seconds=duration,
            node=node,
        )

    def _sector_speak_gate(self, envelope: EventEnvelope, now: float) -> str | None:
        """Return a skip reason when sector speak must stay silent; else None."""
        if envelope.event_type not in _SECTOR_SPEAK_EVENTS:
            return None
        if not getattr(self.settings, "sector_speak", False):
            self._record(
                action="skipped",
                reason="sector_speak_disabled",
                now=now,
                event_type=envelope.event_type,
            )
            return "sector_speak_disabled"
        if not _sector_envelope_notable(envelope):
            self._record(
                action="skipped",
                reason="sector_not_notable",
                now=now,
                event_type=envelope.event_type,
            )
            return "sector_not_notable"
        lap = _sector_lap(envelope)
        cap = int(getattr(self.settings, "sector_speak_max_per_lap", 1) or 0)
        if cap <= 0 or self._sector_speaks_by_lap.get(lap, 0) >= cap:
            self._record(
                action="skipped",
                reason="sector_lap_cap",
                now=now,
                event_type=envelope.event_type,
            )
            return "sector_lap_cap"
        return None

    def _note_sector_spoken(self, envelope: EventEnvelope) -> None:
        if envelope.event_type not in _SECTOR_SPEAK_EVENTS:
            return
        lap = _sector_lap(envelope)
        self._sector_speaks_by_lap[lap] = self._sector_speaks_by_lap.get(lap, 0) + 1

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
    *,
    history: RecentUtteranceHistory | None = None,
) -> str | None:
    """Pick one fully-bound line; prefer non-recent / under filler-tail quota.

    Leftover ``{slots}`` are skipped. When *history* is set, exact repeats and
    overused shared tails are deprioritized; if every candidate is recent the
    call still returns a bound line (never hard-fails speech forever).
    """
    ready = [fill_slots(text, bindings) for text in texts]
    ready = [line for line in ready if line.strip() and not leftover_slots(line)]
    if not ready:
        return None
    pool = prefer_fresh_candidates(ready, history)
    return rng.choice(pool)


def resolve_emotion(bio: BioState | None, use_hr: bool) -> str:
    if not use_hr or bio is None or not bio.connected:
        return "unknown"
    if bio.state in {"calm", "focused", "pushing", "high"}:
        return bio.state
    return "unknown"


def slot_bindings(envelope: EventEnvelope, emotion: str) -> dict[str, object]:
    """Bind envelope metrics for TTS fill.

    Timing slots (``lap_time``, ``gap``, ``delta``, …) are formatted for speech
    via ``format_spoken_bindings``; sentinels become ``None`` so unbound lines
    are skipped. Wire/envelope metrics stay numeric upstream.
    """
    metrics = envelope.metrics
    subject = envelope.subject
    target = envelope.target
    sector = _spoken_sector_label(_first(metrics, "sector", "timingPointId"))
    raw: dict[str, object] = {
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
        "sector": sector,
        "segment_time": _first(metrics, "segmentTime"),
        "target_time": _first(metrics, "targetTime"),
        "projected_time": _first(metrics, "projectedTime"),
        "confidence": _first(metrics, "confidence"),
        "emotion": emotion,
    }
    return format_spoken_bindings(raw)


def _sector_envelope_notable(envelope: EventEnvelope) -> bool:
    """SECTOR_BEST is always notable; SECTOR_SPLIT needs emitter annotation."""
    if envelope.event_type == "SECTOR_BEST":
        return True
    metrics = envelope.metrics
    if metrics.get("notable") is True:
        return True
    if metrics.get("isBest") is True and metrics.get("delta") is not None:
        try:
            return float(metrics["delta"]) <= -0.05
        except (TypeError, ValueError):
            return False
    return False


def _sector_lap(envelope: EventEnvelope) -> int:
    lap = envelope.metrics.get("lap")
    try:
        return int(lap) if lap is not None else -1
    except (TypeError, ValueError):
        return -1


def _spoken_sector_label(value: object) -> str | None:
    """Keep S1/S2 as a single text slot (not separate graph nodes)."""
    if value is None or value == "":
        return None
    text = str(value).strip().upper()
    if len(text) >= 2 and text[0] == "S" and text[1:].isdigit():
        return text
    return str(value).strip() or None


def _first(metrics: dict[str, object], *keys: str) -> object | None:
    for key in keys:
        if key in metrics and metrics[key] not in (None, ""):
            return metrics[key]
    return None
