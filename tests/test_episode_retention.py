"""#259 resolved-episode retention: world outcomes, no prepared-speech queue."""

from __future__ import annotations

from pathlib import Path

import pytest

from irswitch.contracts import load_narrative_catalog
from irswitch.events import __all__ as events_exports
from irswitch.events.episode_registry import (
    Episode,
    EpisodeIntent,
    EpisodeRegistry,
    MaterialOrder,
)
from irswitch.events.episode_retention import (
    RESOLVED_CAP,
    EpisodeRetention,
    RetentionIntent,
)

SOURCE = (
    Path(__file__).resolve().parents[1] / "src" / "irswitch" / "events" / "episode_retention.py"
)


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
    fact_ids: tuple[str, ...] = ("fact:pass",),
    order: MaterialOrder | None = None,
    now_ms: int = 10_000,
    priority: int = 90,
    source_refs: tuple[str, ...] = ("event:overtake",),
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


def _resolve(
    definition_id: str = "single_result",
    *,
    semantic: tuple[str, ...] = ("hero", "car.22", "pass"),
    correlation: tuple[str, ...] = ("corr:1",),
    fact_ids: tuple[str, ...] = ("fact:pass",),
    now_ms: int = 10_000,
    order: MaterialOrder | None = None,
) -> tuple[EpisodeRegistry, Episode]:
    registry = EpisodeRegistry()
    opened = registry.open(
        _intent(
            definition_id=definition_id,
            semantic=semantic,
            correlation=correlation,
            fact_ids=fact_ids,
            now_ms=now_ms,
            order=order or _order(),
        )
    )
    assert opened.episode is not None
    resolved = registry.resolve(opened.episode.episode_id, now_ms=now_ms, reason="outcome_observed")
    assert resolved.episode is not None
    assert isinstance(resolved.episode, Episode)
    return registry, resolved.episode


def test_pass_during_speech_is_selectable_after_completion_if_still_relevant() -> None:
    catalog = load_narrative_catalog().require_catalog()
    policy = catalog.beat("position.pass").policy
    _, episode = _resolve()
    store = EpisodeRetention()
    store.retain(
        RetentionIntent(
            episode=episode,
            beat_id="position.pass",
            now_ms=10_000,
            source_refs=("event:overtake",),
        )
    )

    step = store.on_speech_complete(now_ms=10_000 + policy.ttl_ms - 1, source_refs=("speech:end",))
    assert step.selected
    assert step.selected[0].episode_id == episode.episode_id
    assert step.selected[0].outcome_family == "critical"
    assert step.selected[0].self_contained is True
    assert step.selected[0].speakable_until_ms == 10_000 + policy.ttl_ms
    assert step.selected[0].resolution_salience == policy.base_priority
    assert all(item.reason != "expired_ttl" for item in step.decisions)


def test_expired_pass_is_not_selected_after_ttl() -> None:
    catalog = load_narrative_catalog().require_catalog()
    policy = catalog.beat("position.pass").policy
    _, episode = _resolve()
    store = EpisodeRetention()
    store.retain(
        RetentionIntent(
            episode=episode,
            beat_id="position.pass",
            now_ms=10_000,
            source_refs=("event:overtake",),
        )
    )

    step = store.on_speech_complete(now_ms=10_000 + policy.ttl_ms, source_refs=("speech:end",))
    assert step.selected == ()
    assert any(item.reason == "expired_ttl" for item in step.decisions)


def test_obsolete_gap_updates_are_skipped_after_speech() -> None:
    _, episode = _resolve(
        "battle_ahead",
        semantic=("hero", "car.22"),
        fact_ids=("fact:gap",),
    )
    store = EpisodeRetention()
    store.retain(
        RetentionIntent(
            episode=episode,
            beat_id="battle.approach",
            now_ms=10_000,
            source_refs=("event:approach",),
        )
    )

    step = store.on_speech_complete(now_ms=11_000, source_refs=("speech:end",))
    assert step.selected == ()
    assert any(item.reason == "skipped" for item in step.decisions)
    assert all(item.record.outcome_family == "live_story" for item in step.decisions)


def test_superseded_intermediate_revision_expires() -> None:
    _, first = _resolve(
        "battle_ahead",
        semantic=("hero", "car.8"),
        correlation=("corr:gap.1",),
        fact_ids=("fact:r1",),
        now_ms=1_000,
    )
    _, second = _resolve(
        "battle_ahead",
        semantic=("hero", "car.8"),
        correlation=("corr:gap.2",),
        fact_ids=("fact:r1", "fact:r2"),
        now_ms=2_100,
        order=_order(2),
    )
    store = EpisodeRetention()
    store.retain(
        RetentionIntent(
            episode=first,
            beat_id="battle.approach",
            now_ms=1_000,
            source_refs=("event:gap.1",),
        )
    )
    second_step = store.retain(
        RetentionIntent(
            episode=second,
            beat_id="battle.approach",
            now_ms=2_100,
            source_refs=("event:gap.2",),
        )
    )
    assert any(item.reason == "superseded_revision" for item in second_step.decisions)
    live = store.live()
    assert len(live) == 1
    assert live[0].episode_id == second.episode_id
    assert live[0].fact_ids == ("fact:r1", "fact:r2")


