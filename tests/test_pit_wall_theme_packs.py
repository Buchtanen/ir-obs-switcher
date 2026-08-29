from __future__ import annotations

import hashlib
import json
import re
import shutil
import struct
import subprocess
import zipfile
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PACKS_ROOT = REPO / "assets" / "overlay" / "themes"
V4_MANIFEST = REPO / "src" / "irswitch" / "web" / "themes-v4" / "manifest.json"
V4_CATALOG = REPO / "src" / "irswitch" / "web" / "themes-v4" / "event_catalog.json"

HAS_FFPROBE = shutil.which("ffprobe") is not None
HAS_FFMPEG = shutil.which("ffmpeg") is not None

THEMES = {
    "pit_wall_dark": {
        "prefix": "pw",
        "theme_id": "pitwall_race_control",
        "icon_box": [54, 50, 40, 40],
        "raster_1x": "04_Pitwall_Transient_Raster_1x.zip",
        "raster_2x": "05_Pitwall_Transient_Raster_2x.zip",
        "motion": "10_Pitwall_Motion_Alpha_VP9.zip",
    },
    "pit_wall_light": {
        "prefix": "pl",
        "theme_id": "pitwall_light",
        "icon_box": [39, 46, 48, 48],
        "raster_1x": "04_Pitwall_Light_Transient_Raster_1x.zip",
        "raster_2x": "05_Pitwall_Light_Transient_Raster_2x.zip",
        "motion": "10_Pitwall_Light_Motion_Alpha_VP9.zip",
    },
}

RUNTIME_DIVIDERS = [230 + (150 * index) for index in range(12)]


def _load(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _png_header(data: bytes) -> tuple[int, int, int]:
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    assert data[12:16] == b"IHDR"
    width, height, _depth, color_type = struct.unpack(">IIBB", data[16:26])
    return width, height, color_type


def _ffprobe(path: Path) -> dict[str, object]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height,pix_fmt,r_frame_rate:stream_tags=alpha_mode:format=duration",
            "-of",
            "json",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def _decoded_alpha(path: Path) -> bytes:
    result = subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-c:v",
            "libvpx-vp9",
            "-i",
            str(path),
            "-vf",
            "alphaextract",
            "-pix_fmt",
            "gray",
            "-f",
            "rawvideo",
            "-",
        ],
        check=True,
        capture_output=True,
    )
    return result.stdout


def _webm_has_alpha_mode_tag(data: bytes) -> bool:
    """Best-effort Matroska tag scan without ffprobe (Windows CI has no ffmpeg)."""
    return b"ALPHA_MODE" in data and b"\x01" in data


def _webm_pixel_size(data: bytes) -> tuple[int, int] | None:
    """Read EBML PixelWidth (0xB0) / PixelHeight (0xBA) when present as uint."""
    width = height = None
    i = 0
    while i < len(data) - 4:
        if data[i] == 0xB0 and data[i + 1] in (0x81, 0x82):
            size = data[i + 1] & 0x7F
            value = int.from_bytes(data[i + 2 : i + 2 + size], "big")
            width = value
            i += 2 + size
            continue
        if data[i] == 0xBA and data[i + 1] in (0x81, 0x82):
            size = data[i + 1] & 0x7F
            value = int.from_bytes(data[i + 2 : i + 2 + size], "big")
            height = value
            i += 2 + size
            continue
        i += 1
        if width is not None and height is not None:
            break
    if width is None or height is None:
        return None
    return width, height


@pytest.mark.parametrize("theme_name", THEMES)
def test_event_visual_map_covers_v4_states_and_events(theme_name: str) -> None:
    root = PACKS_ROOT / theme_name
    visual_map = _load(root / "accents" / "event-visual-map.json")
    v4_manifest = _load(V4_MANIFEST)
    v4_catalog = _load(V4_CATALOG)

    assert visual_map["schemaVersion"] == 2
    assert visual_map["themeId"] == THEMES[theme_name]["theme_id"]
    assert set(visual_map["states"]) == set(v4_manifest["states"])
    assert len(visual_map["states"]) == 35
    assert set(visual_map["events"]) == set(v4_catalog["entries"])
    assert len(visual_map["events"]) == 35
    assert visual_map["fallbacks"] == v4_catalog["fallbacks"]

    for state_name, state in visual_map["states"].items():
        assert state["template"] in visual_map["templates"], state_name
        assert state["tone"] in visual_map["tones"], state_name
        assert state["rail"], state_name
        assert state["railLayers"], state_name
        for rail_layer in state["railLayers"]:
            assert (root / rail_layer).is_file(), (state_name, rail_layer)
        assert state["reuseNote"], state_name
        icon = root / state["icon"]
        assert icon.is_file(), (state_name, icon)

    for event_name, route in visual_map["events"].items():
        assert route["state"] in visual_map["states"], event_name
        if "icon" in route:
            assert (root / route["icon"]).is_file(), event_name

    assert visual_map["zones"]["BATTLE_AHEAD"]["layout"] == "BATTLE"
    assert visual_map["zones"]["BATTLE_BEHIND"]["layout"] == "BATTLE"
    assert visual_map["zones"]["BATTLE_AHEAD"]["template"] == "battle"
    assert visual_map["zones"]["BATTLE_BEHIND"]["template"] == "battle"

    icon_policy = visual_map["iconPolicy"]
    assert icon_policy["coverageContract"] == "state-map-exact"
    assert icon_policy["requiredStateGlyphCount"] == 35
    assert len(icon_policy["stateGlyphs"]) == 35
    assert set(icon_policy["stateGlyphs"]) == {
        state["icon"] for state in visual_map["states"].values()
    }
    assert set(icon_policy["eventOverrideGlyphs"]) == {
        route["icon"] for route in visual_map["events"].values() if "icon" in route
    }
    assert icon_policy["crossThemeUtilityNameParityRequired"] is False
    assert not (set(icon_policy["utilityLibrary"]) & set(icon_policy["stateGlyphs"]))

    resolution = visual_map["rendererPolicy"]["templateResolution"]
    assert resolution["runtimeFamilyMayOverride"] is False
    assert resolution["precedence"] == [
        "events.<event>.template",
        "states.<state>.template",
        "fallbacks.<family>",
    ]
    assert visual_map["states"]["position_attack"]["template"] == "position"
    assert resolution["knownRuntimeFamilyExceptions"] == [
        {
            "state": "position_attack",
            "runtimeFamily": "timing",
            "packTemplate": "position",
        }
    ]


