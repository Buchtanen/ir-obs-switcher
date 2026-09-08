"""Upstream FactLedger. Sole writer of immutable FactViews.

Does not import NarrativeRuntime, DetectorBank, mailbox or overlay tape.
Commentary may project a published view; it must not call admit().
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from irswitch.contracts.fact import (
    AtomicFact,
    FactProducer,
    FactScope,
    FactStatus,
    FactView,
    fact_producer,
    semantic_key,
)
from irswitch.contracts.primitives import (
    ContractViolation,
    Identifier,
    LineageId,
    MonotonicMs,
    OccurrenceId,
)

ACTIVE_CAP = 512
HISTORICAL_CAP = 512
_PINNED_SCOPES = frozenset({FactScope.STREAM, FactScope.DOWNSTREAM})
_TERMINAL = frozenset(
    {
        FactStatus.EXPIRED,
        FactStatus.SUPERSEDED,
        FactStatus.HISTORICAL,
        FactStatus.REJECTED,
    }
)


@dataclass(frozen=True, slots=True)
class FactProjection:
    broadcast_epoch: int
    stream_epoch: int
    occurrence_id: str | None
    lineage_id: str | None
    history_complete: bool = True


@dataclass(frozen=True, slots=True)
class FactLedgerStep:
    view: FactView | None
    diagnostics: tuple[str, ...] = ()
    exhausted: bool = False


@dataclass(frozen=True, slots=True)
class FactProjectionStep:
    view: FactView | None
    accepted: bool
    diagnostic: str | None = None


def _lineage_members(lineage_id: str | None) -> frozenset[str]:
    if not lineage_id:
        return frozenset()
    return frozenset(lineage_id.split(">"))


@dataclass
class FactLedger:
    """Process-local typed fact store. Replay-deterministic for the same admits."""

    active_capacity: int = ACTIVE_CAP
    historical_capacity: int = HISTORICAL_CAP
    _active: dict[str, AtomicFact] = field(default_factory=dict)
    _historical: dict[str, AtomicFact] = field(default_factory=dict)
    _keys: dict[tuple[object, ...], str] = field(default_factory=dict)
    _revisions: dict[tuple[object, ...], int] = field(default_factory=dict)
    _view: FactView | None = None
    _view_revision: int = 0
    _history_complete: bool = True
    _exhausted: bool = False
    _unknown_ordinal: int = 0
    _projection: FactProjection | None = None

    def latest_view(self) -> FactView | None:
        return None if self._exhausted else self._view

    def resolve(self, fact_id: str) -> AtomicFact:
        key = str(Identifier(fact_id))
        if key in self._active:
            return self._active[key]
        if key in self._historical:
            return self._historical[key]
        raise ContractViolation(f"unknown factId: {key}")

    def current(
        self,
        predicate: str,
        *,
        subject_id: str | None = None,
        object_id: str | None = None,
    ) -> AtomicFact | None:
        """Return the current speakable fact, or None when the claim is unknown."""

        if self._exhausted or self._view is None:
            return None
        for fact in self._view.facts:
            if (
                fact.predicate == predicate
                and fact.subject_id == subject_id
                and fact.object_id == object_id
                and fact.status in {FactStatus.ACTIVE, FactStatus.PROVISIONAL}
            ):
                return fact
        return None

    def apply_sources(
        self,
        *,
        now_ms: int,
        projection: FactProjection,
        timeline: tuple[AtomicFact, ...] = (),
        snapshot: tuple[AtomicFact, ...] = (),
        detector: tuple[AtomicFact, ...] = (),
    ) -> FactLedgerStep:
        """Admit timeline, then normalized snapshot, then detector evidence."""

        self._require_producer(timeline, FactProducer.TIMELINE)
        self._require_producer(snapshot, FactProducer.SNAPSHOT)
        self._require_producer(detector, FactProducer.DETECTOR)
        return self.apply(
            (*timeline, *snapshot, *detector),
            now_ms=now_ms,
            projection=projection,
        )

    @staticmethod
    def _require_producer(facts: tuple[AtomicFact, ...], expected: FactProducer) -> None:
        for fact in facts:
            actual = fact_producer(fact.predicate)
            if actual is not expected:
                raise ContractViolation(
                    f"predicate {fact.predicate} is {actual.value}, not {expected.value}"
                )

    def apply(
        self,
        facts: tuple[AtomicFact, ...],
        *,
        now_ms: int,
        projection: FactProjection,
    ) -> FactLedgerStep:
        self._align_run(projection)
        changed = False
        diagnostics: list[str] = []
        for fact in facts:
            if self._admit_one(fact, now_ms=now_ms, projection=projection, diagnostics=diagnostics):
                changed = True
        expired = self._expire(now_ms)
        if expired:
            changed = True
            diagnostics.append("fact_expired")
        if not changed and self._view is not None and not self._exhausted:
            return FactLedgerStep(view=self._view, diagnostics=tuple(dict.fromkeys(diagnostics)))
        return self._publish(now_ms=now_ms, projection=projection, diagnostics=diagnostics)

    def expire(self, now_ms: int) -> FactLedgerStep:
        if self._projection is None:
            return FactLedgerStep(view=None)
        if not self._expire(now_ms):
            return FactLedgerStep(view=self.latest_view())
        return self._publish(
            now_ms=now_ms,
            projection=self._projection,
            diagnostics=["fact_expired"],
        )

    def _align_run(self, projection: FactProjection) -> None:
        if self._projection is None or self._projection.stream_epoch != projection.stream_epoch:
            self._active.clear()
            self._historical.clear()
            self._keys.clear()
            self._revisions.clear()
            self._view = None
            self._view_revision = 0
            self._history_complete = projection.history_complete
            self._exhausted = False
            self._unknown_ordinal = 0
        self._projection = projection

    def _admit_one(
        self,
        fact: AtomicFact,
        *,
        now_ms: int,
        projection: FactProjection,
        diagnostics: list[str],
    ) -> bool:
        if int(fact.observed_at_mono_ms) > now_ms:
            raise ContractViolation("observedAtMonoMs cannot be later than FactView createdMonoMs")
        if int(fact.broadcast_epoch) != projection.broadcast_epoch:
            raise ContractViolation("AtomicFact broadcastEpoch must match the projection")
        if int(fact.stream_epoch) != projection.stream_epoch:
            raise ContractViolation("AtomicFact streamEpoch must match the projection")
        if fact.scope is not FactScope.STREAM:
            if projection.occurrence_id is None or projection.lineage_id is None:
                raise ContractViolation("session-scoped facts require a coherent occurrence")
        key = semantic_key(fact)
        previous_id = self._keys.get(key)
        revision = self._revisions.get(key, -1) + 1
        admitted = replace(fact, revision=revision)
        if previous_id is not None and previous_id in self._active:
            previous = self._active.pop(previous_id)
            self._historical[previous_id] = replace(
                previous,
                status=FactStatus.SUPERSEDED,
                valid_until_mono_ms=previous.valid_until_mono_ms or fact.valid_from_mono_ms,
            )
            diagnostics.append("fact_superseded")
        self._revisions[key] = revision
        self._keys[key] = str(admitted.fact_id)
        if admitted.status in {FactStatus.ACTIVE, FactStatus.PROVISIONAL}:
            self._active[str(admitted.fact_id)] = admitted
        else:
            self._historical[str(admitted.fact_id)] = admitted
        self._compact_inactive()
        return True

    def _expire(self, now_ms: int) -> bool:
        changed = False
        for fact_id, fact in list(self._active.items()):
            if fact.valid_until_mono_ms is None:
                continue
            if now_ms < int(fact.valid_until_mono_ms):
                continue
            self._active.pop(fact_id)
            self._historical[fact_id] = replace(fact, status=FactStatus.EXPIRED)
            changed = True
        if changed:
            self._compact_inactive()
        return changed

    def _is_pinned(self, fact: AtomicFact, projection: FactProjection) -> bool:
        if fact.status not in {FactStatus.ACTIVE, FactStatus.PROVISIONAL}:
            return False
        if fact.scope is FactScope.STREAM:
            return True
        if fact.scope is FactScope.DOWNSTREAM:
            occurrence = None if fact.occurrence_id is None else str(fact.occurrence_id)
            return occurrence in _lineage_members(projection.lineage_id)
        return False

    def _evict_unpinned(self, projection: FactProjection, diagnostics: list[str]) -> None:
        unpinned = [
            fact
            for fact in self._active.values()
            if not self._is_pinned(fact, projection)
            and fact.scope in {FactScope.OCCURRENCE, FactScope.REVALIDATE}
        ]
        unpinned.sort(
            key=lambda fact: (int(fact.observed_at_mono_ms), fact.revision, str(fact.fact_id))
        )
        while len(self._active) > self.active_capacity and unpinned:
            fact = unpinned.pop(0)
            self._active.pop(str(fact.fact_id), None)
            self._unknown_ordinal += 1
            unknown = replace(
                fact,
                fact_id=Identifier(f"fact:unknown:{self._unknown_ordinal}"),
                status=FactStatus.UNKNOWN,
                attributes=(),
                evidence_refs=(Identifier("ledger:evicted"),),
            )
            self._historical[str(fact.fact_id)] = replace(fact, status=FactStatus.HISTORICAL)
            self._historical[str(unknown.fact_id)] = unknown
            self._keys[semantic_key(fact)] = str(unknown.fact_id)
            self._history_complete = False
            diagnostics.append("fact_capacity_evicted")

    def _compact_inactive(self) -> None:
        if len(self._historical) <= self.historical_capacity:
            return
        removable = [fact for fact in self._historical.values() if fact.status in _TERMINAL]
        removable.sort(
            key=lambda fact: (int(fact.observed_at_mono_ms), fact.revision, str(fact.fact_id))
        )
        while len(self._historical) > self.historical_capacity and removable:
            fact = removable.pop(0)
            self._historical.pop(str(fact.fact_id), None)
            if self._keys.get(semantic_key(fact)) == str(fact.fact_id):
                self._keys.pop(semantic_key(fact), None)

    def _publish(
        self,
        *,
        now_ms: int,
        projection: FactProjection,
        diagnostics: list[str],
    ) -> FactLedgerStep:
        self._evict_unpinned(projection, diagnostics)
        pinned = [fact for fact in self._active.values() if self._is_pinned(fact, projection)]
        if len(pinned) > self.active_capacity:
            self._exhausted = True
            self._view = None
            diagnostics.append("fact_capacity_exhausted")
            return FactLedgerStep(
                view=None, diagnostics=tuple(dict.fromkeys(diagnostics)), exhausted=True
            )
        if len(self._active) > self.active_capacity:
            self._exhausted = True
            self._view = None
            diagnostics.append("fact_capacity_exhausted")
            return FactLedgerStep(
                view=None, diagnostics=tuple(dict.fromkeys(diagnostics)), exhausted=True
            )
        self._exhausted = False
        published = [fact for fact in self._active.values() if fact.is_current(now_ms)]
        published.extend(
            fact for fact in self._historical.values() if fact.status is FactStatus.UNKNOWN
        )
        published.sort(key=lambda fact: str(fact.fact_id))
        occurrence = (
            None
            if projection.occurrence_id is None
            else OccurrenceId.parse(projection.occurrence_id)
        )
        lineage = None if projection.lineage_id is None else LineageId.parse(projection.lineage_id)
        self._view_revision += 1
        self._view = FactView(
            view_revision=self._view_revision,
            created_mono_ms=MonotonicMs(now_ms),
            broadcast_epoch=projection.broadcast_epoch,
            stream_epoch=projection.stream_epoch,
            occurrence_id=occurrence,
            lineage_id=lineage,
            history_complete=self._history_complete,
            facts=tuple(published),
            compacted_summary_refs=(),
        )
        return FactLedgerStep(
            view=self._view,
            diagnostics=tuple(dict.fromkeys(diagnostics)),
            exhausted=False,
        )


@dataclass
class FactViewProjector:
    """Read-only consumer of published views. Never mutates FactLedger."""

    _view: FactView | None = None

    def apply(self, view: FactView) -> FactProjectionStep:
        if self._view is not None and view.view_revision < self._view.view_revision:
            return FactProjectionStep(
                view=self._view,
                accepted=False,
                diagnostic="fact_view_revision_stale",
            )
        self._view = view
        return FactProjectionStep(view=view, accepted=True)

    def latest(self) -> FactView | None:
        return self._view
