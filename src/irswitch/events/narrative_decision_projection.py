"""Commentary-runtime/2 decision projection helpers (#273 / #284).

Pure library helpers shared by NarrativeRuntime (decision ring) and the
HTTP mount. Not exported from ``events/__init__.py``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from irswitch.contracts.primitives import ContractViolation
from irswitch.events.story_director import (
    SELECTION_THRESHOLD,
    DirectorCandidate,
    DirectorDecision,
)


def _clamp_decisions_limit(limit: object) -> int:
    if isinstance(limit, bool) or not isinstance(limit, int):
        return 20
    if limit < 1:
        return 1
    if limit > 100:
        return 100
    return limit


def _runner_up_from_decision(decision: DirectorDecision) -> dict[str, Any] | None:
    selected_beat = decision.selected.beat_id if decision.selected is not None else None
    contenders = [
        record for record in decision.records if record.eligible and record.beat_id != selected_beat
    ]
    if not contenders:
        return None
    best = max(
        contenders,
        key=lambda record: (
            record.score,
            -record.candidate_order.reducer_sequence,
            -record.candidate_order.source_ordinal,
            record.beat_id,
        ),
    )
    return {"beatId": best.beat_id, "score": float(best.score)}


def build_runtime_decision_entry(
    decision: DirectorDecision,
    candidates: Sequence[DirectorCandidate],
    *,
    reducer_sequence: int,
    at_mono_ms: int,
    threshold: float = SELECTION_THRESHOLD,
) -> dict[str, Any]:
    """Project one StoryDirector decision into a commentary-runtime/2 decision row."""

    if not isinstance(decision, DirectorDecision):
        raise ContractViolation("decision entry builder requires DirectorDecision")
    by_key = {
        (candidate.beat_id, candidate.candidate_order.key()): candidate for candidate in candidates
    }
    selected = decision.selected
    speaking = selected is not None and decision.speech == "speak"
    if speaking and decision.reason == "replaced_precommit":
        kind = "replaced"
    elif speaking:
        kind = "selected"
    else:
        kind = "silence"

    if not speaking or selected is None:
        return {
            "reducerSequence": int(reducer_sequence),
            "atMonoMs": int(at_mono_ms),
            "decision": kind,
            "reason": str(decision.reason),
            "beatId": None,
            "episodeId": None,
            "opportunityId": None,
            "tapeChannel": None,
            "candidateSource": None,
            "candidateOrder": None,
            "relation": None,
            "urgency": None,
            "score": None,
            "threshold": float(threshold),
            "runnerUp": None,
            "terminalReason": None,
        }

    matched = by_key.get((selected.beat_id, selected.candidate_order.key()))
    return {
        "reducerSequence": int(reducer_sequence),
        "atMonoMs": int(at_mono_ms),
        "decision": kind,
        "reason": str(decision.reason),
        "beatId": selected.beat_id,
        "episodeId": selected.episode_id,
        "opportunityId": None if matched is None else matched.opportunity_id,
        "tapeChannel": None if matched is None else matched.tape_channel,
        "candidateSource": selected.source,
        "candidateOrder": selected.candidate_order.to_dict(),
        "relation": None if matched is None else matched.relation,
        "urgency": None if matched is None else matched.urgency,
        "score": float(selected.score),
        "threshold": float(threshold),
        "runnerUp": _runner_up_from_decision(decision),
        "terminalReason": None,
    }


_TERMINAL_DECISIONS = frozenset({"expired", "discarded", "invalidated"})


def build_terminal_decision_entry(
    *,
    decision: str,
    reason: str,
    terminal_reason: str,
    reducer_sequence: int,
    at_mono_ms: int,
    beat_id: str,
    episode_id: str,
    opportunity_id: str | None,
    tape_channel: str,
    candidate_source: str,
    candidate_order: Mapping[str, int],
    relation: str | None,
    urgency: str,
    score: float = 0.0,
    threshold: float = SELECTION_THRESHOLD,
) -> dict[str, Any]:
    """Project one opportunity-terminal row into a commentary-runtime/2 decision."""

    if decision not in _TERMINAL_DECISIONS:
        raise ContractViolation("terminal decision must be expired|discarded|invalidated")
    if not terminal_reason:
        raise ContractViolation("terminalReason is required for terminal decisions")
    return {
        "reducerSequence": int(reducer_sequence),
        "atMonoMs": int(at_mono_ms),
        "decision": str(decision),
        "reason": str(reason),
        "beatId": str(beat_id),
        "episodeId": str(episode_id),
        "opportunityId": None if opportunity_id is None else str(opportunity_id),
        "tapeChannel": str(tape_channel),
        "candidateSource": str(candidate_source),
        "candidateOrder": {
            "reducerSequence": int(candidate_order["reducerSequence"]),
            "sourceOrdinal": int(candidate_order["sourceOrdinal"]),
        },
        "relation": None if relation is None else str(relation),
        "urgency": str(urgency),
        "score": float(score),
        "threshold": float(threshold),
        "runnerUp": None,
        "terminalReason": str(terminal_reason),
    }


def project_runtime_decisions(
    decisions: Sequence[Mapping[str, Any]],
    *,
    runtime: bool,
    limit: int = 20,
) -> dict[str, Any]:
    """Project newest-first decision rows into commentary-runtime/2 DecisionsResponse.

    HTTP mount: ``GET /api/commentary/runtime/decisions`` (additive; does not
    replace legacy ``GET /api/commentary/decisions``).
    """

    capped = _clamp_decisions_limit(limit)
    rows = [dict(item) for item in decisions[:capped]]
    return {
        "schemaVersion": "commentary-runtime/2",
        "runtime": bool(runtime),
        "decisions": rows,
    }
