"""Shared constants and helpers for V4 golden fixture tests."""

from __future__ import annotations

import json
import re
from pathlib import Path

from irswitch.overlay.http import web_root

GOLDEN_FIXTURE_COUNT = 33

GOLDEN_FIXTURES: tuple[str, ...] = (
    "lap_complete",
    "personal_best",
    "target",
    "projected_lap",
    "pb_attack",
    "hot_lap",
    "position_attack",
    "gain_found",
    "clean_streak",
    "hunting",
    "hunted",
    "approach",
    "attack_range",
    "side_by_side",
    "battle_for_position",
    "battle_won",
    "position_gained",
    "position_lost",
    "overtake",
    "rival_threat",
    "pit_entry",
    "pit_lane",
    "pit_stopped",
    "pit_released",
    "pit_exit",
    "pit_outcome",
    "hr_pressure",
    "ble_reconnecting",
    "final_lap",
    "finish",
    "incident",
    "invalid_lap",
    "link_drop",
)

_FIXTURE_ID_RE = re.compile(r"Fixture id:\s*`([a-z0-9_]+)`")
_V4_FIXTURE_EXPORT_RE = re.compile(r"export function (v4Fixture\w+)")
_V4_GOLDEN_CATALOG_ID_RE = re.compile(r'\{ id: "([a-z0-9_]+)"')


def catalog_path() -> Path:
    return web_root() / "themes-v4" / "event_catalog.json"


def golden_doc_path() -> Path:
    return web_root() / "overlay" / "GOLDEN_V4.md"


def display_v4_js() -> str:
    return (web_root() / "overlay" / "js" / "display-v4.js").read_text(encoding="utf-8")


def display_v4_css() -> str:
    return (web_root() / "overlay" / "css" / "display-v4.css").read_text(encoding="utf-8")


def v4_golden_catalog_ids(js: str | None = None) -> list[str]:
    source = js if js is not None else display_v4_js()
    start = source.index("export const V4_GOLDEN_CATALOG = [")
    end = source.index("];", start)
    return _V4_GOLDEN_CATALOG_ID_RE.findall(source[start:end])


def catalog_states() -> set[str]:
    catalog = json.loads(catalog_path().read_text(encoding="utf-8"))
    return {entry["state"] for entry in catalog["entries"].values()}


def fixture_id_pattern() -> re.Pattern[str]:
    return _FIXTURE_ID_RE


def fixture_export_pattern() -> re.Pattern[str]:
    return _V4_FIXTURE_EXPORT_RE
