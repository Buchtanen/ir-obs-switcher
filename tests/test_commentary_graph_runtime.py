"""Stateful graph scoring: semantic fatigue, paths, critical floor and silence."""

from __future__ import annotations

import pytest

from irswitch.commentary.graph import load_sequence_graph
from irswitch.commentary.graph_runtime import (
    SILENCE_NODE_ID,
    GraphCandidate,
    GraphScoringSettings,
    SequenceGraphRuntime,
    candidate_from_envelope,
)
from irswitch.events.envelope import make_envelope


def _candidate(
    node_id: str,
    *,
    event_id: str,
    event_type: str | None = None,
    sequence: int = 1,
    correlation_id: str = "story:1",
    run_epoch: int = 1,
    phase: str = "RESULT",
    target_id: str = "7",
    metrics: dict[str, object] | None = None,
) -> GraphCandidate:
    graph = load_sequence_graph()
    node = graph.nodes[node_id]
    envelope = make_envelope(
        event_type=event_type or node.event_types[0],
        event_id=event_id,
        sequence=sequence,
        phase=phase,
        mode="RACE",
        correlation_id=correlation_id,
        target={"car_id": target_id, "display_name": "Target"},
        metrics={"runEpoch": run_epoch, **(metrics or {})},
    )
    return candidate_from_envelope(
        node,
        envelope,
        run_epoch=run_epoch,
        story_id=f"story:{run_epoch}:{correlation_id}",
        source_revision=sequence,
    )


def _runtime(*, started_at: float = 0.0, **overrides: object) -> SequenceGraphRuntime:
    settings = GraphScoringSettings(**overrides)
    return SequenceGraphRuntime(load_sequence_graph(), settings=settings, started_at=started_at)


def test_semantic_identity_ignores_wording_and_scoring_does_not_mutate_fatigue() -> None:
    runtime = _runtime()
    runtime.reset(run_epoch=1, now=0.0)
    first = _candidate(
        "hunting",
        event_id="e1",
        phase="ENTER",
        metrics={"gap": 1.4, "closingRate": 0.2, "targetCarIdx": 7},
    )
    rephrased = _candidate(
        "hunting",
        event_id="e2",
        sequence=2,
        phase="ENTER",
        metrics={"gap": 1.3, "closingRate": 0.2, "targetCarIdx": 7},
    )
    assert first.semantic_key == rephrased.semantic_key
    baseline = runtime.score(rephrased, now=1.0).final
    assert runtime.record_speaking(first, now=1.0)
    penalized = runtime.score(rephrased, now=2.0).final
    assert runtime.score(rephrased, now=2.0).final == penalized
    assert penalized < baseline


def test_material_gap_band_change_receives_bonus() -> None:
    runtime = _runtime()
    runtime.reset(run_epoch=1, now=0.0)
    hunting = _candidate(
        "hunting",
        event_id="e1",
        phase="ENTER",
        metrics={"gap": 2.2, "closingRate": 0.2, "targetCarIdx": 7},
    )
    runtime.record_speaking(hunting, now=1.0)
    same_band = _candidate(
        "hunting",
        event_id="e2",
        sequence=2,
        phase="ENTER",
        metrics={"gap": 2.0, "closingRate": 0.2, "targetCarIdx": 7},
    )
    attack_band = _candidate(
        "hunting",
        event_id="e3",
        sequence=3,
        phase="ENTER",
        metrics={"gap": 0.7, "closingRate": 0.2, "targetCarIdx": 7},
    )
    assert same_band.semantic_key == attack_band.semantic_key
    assert runtime.score(same_band, now=2.0).material_change == 0.0
    assert runtime.score(attack_band, now=2.0).material_change > 0.0


def test_different_target_is_a_new_semantic_relation() -> None:
    first = _candidate(
        "hunting",
        event_id="e1",
        phase="ENTER",
        target_id="7",
        metrics={"gap": 1.2, "targetCarIdx": 7},
    )
    other = _candidate(
        "hunting",
        event_id="e2",
        phase="ENTER",
        target_id="9",
        metrics={"gap": 1.2, "targetCarIdx": 9},
    )
    assert first.semantic_key != other.semantic_key


def test_fatigue_decays_with_monotonic_time() -> None:
    runtime = _runtime()
    runtime.reset(run_epoch=1, now=0.0)
    spoken = _candidate("field_fact", event_id="e1", metrics={"fact": "position", "position": 5})
    later = _candidate(
        "field_fact",
        event_id="e2",
        sequence=2,
        metrics={"fact": "position", "position": 5},
    )
    runtime.record_speaking(spoken, now=1.0)
    soon = runtime.score(later, now=2.0)
    recovered = runtime.score(later, now=600.0)
    assert recovered.repeat_penalty < soon.repeat_penalty
    assert recovered.final > soon.final


