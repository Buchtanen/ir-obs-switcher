"""#265 freshness commit gate: reject stale text immediately before TTS."""

from __future__ import annotations

import json
from pathlib import Path

from irswitch.events import __all__ as events_exports
from irswitch.events.beat_plan import CandidateOrder
from irswitch.events.freshness_commit import (
    SCHEMA_VERSION,
    BoundFactCopy,
    CommitToken,
    CommitWorld,
    FreshnessGate,
)
from irswitch.events.opportunity_queue import OpportunityIntent, OpportunityQueue

SOURCE = Path(__file__).resolve().parents[1] / "src" / "irswitch" / "events" / "freshness_commit.py"
FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "freshness_commit"
OCCURRENCE = "3:race:0"
LINEAGE = "3:practice:0>3:race:0"
TARGET = ("hero", "car.22")


def _fact(
    fact_id: str = "fact:gap-1",
    *,
    gap_s: float = 1.4,
    revision: int = 1,
    status: str = "active",
    valid_until: int | None = 40_000,
    occurrence_id: str | None = OCCURRENCE,
    lineage_id: str | None = LINEAGE,
) -> BoundFactCopy:
    return BoundFactCopy(
        fact_id=fact_id,
        predicate="battle.gap",
        subject_id="hero",
        object_id="car.22",
        attributes=(("gap_s", gap_s),),
        polarity="positive",
        revision=revision,
        status=status,
        occurrence_id=occurrence_id,
        lineage_id=lineage_id,
        valid_from_mono_ms=1_000,
        valid_until_mono_ms=valid_until,
    )


def _token(**overrides: object) -> CommitToken:
    values: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "token_id": "commit:1",
        "plan_id": "plan:1",
        "beat_id": "battle.approach",
        "episode_id": "episode:battle-1",
        "episode_revision": 1,
        "stream_epoch": 3,
        "occurrence_id": OCCURRENCE,
        "lineage_id": LINEAGE,
        "target_identity": TARGET,
        "selected_facts": (_fact(),),
        "opportunity_id": "opp:1",
        "reservation_token": "res:opp:1",
        "opportunity_material_revision": 1,
        "opportunity_expires_mono_ms": 20_000,
        "planned_mono_ms": 10_000,
        "fact_view_revision": 90,
    }
    values.update(overrides)
    return CommitToken(**values)  # type: ignore[arg-type]


def _world(**overrides: object) -> CommitWorld:
    values: dict[str, object] = {
        "now_ms": 10_400,
        "lane": "building",
        "stream_epoch": 3,
        "occurrence_id": OCCURRENCE,
        "lineage_id": LINEAGE,
        "episode_id": "episode:battle-1",
        "episode_revision": 1,
        "episode_state": "active",
        "target_identity": TARGET,
        "facts": (_fact(),),
        "fact_view_revision": 90,
        "opportunity_state": "reserved",
        "opportunity_material_revision": 1,
        "opportunity_expires_mono_ms": 20_000,
        "reservation_token": "res:opp:1",
        "critical_conflict": False,
    }
    values.update(overrides)
    return CommitWorld(**values)  # type: ignore[arg-type]


def _opp(**overrides: object) -> OpportunityIntent:
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
        "correlation_key": TARGET,
        "tape_channel": None,
        "policy_id": "live_story",
        "created_mono_ms": 10_000,
        "material_revision": 1,
        "source_fact_ids": ("fact:gap-1",),
        "candidate_order": CandidateOrder(reducer_sequence=4, source_ordinal=1),
        "source_order": None,
        "relation": "opens",
        "beat_id": "battle.approach",
        "beat_ids": ("battle.approach", "battle.overlap"),
        "story_id": "battle_ahead",
        "semantic_identity": ("hero", "car.22", "battle"),
    }
    values.update(overrides)
    return OpportunityIntent(**values)  # type: ignore[arg-type]


def test_current_when_unrelated_fact_view_advances() -> None:
    extra = _fact("fact:weather-1", gap_s=0.0)
    world = _world(fact_view_revision=91, facts=(_fact(), extra))
    step = FreshnessGate().evaluate(_token(), world)
    assert step.verdict == "current"
    assert step.reason == "current"
    assert step.suppressed is False
    assert step.same_revision_retry is False
    assert step.rebuilt_surfaces is False
    assert step.opportunity_effect is None
    assert step.token.selected_facts[0].attributes == (("gap_s", 1.4),)


def test_stale_when_selected_fact_changed() -> None:
    newer = _fact(gap_s=1.1, revision=2)
    step = FreshnessGate().evaluate(_token(), _world(facts=(newer,)))
    assert step.verdict == "freshness_stale"
    assert step.reason == "freshness_stale"
    assert "fact_changed" in step.evidence
    assert step.suppressed is True
    assert step.token.selected_facts[0].attributes == (("gap_s", 1.4),)
    assert step.rebuilt_surfaces is False


def test_stale_when_selected_fact_evicted() -> None:
    other = _fact("fact:gap-2", gap_s=1.1, revision=1)
    step = FreshnessGate().evaluate(_token(), _world(facts=(other,)))
    assert step.verdict == "freshness_stale"
    assert "fact_missing" in step.evidence
    assert step.rebuilt_surfaces is False


def test_stale_when_selected_fact_expired_or_superseded() -> None:
    expired = FreshnessGate().evaluate(
        _token(opportunity_expires_mono_ms=60_000),
        _world(
            now_ms=50_000,
            opportunity_expires_mono_ms=60_000,
            facts=(_fact(valid_until=12_000),),
        ),
    )
    assert expired.verdict == "freshness_stale"
    assert "fact_expired" in expired.evidence
    superseded = FreshnessGate().evaluate(
        _token(),
        _world(facts=(_fact(status="superseded"),)),
    )
    assert superseded.verdict == "freshness_stale"
    assert "fact_not_current" in superseded.evidence


