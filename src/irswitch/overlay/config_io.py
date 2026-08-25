"""Atomic INI updates for overlay dotted keys. Never writes secrets from GET."""

from __future__ import annotations

import configparser
import shutil
from pathlib import Path
from typing import Any

from irswitch.overlay.schema import FieldSpec, coerce_value, field_by_key


def _section_and_option(spec: FieldSpec) -> tuple[str, str]:
    """Last dotted segment is the option name; rest is the INI section."""
    if "." not in spec.key:
        return spec.section, spec.key
    option = spec.key.rsplit(".", 1)[1]
    return spec.section, option


def apply_overlay_values(path: Path, values: dict[str, Any]) -> list[str]:
    """
    Update overlay keys in ``path``. Returns sorted list of applied keys.

    Writes a ``.bak`` next to the file first. Unknown keys are rejected.
    """
    applied: list[str] = []
    unknown = [key for key in values if field_by_key(key) is None]
    if unknown:
        raise ValueError(f"Unknown config keys: {', '.join(sorted(unknown))}")

    parser = configparser.ConfigParser()
    parser.read(path, encoding="utf-8")

    coerced: dict[str, tuple[FieldSpec, Any]] = {}
    for key, raw in values.items():
        spec = field_by_key(key)
        if spec is None:
            continue
        coerced[key] = (spec, coerce_value(spec, raw))

    if path.exists():
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))

    for key, (spec, value) in coerced.items():
        section, option = _section_and_option(spec)
        if not parser.has_section(section):
            parser.add_section(section)
        if value is None:
            parser.remove_option(section, option)
            if not parser.options(section):
                parser.remove_section(section)
        elif isinstance(value, bool):
            parser.set(section, option, "true" if value else "false")
        else:
            parser.set(section, option, str(value))
        applied.append(key)

    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        parser.write(handle)
    tmp.replace(path)
    return sorted(applied)
