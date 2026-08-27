"""Shipped overlay theme pack: filenames, geometry, manifest wiring."""

from __future__ import annotations

import json
import re
import struct
import zlib
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
    assert "#bio-compact.has-art" in css
    assert "filter: drop-shadow" not in css
    assert ".widget.has-art.lap" in css
    assert ".widget.has-art.lap .widget-art" not in css


def _png_rgba(path: Path) -> tuple[int, int, bytes]:
    data = path.read_bytes()
    assert data[:8] == PNG_SIGNATURE
    pos = 8
    width = height = bit_depth = color_type = interlace = None
    idat = bytearray()
    while pos < len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        ctype = data[pos + 4 : pos + 8]
        chunk = data[pos + 8 : pos + 8 + length]
        pos += 12 + length
        if ctype == b"IHDR":
            width, height, bit_depth, color_type, _comp, _filt, interlace = struct.unpack(
                ">IIBBBBB", chunk
            )
        elif ctype == b"IDAT":
            idat.extend(chunk)
        elif ctype == b"IEND":
            break
    assert width and height and bit_depth == 8 and color_type == 6 and interlace == 0
    raw = zlib.decompress(bytes(idat))
    bpp = 4
    stride = width * bpp
    prev = bytearray(stride)
    pixels = bytearray()
    i = 0

    def paeth(a: int, b: int, c: int) -> int:
        p = a + b - c
        pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
        if pa <= pb and pa <= pc:
            return a
        if pb <= pc:
            return b
        return c

    for _ in range(height):
        ftype = raw[i]
        i += 1
        filt = raw[i : i + stride]
        i += stride
        recon = bytearray(stride)
        for x, up in enumerate(filt):
            left = recon[x - bpp] if x >= bpp else 0
            up_px = prev[x]
            ul = prev[x - bpp] if x >= bpp else 0
            if ftype == 0:
                recon[x] = up
            elif ftype == 1:
                recon[x] = (up + left) & 255
            elif ftype == 2:
                recon[x] = (up + up_px) & 255
            elif ftype == 3:
                recon[x] = (up + ((left + up_px) // 2)) & 255
            elif ftype == 4:
                recon[x] = (up + paeth(left, up_px, ul)) & 255
            else:
                raise AssertionError(ftype)
        pixels.extend(recon)
        prev = recon
    return width, height, bytes(pixels)


def _cloth_fill_ratio(path: Path) -> float:
    width, height, pixels = _png_rgba(path)
    opaque = 0
    span = 0
    for y in range(height):
        row = pixels[y * width * 4 : (y + 1) * width * 4]
        xs = [x for x in range(width) if row[x * 4 + 3] > 40]
        if len(xs) < 8:
            continue
        left, right = min(xs) + 2, max(xs)
        if right <= left:
            continue
        for x in range(left, right):
            span += 1
            if row[x * 4 + 3] > 200:
                opaque += 1
    assert span > 0, path
    return opaque / span


def test_final_lap_flag_is_solid_white_not_checkered() -> None:
    for theme in THEMES:
        assets = web_root() / "themes" / theme / "assets"
        final = _cloth_fill_ratio(assets / "final_lap_flag.png")
        finish = _cloth_fill_ratio(assets / "finish_flag.png")
        assert final >= 0.92, (theme, final)
        assert finish <= 0.72, (theme, finish)
        assert final - finish >= 0.2, (theme, final, finish)


def test_overlay_js_reuses_glow_and_paints_final_lap_white() -> None:
    js = (web_root() / "overlay" / "js" / "display.js").read_text(encoding="utf-8")
    html = (web_root() / "overlay" / "index.html").read_text(encoding="utf-8")
    art = js.split("function artSlots(event)", 1)[1].split("export function applyPersistentArt", 1)[
        0
    ]
    final = art.split('if (name === "final_lap")', 1)[1].split("if (name ===", 1)[0]
    finish = art.split('if (name === "finish")', 1)[1].split("if (name ===", 1)[0]
    assert "final_lap_flag" in final and "iconMask: false" in final
    assert 'glow: "battle_glow"' in final
    assert "finish_flag" in finish and "iconMask: true" in finish
    for name in ("lap_complete", "personal_best", "heart_rate"):
        block = art.split(f'if (name === "{name}")', 1)[1].split("if (name ===", 1)[0]
        assert 'glow: "battle_glow"' in block, name
    assert 'data-slot="battle_glow"' in html
    assert 'explicit ? Boolean(slots[maskKey]) : name === "icon"' in js
