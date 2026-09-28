import copy
import json
from unittest.mock import patch

import pytest

from irswitch.contracts.studio_definitions import (
    DefinitionError,
    DefinitionStore,
    RevisionConflict,
    compile_document,
    default_document,
)


def new_story_document():
    doc = default_document()
    story = copy.deepcopy(doc["stories"][0])
    story["id"] = "studio.custom_story"
    doc["stories"].append(story)
    return doc


def test_new_story_is_typed_and_event_routing_is_updated():
    doc = new_story_document()
    compiled = compile_document(doc)
    story = compiled.story("studio.custom_story")
    member = (story.open_beat_ids + story.update_beat_ids + story.close_beat_ids)[0]
    assert "studio.custom_story" in compiled.beat(member).story_routes
    assert any(
        "studio.custom_story" in route.story_routes
        for route in compiled.event_routes
        if member in route.beat_ids
    )


@pytest.mark.parametrize(
    "mutation", ["hash", "unknown_beat", "duplicate", "cycle", "parameter", "extra_code"]
)
def test_invalid_documents_fail_closed(mutation):
    doc = new_story_document()
    if mutation == "hash":
        doc["baseCatalogHash"] = "sha256:" + "0" * 64
    if mutation == "unknown_beat":
        doc["stories"][-1]["open_beat_ids"] = ["missing"]
    if mutation == "duplicate":
        doc["stories"][-1]["id"] = doc["stories"][0]["id"].upper()
    if mutation == "cycle":
        doc["edges"][0]["to_beat_id"] = doc["edges"][0]["from_beat_id"]
    if mutation == "parameter":
        doc["stories"][-1]["cadence_minimum_ms"] = -1
    if mutation == "extra_code":
        doc["python"] = "print(1)"
    with pytest.raises(DefinitionError):
        compile_document(doc)


def test_drafts_conflict_atomic_failure_activation_and_restart(tmp_path):
    store = DefinitionStore(tmp_path / "studio-definitions.json")
    assert store.snapshot()["effectiveRevision"] == "builtin"
    saved = store.save(new_story_document(), base_revision=0)
    revision = saved["revisions"][-1]["id"]
    assert saved["effectiveRevision"] == saved["pendingRevision"] == "builtin"
    with pytest.raises(RevisionConflict):
        store.save(default_document(), base_revision=0)
    before = store.path.read_bytes()
    with patch("irswitch.contracts.studio_definitions.os.replace", side_effect=OSError("disk")):
        with pytest.raises(OSError):
            store.select(revision, base_revision=1)
    assert store.path.read_bytes() == before
    selected = store.select(revision, base_revision=1)
    assert selected["effectiveRevision"] == "builtin"
    assert selected["pendingRevision"] == revision
    runtime, status = store.startup()
    assert status["effectiveRevision"] == revision
    assert runtime.story("studio.custom_story")
    store.select("builtin", base_revision=3)
    assert store.snapshot()["effectiveRevision"] == revision
    _, status = store.startup()
    assert status["effectiveRevision"] == "builtin"


def test_corrupt_pending_falls_back_without_overwriting(tmp_path):
    store = DefinitionStore(tmp_path / "definitions.json")
    state = store.save(new_story_document(), base_revision=0)
    store.select(state["revisions"][-1]["id"], base_revision=1)
    raw = json.loads(store.path.read_text())
    raw["revisions"][0]["document"]["baseCatalogHash"] = "bad"
    store.path.write_text(json.dumps(raw))
    before = store.path.read_bytes()
    _, status = store.startup()
    assert status["effectiveRevision"] == "builtin"
    assert status["startupError"]
    assert store.path.read_bytes() == before


def test_malformed_store_and_deep_json_never_break_startup(tmp_path):
    store = DefinitionStore(tmp_path / "definitions.json")
    for raw in (
        "[" * 2000 + "0" + "]" * 2000,
        "{}",
        '{"schemaVersion":"studio-revisions/1","baseRevision":0,"revisions":[null]}',
    ):
        store.path.write_text(raw)
        _, status = store.startup()
        assert status["effectiveRevision"] == "builtin"
        assert status["startupError"]
        assert store.path.read_text() == raw


