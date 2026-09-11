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

WRITE_CSRF_HEADERS = {"X-Requested-With": "irswitch"}

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
            resp = await client.post(
                "/api/commentary/runtime/validate", json=request, headers=WRITE_CSRF_HEADERS
            )
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
                headers=WRITE_CSRF_HEADERS,
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
            resp = await client.post(
                "/api/commentary/runtime/speak", json=request, headers=WRITE_CSRF_HEADERS
            )
            assert resp.status == 202
            data = await resp.json()
            assert data["schemaVersion"] == "commentary-runtime/2"
            assert data["accepted"] is True
            assert data["admittedState"] == "committed"
            assert data["requestId"].startswith("manual:")

            busy = await client.post(
                "/api/commentary/runtime/speak", json=request, headers=WRITE_CSRF_HEADERS
            )
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
            resp = await client.post(
                "/api/commentary/runtime/speak", json=request, headers=WRITE_CSRF_HEADERS
            )
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
            resp = await client.post(
                "/api/commentary/runtime/speak", json=request, headers=WRITE_CSRF_HEADERS
            )
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
            resp = await client.post(
                "/api/commentary/runtime/speak", json=request, headers=WRITE_CSRF_HEADERS
            )
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
            resp = await client.post(
                "/api/commentary/validate", json=request, headers=WRITE_CSRF_HEADERS
            )
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
            resp = await client.post(
                "/api/commentary/speak", json=request, headers=WRITE_CSRF_HEADERS
            )
            assert resp.status == 202
            data = await resp.json()
            assert data["schemaVersion"] == "commentary-runtime/2"
            assert data["accepted"] is True
            assert data["admittedState"] == "committed"
            assert data["requestId"].startswith("manual:")

            busy = await client.post(
                "/api/commentary/speak", json=request, headers=WRITE_CSRF_HEADERS
            )
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
                headers=WRITE_CSRF_HEADERS,
            )
            assert resp.status == 503
            data = await resp.json()
            assert data["schemaVersion"] == "commentary-runtime/2"
            assert data["error"]["code"] == "admission_timeout"


# ---------------------------------------------------------------------------
# #273 Verification: bounds / invalid input / unavailable / mixed-boundary /
# component-preflight exercised through the public HTTP mount.
# ---------------------------------------------------------------------------


def _fixtures() -> Path:
    return Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "commentary_runtime"


@pytest.mark.asyncio
async def test_runtime_write_oversized_content_length_matches_invalid_request() -> None:
    """#273: Content-Length >64KiB freezes to error_invalid_request before parse."""
    import json

    expected = json.loads((_fixtures() / "error_invalid_request.json").read_text(encoding="utf-8"))
    app = _app_with_runtime(None)
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post(
                "/api/commentary/runtime/speak",
                data=b"{}",
                headers={
                    **WRITE_CSRF_HEADERS,
                    "Content-Type": "application/json",
                    "Content-Length": "65537",
                },
            )
            assert resp.status == 400
            assert await resp.json() == expected


@pytest.mark.asyncio
async def test_runtime_write_non_json_content_type_matches_invalid_request() -> None:
    """#273: non-JSON Content-Type freezes to error_invalid_request before parse."""
    import json

    expected = json.loads((_fixtures() / "error_invalid_request.json").read_text(encoding="utf-8"))
    body = b'{"schemaVersion":"commentary-runtime/2","language":"en","text":"hi"}'
    app = _app_with_runtime(None)
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post(
                "/api/commentary/runtime/speak",
                data=body,
                headers={
                    **WRITE_CSRF_HEADERS,
                    "Content-Type": "text/plain",
                    "Content-Length": str(len(body)),
                },
            )
            assert resp.status == 400
            assert await resp.json() == expected


