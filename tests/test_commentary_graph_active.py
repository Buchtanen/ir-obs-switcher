"""Active graph selection integration without TTS worker timing."""

from __future__ import annotations

from irswitch.commentary.director import CommentaryDirector
from irswitch.commentary.graph import load_sequence_graph
from irswitch.commentary.graph_runtime import GraphScoringSettings, SequenceGraphRuntime
from irswitch.commentary.tts import NullTtsSink
from irswitch.events.envelope import EventEnvelope, make_envelope
from irswitch.overlay.settings import CommentarySettings


def _director(**score_overrides: float) -> tuple[CommentaryDirector, SequenceGraphRuntime]:
    graph = load_sequence_graph()
    settings = CommentarySettings(
        enabled=True,
        cooldown_s=0.0,
        use_hr_emotion=False,
        graph_runtime_mode="active",
    )
    director = CommentaryDirector(graph=graph, settings=settings, sink=NullTtsSink())
    runtime = SequenceGraphRuntime(
        graph,
        settings=GraphScoringSettings(**score_overrides),
        started_at=0.0,
    )
    runtime.reset(run_epoch=0, now=0.0)
    director.graph_runtime = runtime
    return director, runtime


def _hunting(event_id: str, *, priority: int = 1, target: int = 7) -> EventEnvelope:
    return make_envelope(
        event_type="HUNTING",
        event_id=event_id,
        sequence=int(event_id.rsplit(":", 1)[-1]),
        phase="ENTER",
        mode="RACE",
        priority=priority,
        correlation_id=f"battle:{target}",
        target={"car_id": str(target), "display_name": "Rossi"},
        metrics={"gap": 1.2, "targetCarIdx": target, "position": 5},
    )


def _field_fact(event_id: str, *, priority: int = 99) -> EventEnvelope:
    return make_envelope(
        event_type="FIELD_FACT",
        event_id=event_id,
        sequence=int(event_id.rsplit(":", 1)[-1]),
        phase="RESULT",
        mode="RACE",
        priority=priority,
        correlation_id="field:position",
        metrics={"fact": "position", "position": 5},
    )


def test_active_graph_uses_editorial_score_instead_of_envelope_priority() -> None:
    director, _runtime = _director()

    spoken = director.observe(
        [_field_fact("event:1", priority=99), _hunting("event:2", priority=1)],
        None,
        1.0,
    )

    assert spoken is not None
    assert spoken.event_type == "HUNTING"
    assert spoken.node_id == "hunting"
    assert spoken.editorial_score == 50.0


def test_active_repeated_semantic_fact_falls_below_threshold() -> None:
    director, runtime = _director()
    first = director.observe([_hunting("event:1")], None, 1.0)
    assert first is not None and first.graph_candidate is not None
    assert runtime.record_speaking(first.graph_candidate, now=1.0)
    assert runtime.note_completed(now=2.0, run_epoch=0)
    director._busy_until = 0.0
    director._global_ready_at = 0.0

    repeated = director.observe([_hunting("event:2")], None, 3.0)

    assert repeated is None
    assert director._last_graph_winner is None


def test_active_node_does_not_use_legacy_node_cooldown() -> None:
    director, runtime = _director(
        node_weight=0.0,
        semantic_weight=0.0,
        edge_weight=0.0,
        path_weight=0.0,
    )
    first = director.observe([_hunting("event:1")], None, 1.0)
    assert first is not None and first.graph_candidate is not None
    runtime.record_speaking(first.graph_candidate, now=1.0)
    runtime.note_completed(now=1.1, run_epoch=0)
    director._busy_until = 0.0
    director._global_ready_at = 0.0

    second = director.observe([_hunting("event:2")], None, 1.2)

    assert second is not None
    assert second.node_id == "hunting"
    assert director.decisions(1)[-1]["reason"] == "spoken"


def test_active_preserves_higher_priority_critical_legacy_event() -> None:
    director, _runtime = _director()
    finish = make_envelope(
        event_type="FINISH",
        event_id="finish:1",
        sequence=1,
        phase="RESULT",
        mode="RACE",
        priority=100,
        correlation_id="finish:1",
        metrics={"position": 4},
    )

    spoken = director.observe([_hunting("event:2", priority=40), finish], None, 1.0)

    assert spoken is not None
    assert spoken.event_type == "FINISH"


def test_active_ranking_error_falls_back_to_legacy_selection() -> None:
    director, runtime = _director()
    graph_rows: list[dict] = []
    director.on_graph_decision = lambda entry, _now: graph_rows.append(entry)

    def fail(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("boom")

    runtime.select = fail  # type: ignore[method-assign,assignment]
    spoken = director.observe([_hunting("event:1")], None, 1.0)

    assert spoken is not None
    assert spoken.node_id == "hunting"
    assert graph_rows[-1]["reason"] == "legacy_fallback"


def test_active_initial_silence_requests_filler_without_defer_and_uses_backoff() -> None:
    director, _runtime = _director()
    calls: list[float] = []

    def provider(now: float) -> None:
        calls.append(now)
        return None

    director.filler_provider = provider

    assert director.tick(33.0) is None
    assert director.tick(33.2) is None
    assert calls == [33.0]


def test_active_incoming_filler_batch_does_not_request_another_filler() -> None:
    director, _runtime = _director()
    calls: list[float] = []
    director.filler_provider = lambda now: calls.append(now)  # type: ignore[assignment]

    spoken = director.observe([_field_fact("event:1")], None, 33.0)

    assert spoken is not None
    assert spoken.event_type == "FIELD_FACT"
    assert calls == []
