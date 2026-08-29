"""Phase 1: manifest-driven geometry contracts (zero visual-change defaults)."""

from __future__ import annotations

import json
import re

from golden_v4_shared import display_v4_css, display_v4_js
from v4_css_geometry import assert_rule_px, resolve_two_px, rule_decls

from irswitch.overlay.display_v4 import V4AssetResolver
from irswitch.overlay.http import web_root
from irswitch.overlay.v4_manifest_schema import validate_v4_manifest


def test_shipped_manifest_schema_2_validates() -> None:
    man = json.loads((web_root() / "themes-v4" / "manifest.json").read_text(encoding="utf-8"))
    assert validate_v4_manifest(man) == []
    assert man["manifest_schema"] == [2, 0]


def test_resolver_publishes_canvases_and_sysinfo() -> None:
    resolved = V4AssetResolver.load("cyber_racing", web_root()).to_dict()
    assert resolved["transient_canvas"] == [420, 140]
    assert resolved["sysinfo_canvas"] == [1920, 72]
    assert resolved["canvases"]["transient"]["size"] == [420, 140]
    assert resolved["zones"]["event"]["max"] == 6
    assert resolved["manifest_schema"] == [2, 0]


def test_display_v4_css_uses_canvas_var_fallbacks() -> None:
    css = display_v4_css()
    assert_rule_px(css, ".v4-widget", {"width": 420.0, "height": 140.0})
    assert "var(--v4-canvas-w" in rule_decls(css, ".v4-widget")["width"]
    assert "var(--v4-canvas-h" in rule_decls(css, ".v4-widget")["height"]
    icon = rule_decls(css, ".v4-art .icon")
    assert resolve_two_px(icon["background-size"]) == (420.0, 140.0)
    assert "var(--v4-canvas-w" in icon["width"]


def test_display_v4_js_applies_manifest_geometry() -> None:
    js = display_v4_js()
    assert "function canvasSize(" in js
    assert "function applyManifestGeometry(" in js
    assert "DEFAULT_CANVAS" in js
    assert "applyManifestGeometry()" in js
    assert "--v4-canvas-w" in js
    assert "--v4-zone-battle-y" in js
    # Zone routing prefers family.zone, battle default preserved.
    assert "family?.zone" in js or "family.zone" in js


def test_display_v4_css_has_no_bare_transient_literals_outside_fallbacks() -> None:
    """Naked 420/140/91 px outside var() fallbacks would fight Phase 1 mechanism."""
    css = display_v4_css()
    # Strip var(--name, Npx) fallbacks, then forbid remaining geometry literals.
    stripped = re.sub(r"var\(\s*--[\w-]+\s*,\s*[^)]+\)", "var(--x)", css)
    for needle in ("420px", "140px", "91px", "1920px", "72px"):
        assert needle not in stripped, f"bare {needle} remains outside var() fallbacks"
