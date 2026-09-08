"""#246 fact inheritance, supersession and compacted summaries."""

from __future__ import annotations

import pytest

from irswitch.contracts import ContractViolation, FactScope, FactStatus
from irswitch.contracts.fact import AtomicFact
from irswitch.events.fact_ledger import FactLedger, FactProjection


def _projection(
    *,
    occurrence_id: str,
    lineage_id: str,
    stream_epoch: int = 1,
) -> FactProjection:
    return FactProjection(
        broadcast_epoch=4,
        stream_epoch=stream_epoch,
        occurrence_id=occurrence_id,
        lineage_id=lineage_id,
        history_complete=True,
    )


def _fact(
    fact_id: str,
    *,
    predicate: str,
    occurrence_id: str | None,
    lineage_id: str | None,
    scope: str,
    subject_id: str | None = None,
    object_id: str | None = None,
    attributes: dict[str, object] | None = None,
    status: str = "active",
    observed_at: int = 1_000,
    valid_from: int = 900,
    valid_until: int | None = None,
    stream_epoch: int = 1,
) -> AtomicFact:
    if attributes is None:
        if predicate == "timing.personal_best":
            attributes = {"lapTime": 91.2, "referenceTime": 91.8, "improvement": 0.6}
        elif predicate == "session.qualifying_result":
            attributes = {"position": 4, "bestLapTime": 90.1}
        elif predicate == "weather.air_temperature":
            attributes = {"value": 22.0, "source": "live"}
        elif predicate == "broadcast.context":
            attributes = {"context": "on_track"}
        elif predicate == "stream.started":
            attributes = {"startReason": "normal"}
        elif predicate == "battle.closing":
            attributes = {
                "gap": 0.42,
                "netClosing": 0.2,
                "slope": -0.05,
                "targetEpoch": "rel:1",
            }
        elif predicate == "session.ended":
            attributes = {"stage": "race", "reason": "rewind_superseded"}
        else:
            attributes = {}
    return AtomicFact(
        fact_id=fact_id,
        predicate=predicate,
        subject_id=subject_id,
        object_id=object_id,
        attributes=attributes,
        polarity="positive",
        valid_from_mono_ms=valid_from,
        valid_until_mono_ms=valid_until,
        observed_at_mono_ms=observed_at,
        broadcast_epoch=4,
        stream_epoch=stream_epoch,
        occurrence_id=occurrence_id,
        lineage_id=lineage_id,
        evidence_refs=("telemetry:1",),
        confidence=0.8,
        scope=scope,
        status=status,
        revision=0,
    )


P1 = "1:practice:0"
Q1 = "1:qualifying:0"
R1 = "1:race:0"
Q2 = "1:qualifying:1"
R2 = "1:race:1"

P1_L = P1
Q1_L = f"{P1}>{Q1}"
R1_L = f"{P1}>{Q1}>{R1}"
Q2_L = f"{P1}>{Q2}"
R2_L = f"{P1}>{Q2}>{R2}"


def _admit_rewind_chain(ledger: FactLedger) -> None:
    stream = _fact(
        "fact:stream:1",
        predicate="stream.started",
        occurrence_id=None,
        lineage_id=None,
        scope="stream",
        subject_id=None,
    )
    context = _fact(
        "fact:ctx:1",
        predicate="broadcast.context",
        occurrence_id=None,
        lineage_id=None,
        scope="stream",
        subject_id=None,
        observed_at=1_010,
        valid_from=1_010,
    )
    practice_best = _fact(
        "fact:p1:best",
        predicate="timing.personal_best",
        occurrence_id=P1,
        lineage_id=P1_L,
        scope="downstream",
        subject_id="car:12",
        observed_at=1_100,
        valid_from=1_100,
    )
    q1_result = _fact(
        "fact:q1:result",
        predicate="session.qualifying_result",
        occurrence_id=Q1,
        lineage_id=Q1_L,
        scope="downstream",
        subject_id="car:12",
        observed_at=1_200,
        valid_from=1_200,
    )
    q1_weather = _fact(
        "fact:q1:weather",
        predicate="weather.air_temperature",
        occurrence_id=Q1,
        lineage_id=Q1_L,
        scope="revalidate",
        observed_at=1_210,
        valid_from=1_210,
    )
    r1_battle = _fact(
        "fact:r1:battle",
        predicate="battle.closing",
        occurrence_id=R1,
        lineage_id=R1_L,
        scope="occurrence",
        subject_id="car:12",
        object_id="car:34",
        observed_at=1_300,
        valid_from=1_300,
    )
    ledger.apply(
        (stream, context, practice_best),
        now_ms=1_100,
        projection=_projection(occurrence_id=P1, lineage_id=P1_L),
    )
    ledger.apply(
        (q1_result, q1_weather),
        now_ms=1_210,
        projection=_projection(occurrence_id=Q1, lineage_id=Q1_L),
    )
    ledger.apply(
        (r1_battle,),
        now_ms=1_300,
        projection=_projection(occurrence_id=R1, lineage_id=R1_L),
    )
    q2_result = _fact(
        "fact:q2:result",
        predicate="session.qualifying_result",
        occurrence_id=Q2,
        lineage_id=Q2_L,
        scope="downstream",
        subject_id="car:12",
        observed_at=1_400,
        valid_from=1_400,
        attributes={"position": 2, "bestLapTime": 89.4},
    )
    q2_weather = _fact(
        "fact:q2:weather",
        predicate="weather.air_temperature",
        occurrence_id=Q2,
        lineage_id=Q2_L,
        scope="revalidate",
        observed_at=1_410,
        valid_from=1_410,
        attributes={"value": 19.5, "source": "live"},
    )
    ledger.apply(
        (q2_result, q2_weather),
        now_ms=1_410,
        projection=_projection(occurrence_id=Q2, lineage_id=Q2_L),
    )
    r2_battle = _fact(
        "fact:r2:battle",
        predicate="battle.closing",
        occurrence_id=R2,
        lineage_id=R2_L,
        scope="occurrence",
        subject_id="car:12",
        object_id="car:34",
        observed_at=1_500,
        valid_from=1_500,
        attributes={
            "gap": 0.21,
            "netClosing": 0.1,
            "slope": -0.08,
            "targetEpoch": "rel:2",
        },
    )
    ledger.apply(
        (r2_battle,),
        now_ms=1_500,
        projection=_projection(occurrence_id=R2, lineage_id=R2_L),
    )


