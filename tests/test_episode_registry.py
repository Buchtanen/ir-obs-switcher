"""#258 lineage-aware EpisodeRegistry: identity, states, reset, capacity."""

from __future__ import annotations

from pathlib import Path

import pytest

from irswitch.contracts import load_narrative_catalog
from irswitch.events import __all__ as events_exports
from irswitch.events.episode_registry import (
    ACTIVE_CAP,
    RESOLVED_CAP,
    EpisodeIntent,
    EpisodeRegistry,
    MaterialOrder,
)

SOURCE = Path(__file__).resolve().parents[1] / "src" / "irswitch" / "events" / "episode_registry.py"


def _order(reducer: int = 1, source: int = 0) -> MaterialOrder:
    return MaterialOrder(reducer_sequence=reducer, source_ordinal=source)


def _intent(
    *,
    definition_id: str = "battle_ahead",
    semantic: tuple[str, ...] = ("hero", "car.22"),
    correlation: tuple[str, ...] = ("corr:1",),
    occurrence_id: str | None = "3:race:0",
    lineage_id: str | None = "3:practice:0>3:race:0",
    scope: str = "occurrence",
    fact_ids: tuple[str, ...] = ("fact:1",),
    order: MaterialOrder | None = None,
    now_ms: int = 1_000,
    priority: int = 64,
    source_refs: tuple[str, ...] = ("event:hunt",),
) -> EpisodeIntent:
    return EpisodeIntent(
        definition_id=definition_id,
        scope=scope,
        occurrence_id=occurrence_id,
        lineage_id=lineage_id,
        semantic_identity=semantic,
        correlation_ids=correlation,
        fact_ids=fact_ids,
        material_order=order or _order(),
        now_ms=now_ms,
        continuation_priority=priority,
        source_refs=source_refs,
    )


def test_open_and_resolve_do_not_require_speech() -> None:
    registry = EpisodeRegistry()
    opened = registry.open(_intent())

    assert opened.decision is None
    assert opened.episode is not None
    assert opened.episode.state == "candidate"
    assert opened.episode.spoken_beat_ids == ()
    assert opened.episode.last_spoken_beat_id is None
    assert opened.episode.material_revision == 1
    assert opened.transitions[0].reason == "opened"
    assert opened.transitions[0].source_refs == ("event:hunt",)

    resolved = registry.resolve(opened.episode.episode_id, now_ms=2_000, reason="outcome_observed")
    assert resolved.episode is not None
    assert resolved.episode.state == "resolved"
    assert resolved.episode.spoken_beat_ids == ()
    assert resolved.episode.resolution_reason == "outcome_observed"
    assert resolved.transitions[0].reason == "outcome_observed"


def test_same_semantic_identity_updates_instead_of_opening_a_second() -> None:
    registry = EpisodeRegistry()
    first = registry.open(_intent())
    second = registry.open(_intent(fact_ids=("fact:1", "fact:2"), order=_order(2), now_ms=1_100))

    assert first.episode is not None
    assert second.episode is not None
    assert second.episode.episode_id == first.episode.episode_id
    assert len(registry.current()) == 1
    assert second.episode.material_revision == 2
    assert second.episode.fact_ids == ("fact:1", "fact:2")
    assert second.transitions[-1].reason == "material_revision"


def test_counterfactual_identities_stay_independent() -> None:
    registry = EpisodeRegistry()
    ahead = registry.open(_intent(semantic=("hero", "car.22"), correlation=("corr:front",)))
    behind = registry.open(
        _intent(
            definition_id="battle_behind",
            semantic=("hero", "car.99"),
            correlation=("corr:rear",),
            order=_order(2),
        )
    )

    assert ahead.episode is not None
    assert behind.episode is not None
    assert ahead.episode.episode_id != behind.episode.episode_id
    assert len(registry.current()) == 2
    reset = registry.reset_occurrences({"3:race:0"}, now_ms=3_000, reason="occurrence_ended")
    assert {row.episode_id for row in reset.affected} == {
        ahead.episode.episode_id,
        behind.episode.episode_id,
    }


