"""#283 EventOpportunity queue and post-beat event-versus-successor policy."""

from __future__ import annotations

import json
from pathlib import Path

from irswitch.contracts.coverage_matrix import can_create_event_opportunity
from irswitch.events import __all__ as events_exports
from irswitch.events.beat_plan import CandidateOrder
from irswitch.events.exposure_store import SCHEMA_VERSION as EXPOSURE_SCHEMA
from irswitch.events.exposure_store import ChannelPressureView
from irswitch.events.opportunity_queue import (
    OPPORTUNITY_CAPACITY,
    POLICY_PROFILES,
    SCHEMA_VERSION,
    SELECTION_THRESHOLD,
    SWITCH_MARGIN,
    ArbitrationContext,
    EpisodeBeatRef,
    EventOpportunity,
    OpportunityIntent,
    OpportunityQueue,
)

SOURCE = (
    Path(__file__).resolve().parents[1] / "src" / "irswitch" / "events" / "opportunity_queue.py"
)
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "opportunity_queue"
HASH = "sha256:" + ("ab" * 32)
OCCURRENCE = "3:race:0"
LINEAGE = "3:practice:0>3:race:0"


def _intent(**overrides: object) -> OpportunityIntent:
    values: dict[str, object] = {
        "opportunity_id": "opp:1",
        "event_id": "event:1",
        "event_kind": "battle.pursuit",
        "current_identifier": "HUNTING",
        "source_class": "detector",
        "candidate_id": "cand:1",
        "detector_observation_id": "obs:1",
        "stream_epoch": 3,
        "occurrence_id": OCCURRENCE,
        "lineage_id": LINEAGE,
        "episode_id": "episode:battle-1",
        "correlation_key": ("hero", "car.22"),
        "tape_channel": None,
        "policy_id": "live_story",
        "created_mono_ms": 10_000,
        "material_revision": 1,
        "source_fact_ids": ("fact:closing-1",),
        "candidate_order": CandidateOrder(reducer_sequence=4, source_ordinal=1),
        "source_order": None,
        "relation": "opens",
        "beat_id": "battle.pursuit",
        "beat_ids": ("battle.pursuit", "battle.approach"),
        "story_id": "battle_ahead",
        "semantic_identity": ("hero", "car.22", "battle"),
    }
    values.update(overrides)
    return OpportunityIntent(**values)  # type: ignore[arg-type]


def _ctx(**overrides: object) -> ArbitrationContext:
    values: dict[str, object] = {
        "now_ms": 10_000,
        "stream_epoch": 3,
        "focused_episode_id": "episode:battle-1",
        "focused_story_id": "battle_ahead",
        "last_spoken_beat_id": None,
        "last_spoken_episode_id": None,
        "focused_material_order": CandidateOrder(0, 0),
        "last_global_spoken_ms": None,
        "last_channel_spoken_ms": {},
        "last_semantic_spoken_ms": {},
        "last_episode_spoken_ms": {},
        "spoken_semantic_revisions": {},
        "valid_successor_targets": (),
        "episode_beats": (),
        "channel_pressure": None,
        "silence_impulse": False,
    }
    values.update(overrides)
    return ArbitrationContext(**values)  # type: ignore[arg-type]


def test_opportunity_round_trips_without_text_or_plan() -> None:
    queue = OpportunityQueue()
    step = queue.admit(_intent())
    assert step.reason == "queued"
    assert step.opportunity is not None
    assert step.opportunity.schema_version == SCHEMA_VERSION
    rebuilt = EventOpportunity.from_dict(step.opportunity.to_dict())
    assert rebuilt == step.opportunity
    payload = step.opportunity.to_dict()
    assert "text" not in payload
    assert "prompt" not in payload
    assert "beatPlan" not in payload
    assert "promptOptions" not in payload
    assert can_create_event_opportunity("HUNTING") is True


