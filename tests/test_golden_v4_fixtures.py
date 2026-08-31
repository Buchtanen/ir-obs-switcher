"""V4 golden fixture registry, docs, and presentation payload checks."""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import pytest
from golden_v4_shared import (
    GOLDEN_FIXTURE_COUNT,
    GOLDEN_FIXTURES,
    catalog_states,
    display_v4_css,
    display_v4_js,
    fixture_export_pattern,
    fixture_id_pattern,
    golden_doc_path,
    v4_golden_catalog_ids,
)

from irswitch.overlay.http import presentation_payload, web_root


def test_golden_fixture_registry_has_33_entries() -> None:
    assert len(GOLDEN_FIXTURES) == GOLDEN_FIXTURE_COUNT


def test_golden_v4_md_documents_33_fixtures() -> None:
    doc = golden_doc_path().read_text(encoding="utf-8")
    documented = fixture_id_pattern().findall(doc)
    assert len(documented) == GOLDEN_FIXTURE_COUNT
    assert len(set(documented)) == GOLDEN_FIXTURE_COUNT


def test_v4_golden_catalog_has_33_entries() -> None:
    catalog_ids = v4_golden_catalog_ids()
    assert len(catalog_ids) == GOLDEN_FIXTURE_COUNT
    assert catalog_ids == list(GOLDEN_FIXTURES)


def test_golden_fixture_registry_covers_catalog_states() -> None:
    catalog_states_set = catalog_states()
    fixture_states = set(GOLDEN_FIXTURES)
    missing = catalog_states_set - fixture_states
    assert not missing, f"catalog states missing golden fixtures: {sorted(missing)}"


def test_golden_fixtures_exported_in_display_v4_js() -> None:
    js = display_v4_js()
    for fixture_id in GOLDEN_FIXTURES:
        assert f'id: "{fixture_id}"' in js, f"missing V4_GOLDEN_CATALOG entry for {fixture_id}"
    assert "export function v4FixtureLapComplete" in js
    assert "export function v4FixtureIncident" in js


def test_golden_v4_md_lists_all_fixture_ids() -> None:
    doc = golden_doc_path().read_text(encoding="utf-8")
    documented = set(fixture_id_pattern().findall(doc))
    missing = set(GOLDEN_FIXTURES) - documented
    extra = documented - set(GOLDEN_FIXTURES)
    assert not missing, f"GOLDEN_V4.md missing fixture ids: {sorted(missing)}"
    assert not extra, f"GOLDEN_V4.md documents unknown fixture ids: {sorted(extra)}"


def test_golden_v4_md_has_gallery_url() -> None:
    doc = golden_doc_path().read_text(encoding="utf-8")
    assert "fixture=all" in doc
    assert "layout=golden" in doc
    assert "renderer=v4" in doc


def test_golden_overlay_assets_present() -> None:
    js = display_v4_js()
    css = (web_root() / "overlay" / "css" / "display-v4.css").read_text(encoding="utf-8")
    overlay_js = (web_root() / "overlay" / "js" / "overlay.js").read_text(encoding="utf-8")
    assert "V4_GOLDEN_CATALOG" in js
    assert "renderV4GoldenGallery" in js
    assert "getV4GoldenFixture" in js
    assert "golden-gallery" in css
    assert "#v4-golden-gallery" in css
    assert "startV4Golden" in overlay_js
    assert (web_root() / "overlay" / "golden.html").is_file()


def test_presentation_payload_includes_v4_when_assets_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from irswitch.overlay.settings import OverlaySettings, OverlayV4Settings

    overlay = replace(
        OverlaySettings(),
        theme="cyber_racing",
        v4=OverlayV4Settings(assets=True, renderer=False),
    )
    monkeypatch.setattr(
        "irswitch.server.api.get_app_config",
        lambda: SimpleNamespace(overlay=overlay),
    )
    payload = presentation_payload()
    assert "v4" in payload
    assert payload["v4"]["assets"] is True
    assert payload["v4"]["manifestUrl"].endswith("themes-v4/manifest.json")


