"""#275 Slice 6 — timing family restart/rewind replay cases."""

from __future__ import annotations

import pytest

from irswitch.contracts import ContractViolation, FactScope, FactStatus
from irswitch.contracts.fact import AtomicFact
from irswitch.contracts.timing_family_map import (
    SESSION_RECAP_WIRE_IDS,
    TIMING_WIRE_IDS,
    row_for_wire_id,
)
from irswitch.contracts.timing_family_replay_cases import (
    TimingReplayCase,
    cases_for_wire_id,
    restart_rewind_replay_cases_are_complete,
    timing_family_replay_cases,
)
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
        elif predicate == "stream.started":
            attributes = {"startReason": "normal"}
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


def _admit_minimal_rewind(ledger: FactLedger) -> None:
    stream = _fact(
        "fact:stream:1",
        predicate="stream.started",
        occurrence_id=None,
        lineage_id=None,
        scope="stream",
        subject_id=None,
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
    ledger.apply(
        (stream, practice_best),
        now_ms=1_100,
        projection=_projection(occurrence_id=P1, lineage_id=P1_L),
    )
    ledger.apply(
        (q1_result,),
        now_ms=1_200,
        projection=_projection(occurrence_id=Q1, lineage_id=Q1_L),
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
    ledger.apply(
        (q2_result,),
        now_ms=1_400,
        projection=_projection(occurrence_id=Q2, lineage_id=Q2_L),
    )
    race_marker = _fact(
        "fact:r2:marker",
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
        (race_marker,),
        now_ms=1_500,
        projection=_projection(occurrence_id=R2, lineage_id=R2_L),
    )


def test_restart_rewind_replay_cases_are_complete() -> None:
    assert restart_rewind_replay_cases_are_complete() is True


def test_replay_inventory_covers_every_timing_wire_and_scenario() -> None:
    cases = timing_family_replay_cases()
    assert cases
    assert all(isinstance(case, TimingReplayCase) for case in cases)
    covered = {wire_id for case in cases for wire_id in case.wire_ids}
    assert covered == set(TIMING_WIRE_IDS)
    assert {case.scenario for case in cases} == {
        "same_ref_restart",
        "rewind_superseded",
        "post_rewind_forward",
    }


def test_recap_wires_stay_lineage_sensitive_in_replay_cases() -> None:
    for wire_id in SESSION_RECAP_WIRE_IDS:
        assert row_for_wire_id(wire_id).requires_active_lineage is True
        cases = cases_for_wire_id(wire_id)
        assert cases
        assert any(case.speakable_after in {"active_only", "historical_recap"} for case in cases)


def test_only_personal_best_and_quali_recap_may_inherit() -> None:
    inherit = {
        wire_id
        for case in timing_family_replay_cases()
        if case.may_inherit_on_active_lineage
        for wire_id in case.wire_ids
    }
    assert inherit == {"PERSONAL_BEST", "QUALI_RECAP"}


def test_cases_for_unknown_wire_raises() -> None:
    with pytest.raises(ContractViolation, match="unknown timing wire id"):
        cases_for_wire_id("NOT_A_TIMING_WIRE")


def test_post_rewind_personal_best_case_matches_ledger_inheritance() -> None:
    ledger = FactLedger()
    _admit_minimal_rewind(ledger)
    assert (
        str(ledger.current("timing.personal_best", subject_id="car:12").fact_id) == "fact:p1:best"
    )
    assert str(ledger.current("session.qualifying_result", subject_id="car:12").fact_id) == (
        "fact:q2:result"
    )
    inherited = {str(fact.fact_id) for fact in ledger.inherited_facts()}
    assert inherited == {"fact:p1:best", "fact:q2:result"}
    assert "fact:q1:result" not in inherited

    case = next(
        item
        for item in timing_family_replay_cases()
        if item.case_id == "post_rewind_forward:personal_best_inherits"
    )
    assert case.may_inherit_on_active_lineage is True
    assert case.speakable_after == "active_only"
    assert case.fact_scope == "downstream"


def test_superseded_quali_recap_case_matches_historical_framing() -> None:
    ledger = FactLedger()
    _admit_minimal_rewind(ledger)
    with pytest.raises(ContractViolation, match="historical|recap"):
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

    case = next(
        item
        for item in timing_family_replay_cases()
        if item.case_id == "rewind_superseded:quali_result_historical"
    )
    assert case.speakable_after == "historical_recap"
    assert case.fact_scope == "historical_only"