def test_silence_and_stream_scope_identity() -> None:
    queue = OpportunityQueue()
    silence = queue.admit(
        _intent(
            opportunity_id="opp:silence",
            event_id=None,
            event_kind="filler.lobby",
            current_identifier=None,
            source_class="silence",
            candidate_id=None,
            detector_observation_id=None,
            occurrence_id=None,
            lineage_id=None,
            episode_id="episode:lobby",
            correlation_key=(),
            policy_id="filler",
            relation="independent",
            beat_id="filler.lobby",
            beat_ids=("filler.lobby",),
            story_id="filler_single",
            semantic_identity=("lobby",),
            source_fact_ids=("fact:track-1",),
        )
    )
    assert silence.reason == "queued"
    assert silence.opportunity is not None
    assert silence.opportunity.event_id is None
    assert silence.opportunity.funnel.source_class == "silence"

    started = queue.admit(
        _intent(
            opportunity_id="opp:stream",
            event_id="event:stream",
            event_kind="stream.started",
            current_identifier=None,
            source_class="lifecycle",
            candidate_id="cand:stream",
            detector_observation_id=None,
            occurrence_id=None,
            lineage_id=None,
            episode_id="episode:stream",
            correlation_key=(),
            policy_id="critical",
            relation="opens",
            beat_id="stream.started",
            beat_ids=("stream.started",),
            story_id="stream_lifecycle",
            semantic_identity=("stream",),
            source_fact_ids=("fact:stream-1",),
        )
    )
    assert started.reason == "queued"
    assert started.opportunity is not None
    assert started.opportunity.occurrence_id is None


def test_alias_and_visual_never_admit() -> None:
    queue = OpportunityQueue()
    alias = queue.admit(_intent(current_identifier="BATTLE_LOST"))
    visual = queue.admit(_intent(opportunity_id="opp:2", current_identifier="BLE_LOST"))
    assert alias.reason == "not_speakable"
    assert visual.reason == "not_speakable"
    assert alias.opportunity is None
    assert can_create_event_opportunity("BATTLE_LOST") is False
    assert can_create_event_opportunity("BLE_LOST") is False


def test_policy_profiles_snapshot_ttl_and_urgency() -> None:
    queue = OpportunityQueue()
    created = 20_000
    expected = {
        "critical": (90.0, "critical", 45_000, 0.25),
        "result": (78.0, "story", 30_000, 0.50),
        "live_story": (64.0, "story", 10_000, 0.80),
        "transient": (56.0, "story", 6_000, 1.00),
        "context": (46.0, "context", 20_000, 1.00),
        "filler": (24.0, "background", 12_000, 1.40),
    }
    assert tuple(item[0] for item in POLICY_PROFILES) == (
        "critical",
        "result",
        "live_story",
        "transient",
        "context",
        "filler",
    )
    for index, (policy_id, values) in enumerate(expected.items(), start=1):
        filler = policy_id == "filler"
        step = queue.admit(
            _intent(
                opportunity_id=f"opp:pol-{index}",
                event_id=None if filler else f"event:pol-{index}",
                policy_id=policy_id,
                created_mono_ms=created,
                candidate_order=CandidateOrder(index, 0),
                current_identifier=None if filler else "HUNTING",
                source_class="silence" if filler else "detector",
                event_kind="filler.quiet_track" if filler else "battle.pursuit",
                beat_id="filler.quiet_track" if filler else "battle.pursuit",
                beat_ids=(("filler.quiet_track",) if filler else ("battle.pursuit",)),
                candidate_id=None if filler else "cand:1",
                detector_observation_id=None if filler else "obs:1",
            )
        )
        assert step.opportunity is not None
        priority, urgency, ttl, penalty = values
        assert step.opportunity.base_priority == priority
        assert step.opportunity.urgency == urgency
        assert step.opportunity.expires_mono_ms == created + ttl
        assert step.opportunity.penalty_coefficient == penalty


def test_half_open_ttl_and_expiry_cancels_reservation() -> None:
    queue = OpportunityQueue()
    admitted = queue.admit(_intent())
    opportunity = admitted.opportunity
    assert opportunity is not None
    assert opportunity.is_valid_at(10_000)
    assert opportunity.is_valid_at(19_999)
    assert not opportunity.is_valid_at(20_000)
    reserved = queue.reserve(opportunity.opportunity_id, now_ms=11_000)
    assert reserved.reason == "reserved"
    expired = queue.expire_due(20_000)
    assert [item.reason for item in expired] == ["expired"]
    assert expired[0].opportunity is not None
    assert expired[0].opportunity.state == "expired"
    assert expired[0].opportunity.terminal_reason == "expired_ttl"
    assert expired[0].opportunity.reservation_token is None
    assert queue.nearest_validity_deadline(20_000) is None
    silent = queue.arbitrate(_ctx(now_ms=20_000, last_spoken_beat_id="battle.pursuit"))
    assert silent.reason == "no_candidate"
    assert silent.selected is None
    assert silent.started_impulse is False


