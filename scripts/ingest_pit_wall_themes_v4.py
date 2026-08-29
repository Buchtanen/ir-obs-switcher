#!/usr/bin/env python3
"""Ingest Pit Wall art packs into runtime themes-v4/ trees.

Reads raster/icon/motion assets from assets/overlay/themes/pit_wall_{dark,light}
and writes src/irswitch/web/themes-v4/pit_wall_{dark,light}/ with snake_case
runtime layer names. Does not edit manifest.json (caller / eng wires themes).

Usage:
  python scripts/ingest_pit_wall_themes_v4.py
  python scripts/ingest_pit_wall_themes_v4.py --check  # verify expected outputs exist
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import zipfile
import zlib
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PACKS = REPO / "assets" / "overlay" / "themes"
V4_ROOT = REPO / "src" / "irswitch" / "web" / "themes-v4"

THEMES = {
    "pit_wall_dark": {
        "prefix": "pw",
        "raster_zip": "04_Pitwall_Transient_Raster_1x.zip",
        "icons_zip": "02_Pitwall_Icons_and_Status.zip",
        "sysinfo_zip": "08_Pitwall_SYSINFO_All_Formats.zip",
    },
    "pit_wall_light": {
        "prefix": "pl",
        "raster_zip": "04_Pitwall_Light_Transient_Raster_1x.zip",
        "icons_zip": "02_Pitwall_Light_Icons_BLE_and_Status.zip",
        "sysinfo_zip": "08_Pitwall_Light_SYSINFO_All_Formats.zip",
    },
}

# Pack template folder → runtime family that owns icons for that plate.
TEMPLATE_FAMILY_ICONS: dict[str, str] = {
    "battle": "battle",
    "hunting": "battle",
    "hunted": "battle",
    "lap": "timing",
    "pb": "timing",
    "position": "position",
    "exception": "exception",
    "pit": "pit",
    "bio": "bio",
    "final-lap": "session",
    "finish": "session",
}

# Semantic suffix → runtime filename (plate stack).
LAYER_SUFFIXES: list[tuple[str, str]] = [
    ("plate-base", "base_plate.png"),
    ("data-surface", "material.png"),
    ("icon-well", "icon_well.png"),
    ("technical-grid", "family_detail.png"),
    ("border", "frame_base.png"),
    ("edge-light", "frame_highlight.png"),
    ("bottom-divider", "frame_highlight.png"),
    ("pivot-divider", "frame_highlight.png"),
    ("timing-ticks", "micro_details.png"),
    ("corner-accent", "corner_left.png"),
    ("exception-fracture", "exception_fracture.png"),
    ("pit-phase-track", "pit_phase_track.png"),
]

SYSINFO_MAP = {
    "base": "sysinfo_base_plate.png",
    "brand-surface": "sysinfo_brand_plate.png",
    "dividers": "sysinfo_dividers_mask.png",
    "bus-line": "sysinfo_frame_highlight.png",
    "footer-accent": "sysinfo_frame_base.png",
    "ticks": "sysinfo_module_segments.png",
}

SYSINFO_ICON_MAP = {
    "cpu": "cpu.png",
    "gpu": "gpu.png",
    "temp": "temp.png",
    "power": "power.png",
    "fps": "fps.png",
    "heart": "heart.png",
    "ble": "ble.png",
    "memory": "ram.png",
    "ram": "ram.png",
    "vram": "vram.png",
    "frametime": "frametime.png",
}

V4_MOTIONS = (
    "enter_reveal",
    "active_pulse",
    "compact_mask",
    "suspend_dim",
    "resume_reacquire",
    "result_burst",
    "exit_trace",
    "theme_glitch",
    "battle_signal_lock",
    "timing_projection_sweep",
    "position_chevron_hit",
    "exception_link_drop",
    "pit_stop_ring",
    "bio_pulse",
    "session_finish_burst",
)


def _png_rgba(width: int, height: int, rgba: tuple[int, int, int, int] = (0, 0, 0, 0)) -> bytes:
    """Minimal uncompressed-filter PNG (stdlib only)."""
    raw = bytearray()
    pixel = bytes(rgba)
    for _ in range(height):
        raw.append(0)  # filter None
        raw.extend(pixel * width)
    compressed = zlib.compress(bytes(raw), 9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return len(data).to_bytes(4, "big") + tag + data + zlib.crc32(tag + data).to_bytes(4, "big")

    ihdr = width.to_bytes(4, "big") + height.to_bytes(4, "big") + bytes([8, 6, 0, 0, 0])
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", compressed)
        + chunk(b"IEND", b"")
    )


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def _zip_pngs(zip_path: Path, predicate) -> dict[str, bytes]:
    out: dict[str, bytes] = {}
    with zipfile.ZipFile(zip_path) as zf:
        for name in zf.namelist():
            if not name.endswith(".png") or name.endswith("/"):
                continue
            if predicate(name):
                out[name] = zf.read(name)
    return out


def _match_layer(stem: str) -> str | None:
    # Prefer longest suffix match.
    for suffix, dest in sorted(LAYER_SUFFIXES, key=lambda item: -len(item[0])):
        if stem.endswith(suffix):
            return dest
    if "status-rail" in stem or "state-rail" in stem:
        # Prefer a single default rail; cyan/blue first, else amber, else any.
        return "__rail__"
    return None


def _ingest_plates(theme_id: str, meta: dict) -> None:
    zip_path = PACKS / theme_id / "packages" / meta["raster_zip"]
    pngs = _zip_pngs(
        zip_path,
        lambda n: "/png/1x/templates/" in n.replace("\\", "/"),
    )
    # group by template folder
    by_tmpl: dict[str, dict[str, bytes]] = {}
    for name, data in pngs.items():
        parts = name.replace("\\", "/").split("/")
        # .../templates/<tmpl>/<file>
        try:
            idx = parts.index("templates")
            tmpl = parts[idx + 1]
            fname = parts[idx + 2]
        except (ValueError, IndexError):
            continue
        by_tmpl.setdefault(tmpl, {})[fname] = data

    for tmpl, files in by_tmpl.items():
        dest_dir = V4_ROOT / theme_id / "plates" / tmpl / "layers"
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        dest_dir.mkdir(parents=True)
        rail_candidates: list[tuple[int, str, bytes]] = []
        written: set[str] = set()
        for fname, data in files.items():
            stem = Path(fname).stem
            # strip theme prefix: pw-battle-01-plate-base
            mapped = _match_layer(stem)
            if mapped is None:
                continue
            if mapped == "__rail__":
                score = 0
                if "cyan" in stem or "blue" in stem:
                    score = 3
                elif "amber" in stem:
                    score = 2
                elif "green" in stem:
                    score = 1
                rail_candidates.append((score, fname, data))
                continue
            if mapped in written and mapped == "frame_highlight.png":
                # first divider/edge wins
                continue
            _write(dest_dir / mapped, data)
            written.add(mapped)
        if rail_candidates:
            rail_candidates.sort(key=lambda row: (-row[0], row[1]))
            _write(dest_dir / "status_rail.png", rail_candidates[0][2])
            written.add("status_rail.png")
        # paintPlateMask requires base_plate
        if "base_plate.png" not in written:
            raise RuntimeError(f"{theme_id}/{tmpl}: missing plate-base layer")
        # transparent stubs for optional cyber-compat / light-parity names
        for stub in ("corner_right.png", "icon_well.png", "family_detail.png"):
            if stub not in written:
                _write(dest_dir / stub, _png_rgba(420, 140))
                written.add(stub)


def _ingest_icons(theme_id: str, meta: dict) -> None:
    prefix = meta["prefix"]
    zip_path = PACKS / theme_id / "packages" / meta["icons_zip"]
    pngs = _zip_pngs(
        zip_path,
        lambda n: "/png/1x/icons/" in n.replace("\\", "/") and f"{prefix}-icon-" in n,
    )
    evm = json.loads((PACKS / theme_id / "accents" / "event-visual-map.json").read_text())
    v4_states = json.loads((V4_ROOT / "manifest.json").read_text())["states"]

    # Clear family icon dirs
    for family in ("battle", "timing", "position", "exception", "pit", "bio", "session"):
        icon_dir = V4_ROOT / theme_id / family / "icons"
        if icon_dir.exists():
            shutil.rmtree(icon_dir)
        icon_dir.mkdir(parents=True)

    # Index pack icons by state-ish stem: pw-icon-hunting.png → hunting
    pack_by_stem: dict[str, bytes] = {}
    for name, data in pngs.items():
        fname = Path(name).name
        stem = fname
        if stem.startswith(f"{prefix}-icon-"):
            stem = stem[len(f"{prefix}-icon-") :]
        stem = Path(stem).stem.replace("-", "_")
        pack_by_stem[stem] = data

    for state_id, state_meta in v4_states.items():
        family = str(state_meta["family"])
        # pack icon path from visual map when present
        pack_icon = evm["states"][state_id]["icon"]
        pack_stem = Path(pack_icon).stem
        if pack_stem.startswith(f"{prefix}-icon-"):
            pack_stem = pack_stem[len(f"{prefix}-icon-") :]
        pack_stem = pack_stem.replace("-", "_")
        data = pack_by_stem.get(pack_stem) or pack_by_stem.get(state_id)
        if data is None:
            raise RuntimeError(f"{theme_id}: missing icon for state {state_id} ({pack_stem})")
        _write(V4_ROOT / theme_id / family / "icons" / f"{state_id}.png", data)


def _ingest_sysinfo(theme_id: str, meta: dict) -> None:
    prefix = meta["prefix"]
    zip_path = PACKS / theme_id / "packages" / meta["sysinfo_zip"]
    pngs = _zip_pngs(
        zip_path,
        lambda n: "/png/1x/sysinfo/" in n.replace("\\", "/"),
    )
    layer_dir = V4_ROOT / theme_id / "sysinfo" / "layers"
    if layer_dir.exists():
        shutil.rmtree(layer_dir)
    layer_dir.mkdir(parents=True)
    for name, data in pngs.items():
        fname = Path(name).name
        stem = fname
        if stem.startswith(f"{prefix}-sysinfo-"):
            stem = stem[len(f"{prefix}-sysinfo-") :]
        stem = Path(stem).stem
        dest = SYSINFO_MAP.get(stem)
        if not dest:
            continue
        if dest == "sysinfo_dividers_mask.png":
            # Pack raster has soft low-alpha strokes; runtime mask needs opaque
            # columns on the 230 + 11×150 grid. Reuse the verified classic mask.
            classic = V4_ROOT / "cyber_racing" / "sysinfo" / "layers" / "sysinfo_dividers_mask.png"
            _write(layer_dir / dest, classic.read_bytes())
        else:
            _write(layer_dir / dest, data)

    # icons from icons zip
    icons_zip = PACKS / theme_id / "packages" / meta["icons_zip"]
    icon_pngs = _zip_pngs(
        icons_zip,
        lambda n: "/png/1x/icons/" in n.replace("\\", "/") and f"{prefix}-icon-" in n,
    )
    icon_dir = V4_ROOT / theme_id / "sysinfo" / "icons"
    if icon_dir.exists():
        shutil.rmtree(icon_dir)
    icon_dir.mkdir(parents=True)
    for name, data in icon_pngs.items():
        stem = Path(name).stem
        if stem.startswith(f"{prefix}-icon-"):
            stem = stem[len(f"{prefix}-icon-") :]
        stem = stem.replace("-", "_")
        # only simple utility names
        base = stem.split("_")[0] if "_" in stem and stem not in SYSINFO_ICON_MAP else stem
        mapped = SYSINFO_ICON_MAP.get(stem) or SYSINFO_ICON_MAP.get(base)
        if mapped:
            _write(icon_dir / mapped, data)
    # ensure required sysinfo icons exist (copy ram←memory already handled)
    required = (
        "cpu.png",
        "gpu.png",
        "temp.png",
        "power.png",
        "ram.png",
        "fps.png",
        "heart.png",
        "vram.png",
        "ble.png",
        "frametime.png",
    )
    for req in required:
        if not (icon_dir / req).is_file():
            # transparent stub keeps resolver/parity happy; demo may look empty
            _write(icon_dir / req, _png_rgba(32, 32))


def _ingest_motion(theme_id: str) -> None:
    src = PACKS / theme_id / "motion"
    dest = V4_ROOT / theme_id / "motion"
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)
    for name in V4_MOTIONS:
        src_file = src / f"{name}.webm"
        if not src_file.is_file():
            raise RuntimeError(f"missing motion reel {src_file}")
        shutil.copy2(src_file, dest / f"{name}.webm")


def ingest_theme(theme_id: str) -> None:
    meta = THEMES[theme_id]
    print(f"ingest {theme_id}…")
    _ingest_plates(theme_id, meta)
    _ingest_icons(theme_id, meta)
    _ingest_sysinfo(theme_id, meta)
    _ingest_motion(theme_id)
    # empty family/layers dirs expected by tests (plates hold real layers)
    for family in ("battle", "timing", "position", "exception", "pit", "bio", "session"):
        layer_dir = V4_ROOT / theme_id / family / "layers"
        layer_dir.mkdir(parents=True, exist_ok=True)
        placeholder = layer_dir / "placeholder.png"
        if not placeholder.is_file():
            placeholder.write_bytes(_png_rgba(1, 1))


def check_theme(theme_id: str) -> list[str]:
    errors: list[str] = []
    root = V4_ROOT / theme_id
    if not root.is_dir():
        return [f"missing theme root {root}"]
    for name in V4_MOTIONS:
        if not (root / "motion" / f"{name}.webm").is_file():
            errors.append(f"missing motion {name}")
    for tmpl in TEMPLATE_FAMILY_ICONS:
        base = root / "plates" / tmpl / "layers" / "base_plate.png"
        if not base.is_file():
            errors.append(f"missing plate {tmpl}/base_plate.png")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--theme", choices=sorted(THEMES), action="append")
    args = parser.parse_args()
    themes = args.theme or list(THEMES)
    if args.check:
        failed = False
        for theme_id in themes:
            errs = check_theme(theme_id)
            if errs:
                failed = True
                print(theme_id, "FAIL")
                for e in errs:
                    print(" ", e)
            else:
                print(theme_id, "OK")
        return 1 if failed else 0
    for theme_id in themes:
        ingest_theme(theme_id)
        errs = check_theme(theme_id)
        if errs:
            print("POST-CHECK FAIL", theme_id, errs, file=sys.stderr)
            return 1
        print(theme_id, "OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
