"""#275 timing family restart/rewind replay cases (Slice 6).

Closed inventory of restart/rewind replay cases for every timing-family
wire. Records lineage dispositions without rewriting frozen
``docs/v2.0.0/machine/*`` hashes or flipping ``FAMILY_ROUTE``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from .primitives import ContractViolation
from .timing_family_map import (
    SESSION_RECAP_WIRE_IDS,
    TIMING_WIRE_IDS,
    row_for_wire_id,
    timing_family_rows,
)

ReplayScenario = Literal["same_ref_restart", "rewind_superseded", "post_rewind_forward"]
FactScopeKind = Literal["occurrence", "downstream", "historical_only"]
SpeakableAfter = Literal["active_only", "none", "historical_recap"]


@dataclass(frozen=True, slots=True)
class TimingReplayCase:
    """One restart/rewind replay case bound to timing wire ids."""

    case_id: str
    scenario: ReplayScenario
    wire_ids: tuple[str, ...]
    before_occurrence_id: str
    before_lineage_id: str
    after_occurrence_id: str
    after_lineage_id: str
    end_reason: Literal["same_ref_restart", "rewind_superseded"]
    fact_scope: FactScopeKind
    speakable_after: SpeakableAfter
    may_inherit_on_active_lineage: bool
    notes: str = ""


# Stable fixture ids (not live telemetry). Mirror fact-inheritance rewind chain.
_P1 = "1:practice:0"
_Q1 = "1:qualifying:0"
_R1 = "1:race:0"
_Q2 = "1:qualifying:1"
_R2 = "1:race:1"
_P1_L = _P1
_Q1_L = f"{_P1}>{_Q1}"
_R1_L = f"{_P1}>{_Q1}>{_R1}"
_Q2_L = f"{_P1}>{_Q2}"
_R2_L = f"{_P1}>{_Q2}>{_R2}"
_P1_RESTART = "1:practice:1"
_P1_RESTART_L = _P1_RESTART


def timing_family_replay_cases() -> tuple[TimingReplayCase, ...]:
    """Return the closed restart/rewind replay inventory for timing wires."""

    return (
        TimingReplayCase(
            case_id="same_ref_restart:lap_sf",
            scenario="same_ref_restart",
            wire_ids=("LAP_COMPLETE",),
            before_occurrence_id=_P1,
            before_lineage_id=_P1_L,
            after_occurrence_id=_P1_RESTART,
            after_lineage_id=_P1_RESTART_L,
            end_reason="same_ref_restart",
            fact_scope="occurrence",
            speakable_after="none",
            may_inherit_on_active_lineage=False,
            notes="Lap identity includes occurrence; restart must not reuse prior lap candidate.",
        ),
        TimingReplayCase(
            case_id="same_ref_restart:sector",
            scenario="same_ref_restart",
            wire_ids=("SECTOR_SPLIT", "SECTOR_BEST"),
            before_occurrence_id=_P1,
            before_lineage_id=_P1_L,
            after_occurrence_id=_P1_RESTART,
            after_lineage_id=_P1_RESTART_L,
            end_reason="same_ref_restart",
            fact_scope="occurrence",
            speakable_after="none",
            may_inherit_on_active_lineage=False,
            notes="Sector splits/bests die with the restarted occurrence.",
        ),
        TimingReplayCase(
            case_id="same_ref_restart:pace_delta",
            scenario="same_ref_restart",
            wire_ids=("GAIN_FOUND", "TIME_LOST"),
            before_occurrence_id=_Q1,
            before_lineage_id=_Q1_L,
            after_occurrence_id=_Q2,
            after_lineage_id=_Q2_L,
            end_reason="same_ref_restart",
            fact_scope="occurrence",
            speakable_after="none",
            may_inherit_on_active_lineage=False,
            notes="Pace gain/loss are transient occurrence updates; restart clears live speakables.",
        ),
        TimingReplayCase(
            case_id="same_ref_restart:attempt_projection",
            scenario="same_ref_restart",
            wire_ids=("HOT_LAP", "PROJECTED_LAP"),
            before_occurrence_id=_Q1,
            before_lineage_id=_Q1_L,
            after_occurrence_id=_Q2,
            after_lineage_id=_Q2_L,
            end_reason="same_ref_restart",
            fact_scope="occurrence",
            speakable_after="none",
            may_inherit_on_active_lineage=False,
            notes="Hot/projected attempts are live-story scoped to the active occurrence.",
        ),
        TimingReplayCase(
            case_id="same_ref_restart:invalid_lap",
            scenario="same_ref_restart",
            wire_ids=("INVALID_LAP",),
            before_occurrence_id=_Q1,
            before_lineage_id=_Q1_L,
            after_occurrence_id=_Q2,
            after_lineage_id=_Q2_L,
            end_reason="same_ref_restart",
            fact_scope="occurrence",
            speakable_after="none",
            may_inherit_on_active_lineage=False,
            notes="Invalid-lap remains PRACTICE|QUALIFYING scoped and occurrence-local after restart.",
        ),
        TimingReplayCase(
            case_id="same_ref_restart:session_intro",
            scenario="same_ref_restart",
            wire_ids=(
                "SESSION_INTRO_PRACTICE",
                "SESSION_INTRO_QUALIFY",
                "SESSION_INTRO_RACE",
            ),
            before_occurrence_id=_R1,
            before_lineage_id=_R1_L,
            after_occurrence_id=_R2,
            after_lineage_id=_R2_L,
            end_reason="same_ref_restart",
            fact_scope="occurrence",
            speakable_after="active_only",
            may_inherit_on_active_lineage=False,
            notes="Session intros require the new active occurrence; prior intro is not inherited.",
        ),
        TimingReplayCase(
            case_id="rewind_superseded:race_timing",
            scenario="rewind_superseded",
            wire_ids=("LAP_COMPLETE", "SECTOR_SPLIT", "SECTOR_BEST", "GAIN_FOUND", "TIME_LOST"),
            before_occurrence_id=_R1,
            before_lineage_id=_R1_L,
            after_occurrence_id=_Q2,
            after_lineage_id=_Q2_L,
            end_reason="rewind_superseded",
            fact_scope="occurrence",
            speakable_after="none",
            may_inherit_on_active_lineage=False,
            notes="Rewind race→qualifying supersedes race timing speakables on the old lineage.",
        ),
        TimingReplayCase(
            case_id="rewind_superseded:quali_result_historical",
            scenario="rewind_superseded",
            wire_ids=("QUALI_RECAP",),
            before_occurrence_id=_Q1,
            before_lineage_id=_Q1_L,
            after_occurrence_id=_Q2,
            after_lineage_id=_Q2_L,
            end_reason="rewind_superseded",
            fact_scope="historical_only",
            speakable_after="historical_recap",
            may_inherit_on_active_lineage=False,
            notes="Superseded qualifying result needs explicit historical/recap framing.",
        ),
        TimingReplayCase(
            case_id="post_rewind_forward:personal_best_inherits",
            scenario="post_rewind_forward",
            wire_ids=("PERSONAL_BEST",),
            before_occurrence_id=_P1,
            before_lineage_id=_P1_L,
            after_occurrence_id=_R2,
            after_lineage_id=_R2_L,
            end_reason="rewind_superseded",
            fact_scope="downstream",
            speakable_after="active_only",
            may_inherit_on_active_lineage=True,
            notes="Practice personal best may inherit on the active post-rewind lineage only.",
        ),
        TimingReplayCase(
            case_id="post_rewind_forward:quali_recap_active_only",
            scenario="post_rewind_forward",
            wire_ids=("QUALI_RECAP",),
            before_occurrence_id=_Q1,
            before_lineage_id=_Q1_L,
            after_occurrence_id=_R2,
            after_lineage_id=_R2_L,
            end_reason="rewind_superseded",
            fact_scope="downstream",
            speakable_after="active_only",
            may_inherit_on_active_lineage=True,
            notes="Race quali recap inherits active Q2 result, never superseded Q1 as live.",
        ),
        TimingReplayCase(
            case_id="post_rewind_forward:session_intro_race",
            scenario="post_rewind_forward",
            wire_ids=("SESSION_INTRO_RACE",),
            before_occurrence_id=_R1,
            before_lineage_id=_R1_L,
            after_occurrence_id=_R2,
            after_lineage_id=_R2_L,
            end_reason="rewind_superseded",
            fact_scope="occurrence",
            speakable_after="active_only",
            may_inherit_on_active_lineage=False,
            notes="New race intro after rewind attaches to R2 active lineage only.",
        ),
        TimingReplayCase(
            case_id="post_rewind_forward:attempt_on_new_quali",
            scenario="post_rewind_forward",
            wire_ids=("HOT_LAP", "PROJECTED_LAP", "INVALID_LAP"),
            before_occurrence_id=_Q1,
            before_lineage_id=_Q1_L,
            after_occurrence_id=_Q2,
            after_lineage_id=_Q2_L,
            end_reason="rewind_superseded",
            fact_scope="occurrence",
            speakable_after="active_only",
            may_inherit_on_active_lineage=False,
            notes="New qualifying attempts after rewind are Q2-local; Q1 attempts stay superseded.",
        ),
    )


def cases_for_wire_id(wire_id: str) -> tuple[TimingReplayCase, ...]:
    """Return replay cases that mention ``wire_id``."""

    if wire_id not in TIMING_WIRE_IDS:
        raise ContractViolation(f"unknown timing wire id: {wire_id}")
    return tuple(case for case in timing_family_replay_cases() if wire_id in case.wire_ids)


def restart_rewind_replay_cases_are_complete() -> bool:
    """Slice 6 helper: every timing wire appears; scenarios and lineage rules hold."""

    cases = timing_family_replay_cases()
    if not cases:
        return False
    covered: set[str] = set()
    scenarios: set[str] = set()
    for case in cases:
        if not case.case_id or not case.wire_ids:
            return False
        if case.end_reason not in {"same_ref_restart", "rewind_superseded"}:
            return False
        if case.scenario == "same_ref_restart" and case.end_reason != "same_ref_restart":
            return False
        if case.scenario == "rewind_superseded" and case.end_reason != "rewind_superseded":
            return False
        if case.before_occurrence_id == case.after_occurrence_id:
            return False
        if case.before_lineage_id == case.after_lineage_id:
            return False
        if case.may_inherit_on_active_lineage and case.speakable_after == "none":
            return False
        if case.speakable_after == "historical_recap" and case.fact_scope != "historical_only":
            return False
        for wire_id in case.wire_ids:
            if wire_id not in TIMING_WIRE_IDS:
                return False
            covered.add(wire_id)
            row = row_for_wire_id(wire_id)
            if wire_id in SESSION_RECAP_WIRE_IDS and not row.requires_active_lineage:
                return False
        scenarios.add(case.scenario)

    if covered != set(TIMING_WIRE_IDS):
        return False
    if scenarios != {"same_ref_restart", "rewind_superseded", "post_rewind_forward"}:
        return False

    # Recap wires must appear in at least one active-lineage-sensitive case.
    for wire_id in SESSION_RECAP_WIRE_IDS:
        recap_cases = cases_for_wire_id(wire_id)
        if not recap_cases:
            return False
        if not any(
            case.speakable_after in {"active_only", "historical_recap"} for case in recap_cases
        ):
            return False

    # Downstream inherit is reserved for PERSONAL_BEST / QUALI_RECAP post-rewind cases.
    inherit_wires = {
        wire_id for case in cases if case.may_inherit_on_active_lineage for wire_id in case.wire_ids
    }
    if inherit_wires != {"PERSONAL_BEST", "QUALI_RECAP"}:
        return False

    # Inventory rows still legacy; this slice does not activate speech.
    if any(row.migration_status != "legacy" for row in timing_family_rows()):
        return False
    return True