@pytest.mark.asyncio
async def test_runtime_speak_text_over_400_matches_validation_failed() -> None:
    """#273: speak text length 401 freezes to error_validation_failed."""
    import json

    expected = json.loads((_fixtures() / "error_validation_failed.json").read_text(encoding="utf-8"))
    app = _app_with_runtime(None)
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post(
                "/api/commentary/runtime/speak",
                json={
                    "schemaVersion": "commentary-runtime/2",
                    "language": "en",
                    "text": "x" * 401,
                },
                headers=WRITE_CSRF_HEADERS,
            )
            assert resp.status == 422
            assert await resp.json() == expected


@pytest.mark.asyncio
async def test_runtime_speak_bad_schema_version_matches_invalid_request() -> None:
    """#273: wrong schemaVersion freezes to error_invalid_request."""
    import json

    expected = json.loads((_fixtures() / "error_invalid_request.json").read_text(encoding="utf-8"))
    app = _app_with_runtime(None)
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post(
                "/api/commentary/runtime/speak",
                json={"schemaVersion": "v1", "language": "en", "text": "Commentary audio test."},
                headers=WRITE_CSRF_HEADERS,
            )
            assert resp.status == 400
            assert await resp.json() == expected


@pytest.mark.asyncio
async def test_runtime_speak_non_en_language_matches_invalid_request() -> None:
    """#273: non-en language freezes to error_invalid_request; lane stays idle."""
    import json

    expected = json.loads((_fixtures() / "error_invalid_request.json").read_text(encoding="utf-8"))
    runtime = NarrativeRuntime()
    runtime.enable()
    app = _app_with_runtime(runtime)
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post(
                "/api/commentary/runtime/speak",
                json={
                    "schemaVersion": "commentary-runtime/2",
                    "language": "cs",
                    "text": "Commentary audio test.",
                },
                headers=WRITE_CSRF_HEADERS,
            )
            assert resp.status == 400
            assert await resp.json() == expected
            assert runtime.status().lane == "idle"


@pytest.mark.asyncio
async def test_runtime_speak_non_string_text_matches_validation_failed() -> None:
    """#273: non-string speak text freezes to error_validation_failed."""
    import json

    expected = json.loads((_fixtures() / "error_validation_failed.json").read_text(encoding="utf-8"))
    app = _app_with_runtime(None)
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post(
                "/api/commentary/runtime/speak",
                json={
                    "schemaVersion": "commentary-runtime/2",
                    "language": "en",
                    "text": 123,
                },
                headers=WRITE_CSRF_HEADERS,
            )
            assert resp.status == 422
            assert await resp.json() == expected


@pytest.mark.asyncio
async def test_runtime_validate_unknown_field_matches_invalid_request() -> None:
    """#273: unknown validate top-level field → invalid_request/400 (detail may name fields)."""
    import json

    request = json.loads((_fixtures() / "validate_request.json").read_text(encoding="utf-8"))
    request = dict(request)
    request["force"] = True
    app = _app_with_runtime(None)
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post(
                "/api/commentary/runtime/validate",
                json=request,
                headers=WRITE_CSRF_HEADERS,
            )
            assert resp.status == 400
            data = await resp.json()
            assert data["schemaVersion"] == "commentary-runtime/2"
            assert data["error"]["code"] == "invalid_request"
            assert "force" in data["error"]["message"]


@pytest.mark.asyncio
async def test_runtime_decisions_limit_clamps_http() -> None:
    """#273: decisions ?limit clamps through HTTP (0→1, 101→≤100, garbage→default)."""
    from test_story_director import _cand as _director_cand
    from test_story_director import _world as _director_world

    from irswitch.events.story_director import StoryDirector

    runtime = NarrativeRuntime(story_director=StoryDirector())
    runtime.enable()
    for idx in range(3):
        runtime.seed_director_for_test(world=_director_world(), candidates=(_director_cand(),))
        runtime.admit(_event_impulse(f"http:clamp:{idx}", revision=90 + idx, fanout=90 + idx))
        assert runtime.reduce_next() is not None

    app = _app_with_runtime(runtime)
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            low = await (await client.get("/api/commentary/runtime/decisions?limit=0")).json()
            high = await (await client.get("/api/commentary/runtime/decisions?limit=101")).json()
            bad = await (await client.get("/api/commentary/runtime/decisions?limit=abc")).json()
            assert len(low["decisions"]) == 1
            assert 1 <= len(high["decisions"]) <= 100
            assert len(high["decisions"]) == 3
            assert len(bad["decisions"]) == 3  # default 20, ring has 3


