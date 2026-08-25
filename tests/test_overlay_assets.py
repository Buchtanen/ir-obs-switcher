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
BANNED_SVG_TEXT = (
    "HUNTING",
    "HUNTED",
    "BPM",
    "FINAL LAP",
    "PERSONAL BEST",
    "CHECKERED",
    "CLOSING IN",
)
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _manifest() -> dict:
    path = web_root() / "themes" / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_theme_pack_file_parity() -> None:
    names: dict[str, list[str]] = {}
    for theme in THEMES:
        files = sorted(
            p.name for p in (web_root() / "themes" / theme / "assets").iterdir() if p.is_file()
        )
        assert len(files) == 37, theme
        for name in files:
            stem = Path(name).stem
            suffix = Path(name).suffix
            assert " " not in name
            assert name == name.lower()
            assert SNAKE_STEM.fullmatch(stem), name
            assert suffix in {".svg", ".png"}, name
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
        assert [width, height] == [840, 280]
        assert data[25] in {4, 6}  # greyscale+alpha or RGBA


def test_svg_geometry_and_no_baked_copy() -> None:
    expected = {Path(name).stem: size for name, size in _manifest()["assets"].items()}
    viewbox = re.compile(r'viewBox="0 0 (\d+) (\d+)"')
    for theme in THEMES:
        for svg in (web_root() / "themes" / theme / "assets").glob("*.svg"):
            text = svg.read_text(encoding="utf-8")
            assert "<text" not in text.lower()
            for token in BANNED_SVG_TEXT:
                assert token not in text, f"{svg}: {token}"
            match = viewbox.search(text)
            assert match, svg
            size = [int(match.group(1)), int(match.group(2))]
            assert size == expected[svg.stem], svg


def test_presentation_payload_default_theme() -> None:
    payload = presentation_payload()
    assert payload["theme"] == "cyber_racing"
    assert (
        payload["assets"]["battle_background"] == "themes/cyber_racing/assets/battle_background.svg"
    )
    assert payload["assets"]["battle_glow"] == "themes/cyber_racing/assets/battle_glow.png"
    assert all(payload["assets"][slot] for slot in ASSET_SLOTS)
