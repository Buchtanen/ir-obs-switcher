"""#284 shadow adapter: FrozenAcceptedEventBatch → AdaptedPublication."""

from __future__ import annotations

import time
from pathlib import Path

from test_n12_consumers import _batch, _context

from irswitch.commentary.mailbox import NarrativeMailbox
from irswitch.events import __all__ as events_exports
from irswitch.events.envelope import make_envelope
from irswitch.events.narrative_ingress import NarrativeIngress
from irswitch.events.narrative_runtime import NarrativeRuntime
from irswitch.events.narrative_shadow_adapter import adapt_batch_for_shadow
from irswitch.events.narrative_shadow_consumer import NarrativeShadowConsumer
from irswitch.events.stream import FrozenAcceptedEventBatch, freeze_accepted_event

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "irswitch"
    / "events"
    / "narrative_shadow_adapter.py"
)
RACE_SOURCE = Path(__file__).resolve().parents[1] / "src" / "irswitch" / "race" / "runtime.py"


def test_shadow_adapter_source_documents_observation_boundary() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    assert "Not exported from ``events/__init__.py``" in text
    assert "observation-only" in text or "Observation-only" in text
    assert "adapt_batch_for_shadow" not in events_exports


def test_adapt_batch_for_shadow_admits_and_reduces_live_shaped_batch() -> None:
    batch = _batch(stream_sequence=21)
    publication = adapt_batch_for_shadow(batch)
    assert publication is not None
    assert publication.fanout_stream_sequence == 21
    assert len(publication.events) >= 1
    mailbox = NarrativeMailbox()
    runtime = NarrativeRuntime(mailbox=mailbox)
    runtime.enable()
    consumer = NarrativeShadowConsumer(
        enabled=True,
        ingress=NarrativeIngress(mailbox),
        runtime=runtime,
    )
    result = consumer.handle_adapted_publication(publication)
    assert result.accepted is True
    assert "shadow_reduced" in result.effects
    assert len(mailbox) == 0


def _mixed_source_batch(*, stream_sequence: int = 40) -> FrozenAcceptedEventBatch:
    """Two commentary events, each source_ordinal=0 — live RacePipeline shape."""

    hunting = freeze_accepted_event(
        make_envelope(
            event_type="HUNTING",
            phase="ENTER",
            mode="RACE",
            event_id="session:HUNTING:1",
            sequence=1,
            session_id="session",
            priority=20,
            monotonic_ms=int(time.monotonic() * 1000),
            dedupe_key="hunting",
            correlation_id="battle:front:1",
        ),
        audiences=("overlay", "commentary"),
        source="battle",
        source_ordinal=0,
    )
    pace = freeze_accepted_event(
        make_envelope(
            event_type="PACE_HUNT",
            phase="RESULT",
            mode="RACE",
            event_id="session:PACE_HUNT:1",
            sequence=2,
            session_id="session",
            priority=40,
            monotonic_ms=int(time.monotonic() * 1000),
            dedupe_key="pace_hunt",
            correlation_id="pace:1",
        ),
        audiences=("commentary",),
        source="timing",
        source_ordinal=0,
    )
    return FrozenAcceptedEventBatch(
        stream_sequence,
        "session",
        1,
        int(time.monotonic() * 1000),
        1,
        _context(),
        (hunting, pace),
    )


def test_adapt_batch_for_shadow_renumbers_mixed_source_ordinals() -> None:
    batch = _mixed_source_batch()
    assert batch.events[0].source_ordinal == 0
    assert batch.events[1].source_ordinal == 0
    publication = adapt_batch_for_shadow(batch, narrative_run_active=True)
    assert publication is not None
    ordinals = [event.source_order.source_ordinal for event in publication.events]
    assert ordinals == [0, 1]
    mailbox = NarrativeMailbox()
    runtime = NarrativeRuntime(mailbox=mailbox)
    runtime.enable()
    consumer = NarrativeShadowConsumer(
        enabled=True,
        ingress=NarrativeIngress(mailbox),
        runtime=runtime,
    )
    result = consumer.handle_adapted_publication(publication)
    assert result.accepted is True
    assert result.reason != "contract_violation"


def test_adapt_batch_for_shadow_skips_overlay_only_batch() -> None:
    batch = _batch(stream_sequence=3, audience=("overlay",))
    assert adapt_batch_for_shadow(batch) is None


def test_race_enables_shadow_cutover_with_adapter_and_actor_run() -> None:
    race = RACE_SOURCE.read_text(encoding="utf-8")
    assert "commentary_enabled = commentary_live_enabled(self._get_config())" in race
    assert "self._narrative_shadow_enabled = commentary_enabled" in race
    assert "commentary_llm_enabled" in race
    assert "_narrative_subscription_cutover = True" in race
    assert "adapt_batch_for_shadow" in race
    assert "CommentaryConsumer" in race
    assert "reduce_after_admit=False" in race
    assert "legacy_stream_handler=None" in race
    assert "_mirror_lifecycle_without_speech" not in race
    assert "build_tts_effect" in race
    assert "_run_narrative_runtime_actor" in race or "narrative_runtime.run" in race
    assert '"narrative_runtime"' in race or "'narrative_runtime'" in race