def test_reset_invalidates_only_affected_lineage() -> None:
    registry = EpisodeRegistry()
    race = registry.open(_intent())
    practice = registry.open(
        _intent(
            definition_id="timing_attempt",
            semantic=("hero", "lap.1"),
            correlation=("corr:lap",),
            occurrence_id="3:practice:0",
            lineage_id="3:practice:0",
            order=_order(2),
        )
    )
    stream = registry.open(
        _intent(
            definition_id="stream_lifecycle",
            scope="stream",
            occurrence_id=None,
            lineage_id=None,
            semantic=("stream",),
            correlation=(),
            order=_order(3),
        )
    )

    step = registry.reset_occurrences({"3:race:0"}, now_ms=4_000, reason="occurrence_superseded")
    assert race.episode is not None
    assert practice.episode is not None
    assert stream.episode is not None
    assert registry.get(race.episode.episode_id).state == "invalidated"
    assert registry.get(practice.episode.episode_id).state == "candidate"
    assert registry.get(stream.episode.episode_id).state == "candidate"
    assert {item.episode_id for item in step.affected} == {race.episode.episode_id}


def test_exclusive_group_suspends_overlapping_battle() -> None:
    registry = EpisodeRegistry()
    hunt = registry.open(_intent())
    registry.activate(hunt.episode.episode_id, now_ms=1_100, source_refs=("event:hunt",))
    two = registry.open(
        _intent(
            definition_id="battle_two_front",
            semantic=("hero", "car.22", "car.33"),
            correlation=("corr:1", "corr:2"),
            order=_order(2),
            now_ms=1_200,
        )
    )

    assert hunt.episode is not None
    assert two.episode is not None
    assert registry.get(hunt.episode.episode_id).state == "suspended"
    assert two.episode.state == "candidate"
    assert any(item.reason == "target_changed" for item in two.transitions)


def test_every_transition_has_reason_and_source_refs() -> None:
    registry = EpisodeRegistry()
    opened = registry.open(_intent())
    activated = registry.activate(
        opened.episode.episode_id, now_ms=1_100, source_refs=("event:confirm",)
    )
    spoken = registry.mark_spoken(
        opened.episode.episode_id, "battle.pursuit", now_ms=1_200, source_refs=("utt:1",)
    )
    suspended = registry.suspend(
        opened.episode.episode_id,
        now_ms=1_300,
        reason="target_changed",
        source_refs=("event:swap",),
    )

    for step in (opened, activated, spoken, suspended):
        assert step.transitions
        for item in step.transitions:
            assert item.reason
            assert item.source_refs


def test_capacity_evicts_suspended_then_candidate_then_lowest_priority_active() -> None:
    registry = EpisodeRegistry(active_capacity=3, resolved_capacity=8)
    first = registry.open(
        _intent(semantic=("a",), correlation=("c:a",), priority=80, order=_order(1))
    )
    second = registry.open(
        _intent(semantic=("b",), correlation=("c:b",), priority=40, order=_order(2), now_ms=1_100)
    )
    third = registry.open(
        _intent(semantic=("c",), correlation=("c:c",), priority=90, order=_order(3), now_ms=1_200)
    )
    registry.activate(first.episode.episode_id, now_ms=1_300, source_refs=("e:1",))
    registry.activate(second.episode.episode_id, now_ms=1_400, source_refs=("e:2",))
    registry.suspend(
        first.episode.episode_id, now_ms=1_500, reason="target_changed", source_refs=("e:s",)
    )

    fourth = registry.open(
        _intent(semantic=("d",), correlation=("c:d",), priority=10, order=_order(4), now_ms=1_600)
    )
    assert first.episode is not None
    assert registry.get(first.episode.episode_id).state == "invalidated"
    assert registry.get(first.episode.episode_id).resolution_reason == "capacity_evicted"
    assert fourth.episode is not None
    assert fourth.episode.state == "candidate"
    assert {item.episode_id for item in registry.current()} == {
        second.episode.episode_id,
        third.episode.episode_id,
        fourth.episode.episode_id,
    }

    fifth = registry.open(
        _intent(semantic=("e",), correlation=("c:e",), priority=70, order=_order(5), now_ms=1_700)
    )
    assert third.episode is not None
    assert registry.get(third.episode.episode_id).state == "invalidated"
    assert fifth.decision is None

    sixth = registry.open(
        _intent(semantic=("f",), correlation=("c:f",), priority=5, order=_order(6), now_ms=1_800)
    )
    assert fourth.episode is not None
    assert registry.get(fourth.episode.episode_id).state == "invalidated"
    assert sixth.episode is not None
    assert registry.get(second.episode.episode_id).state == "active"