def test_display_v4_js_has_unique_fixture_exports() -> None:
    js = (web_root() / "overlay" / "js" / "display-v4.js").read_text(encoding="utf-8")
    exports = fixture_export_pattern().findall(js)
    assert exports, "expected v4Fixture* exports in display-v4.js"
    assert len(exports) == len(set(exports)), f"duplicate exports: {exports}"
    # Boot contract (Phase 0): init marks manifest status for fallback UI.
    assert "dataset.v4Manifest" in js


def test_rival_threat_copy_uses_live_rival_position_not_sample_p8() -> None:
    """Live RIVAL_THREAT has rivalPosition/gap; manifest sample value is hardcoded P8."""
    js = (web_root() / "overlay" / "js" / "display-v4.js").read_text(encoding="utf-8")
    assert 'stateKey === "rival_threat"' in js
    assert "metrics.position ?? metrics.rivalPosition" in js
    assert "resolveTargetName(metrics, envelope)" in js


def test_golden_gallery_clips_glow_overflow() -> None:
    from v4_css_geometry import rule_decls

    js = display_v4_js()
    css = display_v4_css()
    assert "function isGoldenSnapshot(" in js
    assert "paintPlateMask" in js
    assert "glow_" in js
    widget = rule_decls(css, ".v4-widget")
    assert widget.get("isolation") == "isolate"
    assert widget.get("contain") == "paint"
    assert ".golden-stage .v4-widget" in css
    assert "overflow: hidden" in css


def test_v4_live_widget_plate_masks_glow() -> None:
    """Live V4 cards skip glow_* PNGs and plate-mask .v4-art (WebM enter clip)."""
    from v4_css_geometry import rule_decls

    js = display_v4_js()
    css = display_v4_css()
    assert "function paintPlateMask(" in js
    assert "base_plate.png" in js
    assert "material.png" in js
    assert 'setProperty("mask-composite", "add")' in js
    assert 'setProperty("-webkit-mask-composite", "source-over")' in js
    assert 'setProperty("-webkit-mask-image"' in js
    assert "paintPlateMask(art, family" in js
    assert "if (glowMatch) return" in js
    assert ".v4-art.has-plate-mask" in css
    widget = rule_decls(css, ".v4-widget")
    assert widget.get("overflow") == "hidden"
    assert widget.get("contain") == "paint"


def test_session_bio_exception_subtitles_do_not_reuse_headline_tokens() -> None:
    """Headline tokens on subtitle collapse to FINAL LAP / FINAL LAP in the dry test."""
    js = display_v4_js()
    assert 'resolveCopy("session.final_lap") || sample.subtitle' not in js
    assert 'resolveCopy("session.finish") || sample.subtitle' not in js
    assert 'resolveCopy("bio.hr_pressure") || sample.subtitle' not in js
    assert 'resolveCopy("ble.lost") || sample.subtitle' not in js
    assert 'resolveCopy("incident") || sample.subtitle' not in js
    assert 'resolveCopy(copy.statusToken) || sample.subtitle || "ONE MORE PUSH"' in js
    assert 'resolveCopy(copy.statusToken) || sample.subtitle || "RACE COMPLETE"' in js


def test_display_v4_headline_and_active_hold_contract() -> None:
    """Unknown copy tokens fall back to sample title; ACTIVE respects maxHoldMs."""
    js = display_v4_js()
    assert "function resolveHeadline(token, sampleTitle, stateKey)" in js
    assert "function scheduleHoldTimer(node, key, envelope, phase, golden)" in js
    assert "function preemptStickyFamilyPeers(familyName, keepKey, phase)" in js
    assert "resolveHeadline(copy.headlineToken, sample.title, stateKey)" in js
    assert "return labelForToken(token) || token" not in js
    assert "maxHoldMs" in js
    assert "preemptStickyFamilyPeers(familyName, key, phase)" in js