@pytest.mark.asyncio
async def test_runtime_status_tape_capture_unavailable_http() -> None:
    """#273: GET runtime projects tape capture_unavailable golden over HTTP."""
    import json

    runtime = NarrativeRuntime()
    runtime.enable()
    runtime._tape_status = "unavailable"
    expected = json.loads(
        (_fixtures() / "status_component_tape_capture_unavailable.json").read_text(encoding="utf-8")
    )
    app = _app_with_runtime(runtime)
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.get("/api/commentary/runtime")
            assert resp.status == 200
            data = await resp.json()
            assert data["components"]["tape"] == expected


@pytest.mark.asyncio
async def test_runtime_status_mixed_boundary_pending_http() -> None:
    """#273: GET runtime projects value-free mixed pending boundaries over HTTP."""
    import json

    runtime = NarrativeRuntime()
    runtime.enable()
    runtime._config_ledger = {
        "schemaVersion": "commentary-config/2",
        "desiredGeneration": 7,
        "desiredHash": "sha256:" + ("1" * 64),
        "effectiveHash": "sha256:" + ("2" * 64),
        "applySequence": 12,
        "desiredValues": {"commentary.tts.voice": "secret-voice"},
        "pendingChanges": [
            {
                "key": "commentary.tts.voice",
                "boundary": "next_utterance",
                "desiredGeneration": 7,
                "value": "secret-voice",
            },
            {
                "key": "commentary.detector.battle_ahead_v1.max_closing_slope",
                "boundary": "next_stream",
                "desiredGeneration": 7,
                "value": 0.4,
            },
        ],
    }
    expected = json.loads(
        (_fixtures() / "status_config_pending_boundaries.json").read_text(encoding="utf-8")
    )
    app = _app_with_runtime(runtime)
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.get("/api/commentary/runtime")
            assert resp.status == 200
            data = await resp.json()
            assert data["language"] == expected["language"]
            assert data["catalog"] == expected["catalog"]
            assert data["config"] == expected["config"]
            for row in data["config"]["pendingChanges"]:
                assert set(row) == {"key", "boundary", "desiredGeneration"}


@pytest.mark.asyncio
async def test_runtime_status_llm_preflight_pending_http() -> None:
    """#273: LLM preflight pending projects components.llm.status=starting over HTTP."""
    from irswitch.events.qwen_transport import LlmComponent

    component = LlmComponent()
    component.start_preflight(desired_generation=1, warmup=True)
    runtime = NarrativeRuntime(llm_component=component)
    runtime.enable()
    app = _app_with_runtime(runtime)
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.get("/api/commentary/runtime")
            assert resp.status == 200
            llm = (await resp.json())["components"]["llm"]
            assert llm["status"] == "starting"
            assert llm["reason"] is None


@pytest.mark.asyncio
async def test_runtime_status_llm_preflight_failed_unavailable_http() -> None:
    """#273: failed LLM preflight projects unavailable + component_unavailable over HTTP."""
    from irswitch.events.qwen_transport import LlmComponent

    component = LlmComponent()
    component.start_preflight(desired_generation=1, warmup=True)
    component.complete_preflight(generation=1, residency="warmup_failed")
    runtime = NarrativeRuntime(llm_component=component)
    runtime.enable()
    app = _app_with_runtime(runtime)
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.get("/api/commentary/runtime")
            assert resp.status == 200
            llm = (await resp.json())["components"]["llm"]
            assert llm["status"] == "unavailable"
            assert llm["reason"] == "component_unavailable"

