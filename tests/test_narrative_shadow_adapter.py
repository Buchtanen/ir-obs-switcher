"""#284 shadow adapter: FrozenAcceptedEventBatch → AdaptedPublication."""

from __future__ import annotations

from pathlib import Path

from test_n12_consumers import _batch

from irswitch.commentary.mailbox import NarrativeMailbox
from irswitch.events import __all__ as events_exports
from irswitch.events.narrative_ingress import NarrativeIngress
from irswitch.events.narrative_runtime import NarrativeRuntime
from irswitch.events.narrative_shadow_adapter import adapt_batch_for_shadow
from irswitch.events.narrative_shadow_consumer import NarrativeShadowConsumer

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


def test_adapt_batch_for_shadow_skips_overlay_only_batch() -> None:
    batch = _batch(stream_sequence=3, audience=("overlay",))
    assert adapt_batch_for_shadow(batch) is None


def test_race_enables_shadow_cutover_with_adapter_still_no_run() -> None:
    race = RACE_SOURCE.read_text(encoding="utf-8")
    assert "_narrative_shadow_enabled = True" in race
    assert "adapt_batch_for_shadow" in race
    assert "CommentaryConsumer" in race
    assert "narrative_runtime.run()" not in race
    assert "self.narrative_runtime.run()" not in race
