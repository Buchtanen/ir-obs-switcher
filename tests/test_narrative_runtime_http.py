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
            assert data["loop"]["active"] is False
            assert data["loop"]["reduceCount"] == 0
            assert data["loop"]["lastReduceMonoMs"] is None
            assert data["loop"]["supervisors"] == {}
            assert data["timeline"] == {
                "broadcastEpoch": 0,
                "streamEpoch": 0,
                "narrativeRunActive": False,
                "streamActive": None,
                "streamState": "unknown",
                "sessionPlan": None,
                "sessionRef": None,
                "occurrenceId": None,
                "lineageId": None,
                "stage": None,
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


@pytest.mark.asyncio
async def test_runtime_validate_supported_golden() -> None:
    import json
    from pathlib import Path

    fixtures = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "commentary_runtime"
    request = json.loads((fixtures / "validate_request.json").read_text(encoding="utf-8"))
    expected = json.loads((fixtures / "validate_supported.json").read_text(encoding="utf-8"))
    app = _app_with_runtime(None)
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post("/api/commentary/runtime/validate", json=request)
            assert resp.status == 200
            assert await resp.json() == expected


@pytest.mark.asyncio
async def test_runtime_validate_malformed_returns_400() -> None:
    app = _app_with_runtime(None)
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post(
                "/api/commentary/runtime/validate",
                json={"schemaVersion": "commentary-runtime/2"},
            )
            assert resp.status == 400
            data = await resp.json()
            assert data["schemaVersion"] == "commentary-runtime/2"
            assert data["error"]["code"] == "invalid_request"


@pytest.mark.asyncio
async def test_runtime_speak_accepted_and_busy() -> None:
    import json
    from pathlib import Path

    fixtures = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "commentary_runtime"
    request = json.loads((fixtures / "speak_request.json").read_text(encoding="utf-8"))
    runtime = NarrativeRuntime()
    runtime.enable()
    app = _app_with_runtime(runtime)
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post("/api/commentary/runtime/speak", json=request)
            assert resp.status == 202
            data = await resp.json()
            assert data["schemaVersion"] == "commentary-runtime/2"
            assert data["accepted"] is True
            assert data["admittedState"] == "committed"
            assert data["requestId"].startswith("manual:")

            busy = await client.post("/api/commentary/runtime/speak", json=request)
            assert busy.status == 409
            payload = await busy.json()
            assert payload["error"]["code"] == "speech_busy"


@pytest.mark.asyncio


@pytest.mark.asyncio
async def test_runtime_speak_rejects_unknown_body_fields() -> None:
    """#273 manual speak body is schemaVersion/text/language only (no force/overrides)."""
    import json
    from pathlib import Path

    fixtures = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "commentary_runtime"
    request = json.loads((fixtures / "speak_request.json").read_text(encoding="utf-8"))
    request = dict(request)
    request["force"] = True
    runtime = NarrativeRuntime()
    runtime.enable()
    app = _app_with_runtime(runtime)
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post("/api/commentary/runtime/speak", json=request)
            assert resp.status == 400
            data = await resp.json()
            assert data["schemaVersion"] == "commentary-runtime/2"
            assert data["error"]["code"] == "invalid_request"
            # Lane must stay idle — unknown fields never dispatch audio.
            assert runtime.status().lane == "idle"


@pytest.mark.asyncio
async def test_runtime_speak_accepted_admitted_state_is_committed() -> None:
    """#273 202 admittedState is exactly committed after atomic dispatch."""
    import json
    from pathlib import Path

    fixtures = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "commentary_runtime"
    request = json.loads((fixtures / "speak_request.json").read_text(encoding="utf-8"))
    assert set(request) == {"schemaVersion", "text", "language"}
    runtime = NarrativeRuntime()
    runtime.enable()
    app = _app_with_runtime(runtime)
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post("/api/commentary/runtime/speak", json=request)
            assert resp.status == 202
            data = await resp.json()
            assert set(data) == {"schemaVersion", "accepted", "requestId", "admittedState"}
            assert data["admittedState"] == "committed"
            assert runtime.status().lane == "committed"


async def test_runtime_speak_without_provider_returns_503() -> None:
    import json
    from pathlib import Path

    fixtures = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "commentary_runtime"
    request = json.loads((fixtures / "speak_request.json").read_text(encoding="utf-8"))
    app = _app_with_runtime(None)
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post("/api/commentary/runtime/speak", json=request)
            assert resp.status == 503
            data = await resp.json()
            assert data["error"]["code"] == "component_unavailable"


@pytest.mark.asyncio
async def test_public_validate_speak_cutover_aliases_runtime_handlers() -> None:
    """Public /api/commentary/validate|speak share NarrativeRuntime handlers."""
    from irswitch.commentary.http import register_commentary_routes
    from irswitch.events.narrative_runtime_http import (
        handle_commentary_runtime_speak,
        handle_commentary_runtime_validate,
    )

    app = web.Application()
    register_commentary_routes(app)
    resources = {route.resource.canonical for route in app.router.routes()}
    assert "/api/commentary/validate" in resources
    assert "/api/commentary/speak" in resources
    assert "/api/commentary/runtime/validate" in resources
    assert "/api/commentary/runtime/speak" in resources

    by_path = {
        route.resource.canonical: route.handler
        for route in app.router.routes()
        if hasattr(route, "handler") and hasattr(route, "resource")
    }
    assert by_path["/api/commentary/validate"] is handle_commentary_runtime_validate
    assert by_path["/api/commentary/runtime/validate"] is handle_commentary_runtime_validate
    assert by_path["/api/commentary/speak"] is handle_commentary_runtime_speak
    assert by_path["/api/commentary/runtime/speak"] is handle_commentary_runtime_speak


@pytest.mark.asyncio
async def test_public_validate_matches_runtime_golden() -> None:
    import json

    fixtures = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "commentary_runtime"
    request = json.loads((fixtures / "validate_request.json").read_text(encoding="utf-8"))
    expected = json.loads((fixtures / "validate_supported.json").read_text(encoding="utf-8"))
    from irswitch.commentary.http import register_commentary_routes

    app = web.Application()
    register_commentary_routes(app)
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post("/api/commentary/validate", json=request)
            assert resp.status == 200
            assert await resp.json() == expected


@pytest.mark.asyncio
async def test_public_speak_matches_runtime_admit_path() -> None:
    import json

    fixtures = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "commentary_runtime"
    request = json.loads((fixtures / "speak_request.json").read_text(encoding="utf-8"))
    runtime = NarrativeRuntime()
    runtime.enable()
    from irswitch.commentary.http import register_commentary_routes
    from irswitch.events.narrative_runtime_http import APP_NARRATIVE_RUNTIME

    app = web.Application()
    register_commentary_routes(app)
    app[APP_NARRATIVE_RUNTIME] = runtime
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post("/api/commentary/speak", json=request)
            assert resp.status == 202
            data = await resp.json()
            assert data["schemaVersion"] == "commentary-runtime/2"
            assert data["accepted"] is True
            assert data["admittedState"] == "committed"
            assert data["requestId"].startswith("manual:")

            busy = await client.post("/api/commentary/speak", json=request)
            assert busy.status == 409
            payload = await busy.json()
            assert payload["error"]["code"] == "speech_busy"


@pytest.mark.asyncio
async def test_runtime_speak_admission_timeout_maps_503() -> None:
    """HTTP maps ManualSpeakOutcome.admission_timeout → error admission_timeout/503."""

    class _TimeoutProvider:
        def status(self):  # pragma: no cover - unused
            raise AssertionError("status unused")

        async def try_manual_speak(self, text: str, **kwargs):
            from irswitch.events.narrative_runtime import ManualSpeakOutcome

            return ManualSpeakOutcome(kind="admission_timeout")

    app = _app_with_runtime(_TimeoutProvider())  # type: ignore[arg-type]
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post(
                "/api/commentary/runtime/speak",
                json={
                    "schemaVersion": "commentary-runtime/2",
                    "language": "en",
                    "text": "Commentary audio test.",
                },
            )
            assert resp.status == 503
            data = await resp.json()
            assert data["schemaVersion"] == "commentary-runtime/2"
            assert data["error"]["code"] == "admission_timeout"
