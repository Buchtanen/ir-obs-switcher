"""Live StoryDirector world/candidate seed from context facts (#284).

Builds a deterministic ``DirectorSnapshot`` from an APPLY_CONTEXT_BATCH so
``NarrativeRuntime._consult_director`` can call ``StoryDirector.evaluate``
instead of skipping when ``_director_world`` is unset. Not exported from
``events/__init__.py``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from irswitch.contracts.narrative import NarrativeEvent
from irswitch.events.beat_plan import CandidateOrder
from irswitch.events.story_director import (
    DirectorCandidate,
    DirectorWorld,
    EligibilityGates,
    FatigueTerms,
)

DEFAULT_TTL_MS = 10_000
DEFAULT_BASE_PRIORITY = 64.0
CRITICAL_BASE_PRIORITY = 72.0
STORY_CONSECUTIVE_CAP = 3


@dataclass(frozen=True, slots=True)
class DirectorSnapshot:
    world: DirectorWorld
    candidates: tuple[DirectorCandidate, ...]


def _int_field(mapping: Mapping[str, Any], key: str, default: int) -> int:
    value = mapping.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        return default
    return int(value)


def _episode_id_for(event: NarrativeEvent, focused_episode_id: str | None) -> str:
    if focused_episode_id is not None:
        return focused_episode_id
    if event.occurrence_id is not None:
        return f"episode:{event.occurrence_id}"
    return f"episode:{event.kind}"


def _urgency_and_policy(event: NarrativeEvent) -> tuple[str, str, float, bool]:
    phase = str(event.phase)
    delivery = str(event.delivery_class)
    if delivery == "protected" or phase in {"ended", "result"}:
        return "critical", "critical", CRITICAL_BASE_PRIORITY, True
    if phase == "started":
        return "story", "live_story", DEFAULT_BASE_PRIORITY, False
    return "story", "result", DEFAULT_BASE_PRIORITY, False


def _gates_for(event: NarrativeEvent) -> EligibilityGates:
    has_facts = len(event.fact_ids) > 0
    confidence_ok = float(event.confidence) >= 0.5
    return EligibilityGates(
        phase_allowed=True,
        occurrence_current=event.occurrence_id is not None,
        lineage_current=event.lineage_id is not None,
        required_facts_available=has_facts,
        confidence_sufficient=confidence_ok,
        episode_valid=True,
        not_expired=True,
        not_conflicting=True,
        cadence_allowed=True,
        audience_allowed=True,
        source_guard=True,
    )


def candidate_from_event(
    event: NarrativeEvent,
    *,
    reducer_sequence: int,
    source_ordinal: int,
    focused_episode_id: str | None = None,
    ttl_ms: int = DEFAULT_TTL_MS,
) -> DirectorCandidate:
    """Map one NarrativeEvent into an event_opportunity DirectorCandidate."""

    urgency, policy_id, base_priority, is_critical = _urgency_and_policy(event)
    created = int(event.occurred_mono_ms)
    episode_id = _episode_id_for(event, focused_episode_id)
    relation = (
        "continues_focused_episode"
        if focused_episode_id is not None and episode_id == focused_episode_id
        else "independent_of_focused_episode"
    )
    opportunity_id = None
    if event.funnel.opportunity_id is not None:
        opportunity_id = str(event.funnel.opportunity_id)
    elif event.funnel.candidate_id is not None:
        opportunity_id = f"opp:{event.funnel.candidate_id}"
    else:
        opportunity_id = f"opp:{event.event_id}"
    order_seq = reducer_sequence
    order_ord = source_ordinal
    if event.source_order is not None:
        order_seq = int(event.source_order.fanout_stream_sequence)
        order_ord = int(event.source_order.source_ordinal)
    return DirectorCandidate(
        beat_id=str(event.kind),
        episode_id=episode_id,
        episode_revision=max(1, int(event.material_revision) + 1),
        source="event_opportunity",
        relation=relation,
        urgency=urgency,
        policy_id=policy_id,
        tape_channel=str(event.tape_channel),
        candidate_order=CandidateOrder(order_seq, order_ord),
        opportunity_id=opportunity_id,
        base_priority=base_priority,
        continuation_base=None,
        penalty_coefficient=0.8,
        material_band="material" if event.fact_ids else "none",
        preferred_edge=False,
        closure_edge=False,
        unspoken_outcome=False,
        created_mono_ms=created,
        expires_mono_ms=created + max(1, int(ttl_ms)),
        is_closing=str(event.phase) in {"ended", "result"},
        is_critical=is_critical,
        from_accepted_event=True,
        wire_priority=None,
        gates=_gates_for(event),
        fatigue=FatigueTerms(),
    )


def build_director_snapshot(
    *,
    events: Sequence[NarrativeEvent],
    timeline: Mapping[str, Any],
    fact_view: Mapping[str, Any],
    lane: str,
    impulse: str,
    reducer_sequence: int = 0,
    focused_episode_id: str | None = None,
    consecutive_story_beats: int = 0,
    story_consecutive_cap: int = STORY_CONSECUTIVE_CAP,
    incumbent_score: float | None = None,
    incumbent_urgency: str | None = None,
    now_ms: int | None = None,
    ttl_ms: int = DEFAULT_TTL_MS,
) -> DirectorSnapshot:
    """Build world + candidates from a coherent context publication."""

    observed = now_ms if now_ms is not None else _int_field(timeline, "observedMonoMs", 0)
    stream_epoch = _int_field(timeline, "streamEpoch", _int_field(fact_view, "streamEpoch", 1))
    world = DirectorWorld(
        now_ms=int(observed),
        stream_epoch=int(stream_epoch),
        focused_episode_id=focused_episode_id,
        consecutive_story_beats=int(consecutive_story_beats),
        story_consecutive_cap=int(story_consecutive_cap),
        impulse=impulse,
        silence_impulse=impulse in {"silence", "long_silence"},
        lane=lane,
        incumbent_score=incumbent_score,
        incumbent_urgency=incumbent_urgency,
    )
    candidates = tuple(
        candidate_from_event(
            event,
            reducer_sequence=reducer_sequence,
            source_ordinal=index,
            focused_episode_id=focused_episode_id,
            ttl_ms=ttl_ms,
        )
        for index, event in enumerate(events)
    )
    return DirectorSnapshot(world=world, candidates=candidates)


def planning_impulse_for_lane(lane: str) -> str:
    """Impulse token for live context planning given the current speech lane."""

    if lane == "building":
        return "accepted_event"
    return "event"
