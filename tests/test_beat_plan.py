"""#261 immutable BeatPlan and just-in-time planner."""

from __future__ import annotations

import json
from pathlib import Path

from irswitch.events import __all__ as events_exports
from irswitch.events.beat_plan import (
    SCHEMA_VERSION,
    BeatPlanner,
    BoundClaim,
    CandidateOrder,
    FunnelLink,
    PlanIntent,
    PromptOptions,
    tight_prompt_options,
)

SOURCE = Path(__file__).resolve().parents[1] / "src" / "irswitch" / "events" / "beat_plan.py"
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "beat_plan"
HASH = "sha256:" + ("ab" * 32)


def _claim(
    fact_id: str = "fact:lap-1",
    *,
    predicate: str = "timing.lap_completed",
    claim_id: str = "claim:lap",
    attributes: tuple[str, ...] = ("lap",),
) -> BoundClaim:
    return BoundClaim(
        claim_id=claim_id,
        predicate=predicate,
        subject_id="hero",
        object_id=None,
        polarity="positive",
        temporal_frame="current",
        attributes=attributes,
        fact_ids=(fact_id,),
    )


def _funnel(
    *,
    source_class: str = "detector",
    opportunity_id: str | None = "opp:1",
    tape_channel: str = "race.timing.lap",
) -> FunnelLink:
    return FunnelLink(
        source_class=source_class,
        candidate_id="cand:1",
        detector_observation_id=None,
        event_id="event:1",
        material_revision=1,
        opportunity_id=opportunity_id,
        plan_id=None,
        utterance_id=None,
        tape_channel=tape_channel,
    )


def _intent(**overrides: object) -> PlanIntent:
    values: dict[str, object] = {
        "beat_id": "timing.lap.completed",
        "episode_id": "episode:lap-1",
        "episode_revision": 1,
        "stream_epoch": 1,
        "occurrence_id": "3:race:0",
        "lineage_id": "3:practice:0>3:race:0",
        "candidate_source": "event_opportunity",
        "funnel": _funnel(),
        "opportunity_id": "opp:1",
        "required_claims": (_claim(),),
        "optional_claims": (),
        "source_refs": ("event:lap-1",),
        "catalog_hash": HASH,
        "effective_config_hash": HASH,
        "config_apply_sequence": 1,
        "fact_view_revision": 1,
        "planned_mono_ms": 10_000,
        "expires_mono_ms": 40_000,
        "story_id": "timing_attempt",
        "speech_complete": False,
        "is_closing": True,
        "is_critical": False,
        "consecutive_accepted": 0,
        "future_beat_ids": (),
        "max_chars": 160,
        "max_seconds": 8.0,
        "style_card_id": None,
        "realization_pattern": "timing.lap.completed:tight:1",
        "candidate_order": CandidateOrder(reducer_sequence=40, source_ordinal=3),
    }
    values.update(overrides)
    return PlanIntent(**values)  # type: ignore[arg-type]


def test_beat_plan_round_trips_deterministically() -> None:
    planner = BeatPlanner()
    step = planner.plan(_intent(), lane="idle", planning_cycle_id="cycle-1")
    assert step.reason == "planned"
    assert step.plan is not None
    assert step.plan.schema_version == SCHEMA_VERSION
    assert step.plan.cycle_attempt_ordinal == 1
    assert step.plan.language == "en"
    assert step.plan.prompt_options.max_sentences == 1
    rebuilt = step.plan.from_dict(step.plan.to_dict())
    assert rebuilt == step.plan
    assert rebuilt.to_dict() == step.plan.to_dict()


def test_selected_claims_require_fact_refs() -> None:
    planner = BeatPlanner()
    missing = _claim()
    missing = BoundClaim(
        claim_id="claim:lap",
        predicate="timing.lap_completed",
        subject_id="hero",
        object_id=None,
        polarity="positive",
        temporal_frame="current",
        attributes=("lap",),
        fact_ids=(),
    )
    step = planner.plan(_intent(required_claims=(missing,)), lane="idle", planning_cycle_id="c")
    assert step.reason == "source_guard_failed"
    assert step.plan is None