def test_pinned_instances_reject_only_the_new_route() -> None:
    registry = EpisodeRegistry(active_capacity=1, resolved_capacity=4)
    first = registry.open(_intent())
    registry.pin(first.episode.episode_id, "reserved")
    rejected = registry.open(
        _intent(semantic=("other",), correlation=("corr:2",), order=_order(2), now_ms=1_500)
    )

    assert rejected.episode is None
    assert rejected.decision == "episode_capacity_rejected"
    assert registry.get(first.episode.episode_id).state == "candidate"
    assert registry.current()[0].fact_ids == ("fact:1",)


def test_resolved_overflow_drops_oldest_summary() -> None:
    registry = EpisodeRegistry(active_capacity=8, resolved_capacity=2)
    one = registry.open(_intent(semantic=("one",), correlation=("c:1",)))
    two = registry.open(_intent(semantic=("two",), correlation=("c:2",), order=_order(2)))
    three = registry.open(_intent(semantic=("three",), correlation=("c:3",), order=_order(3)))
    registry.resolve(one.episode.episode_id, now_ms=2_000, reason="natural_exit")
    registry.resolve(two.episode.episode_id, now_ms=2_100, reason="natural_exit")
    registry.resolve(three.episode.episode_id, now_ms=2_200, reason="natural_exit")

    assert registry.get(one.episode.episode_id) is None
    assert registry.get(two.episode.episode_id).state == "resolved"
    assert registry.get(three.episode.episode_id).state == "resolved"
    assert registry.history_complete is False


def test_stream_scope_may_omit_occurrence_and_lineage() -> None:
    registry = EpisodeRegistry()
    step = registry.open(
        _intent(
            definition_id="stream_lifecycle",
            scope="stream",
            occurrence_id=None,
            lineage_id=None,
            semantic=("stream",),
            correlation=(),
        )
    )
    assert step.episode is not None
    assert step.episode.scope == "stream"
    assert step.episode.occurrence_id is None
    assert step.episode.lineage_id is None


def test_occurrence_scope_requires_both_ids() -> None:
    registry = EpisodeRegistry()
    with pytest.raises(Exception, match="occurrenceId and lineageId"):
        registry.open(_intent(occurrence_id=None, lineage_id=None))


def test_catalog_stories_are_the_only_definitions() -> None:
    catalog = load_narrative_catalog().require_catalog()
    registry = EpisodeRegistry()
    assert {story.id for story in catalog.stories} >= {
        "battle_ahead",
        "stream_lifecycle",
        "filler_single",
    }
    with pytest.raises(Exception, match="unknown story"):
        registry.open(_intent(definition_id="not_a_story"))


def test_defaults_match_public_contract_and_exports_stay_out_of_events() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    assert ACTIVE_CAP == 64
    assert RESOLVED_CAP == 256
    assert "episode_registry" not in events_exports
    assert "NarrativeRuntime" not in source
    assert "eval(" not in source
    assert "exec(" not in source
    assert "compile(" not in source
    for banned in ("irswitch.commentary", "irswitch.overlay"):
        assert banned not in source
