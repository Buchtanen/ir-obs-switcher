"""Phase 2: per-theme canvas overrides, text_slots, glyph icon mode."""

from __future__ import annotations

import copy
import json

from golden_v4_shared import display_v4_css, display_v4_js

from irswitch.overlay.display_v4 import V4AssetResolver
from irswitch.overlay.http import web_root
from irswitch.overlay.v4_manifest_schema import merge_canvas_config, validate_v4_manifest


def _manifest() -> dict:
    return json.loads((web_root() / "themes-v4" / "manifest.json").read_text(encoding="utf-8"))


def test_shipped_themes_declare_full_canvas_overrides() -> None:
    man = _manifest()
    assert validate_v4_manifest(man) == []
    for theme_id in ("cyber_racing", "stealth_graphite", "night_attack"):
        merged = merge_canvas_config(man, theme_id, "transient")
        assert merged["icon_mode"] == "full_canvas"
        assert "icon_box" not in merged
        assert merged["text_slots"]["title"]["left"] == 119
        assert merged["text_slots"]["title"]["top"] == 38
        assert merged["safe_box"]["left"] == 119


def test_merge_canvas_config_prefers_theme_override() -> None:
    man = _manifest()
    man["themes"]["cyber_racing"]["canvases"]["transient"] = {
        "icon_mode": "glyph",
        "icon_box": [22, 26, 64, 64],
        "safe_box": {"left": 54, "top": 20, "right": 22, "bottom": 18},
    }
    merged = merge_canvas_config(man, "cyber_racing", "transient")
    assert merged["icon_mode"] == "glyph"
    assert merged["icon_box"] == [22, 26, 64, 64]
    assert merged["size"] == [420, 140]
    assert validate_v4_manifest(man) == []


def test_theme_glyph_without_box_rejected() -> None:
    man = copy.deepcopy(_manifest())
    man["themes"]["cyber_racing"]["canvases"]["transient"] = {"icon_mode": "glyph"}
    errors = validate_v4_manifest(man)
    assert any("glyph requires icon_box" in e for e in errors)


def test_theme_full_canvas_with_box_rejected() -> None:
    man = copy.deepcopy(_manifest())
    man["themes"]["cyber_racing"]["canvases"]["transient"] = {
        "icon_mode": "full_canvas",
        "icon_box": [0, 0, 64, 64],
    }
    errors = validate_v4_manifest(man)
    assert any("forbids icon_box" in e for e in errors)


def test_resolver_exposes_theme_canvases() -> None:
    resolved = V4AssetResolver.load("cyber_racing", web_root()).to_dict()
    assert resolved["theme_canvases"]["transient"]["icon_mode"] == "full_canvas"
    assert "title" in resolved["theme_canvases"]["transient"]["text_slots"]


def test_display_v4_js_has_glyph_and_theme_canvas_helpers() -> None:
    js = display_v4_js()
    assert "function resolveThemeCanvas(" in js
    assert "function applyIconMode(" in js
    assert "function applyThemeTextAndIconVars(" in js
    assert "mode-glyph" in js
    assert "icon_mode" in js


def test_display_v4_css_has_glyph_icon_mode() -> None:
    css = display_v4_css()
    assert ".v4-art .icon.mode-glyph" in css
    assert "background-size: contain" in css
    assert "--v4-icon-x" in css
    assert "--v4-icon-w" in css
