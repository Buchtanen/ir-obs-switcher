"""Bounded declarative composition of certified narrative definitions.

Frozen loader/goldens remain authoritative for beats, guards and realization.
Studio may compose stories and select certified edges, never supply code/guards.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import tempfile
from dataclasses import asdict, replace
from pathlib import Path
from threading import RLock
from typing import Any

from .catalog_loader import NarrativeCatalog, StoryDefinition, load_narrative_catalog

SCHEMA = "studio-definitions/1"
MAX_DOCUMENT_BYTES = 128 * 1024
MAX_REVISIONS = 32
_LOCK = RLock()


class DefinitionError(ValueError):
    pass


class RevisionConflict(DefinitionError):
    pass


def _bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise DefinitionError("Document must contain finite JSON values") from exc


def _digest(value: Any) -> str:
    return hashlib.sha256(_bytes(value)).hexdigest()


def default_document() -> dict[str, Any]:
    base = load_narrative_catalog().require_catalog()
    return {
        "schemaVersion": SCHEMA,
        "baseCatalogHash": base.catalog_hash,
        "stories": [asdict(row) for row in base.stories],
        "edges": [asdict(row) for row in base.edges],
    }


def _int(value: Any, low: int, high: int, name: str) -> int:
    if type(value) is not int or not low <= value <= high:
        raise DefinitionError(f"{name}: expected integer {low}..{high}")
    return value


def compile_document(document: Any) -> NarrativeCatalog:
    if not isinstance(document, dict) or set(document) != {
        "schemaVersion",
        "baseCatalogHash",
        "stories",
        "edges",
    }:
        raise DefinitionError("Unknown or missing document fields")
    if len(_bytes(document)) > MAX_DOCUMENT_BYTES:
        raise DefinitionError("Document too large")
    base = load_narrative_catalog().require_catalog()
    if document["schemaVersion"] != SCHEMA or document["baseCatalogHash"] != base.catalog_hash:
        raise DefinitionError("Incompatible schema or base catalog hash")
    rows, edge_rows = document["stories"], document["edges"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= 64 or not isinstance(edge_rows, list):
        raise DefinitionError("Expected 1..64 stories and an edge list")
    certified = {row.id: row for row in base.edges}
    edges = []
    seen_edges: set[str] = set()
    for edge in edge_rows:
        if not isinstance(edge, dict) or not isinstance(edge.get("id"), str):
            raise DefinitionError("Invalid edge")
        known = certified.get(edge["id"])
        # Guard satisfiability is certified for this pair only, not arbitrary rewiring.
        if known is None or _bytes(edge) != _bytes(asdict(known)) or known.id in seen_edges:
            raise DefinitionError(
                "Edge must be a unique certified connection; custom guards/cycles are unsupported"
            )
        seen_edges.add(known.id)
        edges.append(known)
    base_stories = {row.id: row for row in base.stories}
    beat_map = {row.id: row for row in base.beats}
    fields = set(asdict(base.stories[0]))
    seen: set[str] = set()
    stories = []
    for row in rows:
        if not isinstance(row, dict) or set(row) != fields:
            raise DefinitionError("Invalid story fields")
        identifier = row["id"]
        if (
            not isinstance(identifier, str)
            or not re.fullmatch(r"[a-z][a-z0-9_.-]{0,63}", identifier)
            or identifier.casefold() in seen
        ):
            raise DefinitionError("Invalid or duplicate story ID")
        seen.add(identifier.casefold())
        _int(row["cadence_minimum_ms"], 0, 3_600_000, "cadence_minimum_ms")
        _int(row["max_consecutive_non_closing_beats"], 1, 16, "max_consecutive_non_closing_beats")
        if row["on_no_eligible_successor"] not in {
            s.on_no_eligible_successor for s in base.stories
        }:
            raise DefinitionError("Unknown no-successor policy")
        members: list[str] = []
        for field in ("open_beat_ids", "update_beat_ids", "close_beat_ids"):
            values = row[field]
            if (
                not isinstance(values, (tuple, list))
                or any(not isinstance(v, str) or v not in beat_map for v in values)
                or len(values) != len(set(values))
            ):
                raise DefinitionError(f"Unknown or duplicate beat in {field}")
            members.extend(values)
        if not members or len(members) != len(set(members)):
            raise DefinitionError("Story requires unique beat membership")
        # Preserve each certified beat role; no detector or realization semantics change.
        for field in ("open_beat_ids", "update_beat_ids", "close_beat_ids"):
            known_roles = {beat_map[v].role for s in base.stories for v in getattr(s, field)}
            if any(beat_map[v].role not in known_roles for v in row[field]):
                raise DefinitionError(f"Beat role incompatible with {field}")
        supplied = row["successor_edge_ids"]
        expected = {e.id for e in edges if e.from_beat_id in members and e.to_beat_id in members}
        if (
            not isinstance(supplied, (tuple, list))
            or any(not isinstance(v, str) for v in supplied)
            or len(supplied) != len(set(supplied))
            or set(supplied) != expected
        ):
            raise DefinitionError(
                "Story successor_edge_ids must match its selected certified edges"
            )
        if identifier not in base_stories and (
            not row["open_beat_ids"] or not row["close_beat_ids"]
        ):
            raise DefinitionError("New occurrence stories require opening and closing beats")
        original = base_stories.get(identifier)
        if original is None or _bytes(row) != _bytes(asdict(original)):
            reachable = set(row["close_beat_ids"])
            while True:
                expanded = reachable | {
                    e.from_beat_id for e in edges if e.id in expected and e.to_beat_id in reachable
                }
                if expanded == reachable:
                    break
                reachable = expanded
            if not set(row["open_beat_ids"]) <= reachable:
                raise DefinitionError(
                    "Edited story openings must reach a closing beat through certified edges"
                )
            if any(v not in reachable and not beat_map[v].triggers for v in row["update_beat_ids"]):
                raise DefinitionError("Unreachable nonterminal beat without an external trigger")
        if identifier not in base_stories and not any(beat_map[v].triggers for v in members):
            raise DefinitionError("New story has no registered trigger")
        stories.append(
            StoryDefinition(
                **{
                    **row,
                    **{
                        k: tuple(row[k])
                        for k in (
                            "open_beat_ids",
                            "update_beat_ids",
                            "close_beat_ids",
                            "successor_edge_ids",
                        )
                    },
                }
            )
        )
    if not set(base_stories) <= {s.id for s in stories}:
        raise DefinitionError("Built-in story IDs cannot be removed")
    # Every baseline beat must retain at least one story route.
    routes = {
        beat.id: tuple(
            s.id
            for s in stories
            if beat.id in (*s.open_beat_ids, *s.update_beat_ids, *s.close_beat_ids)
        )
        for beat in base.beats
    }
    if any(not ids for ids in routes.values()):
        raise DefinitionError("Unreachable beat: every beat needs a story route")
    beats = tuple(
        replace(
            beat,
            story_routes=routes[beat.id],
            successor_edge_ids=tuple(e.id for e in edges if e.from_beat_id == beat.id),
        )
        for beat in base.beats
    )
    events = tuple(
        replace(event, story_routes=tuple(sorted({s for b in event.beat_ids for s in routes[b]})))
        for event in base.event_routes
    )
    # catalog_hash identifies immutable beat/realization content. Studio revision is separate.
    return replace(
        base, stories=tuple(stories), beats=beats, edges=tuple(edges), event_routes=events
    )


class DefinitionStore:
    def __init__(self, path: Path):
        self.path = path

    def _read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "schemaVersion": "studio-revisions/1",
                "baseRevision": 0,
                "pendingRevision": "builtin",
                "effectiveRevision": "builtin",
                "revisions": [],
            }
        if self.path.stat().st_size > 5 * 1024 * 1024:
            raise DefinitionError("Revision store too large")
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if (
                data["schemaVersion"] != "studio-revisions/1"
                or type(data["baseRevision"]) is not int
                or not isinstance(data["revisions"], list)
                or len(data["revisions"]) > MAX_REVISIONS
            ):
                raise DefinitionError("Invalid revision store")
            required = {
                "schemaVersion",
                "baseRevision",
                "pendingRevision",
                "effectiveRevision",
                "revisions",
            }
            if set(data) != required or data["baseRevision"] < 0:
                raise DefinitionError("Invalid store fields")
            for key in ("pendingRevision", "effectiveRevision"):
                identifier = data[key]
                if not isinstance(identifier, str) or not (
                    identifier == "builtin" or re.fullmatch(r"[0-9a-f]{64}", identifier)
                ):
                    raise DefinitionError("Invalid revision reference")
            identifiers = set()
            for row in data["revisions"]:
                if (
                    not isinstance(row, dict)
                    or set(row) != {"id", "document"}
                    or not isinstance(row["id"], str)
                    or not re.fullmatch(r"[0-9a-f]{64}", row["id"])
                    or not isinstance(row["document"], dict)
                    or row["id"] in identifiers
                ):
                    raise DefinitionError("Invalid revision row")
                identifiers.add(row["id"])
            return dict(data)
        except (ValueError, KeyError, TypeError, RecursionError) as exc:
            raise DefinitionError("Invalid revision store") from exc

    def _write(self, state: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix=".studio-", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(_bytes(state))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(name, self.path)
        finally:
            if os.path.exists(name):
                os.unlink(name)

    def snapshot(self) -> dict[str, Any]:
        with _LOCK:
            return copy.deepcopy({**self._read(), "builtin": default_document()})

    def _check(self, state: dict[str, Any], base_revision: Any) -> None:
        if type(base_revision) is not int or state["baseRevision"] != base_revision:
            raise RevisionConflict("Revision changed; reread and reconcile the draft")

    def save(self, document: Any, *, base_revision: int) -> dict[str, Any]:
        compile_document(document)
        with _LOCK:
            state = self._read()
            self._check(state, base_revision)
            identifier = _digest(document)
            if not any(row["id"] == identifier for row in state["revisions"]):
                while len(state["revisions"]) >= MAX_REVISIONS:
                    victim = next(
                        (
                            row
                            for row in state["revisions"]
                            if row["id"]
                            not in (state["pendingRevision"], state["effectiveRevision"])
                        ),
                        None,
                    )
                    if victim is None:
                        raise DefinitionError("Revision capacity reached")
                    state["revisions"].remove(victim)
                state["revisions"].append({"id": identifier, "document": copy.deepcopy(document)})
            state["baseRevision"] += 1
            self._write(state)
            return {**self.snapshot(), "savedRevision": identifier}

    def _document(self, state: dict[str, Any], identifier: str) -> dict[str, Any]:
        if identifier == "builtin":
            return default_document()
        row = next((r for r in state["revisions"] if r["id"] == identifier), None)
        if row is None or _digest(row["document"]) != identifier:
            raise DefinitionError("Missing or corrupt revision")
        return dict(row["document"])

    def select(self, identifier: str, *, base_revision: int) -> dict[str, Any]:
        with _LOCK:
            state = self._read()
            self._check(state, base_revision)
            compile_document(self._document(state, identifier))
            state["pendingRevision"] = identifier
            state["baseRevision"] += 1
            self._write(state)
            return self.snapshot()

    def startup(self) -> tuple[NarrativeCatalog, dict[str, Any]]:
        """Called only at service startup, before constructing narrative consumers."""
        with _LOCK:
            state: dict[str, Any] = {}
            try:
                state = self._read()
                compiled = compile_document(self._document(state, state["pendingRevision"]))
                if state["effectiveRevision"] != state["pendingRevision"]:
                    promoted = {
                        **state,
                        "effectiveRevision": state["pendingRevision"],
                        "baseRevision": state["baseRevision"] + 1,
                    }
                    self._write(promoted)
                    state = promoted
                return compiled, {
                    "effectiveRevision": state["effectiveRevision"],
                    "startupError": None,
                }
            except (OSError, DefinitionError, KeyError, TypeError):
                try:
                    previous = state["effectiveRevision"]
                    compiled = compile_document(self._document(state, previous))
                except (DefinitionError, KeyError, TypeError):
                    previous = "builtin"
                    compiled = load_narrative_catalog().require_catalog()
                return compiled, {
                    "effectiveRevision": previous,
                    "startupError": "Invalid or unavailable selected revision; previous valid definitions retained",
                }