def test_no_plan_while_speech_lane_busy() -> None:
    planner = BeatPlanner()
    for lane in ("building", "committed", "speaking", "stopping"):
        step = planner.plan(_intent(), lane=lane, planning_cycle_id="busy")
        assert step.reason == "lane_busy"
        assert step.plan is None


def test_plan_does_not_consume_opportunity_or_future_beats() -> None:
    planner = BeatPlanner()
    ok = planner.plan(_intent(), lane="idle", planning_cycle_id="cyc-a")
    assert ok.opportunity_consumed is False
    assert ok.plan is not None
    assert ok.plan.opportunity_id == "opp:1"

    future = planner.plan(
        _intent(future_beat_ids=("timing.pace.gain",)),
        lane="idle",
        planning_cycle_id="cyc-b",
    )
    assert future.reason == "future_successor_forbidden"
    assert future.plan is None
    assert future.opportunity_consumed is False


def test_stream_and_lobby_may_omit_occurrence() -> None:
    planner = BeatPlanner()
    stream = planner.plan(
        _intent(
            beat_id="stream.started",
            episode_id="episode:stream-1",
            occurrence_id=None,
            lineage_id=None,
            candidate_source="event_opportunity",
            opportunity_id=None,
            required_claims=(
                BoundClaim(
                    claim_id="claim:stream",
                    predicate="stream.started",
                    subject_id=None,
                    object_id=None,
                    polarity="positive",
                    temporal_frame="current",
                    attributes=("startReason",),
                    fact_ids=("fact:stream-1",),
                ),
            ),
            source_refs=("event:stream",),
            story_id="stream_lifecycle",
            is_closing=False,
            is_critical=True,
            realization_pattern="stream.started:tight:1",
            funnel=_funnel(
                source_class="lifecycle",
                opportunity_id=None,
                tape_channel="stream.lifecycle",
            ),
        ),
        lane="idle",
        planning_cycle_id="stream",
    )
    assert stream.reason == "planned"
    assert stream.plan is not None
    assert stream.plan.occurrence_id is None
    assert stream.plan.lineage_id is None

    other = planner.plan(
        _intent(occurrence_id=None, lineage_id=None, is_closing=True),
        lane="idle",
        planning_cycle_id="need-occ",
    )
    assert other.reason == "source_guard_failed"


def test_dedup_preserves_all_source_refs() -> None:
    planner = BeatPlanner()
    first = planner.plan(_intent(source_refs=("event:a",)), lane="idle", planning_cycle_id="d1")
    second = planner.plan(
        _intent(source_refs=("event:a", "event:b")),
        lane="idle",
        planning_cycle_id="d1",
    )
    assert second.reason == "deduped"
    assert second.plan is not None
    assert second.plan.plan_id == first.plan.plan_id  # type: ignore[union-attr]
    assert second.plan.source_refs == ("event:a", "event:b")
    assert second.plan.cycle_attempt_ordinal == 1


def test_planning_cycle_allows_one_alternative_then_exhausts() -> None:
    planner = BeatPlanner()
    first = planner.plan(_intent(), lane="idle", planning_cycle_id="cyc")
    alt = planner.plan(
        _intent(beat_id="position.pass", episode_id="episode:pass-1", is_critical=True),
        lane="idle",
        planning_cycle_id="cyc",
    )
    assert first.plan is not None
    assert alt.reason == "planned"
    assert alt.plan is not None
    assert alt.plan.cycle_attempt_ordinal == 2
    assert alt.plan.planning_cycle_id == "cyc"
    third = planner.plan(
        _intent(beat_id="session.flag.yellow", episode_id="episode:flag-1", is_critical=True),
        lane="idle",
        planning_cycle_id="cyc",
    )
    assert third.reason == "planning_cycle_exhausted"
    assert third.plan is None


