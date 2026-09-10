"""#284 HTTP mount for project_runtime_status (commentary-runtime/2 subset)."""

from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from test_narrative_runtime import _event_impulse

from irswitch.events import __all__ as events_exports
from irswitch.events.narrative_ingress import project_runtime_status
from irswitch.events.narrative_runtime import NarrativeRuntime
from irswitch.events.narrative_runtime_http import (
    APP_NARRATIVE_RUNTIME,
    register_narrative_runtime_routes,
)

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "irswitch"
    / "events"
    / "narrative_runtime_http.py"
)


def _app_with_runtime(runtime: NarrativeRuntime | None = None) -> web.Application:
    app = web.Application()
    register_narrative_runtime_routes(app)
    if runtime is not None:
        app[APP_NARRATIVE_RUNTIME] = runtime
    return app


def test_runtime_http_source_documents_mount_boundary() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    assert "/api/commentary/runtime" in text
    assert "project_runtime_status" in text
    assert "does not start" in text.lower() or "does not run" in text.lower()
    assert "NarrativeRuntime" in text
    assert "register_narrative_runtime_routes" not in events_exports
    assert "handle_commentary_runtime_status" not in events_exports
    assert "APP_NARRATIVE_RUNTIME" not in events_exports


@pytest.mark.asyncio
async def test_runtime_status_without_provider_returns_disabled_subset() -> None:
    app = _app_with_runtime(None)
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.get("/api/commentary/runtime")
            assert resp.status == 200
            data = await resp.json()
            assert data["schemaVersion"] == "commentary-runtime/2"
            assert data["status"] == "disabled"
            assert data["speech"]["state"] == "idle"
            assert data["queues"]["mailbox"]["capacity"] == 64
            assert data["timeline"] == {
                "broadcastEpoch": 0,
                "streamEpoch": 0,
                "narrativeRunActive": False,
                "streamActive": None,
                "streamState": "unknown",
                "historyComplete": True,
            }


@pytest.mark.asyncio
async def test_runtime_status_with_enabled_runtime_projects_ready() -> None:
    runtime = NarrativeRuntime()
    runtime.enable()
    expected = project_runtime_status(runtime.status())
    app = _app_with_runtime(runtime)
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.get("/api/commentary/runtime")
            assert resp.status == 200
            data = await resp.json()
            assert data == expected
            assert data["status"] == "ready"
            assert data["speech"]["state"] == "idle"


@pytest.mark.asyncio
async def test_runtime_route_registered_with_legacy_commentary_status() -> None:
    """Mount is additive; legacy /api/commentary/status stays owned by commentary.http."""
    from irswitch.commentary.http import register_commentary_routes

    app = web.Application()
    register_commentary_routes(app)
    resources = {route.resource.canonical for route in app.router.routes()}
    assert "/api/commentary/status" in resources
    assert "/api/commentary/runtime" in resources


@pytest.mark.asyncio
async def test_handler_rejects_non_runtime_provider() -> None:
    app = web.Application()
    register_narrative_runtime_routes(app)
    app[APP_NARRATIVE_RUNTIME] = object()  # type: ignore[assignment]
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.get("/api/commentary/runtime")
            assert resp.status == 500
            data = await resp.json()
            assert "error" in data


@pytest.mark.asyncio
async def test_runtime_decisions_without_provider_returns_empty_runtime_false() -> None:
    app = _app_with_runtime(None)
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.get("/api/commentary/runtime/decisions")
            assert resp.status == 200
            data = await resp.json()
            assert data == {
                "schemaVersion": "commentary-runtime/2",
                "runtime": False,
                "decisions": [],
            }


@pytest.mark.asyncio
async def test_runtime_decisions_with_director_ring_and_limit() -> None:
    from test_story_director import _cand as _director_cand
    from test_story_director import _world as _director_world

    from irswitch.events.story_director import StoryDirector

    runtime = NarrativeRuntime(story_director=StoryDirector())
    runtime.enable()
    runtime.seed_director_for_test(world=_director_world(), candidates=(_director_cand(),))
    runtime.admit(_event_impulse("http:dec:select", revision=81, fanout=81))
    planned = runtime.reduce_next()
    assert planned is not None
    assert "director_selected" in planned.effects

    runtime.seed_director_for_test(
        world=_director_world(lane="building", impulse="timer"),
        candidates=(_director_cand(),),
    )
    runtime.admit(_event_impulse("http:dec:silence", revision=82, fanout=82))
    silenced = runtime.reduce_next()
    assert silenced is not None
    assert "director_silenced" in silenced.effects

    app = _app_with_runtime(runtime)
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.get("/api/commentary/runtime/decisions?limit=1")
            assert resp.status == 200
            data = await resp.json()
            assert data["schemaVersion"] == "commentary-runtime/2"
            assert data["runtime"] is True
            assert len(data["decisions"]) == 1
            assert data["decisions"][0]["decision"] == "silence"

            resp_all = await client.get("/api/commentary/runtime/decisions")
            payload = await resp_all.json()
            assert [item["decision"] for item in payload["decisions"]] == [
                "silence",
                "selected",
            ]


@pytest.mark.asyncio
async def test_runtime_decisions_route_additive_with_legacy_decisions() -> None:
    from irswitch.commentary.http import register_commentary_routes

    app = web.Application()
    register_commentary_routes(app)
    resources = {route.resource.canonical for route in app.router.routes()}
    assert "/api/commentary/decisions" in resources
    assert "/api/commentary/runtime/decisions" in resources