@pytest.mark.parametrize("theme_name", THEMES)
def test_templates_and_icons_use_declared_native_geometry(theme_name: str) -> None:
    root = PACKS_ROOT / theme_name
    visual_map = _load(root / "accents" / "event-visual-map.json")
    tokens = _load(root / "theme-tokens.json")

    assert visual_map["contract"]["transient"] == [420, 140]
    assert visual_map["contract"]["icon"] == [64, 64]
    assert visual_map["contract"]["iconBox"] == THEMES[theme_name]["icon_box"]
    assert tokens["geometry"]["iconBox"] == THEMES[theme_name]["icon_box"]

    for template_name, template in visual_map["templates"].items():
        assert template["canvas"] == [420, 140]
        assert template["layers"], template_name
        for layer in template["layers"]:
            layer_path = root / layer
            assert layer_path.is_file(), (template_name, layer_path)
            svg = layer_path.read_text(encoding="utf-8")
            assert 'viewBox="0 0 420 140"' in svg

    for icon in (root / "icons" / "event").glob("*.svg"):
        svg = icon.read_text(encoding="utf-8")
        if icon.name.endswith("-sprite.svg"):
            continue
        assert 'width="64"' in svg, icon
        assert 'height="64"' in svg, icon
        assert 'viewBox="0 0 64 64"' in svg, icon


@pytest.mark.parametrize("theme_name", THEMES)
def test_sysinfo_grid_matches_runtime_contract(theme_name: str) -> None:
    root = PACKS_ROOT / theme_name
    prefix = THEMES[theme_name]["prefix"]
    tokens = _load(root / "theme-tokens.json")
    divider_svg = (root / "icons" / "sysinfo" / f"{prefix}-sysinfo-dividers.svg").read_text(
        encoding="utf-8"
    )

    grid = tokens["geometry"]["sysinfo"]["grid"]
    assert grid == {
        "brandWidth": 230,
        "moduleWidth": 150,
        "moduleCount": 11,
        "positions": RUNTIME_DIVIDERS,
        "dataEndX": 1880,
        "trailingSafeWidth": 40,
    }
    positions = [int(value) for value in re.findall(r'<path d="M(\d+) ', divider_svg)]
    assert positions == RUNTIME_DIVIDERS


@pytest.mark.parametrize("theme_name", THEMES)
def test_new_family_rasters_are_individual_alpha_assets(theme_name: str) -> None:
    root = PACKS_ROOT / theme_name
    visual_map = _load(root / "accents" / "event-visual-map.json")

    for scale, expected, archive_key in (
        ("1x", (420, 140), "raster_1x"),
        ("2x", (840, 280), "raster_2x"),
    ):
        archive = root / "packages" / THEMES[theme_name][archive_key]
        with zipfile.ZipFile(archive) as zf:
            names = set(zf.namelist())
            for family in ("pit", "exception"):
                for layer in visual_map["templates"][family]["layers"]:
                    png_name = Path(layer).with_suffix(".png").name
                    matches = [
                        name
                        for name in names
                        if f"/raster/png/{scale}/templates/{family}/" in name
                        and name.endswith(png_name)
                    ]
                    assert len(matches) == 1, (archive.name, family, png_name)
                    width, height, color_type = _png_header(zf.read(matches[0]))
                    assert (width, height) == expected
                    assert color_type in {4, 6}, matches[0]


