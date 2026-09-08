"""#245 compile StreamTimeline transitions into typed AtomicFacts."""

from __future__ import annotations

from pathlib import Path

from irswitch.contracts import FactProducer, FactScope, fact_producer
from irswitch.events.fact_ledger import FactLedger, FactProjection
from irswitch.events.timeline_facts import compile_timeline_facts
from irswitch.logic.stream_timeline import (
    BroadcastObservation,
    SessionInfoRow,
    SessionObservation,
    StreamTimeline,
    TimelineTick,
)

ROOT = Path(__file__).resolve().parents[1]


def _row(session_num: int, session_type: str) -> SessionInfoRow:
    return SessionInfoRow(session_num=session_num, session_type=session_type)


def _pqr_rows() -> tuple[SessionInfoRow, ...]:
    return (_row(0, "Practice"), _row(1, "Qualify"), _row(2, "Race"))


def _session(
    *,
    session_num: int = 0,
    session_time_s: float | None = 12.0,
) -> SessionObservation:
    return SessionObservation(
        connected=True,
        availability="complete",
        sub_session_id="sub:1",
        session_num=session_num,
        session_time_s=session_time_s,
        rows=_pqr_rows(),
        track_id=999,
    )


def _tick(
    now_ms: int,
    *,
    epoch: int = 1,
    state: str = "active",
    session: SessionObservation | None = None,
) -> TimelineTick:
    return TimelineTick(
        now_ms=now_ms,
        broadcast=BroadcastObservation(epoch=epoch, state=state),
        session=_session() if session is None else session,
        commentary_enabled=True,
    )


def _open() -> StreamTimeline:
    timeline = StreamTimeline()
    timeline.observe(_tick(1_000, epoch=0, state="inactive"))
    return timeline


def _compile(step):
    return compile_timeline_facts(
        snapshot=step.snapshot,
        commands=step.commands,
        occurrences=step.occurrences,
        plan=step.plan,
    )


def test_opening_run_emits_stream_session_and_next_stage() -> None:
    timeline = _open()
    step = timeline.observe(_tick(2_000, epoch=1, session=_session(session_num=0)))
    facts = _compile(step)
    predicates = [fact.predicate for fact in facts]
    assert predicates == [
        "stream.started",
        "session.started",
        "session.next_present_stage",
    ]
    assert all(fact_producer(fact.predicate) is FactProducer.TIMELINE for fact in facts)
    started = facts[0]
    session = facts[1]
    nxt = facts[2]
    assert started.scope is FactScope.STREAM
    assert started.occurrence_id is None
    assert dict(started.attributes) == {"startReason": "normal"}
    assert dict(session.attributes) == {"stage": "practice", "startReason": "normal_transition"}
    assert str(session.occurrence_id) == "1:practice:0"
    assert dict(nxt.attributes) == {
        "stage": "qualifying",
        "sourceSubSessionId": "sub:1",
        "sourceSessionNum": 1,
    }


def test_forward_transition_ends_old_session_without_opening_speech() -> None:
    timeline = _open()
    first = timeline.observe(_tick(2_000, epoch=1, session=_session(session_num=0)))
    second = timeline.observe(_tick(3_000, epoch=1, session=_session(session_num=1)))
    facts = _compile(second)
    predicates = [fact.predicate for fact in facts]
    assert predicates == [
        "session.ended",
        "session.started",
        "session.next_present_stage",
    ]
    ended = facts[0]
    started = facts[1]
    assert dict(ended.attributes) == {"stage": "practice", "reason": "forward_transition"}
    assert str(ended.occurrence_id) == "1:practice:0"
    assert dict(started.attributes) == {"stage": "qualifying", "startReason": "normal_transition"}
    assert str(started.occurrence_id) == "1:qualifying:0"
    ledger = FactLedger()
    first_projection = FactProjection(
        broadcast_epoch=int(first.snapshot["broadcastEpoch"]),
        stream_epoch=int(first.snapshot["streamEpoch"]),
        occurrence_id=str(first.snapshot["occurrenceId"]),
        lineage_id=str(first.snapshot["lineageId"]),
    )
    second_projection = FactProjection(
        broadcast_epoch=int(second.snapshot["broadcastEpoch"]),
        stream_epoch=int(second.snapshot["streamEpoch"]),
        occurrence_id=str(second.snapshot["occurrenceId"]),
        lineage_id=str(second.snapshot["lineageId"]),
    )
    first_facts = _compile(first)
    ledger.apply_sources(now_ms=2_000, projection=first_projection, timeline=first_facts)
    step = ledger.apply_sources(now_ms=3_000, projection=second_projection, timeline=facts)
    assert step.view is not None
    started_ids = {
        str(fact.occurrence_id) for fact in step.view.facts if fact.predicate == "session.started"
    }
    assert started_ids == {"1:practice:0", "1:qualifying:0"}
    assert any(
        fact.predicate == "session.ended" and str(fact.occurrence_id) == "1:practice:0"
        for fact in step.view.facts
    )


def test_rewind_and_same_stage_restart_keep_origin_identity() -> None:
    timeline = _open()
    timeline.observe(_tick(2_000, session=_session(session_num=0)))
    timeline.observe(_tick(3_000, session=_session(session_num=1)))
    timeline.observe(_tick(4_000, session=_session(session_num=2, session_time_s=80.0)))
    rewind = timeline.observe(_tick(5_000, session=_session(session_num=1)))
    rewind_facts = _compile(rewind)
    predicates = [fact.predicate for fact in rewind_facts]
    assert "session.ended" in predicates
    assert "session.started" in predicates
    started = next(fact for fact in rewind_facts if fact.predicate == "session.started")
    ended = next(fact for fact in rewind_facts if fact.predicate == "session.ended")
    assert dict(started.attributes)["startReason"] == "rewind_branch"
    assert str(started.occurrence_id) == "1:qualifying:1"
    assert dict(ended.attributes)["reason"] == "rewind_superseded"

    timeline.observe(_tick(6_000, session=_session(session_num=2, session_time_s=80.0)))
    timeline.observe(_tick(6_050, session=_session(session_num=2, session_time_s=10.0)))
    restarted = timeline.observe(_tick(6_160, session=_session(session_num=2, session_time_s=10.2)))
    restart_facts = _compile(restarted)
    restarted_fact = next(fact for fact in restart_facts if fact.predicate == "session.restarted")
    assert dict(restarted_fact.attributes) == {
        "stage": "race",
        "predecessorOccurrenceId": "1:race:1",
    }
    assert str(restarted_fact.occurrence_id) == "1:race:2"


def test_compiler_does_not_import_runtime_or_timeline_owner() -> None:
    imports = [
        line
        for line in (ROOT / "src/irswitch/events/timeline_facts.py")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.startswith("from ") or line.startswith("import ")
    ]
    joined = "\n".join(imports)
    assert "NarrativeRuntime" not in joined
    assert "DetectorBank" not in joined
    assert "stream_timeline" not in joined
    assert "overlay.tape" not in joined
    events_init = (ROOT / "src/irswitch/events/__init__.py").read_text(encoding="utf-8")
    assert "compile_timeline_facts" not in events_init
    assert "FactLedger" not in events_init
