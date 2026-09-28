import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from irswitch.server.studio_data import register_studio_data_routes


@pytest.mark.asyncio
async def test_authoritative_catalog_and_absent_episodes(monkeypatch):
    # This case explicitly models provider absence, independently of other app tests.
    monkeypatch.setattr("irswitch.server.studio_data.get_narrative_runtime", lambda: None)
    app = web.Application()
    register_studio_data_routes(app)
    async with TestClient(TestServer(app)) as client:
        response = await client.get("/api/studio/catalog")
        assert response.status == 200
        data = await response.json()
        assert data["schemaVersion"] == "studio-catalog/1"
        assert len(data["narrative"]["beats"]) == 64
        assert data["narrative"]["catalog_hash"].startswith("sha256:")
        assert data["overlay"]["entries"]
        assert data["capabilities"]["liveNodeActivity"] is False
        episodes = await (await client.get("/api/studio/episodes")).json()
        assert episodes["available"] is False
        assert episodes["runId"] is None
        assert (await client.get("/api/studio/episodes?limit=oops")).status == 400


def test_episode_history_is_recorded_bounded_and_instance_scoped():
    from test_episode_registry import _intent as intent

    from irswitch.events.episode_registry import EpisodeRegistry

    registry = EpisodeRegistry()
    opened = registry.open(intent())
    assert opened.episode is not None
    episode_id = opened.episode.episode_id
    registry.activate(episode_id, now_ms=1001, source_refs=("event:test",))
    snapshot = registry.studio_snapshot(limit=50, offset=0)
    assert snapshot["available"] is True
    assert [row["reason"] for row in snapshot["history"]] == ["opened", "activated"]
    assert snapshot["items"][0]["episode_id"] == episode_id
    assert snapshot["runId"] != EpisodeRegistry().studio_snapshot()["runId"]
    for now in range(1100, 1700):
        registry.activate(episode_id, now_ms=now, source_refs=("event:test",))
    snapshot = registry.studio_snapshot()
    assert len(snapshot["history"]) == 512
    assert snapshot["historyComplete"] is False
    assert snapshot["history"][0]["sequence"] > 1
    assert registry.studio_snapshot(offset=1)["items"] == []


def test_generic_and_lifecycle_routes_use_confirmed_occurrence_stage():
    from test_narrative_context_batch import _event

    from irswitch.contracts.catalog_loader import load_narrative_catalog
    from irswitch.contracts.narrative import NarrativeEvent
    from irswitch.events.studio_story_projection import routed_beats

    base = load_narrative_catalog().require_catalog()
    raw = _event(0).to_dict()
    raw["kind"] = "session.enter_car"
    raw["sourceEnvelope"]["eventType"] = "ENTER_CAR"
    assert [b.id for b in routed_beats(base, NarrativeEvent.from_dict(raw))] == [
        "session.enter_car.race"
    ]
    raw["kind"] = "SESSION_STARTED"
    raw["sourceEnvelope"] = None
    raw["sourceOrder"] = None
    raw["deliveryClass"] = "protected"
    raw["funnel"]["sourceClass"] = "lifecycle"
    assert [b.id for b in routed_beats(base, NarrativeEvent.from_dict(raw))] == [
        "session.intro.race"
    ]
    raw["kind"] = "STREAM_STARTED"
    assert [b.id for b in routed_beats(base, NarrativeEvent.from_dict(raw))] == ["stream.started"]
