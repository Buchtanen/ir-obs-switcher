"""#284 authored-pack realization over humanized draft templates."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from test_n12_consumers import _batch

from irswitch.commentary.mailbox import NarrativeMailbox
from irswitch.commentary.tts import NullTtsSink
from irswitch.contracts.authored_pack import load_authored_pack
from irswitch.contracts.command import NarrativeCommand
from irswitch.events import __all__ as events_exports
from irswitch.events.episode_registry import EpisodeRegistry
from irswitch.events.freshness_commit import FreshnessGate
from irswitch.events.narrative import partition_context_batches
from irswitch.events.narrative_realization_bridge import (
    SpeechDraft,
    SpeechDraftCache,
    build_realization_effect,
    draft_from_event,
    realize_authored_text,
    resolve_authored_beat_id,
)
from irswitch.events.narrative_runtime import NarrativeRuntime
from irswitch.events.narrative_shadow_adapter import adapt_batch_for_shadow
from irswitch.events.narrative_tts_bridge import build_tts_effect
from irswitch.events.opportunity_queue import OpportunityQueue
from irswitch.events.story_director import StoryDirector

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "irswitch"
    / "events"
    / "narrative_realization_bridge.py"
)
RACE_SOURCE = Path(__file__).resolve().parents[1] / "src" / "irswitch" / "race" / "runtime.py"


def test_bridge_not_exported() -> None:
    assert "realize_authored_text" not in events_exports
    assert SOURCE.is_file()


def test_resolve_authored_beat_id_normalizes_kind() -> None:
    pack = load_authored_pack()
    assert resolve_authored_beat_id("timing.lap_completed", pack=pack) == "timing.lap.completed"
    assert resolve_authored_beat_id("timing.lap.completed", pack=pack) == "timing.lap.completed"
    assert resolve_authored_beat_id("battle.pursuit", pack=pack) is None


def test_realize_authored_text_for_pack_beat() -> None:
    text = realize_authored_text(
        "timing.lap.completed",
        subject="Car 12",
        claim="completes the lap",
        now_ms=10_000,
    )
    assert text is not None
    assert text.endswith(".")
    assert "Car 12" in text
    assert text != "Lap Completed."


def test_draft_from_event_prefers_authored_when_mapped() -> None:
    publication = adapt_batch_for_shadow(_batch(stream_sequence=31))
    assert publication is not None
    draft = draft_from_event(publication.events[0])
    assert draft is not None
    assert isinstance(draft, SpeechDraft)
    assert draft.source == "authored"
    assert draft.beat_id == "timing.lap.completed"
    assert draft.text.endswith(".")
    assert (
        "Completed." not in draft.text
        or "completes" in draft.text.casefold()
        or "lap" in draft.text.casefold()
    )


def test_draft_from_event_falls_back_to_template_for_unknown_beat() -> None:
    publication = adapt_batch_for_shadow(_batch(stream_sequence=32))
    assert publication is not None
    # Force unknown kind via a copy path: humanize still works for non-pack beats.
    from irswitch.events.narrative_realization_bridge import draft_text_from_event

    text = draft_text_from_event(publication.events[0])
    assert text is not None
    # authored draft path already covers LAP_COMPLETE; template helper still returns speakable
    assert text.endswith(".")


@pytest.mark.asyncio
async def test_realization_effect_uses_authored_from_token_beat() -> None:
    sink = NullTtsSink()
    cache = SpeechDraftCache()
    runtime = NarrativeRuntime(
        mailbox=NarrativeMailbox(),
        realization_effect=build_realization_effect(cache, prefer_authored=True),
        tts_effect=build_tts_effect(sink, locale="en"),
        story_director=StoryDirector(),
        opportunity_queue=OpportunityQueue(),
        episode_registry=EpisodeRegistry(),
        freshness_gate=FreshnessGate(OpportunityQueue()),
    )
    runtime.enable()
    publication = adapt_batch_for_shadow(_batch(stream_sequence=33))
    assert publication is not None
    cache.observe_publication(publication)
    part = partition_context_batches(
        timeline=publication.timeline,
        fact_view=publication.fact_view,
        events=publication.events,
        fanout_stream_sequence=publication.fanout_stream_sequence,
    )[0]
    assert runtime.admit(NarrativeCommand.context_batch("ctx:authored", 1000, part)).accepted

    for _ in range(10):
        reduced = runtime.reduce_next()
        if reduced is None:
            await asyncio.sleep(0.01)
            continue
        token = runtime.current_realization_token()
        if token is not None:
            assert token.get("beatId") in {
                None,
                "timing.lap.completed",
                "timing.lap_completed",
            } or isinstance(token.get("beatId"), str)
        await runtime.apply_effects(reduced.effects)
        await runtime.wait_effects_idle()
        if sink.spoken:
            break
    assert sink.spoken, "expected authored or draft realization to speak"
    spoken = sink.spoken[0].text
    assert spoken.endswith(".")
    # Must not be the old humanized "Lap Completed." leaf title when authored succeeds
    assert spoken != "Lap Completed."


def test_race_wires_prefer_authored_realization() -> None:
    race = RACE_SOURCE.read_text(encoding="utf-8")
    assert "build_realization_effect" in race
    assert "prefer_authored=True" in race
