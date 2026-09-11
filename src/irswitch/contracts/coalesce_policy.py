"""Canonical health/deadline coalesce field paths for NarrativeCommand.

Mailbox admission, ``NarrativeCommand.coalesce_key``, and the branch-only
actor-transition model must share this exact allowlist. APPLY_CONTEXT_BATCH
never coalesces and is intentionally absent.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

# Deadline coalescing: same kind + generation (or exact realization token).
DEADLINE_COALESCE_FIELDS: dict[str, tuple[str, ...]] = {
    "LONG_SILENCE_ELAPSED": ("kind", "token.generation"),
    "VALIDITY_DEADLINE_ELAPSED": ("kind", "token.generation"),
    "REALIZATION_DEADLINE_ELAPSED": (
        "kind",
        "token.requestId",
        "token.requestOrdinal",
        "token.dispatchGeneration",
    ),
}

# Health coalescing: identical generation/status (and detector set for tape).
HEALTH_COALESCE_FIELDS: dict[str, tuple[str, ...]] = {
    "TAPE_HEALTH_CHANGED": (
        "kind",
        "payload.recorderGeneration",
        "payload.status",
        "payload.affectedDetectorIds",
    ),
    "COMPONENT_HEALTH_CHANGED": (
        "kind",
        "payload.component",
        "payload.generation",
        "payload.status",
    ),
}

# Single closed allowlist — health and deadline lists are the identical source.
COALESCE_FIELD_PATHS: dict[str, tuple[str, ...]] = {
    **DEADLINE_COALESCE_FIELDS,
    **HEALTH_COALESCE_FIELDS,
}


def coalesce_key_for(
    kind: str,
    *,
    token: Mapping[str, Any] | None,
    payload: Mapping[str, Any] | None,
) -> tuple[object, ...] | None:
    """Resolve the mailbox coalesce key for ``kind`` from token/payload maps."""

    fields = COALESCE_FIELD_PATHS.get(kind)
    if fields is None:
        return None
    token_map = token or {}
    payload_map = payload or {}
    values: list[object] = []
    for path in fields:
        if path == "kind":
            values.append(kind)
            continue
        root, _, key = path.partition(".")
        source: Mapping[str, Any] = token_map if root == "token" else payload_map
        value: object = source.get(key)
        if key == "affectedDetectorIds":
            value = tuple(value or ())
        values.append(value)
    return tuple(values)
