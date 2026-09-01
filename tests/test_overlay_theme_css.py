"""Runtime theme CSS must exist for every overlay.theme choice.

``applyTheme()`` in overlay.js sets ``#theme-css`` to
``/overlay/static/css/themes/${id}.css``. A missing file 404s and drops
``--primary`` / ``--panel-fill`` (Pit Wall Light/Dark looked unfinished).
Golden/manifest tests listed the theme ids but never asserted these files.
"""

from __future__ import annotations

import re
from pathlib import Path

from irswitch.overlay.http import web_root
from irswitch.overlay.schema import OVERLAY_FIELDS

THEME_CSS_DIR = web_root() / "overlay" / "css" / "themes"
REQUIRED_VARS = (
    "--panel-fill",
    "--border",
    "--primary",
    "--warning",
    "--alert",
    "--text-primary",
    "--text-muted",
    "--glow",
    "--divider",
)


def _theme_choices() -> tuple[str, ...]:
    field = next(item for item in OVERLAY_FIELDS if item.key == "overlay.theme")
    assert field.choices, "overlay.theme must declare choices"
    return field.choices


def test_every_overlay_theme_ships_css() -> None:
    missing: list[str] = []
    for theme in _theme_choices():
        path = THEME_CSS_DIR / f"{theme}.css"
        if not path.is_file():
            missing.append(str(path.relative_to(web_root())))
            continue
        text = path.read_text(encoding="utf-8")
        absent = [var for var in REQUIRED_VARS if var not in text]
        assert not absent, f"{path.name} missing tokens {absent}"
    assert (
        not missing
    ), "applyTheme 404s without these files (Pit Wall Light/Dark regression): " + ", ".join(missing)


def test_apply_theme_loads_schema_css_path() -> None:
    overlay_js = (web_root() / "overlay" / "js" / "overlay.js").read_text(encoding="utf-8")
    assert "function applyTheme(theme)" in overlay_js
    assert "/overlay/static/css/themes/${id}.css?v=${OVERLAY_ASSET_VER}" in overlay_js
    for theme in _theme_choices():
        assert (THEME_CSS_DIR / f"{theme}.css").is_file(), theme


def test_pit_wall_light_css_uses_pack_tokens() -> None:
    text = (THEME_CSS_DIR / "pit_wall_light.css").read_text(encoding="utf-8").lower()
    assert "#1b72ff" in text
    assert "#101b2c" in text
    assert "#ef9e20" in text
    assert "#e84c56" in text


def test_pit_wall_dark_css_uses_pack_tokens() -> None:
    text = (THEME_CSS_DIR / "pit_wall_dark.css").read_text(encoding="utf-8").lower()
    assert "#35d7ff" in text
    assert "#eaf3f7" in text
    assert "#f4a62a" in text
    assert "#ff4e5b" in text


def _png_max_alpha(path: Path) -> int:
    from test_overlay_assets_v3 import _png_rgba

    _w, _h, pixels = _png_rgba(path)
    return max(pixels[i] for i in range(3, len(pixels), 4)) if pixels else 0


def test_pit_wall_light_icon_well_is_not_a_transparent_stub() -> None:
    """Light pack ships icon-well rasters; ingest must not replace them with empty stubs."""
    hunting = (
        web_root()
        / "themes-v4"
        / "pit_wall_light"
        / "plates"
        / "hunting"
        / "layers"
        / "icon_well.png"
    )
    assert hunting.is_file(), hunting
    assert _png_max_alpha(hunting) > 32, hunting


def test_overlay_js_theme_css_dir_matches_disk() -> None:
    """Guard the string overlay.js interpolates — not a parallel CSS tree."""
    overlay_js = (web_root() / "overlay" / "js" / "overlay.js").read_text(encoding="utf-8")
    match = re.search(r"/overlay/static/css/themes/\$\{id\}\.css", overlay_js)
    assert match, "applyTheme href pattern missing"
    assert THEME_CSS_DIR.is_dir()


def test_ingest_check_rejects_stub_light_icon_well() -> None:
    import subprocess
    import sys

    repo = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [
            sys.executable,
            str(repo / "scripts" / "ingest_pit_wall_themes_v4.py"),
            "--check",
            "--theme",
            "pit_wall_light",
        ],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
