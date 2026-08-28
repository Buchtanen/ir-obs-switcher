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
    assert "let resolvedStates" in js


def test_golden_gallery_clips_glow_overflow() -> None:
    js = display_v4_js()
    css = display_v4_css()
    assert "function isGoldenSnapshot(" in js
    assert "paintPlateMask" in js
    assert "glow_" in js
    assert "isolation: isolate" in css
    assert "contain: paint" in css
    assert ".golden-stage .v4-widget" in css
    assert "overflow: hidden" in css


def test_v4_live_widget_plate_masks_glow() -> None:
    """Live V4 cards skip glow_* PNGs and plate-mask .v4-art (WebM enter clip)."""
    js = display_v4_js()
    css = display_v4_css()
    assert "function paintPlateMask(" in js
    assert "base_plate.png" in js
    assert 'setProperty("-webkit-mask-image"' in js
    assert "paintPlateMask(art, family)" in js
    assert "if (glowMatch) return" in js
    assert ".v4-art.has-plate-mask" in css
    assert ".v4-widget {" in css
    widget_block = css.split(".v4-widget {", 1)[1].split("}", 1)[0]
    assert "overflow: hidden" in widget_block
    assert "contain: paint" in widget_block


def test_v4_copy_uses_absolute_plate_slots() -> None:
    """Copy must use V3-aligned absolute slots — not a centered 1fr grid (text too high)."""
    css = display_v4_css()
    assert "grid-template-rows: auto auto 1fr auto" not in css
    assert "align-content: center" not in css
    copy_block = css.split(".v4-copy {", 1)[1].split(".v4-copy .title", 1)[0]
    assert "display: block" in copy_block
    assert "top: 42px" in css
    assert ".v4-copy .title" in css
    assert ".v4-copy .subtitle" in css
    assert ".v4-copy .value" in css
    assert ".v4-copy .meta" in css
    title_block = css.split(".v4-copy .title {", 1)[1].split("}", 1)[0]
    assert "position: absolute" in title_block
    assert "left: 119px" in title_block
    assert "top: 42px" in title_block


def test_v4_icons_use_full_canvas_well_alignment() -> None:
    """V4 icons are 420×140 plates; a 64×64 crop shifts glyphs right of icon_well."""
    css = display_v4_css()
    icon_block = css.split(".v4-art .icon {", 1)[1].split("}", 1)[0]
    assert "width: 420px" in icon_block
    assert "height: 140px" in icon_block
    assert "background-size: 420px 140px" in icon_block
    assert "width: 64px" not in icon_block
    assert "left: 28px" not in icon_block


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
