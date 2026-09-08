"""#245 typed AtomicFact ledger, provenance and bounded FactViews."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from irswitch.contracts import (
    AtomicFact,
    ContractViolation,
    FactProducer,
    FactScope,
    FactStatus,
    FactView,
    fact_producer,
    load_fact_registry,
    semantic_key,
)
from irswitch.events.fact_ledger import (
    FactLedger,
    FactProjection,
    FactViewProjector,
)

ROOT = Path(__file__).resolve().parents[1]


def _projection(
    *,
    occurrence_id: str | None = "1:race:0",
    lineage_id: str | None = "1:practice:0>1:race:0",
    stream_epoch: int = 1,
    history_complete: bool = True,
) -> FactProjection:
    return FactProjection(
        broadcast_epoch=4,
        stream_epoch=stream_epoch,
        occurrence_id=occurrence_id,
        lineage_id=lineage_id,
        history_complete=history_complete,
    )


def _fact(
    fact_id: str,
    *,
    predicate: str = "battle.closing",
    subject_id: str | None = "car:12",
    object_id: str | None = "car:34",
    attributes: dict[str, object] | None = None,
    scope: str = "occurrence",
    status: str = "active",
    occurrence_id: str | None = "1:race:0",
    lineage_id: str | None = "1:practice:0>1:race:0",
    observed_at: int = 1_000,
    valid_from: int = 900,
    valid_until: int | None = 2_000,
    revision: int = 0,
    stream_epoch: int = 1,
    evidence: tuple[str, ...] = ("telemetry:1",),
) -> AtomicFact:
    if attributes is None:
        if predicate == "battle.closing":
            attributes = {
                "gap": 0.42,
                "netClosing": 0.2,
                "slope": -0.05,
                "targetEpoch": "rel:1",
            }
        elif predicate == "stream.started":
            attributes = {"startReason": "normal"}
        elif predicate == "broadcast.context":
            attributes = {"context": "on_track"}
        elif predicate == "timing.personal_best":
            attributes = {
                "lapTime": 91.2,
                "referenceTime": 91.8,
                "improvement": 0.6,
            }
        elif predicate == "session.started":
            attributes = {"stage": "race", "startReason": "normal_transition"}
        else:
            attributes = {}
    return AtomicFact(
        fact_id=fact_id,
        predicate=predicate,
        subject_id=subject_id,
        object_id=object_id,
        attributes=attributes,
        polarity="positive",
        valid_from_mono_ms=valid_from,
        valid_until_mono_ms=valid_until,
        observed_at_mono_ms=observed_at,
        broadcast_epoch=4,
        stream_epoch=stream_epoch,
        occurrence_id=occurrence_id,
        lineage_id=lineage_id,
        evidence_refs=evidence,
        confidence=0.8,
        scope=scope,
        status=status,
        revision=revision,
    )


def test_registry_exposes_the_frozen_57_predicates() -> None:
    registry = load_fact_registry()
    assert len(registry.predicates) == 57
    assert registry.require("stream.started").scope is FactScope.STREAM
    assert registry.require("battle.closing").scope is FactScope.OCCURRENCE


def test_atomic_fact_wire_round_trip_and_stream_nullability() -> None:
    started = _fact(
        "fact:stream:1",
        predicate="stream.started",
        subject_id=None,
        object_id=None,
        scope="stream",
        occurrence_id=None,
        lineage_id=None,
        valid_until=None,
    )
    payload = started.to_dict()
    assert payload["schemaVersion"] == "atomic-fact/2"
    assert payload["occurrenceId"] is None
    assert payload["lineageId"] is None
    assert AtomicFact.from_dict(payload) == started


def test_non_stream_facts_require_occurrence_and_lineage() -> None:
    with pytest.raises(ContractViolation):
        _fact("fact:bad", occurrence_id=None, lineage_id=None)
    missing = {
        "gap": 0.42,
        "netClosing": 0.2,
        "slope": -0.05,
        # targetEpoch missing — unknown, not a zero gap
    }
    with pytest.raises(ContractViolation):
        _fact("fact:missing", attributes=missing)


def test_semantic_key_does_not_reuse_stream_identity_for_session_facts() -> None:
    stream = _fact(
        "fact:stream:1",
        predicate="broadcast.context",
        subject_id=None,
        object_id=None,
        scope="stream",
        occurrence_id=None,
        lineage_id=None,
        valid_until=None,
    )
    race = _fact("fact:battle:1")
    assert semantic_key(stream)[4] is None
    assert semantic_key(race)[4] == "1:race:0"
    assert semantic_key(stream) != semantic_key(race)


def test_admit_publishes_sorted_immutable_view() -> None:
    ledger = FactLedger()
    first = ledger.apply((_fact("fact:battle:1"),), now_ms=1_000, projection=_projection())
    assert first.view is not None
    assert first.view.view_revision == 1
    assert [str(fact.fact_id) for fact in first.view.facts] == ["fact:battle:1"]
    assert first.view.to_dict()["schemaVersion"] == "fact-view/2"
    resolved = ledger.resolve("fact:battle:1")
    assert resolved.revision == 0
    assert resolved.evidence_refs[0] == "telemetry:1"
    assert ledger.current("battle.closing", subject_id="car:12", object_id="car:34") == resolved


def test_same_semantic_key_supersedes_without_growing_active_storage() -> None:
    ledger = FactLedger()
    ledger.apply((_fact("fact:battle:1"),), now_ms=1_000, projection=_projection())
    updated = _fact("fact:battle:2", observed_at=1_100, valid_from=1_050)
    step = ledger.apply((updated,), now_ms=1_100, projection=_projection())
    assert step.view is not None
    assert [str(fact.fact_id) for fact in step.view.facts] == ["fact:battle:2"]
    assert "fact_superseded" in step.diagnostics
    assert ledger.resolve("fact:battle:1").status is FactStatus.SUPERSEDED
    assert ledger.resolve("fact:battle:2").revision == 1
    assert len([fact for fact in step.view.facts if fact.status is FactStatus.ACTIVE]) == 1


def test_half_open_expiry_publishes_fact_only_view() -> None:
    ledger = FactLedger()
    ledger.apply(
        (_fact("fact:battle:1", valid_until=1_500),), now_ms=1_000, projection=_projection()
    )
    still_current = ledger.expire(1_499)
    assert still_current.view is not None
    assert ledger.current("battle.closing", subject_id="car:12", object_id="car:34") is not None
    expired = ledger.expire(1_500)
    assert expired.view is not None
    assert expired.view.view_revision == 2
    assert "fact_expired" in expired.diagnostics
    assert ledger.current("battle.closing", subject_id="car:12", object_id="car:34") is None
    assert ledger.resolve("fact:battle:1").status is FactStatus.EXPIRED


def test_eviction_marks_unknown_not_false_and_keeps_pinned_summaries() -> None:
    ledger = FactLedger(active_capacity=2)
    projection = _projection()
    stream = _fact(
        "fact:stream:1",
        predicate="broadcast.context",
        subject_id=None,
        object_id=None,
        scope="stream",
        occurrence_id=None,
        lineage_id=None,
        valid_until=None,
    )
    downstream = _fact(
        "fact:best:1",
        predicate="timing.personal_best",
        subject_id="car:12",
        object_id=None,
        scope="downstream",
        occurrence_id="1:practice:0",
        lineage_id="1:practice:0",
        valid_until=None,
    )
    closing = _fact("fact:battle:1", observed_at=800)
    step = ledger.apply((stream, downstream, closing), now_ms=1_000, projection=projection)
    assert step.view is not None
    assert "fact_capacity_evicted" in step.diagnostics
    assert step.view.history_complete is False
    assert ledger.current("broadcast.context") is not None
    assert ledger.current("timing.personal_best", subject_id="car:12") is not None
    assert ledger.current("battle.closing", subject_id="car:12", object_id="car:34") is None
    unknown = [fact for fact in step.view.facts if fact.status is FactStatus.UNKNOWN]
    assert unknown
    assert unknown[0].attributes == ()
    assert "gap" not in dict(unknown[0].attributes)


def test_pinned_exhaustion_publishes_no_partial_view() -> None:
    ledger = FactLedger(active_capacity=1)
    first = _fact(
        "fact:ctx:1",
        predicate="broadcast.context",
        subject_id=None,
        object_id=None,
        scope="stream",
        occurrence_id=None,
        lineage_id=None,
        valid_until=None,
    )
    second = _fact(
        "fact:stream:1",
        predicate="stream.started",
        subject_id=None,
        object_id=None,
        scope="stream",
        occurrence_id=None,
        lineage_id=None,
        valid_until=None,
    )
    step = ledger.apply((first, second), now_ms=1_000, projection=_projection())
    assert step.view is None
    assert step.exhausted is True
    assert "fact_capacity_exhausted" in step.diagnostics
    assert ledger.latest_view() is None
    assert ledger.current("broadcast.context") is None


def test_projector_rejects_stale_revision_visibly() -> None:
    ledger = FactLedger()
    first = ledger.apply((_fact("fact:battle:1"),), now_ms=1_000, projection=_projection())
    second = ledger.apply(
        (_fact("fact:battle:2", observed_at=1_100, valid_from=1_050),),
        now_ms=1_100,
        projection=_projection(),
    )
    projector = FactViewProjector()
    assert first.view is not None and second.view is not None
    assert projector.apply(second.view).accepted is True
    stale = projector.apply(first.view)
    assert stale.accepted is False
    assert stale.diagnostic == "fact_view_revision_stale"
    assert stale.view is not None
    assert stale.view.view_revision == 2


def test_apply_is_deterministic_and_does_not_import_runtime() -> None:
    facts = (
        _fact(
            "fact:stream:1",
            predicate="stream.started",
            subject_id=None,
            object_id=None,
            scope="stream",
            occurrence_id=None,
            lineage_id=None,
            valid_until=None,
        ),
        _fact("fact:battle:1"),
    )
    left = FactLedger()
    right = FactLedger()
    projection = _projection()
    assert (
        left.apply(facts, now_ms=1_000, projection=projection).view
        == right.apply(facts, now_ms=1_000, projection=projection).view
    )
    imports = [
        line
        for line in (ROOT / "src/irswitch/events/fact_ledger.py")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.startswith("from ") or line.startswith("import ")
    ]
    joined = "\n".join(imports)
    assert "NarrativeRuntime" not in joined
    assert "DetectorBank" not in joined
    assert "overlay.tape" not in joined
    commentary_init = (ROOT / "src/irswitch/commentary/__init__.py").read_text(encoding="utf-8")
    assert "FactLedger" not in commentary_init
    events_init = (ROOT / "src/irswitch/events/__init__.py").read_text(encoding="utf-8")
    assert "FactLedger" not in events_init


def test_new_stream_epoch_resets_and_does_not_reuse_old_revision() -> None:
    ledger = FactLedger()
    ledger.apply((_fact("fact:battle:1"),), now_ms=1_000, projection=_projection())
    stale_epoch = _fact("fact:battle:8")
    with pytest.raises(ContractViolation):
        ledger.apply((stale_epoch,), now_ms=2_000, projection=_projection(stream_epoch=2))
    later = _fact("fact:battle:9", stream_epoch=2, valid_until=None)
    step = ledger.apply((later,), now_ms=2_000, projection=_projection(stream_epoch=2))
    assert step.view is not None
    assert step.view.stream_epoch == 2
    assert step.view.view_revision == 1
    assert [str(fact.fact_id) for fact in step.view.facts] == ["fact:battle:9"]


def test_registry_assigns_closed_producer_families() -> None:
    registry = load_fact_registry()
    families = {name: spec.producer_class for name, spec in registry.predicates.items()}
    assert len(families) == 57
    assert families["stream.started"] is FactProducer.TIMELINE
    assert families["session.next_present_stage"] is FactProducer.TIMELINE
    assert families["broadcast.context"] is FactProducer.SNAPSHOT
    assert families["context.track_identity"] is FactProducer.SNAPSHOT
    assert families["battle.closing"] is FactProducer.DETECTOR
    assert families["battle.approaching"] is FactProducer.DETECTOR
    assert families["timing.pace_target"] is FactProducer.DETECTOR
    assert fact_producer("bio.hr_state") is FactProducer.DETECTOR
    assert sum(1 for item in families.values() if item is FactProducer.TIMELINE) == 5
    assert sum(1 for item in families.values() if item is FactProducer.DETECTOR) == 9
    assert sum(1 for item in families.values() if item is FactProducer.SNAPSHOT) == 43


def test_apply_sources_uses_timeline_then_snapshot_then_detector() -> None:
    ledger = FactLedger()
    timeline = _fact(
        "fact:stream:1",
        predicate="stream.started",
        subject_id=None,
        object_id=None,
        scope="stream",
        occurrence_id=None,
        lineage_id=None,
        valid_until=None,
    )
    snapshot = _fact(
        "fact:ctx:1",
        predicate="broadcast.context",
        subject_id=None,
        object_id=None,
        scope="stream",
        occurrence_id=None,
        lineage_id=None,
        valid_until=None,
        observed_at=1_100,
        valid_from=1_100,
    )
    detector = _fact("fact:battle:1", observed_at=1_200, valid_from=1_200)
    misplaced = ledger.apply_sources
    with pytest.raises(ContractViolation, match="not detector"):
        misplaced(
            now_ms=1_200,
            projection=_projection(),
            detector=(timeline,),
        )
    first = _fact(
        "fact:ctx:old",
        predicate="broadcast.context",
        subject_id=None,
        object_id=None,
        scope="stream",
        occurrence_id=None,
        lineage_id=None,
        valid_until=None,
        observed_at=900,
        valid_from=900,
    )
    step = ledger.apply_sources(
        now_ms=1_200,
        projection=_projection(),
        timeline=(timeline,),
        snapshot=(first, snapshot),
        detector=(detector,),
    )
    assert step.view is not None
    assert step.view.view_revision == 1
    assert [str(fact.fact_id) for fact in step.view.facts] == [
        "fact:battle:1",
        "fact:ctx:1",
        "fact:stream:1",
    ]
    assert ledger.current("broadcast.context") is not None
    assert str(ledger.current("broadcast.context").fact_id) == "fact:ctx:1"


def test_validate_bindings_reuse_atomic_fact_schema() -> None:
    dto = json.loads(
        (ROOT / "src/irswitch/contracts/schemas/v2/dto-contracts.schema.json").read_text(
            encoding="utf-8"
        )
    )
    api = json.loads(
        (ROOT / "docs/v2.0.0/machine/api-contracts.schema.json").read_text(encoding="utf-8")
    )
    assert dto["$defs"]["AtomicFact"] == api["$defs"]["AtomicFact"]
    payload = _fact(
        "fact:stream:1",
        predicate="stream.started",
        subject_id=None,
        object_id=None,
        scope="stream",
        occurrence_id=None,
        lineage_id=None,
        valid_until=None,
    ).to_dict()
    assert AtomicFact.from_dict(payload).to_dict() == payload


def test_fact_view_rejects_unsorted_or_future_observations() -> None:
    first = _fact("fact:b")
    second = _fact("fact:a", predicate="session.started", subject_id=None, object_id=None)
    with pytest.raises(ContractViolation):
        FactView(
            view_revision=1,
            created_mono_ms=1_000,
            broadcast_epoch=4,
            stream_epoch=1,
            occurrence_id=first.occurrence_id,
            lineage_id=first.lineage_id,
            history_complete=True,
            facts=(first, second),
            compacted_summary_refs=(),
        )
    late = _fact("fact:late", observed_at=2_000)
    with pytest.raises(ContractViolation):
        FactView(
            view_revision=1,
            created_mono_ms=1_000,
            broadcast_epoch=4,
            stream_epoch=1,
            occurrence_id=late.occurrence_id,
            lineage_id=late.lineage_id,
            history_complete=True,
            facts=(late,),
            compacted_summary_refs=(),
        )