def test_v4_copy_uses_absolute_plate_slots() -> None:
    """Copy must use V3-aligned absolute slots — not a centered 1fr grid (text too high)."""
    from v4_css_geometry import assert_rule_px, css_rule_block, rule_decls

    css = display_v4_css()
    copy_block = css_rule_block(css, ".v4-copy")
    assert "grid-template-rows: auto auto 1fr auto" not in copy_block
    assert "align-content: center" not in copy_block
    assert "display: block" in copy_block
    assert ".v4-copy .title" in css
    assert ".v4-copy .subtitle" in css
    assert ".v4-copy .value" in css
    assert ".v4-copy .meta" in css
    title = rule_decls(css, ".v4-copy .title")
    assert title.get("position") == "absolute"
    assert_rule_px(css, ".v4-copy .title", {"left": 119.0, "top": 38.0})


def test_v4_icons_use_full_canvas_well_alignment() -> None:
    """V4 icons are 420×140 plates; a 64×64 crop shifts glyphs right of icon_well."""
    from v4_css_geometry import assert_rule_px, css_rule_block, resolve_two_px, rule_decls

    css = display_v4_css()
    icon_block = css_rule_block(css, ".v4-art .icon")
    assert_rule_px(css, ".v4-art .icon", {"width": 420.0, "height": 140.0})
    decls = rule_decls(css, ".v4-art .icon")
    w, h = resolve_two_px(decls["background-size"])
    assert (w, h) == (420.0, 140.0)
    assert "64px" not in icon_block
    assert "28px" not in icon_block


def test_cyber_racing_icon_wells_centered_on_glyph() -> None:
    """cyber_racing icon_well fill+rim must be concentric on the glyph center."""
    from test_overlay_assets_v3 import _png_rgba

    root = web_root() / "themes-v4" / "cyber_racing"
    wells = sorted(root.rglob("icon_well.png"))
    assert wells, "expected cyber_racing icon_well assets"
    target_x, target_y = 62.0, 70.0
    for path in wells:
        width, height, pixels = _png_rgba(path)
        fill_xs: list[int] = []
        fill_ys: list[int] = []
        rim_xs: list[int] = []
        rim_ys: list[int] = []
        for y in range(height):
            row = pixels[y * width * 4 : (y + 1) * width * 4]
            for x in range(width):
                a = row[x * 4 + 3]
                if a <= 100:
                    continue
                r, g, b = row[x * 4], row[x * 4 + 1], row[x * 4 + 2]
                lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
                if lum <= 40:
                    fill_xs.append(x)
                    fill_ys.append(y)
                else:
                    rim_xs.append(x)
                    rim_ys.append(y)
        assert fill_xs and rim_xs, path.name
        fill_mx = (min(fill_xs) + max(fill_xs)) / 2.0
        fill_my = (min(fill_ys) + max(fill_ys)) / 2.0
        rim_mx = (min(rim_xs) + max(rim_xs)) / 2.0
        rim_my = (min(rim_ys) + max(rim_ys)) / 2.0
        assert abs(fill_mx - rim_mx) <= 1.0, f"{path}: fill/rim x {fill_mx} vs {rim_mx}"
        assert abs(fill_my - rim_my) <= 1.0, f"{path}: fill/rim y {fill_my} vs {rim_my}"
        assert abs(fill_mx - target_x) <= 1.0, f"{path}: fill_mid_x={fill_mx}"
        assert abs(fill_my - target_y) <= 1.5, f"{path}: fill_mid_y={fill_my}"


def test_golden_reduced_motion_paths() -> None:
    js = display_v4_js()
    css = display_v4_css()
    assert "let motionDisabled = false" in js
    assert "function prefersReducedMotion()" in js
    assert "motionDisabled = Boolean(options.motionDisabled)" in js
    assert "prefersReducedMotion() || isGoldenSnapshot(node)" in js
    assert 'window.matchMedia?.("(prefers-reduced-motion: reduce)")' in js
    assert ".golden-stage" in css
    assert ".golden-stage .v4-art" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