def test_transition_and_closure_bonus_come_from_graph_edge() -> None:
    runtime = _runtime()
    runtime.reset(run_epoch=1, now=0.0)
    side = _candidate(
        "side_by_side",
        event_id="e1",
        phase="ENTER",
        correlation_id="battle:7",
        metrics={"gap": 0.2, "targetCarIdx": 7},
    )
    overtake = _candidate(
        "overtake",
        event_id="e2",
        sequence=2,
        correlation_id="battle:7",
        metrics={"position": 4, "oldPosition": 5, "newPosition": 4},
    )
    runtime.record_speaking(side, now=1.0)
    runtime.note_completed(now=1.5, run_epoch=1)
    scored = runtime.score(overtake, now=2.0)
    assert scored.transition > 0.0
    assert scored.closure > 0.0


def test_silence_keeps_previous_spoken_node_for_narrative_continuation() -> None:
    runtime = _runtime()
    runtime.reset(run_epoch=1, now=0.0)
    hunting = _candidate(
        "hunting",
        event_id="e1",
        phase="ENTER",
        correlation_id="battle:7",
        metrics={"gap": 1.2, "targetCarIdx": 7},
    )
    side = _candidate(
        "side_by_side",
        event_id="e2",
        sequence=2,
        phase="ENTER",
        correlation_id="battle:7",
        metrics={"gap": 0.2, "targetCarIdx": 7},
    )

    assert runtime.record_speaking(hunting, now=1.0)
    assert runtime.note_completed(now=2.0, run_epoch=1)

    scored = runtime.score(side, now=3.0)
    assert runtime.current_node_id == SILENCE_NODE_ID
    assert runtime.silence_seconds(3.0) == 1.0
    assert scored.transition > 0.0


def test_repeated_short_path_adds_path_fatigue() -> None:
    runtime = _runtime()
    runtime.reset(run_epoch=1, now=0.0)
    hunting = _candidate(
        "hunting",
        event_id="e1",
        phase="ENTER",
        correlation_id="battle:7",
        metrics={"gap": 1.2, "targetCarIdx": 7},
    )
    side = _candidate(
        "side_by_side",
        event_id="e2",
        sequence=2,
        phase="ENTER",
        correlation_id="battle:7",
        metrics={"gap": 0.2, "targetCarIdx": 7},
    )
    runtime.record_speaking(hunting, now=1.0)
    before = runtime.score(side, now=2.0)
    runtime.record_speaking(side, now=2.0)
    runtime.record_speaking(
        _candidate(
            "hunting",
            event_id="e3",
            sequence=3,
            phase="ENTER",
            correlation_id="battle:8",
            target_id="8",
            metrics={"gap": 1.2, "targetCarIdx": 8},
        ),
        now=10.0,
    )
    repeated = runtime.score(
        _candidate(
            "side_by_side",
            event_id="e4",
            sequence=4,
            phase="ENTER",
            correlation_id="battle:8",
            target_id="8",
            metrics={"gap": 0.2, "targetCarIdx": 8},
        ),
        now=11.0,
    )
    assert before.path_fatigue == 0.0
    assert repeated.path_fatigue < 0.0


def test_new_critical_occurrence_keeps_selection_floor_after_fatigue() -> None:
    runtime = _runtime(selection_threshold=45.0)
    runtime.reset(run_epoch=1, now=0.0)
    for index in range(12):
        runtime.record_speaking(
            _candidate(
                "finish",
                event_id=f"finish-{index}",
                sequence=index + 1,
                correlation_id=f"finish:{index}",
                metrics={"position": 5},
            ),
            now=float(index + 1),
        )
    fresh = _candidate(
        "finish",
        event_id="finish-new",
        sequence=20,
        correlation_id="finish:new",
        metrics={"position": 5},
    )
    score = runtime.score(fresh, now=14.0)
    assert score.critical_floor
    assert score.final >= runtime.settings.selection_threshold
    assert runtime.select([fresh], now=14.0) is not None


def test_duplicate_occurrence_is_recorded_only_once() -> None:
    runtime = _runtime()
    runtime.reset(run_epoch=1, now=0.0)
    candidate = _candidate("finish", event_id="finish-1", metrics={"position": 5})
    assert runtime.record_speaking(candidate, now=1.0)
    assert not runtime.record_speaking(candidate, now=2.0)


def test_silence_bonus_starts_at_soft_boundary_and_can_promote_context() -> None:
    runtime = _runtime(max_silence_s=30.0, max_silence_bonus=30.0)
    runtime.reset(run_epoch=1, now=0.0)
    fact = _candidate("field_fact", event_id="field-1", metrics={"fact": "position", "position": 5})
    assert runtime.current_node_id == SILENCE_NODE_ID
    assert runtime.score(fact, now=17.9).silence == 0.0
    assert runtime.select([fact], now=17.9) is None
    assert runtime.score(fact, now=30.0).silence == pytest.approx(30.0)
    assert runtime.select([fact], now=30.0).candidate == fact


