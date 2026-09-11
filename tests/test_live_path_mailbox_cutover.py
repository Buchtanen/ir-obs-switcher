"""#349 Slice 2 — mailbox cutover for ConfigUpdate/SessionReset + post-recovery revisions.

Sol tip audit: shadow consumer dropped SessionReset/ConfigUpdate, and the
shadow adapter pinned timeline/fact revisions, so after recovery every later
context stayed permanently stale.
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_n12_consumers import _batch
from test_narrative_runtime import _pure_fact

from irswitch.commentary.mailbox import NarrativeMailbox
from irswitch.contracts.command import NarrativeCommand
from irswitch.events.narrative_ingress import NarrativeIngress
from irswitch.events.narrative_runtime import NarrativeRuntime
from irswitch.events.narrative_shadow_adapter import adapt_batch_for_shadow
from irswitch.events.narrative_shadow_consumer import NarrativeShadowConsumer
from irswitch.events.stream import ConfigUpdate, SessionReset, freeze_config
from irswitch.overlay.bus import OverlayBus
from irswitch.overlay.settings import OverlaySettings
from irswitch.race.runtime import RaceRuntime


def test_shadow_adapter_revisions_follow_stream_sequence() -> None:
    low = adapt_batch_for_shadow(_batch(stream_sequence=7), narrative_run_active=True)
    high = adapt_batch_for_shadow(_batch(stream_sequence=110), narrative_run_active=True)
    assert low is not None and high is not None
    assert low.timeline["timelineRevision"] == 7
    assert low.fact_view["viewRevision"] == 7
    assert high.timeline["timelineRevision"] == 110
    assert high.fact_view["viewRevision"] == 110
    assert high.timeline["timelineRevision"] > low.timeline["timelineRevision"]


@pytest.mark.asyncio
async def test_shadow_consumer_admits_config_update_into_mailbox() -> None:
    mailbox = NarrativeMailbox()
    runtime = NarrativeRuntime(mailbox=mailbox)
    runtime.enable()
    consumer = NarrativeShadowConsumer(
        enabled=True,
        ingress=NarrativeIngress(mailbox),
        runtime=runtime,
        reduce_after_admit=True,
    )
    update = ConfigUpdate(
        generation=2,
        frozen_config=freeze_config(
            {"generation": 2, "language": "en", "commentary": {"enabled": False}}
        ),
        stream_sequence=15,
    )
    result = await consumer.handle(update)
    assert result is not None
    assert result.accepted is True
    assert "shadow_config_admitted" in result.effects
    assert runtime.status().config_valid is False


@pytest.mark.asyncio
async def test_shadow_consumer_admits_session_reset_into_mailbox() -> None:
    mailbox = NarrativeMailbox()
    runtime = NarrativeRuntime(mailbox=mailbox)
    runtime.enable()
    consumer = NarrativeShadowConsumer(
        enabled=True,
        ingress=NarrativeIngress(mailbox),
        runtime=runtime,
        reduce_after_admit=True,
    )
    seed = adapt_batch_for_shadow(_batch(stream_sequence=5), narrative_run_active=True)
    assert seed is not None
    assert consumer.handle_adapted_publication(seed).accepted is True
    reset = SessionReset(
        old_session_id="s1",
        new_session_id="s2",
        reason="session_changed",
        stream_sequence=20,
    )
    result = await consumer.handle(reset)
    assert result is not None
    assert result.accepted is True
    assert "shadow_session_reset_admitted" in result.effects
    assert runtime.status().timeline_revision == 20


def test_post_recovery_context_with_higher_stream_sequence_applies() -> None:
    """Stream-following revisions must clear the recovery barrier floor."""

    mailbox = NarrativeMailbox()
    runtime = NarrativeRuntime(mailbox=mailbox)
    runtime.enable()
    latest = _pure_fact("barrier:latest", revision=80, fanout=80)
    runtime.admit(
        NarrativeCommand.recovery(
            "recovery:1",
            9_000,
            latest_context=latest.context_part,
            loss_first_sequence=1,
            loss_last_sequence=2,
            safety_effects=(latest.safety_effect(),),
        )
    )
    recovered = runtime.reduce_next()
    assert recovered is not None
    assert runtime.status().history_complete is False

    publication = adapt_batch_for_shadow(_batch(stream_sequence=81), narrative_run_active=True)
    assert publication is not None
    assert publication.timeline["timelineRevision"] == 81
    consumer = NarrativeShadowConsumer(
        enabled=True,
        ingress=NarrativeIngress(mailbox),
        runtime=runtime,
        reduce_after_admit=True,
    )
    admitted = consumer.handle_adapted_publication(publication)
    assert admitted.accepted is True
    assert runtime.status().timeline_revision == 81


def test_race_runtime_still_gates_shadow_on_commentary_enabled() -> None:
    settings = OverlaySettings()
    settings = replace(settings, commentary=replace(settings.commentary, enabled=False))
    runtime = RaceRuntime(lambda: SimpleNamespace(overlay=settings), None, OverlayBus())
    assert runtime._narrative_shadow_enabled is False
