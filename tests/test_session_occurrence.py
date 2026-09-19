"""#244 SessionOccurrence identity, parent lineage and historical branches."""

from __future__ import annotations

import json

import pytest

from irswitch.contracts import (
    ContractViolation,
    LineageId,
    MonotonicMs,
    OccurrenceId,
    SessionOccurrence,
    SessionRef,
)
from irswitch.logic.stream_timeline import (
    BroadcastObservation,
    SessionInfoRow,
    SessionObservation,
    StreamTimeline,
    TimelineTick,
)


def _row(session_num: int, session_type: str) -> SessionInfoRow:
    return SessionInfoRow(session_num=session_num, session_type=session_type)


def _pqr_rows() -> tuple[SessionInfoRow, ...]:
    return (_row(0, "Practice"), _row(1, "Qualify"), _row(2, "Race"))


def _session(
    *,
    connected: bool = True,
    availability: str = "complete",
    sub_session_id: str | None = "sub:1",
    session_num: int | None = 0,
    session_time_s: float | None = 12.0,
    rows: tuple[SessionInfoRow, ...] | None = None,
) -> SessionObservation:
    return SessionObservation(
        connected=connected,
        availability=availability,
        sub_session_id=sub_session_id,
        session_num=session_num,
        session_time_s=session_time_s,
        rows=_pqr_rows() if rows is None else rows,
        track_id=999,
    )


def _tick(
    now_ms: int,
    *,
    epoch: int = 1,
    state: str = "active",
    enabled: bool = True,
    session: SessionObservation | None = None,
) -> TimelineTick:
    return TimelineTick(
        now_ms=now_ms,
        broadcast=BroadcastObservation(epoch=epoch, state=state),
        session=_session() if session is None else session,
        commentary_enabled=enabled,
    )


def _open(timeline: StreamTimeline | None = None) -> StreamTimeline:
    timeline = StreamTimeline() if timeline is None else timeline
    timeline.observe(_tick(1_000, epoch=0, state="inactive"))
    return timeline


def _record(
    *,
    occurrence_id: str = "1:practice:0",
    session_num: int = 0,
    parent_id: str | None = None,
    lineage_id: str | None = None,
    status: str = "active",
    end_reason: str | None = None,
    ended_at: int | None = None,
    started_at: int = 2_000,
    broadcast_epoch: int = 1,
) -> SessionOccurrence:
    occ = OccurrenceId.parse(occurrence_id)
    parent = None if parent_id is None else OccurrenceId.parse(parent_id)
    lineage = LineageId.parse(lineage_id or occurrence_id)
    return SessionOccurrence(
        occurrence_id=occ,
        broadcast_epoch=broadcast_epoch,
        session_ref=SessionRef("sub:1", session_num),
        parent_id=parent,
        lineage_id=lineage,
        started_at_mono_ms=MonotonicMs(started_at),
        ended_at_mono_ms=None if ended_at is None else MonotonicMs(ended_at),
        end_reason=end_reason,
        status=status,
    )


def test_occurrence_wire_uses_exact_encoded_ids() -> None:
    record = _record(
        occurrence_id="3:race:2",
        session_num=2,
        parent_id="3:qualifying:1",
        lineage_id="3:practice:0>3:qualifying:1>3:race:2",
        status="completed",
        end_reason="forward_transition",
        ended_at=9_000,
        started_at=8_000,
        broadcast_epoch=4,
    )
    expected = {
        "occurrenceId": "3:race:2",
        "broadcastEpoch": 4,
        "sessionRef": {"subSessionId": "sub:1", "sessionNum": 2},
        "parentId": "3:qualifying:1",
        "lineageId": "3:practice:0>3:qualifying:1>3:race:2",
        "startedAtMonoMs": 8_000,
        "endedAtMonoMs": 9_000,
        "endReason": "forward_transition",
        "status": "completed",
    }
    assert record.to_dict() == expected
    assert SessionOccurrence.from_dict(json.loads(json.dumps(expected))) == record
    assert str(record.occurrence_id) == "3:race:2"
    assert str(record.lineage_id) == "3:practice:0>3:qualifying:1>3:race:2"


@pytest.mark.parametrize(
    "kwargs",
    (
        {"parent_id": "1:race:0", "lineage_id": "1:race:0>1:practice:0"},
        {"status": "active", "end_reason": "stream_ended", "ended_at": 3_000},
        {"status": "superseded", "end_reason": None, "ended_at": None},
        {"status": "restarted", "end_reason": "rewind_superseded", "ended_at": 3_000},
        {"status": "abandoned", "end_reason": "forward_transition", "ended_at": 3_000},
        {
            "occurrence_id": "1:qualifying:0",
            "session_num": 1,
            "parent_id": "1:practice:0",
            "lineage_id": "1:qualifying:0",
            "status": "active",
        },
    ),
)
def test_occurrence_contract_rejects_incoherent_records(kwargs: dict[str, object]) -> None:
    with pytest.raises(ContractViolation):
        _record(**kwargs)  # type: ignore[arg-type]


