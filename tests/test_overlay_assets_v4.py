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
TRANSIENT_FAMILIES = ("battle", "timing", "position", "exception", "pit", "bio", "session")
FAMILY_DIRS = (*TRANSIENT_FAMILIES, "motion", "sysinfo")
STATE_COUNT = 35
MOTION_COUNT = 15


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
    assert manifest["manifest_schema"] == [2, 0]
    assert manifest["transient_canvas"] == [420, 140]
    assert manifest["sysinfo_canvas"] == [1920, 72]
    assert manifest["canvases"]["transient"]["size"] == [420, 140]
    assert manifest["canvases"]["transient"]["icon_mode"] == "full_canvas"
    assert manifest["canvases"]["sysinfo"]["size"] == [1920, 72]
    assert manifest["zones"]["battle"]["max"] == 2
    assert manifest["zones"]["event"]["max"] == 6
    assert "swipe_fade" in manifest["transitions"]
    assert set(manifest["themes"]) == set(THEMES)
    assert len(manifest["motions"]) == MOTION_COUNT
    assert len(manifest["states"]) == STATE_COUNT
    assert set(manifest["states"]) >= {
        "lap_complete",
        "hunting",
        "overtake",
        "pit_entry",
        "hr_pressure",
        "final_lap",
    }
    for theme in THEMES:
        families = manifest["themes"][theme]["families"]
        assert families["battle"]["zone"] == "battle"
        assert families["battle"]["canvas"] == "transient"
        assert families["timing"]["zone"] == "event"
        assert families["sysinfo"]["canvas"] == "sysinfo"
        assert "zone" not in families["sysinfo"]


def test_v4_themes_have_expected_family_dirs() -> None:
    themes = sorted(p.name for p in V4_ROOT.iterdir() if p.is_dir())
    assert themes == sorted(THEMES)
    for theme in THEMES:
        for family in FAMILY_DIRS:
            assert (V4_ROOT / theme / family).is_dir(), f"{theme}/{family}"
        for family in TRANSIENT_FAMILIES:
            assert (V4_ROOT / theme / family / "layers").is_dir(), f"{theme}/{family}"
            assert (V4_ROOT / theme / family / "icons").is_dir(), f"{theme}/{family}"


def test_v4_sysinfo_keeps_its_own_canvas() -> None:
    manifest = _manifest()
    for theme in THEMES:
        sysinfo = V4_ROOT / theme / "sysinfo"
        for layer in (sysinfo / "layers").glob("*.png"):
            assert list(_png_size(layer)) == manifest["sysinfo_canvas"], layer
        icons = sorted((sysinfo / "icons").glob("*.png"))
        assert icons
        for icon in icons:
            width, height = _png_size(icon)
            assert height == manifest["sysinfo_canvas"][1], icon
            assert width < manifest["sysinfo_canvas"][0], icon


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
    sysinfo_w, sysinfo_h = manifest["sysinfo_canvas"]
    for theme in THEMES:
        families = manifest["themes"][theme]["families"]
        for family_name, family in families.items():
            for layer in family["layers"]:
                path = _manifest_path_to_disk(f"{family['layer_dir']}/{layer['file']}")
                assert path.is_file(), path
                if path.suffix == ".png":
                    w, h = _png_size(path)
                    expected = (
                        [sysinfo_w, sysinfo_h]
                        if family_name == "sysinfo"
                        else [transient_w, transient_h]
                    )
                    assert [w, h] == expected, path
            for state in family.get("states", ()):
                icon_path = _manifest_path_to_disk(f"{family['icon_dir']}/{state}.png")
                assert icon_path.is_file(), icon_path
                w, h = _png_size(icon_path)
                assert w <= transient_w and h <= transient_h, icon_path
            functional = family.get("functional_component")
            if functional:
                fc_path = _manifest_path_to_disk(f"{family['layer_dir']}/{functional}")
                assert fc_path.is_file(), fc_path


def test_v4_sysinfo_dividers_match_css_module_grid() -> None:
    """V4 divider mask must land on the 230 + 11×150 CSS module edges (V3 grid)."""
    from test_overlay_assets_v3 import _png_rgba

    expected = [230 + 150 * i for i in range(11)]
    for theme in THEMES:
        path = V4_ROOT / theme / "sysinfo" / "layers" / "sysinfo_dividers_mask.png"
        width, height, pixels = _png_rgba(path)
        assert (width, height) == (1920, 72), path
        col_max = [0] * width
        for y in range(height):
            row = pixels[y * width * 4 : (y + 1) * width * 4]
            for x in range(width):
                a = row[x * 4 + 3]
                if a > col_max[x]:
                    col_max[x] = a
        xs = [x for x, a in enumerate(col_max) if a > 80]
        assert xs, theme
        clusters: list[float] = []
        start = prev = xs[0]
        for x in xs[1:]:
            if x - prev > 3:
                clusters.append((start + prev) / 2.0)
                start = x
            prev = x
        clusters.append((start + prev) / 2.0)
        assert len(clusters) == len(expected), (theme, clusters)
        for got, want in zip(clusters, expected, strict=True):
            assert abs(got - want) <= 1.5, f"{theme}: divider {got} vs {want}"


def test_v4_sysinfo_manifest_family_matches_layers() -> None:
    manifest = _manifest()
    sysinfo_w, sysinfo_h = manifest["sysinfo_canvas"]
    expected_icons = {
        "ble.png",
        "cpu.png",
        "fps.png",
        "frametime.png",
        "gpu.png",
        "heart.png",
        "power.png",
        "ram.png",
        "temp.png",
        "vram.png",
    }
    for theme in THEMES:
        family = manifest["themes"][theme]["families"]["sysinfo"]
        layer_dir = V4_ROOT / theme / "sysinfo" / "layers"
        icon_dir = V4_ROOT / theme / "sysinfo" / "icons"
        manifest_files = {layer["file"] for layer in family["layers"]}
        disk_files = {p.name for p in layer_dir.glob("*.png")}
        assert manifest_files == disk_files, theme
        assert family["functional_component"] == "sysinfo_module_segments.png"
        assert {p.name for p in icon_dir.glob("*.png")} == expected_icons, theme
        for layer in family["layers"]:
            path = _manifest_path_to_disk(f"{family['layer_dir']}/{layer['file']}")
            assert path.is_file(), path
            assert list(_png_size(path)) == [sysinfo_w, sysinfo_h], path


def test_v4_state_catalog_matches_families() -> None:
    manifest = _manifest()
    catalog = manifest["states"]
    assigned: set[str] = set()
    for theme in THEMES:
        for family in manifest["themes"][theme]["families"].values():
            assigned.update(family.get("states", ()))
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
        assert len(found) == MOTION_COUNT, theme


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
