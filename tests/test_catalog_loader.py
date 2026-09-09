"""#257 StoryDefinition catalog loader: frozen bundle, invariants, fail-soft mutations."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from irswitch.contracts import (
    load_coverage_matrix,
    load_narrative_catalog,
)
from irswitch.contracts.catalog_loader import (
    BEAT_INVARIANTS,
    GRAPH_INVARIANTS,
    MANDATORY_CHECKS,
    CatalogLoadResult,
    apply_catalog_mutation,
)
from irswitch.contracts.resources import packaged_schema_bytes
from irswitch.events import __all__ as events_exports

ROOT = Path(__file__).resolve().parents[1]
MACHINE = ROOT / "docs" / "v2.0.0" / "machine"
SOURCE = ROOT / "src" / "irswitch" / "contracts" / "catalog_loader.py"
GOLDENS = json.loads((MACHINE / "catalog-loader-goldens.json").read_text(encoding="utf-8"))
PACKAGED = (
    "beat-catalog.json",
    "beat-catalog.schema.json",
    "successor-graph.json",
    "successor-graph.schema.json",
    "catalog-loader-contract.json",
)


def _bundle() -> dict[str, dict]:
    return {
        "registry": json.loads(packaged_schema_bytes("freeze-registry.json")),
        "beats": json.loads(packaged_schema_bytes("beat-catalog.json")),
        "graph": json.loads(packaged_schema_bytes("successor-graph.json")),
        "detectors": json.loads(packaged_schema_bytes("detector-catalog.json")),
        "config": json.loads(packaged_schema_bytes("config-contract.json")),
    }


@pytest.mark.parametrize("name", PACKAGED)
def test_packaged_loader_artifacts_match_frozen_machine_sources(name: str) -> None:
    assert json.loads(packaged_schema_bytes(name)) == json.loads(
        (MACHINE / name).read_text(encoding="utf-8")
    )


def test_frozen_bundle_loads_every_256_row_exactly_once() -> None:
    result = load_narrative_catalog()
    matrix = load_coverage_matrix()

    assert result.outcome == "loaded"
    assert result.catalog is not None
    assert result.failure is None
    catalog = result.catalog
    assert catalog.schema_version == "narrative-catalog/2"
    assert catalog.catalog_hash.startswith("sha256:")
    assert len(catalog.beats) == 64
    assert len({beat.id for beat in catalog.beats}) == 64
    assert {beat.id for beat in catalog.beats} == {beat.id for beat in matrix.beats}
    assert len(catalog.stories) == 11
    assert len(catalog.edges) == 50
    assert len(catalog.families) == 37
    assert len(catalog.policies) == 6
    assert catalog.same_beat_authored_fallback is False
    assert catalog.sequence_graph_fallback is False
    assert result.counts == GOLDENS["valid"]["expectedCounts"]


def test_named_invariants_and_mandatory_checks_all_execute() -> None:
    result = load_narrative_catalog()

    assert result.executed_invariants == BEAT_INVARIANTS + GRAPH_INVARIANTS
    assert result.executed_checks == MANDATORY_CHECKS


def test_event_routes_are_deterministic_and_aliases_cannot_open_stories() -> None:
    catalog = load_narrative_catalog().require_catalog()

    lap = catalog.route_event("LAP_COMPLETE")
    assert lap.beat_ids == ("timing.lap.completed",)
    assert lap.story_routes == ("timing_attempt", "single_result")
    assert lap.tape_channel == "race.timing.lap"
    assert catalog.route_event("BATTLE_LOST") is None
    assert catalog.route_event("BLE_LOST") is None
    assert catalog.route_event("STREAM_START") is None


def test_stories_expose_open_update_close_and_hard_context_axes() -> None:
    catalog = load_narrative_catalog().require_catalog()
    timing = catalog.story("timing_attempt")
    battle = catalog.story("battle_ahead")

    assert "timing.lap.hot" in timing.open_beat_ids
    assert "timing.lap.projected" in timing.update_beat_ids
    assert "timing.lap.completed" in timing.close_beat_ids
    assert timing.cadence_minimum_ms == 8000
    assert timing.max_consecutive_non_closing_beats == 2
    assert "battle.pursuit" in battle.open_beat_ids
    completed = catalog.beat("timing.lap.completed")
    assert completed.stage_any_of == ("practice", "qualifying", "race")
    assert completed.policy.ttl_ms == 30000
    assert completed.policy.base_priority == 78
    assert completed.realization.backend == "authored"
    hunt = catalog.beat("battle.pursuit")
    assert hunt.realization.backend == "qwen_compiled"
    assert hunt.realization.same_beat_authored_fallback is False


def test_detector_story_and_edge_fields_stay_separate() -> None:
    catalog = load_narrative_catalog().require_catalog()

    assert catalog.detector_ids == (
        "battle_ahead_v1",
        "battle_behind_v1",
        "battle_two_front_v1",
    )
    assert all(not hasattr(story, "parameters") for story in catalog.stories)
    assert all(edge.guard_profile_id for edge in catalog.edges)
    assert catalog.beat("battle.pursuit").detector_id is None


@pytest.mark.parametrize("fixture", GOLDENS["invalid"], ids=lambda row: row["id"])
def test_invalid_loader_goldens_disable_commentary_without_raising(fixture: dict) -> None:
    bundle = apply_catalog_mutation(fixture["id"], **_bundle())
    result = load_narrative_catalog(
        registry=bundle["registry"],
        beats=bundle["beats"],
        graph=bundle["graph"],
        detectors=bundle["detectors"],
        config=bundle["config"],
    )

    assert result.outcome == "commentary_disabled"
    assert result.catalog is None
    assert result.failure is not None
    assert result.failure.commentary_enabled is False
    assert result.failure.main_loop_raises is False
    assert result.failure.partial_catalog_published is False
    assert result.failure.runtime_status == "disabled"
    assert result.failure.reason == "catalog_invalid"
    assert fixture["errorContains"] in result.failure.error


def test_style_variant_and_sequence_graph_fallback_fail_closed() -> None:
    beats = json.loads(packaged_schema_bytes("beat-catalog.json"))
    extra = copy.deepcopy(beats["beats"][0])
    extra["id"] = "timing.lap.completed.excited"
    beats["beats"].append(extra)
    styled = load_narrative_catalog(beats=beats)
    assert styled.outcome == "commentary_disabled"
    assert styled.failure is not None
    assert "beat schema rejected" in styled.failure.error

    fallback = json.loads(packaged_schema_bytes("beat-catalog.json"))
    fallback["sequenceGraphFallback"] = "commentary/data/sequence_graph.json"
    banned = load_narrative_catalog(beats=fallback)
    assert banned.outcome == "commentary_disabled"
    assert banned.failure is not None
    assert "sequence_graph" in banned.failure.error


def test_qwen_failure_has_no_same_beat_authored_fallback_field() -> None:
    beats = json.loads(packaged_schema_bytes("beat-catalog.json"))
    hunt = next(row for row in beats["beats"] if row["id"] == "battle.pursuit")
    hunt["realization"]["fallback"] = "authored"
    result = load_narrative_catalog(beats=beats)
    assert result.outcome == "commentary_disabled"
    assert result.failure is not None
    assert "authored fallback" in result.failure.error


def test_loader_is_not_exported_from_events_and_never_uses_eval() -> None:
    source = SOURCE.read_text(encoding="utf-8")

    assert "catalog_loader" not in events_exports
    assert "NarrativeRuntime" not in source
    assert "eval(" not in source
    assert "exec(" not in source
    assert "compile(" not in source
    for banned in ("irswitch.commentary", "irswitch.overlay", "irswitch.events"):
        assert banned not in source


def test_require_catalog_rejects_a_disabled_result() -> None:
    beats = json.loads(packaged_schema_bytes("beat-catalog.json"))
    beats["beats"][0]["policyId"] = "magic"
    result = load_narrative_catalog(beats=beats)
    assert isinstance(result, CatalogLoadResult)
    with pytest.raises(RuntimeError, match="catalog_invalid"):
        result.require_catalog()