@pytest.mark.parametrize("theme_name", THEMES)
def test_motion_reels_and_pack_manifests_are_self_consistent(theme_name: str) -> None:
    root = PACKS_ROOT / theme_name
    motion = _load(root / "motion" / "manifest.json")
    manifest = _load(root / "manifest.json")
    archive_index = _load(root / "packages" / "archive-index.json")
    source_manifest = _load(root / "references" / "source-asset-manifest.json")

    expected_reels = set(_load(V4_MANIFEST)["motions"])
    assert len(expected_reels) == 15
    assert motion["pipeline"] == "alpha-vp9"
    assert motion["fallback"] == "css"
    assert set(motion["webm"]) == expected_reels
    assert set(motion["reels"]) == expected_reels
    assert set(motion["intents"]) >= {
        "enter",
        "active",
        "result",
        "exit",
        "pit-phase",
        "exception-alert",
        "session-sweep",
    }

    reel_hashes = set()
    for reel_name in sorted(expected_reels):
        reel = motion["reels"][reel_name]
        assert reel["file"] == f"{reel_name}.webm"
        assert reel["canvas"] == "transient"
        assert reel["fps"] == 30
        assert reel["alpha"] is True
        assert 0 < reel["durationMs"] <= 500
        assert reel["intent"]

        reel_path = root / "motion" / reel["file"]
        assert reel_path.is_file()
        reel_bytes = reel_path.read_bytes()
        assert len(reel_bytes) > 1000
        reel_hashes.add(hashlib.sha256(reel_bytes).hexdigest())
        # Geometry / alpha: prefer ffprobe+ffmpeg when present; otherwise EBML/tag scan
        # so Windows CI (no ffmpeg tools) still validates the pack contract.
        if HAS_FFPROBE:
            probe = _ffprobe(reel_path)
            stream = probe["streams"][0]
            assert stream["codec_name"] == "vp9"
            assert (stream["width"], stream["height"]) == (420, 140)
            assert stream["pix_fmt"] == "yuv420p"
            assert stream["r_frame_rate"] == "30/1"
            assert stream["tags"]["ALPHA_MODE"] == "1"
            duration_ms = round(float(probe["format"]["duration"]) * 1000)
            assert abs(duration_ms - reel["durationMs"]) <= 2
        else:
            size = _webm_pixel_size(reel_bytes)
            assert size == (420, 140), (reel_name, size)
            assert _webm_has_alpha_mode_tag(reel_bytes), reel_name
        if HAS_FFMPEG:
            alpha = _decoded_alpha(reel_path)
            assert alpha
            assert max(alpha) > 0, f"empty alpha reel: {reel_name}"
            assert min(alpha) == 0, f"full-bleed alpha reel: {reel_name}"
    assert len(reel_hashes) == 15

    with zipfile.ZipFile(root / "packages" / THEMES[theme_name]["motion"]) as zf:
        names = set(zf.namelist())
        for reel_name in expected_reels:
            assert any(name.endswith(f"/assets/motion/{reel_name}.webm") for name in names)
        assert any(name.endswith("/assets/motion/manifest.json") for name in names)

    assert manifest["renderer_contract"]["event_visual_map"] == ("accents/event-visual-map.json")
    assert manifest["renderer_contract"]["theme_tokens"] == "theme-tokens.json"
    assert manifest["renderer_contract"]["motion"] == "motion/manifest.json"

    recorded = {entry["path"]: entry for entry in manifest["files"]}
    actual = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file() and path != root / "manifest.json"
    }
    assert set(recorded) == actual
    for relative, entry in recorded.items():
        path = root / relative
        assert path.is_file(), relative
        data = path.read_bytes()
        # Windows CI may check out text files as CRLF; normalize before size/hash.
        if path.suffix.lower() in {".md", ".txt", ".json", ".css", ".html", ".svg"}:
            data = data.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        assert entry["bytes"] == len(data), relative
        assert entry["sha256"] == hashlib.sha256(data).hexdigest(), relative

    assert source_manifest["assetCount"] == len(source_manifest["assets"])
    source_paths = {entry["path"] for entry in source_manifest["assets"]}
    assert "tokens/event-visual-map.json" in source_paths
    assert "tokens/design-tokens.json" in source_paths
    assert any("assets/vector/templates/pit/" in path for path in source_paths)
    assert any("assets/vector/templates/exception/" in path for path in source_paths)
    for reel_name in expected_reels:
        assert f"assets/motion/{reel_name}.webm" in source_paths

    for archive_entry in archive_index["archives"]:
        archive = root / "packages" / archive_entry["file"]
        assert archive_entry["bytes"] == archive.stat().st_size
        assert archive_entry["sha256"] == hashlib.sha256(archive.read_bytes()).hexdigest()
        with zipfile.ZipFile(archive) as zf:
            assert zf.testzip() is None
            assert archive_entry["files"] == sum(not name.endswith("/") for name in zf.namelist())


def test_dark_and_light_motion_reels_are_theme_specific() -> None:
    dark = PACKS_ROOT / "pit_wall_dark" / "motion"
    light = PACKS_ROOT / "pit_wall_light" / "motion"
    expected_reels = set(_load(V4_MANIFEST)["motions"])
    for reel_name in expected_reels:
        dark_hash = hashlib.sha256((dark / f"{reel_name}.webm").read_bytes()).hexdigest()
        light_hash = hashlib.sha256((light / f"{reel_name}.webm").read_bytes()).hexdigest()
        assert dark_hash != light_hash, reel_name
