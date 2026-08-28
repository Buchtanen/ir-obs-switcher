"""V4 golden layout theme coverage: docs, manifest parity, gallery URLs."""

from __future__ import annotations

import json
import re

from irswitch.overlay.http import web_root
from tests.test_golden_v4_fixtures import (
    GOLDEN_FIXTURES,
    _display_v4_js,
    _golden_doc_path,
    _v4_golden_catalog_ids,
)

GOLDEN_THEMES: tuple[str, ...] = ("cyber_racing", "stealth_graphite", "night_attack")
_V4_GOLDEN_FAMILY_RE = re.compile(r'family: "([a-z_]+)"')


def _manifest() -> dict:
    return json.loads((web_root() / "themes-v4" / "manifest.json").read_text(encoding="utf-8"))


def _golden_catalog_families(js: str | None = None) -> set[str]:
    source = js if js is not None else _display_v4_js()
    start = source.index("export const V4_GOLDEN_CATALOG = [")
    end = source.index("];", start)
    return set(_V4_GOLDEN_FAMILY_RE.findall(source[start:end]))


def test_golden_v4_md_documents_three_themes() -> None:
    doc = _golden_doc_path().read_text(encoding="utf-8")
    for theme in GOLDEN_THEMES:
        assert theme in doc, f"GOLDEN_V4.md missing theme {theme!r}"
    assert "Theme variants" in doc


def test_golden_v4_md_documents_theme_variant_urls() -> None:
    doc = _golden_doc_path().read_text(encoding="utf-8")
    assert "Theme variants" in doc
    for theme in GOLDEN_THEMES:
        assert f"theme={theme}" in doc, f"GOLDEN_V4.md missing example URL for theme {theme!r}"
    gallery_urls = [
        line.strip()
        for line in doc.splitlines()
        if "fixture=all" in line and "layout=golden" in line
    ]
    assert gallery_urls, "expected at least one golden gallery URL example"
    assert any("motion=off" in url for url in gallery_urls)


def test_golden_manifest_families_present_in_all_themes() -> None:
    manifest = _manifest()
    families = _golden_catalog_families()
    assert families, "expected families from V4_GOLDEN_CATALOG"
    for theme in GOLDEN_THEMES:
        theme_families = manifest["themes"][theme]["families"]
        missing = families - set(theme_families)
        assert not missing, f"{theme} missing golden families: {sorted(missing)}"


def test_golden_manifest_states_present_in_all_themes() -> None:
    manifest = _manifest()
    states = manifest["states"]
    for theme in GOLDEN_THEMES:
        for fixture_id in GOLDEN_FIXTURES:
            state = states.get(fixture_id)
            assert state is not None, f"manifest missing state for {fixture_id!r}"
            family_name = state["family"]
            family = manifest["themes"][theme]["families"][family_name]
            icon_path = family["icon_dir"] + f"/{fixture_id}.png"
            assert icon_path.startswith("themes/"), icon_path
            disk = web_root() / "themes-v4" / icon_path.removeprefix("themes/")
            assert disk.is_file(), f"{theme}/{fixture_id} icon missing at {disk}"


def test_v4_golden_catalog_ids_match_fixture_registry() -> None:
    assert _v4_golden_catalog_ids() == list(GOLDEN_FIXTURES)