def test_invalidated_on_old_lineage() -> None:
    step = FreshnessGate().evaluate(
        _token(),
        _world(lineage_id="3:practice:0>3:qualify:0>3:race:0"),
    )
    assert step.verdict == "invalidated"
    assert "lineage_mismatch" in step.evidence
    assert step.suppressed is True


def test_invalidated_on_changed_target() -> None:
    step = FreshnessGate().evaluate(_token(), _world(target_identity=("hero", "car.7")))
    assert step.verdict == "invalidated"
    assert "target_changed" in step.evidence
    assert step.same_revision_retry is False


def test_stale_on_opportunity_ttl_and_supersession() -> None:
    expired = FreshnessGate().evaluate(
        _token(),
        _world(now_ms=20_000, opportunity_expires_mono_ms=15_000),
    )
    assert expired.verdict == "freshness_stale"
    assert "opportunity_expired" in expired.evidence
    superseded = FreshnessGate().evaluate(
        _token(),
        _world(opportunity_state="superseded", reservation_token=None),
    )
    assert superseded.verdict == "freshness_stale"
    assert "opportunity_superseded" in superseded.evidence


def test_invalidated_on_critical_conflict() -> None:
    step = FreshnessGate().evaluate(_token(), _world(critical_conflict=True))
    assert step.verdict == "invalidated"
    assert "critical_conflict" in step.evidence


def test_failure_releases_reservation_and_suppresses_revision() -> None:
    queue = OpportunityQueue()
    admitted = queue.admit(_opp())
    assert admitted.reason in {"admitted", "queued"}
    reserved = queue.reserve("opp:1", now_ms=10_000)
    assert reserved.reason == "reserved"
    token = _token(reservation_token=reserved.opportunity.reservation_token)
    gate = FreshnessGate(queue)
    step = gate.evaluate(token, _world(facts=(_fact(gap_s=1.1, revision=2),)))
    assert step.verdict == "freshness_stale"
    assert step.opportunity_effect == "attempt_released"
    assert step.suppressed is True
    assert queue.live_ids() == ("opp:1",)
    retry = gate.evaluate(token, _world())
    assert retry.verdict == "freshness_stale"
    assert "suppressed_revision" in retry.evidence
    assert retry.same_revision_retry is False


def test_same_revision_cannot_retry_after_invalidation() -> None:
    gate = FreshnessGate()
    first = gate.evaluate(_token(), _world(lineage_id="3:practice:0"))
    assert first.verdict == "invalidated"
    second = gate.evaluate(_token(), _world())
    assert second.verdict == "freshness_stale"
    assert second.same_revision_retry is False
    later = gate.evaluate(_token(episode_revision=2), _world(episode_revision=2))
    assert later.verdict == "current"


def test_never_rebuilds_from_newer_truth() -> None:
    token = _token()
    world = _world(facts=(_fact("fact:gap-2", gap_s=1.1),))
    step = FreshnessGate().evaluate(token, world)
    assert step.verdict == "freshness_stale"
    assert step.rebuilt_surfaces is False
    assert step.token is token
    assert [copy.fact_id for copy in step.token.selected_facts] == ["fact:gap-1"]


def test_not_reached_when_lane_is_not_building() -> None:
    step = FreshnessGate().evaluate(_token(), _world(lane="idle"))
    assert step.verdict == "not_reached"
    assert step.reason == "not_reached"
    assert step.suppressed is False
    assert step.opportunity_effect is None


def test_replay_fixtures_cover_transition_identity_and_expiry() -> None:
    transition = json.loads((FIXTURES / "transition.json").read_text(encoding="utf-8"))
    identity = json.loads((FIXTURES / "counterfactual_identity.json").read_text(encoding="utf-8"))
    expiry = json.loads((FIXTURES / "expiry.json").read_text(encoding="utf-8"))
    current = FreshnessGate().evaluate(
        _token(token_id=transition["tokenId"], planned_mono_ms=transition["nowMs"]),
        _world(now_ms=transition["nowMs"]),
    )
    assert current.verdict == transition["expectVerdict"]
    assert current.reason == transition["expectReason"]
    assert current.schema_version == SCHEMA_VERSION
    missing = FreshnessGate().evaluate(
        _token(),
        _world(facts=(_fact(identity["otherFactId"], gap_s=1.1),)),
    )
    assert missing.verdict == identity["expectVerdict"]
    expired = FreshnessGate().evaluate(
        _token(opportunity_expires_mono_ms=expiry["expiresMonoMs"]),
        _world(now_ms=expiry["nowMs"], opportunity_expires_mono_ms=expiry["expiresMonoMs"]),
    )
    assert expired.verdict == expiry["expectVerdict"]
    assert expiry["nowMs"] >= expiry["expiresMonoMs"]


def test_records_latency_and_exports_stay_out() -> None:
    step = FreshnessGate().evaluate(_token(planned_mono_ms=10_000), _world(now_ms=10_400))
    assert step.latency_ms is not None
    assert step.latency_ms["plan_to_commit"] == 400
    assert "freshness_commit" not in events_exports
    source = SOURCE.read_text(encoding="utf-8")
    for banned in (
        "NarrativeRuntime",
        "eval(",
        "exec(",
        "compile(",
        "irswitch.commentary",
        "irswitch.overlay",
        "RealizationBundle",
        "import sounddevice",
        "win32com",
    ):
        assert banned not in source
