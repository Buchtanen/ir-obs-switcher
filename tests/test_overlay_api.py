"""Overlay HTTP/WS and debug inject. Switcher /ws must stay unchanged."""

from __future__ import annotations

from pathlib import Path

import pytest
from aiohttp import web

from irswitch.overlay.http import CSRF_HEADER, CSRF_VALUE, reset_overlay_server
from irswitch.server.api import create_app, reset_state


@pytest.fixture
def app() -> web.Application:
    reset_state()
    reset_overlay_server()
    return create_app()


@pytest.mark.asyncio
async def test_overlay_ws_sends_snapshot(app: web.Application) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            async with client.ws_connect("/ws/overlay") as ws:
                msg = await ws.receive_json()
                assert msg["type"] == "snapshot"
                assert "race" in msg
                assert "bio" in msg
                assert "system" in msg
                assert "activeEvents" in msg
                assert msg["theme"] == "cyber_racing"
                assert msg["assets"]["sysinfo_background"].endswith("sysinfo_background.svg")
                assert msg["assets"]["battle_glow"].endswith("battle_glow.png")


@pytest.mark.asyncio
async def test_overlay_snapshot_and_theme_assets_served(app: web.Application) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.get("/api/overlay/snapshot")
            assert resp.status == 200
            body = await resp.json()
            assert body["type"] == "snapshot"
            assert body["theme"] == "cyber_racing"
            assert body["assets"]["battle_background"]
            asset = await client.get("/overlay/web/" + body["assets"]["battle_background"])
            assert asset.status == 200
            glow = await client.get("/overlay/web/" + body["assets"]["battle_glow"])
            assert glow.status == 200


@pytest.mark.asyncio
async def test_debug_emit_requires_csrf(app: web.Application) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.post("/overlay/debug/emit", json={"name": "hunting"})
            assert resp.status == 403
            resp = await client.post(
                "/overlay/debug/emit",
                json={"name": "hunting"},
                headers={CSRF_HEADER: CSRF_VALUE},
            )
            assert resp.status == 200
            body = await resp.json()
            assert body["event"]["data"]["state"] == "hunting"


@pytest.mark.asyncio
async def test_config_get_redacts_password(app: web.Application, tmp_path: Path) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    from irswitch.config import AppConfig
    from irswitch.server.api import set_app_config
    from irswitch.server.app_keys import APP_CONFIG, APP_CONFIG_PATH

    ini = tmp_path / "config.ini"
    ini.write_text("""[app]
http_host = 127.0.0.1
http_port = 17321
log_level = INFO
[iracing]
poll_hz = 5
[obs]
ws_url = ws://127.0.0.1:4455
password = super-secret
[switching]
autoswitch_default = true
debounce_ms = 900
cooldown_ms = 1000
override_seconds = 120
safe_scene = Idle
[scenes]
IDLE = Idle
GARAGE = Pits
RACE = Race
REPLAY = Replay
""")
    cfg = AppConfig.from_file(ini)
    set_app_config(cfg)
    app[APP_CONFIG] = cfg
    app[APP_CONFIG_PATH] = ini

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.get("/api/config")
            assert resp.status == 200
            data = await resp.json()
            assert data["switcher"]["obs.password"] == "***"
            assert "schema" in data
            put = await client.put(
                "/api/config",
                json={"values": {"sampling.default_hz": 7}},
                headers={CSRF_HEADER: CSRF_VALUE},
            )
            assert put.status == 200
            reloaded = AppConfig.from_file(ini)
            assert reloaded.overlay.sampling.default_hz == 7


@pytest.mark.asyncio
async def test_overlay_page_served(app: web.Application) -> None:
    from aiohttp.test_utils import TestClient, TestServer

    async with TestServer(app) as server:
        async with TestClient(server) as client:
            resp = await client.get("/overlay")
            assert resp.status == 200
            text = await resp.text()
            assert "sysinfo-widget" in text
            assert "data-slot=" in text
            asset = await client.get("/overlay/web/themes/cyber_racing/assets/sysinfo_background.svg")
            assert asset.status == 200
            dbg = await client.get("/overlay/debug")
            assert dbg.status == 200
            demo = await client.get("/overlay/demo")
            assert demo.status == 200
            demo_html = await demo.text()
            assert "/overlay?demo=1" in demo_html
            assert "cyber_racing" in demo_html
            script = await client.get("/overlay/static/js/demo.js")
            assert script.status == 200
            cfg = await client.get("/config")
            assert cfg.status == 200
