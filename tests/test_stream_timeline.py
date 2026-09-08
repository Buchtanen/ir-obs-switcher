"""F22/F25/F31 StreamTimeline: epochs, precedence, plans, rewind."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from irswitch.contracts.primitives import Stage
from irswitch.contracts.resources import packaged_schema_bytes
from irswitch.logic.broadcast_clock import BroadcastClock
from irswitch.logic.stream_timeline import (
    BroadcastObservation,
    SessionInfoRow,
    SessionObservation,
    StreamTimeline,
    TimelineTick,
    compile_session_plan,
    observe_broadcast_clock,
)

ROOT = Path(__file__).resolve().parents[1]
FROZEN_MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
SCHEMA = json.loads(packaged_schema_bytes("dto-contracts.schema.json"))

_BUILDER = importlib.util.spec_from_file_location(
    "v2_build_dto_schemas", FROZEN_MACHINE / "build_dto_schemas.py"
)
assert _BUILDER is not None and _BUILDER.loader is not None
_dto_builder = importlib.util.module_from_spec(_BUILDER)
_BUILDER.loader.exec_module(_dto_builder)


def _errors(value: object) -> list[str]:
    return _dto_builder.schema_errors(value, SCHEMA, SCHEMA)


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
    track_id: int | None = 999,
) -> SessionObservation:
    return SessionObservation(
        connected=connected,
        availability=availability,
        sub_session_id=sub_session_id,
        session_num=session_num,
        session_time_s=session_time_s,
        rows=_pqr_rows() if rows is None else rows,
        track_id=track_id,
    )


def _tick(
    now_ms: int,
    *,
    epoch: int = 2,
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


def _kinds(step) -> list[str]:
    return [item.kind for item in step.commands]


PRECEDENCE_ROWS = (
    "disconnect_suspends_without_identity_change",
    "reconnect_same_ref_is_not_restart",
    "ref_change_ignores_simultaneous_rewind",
    "unconfirmed_rewind_is_not_restart",
    "confirmed_rewind_restarts_same_ref",
)


def test_precedence_table_covers_every_section_57_row() -> None:
    assert set(PRECEDENCE_ROWS) == {
        "disconnect_suspends_without_identity_change",
        "reconnect_same_ref_is_not_restart",
        "ref_change_ignores_simultaneous_rewind",
        "unconfirmed_rewind_is_not_restart",
        "confirmed_rewind_restarts_same_ref",
    }


def test_session_ref_ignores_track_id_as_identity() -> None:
    timeline = StreamTimeline()
    first = timeline.observe(
        _tick(1_000, epoch=0, state="inactive", enabled=True, session=_session(session_num=2))
    )
    started = timeline.observe(
        _tick(
            2_000,
            epoch=1,
            session=_session(session_num=2, track_id=111, session_time_s=40.0),
        )
    )
    same_ref_other_track = timeline.observe(
        _tick(
            3_000,
            epoch=1,
            session=_session(session_num=2, track_id=222, session_time_s=41.0),
        )
    )

    assert first.snapshot["sessionRef"] is None
    assert started.snapshot["sessionRef"] == {"subSessionId": "sub:1", "sessionNum": 2}
    assert same_ref_other_track.snapshot["sessionRef"] == started.snapshot["sessionRef"]
    assert "SESSION_STARTED" not in _kinds(same_ref_other_track)
    assert started.snapshot["stage"] == "race"


def test_missing_identity_cannot_create_session_scoped_claims() -> None:
    timeline = StreamTimeline()
    timeline.observe(_tick(1_000, epoch=0, state="inactive"))
    step = timeline.observe(
        _tick(
            2_000,
            epoch=1,
            session=_session(sub_session_id=None, session_num=None, track_id=14),
        )
    )

    assert step.snapshot["narrativeRunActive"] is True
    assert step.snapshot["sessionRef"] is None
    assert step.snapshot["occurrenceId"] is None
    assert step.snapshot["lineageId"] is None
    assert "SESSION_STARTED" not in _kinds(step)


@pytest.mark.parametrize("row_id", PRECEDENCE_ROWS)
def test_section_57_precedence_row(row_id: str) -> None:
    timeline = StreamTimeline()
    timeline.observe(_tick(1_000, epoch=0, state="inactive"))
    live = timeline.observe(
        _tick(2_000, epoch=1, session=_session(session_num=2, session_time_s=80.0))
    )
    assert live.snapshot["occurrenceId"] == "1:race:0"

    if row_id == "disconnect_suspends_without_identity_change":
        step = timeline.observe(
            _tick(
                3_000,
                epoch=1,
                session=_session(connected=False, session_num=2, session_time_s=81.0),
            )
        )
        assert "session_suspended" in step.snapshot["transitionReasons"]
        assert step.snapshot["sessionRef"] is None
        assert step.snapshot["occurrenceId"] is None
        assert "SESSION_ENDED" not in _kinds(step)
        assert "SESSION_RESTARTED" not in _kinds(step)
        return

    if row_id == "reconnect_same_ref_is_not_restart":
        timeline.observe(
            _tick(
                3_000,
                epoch=1,
                session=_session(connected=False, session_num=2, session_time_s=81.0),
            )
        )
        step = timeline.observe(
            _tick(3_050, epoch=1, session=_session(session_num=2, session_time_s=82.0))
        )
        assert step.snapshot["occurrenceId"] == "1:race:0"
        assert "session_resumed" in step.snapshot["transitionReasons"]
        assert "SESSION_RESTARTED" not in _kinds(step)
        return

    if row_id == "ref_change_ignores_simultaneous_rewind":
        step = timeline.observe(
            _tick(
                3_000,
                epoch=1,
                session=_session(session_num=1, session_time_s=1.0, rows=_pqr_rows()),
            )
        )
        assert _kinds(step) == ["SESSION_ENDED", "SESSION_STARTED"]
        assert step.snapshot["transitionReasons"] == [
            "session_ended",
            "session_superseded",
            "session_started",
        ]
        assert step.snapshot["occurrenceId"] == "1:qualifying:0"
        assert step.snapshot["lineageId"] == "1:qualifying:0"
        assert "SESSION_RESTARTED" not in _kinds(step)
        return

    if row_id == "unconfirmed_rewind_is_not_restart":
        step = timeline.observe(
            _tick(2_050, epoch=1, session=_session(session_num=2, session_time_s=10.0))
        )
        assert "SESSION_RESTARTED" not in _kinds(step)
        assert step.snapshot["occurrenceId"] == "1:race:0"
        return

    step = timeline.observe(
        _tick(2_050, epoch=1, session=_session(session_num=2, session_time_s=10.0))
    )
    confirmed = timeline.observe(
        _tick(2_160, epoch=1, session=_session(session_num=2, session_time_s=10.2))
    )
    assert "SESSION_RESTARTED" not in _kinds(step)
    assert _kinds(confirmed) == ["SESSION_RESTARTED"]
    assert confirmed.snapshot["occurrenceId"] == "1:race:1"
    assert confirmed.snapshot["transitionReasons"] == ["session_restarted"]


def test_obs_unknown_cannot_emit_stream_ended() -> None:
    timeline = StreamTimeline()
    clock = BroadcastClock()
    inactive = observe_broadcast_clock(clock, now_s=1.0, streaming=False)
    timeline.observe(_tick(1_000, epoch=inactive.epoch, state=inactive.state))
    active = observe_broadcast_clock(clock, now_s=2.0, streaming=True)
    started = timeline.observe(_tick(2_000, epoch=active.epoch, state=active.state))
    unknown = observe_broadcast_clock(clock, now_s=3.0, streaming=None)
    step = timeline.observe(_tick(3_000, epoch=unknown.epoch, state=unknown.state))

    assert started.snapshot["narrativeRunActive"] is True
    assert unknown.state == "unknown"
    assert step.snapshot["obsState"] == "unknown"
    assert step.snapshot["broadcastEpoch"] == started.snapshot["broadcastEpoch"]
    assert step.snapshot["streamEpoch"] == started.snapshot["streamEpoch"]
    assert "STREAM_ENDED" not in _kinds(step)
    assert "broadcast_unknown" in step.snapshot["transitionReasons"]


def test_f22_start_reasons_are_exclusive() -> None:
    normal = StreamTimeline()
    normal.observe(_tick(1_000, epoch=0, state="inactive"))
    normal_step = normal.observe(_tick(2_000, epoch=1))
    assert [
        item.start_reason for item in normal_step.commands if item.kind == "STREAM_STARTED"
    ] == ["normal"]
    assert normal_step.snapshot["transitionReasons"][0] == "broadcast_started"
    assert normal_step.snapshot["historyComplete"] is True

    attached = StreamTimeline()
    attached.observe(_tick(1_000, epoch=4, state="active", enabled=False))
    attached_step = attached.observe(_tick(2_000, epoch=4, state="active", enabled=True))
    assert [
        item.start_reason for item in attached_step.commands if item.kind == "STREAM_STARTED"
    ] == ["attached_live"]
    assert attached_step.snapshot["transitionReasons"][0] == "attached_live"
    assert attached_step.snapshot["historyComplete"] is False

    recovered = StreamTimeline(process_recovery=True)
    recovered_step = recovered.observe(_tick(1_000, epoch=1, state="active"))
    assert [
        item.start_reason for item in recovered_step.commands if item.kind == "STREAM_STARTED"
    ] == ["process_recovery"]
    assert recovered_step.snapshot["transitionReasons"][0] == "process_recovery"
    assert recovered_step.snapshot["historyComplete"] is False

    mid = StreamTimeline()
    mid.observe(_tick(1_000, epoch=0, state="inactive"))
    mid.observe(_tick(2_000, epoch=2, state="active"))
    disabled = mid.observe(_tick(3_000, epoch=2, state="active", enabled=False))
    enabled = mid.observe(
        _tick(4_000, epoch=2, state="active", enabled=True, session=_session(session_num=2))
    )
    assert "STREAM_ENDED" not in _kinds(disabled)
    assert disabled.snapshot["broadcastEpoch"] == 2
    assert disabled.snapshot["narrativeRunActive"] is False
    assert [item.start_reason for item in enabled.commands if item.kind == "STREAM_STARTED"] == [
        "enabled_mid_stream"
    ]
    assert enabled.snapshot["streamEpoch"] == 2
    assert enabled.snapshot["historyComplete"] is False
    assert enabled.snapshot["occurrenceId"] == "2:race:0"
    assert "narrative_enabled" in enabled.snapshot["transitionReasons"]

    resume = StreamTimeline()
    resume.observe(_tick(1_000, epoch=0, state="inactive"))
    live = resume.observe(_tick(2_000, epoch=3, state="active"))
    unknown = resume.observe(_tick(3_000, epoch=3, state="unknown"))
    back = resume.observe(_tick(4_000, epoch=3, state="active"))
    assert (
        live.snapshot["streamEpoch"]
        == unknown.snapshot["streamEpoch"]
        == back.snapshot["streamEpoch"]
    )
    assert "STREAM_STARTED" not in _kinds(back)
    assert back.snapshot["transitionReasons"] == ["broadcast_resumed"]


def test_f25_simultaneous_boundaries_keep_canonical_reason_order() -> None:
    timeline = StreamTimeline()
    timeline.observe(_tick(1_000, epoch=0, state="inactive"))
    first = timeline.observe(
        _tick(2_000, epoch=1, session=_session(session_num=2, session_time_s=3.0))
    )
    assert first.snapshot["transitionReasons"] == ["broadcast_started", "session_started"]
    assert _kinds(first) == ["STREAM_STARTED", "SESSION_STARTED"]
    assert first.snapshot["occurrenceId"] == "1:race:0"

    timeline.observe(_tick(3_000, epoch=1, session=_session(session_num=1, session_time_s=20.0)))
    second = timeline.observe(
        _tick(4_000, epoch=1, session=_session(session_num=2, session_time_s=1.0))
    )
    assert second.snapshot["transitionReasons"] == ["session_ended", "session_started"]
    assert _kinds(second) == ["SESSION_ENDED", "SESSION_STARTED"]
    assert second.snapshot["lineageId"] == "1:qualifying:0>1:race:1"


def test_f31_session_plan_subsets_prefix_and_conflicts() -> None:
    cases = {
        "P": (_row(0, "Practice"),),
        "Q": (_row(1, "Qualify"),),
        "R": (_row(2, "Race"),),
        "PQ": (_row(0, "Practice"), _row(1, "Qualify")),
        "PR": (_row(0, "Practice"), _row(2, "Race")),
        "QR": (_row(1, "Qualify"), _row(2, "Race")),
        "PQR": _pqr_rows(),
    }
    for label, rows in cases.items():
        plan = compile_session_plan(
            sub_session_id="sub:1",
            rows=rows,
            captured_mono_ms=100,
            plan_revision=1,
        )
        assert plan is not None and plan.valid is True, label
        assert (
            tuple(entry.stage for entry in plan.entries)
            == {
                "P": (Stage.PRACTICE,),
                "Q": (Stage.QUALIFYING,),
                "R": (Stage.RACE,),
                "PQ": (Stage.PRACTICE, Stage.QUALIFYING),
                "PR": (Stage.PRACTICE, Stage.RACE),
                "QR": (Stage.QUALIFYING, Stage.RACE),
                "PQR": (Stage.PRACTICE, Stage.QUALIFYING, Stage.RACE),
            }[label]
        )

    timeline = StreamTimeline()
    timeline.observe(_tick(1_000, epoch=0, state="inactive"))
    warmup_rows = (
        _row(0, "Warmup"),
        *_pqr_rows(),
        *(_row(20 + i, f"External-{i}") for i in range(17)),
    )
    live = timeline.observe(
        _tick(
            2_000,
            epoch=1,
            session=_session(session_num=None, rows=warmup_rows, session_time_s=None),
        )
    )
    assert live.snapshot["sessionPlanRevision"] == 1
    assert live.plan is not None and live.plan.valid is True
    assert live.snapshot["sessionRef"] is None
    assert live.plan.unsupported_overflow_count == 2
    assert [item.external_type for item in live.plan.unsupported_entries[:2]] == [
        "Warmup",
        "External-0",
    ]

    repeat = timeline.observe(
        _tick(
            3_000,
            epoch=1,
            session=_session(session_num=1, rows=warmup_rows, session_time_s=8.0),
        )
    )
    assert repeat.snapshot["sessionPlanRevision"] == 1
    assert repeat.snapshot["stage"] == "qualifying"

    future = StreamTimeline()
    future.observe(_tick(1_000, epoch=0, state="inactive"))
    pq = (_row(0, "Practice"), _row(1, "Qualify"))
    future.observe(_tick(2_000, epoch=1, session=_session(session_num=1, rows=pq)))
    grown = future.observe(
        _tick(
            3_000,
            epoch=1,
            session=_session(session_num=1, rows=(*pq, _row(2, "Race"))),
        )
    )
    assert grown.snapshot["sessionPlanRevision"] == 2
    assert [entry.stage.value for entry in grown.plan.entries] == [
        "practice",
        "qualifying",
        "race",
    ]

    latched = future.observe(
        _tick(4_000, epoch=1, session=_session(session_num=1, rows=(_row(1, "Qualify"),)))
    )
    assert latched.plan is not None and latched.plan.valid is False
    assert latched.plan.reason == "session_plan_conflict"
    assert latched.snapshot["sessionRef"] is None
    assert "RESET" in _kinds(latched)

    unavailable = future.observe(
        _tick(
            5_000,
            epoch=1,
            session=_session(availability="partial", session_num=1, rows=()),
        )
    )
    assert unavailable.snapshot["sessionPlanRevision"] == latched.snapshot["sessionPlanRevision"]
    assert "session_suspended" in unavailable.snapshot["transitionReasons"]
    assert unavailable.snapshot["sessionRef"] is None


def test_coherent_invalid_plan_is_not_unavailable_partial() -> None:
    timeline = StreamTimeline()
    timeline.observe(_tick(1_000, epoch=0, state="inactive"))
    conflict = timeline.observe(
        _tick(
            2_000,
            epoch=1,
            session=_session(
                session_num=0,
                rows=(_row(2, "Race"), _row(0, "Practice")),
            ),
        )
    )
    partial = StreamTimeline()
    partial.observe(_tick(1_000, epoch=0, state="inactive"))
    suspended = partial.observe(
        _tick(
            2_000,
            epoch=1,
            session=_session(availability="unavailable", connected=True, rows=()),
        )
    )

    assert conflict.plan is not None and conflict.plan.valid is False
    assert conflict.snapshot["sessionPlanRevision"] == 1
    assert conflict.snapshot["sessionRef"] is None
    assert suspended.plan is None
    assert suspended.snapshot["sessionPlanRevision"] is None
    assert "session_plan_conflict" not in (suspended.snapshot["transitionReasons"])


def test_same_ref_supported_stage_conflict_is_quarantined() -> None:
    timeline = StreamTimeline()
    timeline.observe(_tick(1_000, epoch=0, state="inactive"))
    timeline.observe(
        _tick(
            2_000,
            epoch=1,
            session=_session(session_num=2, rows=(_row(2, "Race"),), session_time_s=20.0),
        )
    )
    step = timeline.observe(
        _tick(
            3_000,
            epoch=1,
            session=_session(session_num=2, rows=(_row(2, "Qualify"),), session_time_s=21.0),
        )
    )

    assert step.snapshot["stage"] == "race"
    assert step.snapshot["occurrenceId"] == "1:race:0"
    assert "SESSION_STARTED" not in _kinds(step)
    assert "RESET" in _kinds(step)
    assert "session_identity_conflict" in step.diagnostics


def test_canonical_progression_and_backward_lineage() -> None:
    timeline = StreamTimeline()
    timeline.observe(_tick(1_000, epoch=0, state="inactive"))
    p0 = timeline.observe(_tick(2_000, epoch=1, session=_session(session_num=0)))
    q0 = timeline.observe(_tick(3_000, epoch=1, session=_session(session_num=1)))
    r0 = timeline.observe(_tick(4_000, epoch=1, session=_session(session_num=2)))
    q1 = timeline.observe(_tick(5_000, epoch=1, session=_session(session_num=1)))
    r1 = timeline.observe(_tick(6_000, epoch=1, session=_session(session_num=2)))

    assert p0.snapshot["lineageId"] == "1:practice:0"
    assert q0.snapshot["lineageId"] == "1:practice:0>1:qualifying:0"
    assert r0.snapshot["lineageId"] == "1:practice:0>1:qualifying:0>1:race:0"
    assert q1.snapshot["lineageId"] == "1:practice:0>1:qualifying:1"
    assert r1.snapshot["lineageId"] == "1:practice:0>1:qualifying:1>1:race:1"
    assert q1.snapshot["transitionReasons"] == [
        "session_ended",
        "session_superseded",
        "session_started",
    ]


def test_replay_is_deterministic_for_the_same_ticks() -> None:
    ticks = (
        _tick(1_000, epoch=0, state="inactive"),
        _tick(2_000, epoch=1, session=_session(session_num=0)),
        _tick(3_000, epoch=1, session=_session(session_num=1)),
        _tick(4_000, epoch=1, state="unknown", session=_session(session_num=1)),
        _tick(5_000, epoch=1, session=_session(session_num=1)),
    )
    first = StreamTimeline()
    second = StreamTimeline()
    left = [first.observe(tick).snapshot for tick in ticks]
    right = [second.observe(tick).snapshot for tick in ticks]
    assert left == right
    for snapshot in left:
        assert _errors(snapshot) == []


def test_snapshot_matches_frozen_timeline_shape() -> None:
    timeline = StreamTimeline()
    timeline.observe(_tick(1_000, epoch=0, state="inactive"))
    step = timeline.observe(_tick(2_000, epoch=1, session=_session(session_num=2)))
    assert _errors(step.snapshot) == []
    assert step.snapshot["schemaVersion"] == "timeline-snapshot/2"


def test_timeline_does_not_import_runtime_or_overlay() -> None:
    source = ROOT / "src/irswitch/logic/stream_timeline.py"
    imports = [
        line
        for line in source.read_text(encoding="utf-8").splitlines()
        if line.startswith("from ") or line.startswith("import ")
    ]
    joined = "\n".join(imports)
    assert "NarrativeRuntime" not in joined
    assert "DetectorBank" not in joined
    assert "overlay.tape" not in joined
    assert "commentary.mailbox" not in joined


def test_compile_session_plan_incomplete_identity_is_conflict() -> None:
    plan = compile_session_plan(
        sub_session_id=None,
        rows=_pqr_rows(),
        captured_mono_ms=1,
        plan_revision=1,
    )
    assert plan.valid is False
    assert plan.reason == "session_plan_conflict"
    assert plan.entries == ()