def test_pass_and_finish_outcomes_are_self_contained() -> None:
    _, pass_episode = _resolve()
    _, finish = _resolve(
        "single_result",
        semantic=("hero", "finish"),
        correlation=("corr:finish",),
        fact_ids=("fact:finish",),
        now_ms=12_000,
        order=_order(2),
    )
    store = EpisodeRetention()
    store.retain(
        RetentionIntent(
            episode=pass_episode,
            beat_id="position.pass",
            now_ms=10_000,
            source_refs=("event:overtake",),
        )
    )
    store.retain(
        RetentionIntent(
            episode=finish,
            beat_id="session.hero_finish",
            now_ms=12_000,
            source_refs=("event:finish",),
        )
    )
    live = store.live()
    assert {item.beat_id for item in live} == {"position.pass", "session.hero_finish"}
    assert all(item.self_contained for item in live)


def test_ttl_and_salience_come_from_catalog_policy_family() -> None:
    catalog = load_narrative_catalog().require_catalog()
    expected = {item.id: (item.ttl_ms, item.base_priority) for item in catalog.policies}
    assert expected["critical"] == (45_000, 90)
    assert expected["result"] == (30_000, 78)
    assert expected["live_story"] == (10_000, 64)
    assert expected["transient"] == (6_000, 56)

    _, episode = _resolve(
        "timing_attempt",
        semantic=("hero", "lap.3"),
        fact_ids=("fact:lap",),
    )
    store = EpisodeRetention()
    step = store.retain(
        RetentionIntent(
            episode=episode,
            beat_id="timing.lap.completed",
            now_ms=10_000,
            source_refs=("event:lap",),
        )
    )
    record = step.retained
    assert record is not None
    ttl, salience = expected["result"]
    assert record.outcome_family == "result"
    assert record.speakable_until_ms == 10_000 + ttl
    assert record.resolution_salience == salience


def test_speech_complete_records_expired_and_skipped_reasons() -> None:
    catalog = load_narrative_catalog().require_catalog()
    _, pass_episode = _resolve(now_ms=1_000)
    _, gap = _resolve(
        "battle_ahead",
        semantic=("hero", "car.5"),
        correlation=("corr:gap",),
        fact_ids=("fact:gap",),
        now_ms=40_000,
        order=_order(2),
    )
    store = EpisodeRetention()
    store.retain(
        RetentionIntent(
            episode=pass_episode,
            beat_id="position.pass",
            now_ms=1_000,
            source_refs=("event:overtake",),
        )
    )
    store.retain(
        RetentionIntent(
            episode=gap,
            beat_id="battle.approach",
            now_ms=40_000,
            source_refs=("event:gap",),
        )
    )
    step = store.on_speech_complete(
        now_ms=1_000 + catalog.beat("position.pass").policy.ttl_ms,
        source_refs=("speech:end",),
    )
    reasons = {item.reason for item in step.decisions}
    assert "expired_ttl" in reasons
    assert "skipped" in reasons
    assert step.selected == ()


def test_unresolved_episode_cannot_be_retained() -> None:
    registry = EpisodeRegistry()
    opened = registry.open(_intent())
    assert opened.episode is not None
    store = EpisodeRetention()
    with pytest.raises(Exception, match="resolved"):
        store.retain(
            RetentionIntent(
                episode=opened.episode,
                beat_id="position.pass",
                now_ms=10_000,
                source_refs=("event:overtake",),
            )
        )


def test_no_prepared_speech_fields_and_exports_stay_out_of_events() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    _, episode = _resolve()
    store = EpisodeRetention()
    step = store.retain(
        RetentionIntent(
            episode=episode,
            beat_id="position.pass",
            now_ms=10_000,
            source_refs=("event:overtake",),
        )
    )
    record = step.retained
    assert record is not None
    assert not hasattr(record, "utterance")
    assert not hasattr(record, "prompt")
    assert not hasattr(record, "beat_plan")
    assert "episode_retention" not in events_exports
    assert RESOLVED_CAP == 256
    for banned in (
        "NarrativeRuntime",
        "eval(",
        "exec(",
        "compile(",
        "irswitch.commentary",
        "irswitch.overlay",
        "BeatPlan",
        "TtsUtterance",
    ):
        assert banned not in source
