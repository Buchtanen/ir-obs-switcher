"""V4 overlay theme pack: manifest wiring, parity, geometry, size budget."""

from __future__ import annotations

import json
import re
import struct
from pathlib import Path

from irswitch.overlay.http import web_root

THEMES = ("cyber_racing", "stealth_graphite", "night_attack")
SNAKE_STEM = re.compile(r"^[a-z0-9_]+$")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
V4_ROOT = web_root() / "themes-v4"
MAX_PACK_BYTES = 8 * 1024 * 1024  # production ~5.8 MiB; headroom for CI


def _manifest() -> dict:
    return json.loads((V4_ROOT / "manifest.json").read_text(encoding="utf-8"))


def _manifest_path_to_disk(rel: str) -> Path:
    """Manifest paths use ``themes/``; shipped tree lives under ``themes-v4/``."""
    if rel.startswith("themes/"):
        rel = "themes-v4/" + rel[len("themes/") :]
    return web_root() / rel


def _png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == PNG_SIGNATURE, path
    width, height = struct.unpack(">II", data[16:24])
    return width, height


def test_v4_manifest_version_and_canvas() -> None:
    manifest = _manifest()
    assert manifest["version"] == 4
    assert manifest["transient_canvas"] == [420, 140]
    assert manifest["sysinfo_canvas"] == [1920, 72]
    assert set(manifest["themes"]) == set(THEMES)
    assert set(manifest["states"]) >= {
        "lap_complete",
        "hunting",
        "overtake",
        "pit_entry",
        "hr_pressure",
        "final_lap",
    }


def test_v4_theme_file_parity() -> None:
    names: dict[str, list[str]] = {}
    for theme in THEMES:
        files = sorted(
            str(p.relative_to(V4_ROOT / theme)).replace("\\", "/")
            for p in (V4_ROOT / theme).rglob("*")
            if p.is_file()
        )
        for rel in files:
            name = Path(rel).name
            stem = Path(name).stem
            suffix = Path(name).suffix
            assert " " not in name, rel
            assert name == name.lower(), rel
            assert SNAKE_STEM.fullmatch(stem), rel
            assert suffix in {".png", ".webm"}, rel
        names[theme] = files
    assert names["cyber_racing"] == names["stealth_graphite"] == names["night_attack"]
    assert len(names["cyber_racing"]) == 185


def test_v4_layer_and_icon_files_exist() -> None:
    manifest = _manifest()
    transient_w, transient_h = manifest["transient_canvas"]
    for theme in THEMES:
        families = manifest["themes"][theme]["families"]
        for family_name, family in families.items():
            for layer in family["layers"]:
                path = _manifest_path_to_disk(f"{family['layer_dir']}/{layer['file']}")
                assert path.is_file(), path
                if path.suffix == ".png":
                    w, h = _png_size(path)
                    assert [w, h] == [transient_w, transient_h], path
            for state in family["states"]:
                icon_path = _manifest_path_to_disk(f"{family['icon_dir']}/{state}.png")
                assert icon_path.is_file(), icon_path
                w, h = _png_size(icon_path)
                assert w <= transient_w and h <= transient_h, icon_path
            functional = family.get("functional_component")
            if functional:
                fc_path = _manifest_path_to_disk(f"{family['layer_dir']}/{functional}")
                assert fc_path.is_file(), fc_path


def test_v4_state_catalog_matches_families() -> None:
    manifest = _manifest()
    catalog = manifest["states"]
    assigned: set[str] = set()
    for theme in THEMES:
        for family in manifest["themes"][theme]["families"].values():
            assigned.update(family["states"])
    assert assigned == set(catalog)
    for state, meta in catalog.items():
        assert meta["family"] in {
            "battle",
            "timing",
            "position",
            "exception",
            "pit",
            "bio",
            "session",
            "sysinfo",
        }
        assert meta["tone"] in {"primary", "warning", "alert"}
        assert "lifecycle" in meta
        sample = meta.get("sample") or {}
        for slot in ("title", "subtitle", "value", "meta"):
            assert slot in sample, state


def test_v4_motion_reels_per_theme() -> None:
    manifest = _manifest()
    expected = sorted(f"{name}.webm" for name in manifest["motions"])
    for theme in THEMES:
        motion_dir = V4_ROOT / theme / "motion"
        found = sorted(p.name for p in motion_dir.iterdir() if p.suffix == ".webm")
        assert found == expected, theme


def test_v4_pack_size_budget() -> None:
    total = sum(p.stat().st_size for p in V4_ROOT.rglob("*") if p.is_file())
    assert total <= MAX_PACK_BYTES, total
    assert total >= 4 * 1024 * 1024  # sanity: production pack is not empty/tiny


def test_v4_tree_has_no_review_previews() -> None:
    leaked = [
        p
        for p in V4_ROOT.rglob("*")
        if p.is_file()
        and (
            p.suffix.lower() == ".mp4"
            or "golden_master" in p.name
            or "review_2x" in p.name
            or "composite_no_text" in p.name
        )
    ]
    assert leaked == []
    assert not list(V4_ROOT.glob("**/previews/**"))