def test_r2_after_rewind_inherits_p1_and_q2_only() -> None:
    ledger = FactLedger()
    _admit_rewind_chain(ledger)
    view = ledger.latest_view()
    assert view is not None
    ids = {str(fact.fact_id) for fact in view.facts}
    assert ids >= {
        "fact:stream:1",
        "fact:ctx:1",
        "fact:p1:best",
        "fact:q2:result",
        "fact:r2:battle",
    }
    assert "fact:q2:weather" not in ids
    assert "fact:q1:result" not in ids
    assert "fact:q1:weather" not in ids
    assert "fact:r1:battle" not in ids
    assert ledger.current("timing.personal_best", subject_id="car:12") is not None
    assert (
        str(ledger.current("timing.personal_best", subject_id="car:12").fact_id) == "fact:p1:best"
    )
    assert str(ledger.current("session.qualifying_result", subject_id="car:12").fact_id) == (
        "fact:q2:result"
    )
    assert ledger.current("battle.closing", subject_id="car:12", object_id="car:34") is not None
    assert (
        str(ledger.current("battle.closing", subject_id="car:12", object_id="car:34").fact_id)
        == "fact:r2:battle"
    )
    inherited = ledger.inherited_facts()
    assert {str(fact.fact_id) for fact in inherited} == {"fact:p1:best", "fact:q2:result"}
    assert all(id(fact) == id(ledger.resolve(str(fact.fact_id))) for fact in view.facts)


def test_superseded_facts_require_explicit_historical_framing() -> None:
    ledger = FactLedger()
    _admit_rewind_chain(ledger)
    assert ledger.current("session.qualifying_result", subject_id="car:12") is not None
    assert str(ledger.current("session.qualifying_result", subject_id="car:12").fact_id) != (
        "fact:q1:result"
    )
    with pytest.raises(ContractViolation, match="historical\\|recap"):
        ledger.historical("session.qualifying_result", occurrence_id=Q1, subject_id="car:12")
    recap = ledger.historical(
        "session.qualifying_result",
        occurrence_id=Q1,
        subject_id="car:12",
        framing="recap",
    )
    assert recap is not None
    assert str(recap.fact_id) == "fact:q1:result"
    assert recap.status in {FactStatus.HISTORICAL, FactStatus.SUPERSEDED}
    assert recap.scope is FactScope.DOWNSTREAM
    stale_weather = ledger.historical(
        "weather.air_temperature",
        occurrence_id=Q1,
        framing="historical",
    )
    assert stale_weather is not None
    assert str(stale_weather.fact_id) == "fact:q1:weather"
    assert ledger.current("weather.air_temperature") is None
    r2_weather = ledger.historical(
        "weather.air_temperature",
        occurrence_id=Q2,
        framing="historical",
    )
    assert r2_weather is not None
    assert str(r2_weather.fact_id) == "fact:q2:weather"


def test_inherited_view_does_not_copy_facts() -> None:
    ledger = FactLedger()
    _admit_rewind_chain(ledger)
    first = ledger.resolve("fact:p1:best")
    view = ledger.latest_view()
    assert view is not None
    published = next(fact for fact in view.facts if str(fact.fact_id) == "fact:p1:best")
    assert published is first
    assert published.occurrence_id is not None
    assert str(published.occurrence_id) == P1


