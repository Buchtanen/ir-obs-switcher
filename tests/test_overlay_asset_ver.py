"""Overlay HUD asset ?v= lockstep (OBS CEF cache bust)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "src" / "irswitch" / "web" / "overlay"
OVERLAY_JS = OVERLAY / "js" / "overlay.js"
DISPLAY_V4 = OVERLAY / "js" / "display-v4.js"
INDEX = OVERLAY / "index.html"
DEMO_V4 = OVERLAY / "js" / "demo-v4.js"

_VER_RE = re.compile(r'const OVERLAY_ASSET_VER = "([^"]+)"')
_CACHE_RE = re.compile(r'const ASSET_CACHE = "([^"]+)"')
_QV_RE = re.compile(r"\?v=([0-9.]+)")


def test_overlay_asset_ver_lockstep() -> None:
    overlay_js = OVERLAY_JS.read_text(encoding="utf-8")
    match = _VER_RE.search(overlay_js)
    assert match, "OVERLAY_ASSET_VER missing in overlay.js"
    ver = match.group(1)
    assert overlay_js.count(f'OVERLAY_ASSET_VER = "{ver}"') == 1

    index = INDEX.read_text(encoding="utf-8")
    index_vers = _QV_RE.findall(index)
    assert index_vers, "index.html has no ?v="
    assert set(index_vers) == {ver}, f"index.html ?v= {index_vers} != {ver}"

    demo = DEMO_V4.read_text(encoding="utf-8")
    demo_vers = _QV_RE.findall(demo)
    assert demo_vers, "demo-v4.js has no ?v="
    assert set(demo_vers) == {ver}, f"demo-v4.js ?v= {demo_vers} != {ver}"

    assert "themes/${id}.css?v=${OVERLAY_ASSET_VER}" in overlay_js
    assert f"cyber_racing.css?v={ver}" in index

    display = DISPLAY_V4.read_text(encoding="utf-8")
    cache = _CACHE_RE.search(display)
    assert cache, "ASSET_CACHE missing in display-v4.js"
    assert (
        cache.group(1) == ver
    ), f"display-v4.js ASSET_CACHE {cache.group(1)!r} != OVERLAY_ASSET_VER {ver!r}"
