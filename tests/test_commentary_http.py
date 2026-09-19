"""Commentary page + cut-over validate/speak API (#284 / #273)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from aiohttp import web

from irswitch.events.narrative_runtime import NarrativeRuntime
from irswitch.events.narrative_runtime_http import APP_NARRATIVE_RUNTIME, set_narrative_runtime
from irswitch.overlay.http import reset_overlay_server
from irswitch.server.api import create_app, reset_state

WRITE_CSRF_HEADERS = {"X-Requested-With": "irswitch"}

FIXTURES = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "commentary_runtime"


@pytest.fixture
def app() -> web.Application:
    reset_state()
    reset_overlay_server()
    set_narrative_runtime(None)
    return create_app()


@pytest.mark.asyncio
async def test_commentary_page_and_status(app: web.Application) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            page = await client.get("/commentary")
            assert page.status == 200
            html = await page.text()
            assert "Commentary" in html or "koment" in html.lower()
            status = await client.get("/api/commentary/status")
            assert status.status == 200
            body = await status.json()
            assert "backend" in body
            assert body["sample"]
            assert "settings" in body
            assert any(node["id"] == "overtake" for node in body["nodes"])


@pytest.mark.asyncio
async def test_public_speak_without_runtime_returns_503(app: web.Application) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    request = json.loads((FIXTURES / "speak_request.json").read_text(encoding="utf-8"))
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post(
                "/api/commentary/speak", json=request, headers=WRITE_CSRF_HEADERS
            )
            assert resp.status == 503
            body = await resp.json()
            assert body["schemaVersion"] == "commentary-runtime/2"
            assert body["error"]["code"] == "component_unavailable"


@pytest.mark.asyncio
async def test_public_validate_uses_runtime_contract(app: web.Application) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    request = json.loads((FIXTURES / "validate_request.json").read_text(encoding="utf-8"))
    expected = json.loads((FIXTURES / "validate_supported.json").read_text(encoding="utf-8"))
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post(
                "/api/commentary/validate", json=request, headers=WRITE_CSRF_HEADERS
            )
            assert resp.status == 200
            assert await resp.json() == expected


@pytest.mark.asyncio
async def test_public_speak_admits_via_narrative_runtime(app: web.Application) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    request = json.loads((FIXTURES / "speak_request.json").read_text(encoding="utf-8"))
    runtime = NarrativeRuntime()
    runtime.enable()
    app[APP_NARRATIVE_RUNTIME] = runtime
    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post(
                "/api/commentary/speak", json=request, headers=WRITE_CSRF_HEADERS
            )
            assert resp.status == 202
            body = await resp.json()
            assert body["accepted"] is True
            assert body["admittedState"] == "committed"
            assert body["schemaVersion"] == "commentary-runtime/2"


@pytest.mark.asyncio
async def test_public_speak_rejects_legacy_body_shape(app: web.Application) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post(
                "/api/commentary/speak",
                json={"text": "He takes P5 from Rossi.", "nodeId": "overtake"},
                headers=WRITE_CSRF_HEADERS,
            )
            assert resp.status == 400
            body = await resp.json()
            assert body["error"]["code"] == "invalid_request"


@pytest.mark.asyncio
async def test_decisions_endpoint_without_runtime(app: web.Application) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.get("/api/commentary/decisions")
            assert resp.status == 200
            body = await resp.json()
            assert body["runtime"] is False
            assert body["decisions"] == []
            status = await client.get("/api/commentary/status")
            payload = await status.json()
            assert "audioHint" in payload
            assert "Virtual Audio" in payload["audioHint"]
            assert "settings" in payload


@pytest.mark.asyncio
async def test_commentary_page_exposes_decision_panel(app: web.Application) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            page = await client.get("/commentary")
            html = await page.text()
            assert (
                "decision log" in html.lower()
                or "proč ticho" in html.lower()
                or "decision" in html.lower()
            )
            assert "/api/commentary/runtime/decisions" in html
            assert "/api/commentary/runtime" in html
            # #273: dashboard must not call legacy status/decisions contracts.
            assert "/api/commentary/status" not in html
            assert '"/api/commentary/decisions"' not in html
            assert "/api/commentary/decisions?" not in html


@pytest.mark.asyncio
async def test_assignments_route_unregistered_generic_404(app: web.Application) -> None:
    """#273: GET /api/commentary/assignments removed — generic 404, no tombstone."""
    from aiohttp.test_utils import TestClient, TestServer

    resources = {resource.canonical for resource in app.router.resources()}
    assert "/api/commentary/assignments" not in resources

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.get("/api/commentary/assignments")
            assert resp.status == 404
            content_type = resp.headers.get("Content-Type", "")
            # Generic aiohttp/server 404 — not a commentary-runtime JSON tombstone.
            if "application/json" in content_type:
                body = await resp.json()
                assert "schemaVersion" not in body
                assert body.get("error", {}).get("code") != "gone"
            else:
                text = await resp.text()
                assert "commentary-runtime" not in text
                assert "gone" not in text.lower()


@pytest.mark.asyncio
async def test_commentary_page_uses_versioned_contracts_only(app: web.Application) -> None:
    """#273: operator page fetches only commentary-runtime/2 public paths."""
    from aiohttp.test_utils import TestClient, TestServer

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            page = await client.get("/commentary")
            html = await page.text()
            for required in (
                "/api/commentary/runtime",
                "/api/commentary/runtime/decisions",
                "/api/commentary/validate",
                "/api/commentary/speak",
            ):
                assert required in html
            for banned in (
                "/api/commentary/status",
                "/api/commentary/assignments",
            ):
                assert banned not in html
            assert "/api/commentary/decisions" not in html.replace(
                "/api/commentary/runtime/decisions", ""
            )


@pytest.mark.asyncio
async def test_commentary_page_surfaces_by_tape_channel_cadence(app: web.Application) -> None:
    """#273: operator page renders byTapeChannel cadence without DEBUG/event parsing."""
    from aiohttp.test_utils import TestClient, TestServer

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            page = await client.get("/commentary")
            html = await page.text()
            assert "byTapeChannel" in html
            assert "summarizeByTapeChannel" in html
            for counter in ("kick", "accepted", "queued", "selected", "started", "expired"):
                assert counter + "=" in html
