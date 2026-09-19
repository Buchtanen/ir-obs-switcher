"""#278 Slice 11 — offline F32/F38 facts-capacity + realization freshness drivers.

Consumes frozen machine rows and proves FactLedger/EpisodeRegistry capacity
locks (update without growth, deterministic eviction to unknown-not-false,
pinned exhaustion without partial publish, degraded recover, eviction order,
pinned reject) plus FreshnessGate/AuthoredRealizer frozen-bundle freshness
locks. Does not rewrite ``docs/v2.0.0/machine/*`` hashes and does not claim
live §24.9 GO.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from test_authored_pack import _bundle, _lexicon
from test_episode_registry import _intent, _order
from test_fact_ledger import _fact, _projection
from test_freshness_commit import _fact as _bound_fact
from test_freshness_commit import _token, _world

from irswitch.contracts import FactStatus
from irswitch.contracts.authored_pack import AuthoredRealizer
from irswitch.events.episode_registry import EpisodeRegistry
from irswitch.events.fact_ledger import FactLedger
from irswitch.events.freshness_commit import FreshnessGate

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
FIXTURES_PATH = MACHINE / "vertical-slice-fixtures.json"
BUILDER_PATH = MACHINE / "build_vertical_slice_fixtures.py"

SLICE11_IDS = ("F32", "F38")


def _load_builder() -> Any:
    module_name = "irswitch_vertical_slice_facts_freshness_builder_under_test"
    if module_name in sys.modules:
        return sys.modules[module_name]
    machine_path = str(MACHINE)
    if machine_path not in sys.path:
        sys.path.insert(0, machine_path)
    spec = importlib.util.spec_from_file_location(module_name, BUILDER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


builder = _load_builder()


@pytest.fixture(scope="module")
def fixtures_by_id() -> dict[str, dict[str, Any]]:
    bundle = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    return {row["id"]: row for row in bundle["fixtures"]}


@pytest.mark.parametrize("fixture_id", SLICE11_IDS)
def test_slice11_machine_projection_and_calculations(
    fixtures_by_id: dict[str, dict[str, Any]], fixture_id: str
) -> None:
    row = fixtures_by_id[fixture_id]
    assert builder.execute_model(row) == row["expectations"]
    for calculation in row.get("calculations") or ():
        assert builder.evaluate(calculation) == calculation["expected"]


def test_f32_fact_and_episode_capacity_fail_unknown_never_false(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F32: bounded facts/episodes evict deterministically without inventing falsehood."""

    expected = set(fixtures_by_id["F32"]["expectations"])
    observed: set[str] = set()
    projection = _projection()

    ledger = FactLedger(active_capacity=8)
    ledger.apply((_fact("fact:battle:1"),), now_ms=1_000, projection=projection)
    updated = ledger.apply(
        (_fact("fact:battle:2", observed_at=1_100, revision=1, valid_from=1_050),),
        now_ms=1_100,
        projection=projection,
    )
    assert "fact_superseded" in updated.diagnostics
    assert len([fact for fact in updated.view.facts if fact.status is FactStatus.ACTIVE]) == 1
    observed.add("update_no_growth")

    crowded = FactLedger(active_capacity=2)
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
    evicted = crowded.apply((stream, downstream, closing), now_ms=1_000, projection=projection)
    assert "fact_capacity_evicted" in evicted.diagnostics
    assert crowded.current("battle.closing", subject_id="car:12", object_id="car:34") is None
    unknown = [fact for fact in evicted.view.facts if fact.status is FactStatus.UNKNOWN]
    assert unknown and unknown[0].attributes == ()
    assert evicted.view.history_complete is False
    observed.add("deterministic_fact_evict")
    observed.add("unknown_not_false")

    pinned = FactLedger(active_capacity=1)
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
    exhausted = pinned.apply((first, second), now_ms=1_000, projection=projection)
    assert exhausted.view is None
    assert exhausted.exhausted is True
    assert "fact_capacity_exhausted" in exhausted.diagnostics
    observed.add("pinned_exhaustion_no_partial")

    recovered = crowded.apply(
        (_fact("fact:battle:9", observed_at=1_200),),
        now_ms=1_200,
        projection=projection,
    )
    assert recovered.view is not None
    observed.add("recover_degraded")

    registry = EpisodeRegistry(active_capacity=3, resolved_capacity=8)
    first_ep = registry.open(
        _intent(semantic=("a",), correlation=("c:a",), priority=80, order=_order(1))
    )
    second_ep = registry.open(
        _intent(semantic=("b",), correlation=("c:b",), priority=40, order=_order(2), now_ms=1_100)
    )
    third_ep = registry.open(
        _intent(semantic=("c",), correlation=("c:c",), priority=90, order=_order(3), now_ms=1_200)
    )
    registry.activate(first_ep.episode.episode_id, now_ms=1_300, source_refs=("e:1",))
    registry.activate(second_ep.episode.episode_id, now_ms=1_400, source_refs=("e:2",))
    registry.suspend(
        first_ep.episode.episode_id,
        now_ms=1_500,
        reason="target_changed",
        source_refs=("e:s",),
    )
    fourth_ep = registry.open(
        _intent(semantic=("d",), correlation=("c:d",), priority=10, order=_order(4), now_ms=1_600)
    )
    assert registry.get(first_ep.episode.episode_id).state == "invalidated"
    assert registry.get(first_ep.episode.episode_id).resolution_reason == "capacity_evicted"
    fifth_ep = registry.open(
        _intent(semantic=("e",), correlation=("c:e",), priority=70, order=_order(5), now_ms=1_700)
    )
    assert registry.get(third_ep.episode.episode_id).state == "invalidated"
    sixth_ep = registry.open(
        _intent(semantic=("f",), correlation=("c:f",), priority=5, order=_order(6), now_ms=1_800)
    )
    assert registry.get(fourth_ep.episode.episode_id).state == "invalidated"
    assert registry.get(second_ep.episode.episode_id).state == "active"
    assert fifth_ep is not None and sixth_ep is not None
    observed.add("episode_eviction_order")

    pinned_registry = EpisodeRegistry(active_capacity=1, resolved_capacity=4)
    pinned_first = pinned_registry.open(_intent())
    pinned_registry.pin(pinned_first.episode.episode_id, "reserved")
    rejected = pinned_registry.open(
        _intent(semantic=("other",), correlation=("corr:2",), order=_order(2), now_ms=1_500)
    )
    assert rejected.episode is None
    assert rejected.decision == "episode_capacity_rejected"
    observed.add("pinned_reject")

    assert observed == expected


