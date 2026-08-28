"""V4 asset resolver, presentation payload, and i18n HTTP wiring."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from irswitch.overlay.display_v4 import V4AssetResolver, manifest_rel_to_web
from irswitch.overlay.http import (
    handle_overlay_i18n,
    presentation_payload,
    register_overlay_routes,
    web_root,
)
from irswitch.overlay.i18n import EN, copy_catalog_for_renderer
from irswitch.overlay.settings import OverlaySettings, OverlayV4Settings


@pytest.fixture
def v4_config(monkeypatch: pytest.MonkeyPatch) -> None:
    overlay = replace(
        OverlaySettings(),
        theme="cyber_racing",
        language="cs",
        v4=OverlayV4Settings(assets=True, renderer=False),
    )
    monkeypatch.setattr(
        "irswitch.server.api.get_app_config",
        lambda: SimpleNamespace(overlay=overlay),
    )


def test_manifest_rel_to_web_maps_theme_prefix() -> None:
    rel = "themes/cyber_racing/battle/layers/shadow.png"
    assert manifest_rel_to_web(rel) == "themes-v4/cyber_racing/battle/layers/shadow.png"


def test_v4_resolver_resolves_known_states() -> None:
    root = web_root()
    resolver = V4AssetResolver.load("cyber_racing", root)

    lap = resolver.resolve("timing", "lap_complete")
    assert lap["family"] == "timing"
    assert lap["state"] == "lap_complete"
    assert lap["icon"] == "themes-v4/cyber_racing/timing/icons/lap_complete.png"
    assert (root / lap["icon"]).is_file()
    assert any(layer["file"] == "shadow.png" and layer["path"] for layer in lap["layers"])

    pit = resolver.resolve_state("pit_entry")
    assert pit is not None
    assert pit["family"] == "pit"
    assert pit["icon"] == "themes-v4/cyber_racing/pit/icons/pit_entry.png"
    assert (root / pit["icon"]).is_file()

    bio = resolver.resolve_state("hr_pressure")
    assert bio is not None
    assert bio["family"] == "bio"
    assert bio["icon"] == "themes-v4/cyber_racing/bio/icons/hr_pressure.png"
    assert (root / bio["icon"]).is_file()


def test_v4_resolver_motion_reels() -> None:
    resolver = V4AssetResolver.load("cyber_racing", web_root())
    enter = resolver.resolve_motion("enter_reveal")
    theme = resolver.resolve_motion("theme_glitch")
    assert enter == "themes-v4/cyber_racing/motion/enter_reveal.webm"
    assert theme == "themes-v4/cyber_racing/motion/theme_glitch.webm"
    assert (web_root() / enter).is_file()
    assert (web_root() / theme).is_file()


def test_presentation_payload_omits_v4_when_flags_off(monkeypatch: pytest.MonkeyPatch) -> None:
    overlay = replace(OverlaySettings(), v4=OverlayV4Settings(assets=False, renderer=False))
    monkeypatch.setattr(
        "irswitch.server.api.get_app_config",
        lambda: SimpleNamespace(overlay=overlay),
    )
    payload = presentation_payload()
    assert "v4" not in payload
    assert payload["assets"]["battle_base_plate"].startswith("themes/cyber_racing/assets/")


def test_presentation_payload_includes_v4_resolver(v4_config: None) -> None:
    payload = presentation_payload()
    assert "v4" in payload
    v4 = payload["v4"]
    assert v4["assets"] is True
    assert v4["renderer"] is False
    assert v4["language"] == "cs"
    assert (
        v4["copyCatalog"]["lap.personal_best"]
        == copy_catalog_for_renderer("cs")["lap.personal_best"]
    )
    assert v4["resolved"]["theme"] == "cyber_racing"
    assert "lap_complete" in v4["resolved"]["states"]
    assert v4["resolved"]["motions"]["enter_reveal"].endswith("enter_reveal.webm")
    assert payload["assets"]["battle_base_plate"].startswith("themes/cyber_racing/assets/")


def test_copy_catalog_for_renderer_merges_locale() -> None:
    catalog = copy_catalog_for_renderer("cs")
    assert catalog["lap.personal_best"] != EN["lap.personal_best"]
    assert catalog["incident"] == EN["incident"]


@pytest.mark.asyncio
async def test_overlay_i18n_endpoint(v4_config: None) -> None:
    app = web.Application()
    register_overlay_routes(app)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/overlay/i18n")
        assert resp.status == 200
        body = await resp.json()
        assert body["language"] == "cs"
        assert (
            body["copyCatalog"]["lap.personal_best"]
            == copy_catalog_for_renderer("cs")["lap.personal_best"]
        )


@pytest.mark.asyncio
async def test_handle_overlay_i18n_direct() -> None:
    request = SimpleNamespace()
    resp = await handle_overlay_i18n(request)  # type: ignore[arg-type]
    assert resp.status == 200
