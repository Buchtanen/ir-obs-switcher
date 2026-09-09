"""#284 NarrativeIngress — shadow fanout→mailbox adapter (not live-wired)."""

from __future__ import annotations

from pathlib import Path

from test_narrative_context_batch import _event, _fact_view, _timeline

from irswitch.commentary.mailbox import NarrativeMailbox
from irswitch.events import __all__ as events_exports
from irswitch.events.narrative_ingress import NarrativeIngress, project_runtime_status
from irswitch.events.narrative_runtime import NarrativeRuntime, RuntimeStatus

SOURCE = (
    Path(__file__).resolve().parents[1] / "src" / "irswitch" / "events" / "narrative_ingress.py"
)


def test_ingress_source_documents_shadow_boundary() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    assert "Not exported from ``events/__init__.py``" in text
    assert "race.runtime" in text
    assert "commentary.consumer" in text
    assert "NarrativeIngress" not in events_exports
    assert "project_runtime_status" not in events_exports


def test_admit_context_publication_preserves_order_and_sequences() -> None:
    mailbox = NarrativeMailbox()
    ingress = NarrativeIngress(mailbox)
    events = tuple(_event(index) for index in range(3))
    result = ingress.admit_context_publication(
        timeline=_timeline(),
        fact_view=_fact_view(3),
        events=events,
        fanout_stream_sequence=11,
        command_id_prefix="pub:1",
        enqueued_mono_ms=2_000,
    )
    assert result.accepted
    assert result.reason == "accepted"
    assert result.command_ids == ("pub:1:0",)
    assert result.mailbox_sequences == (1,)
    assert "ingress_publication_complete" in result.effects
    assert len(mailbox) == 1
    command = mailbox.dequeue()
    assert command is not None
    assert command.kind == "APPLY_CONTEXT_BATCH"
    assert command.external_order is not None
    assert command.external_order.fanout_stream_sequence == 11
    assert command.external_order.first_source_ordinal == 0
    assert command.external_order.last_source_ordinal == 2


def test_admit_splits_at_64_events_preserving_total_order() -> None:
    ingress = NarrativeIngress()
    events = tuple(_event(index) for index in range(65))
    result = ingress.admit_context_publication(
        timeline=_timeline(),
        fact_view=_fact_view(65),
        events=events,
        fanout_stream_sequence=11,
        command_id_prefix="pub:split",
        enqueued_mono_ms=2_100,
    )
    assert result.accepted
    assert result.command_ids == ("pub:split:0", "pub:split:1")
    assert result.mailbox_sequences == (1, 2)
    first = ingress.mailbox.dequeue()
    second = ingress.mailbox.dequeue()
    assert first is not None and second is not None
    assert first.mailbox_sequence < second.mailbox_sequence
    assert first.external_order is not None and second.external_order is not None
    assert first.external_order.first_source_ordinal == 0
    assert first.external_order.last_source_ordinal == 63
    assert second.external_order.first_source_ordinal == 64
    assert second.external_order.last_source_ordinal == 64


def test_ingress_mailbox_can_feed_narrative_runtime_without_live_wiring() -> None:
    mailbox = NarrativeMailbox()
    ingress = NarrativeIngress(mailbox)
    result = ingress.admit_context_publication(
        timeline=_timeline(),
        fact_view=_fact_view(1),
        events=(_event(0),),
        fanout_stream_sequence=11,
        command_id_prefix="pub:rt",
        enqueued_mono_ms=2_200,
    )
    assert result.accepted
    runtime = NarrativeRuntime(mailbox=mailbox)
    runtime.enable()
    reduced = runtime.reduce_next()
    assert reduced is not None
    assert reduced.kind == "APPLY_CONTEXT_BATCH"
    assert reduced.disposition == "handled"
    assert "plan_dispatched" in reduced.effects


def test_project_runtime_status_emits_commentary_runtime_subset() -> None:
    runtime = NarrativeRuntime()
    runtime.enable()
    status = runtime.status()
    assert isinstance(status, RuntimeStatus)
    projection = project_runtime_status(status)
    assert projection["schemaVersion"] == "commentary-runtime/2"
    assert projection["status"] == "ready"
    assert projection["speech"]["state"] == "idle"
    assert projection["queues"]["mailbox"]["capacity"] == 64
    assert projection["queues"]["mailbox"]["depth"] == 0
    assert projection["timeline"]["historyComplete"] is True
    assert projection["recovery"]["count"] == 0
    assert "admissionDiagnostics" in projection["diagnostics"]