def test_consume_only_on_speech_started_failed_attempt_releases() -> None:
    queue = OpportunityQueue()
    admitted = queue.admit(_intent())
    assert admitted.opportunity is not None
    early = queue.consume_speech_started("missing", now_ms=11_000)
    assert early.reason == "not_reserved"
    reserved = queue.reserve(admitted.opportunity.opportunity_id, now_ms=11_000)
    assert reserved.opportunity is not None
    token = reserved.opportunity.reservation_token
    assert token is not None
    failed = queue.reject_attempt(token, beat_id="battle.pursuit", now_ms=12_000)
    assert failed.reason == "attempt_released"
    assert failed.opportunity is not None
    assert failed.opportunity.state == "pending"
    assert failed.opportunity.reservation_token is None
    again = queue.reserve(admitted.opportunity.opportunity_id, now_ms=12_500)
    token = again.opportunity.reservation_token if again.opportunity else None
    assert token is not None
    consumed = queue.consume_speech_started(token, now_ms=13_000)
    assert consumed.reason == "consumed"
    assert consumed.opportunity is not None
    assert consumed.opportunity.state == "consumed"
    assert consumed.opportunity.terminal_reason == "consumed_playback_accepted"
    spoken = queue.note_spoken(admitted.opportunity.opportunity_id, now_ms=13_100)
    assert spoken.reason == "spoken"
    counters = queue.channel_counters("race.battle.closing")
    assert counters.queued == 1
    assert counters.consumed == 1
    assert counters.spoken == 1


def test_related_update_vs_independent_conflict() -> None:
    queue = OpportunityQueue()
    first = queue.admit(_intent())
    assert first.reason == "queued"
    updated = queue.admit(
        _intent(
            opportunity_id="opp:2",
            event_id="event:2",
            event_kind="battle.approach",
            current_identifier="APPROACH",
            relation="updates",
            beat_id="battle.approach",
            beat_ids=("battle.approach",),
            material_revision=2,
            candidate_order=CandidateOrder(5, 0),
            created_mono_ms=11_000,
        )
    )
    assert updated.reason == "queued"
    assert updated.superseded_id == "opp:1"
    assert queue.live_ids() == ("opp:2",)
    independent = queue.admit(
        _intent(
            opportunity_id="opp:3",
            event_id="event:3",
            event_kind="pit.entry",
            current_identifier="PIT_ENTRY",
            episode_id="episode:pit-1",
            correlation_key=("hero", "pit.1"),
            policy_id="live_story",
            relation="independent",
            beat_id="pit.entry",
            beat_ids=("pit.entry",),
            story_id="pit_cycle",
            semantic_identity=("hero", "pit.1"),
            candidate_order=CandidateOrder(6, 0),
            created_mono_ms=11_500,
        )
    )
    assert independent.reason == "queued"
    conflict = queue.admit(
        _intent(
            opportunity_id="opp:4",
            event_id="event:4",
            event_kind="battle.pressure_behind",
            current_identifier="HUNTED",
            episode_id="episode:behind-1",
            correlation_key=("hero", "car.7"),
            relation="conflicts",
            beat_id="battle.pressure_behind",
            beat_ids=("battle.pressure_behind",),
            story_id="battle_behind",
            semantic_identity=("hero", "car.7", "battle"),
            candidate_order=CandidateOrder(7, 0),
            created_mono_ms=12_000,
        )
    )
    assert conflict.reason == "queued"
    assert set(queue.live_ids()) == {"opp:2", "opp:3", "opp:4"}


def test_overflow_evicts_by_candidate_order() -> None:
    queue = OpportunityQueue(capacity=2)
    first = queue.admit(_intent(opportunity_id="opp:old", candidate_order=CandidateOrder(1, 0)))
    second = queue.admit(
        _intent(
            opportunity_id="opp:mid",
            event_id="event:2",
            candidate_order=CandidateOrder(2, 0),
            correlation_key=("hero", "car.9"),
            episode_id="episode:b",
        )
    )
    third = queue.admit(
        _intent(
            opportunity_id="opp:new",
            event_id="event:3",
            candidate_order=CandidateOrder(3, 0),
            correlation_key=("hero", "car.8"),
            episode_id="episode:c",
        )
    )
    assert first.reason == "queued"
    assert second.reason == "queued"
    assert third.reason == "queued"
    assert third.evicted_id == "opp:old"
    assert queue.live_ids() == ("opp:mid", "opp:new")
    assert queue.channel_counters("race.battle.closing").evicted == 1
    assert OPPORTUNITY_CAPACITY == 128


