"""TDD contract tests for the bounded serializable v2 SessionPlan."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from irswitch.contracts import (
    ContractViolation,
    MonotonicMs,
    SessionPlan,
    SessionPlanEntry,
    SessionRef,
    Stage,
    UnsupportedSessionEntry,
    packaged_schema_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
FROZEN_MACHINE = ROOT / "docs" / "v2.0.0" / "machine"


def _entry(sub_session_id: str, session_num: int, stage: Stage) -> SessionPlanEntry:
    return SessionPlanEntry(SessionRef(sub_session_id, session_num), stage)


def test_valid_session_plan_round_trip_uses_exact_lower_camel_wire_shape() -> None:
    plan = SessionPlan.valid_plan(
        plan_revision=4,
        captured_mono_ms=MonotonicMs(9_000),
        sub_session_id="sub:42",
        entries=(
            _entry("sub:42", 0, Stage.PRACTICE),
            _entry("sub:42", 2, Stage.RACE),
        ),
        unsupported_entries=(UnsupportedSessionEntry(1, "Warmup"),),
    )

    expected = {
        "schemaVersion": "session-plan/2",
        "planRevision": 4,
        "capturedMonoMs": 9_000,
        "subSessionId": "sub:42",
        "valid": True,
        "reason": None,
        "entries": [
            {
                "sessionRef": {"subSessionId": "sub:42", "sessionNum": 0},
                "stage": "practice",
            },
            {
                "sessionRef": {"subSessionId": "sub:42", "sessionNum": 2},
                "stage": "race",
            },
        ],
        "unsupportedEntries": [{"sessionNum": 1, "externalType": "Warmup"}],
        "unsupportedOverflowCount": 0,
    }
    assert plan.to_dict() == expected
    assert SessionPlan.from_dict(json.loads(json.dumps(expected))) == plan
    assert SessionPlan.from_dict(plan.to_dict()).to_dict() == expected


def test_unsupported_rows_are_bounded_with_exact_overflow_count() -> None:
    unsupported = tuple(UnsupportedSessionEntry(index, f"External-{index}") for index in range(19))

    plan = SessionPlan.valid_plan(
        plan_revision=1,
        captured_mono_ms=MonotonicMs(100),
        sub_session_id="sub:1",
        entries=(_entry("sub:1", 20, Stage.RACE),),
        unsupported_entries=unsupported,
    )

    assert len(plan.unsupported_entries) == 16
    assert plan.unsupported_entries[0].session_num == 0
    assert plan.unsupported_entries[-1].session_num == 15
    assert plan.unsupported_overflow_count == 3
    assert plan.to_dict()["unsupportedOverflowCount"] == 3


def test_invalid_session_plan_is_serializable_and_carries_no_supported_entries() -> None:
    plan = SessionPlan.conflict(
        plan_revision=7,
        captured_mono_ms=MonotonicMs(200),
        sub_session_id=None,
        unsupported_entries=(UnsupportedSessionEntry(3, "Warmup"),),
    )

    assert plan.valid is False
    assert plan.reason == "session_plan_conflict"
    assert plan.entries == ()
    assert SessionPlan.from_dict(plan.to_dict()) == plan


@pytest.mark.parametrize(
    "entries",
    [
        (),
        (
            _entry("sub:1", 0, Stage.RACE),
            _entry("sub:1", 1, Stage.QUALIFYING),
        ),
        (
            _entry("sub:1", 0, Stage.PRACTICE),
            _entry("sub:1", 1, Stage.PRACTICE),
        ),
        (_entry("different", 0, Stage.PRACTICE),),
    ],
)
def test_valid_plan_rejects_empty_or_incoherent_entries(
    entries: tuple[SessionPlanEntry, ...],
) -> None:
    with pytest.raises(ContractViolation):
        SessionPlan.valid_plan(
            plan_revision=1,
            captured_mono_ms=MonotonicMs(100),
            sub_session_id="sub:1",
            entries=entries,
        )


def test_session_plan_parser_rejects_unknown_fields_and_wrong_version() -> None:
    plan = SessionPlan.conflict(
        plan_revision=1,
        captured_mono_ms=MonotonicMs(100),
        sub_session_id=None,
    ).to_dict()
    plan["unexpected"] = True
    with pytest.raises(ContractViolation):
        SessionPlan.from_dict(plan)

    plan.pop("unexpected")
    plan["schemaVersion"] = "session-plan/3"
    with pytest.raises(ContractViolation):
        SessionPlan.from_dict(plan)


def test_session_plan_parser_rejects_unbounded_or_inconsistent_wire_values() -> None:
    plan = SessionPlan.valid_plan(
        plan_revision=1,
        captured_mono_ms=MonotonicMs(100),
        sub_session_id="sub:1",
        entries=(_entry("sub:1", 0, Stage.PRACTICE),),
    ).to_dict()

    plan["unsupportedEntries"] = [
        {"sessionNum": index, "externalType": "Other"} for index in range(17)
    ]
    with pytest.raises(ContractViolation):
        SessionPlan.from_dict(plan)

    plan["unsupportedEntries"] = []
    plan["valid"] = False
    plan["reason"] = "session_plan_conflict"
    with pytest.raises(ContractViolation):
        SessionPlan.from_dict(plan)


@pytest.mark.parametrize("name", ["freeze-registry.json", "dto-contracts.schema.json"])
def test_packaged_schema_loader_returns_frozen_bytes(name: str) -> None:
    assert packaged_schema_bytes(name) == (FROZEN_MACHINE / name).read_bytes()


def test_packaged_schema_loader_rejects_unknown_or_traversal_names() -> None:
    with pytest.raises(ContractViolation):
        packaged_schema_bytes("unknown.json")
    with pytest.raises(ContractViolation):
        packaged_schema_bytes("../freeze-registry.json")
