"""Studio is additive and served from the same packaged web root as the HUD."""

from pathlib import Path
from unittest.mock import patch

import pytest
from aiohttp.test_utils import TestClient, TestServer

from irswitch.overlay.http import reset_overlay_server
from irswitch.server.api import create_app, reset_state


@pytest.mark.asyncio
async def test_studio_routes_and_existing_pages() -> None:
    reset_state()
    reset_overlay_server()
    async with TestClient(TestServer(create_app())) as client:
        redirect = await client.get("/studio", allow_redirects=False)
        assert redirect.status == 308
        assert redirect.headers["Location"] == "/studio/"
        page = await client.get("/studio/")
        assert page.status == 200
        html = await page.text()
        assert "irswitch Studio" in html
        import re

        asset_paths = re.findall(r'(?:src|href)="(/studio/assets/[^\"]+)"', html)
        assert asset_paths
        for path in asset_paths:
            asset = await client.get(path)
            assert asset.status == 200, path
        assert (await client.get("/studio/assets/")).status == 403
        assert (await client.get("/studio/assets/missing.js")).status == 404
        for path in ("/admin", "/config", "/commentary", "/overlay"):
            assert (await client.get(path)).status == 200, path


@pytest.mark.asyncio
async def test_studio_missing_build_returns_actionable_503(tmp_path: Path) -> None:
    from aiohttp import web

    from irswitch.server.studio import register_studio_routes

    app = web.Application()
    with patch("irswitch.server.studio.web_root", return_value=tmp_path):
        register_studio_routes(app)
        async with TestClient(TestServer(app)) as client:
            response = await client.get("/studio/")
            assert response.status == 503
            assert "build" in (await response.text()).lower()


def test_studio_uses_frozen_web_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import sys

    from irswitch.overlay.http import web_root

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    assert web_root() / "studio" == tmp_path / "irswitch" / "web" / "studio"