def test_f38_realization_input_frozen_and_freshness_compares_exact_facts(
    fixtures_by_id: dict[str, dict[str, Any]],
) -> None:
    """F38: frozen realization/freshness bundle; equal pass; alias/stale/malformed locks."""

    expected = set(fixtures_by_id["F38"]["expectations"])
    observed: set[str] = set()

    gate = FreshnessGate()
    token = _token()
    current = gate.evaluate(token, _world())
    assert current.verdict == "current"
    assert current.rebuilt_surfaces is False
    assert current.token is token
    observed.add("bundle_frozen")
    observed.add("equal_facts_pass")

    invalidated = gate.evaluate(token, _world(target_identity=("hero", "car.7")))
    assert invalidated.verdict == "invalidated"
    assert "target_changed" in invalidated.evidence
    assert invalidated.token is token
    observed.add("alias_immutable")

    changed = gate.evaluate(token, _world(facts=(_bound_fact(gap_s=1.1, revision=2),)))
    missing = gate.evaluate(
        token, _world(facts=(_bound_fact("fact:gap-2", gap_s=1.1, revision=1),))
    )
    assert changed.verdict == "freshness_stale"
    assert missing.verdict == "freshness_stale"
    observed.add("changed_missing_stale")

    authored = _bundle()
    assert authored.bundle_hash.startswith("sha256:")
    assert authored.fact_binding_hash.startswith("sha256:")
    assert authored.surface_lexicon_hash.startswith("sha256:")
    observed.add("hashes_recorded")

    realizer = AuthoredRealizer()
    stale_hash = realizer.realize(
        authored, now_ms=10_000, expected_bundle_hash="sha256:" + ("0" * 64)
    )
    malformed = realizer.realize(_bundle(lexicon=_lexicon(claim="")), now_ms=10_000)
    assert stale_hash.reason == "realization_input_invalid"
    assert malformed.reason == "realization_input_invalid"
    observed.add("malformed_input_rejected")

    assert observed == expected