def test_concurrent_generation_and_bounded_protected_history(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    store = DefinitionStore(tmp_path / "definitions.json")

    def save_once():
        try:
            return store.save(new_story_document(), base_revision=0)
        except RevisionConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: save_once(), range(2)))
    assert results.count("conflict") == 1
    first = store.snapshot()["revisions"][0]["id"]
    store.select(first, base_revision=1)
    store.startup()
    for index in range(34):
        doc = new_story_document()
        doc["stories"][-1]["cadence_minimum_ms"] = index + 1
        state = store.save(doc, base_revision=store.snapshot()["baseRevision"])
    assert len(state["revisions"]) == 32
    assert any(row["id"] == first for row in state["revisions"])
    assert state["effectiveRevision"] == state["pendingRevision"] == first


def test_failed_startup_promotion_preserves_previous_effective(tmp_path):
    store = DefinitionStore(tmp_path / "definitions.json")
    saved = store.save(new_story_document(), base_revision=0)
    store.select(saved["savedRevision"], base_revision=1)
    before = store.path.read_bytes()
    with patch("irswitch.contracts.studio_definitions.os.replace", side_effect=OSError("disk")):
        runtime, status = store.startup()
    assert status["effectiveRevision"] == "builtin"
    assert status["startupError"]
    assert not any(story.id == "studio.custom_story" for story in runtime.stories)
    assert store.path.read_bytes() == before


def test_nonterminating_story_and_custom_stream_template_are_rejected():
    doc = new_story_document()
    doc["edges"] = []
    for story in doc["stories"]:
        story["successor_edge_ids"] = []
    with pytest.raises(DefinitionError, match="closing"):
        compile_document(doc)
    doc = default_document()
    story = copy.deepcopy(next(s for s in doc["stories"] if s["id"] == "stream_lifecycle"))
    story["id"] = "studio.stream"
    doc["stories"].append(story)
    with pytest.raises(DefinitionError, match="opening and closing"):
        compile_document(doc)


def test_activated_story_reaches_runtime_world_instances_and_consumer_catalog(
    tmp_path, monkeypatch
):
    from test_narrative_runtime import _event_impulse

    from irswitch.contracts import runtime_catalog
    from irswitch.events.episode_registry import EpisodeRegistry
    from irswitch.events.narrative_runtime import NarrativeRuntime
    from irswitch.events.opportunity_queue import OpportunityQueue

    monkeypatch.setattr(runtime_catalog, "_effective", None)
    monkeypatch.setattr(
        runtime_catalog, "_status", {"effectiveRevision": "builtin", "startupError": None}
    )
    doc = default_document()
    custom = copy.deepcopy(next(s for s in doc["stories"] if s["id"] == "battle_ahead"))
    custom["id"] = "studio.battle"
    custom["cadence_minimum_ms"] = 1234
    doc["stories"].append(custom)
    store = DefinitionStore(tmp_path / "definitions.json")
    saved = store.save(doc, base_revision=0)
    revision = saved["revisions"][-1]["id"]
    store.select(revision, base_revision=1)
    assert "studio.battle" not in {
        s.id for s in runtime_catalog.load_runtime_catalog().require_catalog().stories
    }
    runtime_catalog.initialize_runtime_catalog(store.path)
    queue = OpportunityQueue()
    assert queue._loaded().story("studio.battle").cadence_minimum_ms == 1234
    registry = EpisodeRegistry()
    runtime = NarrativeRuntime(episode_registry=registry)
    runtime.enable()
    runtime.admit(_event_impulse("studio:custom"))
    tuple(runtime.drain())
    snapshot = runtime.studio_episodes()
    assert snapshot["definitionRevision"] == revision
    assert any(row["definition_id"] == "studio.battle" for row in snapshot["items"])
    assert any(
        row["source_refs"] == ["event:hunting:0"] or row["source_refs"] == ("event:hunting:0",)
        for row in snapshot["history"]
    )
