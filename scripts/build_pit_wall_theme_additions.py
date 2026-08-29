#!/usr/bin/env python3
"""Build the Pit Wall Dark/Light V4 art-pack additions.

The script deliberately uses only the standard library plus ImageMagick's
``convert`` and FFmpeg commands. SVG remains the source of truth; PNG/WebP and
alpha-VP9 files in the tracked export archives are deterministic derivatives.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import shutil
import struct
import subprocess
import tempfile
import zipfile
from collections import OrderedDict
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
PACKS_ROOT = REPO / "assets" / "overlay" / "themes"
V4_MANIFEST = REPO / "src" / "irswitch" / "web" / "themes-v4" / "manifest.json"
V4_CATALOG = REPO / "src" / "irswitch" / "web" / "themes-v4" / "event_catalog.json"
ZIP_TIME = (2026, 8, 29, 0, 0, 0)
DIVIDERS = [230 + 150 * index for index in range(12)]

MOTION_REELS: OrderedDict[str, dict[str, Any]] = OrderedDict(
    [
        ("enter_reveal", {"frames": {"pw": 11, "pl": 10}, "intent": "native plate reveal with rail and timing sweep"}),
        ("theme_glitch", {"frames": 9, "intent": "single theme-character accent; segmented telemetry for Dark, soft optical reacquire for Light"}),
        ("active_pulse", {"frames": 8, "intent": "one local data pulse without full-card looping"}),
        ("compact_mask", {"frames": 7, "intent": "secondary detail retracts while native plate geometry stays fixed"}),
        ("suspend_dim", {"frames": 9, "intent": "one masked neutral dim pass inside the plate silhouette"}),
        ("resume_reacquire", {"frames": 9, "intent": "short locator reacquire and rail return"}),
        ("result_burst", {"frames": 10, "intent": "short icon-well result accent with no baked content"}),
        ("exit_trace", {"frames": 9, "intent": "reverse trace wipe without scale-out"}),
        ("battle_signal_lock", {"frames": 11, "intent": "single target acquisition and pressure-rail lock"}),
        ("timing_projection_sweep", {"frames": 10, "intent": "one timing projection trace across the data surface"}),
        ("position_chevron_hit", {"frames": 8, "intent": "directional chevron reveal for position results"}),
        ("exception_link_drop", {"frames": 8, "intent": "single fracture reveal with no repeated flash"}),
        ("pit_stop_ring", {"frames": 9, "intent": "six-step pit phase track accent only"}),
        ("bio_pulse", {"frames": 10, "intent": "single sample-driven biometric trace pulse"}),
        ("session_finish_burst", {"frames": 13, "intent": "one edge-bus sweep for final lap or finish"}),
    ]
)


THEMES: dict[str, dict[str, Any]] = {
    "pit_wall_dark": {
        "theme_id": "pitwall_race_control",
        "display_name": "Pit Wall Dark",
        "prefix": "pw",
        "ink": "#EAF3F7",
        "icon_box": [54, 50, 40, 40],
        "package_dir": "Pitwall_Race_Control_Asset_Package",
        "archives": {
            "core": "01_Pitwall_Core_Vector_and_Tokens.zip",
            "icons": "02_Pitwall_Icons_and_Status.zip",
            "vector": "03_Pitwall_Transient_Templates_Vector.zip",
            "raster_1x": "04_Pitwall_Transient_Raster_1x.zip",
            "raster_2x": "05_Pitwall_Transient_Raster_2x.zip",
            "common_1x": "06_Pitwall_Common_Raster_1x.zip",
            "common_2x": "07_Pitwall_Common_Raster_2x.zip",
            "sysinfo": "08_Pitwall_SYSINFO_All_Formats.zip",
            "docs": "09_Pitwall_Documentation_Examples_Manifests.zip",
            "motion": "10_Pitwall_Motion_Alpha_VP9.zip",
        },
        "tones": {
            "primary": {"rail": "cyan", "color": "#35D7FF"},
            "timing": {"rail": "cyan", "color": "#35D7FF"},
            "positive": {"rail": "green", "color": "#36D28A"},
            "warning": {"rail": "amber", "color": "#F4A62A"},
            "critical": {"rail": "red", "color": "#FF4E5B"},
            "bio": {"rail": "amber", "color": "#F4A62A"},
            "neutral": {"rail": "neutral", "color": "#8DA2AD"},
        },
    },
    "pit_wall_light": {
        "theme_id": "pitwall_light",
        "display_name": "Pit Wall Light",
        "prefix": "pl",
        "ink": "#101B2C",
        "icon_box": [39, 46, 48, 48],
        "package_dir": "Pitwall_Light_Asset_Package",
        "archives": {
            "core": "01_Pitwall_Light_Core_Vector_and_Tokens.zip",
            "icons": "02_Pitwall_Light_Icons_BLE_and_Status.zip",
            "vector": "03_Pitwall_Light_Transient_Templates_Vector.zip",
            "raster_1x": "04_Pitwall_Light_Transient_Raster_1x.zip",
            "raster_2x": "05_Pitwall_Light_Transient_Raster_2x.zip",
            "common_1x": "06_Pitwall_Light_Common_Raster_1x.zip",
            "common_2x": "07_Pitwall_Light_Common_Raster_2x.zip",
            "sysinfo": "08_Pitwall_Light_SYSINFO_All_Formats.zip",
            "docs": "09_Pitwall_Light_Documentation_Examples_Manifests.zip",
            "motion": "10_Pitwall_Light_Motion_Alpha_VP9.zip",
        },
        "tones": {
            "primary": {"rail": "blue", "color": "#1B72FF"},
            "timing": {"rail": "cyan", "color": "#17B7DB"},
            "positive": {"rail": "green", "color": "#15A875"},
            "warning": {"rail": "amber", "color": "#EF9E20"},
            "critical": {"rail": "red", "color": "#E84C56"},
            "bio": {"rail": "violet", "color": "#795CFF"},
            "neutral": {"rail": "neutral", "color": "#6D7B8F"},
        },
    },
}


STATE_SPECS: OrderedDict[str, dict[str, str]] = OrderedDict(
    [
        ("hunting", {"template": "hunting", "tone": "primary", "zone": "BATTLE_AHEAD", "note": "Approved HUNTING plate."}),
        ("hunted", {"template": "hunted", "tone": "warning", "zone": "BATTLE_BEHIND", "note": "Approved HUNTED plate; critical payload may select red rail."}),
        ("approach", {"template": "hunting", "tone": "primary", "zone": "BATTLE_AHEAD", "note": "Reuses HUNTING plate with approach glyph and copy."}),
        ("attack_range", {"template": "battle", "tone": "warning", "zone": "BATTLE_AHEAD", "note": "Reuses BATTLE plate with attack-range glyph."}),
        ("side_by_side", {"template": "battle", "tone": "warning", "zone": "BATTLE_AHEAD", "note": "Reuses BATTLE plate with side-by-side glyph."}),
        ("battle_for_position", {"template": "battle", "tone": "warning", "zone": "BATTLE_AHEAD", "note": "Approved dual-rail BATTLE plate."}),
        ("battle_won", {"template": "battle", "tone": "positive", "zone": "BATTLE_AHEAD", "note": "Reuses BATTLE plate as a result state."}),
        ("target", {"template": "lap", "tone": "primary", "zone": "EVENT", "note": "Reuses LAP timing plate with target glyph."}),
        ("projected_lap", {"template": "lap", "tone": "timing", "zone": "EVENT", "note": "Reuses LAP timing plate with projection glyph."}),
        ("pb_attack", {"template": "pb", "tone": "positive", "zone": "EVENT", "note": "Reuses PB plate with PB-attack glyph."}),
        ("lap_complete", {"template": "lap", "tone": "timing", "zone": "EVENT", "note": "Approved LAP plate."}),
        ("personal_best", {"template": "pb", "tone": "positive", "zone": "EVENT", "note": "Approved PB plate."}),
        ("hot_lap", {"template": "lap", "tone": "warning", "zone": "EVENT", "note": "Reuses LAP plate with hot-lap glyph."}),
        ("position_attack", {"template": "position", "tone": "warning", "zone": "EVENT", "note": "Reuses POSITION plate with grid-attack glyph."}),
        ("gain_found", {"template": "pb", "tone": "positive", "zone": "EVENT", "note": "Reuses PB plate with gain glyph."}),
        ("clean_streak", {"template": "pb", "tone": "positive", "zone": "EVENT", "note": "Reuses PB plate with clean-streak glyph."}),
        ("overtake", {"template": "position", "tone": "positive", "zone": "EVENT", "note": "Reuses POSITION plate with overtake glyph."}),
        ("position_gained", {"template": "position", "tone": "positive", "zone": "EVENT", "note": "Approved POSITION plate, upward motion direction."}),
        ("position_lost", {"template": "position", "tone": "warning", "zone": "EVENT", "note": "Approved POSITION plate, downward motion direction; red only if critical."}),
        ("rival_threat", {"template": "position", "tone": "warning", "zone": "EVENT", "note": "Reuses POSITION plate with rival-threat glyph."}),
        ("invalid_lap", {"template": "exception", "tone": "critical", "zone": "EVENT", "note": "New EXCEPTION family plate."}),
        ("incident", {"template": "exception", "tone": "warning", "zone": "EVENT", "note": "New EXCEPTION family plate."}),
        ("link_drop", {"template": "exception", "tone": "critical", "zone": "EVENT", "note": "New EXCEPTION family plate with broken-link glyph."}),
        ("pit_entry", {"template": "pit", "tone": "warning", "zone": "EVENT", "note": "New PIT family plate, phase 1/6."}),
        ("pit_lane", {"template": "pit", "tone": "warning", "zone": "EVENT", "note": "New PIT family plate, phase 2/6."}),
        ("pit_stopped", {"template": "pit", "tone": "warning", "zone": "EVENT", "note": "New PIT family plate, phase 3/6."}),
        ("pit_released", {"template": "pit", "tone": "primary", "zone": "EVENT", "note": "New PIT family plate, phase 4/6."}),
        ("pit_exit", {"template": "pit", "tone": "primary", "zone": "EVENT", "note": "New PIT family plate, phase 5/6."}),
        ("pit_outcome", {"template": "pit", "tone": "positive", "zone": "EVENT", "note": "New PIT family plate, result phase 6/6."}),
        ("hr_pressure", {"template": "bio", "tone": "bio", "zone": "BIO_EXPANDED", "note": "Approved BIO plate."}),
        ("composure_test", {"template": "bio", "tone": "bio", "zone": "BIO_EXPANDED", "note": "Reuses BIO plate with composure glyph."}),
        ("high_load", {"template": "bio", "tone": "critical", "zone": "BIO_EXPANDED", "note": "Reuses BIO plate with high-load glyph."}),
        ("ble_reconnecting", {"template": "bio", "tone": "warning", "zone": "BIO_EXPANDED", "note": "Reuses BIO plate with BLE reconnect glyph."}),
        ("final_lap", {"template": "final-lap", "tone": "warning", "zone": "SESSION", "note": "Approved FINAL LAP plate."}),
        ("finish", {"template": "finish", "tone": "positive", "zone": "SESSION", "note": "Approved FINISH plate."}),
    ]
)


# Each drawing is authored for a 64 x 64 monochrome line icon.
ICON_DRAWINGS: dict[str, str] = {
    "hunting": '<circle cx="32" cy="32" r="17"/><circle cx="32" cy="32" r="6"/><path d="M32 6V19M32 45V58M6 32H19M45 32H58"/>',
    "hunted": '<path d="M32 7L51 14V29C51 42 43 51 32 57C21 51 13 42 13 29V14Z"/><path d="M19 26H30M19 32H34M19 38H29M43 24L49 30L43 36"/>',
    "approach": '<path d="M9 17L25 32L9 47M39 17L55 32L39 47"/><path d="M27 12V52"/>',
    "attack_range": '<circle cx="29" cy="32" r="15"/><path d="M29 8V18M29 46V56M5 32H15M43 32H53M42 13L54 13L48 24"/>',
    "side_by_side": '<rect x="10" y="16" width="17" height="32" rx="5"/><rect x="37" y="16" width="17" height="32" rx="5"/><path d="M18 10V16M46 48V54M30 22H34M30 42H34"/>',
    "battle_for_position": '<path d="M10 20H44L37 13M44 20L37 27M54 44H20L27 37M20 44L27 51"/><circle cx="32" cy="32" r="7"/>',
    "battle_won": '<path d="M22 10H42V20C42 31 38 37 32 37C26 37 22 31 22 20Z"/><path d="M22 16H12C12 27 17 31 24 31M42 16H52C52 27 47 31 40 31M32 37V48M23 54H41M27 48H37"/>',
    "target": '<path d="M11 22V11H22M42 11H53V22M53 42V53H42M22 53H11V42"/><circle cx="32" cy="32" r="12"/><path d="M32 25V39M25 32H39"/>',
    "projected_lap": '<circle cx="31" cy="33" r="20" stroke-dasharray="4 5"/><path d="M31 18V33L43 40M12 12L18 18M50 12L44 18"/>',
    "pb_attack": '<circle cx="29" cy="34" r="18"/><path d="M29 16V9M23 9H35M29 34L39 27M47 17H57M52 12V22"/>',
    "lap_complete": '<path d="M15 55V10M16 12C27 5 36 20 49 11V35C36 44 27 29 16 36"/><path d="M18 14L46 34M18 34L43 12M31 11V37"/>',
    "personal_best": '<circle cx="27" cy="34" r="17"/><path d="M27 18V10M21 10H33M27 34L36 27M48 20L51 27L58 28L53 33L54 40L48 36L42 40L43 33L38 28L45 27Z"/>',
    "hot_lap": '<path d="M34 7C38 18 27 20 33 29C25 27 22 21 23 14C12 25 13 47 32 56C50 50 54 31 43 20C43 31 38 34 34 36C37 26 31 20 34 7Z"/><path d="M27 46L32 41L37 46"/>',
    "position_attack": '<path d="M10 14H38V50H10Z M19 14V50M29 14V50M10 26H38M10 38H38M43 43L55 31M47 31H55V39"/>',
    "gain_found": '<path d="M9 49L23 35L33 41L52 19M41 19H52V30"/><path d="M9 55H55"/>',
    "clean_streak": '<path d="M32 7L50 14V29C50 42 42 51 32 57C22 51 14 42 14 29V14Z"/><path d="M22 32L29 39L43 23"/>',
    "overtake": '<rect x="8" y="28" width="18" height="22" rx="4"/><rect x="38" y="14" width="18" height="22" rx="4"/><path d="M17 22C26 12 38 12 47 8M40 7L47 8L46 15"/>',
    "position_gained": '<path d="M32 55V13M17 29L32 13L47 29"/><path d="M15 50H49"/>',
    "position_lost": '<path d="M32 9V51M17 35L32 51L47 35"/><path d="M15 14H49"/>',
    "rival_threat": '<path d="M32 7L57 52H7Z"/><path d="M32 22V37M32 45H32.1"/><circle cx="32" cy="32" r="21" stroke-dasharray="3 5"/>',
    "invalid_lap": '<circle cx="28" cy="33" r="18"/><path d="M28 16V9M22 9H34M28 33L38 26M10 53L53 10"/>',
    "incident": '<path d="M32 7L58 54H6Z"/><path d="M32 22V38M32 47H32.1"/>',
    "link_drop": '<path d="M25 40L20 45C15 50 8 50 4 46C0 42 1 35 5 31L15 21C20 16 28 16 32 21M39 24L44 19C49 14 56 14 60 18C64 22 63 29 59 33L49 43C44 48 36 48 32 43M21 43L43 21M21 21L43 43"/>',
    "pit_entry": '<path d="M10 53V12M54 53V12M20 53V36C20 27 27 20 36 20H50M42 13L50 20L42 27"/><path d="M15 43H20"/>',
    "pit_lane": '<path d="M15 56L23 8M49 56L41 8M32 14V22M32 30V38M32 46V54"/><circle cx="32" cy="32" r="22" stroke-dasharray="2 7"/>',
    "pit_stopped": '<path d="M22 7H42L57 22V42L42 57H22L7 42V22Z"/><path d="M22 24V40M42 24V40M22 32H42"/>',
    "pit_released": '<path d="M13 10V54M13 16H38V48H13M29 24L48 32L29 40M48 32H56"/>',
    "pit_exit": '<path d="M10 53V12M54 53V12M44 53V36C44 27 37 20 28 20H14M22 13L14 20L22 27"/><path d="M44 43H49"/>',
    "pit_outcome": '<path d="M14 55V10M15 12C26 6 34 19 48 12V34C34 41 26 28 15 35M24 49L31 55L47 42"/>',
    "hr_pressure": '<path d="M32 55S8 42 8 24C8 12 23 8 32 20C41 8 56 12 56 24C56 42 32 55 32 55Z"/><path d="M18 34H26L30 25L36 42L40 34H49"/>',
    "composure_test": '<path d="M32 54S10 42 10 25C10 14 23 10 32 21C41 10 54 14 54 25C54 42 32 54 32 54Z"/><path d="M17 35H25L29 30L34 38L39 32L47 35"/>',
    "high_load": '<path d="M30 54S9 42 9 25C9 14 22 10 30 21C38 10 51 14 51 25C51 42 30 54 30 54Z"/><path d="M15 35H23L27 25L33 44L38 31L44 35H51M56 12V29M56 38H56.1"/>',
    "ble_reconnecting": '<path d="M29 8L44 21L29 32L44 43L29 56V8ZM17 20L44 43M17 44L44 21"/><path d="M8 13A27 27 0 0 1 52 10M52 10L51 19M52 10L43 10M56 51A27 27 0 0 1 12 54M12 54L13 45M12 54L21 54"/>',
    "final_lap": '<path d="M14 56V9M15 11C26 5 36 19 50 11V36C36 44 26 29 15 37"/><path d="M33 17V32M27 32H39"/>',
    "finish": '<path d="M14 56V9M15 11C27 5 36 20 50 11V36C36 44 27 29 15 37"/><path d="M16 13L49 35M16 35L46 11M31 10V39"/>',
    "cpu_temp_high": '<rect x="8" y="15" width="34" height="34" rx="5"/><path d="M17 8V15M27 8V15M37 8V15M17 49V56M27 49V56M37 49V56M8 24H2M8 34H2M8 44H2M42 24H48M42 34H48M42 44H48M56 15V39M50 39A6 6 0 1 0 62 39A6 6 0 0 0 56 39Z"/>',
    "gpu_temp_high": '<path d="M7 16H45V48H7Z M14 23H38V41H14Z M45 25H54M45 32H54M45 39H54"/><path d="M58 14V39M52 39A6 6 0 1 0 64 39A6 6 0 0 0 58 39Z"/>',
}


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def icon_svg(title: str, drawing: str, ink: str) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64" fill="none">
  <title>{title}</title>
  <g fill="none" stroke="{ink}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round">{drawing}</g>
</svg>'''


def canvas_svg(title: str, body: str, defs: str = "") -> str:
    defs_block = f"\n  <defs>{defs}</defs>" if defs else ""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="420" height="140" viewBox="0 0 420 140" fill="none">
  <title>{title}</title>{defs_block}
  {body}
</svg>'''


def copy_svg(source: Path, destination: Path, old_scope: str, new_scope: str) -> None:
    text = source.read_text(encoding="utf-8").replace(old_scope, new_scope)
    write_text(destination, text)


def build_icons(root: Path, config: dict[str, Any]) -> None:
    prefix = config["prefix"]
    for state_name, drawing in ICON_DRAWINGS.items():
        stem = state_name.replace("_", "-")
        destination = root / "icons" / "event" / f"{prefix}-icon-{stem}.svg"
        # Target and finish are approved masters already present in both packs.
        if state_name in {"target", "finish"} and destination.exists():
            continue
        title = f'{config["display_name"]} {stem} icon'
        write_text(
            destination,
            icon_svg(title, drawing, config["ink"]),
        )


def build_dark_templates(root: Path) -> None:
    template_root = root / "frames" / "templates"
    source = template_root / "position"
    common_rails = root / "frames" / "common" / "rails"
    for family, colors in {"pit": ("amber", "cyan", "green"), "exception": ("amber", "red")}.items():
        target = template_root / family
        for order, suffix in (
            ("01", "plate-base"),
            ("02", "data-surface"),
            ("03", "border"),
            ("05", "timing-ticks"),
            ("07", "corner-accent"),
            ("08", "bottom-divider"),
        ):
            copy_svg(
                source / f"pw-position-{order}-{suffix}.svg",
                target / f"pw-{family}-{order}-{suffix}.svg",
                "position",
                family,
            )
        for color in colors:
            copy_svg(
                common_rails / f"pw-status-rail-left-{color}.svg",
                target / f"pw-{family}-04-status-rail-left-{color}.svg",
                "status rail",
                f"{family} status rail",
            )

    pit_detail = canvas_svg(
        "Pit Wall Dark pit phase track",
        '<path d="M126 112H390" stroke="#8DA2AD" stroke-opacity=".18"/>'
        '<g fill="#35D7FF" fill-opacity=".34">'
        '<rect x="126" y="108" width="32" height="8" rx="2"/><rect x="166" y="108" width="32" height="8" rx="2"/>'
        '<rect x="206" y="108" width="32" height="8" rx="2"/><rect x="246" y="108" width="32" height="8" rx="2"/>'
        '<rect x="286" y="108" width="32" height="8" rx="2"/><rect x="326" y="108" width="32" height="8" rx="2"/></g>'
        '<path d="M76 30V110M92 30V110M84 38V50M84 60V72M84 82V94" stroke="#F4A62A" stroke-opacity=".28"/>',
    )
    write_text(template_root / "pit" / "pw-pit-06-pit-phase-track.svg", pit_detail)

    exception_detail = canvas_svg(
        "Pit Wall Dark exception fracture",
        '<path d="M286 20L267 49L289 64L257 91L274 118" stroke="#FF4E5B" stroke-opacity=".26" stroke-width="2"/>'
        '<path d="M289 64L321 51M257 91L232 83M274 118L306 105" stroke="#F4A62A" stroke-opacity=".18"/>'
        '<path d="M126 111H390" stroke="#FF4E5B" stroke-opacity=".22" stroke-dasharray="3 6"/>',
    )
    write_text(
        template_root / "exception" / "pw-exception-06-exception-fracture.svg",
        exception_detail,
    )


def build_light_templates(root: Path) -> None:
    template_root = root / "frames" / "templates"
    source = template_root / "position"
    common_rails = root / "accents" / "common" / "accents"
    for family, colors in {"pit": ("amber", "blue", "green"), "exception": ("amber", "red")}.items():
        target = template_root / family
        for order, suffix in (
            ("01", "plate-base"),
            ("02", "data-surface"),
            ("03", "technical-grid"),
            ("04", "icon-well"),
            ("05", "border"),
            ("06", "edge-light"),
            ("08", "timing-ticks"),
            ("09", "corner-accent"),
            ("10", "bottom-divider"),
        ):
            copy_svg(
                source / f"pl-position-{order}-{suffix}.svg",
                target / f"pl-{family}-{order}-{suffix}.svg",
                "position",
                family,
            )
        for color in colors:
            copy_svg(
                common_rails / f"pl-state-rail-left-{color}.svg",
                target / f"pl-{family}-07-state-rail-left-{color}.svg",
                "state rail",
                f"{family} state rail",
            )

    pit_detail = canvas_svg(
        "Pit Wall Light pit phase track",
        '<path d="M126 111H390" stroke="#315579" stroke-opacity=".13"/>'
        '<g fill="#1B72FF" fill-opacity=".22">'
        '<rect x="126" y="107" width="32" height="8" rx="4"/><rect x="166" y="107" width="32" height="8" rx="4"/>'
        '<rect x="206" y="107" width="32" height="8" rx="4"/><rect x="246" y="107" width="32" height="8" rx="4"/>'
        '<rect x="286" y="107" width="32" height="8" rx="4"/><rect x="326" y="107" width="32" height="8" rx="4"/></g>'
        '<path d="M76 35V105M91 35V105M83.5 43V53M83.5 63V73M83.5 83V93" stroke="#EF9E20" stroke-opacity=".20"/>',
    )
    write_text(template_root / "pit" / "pl-pit-11-pit-phase-track.svg", pit_detail)

    exception_detail = canvas_svg(
        "Pit Wall Light exception fracture",
        '<path d="M292 21L273 49L295 65L263 91L281 118" stroke="#E84C56" stroke-opacity=".22" stroke-width="2"/>'
        '<path d="M295 65L326 52M263 91L238 83M281 118L312 105" stroke="#EF9E20" stroke-opacity=".15"/>'
        '<path d="M126 110H390" stroke="#E84C56" stroke-opacity=".16" stroke-dasharray="3 7"/>',
    )
    write_text(
        template_root / "exception" / "pl-exception-11-exception-fracture.svg",
        exception_detail,
    )


def build_templates(root: Path, config: dict[str, Any]) -> None:
    if config["prefix"] == "pw":
        build_dark_templates(root)
    else:
        build_light_templates(root)


def update_sysinfo(root: Path, config: dict[str, Any]) -> None:
    prefix = config["prefix"]
    color = "#A7BBC4" if prefix == "pw" else "#315579"
    opacity = ".18" if prefix == "pw" else ".14"
    y1, y2 = (14, 62) if prefix == "pw" else (15, 61)
    paths = "".join(
        f'<path d="M{x} {y1}V{y2}" stroke="{color}" stroke-opacity="{opacity}"/>'
        for x in DIVIDERS
    )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1920" height="72" viewBox="0 0 1920 72" fill="none">
  <title>{config["display_name"]} SYSINFO runtime-grid dividers</title>
  <!-- Runtime grid: brand 230 px + 11 modules x 150 px; x=1880..1920 is trailing safe area. -->
  {paths}
</svg>'''
    write_text(root / "icons" / "sysinfo" / f"{prefix}-sysinfo-dividers.svg", svg)


def update_tokens(root: Path, config: dict[str, Any]) -> None:
    path = root / "theme-tokens.json"
    tokens = json.loads(path.read_text(encoding="utf-8"))
    geometry = tokens.setdefault("geometry", {})
    geometry["iconBox"] = config["icon_box"]
    if config["prefix"] == "pl":
        geometry["iconWell"] = {
            "x": 22,
            "y": 26,
            "width": 82,
            "height": 88,
            "radius": 22,
            "iconBox": config["icon_box"],
        }
    sysinfo = geometry.setdefault("sysinfo", {})
    sysinfo["width"] = 1920
    sysinfo["height"] = 72
    sysinfo["brandWidth"] = 230
    sysinfo.pop("standardSegmentWidth", None)
    sysinfo.pop("bioSegmentWidth", None)
    sysinfo["grid"] = {
        "brandWidth": 230,
        "moduleWidth": 150,
        "moduleCount": 11,
        "positions": DIVIDERS,
        "dataEndX": 1880,
        "trailingSafeWidth": 40,
    }
    tokens["version"] = "1.1.0"
    write_text(path, json.dumps(tokens, indent=2, ensure_ascii=False))


def template_registry(root: Path) -> dict[str, Any]:
    registry: dict[str, Any] = {}
    for directory in sorted((root / "frames" / "templates").iterdir()):
        if not directory.is_dir():
            continue
        base_layers: list[str] = []
        rail_layers: dict[str, str] = {}
        for path in sorted(directory.glob("*.svg")):
            relative = path.relative_to(root).as_posix()
            match = re.search(r"(?:status|state)-rail-(left|right)-([a-z]+)\.svg$", path.name)
            if match:
                rail_layers[f"{match.group(1)}-{match.group(2)}"] = relative
            else:
                base_layers.append(relative)
        registry[directory.name] = {
            "canvas": [420, 140],
            "root": directory.relative_to(root).as_posix(),
            "layers": base_layers,
            "railLayers": rail_layers,
        }
    return registry


def state_rail_layers(
    template: dict[str, Any], rail_color: str, state_name: str, prefix: str
) -> list[str]:
    layers: dict[str, str] = template["railLayers"]
    if state_name == "battle_for_position":
        primary = "cyan" if prefix == "pw" else "blue"
        return [
            path
            for key in (f"left-{primary}", "right-amber")
            if (path := layers.get(key)) is not None
        ]
    preferred_side = "right" if state_name == "hunted" else "left"
    candidates = (
        f"{preferred_side}-{rail_color}",
        f"left-{rail_color}",
        f"right-{rail_color}",
    )
    for key in candidates:
        if key in layers:
            return [layers[key]]
    return []


def common_rail_layer(
    root: Path, config: dict[str, Any], state_name: str, rail_color: str
) -> str:
    side = "right" if state_name == "hunted" else "left"
    prefix = config["prefix"]
    if prefix == "pw":
        path = root / "frames" / "common" / "rails" / f"pw-status-rail-{side}-{rail_color}.svg"
    else:
        path = root / "accents" / "common" / "accents" / f"pl-state-rail-{side}-{rail_color}.svg"
    if not path.is_file():
        raise FileNotFoundError(f"No {rail_color} rail for {state_name}: {path}")
    return path.relative_to(root).as_posix()


def build_event_map(root: Path, config: dict[str, Any]) -> None:
    v4 = json.loads(V4_MANIFEST.read_text(encoding="utf-8"))
    catalog = json.loads(V4_CATALOG.read_text(encoding="utf-8"))
    templates = template_registry(root)
    prefix = config["prefix"]
    states: dict[str, Any] = OrderedDict()
    for state_name, spec in STATE_SPECS.items():
        assert state_name in v4["states"], state_name
        tone = spec["tone"]
        rail = config["tones"][tone]["rail"]
        lifecycle = v4["states"][state_name]["lifecycle"]
        motion = "result" if lifecycle == "RESULT_EXIT" else "active"
        if spec["template"] == "pit":
            motion = "pit-phase" if lifecycle != "RESULT_EXIT" else "result"
        elif spec["template"] == "exception":
            motion = "exception-alert"
        elif state_name in {"final_lap", "finish"}:
            motion = "session-sweep" if state_name == "final_lap" else "result"
        icon_name = state_name.replace("_", "-")
        rail_layers = state_rail_layers(templates[spec["template"]], rail, state_name, prefix)
        if not rail_layers:
            rail_layers = [common_rail_layer(root, config, state_name, rail)]
        state = {
            "template": spec["template"],
            "icon": f"icons/event/{prefix}-icon-{icon_name}.svg",
            "tone": tone,
            "rail": rail,
            "railLayers": rail_layers,
            "zone": spec["zone"],
            "lifecycle": lifecycle,
            "motion": motion,
            "reuseNote": spec["note"],
        }
        if state_name in {"hunted", "position_lost"}:
            state["criticalRail"] = "red"
            critical_layers = state_rail_layers(
                templates[spec["template"]], "red", state_name, prefix
            )
            state["criticalRailLayers"] = critical_layers or [
                common_rail_layer(root, config, state_name, "red")
            ]
        states[state_name] = state

    events: dict[str, Any] = OrderedDict()
    for event_name, route in catalog["entries"].items():
        event_route: dict[str, Any] = {"state": route["state"]}
        if event_name == "CPU_TEMP_HIGH":
            event_route["icon"] = f"icons/event/{prefix}-icon-cpu-temp-high.svg"
        elif event_name == "GPU_TEMP_HIGH":
            event_route["icon"] = f"icons/event/{prefix}-icon-gpu-temp-high.svg"
        events[event_name] = event_route

    state_glyphs = sorted({state["icon"] for state in states.values()})
    event_override_glyphs = sorted(
        {route["icon"] for route in events.values() if "icon" in route}
    )
    covered_glyphs = set(state_glyphs) | set(event_override_glyphs)
    utility_library = sorted(
        path.relative_to(root).as_posix()
        for path in (root / "icons" / "event").glob(f"{prefix}-icon-*.svg")
        if path.relative_to(root).as_posix() not in covered_glyphs
        and not path.name.endswith("-sprite.svg")
    )

    visual_map = {
        "schemaVersion": 2,
        "themeId": config["theme_id"],
        "contract": {
            "transient": [420, 140],
            "sysinfo": [1920, 72],
            "icon": [64, 64],
            "iconBox": config["icon_box"],
            "sysinfoGrid": {
                "brandWidth": 230,
                "moduleWidth": 150,
                "moduleCount": 11,
                "positions": DIVIDERS,
                "dataEndX": 1880,
                "trailingSafeWidth": 40,
            },
        },
        "tones": config["tones"],
        "iconPolicy": {
            "coverageContract": "state-map-exact",
            "requiredStateGlyphCount": 35,
            "stateGlyphs": state_glyphs,
            "eventOverrideGlyphs": event_override_glyphs,
            "utilityLibrary": utility_library,
            "crossThemeUtilityNameParityRequired": False,
            "coverageNote": "Only stateGlyphs satisfy the 35-state coverage contract. Event overrides and utilityLibrary are intentional extras and do not indicate a coverage gap.",
        },
        "rendererPolicy": {
            "templateResolution": {
                "precedence": [
                    "events.<event>.template",
                    "states.<state>.template",
                    "fallbacks.<family>",
                ],
                "runtimeFamilyMayOverride": False,
                "runtimeFamilyRole": "routing and lifecycle metadata only",
                "knownRuntimeFamilyExceptions": [
                    {
                        "state": "position_attack",
                        "runtimeFamily": "timing",
                        "packTemplate": "position",
                    }
                ],
            }
        },
        "zones": {
            "BATTLE_AHEAD": {
                "layout": "BATTLE",
                "template": "battle",
                "anchor": "bottom-left",
                "stackOrder": 0,
                "semantic": "opponent-ahead",
            },
            "BATTLE_BEHIND": {
                "layout": "BATTLE",
                "template": "battle",
                "anchor": "bottom-left",
                "stackOrder": 1,
                "semantic": "opponent-behind",
            },
            "EVENT": {"layout": "EVENT", "anchor": "bottom-right"},
            "SESSION": {"layout": "SESSION", "anchor": "top-center"},
            "BIO_EXPANDED": {"layout": "BIO_EXPANDED", "anchor": "top-right"},
        },
        "templates": templates,
        "states": states,
        "events": events,
        "fallbacks": catalog["fallbacks"],
    }
    write_text(
        root / "accents" / "event-visual-map.json",
        json.dumps(visual_map, indent=2, ensure_ascii=False),
    )


def motion_frame_svg(
    reel: str, frame: int, frame_count: int, config: dict[str, Any]
) -> str:
    is_dark = config["prefix"] == "pw"
    p = frame / max(frame_count - 1, 1)
    eased = p * p * (3 - (2 * p))
    pulse = math.sin(math.pi * p)
    opacity = max(0.0, pulse)
    primary = config["tones"]["primary"]["color"]
    timing = config["tones"]["timing"]["color"]
    warning = config["tones"]["warning"]["color"]
    critical = config["tones"]["critical"]["color"]
    positive = config["tones"]["positive"]["color"]
    bio = config["tones"]["bio"]["color"]
    neutral = config["tones"]["neutral"]["color"]
    icon_x, icon_y, icon_w, icon_h = config["icon_box"]
    cx = icon_x + (icon_w / 2)
    cy = icon_y + (icon_h / 2)
    silhouette = (
        "M12 8H394L412 26V114L394 132H12L4 124V16Z"
        if is_dark
        else "M22 8H388Q406 8 412 26V114Q406 132 388 132H22Q8 132 8 118V22Q8 8 22 8Z"
    )
    elements: list[str] = []

    def line(x1: float, y1: float, x2: float, y2: float, color: str, alpha: float, width: float = 2) -> None:
        elements.append(
            f'<line x1="{x1:.2f}" y1="{y1:.2f}" x2="{x2:.2f}" y2="{y2:.2f}" stroke="{color}" stroke-opacity="{max(0, min(alpha, 1)):.3f}" stroke-width="{width:.2f}" stroke-linecap="round"/>'
        )

    def circle(x: float, y: float, radius: float, color: str, alpha: float, width: float = 2, fill: str = "none") -> None:
        elements.append(
            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{max(radius, 0.1):.2f}" fill="{fill}" fill-opacity="{max(0, min(alpha * .18, 1)):.3f}" stroke="{color}" stroke-opacity="{max(0, min(alpha, 1)):.3f}" stroke-width="{width:.2f}"/>'
        )

    def rect(x: float, y: float, width: float, height: float, color: str, alpha: float, radius: float = 0) -> None:
        elements.append(
            f'<rect x="{x:.2f}" y="{y:.2f}" width="{max(width, .1):.2f}" height="{max(height, .1):.2f}" rx="{radius:.2f}" fill="{color}" fill-opacity="{max(0, min(alpha, 1)):.3f}"/>'
        )

    if reel == "enter_reveal":
        x = 10 + (400 * eased)
        line(x, 10, x, 130, primary, opacity * .95, 3 if is_dark else 2)
        line(12, 11, x, 11, primary, opacity * .55, 1.5)
        line(12, 129, x, 129, timing, opacity * .42, 1)
        rect(8, 130 - (120 * eased), 4 if is_dark else 3, 120 * eased, primary, opacity * .85, 1)
        for tick_x in range(24, 410, 24):
            if tick_x <= x:
                line(tick_x, 17, tick_x, 22 if is_dark else 20, primary, opacity * .48, 1)
        if not is_dark:
            rect(max(8, x - 24), 14, 24, 112, primary, opacity * .08, 12)
    elif reel == "theme_glitch":
        if is_dark:
            jitter = math.sin(frame * 2.7) * 9
            for index, y in enumerate((24, 46, 92, 116)):
                start = 112 + ((index * 57 + frame * 23) % 230) + jitter
                line(start, y, min(start + 34 + index * 7, 404), y, primary if index != 2 else warning, opacity * (.75 - index * .08), 2)
            rect(18 + ((frame * 31) % 62), 18, 2, 104, primary, opacity * .45)
        else:
            radius = 14 + (22 * eased)
            circle(cx, cy, radius, primary, opacity * .52, 1.5)
            circle(cx, cy, radius + 8, timing, opacity * .22, 1)
            for index, y in enumerate((22, 118)):
                start = 126 + ((frame * 37 + index * 73) % 210)
                line(start, y, min(start + 28, 400), y, primary, opacity * .30, 1.5)
    elif reel == "active_pulse":
        if is_dark:
            end = 120 + (250 * eased)
            line(120, 101, end, 101, timing, opacity * .65, 1.5)
            for index in range(5):
                x = 138 + (index * 48)
                if x < end:
                    line(x, 96, x, 106, primary, opacity * .38, 1)
            circle(end, 101, 3 + 3 * pulse, primary, opacity * .75, 1.5, primary)
        else:
            circle(cx, cy, 12 + (24 * eased), primary, opacity * .50, 1.5)
            rect(126, 103, 236 * eased, 2, timing, opacity * .18, 1)
    elif reel == "compact_mask":
        retract = 1 - eased
        for index, y in enumerate((27, 39, 112)):
            width = (188 - index * 22) * retract
            line(394 - width, y, 394, y, neutral, opacity * (.42 - index * .06), 1.5)
        for index in range(4):
            x = 132 + index * 17
            line(x, 112 - (10 * retract), x + 8, 102 - (10 * retract), primary, opacity * .26, 1)
    elif reel == "suspend_dim":
        rect(4, 8, 408, 124, neutral, opacity * (.16 if is_dark else .10), 10 if not is_dark else 0)
        for x in range(-60, 460, 26):
            line(x + (30 * eased), 132, x + 78 + (30 * eased), 8, neutral, opacity * .10, 1)
        line(10, 128, 410, 128, neutral, opacity * .26, 2)
    elif reel == "resume_reacquire":
        radius = 34 - (18 * eased)
        circle(cx, cy, radius, primary, opacity * .68, 2)
        circle(cx, cy, radius + 8, timing, opacity * .24, 1)
        x = 12 + (398 * eased)
        line(x, 16, x, 124, primary, opacity * .50, 1.5)
        rect(8, 106 - (88 * eased), 3, 88 * eased, primary, opacity * .70, 1)
    elif reel == "result_burst":
        radius = 10 + (36 * eased)
        ray_count = 12 if is_dark else 8
        for index in range(ray_count):
            angle = (math.tau * index / ray_count) + (0.12 if is_dark else 0)
            inner = radius * .68
            outer = radius
            line(cx + math.cos(angle) * inner, cy + math.sin(angle) * inner, cx + math.cos(angle) * outer, cy + math.sin(angle) * outer, positive if index % 3 == 0 else primary, opacity * .72, 1.5)
        circle(cx, cy, radius * .62, primary, opacity * (.52 if is_dark else .30), 2)
        if not is_dark:
            circle(cx, cy, radius * .86, positive, opacity * .18, 1)
    elif reel == "exit_trace":
        x = 410 - (400 * eased)
        line(x, 10, x, 130, primary, opacity * .82, 2.5 if is_dark else 1.5)
        line(x, 11, 408, 11, primary, opacity * .38, 1.5)
        line(x, 129, 408, 129, timing, opacity * .30, 1)
        rect(408, 18, 3, 104 * (1 - eased), primary, opacity * .46, 1)
    elif reel == "battle_signal_lock":
        radius = 30 - (14 * eased)
        circle(cx, cy, radius, primary, opacity * .58, 1.5)
        gap = 18 + (12 * (1 - eased))
        for sx, sy in ((-1, -1), (1, -1), (-1, 1), (1, 1)):
            bx = cx + sx * gap
            by = cy + sy * gap
            line(bx, by, bx - sx * 9, by, warning if sx > 0 else primary, opacity * .78, 2)
            line(bx, by, bx, by - sy * 9, warning if sx > 0 else primary, opacity * .78, 2)
        rect(398, 24 + (72 * (1 - eased)), 4, 72 * eased, warning, opacity * .70, 1)
    elif reel == "timing_projection_sweep":
        reveal = 116 + (282 * eased)
        points = [(116, 101), (154, 88), (192, 94), (232, 70), (276, 77), (322, 48), (398, 56)]
        visible = [point for point in points if point[0] <= reveal]
        for first, second in zip(visible, visible[1:], strict=False):
            line(first[0], first[1], second[0], second[1], timing, opacity * .74, 1.8)
        line(reveal, 24, reveal, 116, primary, opacity * .42, 1)
        for x, y in visible:
            circle(x, y, 2.5, primary, opacity * .72, 1, primary)
    elif reel == "position_chevron_hit":
        travel = 18 * (1 - eased)
        for index in range(3):
            x = 154 + index * 54 + travel
            alpha = opacity * (.42 + index * .16)
            elements.append(f'<path d="M{x:.2f} 48L{x + 20:.2f} 70L{x:.2f} 92" fill="none" stroke="{positive}" stroke-opacity="{alpha:.3f}" stroke-width="{3 if is_dark else 2.2}" stroke-linecap="round" stroke-linejoin="round"/>')
        line(126, 112, 352 * eased, 112, primary, opacity * .30, 1.5)
    elif reel == "exception_link_drop":
        dash = 220 * (1 - eased)
        fracture = "M112 22L160 49L144 67L218 82L203 112L266 96L306 122L350 88L402 112"
        elements.append(f'<path d="{fracture}" fill="none" stroke="{critical}" stroke-opacity="{opacity * .82:.3f}" stroke-width="{2.4 if is_dark else 1.8}" stroke-dasharray="220" stroke-dashoffset="{dash:.2f}" stroke-linecap="round" stroke-linejoin="round"/>')
        for index, y in enumerate((36, 104)):
            start = 248 + ((frame * 29 + index * 61) % 118)
            line(start, y, min(start + 22, 405), y, critical, opacity * .38, 1.5)
    elif reel == "pit_stop_ring":
        active_step = min(5, int(eased * 6))
        for index in range(6):
            x = 142 + index * 43
            alpha = opacity * (.82 if index == active_step else .24)
            color = positive if index <= active_step else warning
            circle(x, 112, 4 if index != active_step else 7, color, alpha, 1.5, color if index <= active_step else "none")
            if index < 5:
                line(x + 8, 112, x + 35, 112, positive if index < active_step else neutral, opacity * .28, 1.5)
        circle(cx, cy, 14 + (10 * pulse), warning, opacity * .38, 1.5)
    elif reel == "bio_pulse":
        reveal = 118 + (278 * eased)
        points = [(118, 78), (160, 78), (178, 62), (194, 98), (214, 48), (234, 78), (282, 78), (326, 69), (350, 78), (396, 78)]
        visible = [point for point in points if point[0] <= reveal]
        for first, second in zip(visible, visible[1:], strict=False):
            line(first[0], first[1], second[0], second[1], bio, opacity * .72, 1.8)
        circle(cx, cy, 12 + (14 * pulse), bio, opacity * .42, 1.5)
    elif reel == "session_finish_burst":
        path = "M12 10H394L410 26V114L394 130H12"
        dash_offset = 116 - (116 * eased)
        elements.append(f'<path d="{path}" pathLength="116" fill="none" stroke="{positive}" stroke-opacity="{opacity * .76:.3f}" stroke-width="{2.6 if is_dark else 2}" stroke-dasharray="22 94" stroke-dashoffset="{dash_offset:.2f}" stroke-linecap="round"/>')
        line(116, 118, 116 + (278 * eased), 118, primary, opacity * .24, 1.5)
    else:
        raise ValueError(f"Unknown motion reel: {reel}")

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="420" height="140" viewBox="0 0 420 140">
<defs><clipPath id="plate"><path d="{silhouette}"/></clipPath></defs>
<g clip-path="url(#plate)">{''.join(elements)}</g>
</svg>'''


def probe_webm(path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=codec_name,width,height,pix_fmt,r_frame_rate:stream_tags=alpha_mode:format=duration",
            "-of", "json", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    stream = payload["streams"][0]
    return {
        "codec": stream["codec_name"],
        "width": stream["width"],
        "height": stream["height"],
        "pixelFormat": stream["pix_fmt"],
        "fps": stream["r_frame_rate"],
        "alphaMode": stream.get("tags", {}).get("ALPHA_MODE"),
        "durationMs": round(float(payload["format"]["duration"]) * 1000),
    }


def build_motion_reels(root: Path, config: dict[str, Any]) -> dict[str, dict[str, Any]]:
    output_dir = root / "motion"
    output_dir.mkdir(parents=True, exist_ok=True)
    metadata: dict[str, dict[str, Any]] = OrderedDict()
    with tempfile.TemporaryDirectory(prefix=f"{config['prefix']}-motion-") as raw_temp:
        temp = Path(raw_temp)
        for reel_name, reel_spec in MOTION_REELS.items():
            frame_spec = reel_spec["frames"]
            frame_count = frame_spec[config["prefix"]] if isinstance(frame_spec, dict) else frame_spec
            frame_dir = temp / reel_name
            frame_dir.mkdir()
            for frame in range(frame_count):
                svg = frame_dir / f"frame-{frame:03d}.svg"
                png = frame_dir / f"frame-{frame:03d}.png"
                write_text(svg, motion_frame_svg(reel_name, frame, frame_count, config))
                subprocess.run(
                    ["convert", "-background", "none", str(svg), "-strip", "PNG32:" + str(png)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
            output = output_dir / f"{reel_name}.webm"
            subprocess.run(
                [
                    "ffmpeg", "-loglevel", "error", "-y", "-framerate", "30",
                    "-i", str(frame_dir / "frame-%03d.png"), "-an", "-c:v", "libvpx-vp9",
                    "-lossless", "1", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0",
                    "-row-mt", "0", "-threads", "1", "-deadline", "good", "-cpu-used", "0",
                    "-fflags", "+bitexact", "-map_metadata", "-1",
                    "-metadata:s:v:0", "alpha_mode=1",
                    str(output),
                ],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            probe = probe_webm(output)
            if probe != {
                "codec": "vp9",
                "width": 420,
                "height": 140,
                "pixelFormat": "yuv420p",
                "fps": "30/1",
                "alphaMode": "1",
                "durationMs": probe["durationMs"],
            }:
                raise RuntimeError(f"Invalid motion reel contract for {output}: {probe}")
            metadata[reel_name] = {
                "file": output.name,
                "durationMs": probe["durationMs"],
                "intent": reel_spec["intent"],
                "canvas": "transient",
                "fps": 30,
                "alpha": True,
            }
    return metadata


def build_motion_qa(root: Path, config: dict[str, Any], reels: dict[str, dict[str, Any]]) -> None:
    lines = [
        f'# {config["display_name"]} motion QA',
        "",
        "Generated and verified by `scripts/build_pit_wall_theme_additions.py`.",
        "",
        "| Reel | Size | Codec | Pixel format | Alpha | FPS | Duration | SHA-256 |",
        "|---|---:|---|---|---:|---:|---:|---|",
    ]
    for reel in reels.values():
        path = root / "motion" / reel["file"]
        probe = probe_webm(path)
        lines.append(
            f'| `{reel["file"]}` | {probe["width"]} x {probe["height"]} | {probe["codec"]} | {probe["pixelFormat"]} | {probe["alphaMode"]} | {probe["fps"]} | {probe["durationMs"]} ms | `{sha256(path)}` |'
        )
    lines.extend(
        [
            "",
            "All reels are one-shot, contain no text or numbers, and end on a transparent frame so the static plate remains authoritative.",
        ]
    )
    write_text(root / "references" / "docs" / "MOTION_QA.md", "\n".join(lines))


def build_motion(root: Path, config: dict[str, Any]) -> None:
    reels = build_motion_reels(root, config)
    motion = {
        "schemaVersion": 1,
        "themeId": config["theme_id"],
        "pipeline": "alpha-vp9",
        "fallback": "css",
        "webmNaming": "stem-without-extension",
        "webm": list(reels),
        "intents": {
            "enter": {"reels": ["enter_reveal", "theme_glitch"]},
            "active": {"reels": ["active_pulse"]},
            "result": {"reels": ["result_burst"]},
            "exit": {"reels": ["exit_trace"]},
            "pit-phase": {"reels": ["pit_stop_ring"]},
            "exception-alert": {"reels": ["exception_link_drop"]},
            "session-sweep": {"reels": ["session_finish_burst"]},
        },
        "reels": reels,
        "reducedMotion": {"maxDurationMs": 160, "disable": ["sweep", "trace-scroll", "flash"]},
    }
    write_text(root / "motion" / "manifest.json", json.dumps(motion, indent=2))
    build_motion_qa(root, config, reels)


def build_state_map_doc(root: Path, config: dict[str, Any]) -> None:
    visual_map = json.loads((root / "accents" / "event-visual-map.json").read_text())
    lines = [
        f'# {config["display_name"]} - V4 state visual map',
        "",
        "This is the human-readable mirror of `accents/event-visual-map.json`. The JSON file is authoritative for the renderer.",
        "",
        "| V4 state | Template | Icon | Tone / rail | Zone | Reuse decision |",
        "|---|---|---|---|---|---|",
    ]
    for state_name, state in visual_map["states"].items():
        icon = Path(state["icon"]).stem
        rail = state["rail"]
        if state_name == "battle_for_position":
            rail = "dual " + ("cyan + amber" if config["prefix"] == "pw" else "blue + amber")
        lines.append(
            f'| `{state_name}` | `{state["template"]}` | `{icon}` | `{state["tone"]}` / `{rail}` | `{state["zone"]}` | {state["reuseNote"]} |'
        )
    lines.extend(
        [
            "",
            "## Event and zone routing",
            "",
            "The same JSON also contains all 35 uppercase event routes from `themes-v4/event_catalog.json`. `BATTLE_AHEAD` and `BATTLE_BEHIND` are explicit aliases of the `BATTLE` layout; they differ only by semantic direction and stack order.",
            "",
            "CPU/GPU thermal events route to the `incident` state and override only the glyph (`cpu-temp-high` / `gpu-temp-high`).",
            "",
            "## Template resolution precedence",
            "",
            "The pack map, not the runtime family label, is authoritative for plate selection. Resolution order is an explicit event template override, then `states.<state>.template`, then the declared family fallback. Runtime family is routing/lifecycle metadata and must not replace a resolved pack template.",
            "",
            "`position_attack` is the known cross-family case: runtime family `timing`, pack template `position`. The renderer must render the POSITION plate and the state-specific glyph.",
            "",
            "## Icon coverage and utility library",
            "",
            "The 35-state coverage gate counts only `iconPolicy.stateGlyphs`. CPU/GPU temperature glyphs are event overrides. The remaining BLE, system, telemetry and generic status glyphs are an optional utility library and do not represent missing V4 states.",
            "",
            "Utility naming is theme-local by design. Dark may expose `memory` / `pressure`, while Light may expose `ram` / `vram` / `shield`; cross-theme utility-name parity is not required. State glyph naming remains exact and complete in both packs.",
        ]
    )
    write_text(root / "references" / "docs" / "STATE_VISUAL_MAP.md", "\n".join(lines))


def update_docs(root: Path, config: dict[str, Any]) -> None:
    readme = root / "README.md"
    readme_text = readme.read_text(encoding="utf-8")
    readme_text = readme_text.replace(
        "- motion is CSS fallback by design until an alpha-WebM pipeline is established.",
        "- 15 authoritative 420 x 140 alpha-VP9 motion reels in `motion/`; CSS remains a missing-file fallback only.",
    )
    if "MOTION_QA.md" not in readme_text:
        readme_text = readme_text.replace(
            "- 15 authoritative 420 x 140 alpha-VP9 motion reels in `motion/`; CSS remains a missing-file fallback only.",
            "- 15 authoritative 420 x 140 alpha-VP9 motion reels in `motion/`; CSS remains a missing-file fallback only;\n- ffprobe verification sheet: `references/docs/MOTION_QA.md`.",
        )
    write_text(readme, readme_text)

    implementation = root / "references" / "docs" / "IMPLEMENTATION.md"
    text = implementation.read_text(encoding="utf-8")
    text = text.replace("`tokens/event-visual-map.json`", "`accents/event-visual-map.json`")
    text = text.replace("assets/vector/ble-hr", "icons/ble-hr")
    text = text.replace(
        "- No repeatable WebM authoring pipeline exists in this pack. `motion/manifest.json` is authoritative and selects CSS fallback intent; no placeholder video is shipped.",
        "- All 15 V4 motion reels are authoritative 420 x 140 alpha-VP9 assets generated by the deterministic build script. CSS remains a missing-file fallback only.\n- State glyph coverage and the optional utility icon library are separate contracts. Utility names may differ between themes and do not count as a 35-state coverage gap.\n- Plate selection follows the pack map, not runtime family. In particular, `position_attack` resolves to the `position` template even though its runtime family is `timing`.",
    )
    text = text.replace(
        "- The repository contains compiled reference WebM reels for existing V4 themes, but no source motion project or deterministic export recipe for either Pit Wall theme. `motion/manifest.json` therefore selects the CSS fallback by design; unrelated compiled reels are not copied into this pack.",
        "- All 15 V4 motion reels are authoritative 420 x 140 alpha-VP9 assets generated by the deterministic build script. CSS remains a missing-file fallback only.",
    )
    appendix = f'''

## V4 art-pack completion (1.1.0)

- The authoritative 35-state map is `accents/event-visual-map.json`; the readable table is `references/docs/STATE_VISUAL_MAP.md`.
- `pit` and `exception` are real family templates with independent SVG layers and 1x/2x alpha raster exports in packages 03-05.
- Native transient geometry is 420 x 140. Individual cards must not be enlarged with CSS scale.
- Event glyph masters are 64 x 64 SVG. The exact icon box is `{config["icon_box"]}` (`[x,y,w,h]`).
- SYSINFO uses the runtime grid `brand 230 + 11 x 150`; x=1880..1920 stays as a trailing safe area.
- All 15 V4 motion reels are authoritative 420 x 140 alpha-VP9 assets generated by the deterministic build script. CSS remains a missing-file fallback only.
- State glyph coverage and the optional utility icon library are separate contracts. Utility names may differ between themes and do not count as a 35-state coverage gap.
- Plate selection follows the pack map, not runtime family. In particular, `position_attack` resolves to the `position` template even though its runtime family is `timing`.
'''
    if "## V4 art-pack completion (1.1.0)" not in text:
        text += appendix
    write_text(implementation, text)

    anchors = root / "references" / "docs" / "LAYERING_AND_ANCHORS.md"
    anchor_text = anchors.read_text(encoding="utf-8")
    anchor_text = re.sub(
        r"brand 230(?: px)?[^\n|]*",
        "brand 230; 11 data modules x 150; trailing safe area 40",
        anchor_text,
    )
    if "Authoritative icon box:" not in anchor_text:
        anchor_text += f"\n\nAuthoritative icon box: `{config['icon_box']}` (`[x,y,w,h]`).\n"
    write_text(anchors, anchor_text)

    naming = root / "references" / "docs" / "NAMING_CONVENTION.md"
    naming_text = naming.read_text(encoding="utf-8")
    if "`pit`" not in naming_text:
        naming_text += "\nAdded semantic scopes: `pit`, `exception`; state glyphs use the complete state stem, for example `pw-icon-pit-entry.svg` / `pl-icon-invalid-lap.svg`.\n"
    if "Utility icon parity" not in naming_text:
        naming_text += "\n## Utility icon parity\n\nExact cross-theme naming applies to the 35 state glyphs, not to the optional utility library. Dark-specific `memory` / `pressure` and Light-specific `ram` / `vram` / `shield` are intentional theme-local utilities. `iconPolicy` in the event visual map is authoritative for classifying state, event-override and utility icons.\n"
    write_text(naming, naming_text)

    for motion_doc in (root / "motion" / "MOTION.md", root / "references" / "docs" / "MOTION.md"):
        motion_text = motion_doc.read_text(encoding="utf-8")
        old_status = "No repeatable WebM authoring pipeline is established in this pack. `motion/manifest.json` therefore declares CSS fallback as authoritative. Reels may be added later only when alpha-VP9 export and deterministic verification are available; no placeholder WebM is included."
        interim_status = "This is a deliberate CSS fallback, not an accidental omission. The repository contains compiled alpha-VP9 reels for existing V4 themes, but no authoring sources or deterministic export script for either Pit Wall theme. Copying another theme's compiled motion would violate the Pit Wall visual language. `motion/manifest.json` records the decision and the gate for future WebM delivery: approved Pit Wall motion masters plus a reproducible alpha-VP9 exporter."
        new_status = "The 15 theme-specific reels in this directory are authoritative alpha-VP9 motion assets. They are generated reproducibly by `scripts/build_pit_wall_theme_additions.py`, use the native 420 x 140 canvas, contain no baked text or numbers, and end transparent so the static plate remains authoritative. CSS is retained only as a missing-file and reduced-motion fallback. See `references/docs/MOTION_QA.md` for the ffprobe matrix."
        if "WebM delivery status" not in motion_text:
            motion_text += f"\n## WebM delivery status\n\n{new_status}\n"
        else:
            motion_text = motion_text.replace(old_status, new_status)
            motion_text = motion_text.replace(interim_status, new_status)
        write_text(motion_doc, motion_text)

    build_state_map_doc(root, config)


def run_convert(source: Path, destination: Path, width: int, height: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    target = str(destination)
    if destination.suffix == ".png":
        target = "PNG32:" + target
    command = [
        "convert",
        "-background",
        "none",
        str(source),
        "-resize",
        f"{width}x{height}!",
        "-strip",
    ]
    if destination.suffix == ".webp":
        command += ["-define", "webp:lossless=true"]
    command.append(target)
    subprocess.run(command, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def deterministic_zip(source_root: Path, archive: Path) -> None:
    temp = archive.with_suffix(".tmp")
    with zipfile.ZipFile(temp, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in sorted(source_root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source_root).as_posix()
            info = zipfile.ZipInfo(relative, ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, path.read_bytes())
    temp.replace(archive)


def extract_archive(archive: Path, destination: Path) -> None:
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(destination)


def package_path(temp: Path, config: dict[str, Any], relative: str) -> Path:
    path = temp / config["package_dir"] / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def update_export_archives(root: Path, config: dict[str, Any]) -> None:
    archives = config["archives"]
    prefix = config["prefix"]
    package_dir = config["package_dir"]
    packages_dir = root / "packages"

    with tempfile.TemporaryDirectory(prefix="pit-wall-pack-") as raw_temp:
        temp_root = Path(raw_temp)

        # Core: authoritative tokens, map and machine-readable motion intent.
        core_dir = temp_root / "core"
        extract_archive(packages_dir / archives["core"], core_dir)
        shutil.copy2(root / "theme-tokens.json", package_path(core_dir, config, "tokens/design-tokens.json"))
        shutil.copy2(root / "accents" / "event-visual-map.json", package_path(core_dir, config, "tokens/event-visual-map.json"))
        shutil.copy2(root / "motion" / "manifest.json", package_path(core_dir, config, "tokens/motion-manifest.json"))
        deterministic_zip(core_dir, packages_dir / archives["core"])

        # Icons: SVG plus 1x/2x PNG and lossless WebP derivatives.
        icons_dir = temp_root / "icons"
        extract_archive(packages_dir / archives["icons"], icons_dir)
        for icon in sorted((root / "icons" / "event").glob(f"{prefix}-icon-*.svg")):
            shutil.copy2(icon, package_path(icons_dir, config, f"assets/vector/icons/{icon.name}"))
            for scale, size in (("1x", 64), ("2x", 128)):
                for fmt in ("png", "webp"):
                    destination = package_path(
                        icons_dir,
                        config,
                        f"assets/raster/{fmt}/{scale}/icons/{icon.stem}.{fmt}",
                    )
                    run_convert(icon, destination, size, size)
        deterministic_zip(icons_dir, packages_dir / archives["icons"])

        # Vector family templates.
        vector_dir = temp_root / "vector"
        extract_archive(packages_dir / archives["vector"], vector_dir)
        for family in ("pit", "exception"):
            for layer in sorted((root / "frames" / "templates" / family).glob("*.svg")):
                shutil.copy2(
                    layer,
                    package_path(
                        vector_dir, config, f"assets/vector/templates/{family}/{layer.name}"
                    ),
                )
        deterministic_zip(vector_dir, packages_dir / archives["vector"])

        # Individual 420x140 and 840x280 family layers (PNG + WebP).
        for scale, size, key in (
            ("1x", (420, 140), "raster_1x"),
            ("2x", (840, 280), "raster_2x"),
        ):
            raster_dir = temp_root / f"raster-{scale}"
            extract_archive(packages_dir / archives[key], raster_dir)
            for family in ("pit", "exception"):
                for layer in sorted((root / "frames" / "templates" / family).glob("*.svg")):
                    for fmt in ("png", "webp"):
                        destination = package_path(
                            raster_dir,
                            config,
                            f"assets/raster/{fmt}/{scale}/templates/{family}/{layer.stem}.{fmt}",
                        )
                        run_convert(layer, destination, *size)
            deterministic_zip(raster_dir, packages_dir / archives[key])

        # SYSINFO: replace only the divider layer and its 1x/2x derivatives.
        sysinfo_dir = temp_root / "sysinfo"
        extract_archive(packages_dir / archives["sysinfo"], sysinfo_dir)
        divider = root / "icons" / "sysinfo" / f"{prefix}-sysinfo-dividers.svg"
        shutil.copy2(
            divider,
            package_path(sysinfo_dir, config, f"assets/vector/sysinfo/{divider.name}"),
        )
        for scale, size in (("1x", (1920, 72)), ("2x", (3840, 144))):
            for fmt in ("png", "webp"):
                destination = package_path(
                    sysinfo_dir,
                    config,
                    f"assets/raster/{fmt}/{scale}/sysinfo/{divider.stem}.{fmt}",
                )
                run_convert(divider, destination, *size)
        deterministic_zip(sysinfo_dir, packages_dir / archives["sysinfo"])

        # Authoritative alpha-VP9 motion reel package.
        motion_dir = temp_root / "motion"
        for reel in sorted((root / "motion").glob("*.webm")):
            shutil.copy2(
                reel,
                package_path(motion_dir, config, f"assets/motion/{reel.name}"),
            )
        shutil.copy2(
            root / "motion" / "manifest.json",
            package_path(motion_dir, config, "assets/motion/manifest.json"),
        )
        shutil.copy2(
            root / "motion" / "MOTION.md",
            package_path(motion_dir, config, "assets/motion/MOTION.md"),
        )
        deterministic_zip(motion_dir, packages_dir / archives["motion"])

        # Documentation bundle and full source-package manifest.
        docs_dir = temp_root / "docs"
        extract_archive(packages_dir / archives["docs"], docs_dir)
        for doc in sorted((root / "references" / "docs").glob("*.md")):
            shutil.copy2(doc, package_path(docs_dir, config, f"docs/{doc.name}"))
        shutil.copy2(root / "motion" / "manifest.json", package_path(docs_dir, config, "docs/MOTION_MANIFEST.json"))

        union_dir = temp_root / "union"
        for key in (
            "core",
            "icons",
            "vector",
            "raster_1x",
            "raster_2x",
            "common_1x",
            "common_2x",
            "sysinfo",
            "motion",
        ):
            extract_archive(packages_dir / archives[key], union_dir)
        # Include docs/examples but ignore stale manifests before rebuilding them.
        for path in (docs_dir / package_dir).rglob("*"):
            if path.is_file() and "/manifests/" not in path.as_posix():
                destination = union_dir / package_dir / path.relative_to(docs_dir / package_dir)
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)

        package_root = union_dir / package_dir
        old_manifest = json.loads((root / "references" / "source-asset-manifest.json").read_text())
        rebuilt = rebuild_source_manifest(package_root, old_manifest, config)
        manifest_dir = docs_dir / package_dir / "manifests"
        manifest_dir.mkdir(parents=True, exist_ok=True)
        write_text(manifest_dir / "asset-manifest.json", json.dumps(rebuilt, indent=2, ensure_ascii=False))
        write_source_csv(manifest_dir / "asset-manifest.csv", rebuilt["assets"])
        write_source_sums(manifest_dir / "SHA256SUMS.txt", package_root)
        shutil.copy2(manifest_dir / "asset-manifest.json", root / "references" / "source-asset-manifest.json")
        deterministic_zip(docs_dir, packages_dir / archives["docs"])


def svg_dimensions(path: Path) -> tuple[int | None, int | None]:
    if path.suffix.lower() == ".svg":
        head = path.read_text(encoding="utf-8", errors="replace")[:1000]
        width = re.search(r'width="(\d+)"', head)
        height = re.search(r'height="(\d+)"', head)
        return (int(width.group(1)) if width else None, int(height.group(1)) if height else None)
    if path.suffix.lower() == ".png":
        data = path.read_bytes()[:26]
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", data[16:24])
    if path.suffix.lower() == ".webm":
        probe = probe_webm(path)
        return probe["width"], probe["height"]
    return None, None


def category_for(path: str) -> str:
    if path.startswith("assets/motion"):
        return "motion"
    if path.startswith("assets/vector/templates"):
        return "template-layer"
    if "/icons" in path or path.startswith("assets/vector/icons"):
        return "icon"
    if "sysinfo" in path:
        return "sysinfo"
    if path.startswith("tokens"):
        return "tokens"
    if path.startswith("docs") or path.endswith(".md"):
        return "documentation"
    if path.startswith("examples"):
        return "example"
    return "asset"


def rebuild_source_manifest(
    package_root: Path, old_manifest: dict[str, Any], config: dict[str, Any]
) -> dict[str, Any]:
    old_by_path = {entry["path"]: entry for entry in old_manifest.get("assets", [])}
    assets: list[dict[str, Any]] = []
    for path in sorted(package_root.rglob("*")):
        if not path.is_file() or "/manifests/" in path.as_posix():
            continue
        relative = path.relative_to(package_root).as_posix()
        entry = dict(old_by_path.get(relative, {}))
        width, height = svg_dimensions(path)
        entry.update(
            {
                "path": relative,
                "format": path.suffix.lower().lstrip("."),
                "category": entry.get("category", category_for(relative)),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "transparent": path.suffix.lower() in {".svg", ".png", ".webp", ".webm"},
            }
        )
        if width is not None:
            entry["width"] = width
        else:
            entry.setdefault("width", None)
        if height is not None:
            entry["height"] = height
        else:
            entry.setdefault("height", None)
        if config["prefix"] == "pl":
            entry.setdefault("logicalWidth", width)
            entry.setdefault("logicalHeight", height)
            entry.setdefault("scale", 1)
            entry.setdefault("anchor", "local:0,0")
            entry.setdefault("safeArea", {"x": 0, "y": 0, "width": width, "height": height})
            entry.setdefault("zIndex", 50)
            entry.setdefault("animationRole", "reusable-layer")
            entry.setdefault("stateColor", None)
        assets.append(entry)
    rebuilt = {
        "package": old_manifest.get("package", config["display_name"] + " Asset Package"),
        "version": "1.1.0",
        "assetCount": len(assets),
        "assets": assets,
    }
    if "themeId" in old_manifest:
        rebuilt["themeId"] = old_manifest["themeId"]
    return rebuilt


def write_source_csv(path: Path, assets: list[dict[str, Any]]) -> None:
    fields: list[str] = []
    for entry in assets:
        for key in entry:
            if key not in fields:
                fields.append(key)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for entry in assets:
            writer.writerow(
                {
                    key: json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value
                    for key, value in entry.items()
                }
            )


def write_source_sums(path: Path, package_root: Path) -> None:
    lines = []
    for file in sorted(package_root.rglob("*")):
        if file.is_file() and "/manifests/" not in file.as_posix():
            lines.append(f"{sha256(file)}  {file.relative_to(package_root).as_posix()}")
    write_text(path, "\n".join(lines))


def update_archive_index(root: Path) -> None:
    index_path = root / "packages" / "archive-index.json"
    index = json.loads(index_path.read_text(encoding="utf-8"))
    motion_archive = THEMES[root.name]["archives"]["motion"]
    if not any(entry["file"] == motion_archive for entry in index["archives"]):
        index["archives"].append(
            {
                "file": motion_archive,
                "contents": ["assets/motion"],
            }
        )
    for entry in index["archives"]:
        archive = root / "packages" / entry["file"]
        entry["bytes"] = archive.stat().st_size
        entry["sizeMiB"] = round(archive.stat().st_size / (1024 * 1024), 3)
        with zipfile.ZipFile(archive) as zf:
            entry["files"] = sum(not name.endswith("/") for name in zf.namelist())
            bad = zf.testzip()
        entry["sha256"] = sha256(archive)
        entry["integrity"] = "ok" if bad is None else f"failed:{bad}"
    write_text(index_path, json.dumps(index, indent=2, ensure_ascii=False))


def update_root_manifest(root: Path, config: dict[str, Any]) -> None:
    manifest_path = root / "manifest.json"
    existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path == manifest_path:
            continue
        relative = path.relative_to(root).as_posix()
        files.append({"path": relative, "bytes": path.stat().st_size, "sha256": sha256(path)})
    manifest = {
        "schema_version": 2,
        "theme_id": existing["theme_id"],
        "display_name": existing["display_name"],
        "base_commit": existing["base_commit"],
        "asset_root": existing["asset_root"],
        "renderer_contract": {
            "version": 4,
            "event_visual_map": "accents/event-visual-map.json",
            "theme_tokens": "theme-tokens.json",
            "motion": "motion/manifest.json",
            "transient_canvas": [420, 140],
            "sysinfo_canvas": [1920, 72],
            "icon_canvas": [64, 64],
            "icon_box": config["icon_box"],
        },
        "files": files,
    }
    write_text(manifest_path, json.dumps(manifest, indent=2, ensure_ascii=False))


def update_examples(root: Path, config: dict[str, Any]) -> None:
    css_path = next((root / "references" / "examples" / "css").glob("*.css"))
    css = css_path.read_text(encoding="utf-8")
    if config["prefix"] == "pl":
        css = re.sub(
            r"\.pl-icon\{[^}]+\}",
            ".pl-icon{position:absolute;z-index:30;left:39px;top:46px;width:48px;height:48px;color:var(--pl-state)}",
            css,
        )
        css = css.replace("grid-template-columns:repeat(10,minmax(0,1fr))", "grid-template-columns:repeat(11,150px)")
    else:
        css = css.replace(
            ".pw-icon{grid-row:1/4;align-self:center;width:40px;height:40px;color:var(--pw-state)}",
            ".pw-icon{position:absolute;left:0;top:32px;width:40px;height:40px;color:var(--pw-state)}",
        )
        css = css.replace("grid-template-columns:repeat(9,minmax(0,1fr))", "grid-template-columns:repeat(11,150px)")
    write_text(css_path, css)


def build_theme(theme_name: str, config: dict[str, Any]) -> None:
    root = PACKS_ROOT / theme_name
    build_icons(root, config)
    build_templates(root, config)
    update_sysinfo(root, config)
    update_tokens(root, config)
    build_event_map(root, config)
    build_motion(root, config)
    update_docs(root, config)
    update_examples(root, config)
    update_export_archives(root, config)
    update_archive_index(root)
    update_root_manifest(root, config)


def main() -> None:
    if shutil.which("convert") is None:
        raise SystemExit("ImageMagick 'convert' is required to build raster derivatives")
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        raise SystemExit("FFmpeg and ffprobe are required to build and verify motion reels")
    for theme_name, config in THEMES.items():
        build_theme(theme_name, config)
    print("Built Pit Wall Dark/Light V4 additions")


if __name__ == "__main__":
    main()