def test_canonical_pqr_then_rewind_to_qualifying_keeps_historical_branch() -> None:
    timeline = _open()
    timeline.observe(_tick(2_000, session=_session(session_num=0)))
    timeline.observe(_tick(3_000, session=_session(session_num=1)))
    timeline.observe(_tick(4_000, session=_session(session_num=2)))
    rewind = timeline.observe(_tick(5_000, session=_session(session_num=1)))

    assert rewind.snapshot["occurrenceId"] == "1:qualifying:1"
    assert rewind.snapshot["lineageId"] == "1:practice:0>1:qualifying:1"
    assert rewind.snapshot["transitionReasons"] == [
        "session_ended",
        "session_superseded",
        "session_started",
    ]

    practice = timeline.resolve("1:practice:0")
    old_quali = timeline.resolve("1:qualifying:0")
    old_race = timeline.resolve("1:race:0")
    new_quali = timeline.resolve("1:qualifying:1")

    assert practice.status == "completed"
    assert practice.end_reason == "forward_transition"
    assert practice.parent_id is None
    assert old_quali.status == "superseded"
    assert old_quali.end_reason == "rewind_superseded"
    assert old_quali.parent_id == OccurrenceId.parse("1:practice:0")
    assert old_race.status == "superseded"
    assert old_race.end_reason == "rewind_superseded"
    assert old_race.parent_id == OccurrenceId.parse("1:qualifying:0")
    assert new_quali.status == "active"
    assert new_quali.parent_id == OccurrenceId.parse("1:practice:0")
    assert str(new_quali.lineage_id) == "1:practice:0>1:qualifying:1"
    assert {str(item.occurrence_id) for item in timeline.retained_occurrences()} == {
        "1:practice:0",
        "1:qualifying:0",
        "1:race:0",
        "1:qualifying:1",
    }


def test_later_race_after_rewind_inherits_new_qualifying_only() -> None:
    timeline = _open()
    timeline.observe(_tick(2_000, session=_session(session_num=0)))
    timeline.observe(_tick(3_000, session=_session(session_num=1)))
    timeline.observe(_tick(4_000, session=_session(session_num=2)))
    timeline.observe(_tick(5_000, session=_session(session_num=1)))
    race = timeline.observe(_tick(6_000, session=_session(session_num=2)))

    assert race.snapshot["lineageId"] == "1:practice:0>1:qualifying:1>1:race:1"
    current = timeline.resolve("1:race:1")
    assert current.status == "active"
    assert current.parent_id == OccurrenceId.parse("1:qualifying:1")
    assert timeline.resolve("1:qualifying:0").status == "superseded"
    assert timeline.resolve("1:race:0").status == "superseded"


REWIND_CASES = (
    (
        "race_to_qualifying",
        (0, 1, 2, 1),
        "1:practice:0>1:qualifying:1",
        ("1:qualifying:0", "1:race:0"),
    ),
    (
        "race_to_practice",
        (0, 1, 2, 0),
        "1:practice:1",
        ("1:practice:0", "1:qualifying:0", "1:race:0"),
    ),
    (
        "qualifying_to_practice",
        (0, 1, 0),
        "1:practice:1",
        ("1:practice:0", "1:qualifying:0"),
    ),
)


@pytest.mark.parametrize("case_id,nums,active_lineage,superseded", REWIND_CASES)
def test_rewind_fixtures_preserve_canonical_stage_order(
    case_id: str,
    nums: tuple[int, ...],
    active_lineage: str,
    superseded: tuple[str, ...],
) -> None:
    del case_id
    timeline = _open()
    step = None
    for offset, session_num in enumerate(nums):
        step = timeline.observe(
            _tick(2_000 + offset * 1_000, session=_session(session_num=session_num))
        )
    assert step is not None
    assert step.snapshot["lineageId"] == active_lineage
    stages = [item.stage.value for item in LineageId.parse(active_lineage).occurrences]
    assert stages == sorted(stages, key=["practice", "qualifying", "race"].index)
    for occurrence_id in superseded:
        record = timeline.resolve(occurrence_id)
        assert record.status == "superseded"
        assert record.end_reason == "rewind_superseded"
    current = timeline.resolve(str(step.snapshot["occurrenceId"]))
    assert current.status == "active"
    assert current.session_ref == SessionRef("sub:1", nums[-1])