def test_silence_starts_after_completion_not_speaking_start() -> None:
    runtime = _runtime(started_at=5.0)
    runtime.reset(run_epoch=1, now=5.0)
    candidate = _candidate("hunting", event_id="e1", phase="ENTER")
    runtime.record_speaking(candidate, now=10.0)
    assert runtime.silence_seconds(20.0) == 0.0
    assert runtime.note_completed(now=20.0, run_epoch=1)
    assert runtime.silence_seconds(25.0) == pytest.approx(5.0)


def test_reset_clears_fatigue_and_rejects_stale_lifecycle() -> None:
    runtime = _runtime()
    runtime.reset(run_epoch=1, now=0.0)
    old = _candidate("field_fact", event_id="e1", metrics={"fact": "position", "position": 5})
    runtime.record_speaking(old, now=1.0)
    assert runtime.fatigue_counts()["semantic"] == 1
    runtime.reset(run_epoch=2, now=10.0)
    assert runtime.fatigue_counts() == {"node": 0, "edge": 0, "semantic": 0, "path": 0}
    assert not runtime.note_completed(now=11.0, run_epoch=1)
    assert runtime.current_node_id == SILENCE_NODE_ID


def test_selection_tie_break_is_stable_by_sequence_then_ids() -> None:
    runtime = _runtime(selection_threshold=0.0)
    runtime.reset(run_epoch=1, now=0.0)
    later = _candidate("gain_found", event_id="b", sequence=2, metrics={"lap": 2, "delta": 0.2})
    earlier = _candidate("time_lost", event_id="a", sequence=1, metrics={"lap": 2, "delta": 0.2})
    assert runtime.score(later, now=1.0).final == runtime.score(earlier, now=1.0).final
    assert runtime.select([later, earlier], now=1.0).candidate == earlier


def test_runtime_stores_are_bounded() -> None:
    runtime = _runtime(max_semantic_stats=2, max_path_stats=2, max_occurrences=2)
    runtime.reset(run_epoch=1, now=0.0)
    for index in range(6):
        runtime.record_speaking(
            _candidate(
                "field_fact",
                event_id=f"e{index}",
                sequence=index + 1,
                correlation_id=f"field:{index}",
                metrics={"fact": "gap", "targetCarIdx": index, "gap": 1.0 + index},
            ),
            now=float(index + 1),
        )
    counts = runtime.fatigue_counts()
    assert counts["semantic"] <= 2
    assert counts["path"] <= 2
    assert runtime.occurrence_count <= 2


def test_empty_or_below_threshold_candidate_set_stays_silent() -> None:
    runtime = _runtime()
    runtime.reset(run_epoch=1, now=0.0)
    assert runtime.select([], now=100.0) is None
    low = _candidate("field_fact", event_id="e1", metrics={"fact": "position", "position": 5})
    assert runtime.select([low], now=1.0) is None


def test_filler_due_uses_initial_silence_and_bounded_no_fact_backoff() -> None:
    runtime = _runtime(max_silence_s=30.0, filler_retry_s=5.0, no_fact_retry_s=10.0)
    runtime.reset(run_epoch=1, now=0.0)

    assert not runtime.filler_due(29.9)
    assert runtime.filler_due(30.0)
    runtime.note_filler_requested(now=30.0)
    assert not runtime.filler_due(34.9)
    assert runtime.filler_due(35.0)
    runtime.note_filler_result(status="no_fact", now=35.0)
    assert not runtime.filler_due(44.9)
    assert runtime.filler_due(45.0)


def test_identical_timeline_is_deterministic_when_candidate_order_changes() -> None:
    def replay(reverse: bool) -> list[tuple[str, float, float, float]]:
        runtime = _runtime(selection_threshold=0.0)
        runtime.reset(run_epoch=1, now=0.0)
        batches = [
            [
                _candidate(
                    "field_fact",
                    event_id="field:1",
                    sequence=2,
                    metrics={"fact": "position", "position": 5},
                ),
                _candidate(
                    "hunting",
                    event_id="hunt:1",
                    sequence=1,
                    phase="ENTER",
                    correlation_id="battle:7",
                    metrics={"gap": 1.2, "targetCarIdx": 7},
                ),
            ],
            [
                _candidate(
                    "side_by_side",
                    event_id="side:1",
                    sequence=4,
                    phase="ENTER",
                    correlation_id="battle:7",
                    metrics={"gap": 0.2, "targetCarIdx": 7},
                ),
                _candidate(
                    "time_lost",
                    event_id="lap:1",
                    sequence=3,
                    metrics={"lap": 4, "delta": 0.3},
                ),
            ],
        ]
        output: list[tuple[str, float, float, float]] = []
        for index, original in enumerate(batches, start=1):
            candidates = list(reversed(original)) if reverse else original
            selection = runtime.select(candidates, now=float(index))
            assert selection is not None
            output.append(
                (
                    selection.candidate.event_id,
                    selection.score.final,
                    selection.score.transition,
                    selection.score.repeat_penalty,
                )
            )
            assert runtime.record_speaking(selection.candidate, now=float(index))
            assert runtime.note_completed(now=float(index) + 0.25, run_epoch=1)
        return output

    assert replay(reverse=False) == replay(reverse=True)
