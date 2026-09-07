#!/usr/bin/env python3
"""Build/check branch-only v2 machine registries from their canonical Markdown tables."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
DOCS = ROOT / "docs" / "v2.0.0"
REGISTRY_PATH = Path(__file__).with_name("freeze-registry.json")
V4_GOLDEN_PATH = Path(__file__).with_name("v4-event-envelope.golden.json")


def _clean(cell: str) -> str:
    return cell.strip().replace("`", "")


def _table(path: Path, heading: str) -> list[list[str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    start = lines.index(heading) + 1
    rows: list[list[str]] = []
    entered = False
    for line in lines[start:]:
        if line.startswith("|"):
            entered = True
            cells = [_clean(cell) for cell in line.strip().strip("|").split("|")]
            if cells and not all(re.fullmatch(r":?-+:?", cell) for cell in cells):
                rows.append(cells)
        elif entered:
            break
    if not rows:
        raise ValueError(f"table not found after {heading!r} in {path}")
    return rows[1:]


def _attributes(raw: str) -> tuple[list[dict[str, Any]], int]:
    if raw == "—":
        return [], 0
    result: list[dict[str, Any]] = []
    for match in re.finditer(r"([A-Za-z][A-Za-z0-9]*):([a-z][a-z0-9_]*)", raw):
        prefix = raw[max(0, raw.rfind(";", 0, match.start()) + 1) : match.start()]
        result.append(
            {
                "id": match.group(1),
                "scalarType": match.group(2),
                "required": "optional" not in prefix.lower(),
            }
        )
    if not result:
        raise ValueError(f"unparsed fact attributes: {raw}")
    minimum = 1 if "at least one required" in raw else sum(item["required"] for item in result)
    return result, minimum


def _enum_registry(text: str) -> dict[str, list[str]]:
    enums: dict[str, list[str]] = {}
    for line in text.splitlines():
        match = re.match(r"- `([a-z][a-z0-9_]*)`: `([^`]+)`", line)
        if match:
            enums[match.group(1)] = match.group(2).split("|")
    return enums


def _tape_channels(text: str) -> list[str]:
    marker = "## Tape-channel registry"
    section = text.split(marker, 1)[1]
    block = section.split("```text", 1)[1].split("```", 1)[0]
    return [line.strip() for line in block.splitlines() if line.strip()]


def _states() -> dict[str, list[str]]:
    return {
        "detector": ["inactive", "candidate", "active", "clearing"],
        "episode": ["candidate", "active", "suspended", "resolved", "invalidated"],
        "eventOpportunity": [
            "pending",
            "reserved",
            "consumed",
            "expired",
            "superseded",
            "invalidated",
            "evicted",
        ],
        "narrativeRuntime": ["disabled", "starting", "ready", "degraded", "stopping", "stopped"],
        "obs": ["inactive", "active", "unknown"],
        "speechLane": ["idle", "building", "committed", "speaking", "stopping"],
        "ttsCallback": ["playback_accepted", "completed", "interrupted", "failed"],
    }


def _beat_ids(raw: str) -> list[str]:
    if raw == "—":
        return []
    result: list[str] = []
    prefix = ""
    for item in (part.strip() for part in raw.split(",")):
        if item.startswith("."):
            item = prefix + item
        else:
            prefix = item.rsplit(".", 1)[0]
        result.append(item)
    return result


def build_registry() -> dict[str, Any]:
    fact_path = DOCS / "fact-feature-registry.md"
    schema_path = DOCS / "schema-contracts.md"
    event_path = DOCS / "event-beat-disposition.md"
    fact_text = fact_path.read_text(encoding="utf-8")

    scalar_types = [
        {"id": row[0], "contract": row[1]} for row in _table(fact_path, "## Scalar and enum types")
    ]
    predicates = []
    for row in _table(fact_path, "## Canonical fact predicates"):
        attrs, minimum = _attributes(row[2])
        predicates.append(
            {
                "id": row[0],
                "actors": row[1],
                "attributes": attrs,
                "minimumAttributeCount": minimum,
                "scope": row[3],
                "producer": row[4],
            }
        )
    features = [
        {"id": row[0], "scalarType": row[1], "definition": row[2], "unknownWhen": row[3]}
        for row in _table(fact_path, "## Canonical feature IDs")
    ]
    versions = [
        {"artifact": row[0], "schemaVersion": row[1]}
        for row in _table(schema_path, "## Frozen version strings")
    ]
    reasons = [
        {"domain": row[0], "ids": [item.strip() for item in row[1].split(",")]}
        for row in _table(schema_path, "## Frozen reason IDs")
        if row[0] != "Domain"
    ]
    relations = [
        {"id": row[0], "meaning": row[1]}
        for row in _table(schema_path, "## Frozen director relation IDs")
    ]
    event_identifiers = []
    for row in _table(event_path, "## Identifier disposition"):
        narrative_kind = None if row[3] == "—" else row[3]
        if narrative_kind is not None:
            event_class = "speakable"
        elif row[5] == "compat.alias":
            event_class = "compatibility_alias"
        else:
            event_class = "visual_only"
        event_identifiers.append(
            {
                "id": row[0],
                "sourceClass": row[1],
                "disposition": row[2],
                "eventClass": event_class,
                "narrativeKind": narrative_kind,
                "beatDefinitions": _beat_ids(row[4]),
                "tapeChannel": row[5],
            }
        )
    lifecycle_events = [
        {
            "id": row[0],
            "producer": row[1],
            "speechRouting": row[2],
            "tapeChannel": row[3],
        }
        for row in _table(event_path, "### New internal lifecycle event kinds")
    ]

    return {
        "registryVersion": "v2-freeze-registry/1",
        "sourceBaseline": "master@0ce75d4",
        "sources": [
            "docs/v2.0.0/fact-feature-registry.md",
            "docs/v2.0.0/schema-contracts.md",
            "docs/v2.0.0/event-beat-disposition.md",
        ],
        "scalarTypes": scalar_types,
        "enums": _enum_registry(fact_text),
        "factPredicates": predicates,
        "features": features,
        "tapeChannels": _tape_channels(fact_text),
        "schemaVersions": versions,
        "reasonRegistry": reasons,
        "relationRegistry": relations,
        "stateRegistry": _states(),
        "eventIdentifiers": event_identifiers,
        "internalLifecycleEvents": lifecycle_events,
    }


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()


def _unique(items: list[str], label: str) -> None:
    if len(items) != len(set(items)):
        duplicates = sorted({item for item in items if items.count(item) > 1})
        raise ValueError(f"duplicate {label}: {duplicates}")


def validate_registry(registry: dict[str, Any]) -> None:
    expected_counts = {
        "factPredicates": 57,
        "features": 21,
        "tapeChannels": 36,
        "eventIdentifiers": 60,
        "internalLifecycleEvents": 5,
        "relationRegistry": 6,
    }
    for key, expected in expected_counts.items():
        actual = len(registry[key])
        if actual != expected:
            raise ValueError(f"{key}: expected {expected}, got {actual}")

    scalar_ids = [item["id"] for item in registry["scalarTypes"]]
    enum_ids = list(registry["enums"])
    known_types = set(scalar_ids) | set(enum_ids)
    _unique(scalar_ids, "scalar type")
    _unique(enum_ids, "enum")
    _unique([item["id"] for item in registry["factPredicates"]], "fact predicate")
    _unique([item["id"] for item in registry["features"]], "feature")
    _unique(registry["tapeChannels"], "tape channel")
    _unique([item["id"] for item in registry["eventIdentifiers"]], "event identifier")
    _unique([item["id"] for item in registry["internalLifecycleEvents"]], "lifecycle event")
    _unique([item["schemaVersion"] for item in registry["schemaVersions"]], "schema version")
    _unique([item["id"] for item in registry["relationRegistry"]], "director relation")

    for predicate in registry["factPredicates"]:
        _unique([item["id"] for item in predicate["attributes"]], f"{predicate['id']} attribute")
        for attribute in predicate["attributes"]:
            if attribute["scalarType"] not in known_types:
                raise ValueError(
                    f"{predicate['id']}.{attribute['id']}: unknown type {attribute['scalarType']}"
                )
    for feature in registry["features"]:
        if feature["scalarType"] not in known_types:
            raise ValueError(f"{feature['id']}: unknown type {feature['scalarType']}")
    known_channels = set(registry["tapeChannels"])
    for event in registry["eventIdentifiers"] + registry["internalLifecycleEvents"]:
        if event["tapeChannel"] not in known_channels:
            raise ValueError(f"{event['id']}: unknown tape channel {event['tapeChannel']}")
    for event in registry["eventIdentifiers"]:
        if event["eventClass"] == "speakable" and not event["beatDefinitions"]:
            raise ValueError(f"{event['id']}: speakable event has no beat")
        if event["eventClass"] != "speakable" and event["beatDefinitions"]:
            raise ValueError(f"{event['id']}: nonspeakable event has beats")

    _unique([domain["domain"] for domain in registry["reasonRegistry"]], "reason domain")
    for domain in registry["reasonRegistry"]:
        _unique(domain["ids"], f"{domain['domain']} reason ID")
    for state_name, states in registry["stateRegistry"].items():
        _unique(states, f"{state_name} state")


def validate_v4_golden() -> None:
    golden = json.loads(V4_GOLDEN_PATH.read_text(encoding="utf-8"))
    digest = "sha256:" + hashlib.sha256(canonical_bytes(golden["eventEnvelope"])).hexdigest()
    if digest != golden["canonicalSha256"]:
        raise ValueError(f"V4 golden hash mismatch: {digest}")
    if golden["eventEnvelope"].get("schemaVersion") != "1.0":
        raise ValueError("V4 golden schemaVersion changed")
    forbidden = {"tapeChannel", "factIds", "occurrenceId", "lineageId", "reducerSequence"}
    leaked = forbidden.intersection(golden["eventEnvelope"])
    if leaked:
        raise ValueError(f"narrative fields leaked into V4 wire: {sorted(leaked)}")

    sys.path.insert(0, str(ROOT / "src"))
    from irswitch.events.envelope import EventEnvelope  # noqa: PLC0415
    from irswitch.events.stream import freeze_envelope, thaw_envelope  # noqa: PLC0415

    restored = EventEnvelope.from_dict(golden["eventEnvelope"])
    if restored.to_dict() != golden["eventEnvelope"]:
        raise ValueError("current EventEnvelope wire differs from master golden")
    restored.sequence = 1
    frozen = freeze_envelope(restored)
    if thaw_envelope(frozen).to_dict() != restored.to_dict():
        raise ValueError("current EventEnvelope freeze/thaw is not lossless")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--emit", action="store_true", help="print generated registry JSON")
    parser.add_argument("--write", action="store_true", help="write generated registry JSON")
    args = parser.parse_args()
    generated = build_registry()
    validate_registry(generated)
    if args.emit:
        print(json.dumps(generated, ensure_ascii=False, sort_keys=True, indent=2))
        return 0
    if args.write:
        REGISTRY_PATH.write_text(
            json.dumps(generated, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"wrote {REGISTRY_PATH.name}")
        return 0
    checked_in = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    if canonical_bytes(generated) != canonical_bytes(checked_in):
        print("freeze-registry.json is stale; regenerate from canonical Markdown", file=sys.stderr)
        return 1
    validate_registry(checked_in)
    validate_v4_golden()
    print(
        "freeze registry OK: 60 events + 5 lifecycle, 57 predicates, 21 features, "
        f"36 tape channels, {len(checked_in['relationRegistry'])} relations, "
        f"{len(checked_in['schemaVersions'])} schemas"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
