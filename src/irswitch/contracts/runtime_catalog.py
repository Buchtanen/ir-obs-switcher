"""Explicit startup-only catalog composition; getters never read or write files."""

from dataclasses import replace
from pathlib import Path

from .catalog_loader import CatalogLoadResult, load_narrative_catalog
from .studio_definitions import DefinitionStore

_effective: CatalogLoadResult | None = None
_status: dict = {"effectiveRevision": "builtin", "startupError": None}


def initialize_runtime_catalog(path: Path) -> dict:
    global _effective, _status
    compiled, status = DefinitionStore(path).startup()
    base = load_narrative_catalog()
    _effective = replace(
        base,
        catalog=compiled,
        counts={
            **base.counts,
            "storyDefinitions": len(compiled.stories),
            "successorEdges": len(compiled.edges),
        },
    )
    _status = dict(status)
    return dict(status)


def load_runtime_catalog() -> CatalogLoadResult:
    return _effective if _effective is not None else load_narrative_catalog()


def runtime_definition_status() -> dict:
    return dict(_status)