def test_higher_urgency_switches_equal_needs_margin() -> None:
    queue = OpportunityQueue()
    queue.admit(
        _intent(
            opportunity_id="opp:pass",
            event_id="event:pass",
            event_kind="position.pass",
            current_identifier="OVERTAKE",
            policy_id="critical",
            relation="independent",
            beat_id="position.pass",
            beat_ids=("position.pass",),
            story_id="single_result",
            episode_id="episode:pass-1",
            correlation_key=("hero", "pass"),
            semantic_identity=("hero", "pass"),
        )
    )
    switched = queue.arbitrate(
        _ctx(
            last_spoken_beat_id="battle.pursuit",
            last_spoken_episode_id="episode:battle-1",
            valid_successor_targets=("battle.approach",),
        )
    )
    assert switched.reason == "higher_urgency_switch"
    assert switched.selected is not None
    assert switched.selected.beat_id == "position.pass"
    assert switched.selected.relation == "independent_of_focused_episode"

    queue = OpportunityQueue()
    queue.admit(
        _intent(
            opportunity_id="opp:lap",
            event_id="event:lap",
            event_kind="timing.lap.completed",
            current_identifier="LAP_COMPLETE",
            policy_id="result",
            relation="independent",
            beat_id="timing.lap.completed",
            beat_ids=("timing.lap.completed",),
            story_id="single_result",
            episode_id="episode:lap-1",
            correlation_key=("hero", "lap"),
            semantic_identity=("hero", "lap"),
            tape_channel="race.timing.lap",
        )
    )
    held = queue.arbitrate(
        _ctx(
            last_spoken_beat_id="battle.pursuit",
            last_spoken_episode_id="episode:battle-1",
            valid_successor_targets=("battle.approach",),
        )
    )
    assert held.reason == "active_story_continuation"
    assert held.selected is not None
    assert held.selected.beat_id == "battle.approach"
    assert held.selected.score + SWITCH_MARGIN > 78.0
    assert SELECTION_THRESHOLD == 35.0

    squeezed = queue.arbitrate(
        _ctx(
            last_spoken_beat_id="battle.pursuit",
            last_spoken_episode_id="episode:battle-1",
            valid_successor_targets=("battle.approach",),
            channel_pressure=ChannelPressureView(
                schema_version=EXPOSURE_SCHEMA,
                now_ms=10_000,
                by_channel=(("race.battle.closing", 12.0),),
            ),
        )
    )
    assert squeezed.reason == "switch_margin_met"
    assert squeezed.selected is not None
    assert squeezed.selected.beat_id == "timing.lap.completed"


def test_tie_break_uses_candidate_order() -> None:
    queue = OpportunityQueue()
    queue.admit(
        _intent(
            opportunity_id="opp:newer",
            event_id="event:newer",
            candidate_order=CandidateOrder(9, 2),
            correlation_key=("hero", "a"),
            episode_id="episode:a",
        )
    )
    queue.admit(
        _intent(
            opportunity_id="opp:older",
            event_id="event:older",
            candidate_order=CandidateOrder(3, 1),
            correlation_key=("hero", "b"),
            episode_id="episode:b",
        )
    )
    decision = queue.arbitrate(_ctx(focused_episode_id=None, focused_story_id=None))
    assert decision.reason == "highest_valid_candidate"
    assert decision.selected is not None
    assert decision.selected.opportunity_id == "opp:older"


def test_silence_without_event_or_successor_filler_only_on_impulse() -> None:
    queue = OpportunityQueue()
    queue.admit(
        _intent(
            opportunity_id="opp:fill",
            event_id=None,
            event_kind="filler.quiet_track",
            current_identifier=None,
            source_class="silence",
            candidate_id=None,
            detector_observation_id=None,
            policy_id="filler",
            relation="independent",
            beat_id="filler.quiet_track",
            beat_ids=("filler.quiet_track",),
            story_id="filler_single",
            semantic_identity=("quiet",),
            source_fact_ids=("fact:quiet-1",),
        )
    )
    empty = queue.arbitrate(_ctx())
    assert empty.reason == "no_candidate"
    assert empty.selected is None
    filled = queue.arbitrate(_ctx(silence_impulse=True))
    assert filled.reason == "highest_valid_candidate"
    assert filled.selected is not None
    assert filled.selected.beat_id == "filler.quiet_track"
    assert filled.selected.source == "filler"

    other = OpportunityQueue()
    other.admit(_intent())
    with_event = other.arbitrate(
        _ctx(
            silence_impulse=True,
            episode_beats=(
                EpisodeBeatRef(
                    beat_id="battle.two_front",
                    episode_id="episode:other",
                    story_id="battle_two_front",
                    material_revision=1,
                    candidate_order=CandidateOrder(0, 0),
                    tape_channel="race.battle.two_front",
                    policy_id="live_story",
                ),
            ),
        )
    )
    assert with_event.selected is not None
    assert with_event.selected.source != "filler"


