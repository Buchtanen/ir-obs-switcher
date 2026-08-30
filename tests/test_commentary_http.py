"""Commentary page and speak/validate API."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from aiohttp import web

from irswitch.commentary.tts import TtsResult
from irswitch.overlay.http import CSRF_HEADER, CSRF_VALUE, reset_overlay_server
from irswitch.server.api import create_app, reset_state


@pytest.fixture
def app() -> web.Application:
    reset_state()
    reset_overlay_server()
    return create_app()


@pytest.mark.asyncio
async def test_commentary_page_and_status(app: web.Application) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            page = await client.get("/commentary")
            assert page.status == 200
            html = await page.text()
            assert "Mluvit v prohlížeči" in html
            status = await client.get("/api/commentary/status")
            assert status.status == 200
            body = await status.json()
            assert "backend" in body
            assert body["sample"]
            assert any(node["id"] == "overtake" for node in body["nodes"])


@pytest.mark.asyncio
async def test_validate_and_speak_require_csrf(app: web.Application) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            denied = await client.post("/api/commentary/speak", json={"text": "Hello."})
            assert denied.status == 403


@pytest.mark.asyncio
async def test_validate_rejects_bad_line(app: web.Application) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post(
                "/api/commentary/validate",
                json={"text": "NO TERMINAL", "nodeId": "overtake"},
                headers={CSRF_HEADER: CSRF_VALUE},
            )
            body = await resp.json()
            assert body["ok"] is False
            assert any(item["code"] == "terminal_punct" for item in body["issues"])


@pytest.mark.asyncio
async def test_speak_calls_tts_after_validation(app: web.Application) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    with patch(
        "irswitch.commentary.http.speak_text",
        return_value=TtsResult(backend="espeak", spoken=True),
    ) as mocked:
        async with TestServer(app) as server:
            async with TestClient(server) as client:
                resp = await client.post(
                    "/api/commentary/speak",
                    json={"text": "You take P5 from Rossi.", "nodeId": "overtake"},
                    headers={CSRF_HEADER: CSRF_VALUE},
                )
                body = await resp.json()
                assert resp.status == 200
                assert body["spoken"] is True
                assert body["backend"] == "espeak"
                mocked.assert_called_once()


@pytest.mark.asyncio
async def test_speak_blocks_invalid_text(app: web.Application) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    with patch("irswitch.commentary.http.speak_text") as mocked:
        async with TestServer(app) as server:
            async with TestClient(server) as client:
                resp = await client.post(
                    "/api/commentary/speak",
                    json={"text": "SHOUTING WITHOUT PUNCT", "nodeId": "overtake"},
                    headers={CSRF_HEADER: CSRF_VALUE},
                )
                assert resp.status == 400
                mocked.assert_not_called()


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
            assert "decisionLogSize" in payload["settings"]


@pytest.mark.asyncio
async def test_commentary_page_exposes_decision_panel(app: web.Application) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            page = await client.get("/commentary")
            html = await page.text()
            assert "decision log" in html.lower() or "Proč ticho" in html
            assert "/api/commentary/decisions" in html
