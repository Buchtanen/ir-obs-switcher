"""Validate V4 overlay theme manifests (Phase 0 groundwork for schema 2.x)."""

from __future__ import annotations

from typing import Any


def _is_positive_int_pair(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in value)
    )


def validate_v4_manifest(manifest: dict[str, Any]) -> list[str]:
    """Return human-readable errors; empty list means the manifest is usable today.

    Accepts the shipped schema (``version`` + canvas aliases + themes/states/motions)
    and optionally future ``manifest_schema`` / ``canvases`` / ``zones`` keys without
    requiring them yet.
    """
    errors: list[str] = []
    if not isinstance(manifest, dict):
        return ["manifest root must be an object"]

    version = manifest.get("version")
    if version != 4:
        errors.append(f"version must be 4, got {version!r}")

    schema = manifest.get("manifest_schema")
    if schema is not None:
        if (
            not isinstance(schema, (list, tuple))
            or len(schema) != 2
            or not all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in schema)
        ):
            errors.append("manifest_schema must be [major, minor] non-negative integers")
        elif int(schema[0]) > 2:
            errors.append(f"unsupported manifest_schema major {schema[0]} (max supported 2)")

    transient = manifest.get("transient_canvas")
    sysinfo = manifest.get("sysinfo_canvas")
    canvases = manifest.get("canvases")

    if transient is None and not (isinstance(canvases, dict) and "transient" in canvases):
        errors.append("missing transient_canvas (or canvases.transient)")
    elif transient is not None and not _is_positive_int_pair(transient):
        errors.append(f"transient_canvas must be [w, h] positive ints, got {transient!r}")

    if sysinfo is None and not (isinstance(canvases, dict) and "sysinfo" in canvases):
        errors.append("missing sysinfo_canvas (or canvases.sysinfo)")
    elif sysinfo is not None and not _is_positive_int_pair(sysinfo):
        errors.append(f"sysinfo_canvas must be [w, h] positive ints, got {sysinfo!r}")

    if isinstance(canvases, dict):
        for canvas_id, cfg in canvases.items():
            if not isinstance(cfg, dict):
                errors.append(f"canvases.{canvas_id} must be an object")
                continue
            size = cfg.get("size")
            if size is not None and not _is_positive_int_pair(size):
                errors.append(f"canvases.{canvas_id}.size must be [w, h] positive ints")
            icon_mode = cfg.get("icon_mode")
            icon_box = cfg.get("icon_box")
            if icon_mode is not None and icon_mode not in {"full_canvas", "glyph"}:
                errors.append(
                    f"canvases.{canvas_id}.icon_mode must be full_canvas|glyph, got {icon_mode!r}"
                )
            if icon_mode == "full_canvas" and icon_box is not None:
                errors.append(f"canvases.{canvas_id}: icon_mode full_canvas forbids icon_box")
            if icon_mode == "glyph" and icon_box is None:
                errors.append(f"canvases.{canvas_id}: icon_mode glyph requires icon_box")
            if icon_box is not None:
                if not (
                    isinstance(icon_box, (list, tuple))
                    and len(icon_box) == 4
                    and all(isinstance(v, int) and not isinstance(v, bool) for v in icon_box)
                ):
                    errors.append(f"canvases.{canvas_id}.icon_box must be [x, y, w, h] ints")
                elif size is not None and _is_positive_int_pair(size):
                    x, y, w, h = icon_box
                    if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > size[0] or y + h > size[1]:
                        errors.append(
                            f"canvases.{canvas_id}.icon_box out of bounds for size {list(size)}"
                        )

    themes = manifest.get("themes")
    if not isinstance(themes, dict) or not themes:
        errors.append("themes must be a non-empty object")

    states = manifest.get("states")
    if not isinstance(states, dict) or not states:
        errors.append("states must be a non-empty object")
    elif isinstance(themes, dict):
        for state, meta in states.items():
            if not isinstance(meta, dict):
                errors.append(f"states.{state} must be an object")
                continue
            family = meta.get("family")
            if not family:
                errors.append(f"states.{state} missing family")
                continue
            for theme_id, theme_cfg in themes.items():
                if not isinstance(theme_cfg, dict):
                    continue
                families = theme_cfg.get("families") or {}
                if family not in families:
                    errors.append(f"states.{state} family {family!r} missing in themes.{theme_id}")

    zones = manifest.get("zones")
    if zones is not None:
        if not isinstance(zones, dict):
            errors.append("zones must be an object")
        else:
            for zone_id, zone in zones.items():
                if not isinstance(zone, dict):
                    errors.append(f"zones.{zone_id} must be an object")
                    continue
                if "max" in zone:
                    max_items = zone["max"]
                    if (
                        not isinstance(max_items, int)
                        or isinstance(max_items, bool)
                        or max_items < 1
                    ):
                        errors.append(f"zones.{zone_id}.max must be int >= 1")

    motions = manifest.get("motions")
    if motions is None:
        errors.append("motions missing")
    elif isinstance(motions, list):
        if not all(isinstance(m, str) and m for m in motions):
            errors.append("motions list entries must be non-empty strings")
    elif isinstance(motions, dict):
        if not all(isinstance(k, str) and k for k in motions):
            errors.append("motions map keys must be non-empty strings")
    else:
        errors.append("motions must be a list or object")

    return errors
