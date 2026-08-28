"""V4 event catalog: eventType ↔ manifest state mapping."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, cast

from irswitch.overlay.http import web_root

_CATALOG_REL = Path("themes-v4") / "event_catalog.json"
_MANIFEST_REL = Path("themes-v4") / "manifest.json"


def catalog_path() -> Path:
    return web_root() / _CATALOG_REL


def manifest_path() -> Path:
    return web_root() / _MANIFEST_REL


@lru_cache(maxsize=1)
def load_event_catalog() -> dict[str, Any]:
    data = json.loads(catalog_path().read_text(encoding="utf-8"))
    return cast(dict[str, Any], data)


@lru_cache(maxsize=1)
def load_v4_manifest() -> dict[str, Any]:
    data = json.loads(manifest_path().read_text(encoding="utf-8"))
    return cast(dict[str, Any], data)


def catalog_entries() -> dict[str, dict[str, Any]]:
    return dict(load_event_catalog().get("entries") or {})


def catalog_fallbacks() -> dict[str, str]:
    return dict(load_event_catalog().get("fallbacks") or {})


def state_for_event_type(event_type: str) -> str | None:
    """Resolve manifest state key for a wire ``eventType``."""
    key = event_type.strip().upper()
    entry = catalog_entries().get(key)
    if entry is not None:
        return str(entry["state"])
    fallback = catalog_fallbacks().get(key)
    return fallback


def debug_key_for_event_type(event_type: str) -> str | None:
    key = event_type.strip().upper()
    entry = catalog_entries().get(key)
    if entry is None:
        return None
    return str(entry.get("debug_key") or "")


def event_type_for_debug_key(debug_key: str) -> str | None:
    for event_type, entry in catalog_entries().items():
        if entry.get("debug_key") == debug_key:
            return event_type
    return None