def test_candidate_order_is_stable_age_authority() -> None:
    planner = BeatPlanner()
    older = CandidateOrder(reducer_sequence=40, source_ordinal=3)
    newer = CandidateOrder(reducer_sequence=40, source_ordinal=4)
    assert older.key() < newer.key()
    step = planner.plan(_intent(candidate_order=older), lane="idle", planning_cycle_id="ord")
    assert step.plan is not None
    assert step.plan.candidate_order == older


def test_half_open_expiry_and_tts_budget() -> None:
    planner = BeatPlanner()
    step = planner.plan(
        _intent(planned_mono_ms=40_000, expires_mono_ms=50_000, max_chars=160),
        lane="idle",
        planning_cycle_id="exp",
    )
    plan = step.plan
    assert plan is not None
    assert plan.is_valid_at(40_000)
    assert plan.is_valid_at(49_999)
    assert not plan.is_valid_at(39_999)
    assert not plan.is_valid_at(50_000)
    assert plan.prompt_options.max_sentences == 1
    assert 1 <= plan.max_chars <= 512
    assert plan.prompt_options == tight_prompt_options(
        stream_epoch=1,
        opportunity_id="opp:1",
        episode_id="episode:lap-1",
        episode_revision=1,
        beat_id="timing.lap.completed",
        cycle_attempt_ordinal=1,
    )


def test_consecutive_cap_spares_closure_and_critical() -> None:
    planner = BeatPlanner()
    blocked = planner.plan(
        _intent(
            is_closing=False,
            is_critical=False,
            consecutive_accepted=2,
            story_id="timing_attempt",
            beat_id="timing.pace.gain",
            episode_id="episode:pace-1",
            required_claims=(
                BoundClaim(
                    claim_id="claim:delta",
                    predicate="timing.delta_improved",
                    subject_id="hero",
                    object_id=None,
                    polarity="positive",
                    temporal_frame="current",
                    attributes=("delta",),
                    fact_ids=("fact:delta-1",),
                ),
            ),
            realization_pattern="timing.pace.gain:tight:1",
        ),
        lane="idle",
        planning_cycle_id="cap-1",
    )
    assert blocked.reason == "consecutive_cap"

    closing = planner.plan(
        _intent(is_closing=True, consecutive_accepted=2, story_id="timing_attempt"),
        lane="idle",
        planning_cycle_id="cap-2",
    )
    assert closing.reason == "planned"

    critical = planner.plan(
        _intent(
            beat_id="position.pass",
            episode_id="episode:pass-2",
            is_closing=False,
            is_critical=True,
            consecutive_accepted=2,
            story_id="timing_attempt",
            required_claims=(
                BoundClaim(
                    claim_id="claim:pass",
                    predicate="position.passed",
                    subject_id="hero",
                    object_id="car.22",
                    polarity="positive",
                    temporal_frame="current",
                    attributes=("oldPasserPosition", "newPasserPosition"),
                    fact_ids=("fact:pass-1",),
                ),
            ),
            realization_pattern="position.pass:tight:1",
        ),
        lane="idle",
        planning_cycle_id="cap-3",
    )
    assert critical.reason == "planned"


def test_self_contained_outcomes_remain_selectable() -> None:
    planner = BeatPlanner()
    result = planner.plan(
        _intent(speech_complete=True, is_closing=True), lane="idle", planning_cycle_id="sc-1"
    )
    assert result.reason == "planned"

    intermediate = planner.plan(
        _intent(
            beat_id="timing.pace.gain",
            episode_id="episode:pace-2",
            speech_complete=True,
            is_closing=False,
            is_critical=False,
            required_claims=(
                BoundClaim(
                    claim_id="claim:delta2",
                    predicate="timing.delta_improved",
                    subject_id="hero",
                    object_id=None,
                    polarity="positive",
                    temporal_frame="current",
                    attributes=("delta",),
                    fact_ids=("fact:delta-2",),
                ),
            ),
            realization_pattern="timing.pace.gain:tight:1",
        ),
        lane="idle",
        planning_cycle_id="sc-2",
    )
    assert intermediate.reason == "not_self_contained"


