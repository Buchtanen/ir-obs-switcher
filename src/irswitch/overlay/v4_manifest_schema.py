"""Validate V4 overlay theme manifests (schema 2.x)."""

from __future__ import annotations

from typing import Any


def _is_positive_int_pair(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in value)
    )


def _validate_safe_box(path: str, safe_box: Any, size: Any, errors: list[str]) -> None:
    if not isinstance(safe_box, dict):
        errors.append(f"{path}.safe_box must be an object with left/top/right/bottom")
        return
    for key in ("left", "top", "right", "bottom"):
        if key not in safe_box:
            errors.append(f"{path}.safe_box missing {key}")
            continue
        if not isinstance(safe_box[key], int) or isinstance(safe_box[key], bool):
            errors.append(f"{path}.safe_box.{key} must be int")
        elif safe_box[key] < 0:
            errors.append(f"{path}.safe_box.{key} must be >= 0")
    if (
        _is_positive_int_pair(size)
        and all(k in safe_box for k in ("left", "top", "right", "bottom"))
        and all(
            isinstance(safe_box[k], int) and not isinstance(safe_box[k], bool)
            for k in ("left", "top", "right", "bottom")
        )
    ):
        if safe_box["left"] + safe_box["right"] >= size[0]:
            errors.append(f"{path}.safe_box horizontal insets exceed width")
        if safe_box["top"] + safe_box["bottom"] >= size[1]:
            errors.append(f"{path}.safe_box vertical insets exceed height")


def _validate_text_slots(path: str, text_slots: Any, size: Any, errors: list[str]) -> None:
    if not isinstance(text_slots, dict):
        errors.append(f"{path}.text_slots must be an object")
        return
    for slot_name, slot in text_slots.items():
        slot_path = f"{path}.text_slots.{slot_name}"
        if not isinstance(slot, dict):
            errors.append(f"{slot_path} must be an object")
            continue
        for key in ("left", "top", "right"):
            if key not in slot:
                errors.append(f"{slot_path} missing {key}")
            elif not isinstance(slot[key], int) or isinstance(slot[key], bool) or slot[key] < 0:
                errors.append(f"{slot_path}.{key} must be int >= 0")
        if "font_px" in slot and (
            not isinstance(slot["font_px"], int)
            or isinstance(slot["font_px"], bool)
            or slot["font_px"] < 1
        ):
            errors.append(f"{slot_path}.font_px must be int >= 1")
        if _is_positive_int_pair(size) and all(
            isinstance(slot.get(k), int) and not isinstance(slot.get(k), bool)
            for k in ("left", "top", "right")
        ):
            if slot["left"] + slot["right"] >= size[0]:
                errors.append(f"{slot_path} horizontal insets exceed canvas width")
            if slot["top"] >= size[1]:
                errors.append(f"{slot_path}.top out of canvas height")


def _validate_canvas_cfg(
    path: str, cfg: Any, *, inherit_size: Any = None, errors: list[str]
) -> None:
    if not isinstance(cfg, dict):
        errors.append(f"{path} must be an object")
        return
    size = cfg.get("size", inherit_size)
    if "size" in cfg and not _is_positive_int_pair(cfg["size"]):
        errors.append(f"{path}.size must be [w, h] positive ints")
    icon_mode = cfg.get("icon_mode")
    icon_box = cfg.get("icon_box")
    if icon_mode is not None and icon_mode not in {"full_canvas", "glyph"}:
        errors.append(f"{path}.icon_mode must be full_canvas|glyph, got {icon_mode!r}")
    if icon_mode == "full_canvas" and icon_box is not None:
        errors.append(f"{path}: icon_mode full_canvas forbids icon_box")
    if icon_mode == "glyph" and icon_box is None:
        errors.append(f"{path}: icon_mode glyph requires icon_box")
    if icon_box is not None:
        if not (
            isinstance(icon_box, (list, tuple))
            and len(icon_box) == 4
            and all(isinstance(v, int) and not isinstance(v, bool) for v in icon_box)
        ):
            errors.append(f"{path}.icon_box must be [x, y, w, h] ints")
        elif _is_positive_int_pair(size):
            x, y, w, h = icon_box
            if w <= 0 or h <= 0 or x < 0 or y < 0 or x + w > size[0] or y + h > size[1]:
                errors.append(f"{path}.icon_box out of bounds for size {list(size)}")
    if "safe_box" in cfg:
        _validate_safe_box(path, cfg["safe_box"], size, errors)
    if "text_slots" in cfg:
        _validate_text_slots(path, cfg["text_slots"], size, errors)


def merge_canvas_config(
    manifest: dict[str, Any],
    theme_id: str,
    canvas_id: str,
) -> dict[str, Any]:
    """Merge root ``canvases.<id>`` with ``themes.<theme>.canvases.<id>`` override."""
    root = dict((manifest.get("canvases") or {}).get(canvas_id) or {})
    theme_cfg = (manifest.get("themes") or {}).get(theme_id) or {}
    override = dict((theme_cfg.get("canvases") or {}).get(canvas_id) or {})
    merged = {**root, **override}
    if "size" not in merged or merged.get("size") is None:
        if canvas_id == "transient" and _is_positive_int_pair(manifest.get("transient_canvas")):
            merged["size"] = list(manifest["transient_canvas"])
        elif canvas_id == "sysinfo" and _is_positive_int_pair(manifest.get("sysinfo_canvas")):
            merged["size"] = list(manifest["sysinfo_canvas"])
    return merged


def validate_v4_manifest(manifest: dict[str, Any]) -> list[str]:
    """Return human-readable errors; empty list means the manifest is usable."""
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
            _validate_canvas_cfg(f"canvases.{canvas_id}", cfg, errors=errors)

    themes = manifest.get("themes")
    if not isinstance(themes, dict) or not themes:
        errors.append("themes must be a non-empty object")
    elif isinstance(themes, dict):
        for theme_id, theme_cfg in themes.items():
            if not isinstance(theme_cfg, dict):
                errors.append(f"themes.{theme_id} must be an object")
                continue
            theme_canvases = theme_cfg.get("canvases")
            if theme_canvases is None:
                continue
            if not isinstance(theme_canvases, dict):
                errors.append(f"themes.{theme_id}.canvases must be an object")
                continue
            for canvas_id, override in theme_canvases.items():
                root_cfg = (canvases or {}).get(canvas_id) if isinstance(canvases, dict) else {}
                inherit_size = None
                if isinstance(root_cfg, dict):
                    inherit_size = root_cfg.get("size")
                if inherit_size is None and canvas_id == "transient":
                    inherit_size = transient
                if inherit_size is None and canvas_id == "sysinfo":
                    inherit_size = sysinfo
                # Validate merged exclusivity (override icon_mode vs root icon_box).
                merged = dict(root_cfg or {})
                if isinstance(override, dict):
                    merged.update(override)
                _validate_canvas_cfg(
                    f"themes.{theme_id}.canvases.{canvas_id}",
                    merged,
                    inherit_size=inherit_size,
                    errors=errors,
                )

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
