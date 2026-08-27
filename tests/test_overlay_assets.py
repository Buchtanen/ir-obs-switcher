"""Shipped overlay theme pack: filenames, geometry, manifest wiring."""

from __future__ import annotations

import json
import re
import struct
from pathlib import Path

from irswitch.overlay.display import ASSET_SLOTS, AssetManifest
from irswitch.overlay.http import presentation_payload, web_root

THEMES = ("cyber_racing", "stealth_graphite", "night_attack")
SNAKE_STEM = re.compile(r"^[a-z0-9_]+$")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
WEBM_FILES = (
    "battle_radar_loop.webm",
    "battle_scan_enter.webm",
    "finish_accent_sweep.webm",
)


def _manifest() -> dict:
    path = web_root() / "themes" / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_theme_pack_file_parity() -> None:
    names: dict[str, list[str]] = {}
    for theme in THEMES:
        files = sorted(
            p.name for p in (web_root() / "themes" / theme / "assets").iterdir() if p.is_file()
        )
        png = [name for name in files if name.endswith(".png")]
        webm = [name for name in files if name.endswith(".webm")]
        assert len(png) == 37, theme
        assert webm == sorted(WEBM_FILES), theme
        for name in files:
            stem = Path(name).stem
            suffix = Path(name).suffix
            assert " " not in name
            assert name == name.lower()
            assert SNAKE_STEM.fullmatch(stem), name
            assert suffix in {".png", ".webm"}, name
        names[theme] = files
    assert names["cyber_racing"] == names["stealth_graphite"] == names["night_attack"]


def test_asset_slots_resolve_and_glow_has_alpha() -> None:
    for theme in THEMES:
        manifest = AssetManifest(theme, web_root())
        resolved = manifest.to_dict()["assets"]
        assert set(resolved) == set(ASSET_SLOTS)
        for slot, rel in resolved.items():
            assert rel, f"{theme}/{slot}"
            path = web_root() / rel
            assert path.is_file(), path
        glow = web_root() / resolved["battle_glow"]
        data = glow.read_bytes()
        assert data[:8] == PNG_SIGNATURE
        width, height = struct.unpack(">II", data[16:24])
        assert [width, height] == [420, 140]
        assert data[25] in {4, 6}  # greyscale+alpha or RGBA
        assert resolved["battle_radar_loop"].endswith(".webm")
        assert resolved["finish_accent_sweep"].endswith(".webm")


def test_png_geometry_matches_manifest() -> None:
    expected = {Path(name).stem: size for name, size in _manifest()["assets"].items()}
    for theme in THEMES:
        assert not list((web_root() / "themes" / theme / "assets").glob("*.svg"))
        for png in (web_root() / "themes" / theme / "assets").glob("*.png"):
            data = png.read_bytes()
            assert data[:8] == PNG_SIGNATURE, png
            width, height = struct.unpack(">II", data[16:24])
            assert [width, height] == expected[png.stem], png


def test_resolve_prefers_png_then_svg_fallback(tmp_path: Path) -> None:
    assets = tmp_path / "themes" / "cyber_racing" / "assets"
    assets.mkdir(parents=True)
    (assets / "heart_icon.svg").write_text("<svg/>")
    manifest = AssetManifest("cyber_racing", tmp_path)
    assert manifest.resolve("heart_icon") == "themes/cyber_racing/assets/heart_icon.svg"
    (assets / "heart_icon.png").write_bytes(b"x")
    assert manifest.resolve("heart_icon") == "themes/cyber_racing/assets/heart_icon.png"


def test_presentation_payload_default_theme() -> None:
    payload = presentation_payload()
    assert payload["theme"] == "cyber_racing"
    assert (
        payload["assets"]["battle_background"] == "themes/cyber_racing/assets/battle_background.png"
    )
    assert payload["assets"]["battle_glow"] == "themes/cyber_racing/assets/battle_glow.png"
    assert payload["assets"]["battle_scan_enter"].endswith("battle_scan_enter.webm")
    assert all(payload["assets"][slot] for slot in ASSET_SLOTS)


def test_overlay_css_plate_fill_is_fallback_only() -> None:
    css = (web_root() / "overlay" / "css" / "overlay.css").read_text(encoding="utf-8")
    assert ".widget.fallback" in css
    assert "#sysinfo-widget.fallback" in css
    assert "html.is-demo" in css
    assert "bottom: 91px" in css
