"""#284 NarrativeRuntime realization_effect + StoryDirector composition."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from test_n12_consumers import _batch

from irswitch.commentary.mailbox import NarrativeMailbox
from irswitch.commentary.tts import NullTtsSink
from irswitch.contracts.command import NarrativeCommand
from irswitch.events.episode_registry import EpisodeRegistry
from irswitch.events.freshness_commit import FreshnessGate
from irswitch.events.narrative import partition_context_batches
from irswitch.events.narrative_realization_bridge import (
    SpeechDraftCache,
    build_realization_effect,
    draft_text_from_event,
)
from irswitch.events.narrative_runtime import NarrativeRuntime
from irswitch.events.narrative_shadow_adapter import adapt_batch_for_shadow
from irswitch.events.narrative_tts_bridge import build_tts_effect
from irswitch.events.opportunity_queue import OpportunityQueue
from irswitch.events.story_director import StoryDirector

RACE_SOURCE = Path(__file__).resolve().parents[1] / "src" / "irswitch" / "race" / "runtime.py"


def test_draft_text_from_shadow_event_is_speakable() -> None:
    publication = adapt_batch_for_shadow(_batch(stream_sequence=21))
    assert publication is not None
    text = draft_text_from_event(publication.events[0])
    assert text is not None
    assert text.endswith(".")
    assert 1 <= len(text) <= 400


@pytest.mark.asyncio
async def test_realization_effect_then_tts_effect_speaks_draft() -> None:
    sink = NullTtsSink()
    cache = SpeechDraftCache()
    publication = adapt_batch_for_shadow(_batch(stream_sequence=22))
    assert publication is not None
    cache.observe_publication(publication)
    opportunity_queue = OpportunityQueue()
    runtime = NarrativeRuntime(
        mailbox=NarrativeMailbox(),
        realization_effect=build_realization_effect(cache),
        tts_effect=build_tts_effect(sink, locale="en"),
        story_director=StoryDirector(),
        opportunity_queue=opportunity_queue,
        episode_registry=EpisodeRegistry(),
        freshness_gate=FreshnessGate(opportunity_queue),
    )
    runtime.enable()
    part = partition_context_batches(
        timeline=publication.timeline,
        fact_view=publication.fact_view,
        events=publication.events,
        fanout_stream_sequence=publication.fanout_stream_sequence,
    )[0]
    assert part.planning_impulse is True
    assert runtime.admit(NarrativeCommand.context_batch("ctx:live", 1000, part)).accepted

    # Drain until realization has been requested and completed through effects.
    for _ in range(8):
        reduced = runtime.reduce_next()
        if reduced is None:
            await asyncio.sleep(0.01)
            continue
        await runtime.apply_effects(reduced.effects)
        await runtime.wait_effects_idle()
        if sink.spoken:
            break
    assert sink.spoken, "expected tts_effect to speak drafted realization text"
    assert sink.spoken[0].text.endswith(".")


def test_race_wires_realization_effect_and_story_director() -> None:
    race = RACE_SOURCE.read_text(encoding="utf-8")
    assert "build_realization_effect" in race
    assert "SpeechDraftCache" in race
    assert "story_director=StoryDirector()" in race
    assert "realization_effect=realization_effect" in race
    assert "opportunity_queue=opportunity_queue" in race
    assert "episode_registry=EpisodeRegistry()" in race
    assert "freshness_gate=FreshnessGate(opportunity_queue)" in race
    assert "_adapt_batch_for_shadow_with_drafts" in race
    assert "build_tts_effect" in race
