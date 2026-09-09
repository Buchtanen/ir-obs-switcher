"""StoryDirector hard eligibility and deterministic arbitration (v2 #262).

Not live-wired and not exported from ``events/__init__.py``. Composes snapshot
gates and FatigueTerms. Does not import commentary or overlay packages.
Does not implement the speech lane or emit an utterance.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass

from irswitch.events.beat_plan import GLOBAL_CONSECUTIVE_CAP, CandidateOrder
from irswitch.events.opportunity_queue import URGENCY_RANK

SCHEMA_VERSION = "director-decision/2"
SELECTION_THRESHOLD = 35.0
SWITCH_MARGIN = 8.0
DECISION_CAPACITY = 128
LONG_SILENCE_S = 33.0
SILENCE_PRESSURE_BASE = 12.0
SILENCE_PRESSURE_EXTRA_CAP = 8.0
CONTINUITY_BONUS = 6.0
PREFERRED_EDGE_BONUS = 6.0
CLOSURE_EDGE_BONUS = 8.0
CLOSURE_URGENCY_BONUS = 12.0
MATERIAL_BONUS = {"none": 0.0, "minor": 3.0, "material": 6.0, "major": 10.0}
SEMANTIC_FATIGUE_WEIGHT = 8.0
SEMANTIC_FATIGUE_CAP = 3.0
PATTERN_FATIGUE_WEIGHT = 5.0
PATTERN_FATIGUE_CAP = 2.0
LEXICAL_WEIGHT = 8.0
STALENESS_WEIGHT = 10.0
REPLACEMENT_BASE = 8.0
REPLACEMENT_SPAN = 8.0
FOCUSED_EVENT_RELATIONS = frozenset(
    {
        "updates",
        "resolves",
        "updates_active_episode",
        "resolves_active_episode",
    }
)
HARD_GUARD_FIELDS = (
    "phase_allowed",
    "occurrence_current",
    "lineage_current",
    "required_facts_available",
    "confidence_sufficient",
    "episode_valid",
    "not_expired",
    "not_conflicting",
    "audience_allowed",
)


def _finite(value: float) -> float:
    number = float(value)
    if not math.isfinite(number):
        return 0.0
    return round(number, 10)


def _clamp01(value: float) -> float:
    if value <= 0.0:
        return 0.0
    if value >= 1.0:
        return 1.0
    return value


def _urgency_rank(value: str) -> int:
    return URGENCY_RANK.get(value, 0)


@dataclass(frozen=True, slots=True)
class EligibilityGates:
    phase_allowed: bool = True
    occurrence_current: bool = True
    lineage_current: bool = True
    required_facts_available: bool = True
    confidence_sufficient: bool = True
    episode_valid: bool = True
    not_expired: bool = True
    not_conflicting: bool = True
    cadence_allowed: bool = True
    audience_allowed: bool = True
    source_guard: bool = True


@dataclass(frozen=True, slots=True)
class FatigueTerms:
    semantic: float = 0.0
    pattern: float = 0.0
    lexical_jaccard: float = 0.0
    channel_pressure: float = 0.0


@dataclass(frozen=True, slots=True)
class DirectorCandidate:
    beat_id: str
    episode_id: str
    episode_revision: int
    source: str
    relation: str | None
    urgency: str
    policy_id: str
    tape_channel: str
    candidate_order: CandidateOrder
    opportunity_id: str | None
    base_priority: float
    continuation_base: float | None
    penalty_coefficient: float
    material_band: str
    preferred_edge: bool
    closure_edge: bool
    unspoken_outcome: bool
    created_mono_ms: int
    expires_mono_ms: int
    is_closing: bool
    is_critical: bool
    from_accepted_event: bool
    wire_priority: int | None
    gates: EligibilityGates
    fatigue: FatigueTerms


@dataclass(frozen=True, slots=True)
class DirectorWorld:
    now_ms: int
    stream_epoch: int
    focused_episode_id: str | None
    consecutive_story_beats: int
    story_consecutive_cap: int
    impulse: str
    silence_impulse: bool = False
    silence_extra_s: float = 0.0
    lane: str | None = None
    incumbent_score: float | None = None
    incumbent_urgency: str | None = None
    building_elapsed_ms: int | None = None
    request_timeout_ms: int | None = None


@dataclass(frozen=True, slots=True)
class ScoreTerms:
    base: float
    continuity_bonus: float
    edge_preference: float
    closure_urgency: float
    material_change_bonus: float
    silence_pressure: float
    semantic_fatigue_penalty: float
    pattern_fatigue_penalty: float
    lexical_repetition_penalty: float
    staleness_penalty: float
    replacement_cost: float
    event_penalty: float
    total: float


@dataclass(frozen=True, slots=True)
class CandidateRecord:
    beat_id: str
    episode_id: str
    episode_revision: int
    source: str
    eligible: bool
    reject_reason: str | None
    score: float
    candidate_order: CandidateOrder


@dataclass(frozen=True, slots=True)
class DirectorDecision:
    reason: str
    selected: CandidateRecord | None
    records: tuple[CandidateRecord, ...]
    speech: str
    schema_version: str
    planning_cycle_id: int
    cycle_attempt_ordinal: int


@dataclass(frozen=True, slots=True)
class _Ranked:
    candidate: DirectorCandidate
    record: CandidateRecord
    score: float
    urgency: str


def _continuation_base(candidate: DirectorCandidate) -> float:
    if candidate.continuation_base is None:
        return max(0.0, _finite(candidate.base_priority) - 6.0)
    return _finite(candidate.continuation_base)


def _continuity(candidate: DirectorCandidate, world: DirectorWorld) -> float:
    if world.focused_episode_id is None:
        return 0.0
    if candidate.episode_id != world.focused_episode_id:
        return 0.0
    return CONTINUITY_BONUS


def _edge_preference(candidate: DirectorCandidate) -> float:
    if candidate.closure_edge:
        return CLOSURE_EDGE_BONUS
    if candidate.preferred_edge:
        return PREFERRED_EDGE_BONUS
    return 0.0


def _closure_urgency(candidate: DirectorCandidate) -> float:
    return CLOSURE_URGENCY_BONUS if candidate.unspoken_outcome else 0.0


def _material_bonus(candidate: DirectorCandidate) -> float:
    return MATERIAL_BONUS.get(candidate.material_band, 0.0)


def _silence_pressure(candidate: DirectorCandidate, world: DirectorWorld) -> float:
    if candidate.source != "filler":
        return 0.0
    if not (world.silence_impulse or world.impulse == "silence"):
        return 0.0
    extra = SILENCE_PRESSURE_EXTRA_CAP * _clamp01(world.silence_extra_s / LONG_SILENCE_S)
    return SILENCE_PRESSURE_BASE + extra


def _fatigue_penalties(candidate: DirectorCandidate) -> tuple[float, float, float]:
    semantic = SEMANTIC_FATIGUE_WEIGHT * min(
        SEMANTIC_FATIGUE_CAP, _finite(candidate.fatigue.semantic)
    )
    pattern = PATTERN_FATIGUE_WEIGHT * min(PATTERN_FATIGUE_CAP, _finite(candidate.fatigue.pattern))
    lexical = LEXICAL_WEIGHT * max(0.0, _finite(candidate.fatigue.lexical_jaccard))
    return semantic, pattern, lexical


def _staleness(candidate: DirectorCandidate, world: DirectorWorld) -> float:
    ttl = candidate.expires_mono_ms - candidate.created_mono_ms
    age = world.now_ms - candidate.created_mono_ms
    if ttl <= 0:
        return STALENESS_WEIGHT
    return STALENESS_WEIGHT * _clamp01(age / ttl)


def _replacement_cost(world: DirectorWorld, *, replacing: bool) -> float:
    if not replacing:
        return 0.0
    elapsed = float(world.building_elapsed_ms or 0)
    timeout = float(world.request_timeout_ms or 0)
    ratio = 0.0 if timeout <= 0.0 else _clamp01(elapsed / timeout)
    return REPLACEMENT_BASE + REPLACEMENT_SPAN * ratio


def _event_penalty(candidate: DirectorCandidate) -> float:
    return _finite(
        _finite(candidate.penalty_coefficient) * _finite(candidate.fatigue.channel_pressure)
    )


def _window_open(candidate: DirectorCandidate, world: DirectorWorld) -> bool:
    return candidate.created_mono_ms <= world.now_ms < candidate.expires_mono_ms


def score_terms(
    candidate: DirectorCandidate,
    world: DirectorWorld,
    *,
    replacing: bool,
) -> ScoreTerms:
    continuity = _continuity(candidate, world)
    edge = _edge_preference(candidate)
    closure = _closure_urgency(candidate)
    material = _material_bonus(candidate)
    silence = _silence_pressure(candidate, world)
    semantic, pattern, lexical = _fatigue_penalties(candidate)
    staleness = _staleness(candidate, world)
    replacement = _replacement_cost(world, replacing=replacing)
    event_penalty = _event_penalty(candidate)
    base = _finite(candidate.base_priority)
    raw = (
        base
        + continuity
        + edge
        + closure
        + material
        + silence
        - semantic
        - pattern
        - lexical
        - staleness
        - replacement
    )
    continuation = (
        _continuation_base(candidate)
        + edge
        + material
        + closure
        + continuity
        - semantic
        - pattern
        - lexical
        - staleness
    )
    if candidate.source == "event_opportunity":
        total = raw - event_penalty
    elif candidate.source == "story_successor":
        total = continuation
    else:
        total = raw
    return ScoreTerms(
        base=base,
        continuity_bonus=continuity,
        edge_preference=edge,
        closure_urgency=closure,
        material_change_bonus=material,
        silence_pressure=silence,
        semantic_fatigue_penalty=semantic,
        pattern_fatigue_penalty=pattern,
        lexical_repetition_penalty=lexical,
        staleness_penalty=staleness,
        replacement_cost=replacement,
        event_penalty=event_penalty,
        total=_finite(total),
    )


def effective_score(
    candidate: DirectorCandidate,
    world: DirectorWorld,
    *,
    replacing: bool,
) -> float:
    return score_terms(candidate, world, replacing=replacing).total


def _cadence_blocked(candidate: DirectorCandidate, world: DirectorWorld) -> bool:
    if not candidate.gates.cadence_allowed:
        return True
    if candidate.source != "story_successor":
        return False
    if candidate.is_closing or candidate.is_critical:
        return False
    cap = min(GLOBAL_CONSECUTIVE_CAP, max(0, world.story_consecutive_cap))
    return world.consecutive_story_beats >= cap


def _reject_reason(
    candidate: DirectorCandidate,
    world: DirectorWorld,
    *,
    attempted: set[tuple[str, int]],
    ignore_attempts: bool,
) -> str | None:
    key = (candidate.beat_id, candidate.episode_revision)
    if key in attempted and not ignore_attempts:
        return "attempt_suppressed"
    if not candidate.gates.source_guard:
        return "source_guard_failed"
    if _cadence_blocked(candidate, world):
        return "cadence_blocked"
    if not _window_open(candidate, world):
        return "hard_guard_failed"
    if any(not getattr(candidate.gates, name) for name in HARD_GUARD_FIELDS):
        return "hard_guard_failed"
    return None


def _continues_focused(candidate: DirectorCandidate, world: DirectorWorld) -> bool:
    if world.focused_episode_id is None:
        return False
    if candidate.episode_id != world.focused_episode_id:
        return False
    if candidate.source == "story_successor":
        return True
    return candidate.source == "event_opportunity" and candidate.relation in FOCUSED_EVENT_RELATIONS


def _urgency_score_key(item: _Ranked) -> tuple[int, float, int, int, str, str]:
    order = item.candidate.candidate_order
    return (
        -_urgency_rank(item.urgency),
        -item.score,
        order.reducer_sequence,
        order.source_ordinal,
        item.candidate.episode_id,
        item.candidate.beat_id,
    )


def _score_urgency_key(item: _Ranked) -> tuple[float, int, int, int, str, str]:
    order = item.candidate.candidate_order
    return (
        -item.score,
        -_urgency_rank(item.urgency),
        order.reducer_sequence,
        order.source_ordinal,
        item.candidate.episode_id,
        item.candidate.beat_id,
    )


def _best_urgency(items: Iterable[_Ranked]) -> _Ranked | None:
    ranked = sorted(items, key=_urgency_score_key)
    return ranked[0] if ranked else None


def _best_score(items: Iterable[_Ranked]) -> _Ranked | None:
    ranked = sorted(items, key=_score_urgency_key)
    return ranked[0] if ranked else None


def _story_choice(story: list[_Ranked], world: DirectorWorld) -> tuple[_Ranked | None, str | None]:
    if not story:
        return None, None
    focused = [item for item in story if _continues_focused(item.candidate, world)]
    primary = _best_urgency(focused)
    if primary is None:
        picked = _best_urgency(story)
        return picked, "highest_valid_candidate"
    outsiders = [
        item
        for item in story
        if item is not primary and not _continues_focused(item.candidate, world)
    ]
    higher = [
        item for item in outsiders if _urgency_rank(item.urgency) > _urgency_rank(primary.urgency)
    ]
    if higher:
        return _best_urgency(higher), "higher_urgency_switch"
    margin = [
        item
        for item in outsiders
        if _urgency_rank(item.urgency) <= _urgency_rank(primary.urgency)
        and item.score >= primary.score + SWITCH_MARGIN
    ]
    if margin:
        return _best_score(margin), "switch_margin_met"
    return primary, "active_story_continuation"


def _is_building(world: DirectorWorld) -> bool:
    return world.lane == "building"


def _is_replacement_impulse(world: DirectorWorld) -> bool:
    return _is_building(world) and world.impulse == "accepted_event"


def _replacement_beats_incumbent(item: _Ranked, world: DirectorWorld) -> bool:
    if world.incumbent_score is None:
        return True
    if world.incumbent_urgency is not None:
        if _urgency_rank(item.urgency) > _urgency_rank(world.incumbent_urgency):
            return True
    return item.score >= world.incumbent_score + SWITCH_MARGIN


class StoryDirector:
    """Hard-gate then score a mixed story/filler candidate set."""

    def __init__(self) -> None:
        self._cycle_id = 0
        self._attempt = 0
        self._failures = 0
        self._exhausted = False
        self._attempted: set[tuple[str, int]] = set()

    def note_failure(self, beat_id: str, episode_revision: int) -> None:
        self._attempted.add((beat_id, episode_revision))
        self._failures += 1
        if self._failures >= 2:
            self._exhausted = True

    def evaluate(
        self,
        world: DirectorWorld,
        candidates: Iterable[DirectorCandidate],
    ) -> DirectorDecision:
        replacing = _is_replacement_impulse(world)
        ignore_attempts = replacing
        rows: list[tuple[DirectorCandidate, ScoreTerms, str | None]] = []
        for candidate in tuple(candidates)[:DECISION_CAPACITY]:
            terms = score_terms(candidate, world, replacing=replacing)
            reason = _reject_reason(
                candidate,
                world,
                attempted=self._attempted,
                ignore_attempts=ignore_attempts,
            )
            rows.append((candidate, terms, reason))
        records = tuple(
            CandidateRecord(
                beat_id=candidate.beat_id,
                episode_id=candidate.episode_id,
                episode_revision=candidate.episode_revision,
                source=candidate.source,
                eligible=reason is None,
                reject_reason=reason,
                score=terms.total,
                candidate_order=candidate.candidate_order,
            )
            for candidate, terms, reason in rows
        )
        ranked = [
            _Ranked(candidate, record, record.score, candidate.urgency)
            for (candidate, _terms, reason), record in zip(rows, records, strict=True)
            if reason is None and record.score >= SELECTION_THRESHOLD
        ]
        if self._exhausted and not replacing:
            return self._decision("planning_cycle_exhausted", None, records)
        if _is_building(world) and not replacing:
            return self._decision("incumbent_held", None, records)
        if replacing:
            challengers = [
                item
                for item in ranked
                if item.candidate.source == "event_opportunity"
                and item.candidate.from_accepted_event
                and _replacement_beats_incumbent(item, world)
            ]
            picked, _choice_reason = _story_choice(challengers, world)
            if picked is None:
                return self._decision("incumbent_held", None, records)
            return self._commit(picked.record, "replaced_precommit", records, new_cycle=True)
        story = [item for item in ranked if item.candidate.source != "filler"]
        filler = [item for item in ranked if item.candidate.source == "filler"]
        picked, choice_reason = _story_choice(story, world)
        if picked is not None and choice_reason is not None:
            return self._commit(picked.record, choice_reason, records, new_cycle=False)
        fallback = _best_urgency(filler)
        if fallback is not None:
            return self._commit(
                fallback.record, "highest_valid_candidate", records, new_cycle=False
            )
        if any(record.eligible for record in records):
            return self._decision("below_threshold", None, records)
        return self._decision("no_candidate", None, records)

    def _commit(
        self,
        selected: CandidateRecord,
        reason: str,
        records: tuple[CandidateRecord, ...],
        *,
        new_cycle: bool,
    ) -> DirectorDecision:
        if new_cycle:
            self._cycle_id += 1
            self._attempt = 1
            self._failures = 0
            self._exhausted = False
            self._attempted.clear()
        elif self._cycle_id == 0:
            self._cycle_id = 1
            self._attempt = 1
        elif self._failures > 0:
            self._attempt = 2
        return self._decision(reason, selected, records)

    def _decision(
        self,
        reason: str,
        selected: CandidateRecord | None,
        records: tuple[CandidateRecord, ...],
    ) -> DirectorDecision:
        return DirectorDecision(
            reason=reason,
            selected=selected,
            records=records,
            speech="speak" if selected is not None else "silence",
            schema_version=SCHEMA_VERSION,
            planning_cycle_id=self._cycle_id,
            cycle_attempt_ordinal=self._attempt,
        )
