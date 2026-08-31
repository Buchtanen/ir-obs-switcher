"""Post-arbitration commentary director: envelope → graph node → TTS sink."""

from __future__ import annotations

import logging
import random
from collections import deque
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from irswitch.commentary.anti_repeat import (
    DEFAULT_HISTORY_SIZE,
    RecentUtteranceHistory,
    prefer_fresh_candidates,
)
from irswitch.commentary.graph import (
    GraphEdge,
    GraphNode,
    SequenceGraph,
    load_sequence_graph,
    normalize_graph_mode,
)
from irswitch.commentary.opener import OPENER_EVENTS, STREAM_START, OpenerMutex
from irswitch.commentary.scheduler import SpeechScheduler
from irswitch.commentary.slot_format import format_spoken_bindings
from irswitch.commentary.speech_hero import mix_hero_name, resolve_hero_names
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
from irswitch.overlay.settings import CommentarySchedulerSettings, CommentarySettings

logger = logging.getLogger(__name__)

_SPEAK_PHASES = frozenset({"ENTER", "RESULT", "EXIT"})
_SECTOR_SPEAK_EVENTS = frozenset({"SECTOR_SPLIT", "SECTOR_BEST"})
_GAP_HUNT_EVENTS = frozenset({"HUNTING", "HUNTED"})
_INCIDENT_PAIR_EVENTS = frozenset({"INCIDENT", "INCIDENT_AFTERMATH"})
_SESSION_BRIEF_EVENTS = frozenset(
    {
        "SESSION_INTRO_PRACTICE",
        "SESSION_INTRO_QUALIFY",
        "SESSION_INTRO_RACE",
        "SOF_BRIEF",
        "WEATHER_BRIEF",
        "SESSION_WRAP",
        "SESSION_PREVIEW",
        "SESSION_CHECKERED",
    }
)
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
    _scheduler: SpeechScheduler = field(default_factory=SpeechScheduler)
    _current_event_type: str | None = None
    filler_provider: Callable[[float], EventEnvelope | None] | None = None
    filler_formatter: Callable[[EventEnvelope], str | None] | None = None
    _iracing_hero_names: tuple[str, ...] = field(default_factory=tuple)
    opener: OpenerMutex = field(default_factory=OpenerMutex)

    def __post_init__(self) -> None:
        size = max(1, int(self.decision_log_size))
        self._decisions = deque(maxlen=size)
        if not isinstance(self._recent, RecentUtteranceHistory):
            self._recent = RecentUtteranceHistory(size=DEFAULT_HISTORY_SIZE)
        if not isinstance(self._sector_speaks_by_lap, dict):
            self._sector_speaks_by_lap = {}
        if not isinstance(self._iracing_hero_names, tuple):
            self._iracing_hero_names = tuple(self._iracing_hero_names or ())
        self._sync_scheduler_settings()

    def note_hero_names(self, names: Sequence[str] | None) -> None:
        """iRacing-derived first/last tokens; config override still wins at mix time."""
        cleaned: list[str] = []
        for raw in names or ():
            token = str(raw).strip() if raw else ""
            if token and token not in cleaned:
                cleaned.append(token)
        self._iracing_hero_names = tuple(cleaned)

    def hero_names(self) -> tuple[str, ...]:
        cfg = self.settings
        return resolve_hero_names(
            driver_name=getattr(cfg, "driver_name", "") or "",
            driver_nickname=getattr(cfg, "driver_nickname", "") or "",
            iracing_names=self._iracing_hero_names,
        )

    def _apply_hero_mix(self, text: str) -> tuple[str, tuple[str, ...], str | None]:
        names = self.hero_names()
        mixed = mix_hero_name(text, names, self.language, rng=self.rng)
        chosen = None
        for token in names:
            if token and token in mixed:
                chosen = token
                break
        return mixed, names, chosen

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
        self._scheduler.reset()
        self._current_event_type = None
        self.opener.reset()
        self._sync_scheduler_settings()

    def status_snapshot(self, now: float, *, enabled: bool | None = None) -> dict[str, Any]:
        """Public read-only status for dashboards. No side effects.

        ``now`` and ``lastSpokeAt`` / ``busyUntil`` are **monotonic** seconds
        (same clock as :meth:`observe`), not wall clock. Pass ``enabled`` when
        the caller holds fresher config than :attr:`settings`.
        """
        enabled_flag = bool(self.settings.enabled if enabled is None else enabled)
        available = bool(getattr(self.graph, "nodes", None))
        busy_until = float(self._busy_until)
        busy = self._is_busy(now)
        if not enabled_flag:
            status = "disabled"
        elif not available:
            status = "idle"
        elif busy:
            status = "speaking"
        else:
            status = "ready"
        return {
            "enabled": enabled_flag,
            "available": available,
            "busy": busy,
            "busyUntil": busy_until,
            "status": status,
            "lastSpokeAt": self._last.at if self._last is not None else None,
        }

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

    def _sync_scheduler_settings(self) -> None:
        sched = getattr(self.settings, "scheduler", None)
        if isinstance(sched, CommentarySchedulerSettings):
            self._scheduler.settings = sched
        else:
            self._scheduler.settings = CommentarySchedulerSettings()

    def tick(self, now: float, bio: BioState | None = None) -> CommentaryUtterance | None:
        """Idle flush / silence watchdog. Call once per race frame when enabled."""
        if not self.settings.enabled:
            return None
        if not self._scheduler.settings.defer_enabled:
            return None
        self._sync_scheduler_settings()
        for expired in self._scheduler.expire(now):
            self._record(
                action="skipped",
                reason="deferred_expired",
                now=now,
                event_type=expired.utterance.event_type,
                node_id=expired.utterance.node_id,
                text=expired.utterance.text,
            )
        if now < self._busy_until or now < self._global_ready_at or self._sink_busy():
            return None
        deferred = self._scheduler.pop_ready(now)
        if deferred is not None:
            # Speak only the best deferred line; drop the rest (never drain queue).
            for dropped in self._scheduler.clear():
                self._record(
                    action="skipped",
                    reason="deferred_dropped",
                    now=now,
                    event_type=dropped.utterance.event_type,
                    node_id=dropped.utterance.node_id,
                    text=dropped.utterance.text,
                )
            return self._speak_prepared(
                deferred.utterance,
                now=now,
                reason="spoken_deferred",
                past=True,
            )
        last_at = self._last.at if self._last is not None else None
        if self._scheduler.silence_due(last_spoke_at=last_at, now=now):
            spoken = self._speak_silence_filler(now)
            if spoken is not None:
                return spoken
            self._record(action="skipped", reason="silence_no_filler", now=now)
        return None

    def _speak_silence_filler(self, now: float) -> CommentaryUtterance | None:
        provider = self.filler_provider
        if provider is None:
            return None
        try:
            envelope = provider(now)
        except Exception:
            logger.warning("filler_provider failed", exc_info=True)
            return None
        if envelope is None:
            return None
        # Prefer graph node when authored; else template formatter from RaceObserver.
        emotion = "unknown"
        drafted = self._consider(envelope, emotion, now, commit=False)
        if drafted is not None:
            return self._speak_prepared(drafted, now=now, reason="silence_fill", past=False)
        return None

    def _utterance_from_formatter(self, envelope: EventEnvelope) -> CommentaryUtterance | None:
        """Build a one-off utterance when the graph has no matching node."""
        formatter = self.filler_formatter
        if formatter is None:
            return None
        try:
            text = formatter(envelope)
        except Exception:
            logger.warning("filler_formatter failed", exc_info=True)
            return None
        if not text:
            return None
        text, hero_names, hero_name = self._apply_hero_mix(text)
        from irswitch.commentary.graph import GraphNode, TtsLimits

        node = GraphNode(
            id=f"fmt:{envelope.event_type.lower()}",
            family="session",
            event_types=(envelope.event_type,),
            phases=("RESULT",),
            speak_priority=int(envelope.priority),
            cooldown_s=8.0,
            slots=(),
            hr_states=("unknown",),
            tts=TtsLimits(),
            variants={},
        )
        return CommentaryUtterance(
            node_id=node.id,
            locale=self.language,
            emotion="unknown",
            text=text,
            event_type=envelope.event_type,
            event_id=envelope.event_id,
            correlation_id=envelope.correlation_id,
            estimated_seconds=min(node.tts.max_seconds, max(0.8, len(text.split()) * 0.35)),
            node=node,
            priority=int(envelope.priority),
            past_framing=False,
            hero_names=hero_names,
            hero_name=hero_name,
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
        self._sync_scheduler_settings()
        if language is not None:
            self.language = normalize_language(language)

        flushed = self.tick(now, bio)
        if flushed is not None and not envelopes:
            return flushed

        ranked = sorted(
            (env for env in envelopes if env.phase in _SPEAK_PHASES),
            key=lambda env: env.priority,
            reverse=True,
        )
        ranked = _prefer_incident_over_aftermath(ranked)
        if envelopes and not ranked:
            self._record(
                action="skipped",
                reason="no_speak_phase",
                now=now,
                event_type=envelopes[0].event_type,
            )
            return None

        busy = self._is_busy(now)
        if busy and ranked:
            top = ranked[0]
            if self._scheduler.should_hard_interrupt(
                top.event_type, current_event_type=self._current_event_type
            ):
                self._hard_interrupt(now)
                busy = False
            elif self._scheduler.settings.defer_enabled:
                return self._park_ranked(ranked, bio, now)
            else:
                self._record(
                    action="skipped",
                    reason="busy",
                    now=now,
                    event_type=top.event_type,
                )
                return None

        if now < self._global_ready_at:
            if envelopes:
                self._record(
                    action="skipped",
                    reason="global_cooldown",
                    now=now,
                    event_type=ranked[0].event_type if ranked else "",
                )
            return flushed

        if flushed is not None:
            # Already spoke a deferred line this tick; park new arrivals if any.
            if ranked and self._scheduler.settings.defer_enabled:
                self._park_ranked(ranked, bio, now)
            return flushed

        emotion = resolve_emotion(bio, self.settings.use_hr_emotion)
        for envelope in ranked:
            utterance = self._consider(envelope, emotion, now, commit=True)
            if utterance is not None:
                return self._speak_prepared(utterance, now=now, reason="spoken", past=False)
        return None

    def _is_busy(self, now: float) -> bool:
        """Estimate busy OR sink still speaking/waiting (#180)."""
        return now < self._busy_until or self._sink_busy()

    def _sink_busy(self) -> bool:
        probe = getattr(self.sink, "is_busy", None)
        if callable(probe):
            try:
                return bool(probe())
            except Exception:
                logger.debug("tts is_busy probe failed", exc_info=True)
                return False
        pending = getattr(self.sink, "pending_count", None)
        if callable(pending):
            try:
                return int(pending()) > 0
            except Exception:
                logger.debug("tts pending_count probe failed", exc_info=True)
        return False

    def _hard_interrupt(self, now: float) -> None:
        interrupt = getattr(self.sink, "interrupt", None)
        if callable(interrupt):
            try:
                interrupt()
            except Exception:
                logger.warning("tts interrupt failed", exc_info=True)
        self._busy_until = now
        self._global_ready_at = now
        self._record(action="skipped", reason="interrupted", now=now)

    def _park_ranked(
        self,
        ranked: list[EventEnvelope],
        bio: BioState | None,
        now: float,
    ) -> CommentaryUtterance | None:
        emotion = resolve_emotion(bio, self.settings.use_hr_emotion)
        for envelope in ranked:
            draft = self._consider(envelope, emotion, now, commit=False)
            if draft is None:
                continue
            ok = self._scheduler.park(draft, priority=envelope.priority, now=now)
            self._record(
                action="skipped",
                reason="deferred" if ok else "deferred_dropped",
                now=now,
                event_type=envelope.event_type,
                node_id=draft.node_id,
                text=draft.text,
            )
            return None
        self._record(
            action="skipped",
            reason="busy",
            now=now,
            event_type=ranked[0].event_type if ranked else "",
        )
        return None

    def _speak_prepared(
        self,
        utterance: CommentaryUtterance,
        *,
        now: float,
        reason: str,
        past: bool,
    ) -> CommentaryUtterance:
        spoken = utterance
        if past and utterance.past_framing is False:
            spoken = CommentaryUtterance(
                node_id=utterance.node_id,
                locale=utterance.locale,
                emotion=utterance.emotion,
                text=utterance.text,
                event_type=utterance.event_type,
                event_id=utterance.event_id,
                correlation_id=utterance.correlation_id,
                estimated_seconds=utterance.estimated_seconds,
                node=utterance.node,
                priority=utterance.priority,
                past_framing=True,
                hero_names=utterance.hero_names,
                hero_name=utterance.hero_name,
            )
        # Commit timing if this was a draft (deferred path).
        duration = spoken.estimated_seconds
        self._cooldowns[spoken.node_id] = now + spoken.node.cooldown_s
        self._busy_until = now + duration
        self._global_ready_at = now + self.settings.cooldown_s
        self._last = _LastSpoken(spoken.node_id, spoken.correlation_id, now)
        self._current_event_type = spoken.event_type
        if spoken.event_type in OPENER_EVENTS:
            self.opener.note(spoken.event_type, now)
        self._recent.remember(spoken.text)
        self.sink.enqueue(spoken)
        self._record(
            action="spoken",
            reason=reason,
            now=now,
            event_type=spoken.event_type,
            node_id=spoken.node_id,
            emotion=spoken.emotion,
            text=spoken.text,
        )
        return spoken

    def _consider(
        self,
        envelope: EventEnvelope,
        emotion: str,
        now: float,
        *,
        commit: bool = True,
    ) -> CommentaryUtterance | None:
        sector_gate = self._sector_speak_gate(envelope, now)
        if sector_gate is not None:
            return None
        hunt_gate = self._gap_hunt_tts_gate(envelope, now)
        if hunt_gate is not None:
            return None
        briefs_gate = self._session_briefs_gate(envelope, now)
        if briefs_gate is not None:
            return None
        opener_gate = self._opener_gate(envelope, now)
        if opener_gate is not None:
            return None
        pair_gate = self._incident_pair_gate(envelope, now)
        if pair_gate is not None:
            return None
        node = self._pick_node(envelope, now)
        if node is None:
            synthetic = self._utterance_from_formatter(envelope)
            if synthetic is None:
                self._record(
                    action="skipped",
                    reason="no_node",
                    now=now,
                    event_type=envelope.event_type,
                )
                return None
            return synthetic
        if commit and now < self._cooldowns.get(node.id, 0.0):
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
        bindings = slot_bindings(envelope, resolved, language=self.language)
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
        spoken, hero_names, hero_name = self._apply_hero_mix(spoken)
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
        if commit:
            self._cooldowns[node.id] = now + node.cooldown_s
            self._busy_until = now + duration
            self._global_ready_at = now + self.settings.cooldown_s
            self._last = _LastSpoken(node.id, envelope.correlation_id, now)
            self._recent.remember(spoken)
            self._note_sector_spoken(envelope)
            self._current_event_type = envelope.event_type
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
            priority=int(envelope.priority),
            past_framing=False,
            hero_names=hero_names,
            hero_name=hero_name,
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

    def _gap_hunt_tts_gate(self, envelope: EventEnvelope, now: float) -> str | None:
        """Mute gap-hunt TTS in P/Q unless the commentary flags are on. HUD may still hunt."""
        if envelope.event_type not in _GAP_HUNT_EVENTS:
            return None
        mode = normalize_graph_mode(envelope.mode)
        allowed = True
        if mode == "practice":
            allowed = bool(getattr(self.settings, "gap_hunt_tts_in_practice", False))
        elif mode == "qualify":
            allowed = bool(getattr(self.settings, "gap_hunt_tts_in_qualifying", False))
        if allowed:
            return None
        self._record(
            action="skipped",
            reason="gap_hunt_tts_disabled",
            now=now,
            event_type=envelope.event_type,
        )
        return "gap_hunt_tts_disabled"

    def _session_briefs_gate(self, envelope: EventEnvelope, now: float) -> str | None:
        """Return a skip reason when session briefs stay silent; else None."""
        if envelope.event_type not in _SESSION_BRIEF_EVENTS:
            return None
        if not getattr(self.settings, "session_briefs", False):
            self._record(
                action="skipped",
                reason="session_briefs_disabled",
                now=now,
                event_type=envelope.event_type,
            )
            return "session_briefs_disabled"
        return None

    def _incident_pair_gate(self, envelope: EventEnvelope, now: float) -> str | None:
        """At most one of INCIDENT / INCIDENT_AFTERMATH per tick. Prefer INCIDENT."""
        if envelope.event_type not in _INCIDENT_PAIR_EVENTS:
            return None
        last = self._last
        last_type = self._current_event_type
        if last is None or last_type not in _INCIDENT_PAIR_EVENTS:
            return None
        if last.at != now:
            return None
        if last_type == envelope.event_type:
            return None
        self._record(
            action="skipped",
            reason="incident_pair",
            now=now,
            event_type=envelope.event_type,
        )
        return "incident_pair"

    def _opener_gate(self, envelope: EventEnvelope, now: float) -> str | None:
        if envelope.event_type == STREAM_START:
            self.opener.note(STREAM_START, now)
            return None
        reason = self.opener.skip_reason(envelope.event_type, now)
        if reason is None:
            return None
        self._record(
            action="skipped",
            reason=reason,
            now=now,
            event_type=envelope.event_type,
        )
        return reason

    def _note_sector_spoken(self, envelope: EventEnvelope) -> None:
        if envelope.event_type not in _SECTOR_SPEAK_EVENTS:
            return
        lap = _sector_lap(envelope)
        self._sector_speaks_by_lap[lap] = self._sector_speaks_by_lap.get(lap, 0) + 1

    def _pick_node(self, envelope: EventEnvelope, now: float) -> GraphNode | None:
        metrics = envelope.metrics if isinstance(envelope.metrics, dict) else {}
        branch = metrics.get("branch")
        candidates = self.graph.nodes_for(
            envelope.event_type,
            envelope.phase,
            mode=envelope.mode,
            branch=str(branch) if branch is not None else None,
        )
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


def _prefer_incident_over_aftermath(ranked: list[EventEnvelope]) -> list[EventEnvelope]:
    """Same-tick list: drop INCIDENT_AFTERMATH when INCIDENT is also ranked."""
    types = {env.event_type for env in ranked}
    if "INCIDENT" in types and "INCIDENT_AFTERMATH" in types:
        return [env for env in ranked if env.event_type != "INCIDENT_AFTERMATH"]
    return ranked


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


def slot_bindings(
    envelope: EventEnvelope,
    emotion: str,
    *,
    language: str = "en",
) -> dict[str, object]:
    """Bind envelope metrics for TTS fill.

    Timing slots (``lap_time``, ``gap``, ``delta``, …) are formatted for speech
    via ``format_spoken_bindings``; sentinels become ``None`` so unbound lines
    are skipped. Wire/envelope metrics stay numeric upstream.

    Observer/narrative extras (``mode``, ``kind``, ``leader_name``) are localized
    when *language* starts with ``cs``.
    """
    metrics = envelope.metrics
    subject = envelope.subject
    target = envelope.target
    sector = _spoken_sector_label(_first(metrics, "sector", "timingPointId"))
    cs = language.lower().startswith("cs")
    if cs:
        mode = _first(metrics, "modeLabelCs", "modeLabel", "mode")
    else:
        mode = _first(metrics, "modeLabel", "mode")
    raw: dict[str, object] = {
        "position": _first(metrics, "newPosition", "position", "classPosition")
        or subject.class_position,
        "old_position": _first(metrics, "oldPosition"),
        "target_name": (target.display_name if target is not None else None)
        or _first(metrics, "targetName", "target_name"),
        "leader_name": _first(metrics, "leaderName", "leader", "leader_name"),
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
        # W4/H4 session briefs (pre-formatted labels from sidecar emitters).
        "track": _first(metrics, "track"),
        "field_size": _first(metrics, "field_size", "fieldSize"),
        "sof": _first(metrics, "sof"),
        "sof_class": _first(metrics, "sof_class", "sofClass"),
        "skies": _first(metrics, "skies"),
        "air_temp": _first(metrics, "air_temp", "airTemp"),
        "track_temp": _first(metrics, "track_temp", "trackTemp"),
        "wind_speed": _first(metrics, "wind_speed", "windSpeed"),
        "precipitation": _first(metrics, "precipitation"),
        # P3/P4 observer narrative + aftermath (graph nodes).
        "mode": mode,
        "kind": _spoken_kind(_first(metrics, "kind"), cs=cs),
        "fact": _first(metrics, "fact"),
    }
    return format_spoken_bindings(raw)


def _spoken_kind(value: object, *, cs: bool) -> str | None:
    """Map aftermath/narrative kind codes to short spoken phrases."""
    if value is None or value == "":
        return None
    key = str(value).strip().lower()
    if cs:
        mapping = {
            "stalled": "stojí",
            "rolling": "stále v pohybu",
            "back_under_way": "znovu jede",
            "session_wrap": "konec",
            "session_preview": "další",
            "session_checkered": "šachovnice",
            "weather_change": "počasí",
            "field_fact": "pole",
        }
    else:
        mapping = {
            "stalled": "stalled",
            "rolling": "still rolling",
            "back_under_way": "back under way",
            "session_wrap": "wrap",
            "session_preview": "preview",
            "session_checkered": "checkered",
            "weather_change": "weather",
            "field_fact": "field",
        }
    return mapping.get(key, str(value).strip())


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