def test_rejected_beat_allows_other_beat_from_same_opportunity() -> None:
    queue = OpportunityQueue()
    admitted = queue.admit(_intent())
    assert admitted.opportunity is not None
    first = queue.arbitrate(_ctx())
    assert first.selected is not None
    assert first.selected.beat_id == "battle.pursuit"
    reserved = queue.reserve(admitted.opportunity.opportunity_id, now_ms=11_000)
    token = reserved.opportunity.reservation_token if reserved.opportunity else None
    assert token is not None
    queue.reject_attempt(token, beat_id="battle.pursuit", now_ms=11_500)
    second = queue.arbitrate(_ctx(now_ms=12_000))
    assert second.selected is not None
    assert second.selected.opportunity_id == "opp:1"
    assert second.selected.beat_id == "battle.approach"
    assert second.opportunity_consumed is False


def test_reads_exposure_channel_pressure() -> None:
    queue = OpportunityQueue()
    queue.admit(_intent())
    pressure = ChannelPressureView(
        schema_version=EXPOSURE_SCHEMA,
        now_ms=10_000,
        by_channel=(("race.battle.closing", 6.0),),
    )
    decision = queue.arbitrate(_ctx(channel_pressure=pressure))
    assert decision.selected is not None
    assert decision.selected.score == 64.0 - (0.8 * 6.0)
    assert decision.selected.channel_pressure == 6.0
    source = SOURCE.read_text(encoding="utf-8")
    assert "ChannelPressureView" in source
    assert "opportunity_queue" not in Path(SOURCE.parent / "exposure_store.py").read_text(
        encoding="utf-8"
    )


def test_replay_fixtures_cover_transition_identity_and_expiry() -> None:
    transition = json.loads((FIXTURES / "transition.json").read_text(encoding="utf-8"))
    identity = json.loads((FIXTURES / "counterfactual_identity.json").read_text(encoding="utf-8"))
    expiry = json.loads((FIXTURES / "expiry.json").read_text(encoding="utf-8"))

    queue = OpportunityQueue()
    step = queue.admit(
        _intent(
            opportunity_id=transition["opportunityId"],
            event_id=transition["eventId"],
            created_mono_ms=transition["createdMonoMs"],
            candidate_order=CandidateOrder(*transition["candidateOrder"]),
        )
    )
    assert step.reason == transition["expectAdmit"]
    decision = queue.arbitrate(_ctx(now_ms=transition["arbitrateAtMs"]))
    assert decision.reason == transition["expectDecision"]
    assert decision.selected is not None
    assert decision.selected.opportunity_id == transition["opportunityId"]

    other = OpportunityQueue()
    other.admit(_intent(opportunity_id="opp:keep"))
    other.admit(
        _intent(
            opportunity_id=identity["challengerId"],
            event_id="event:other",
            episode_id=identity["otherEpisodeId"],
            correlation_key=tuple(identity["otherCorrelation"]),
            candidate_order=CandidateOrder(8, 0),
        )
    )
    assert set(other.live_ids()) == {"opp:keep", identity["challengerId"]}

    aging = OpportunityQueue()
    aging.admit(_intent(created_mono_ms=expiry["createdMonoMs"]))
    expired = aging.expire_due(expiry["expireAtMs"])
    assert [item.reason for item in expired] == ["expired"]
    later = aging.arbitrate(_ctx(now_ms=expiry["arbitrateAtMs"]))
    assert later.reason == expiry["expectDecision"]
    assert later.started_impulse is False


def test_exports_and_banned_imports_stay_out() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    assert "opportunity_queue" not in events_exports
    for banned in (
        "NarrativeRuntime",
        "eval(",
        "exec(",
        "compile(",
        "irswitch.commentary",
        "irswitch.overlay",
        "math.exp",
    ):
        assert banned not in source
    assert HASH.startswith("sha256:")