def test_revalidate_facts_are_not_automatically_current_after_transition() -> None:
    ledger = FactLedger()
    weather = _fact(
        "fact:q1:weather",
        predicate="weather.air_temperature",
        occurrence_id=Q1,
        lineage_id=Q1_L,
        scope="revalidate",
    )
    ledger.apply(
        (weather,), now_ms=1_200, projection=_projection(occurrence_id=Q1, lineage_id=Q1_L)
    )
    race = ledger.apply((), now_ms=1_300, projection=_projection(occurrence_id=R1, lineage_id=R1_L))
    assert race.view is not None
    assert ledger.current("weather.air_temperature") is None
    ids = {str(fact.fact_id) for fact in race.view.facts}
    assert "fact:q1:weather" not in ids
    archived = ledger.resolve("fact:q1:weather")
    assert archived.status is FactStatus.HISTORICAL


def test_occurrence_summary_is_self_contained() -> None:
    ledger = FactLedger()
    _admit_rewind_chain(ledger)
    q2 = ledger.occurrence_summary(Q2)
    assert [str(fact.fact_id) for fact in q2] == ["fact:q2:result"]
    assert dict(q2[0].attributes)["position"] == 2
    q1 = ledger.occurrence_summary(Q1)
    assert [str(fact.fact_id) for fact in q1] == ["fact:q1:result"]
    r1 = ledger.occurrence_summary(R1)
    assert r1 == ()


def test_repeated_rewind_chain_keeps_active_ancestors_only() -> None:
    ledger = FactLedger()
    _admit_rewind_chain(ledger)
    q3 = "1:qualifying:2"
    r3 = "1:race:2"
    q3_lineage = f"{P1}>{q3}"
    r3_lineage = f"{P1}>{q3}>{r3}"
    q3_result = _fact(
        "fact:q3:result",
        predicate="session.qualifying_result",
        occurrence_id=q3,
        lineage_id=q3_lineage,
        scope="downstream",
        subject_id="car:12",
        observed_at=1_600,
        valid_from=1_600,
        attributes={"position": 6, "bestLapTime": 90.9},
    )
    ledger.apply(
        (q3_result,),
        now_ms=1_600,
        projection=_projection(occurrence_id=q3, lineage_id=q3_lineage),
    )
    r3_battle = _fact(
        "fact:r3:battle",
        predicate="battle.closing",
        occurrence_id=r3,
        lineage_id=r3_lineage,
        scope="occurrence",
        subject_id="car:12",
        object_id="car:34",
        observed_at=1_700,
        valid_from=1_700,
    )
    step = ledger.apply(
        (r3_battle,),
        now_ms=1_700,
        projection=_projection(occurrence_id=r3, lineage_id=r3_lineage),
    )
    assert step.view is not None
    ids = {str(fact.fact_id) for fact in step.view.facts}
    assert "fact:p1:best" in ids
    assert "fact:q3:result" in ids
    assert "fact:r3:battle" in ids
    assert "fact:q1:result" not in ids
    assert "fact:q2:result" not in ids
    assert "fact:r2:battle" not in ids
    assert {str(fact.fact_id) for fact in ledger.inherited_facts()} == {
        "fact:p1:best",
        "fact:q3:result",
    }


def test_historical_compaction_emits_summary_refs_not_complete_history() -> None:
    ledger = FactLedger(historical_capacity=4)
    projection = _projection(occurrence_id=R1, lineage_id=R1_L)
    for index in range(8):
        battle = _fact(
            f"fact:r1:battle:{index}",
            predicate="battle.closing",
            occurrence_id=R1,
            lineage_id=R1_L,
            scope="occurrence",
            subject_id="car:12",
            object_id=f"car:{30 + index}",
            observed_at=1_000 + index,
            valid_from=1_000 + index,
            attributes={
                "gap": 0.4 + index * 0.01,
                "netClosing": 0.2,
                "slope": -0.05,
                "targetEpoch": f"rel:{index}",
            },
        )
        later = _fact(
            f"fact:r1:battle:{index}:next",
            predicate="battle.closing",
            occurrence_id=R1,
            lineage_id=R1_L,
            scope="occurrence",
            subject_id="car:12",
            object_id=f"car:{30 + index}",
            observed_at=1_100 + index,
            valid_from=1_100 + index,
            attributes={
                "gap": 0.3,
                "netClosing": 0.1,
                "slope": -0.04,
                "targetEpoch": f"rel:{index}",
            },
        )
        ledger.apply((battle, later), now_ms=1_100 + index, projection=projection)
    view = ledger.latest_view()
    assert view is not None
    assert view.compacted_summary_refs
    assert len(view.compacted_summary_refs) <= 64
    refs = [str(item) for item in view.compacted_summary_refs]
    assert refs == sorted(refs)
    assert view.history_complete is False or len(ledger._historical) <= ledger.historical_capacity