def test_full_ledger_dump_is_forbidden() -> None:
    planner = BeatPlanner()
    extras = tuple(f"fact:extra-{index}" for index in range(8))
    step = planner.plan(
        _intent(selected_fact_ids=("fact:lap-1",) + extras),
        lane="idle",
        planning_cycle_id="dump",
    )
    assert step.reason == "ledger_dump_forbidden"
    assert step.plan is None


def test_replay_fixtures_cover_transition_identity_and_expiry() -> None:
    planner = BeatPlanner()
    transition = json.loads((FIXTURES / "transition.json").read_text(encoding="utf-8"))
    claims = tuple(
        BoundClaim(
            claim_id=item["claimId"],
            predicate=item["predicate"],
            subject_id=item["subjectId"],
            object_id=item["objectId"],
            polarity=item["polarity"],
            temporal_frame=item["temporalFrame"],
            attributes=tuple(item["attributes"]),
            fact_ids=tuple(item["factIds"]),
        )
        for item in transition["intent"]["requiredClaims"]
    )
    step = planner.plan(
        _intent(
            beat_id=transition["intent"]["beatId"],
            episode_id=transition["intent"]["episodeId"],
            source_refs=tuple(transition["intent"]["sourceRefs"]),
            required_claims=claims,
            is_closing=True,
        ),
        lane=transition["lane"],
        planning_cycle_id=transition["planningCycleId"],
    )
    assert step.reason == transition["expect"]["reason"]
    assert step.plan is not None
    assert step.plan.cycle_attempt_ordinal == transition["expect"]["cycleAttemptOrdinal"]
    assert step.opportunity_consumed is transition["expect"]["opportunityConsumed"]

    identity = json.loads((FIXTURES / "counterfactual_identity.json").read_text(encoding="utf-8"))
    planner = BeatPlanner()
    first_id = None
    for item in identity["steps"]:
        result = planner.plan(
            _intent(
                episode_revision=item["episodeRevision"],
                source_refs=tuple(item["sourceRefs"]),
            ),
            lane=identity["lane"],
            planning_cycle_id=identity["planningCycleId"],
        )
        assert result.reason == item["expect"]
        if item["expect"] == "planned":
            first_id = first_id or result.plan.plan_id  # type: ignore[union-attr]
        if item["expect"] == "deduped":
            assert result.plan is not None
            assert result.plan.plan_id == first_id
            assert result.plan.source_refs == ("event:a", "event:c")

    expiry = json.loads((FIXTURES / "expiry.json").read_text(encoding="utf-8"))
    plan = (
        BeatPlanner()
        .plan(
            _intent(
                episode_id="episode:exp-1",
                planned_mono_ms=expiry["plannedMonoMs"],
                expires_mono_ms=expiry["expiresMonoMs"],
            ),
            lane="idle",
            planning_cycle_id="fix-exp",
        )
        .plan
    )
    assert plan is not None
    for now in expiry["validAt"]:
        assert plan.is_valid_at(now)
    for now in expiry["invalidAt"]:
        assert not plan.is_valid_at(now)


def test_prompt_options_baseline_is_tight_and_exports_stay_out() -> None:
    options = PromptOptions.tight(seed=1)
    assert options.freedom == "tight"
    assert options.pattern_choice == "fixed"
    assert options.optional_claim_limit == 0
    assert options.max_sentences == 1
    source = SOURCE.read_text(encoding="utf-8")
    assert "beat_plan" not in events_exports
    for banned in (
        "NarrativeRuntime",
        "eval(",
        "exec(",
        "compile(",
        "irswitch.commentary",
        "irswitch.overlay",
        "TtsUtterance",
    ):
        assert banned not in source