def test_same_stage_restart_keeps_parent_and_archives_old_occurrence() -> None:
    timeline = _open()
    timeline.observe(_tick(2_000, session=_session(session_num=0)))
    timeline.observe(_tick(3_000, session=_session(session_num=1)))
    timeline.observe(_tick(4_000, session=_session(session_num=2, session_time_s=80.0)))
    timeline.observe(_tick(4_050, session=_session(session_num=2, session_time_s=10.0)))
    restarted = timeline.observe(_tick(4_160, session=_session(session_num=2, session_time_s=10.2)))

    assert restarted.snapshot["occurrenceId"] == "1:race:1"
    assert restarted.snapshot["lineageId"] == "1:practice:0>1:qualifying:0>1:race:1"
    old_race = timeline.resolve("1:race:0")
    new_race = timeline.resolve("1:race:1")
    assert old_race.status == "restarted"
    assert old_race.end_reason == "same_ref_restart"
    assert old_race.parent_id == OccurrenceId.parse("1:qualifying:0")
    assert new_race.status == "active"
    assert new_race.parent_id == old_race.parent_id
    assert timeline.resolve("1:practice:0").status == "completed"
    assert timeline.resolve("1:qualifying:0").status == "completed"


def test_each_encoded_occurrence_resolves_to_one_ref() -> None:
    timeline = _open()
    timeline.observe(_tick(2_000, session=_session(session_num=0)))
    timeline.observe(_tick(3_000, session=_session(session_num=1)))
    timeline.observe(_tick(4_000, session=_session(session_num=2)))
    timeline.observe(_tick(5_000, session=_session(session_num=1)))

    seen: set[str] = set()
    for record in timeline.retained_occurrences():
        encoded = str(record.occurrence_id)
        assert encoded not in seen
        seen.add(encoded)
        resolved = timeline.resolve(encoded)
        assert resolved is record or resolved == record
        assert resolved.session_ref == record.session_ref
        parsed = OccurrenceId.parse(encoded)
        assert timeline.resolve(parsed) == resolved
    assert seen == {
        "1:practice:0",
        "1:qualifying:0",
        "1:race:0",
        "1:qualifying:1",
    }
    with pytest.raises(ContractViolation):
        timeline.resolve("1:race:9")


def test_disconnect_does_not_allocate_or_close_occurrence() -> None:
    timeline = _open()
    live = timeline.observe(_tick(2_000, session=_session(session_num=2, session_time_s=40.0)))
    timeline.observe(
        _tick(3_000, session=_session(connected=False, session_num=2, session_time_s=41.0))
    )
    resumed = timeline.observe(_tick(3_050, session=_session(session_num=2, session_time_s=42.0)))

    record = timeline.resolve("1:race:0")
    assert live.snapshot["occurrenceId"] == resumed.snapshot["occurrenceId"] == "1:race:0"
    assert record.status == "active"
    assert record.end_reason is None
    assert len(timeline.retained_occurrences()) == 1


def test_stream_end_abandons_current_and_keeps_historical_branch() -> None:
    timeline = _open()
    timeline.observe(_tick(2_000, session=_session(session_num=0)))
    timeline.observe(_tick(3_000, session=_session(session_num=1)))
    ended = timeline.observe(
        _tick(4_000, epoch=1, state="inactive", session=_session(session_num=1))
    )

    assert ended.snapshot["occurrenceId"] is None
    practice = timeline.resolve("1:practice:0")
    quali = timeline.resolve("1:qualifying:0")
    assert practice.status == "completed"
    assert quali.status == "abandoned"
    assert quali.end_reason == "stream_ended"
    assert quali.ended_at_mono_ms == MonotonicMs(4_000)


def test_new_stream_epoch_does_not_reuse_old_occurrence_ids() -> None:
    timeline = _open()
    first = timeline.observe(_tick(2_000, epoch=1, session=_session(session_num=2)))
    timeline.observe(_tick(3_000, epoch=1, state="active", enabled=False))
    second = timeline.observe(_tick(4_000, epoch=1, session=_session(session_num=2)))

    assert first.snapshot["occurrenceId"] == "1:race:0"
    assert second.snapshot["occurrenceId"] == "2:race:0"
    assert timeline.resolve("1:race:0").status == "abandoned"
    assert timeline.resolve("2:race:0").status == "active"
    assert timeline.resolve("1:race:0").session_ref == timeline.resolve("2:race:0").session_ref


def test_unvisited_ancestors_are_not_invented() -> None:
    timeline = _open()
    race = timeline.observe(_tick(2_000, session=_session(session_num=2)))
    rewind = timeline.observe(_tick(3_000, session=_session(session_num=1)))

    assert race.snapshot["lineageId"] == "1:race:0"
    assert rewind.snapshot["lineageId"] == "1:qualifying:0"
    assert timeline.resolve("1:qualifying:0").parent_id is None
    with pytest.raises(ContractViolation):
        timeline.resolve("1:practice:0")
