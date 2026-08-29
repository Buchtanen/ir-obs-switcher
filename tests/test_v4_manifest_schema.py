"""Phase 0: V4 manifest schema validator groundwork."""

from __future__ import annotations

import copy
import json

import pytest

from irswitch.overlay.http import web_root
from irswitch.overlay.v4_manifest_schema import validate_v4_manifest


def _shipped() -> dict:
    return json.loads((web_root() / "themes-v4" / "manifest.json").read_text(encoding="utf-8"))


def test_shipped_v4_manifest_validates() -> None:
    errors = validate_v4_manifest(_shipped())
    assert errors == []


def test_rejects_wrong_version() -> None:
    man = _shipped()
    man["version"] = 3
    assert any("version" in e for e in validate_v4_manifest(man))


def test_rejects_invalid_transient_canvas() -> None:
    man = _shipped()
    man["transient_canvas"] = [420]
    assert any("transient_canvas" in e for e in validate_v4_manifest(man))
    man["transient_canvas"] = [420, -1]
    assert any("transient_canvas" in e for e in validate_v4_manifest(man))


def test_rejects_unknown_schema_major() -> None:
    man = _shipped()
    man["manifest_schema"] = [9, 0]
    assert any("manifest_schema" in e for e in validate_v4_manifest(man))


def test_accepts_future_canvases_full_canvas() -> None:
    man = _shipped()
    man["manifest_schema"] = [2, 0]
    man["canvases"] = {
        "transient": {"size": [420, 140], "icon_mode": "full_canvas"},
        "sysinfo": {"size": [1920, 72], "icon_mode": "glyph", "icon_box": [0, 0, 32, 32]},
    }
    assert validate_v4_manifest(man) == []


def test_rejects_full_canvas_with_icon_box() -> None:
    man = _shipped()
    man["canvases"] = {
        "transient": {
            "size": [420, 140],
            "icon_mode": "full_canvas",
            "icon_box": [28, 38, 64, 64],
        }
    }
    errors = validate_v4_manifest(man)
    assert any("forbids icon_box" in e for e in errors)


def test_rejects_glyph_without_icon_box() -> None:
    man = _shipped()
    man["canvases"] = {"transient": {"size": [420, 140], "icon_mode": "glyph"}}
    errors = validate_v4_manifest(man)
    assert any("requires icon_box" in e for e in errors)


def test_rejects_icon_box_out_of_bounds() -> None:
    man = _shipped()
    man["canvases"] = {
        "transient": {
            "size": [420, 140],
            "icon_mode": "glyph",
            "icon_box": [400, 100, 64, 64],
        }
    }
    errors = validate_v4_manifest(man)
    assert any("out of bounds" in e for e in errors)


def test_rejects_state_family_missing_from_theme() -> None:
    man = copy.deepcopy(_shipped())
    theme = next(iter(man["themes"]))
    del man["themes"][theme]["families"]["pit"]
    errors = validate_v4_manifest(man)
    assert any("pit" in e and theme in e for e in errors)


def test_accepts_motions_as_map() -> None:
    man = _shipped()
    man["motions"] = {name: {"canvas": "transient"} for name in man["motions"]}
    assert validate_v4_manifest(man) == []


@pytest.mark.parametrize(
    "zones",
    [
        {"battle": {"max": 2}, "event": {"max": 6}},
        {"battle": {"max": 2}, "event": {"max": 1}},
    ],
)
def test_accepts_zones_with_positive_max(zones: dict) -> None:
    man = _shipped()
    man["zones"] = zones
    assert validate_v4_manifest(man) == []


def test_rejects_zone_max_below_one() -> None:
    man = _shipped()
    man["zones"] = {"event": {"max": 0}}
    assert any("max" in e for e in validate_v4_manifest(man))
