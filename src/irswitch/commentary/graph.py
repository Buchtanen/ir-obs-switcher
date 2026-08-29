"""JSON sequence graph: nodes, edges, TTS constraints. No external graph DB."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from irswitch.events.event_catalog import catalog_entries, catalog_fallbacks

GRAPH_VERSION = 1
ALLOWED_HR_STATES = frozenset({"unknown", "calm", "focused", "pushing", "high"})
ALLOWED_SLOT_TYPES = frozenset({"int", "time", "delta", "gap", "name", "label"})
ALLOWED_SSML = frozenset({"break", "emphasis"})
VARIANT_KEYS = ("neutral", "calm", "focused", "pushing", "high")
SUPPORTED_LOCALES = ("en", "cs")

_DEFAULT_GRAPH = Path(__file__).resolve().parent / "data" / "sequence_graph.json"


@dataclass(frozen=True)
class SlotSpec:
    name: str
    type: str
    example: str


@dataclass(frozen=True)
class TtsLimits:
    max_chars: int = 90
    max_seconds: float = 5.5
    ssml_allowed: tuple[str, ...] = ("break", "emphasis")
    require_terminal_punct: bool = True


@dataclass(frozen=True)
class GraphEdge:
    source: str
    target: str
    same_correlation: bool = True
    min_gap_s: float = 0.0
    max_gap_s: float = 60.0


@dataclass
class GraphNode:
    id: str
    family: str
    event_types: tuple[str, ...]
    phases: tuple[str, ...]
    speak_priority: int
    cooldown_s: float
    slots: tuple[SlotSpec, ...]
    hr_states: tuple[str, ...]
    notes: str = ""
    tts: TtsLimits = field(default_factory=TtsLimits)
    variants: dict[str, dict[str, tuple[str, ...]]] = field(default_factory=dict)

    def variant_bucket(self, locale: str, emotion: str) -> tuple[str, ...]:
        locale_map = self.variants.get(locale) or {}
        if emotion in locale_map and locale_map[emotion]:
            return locale_map[emotion]
        if emotion == "calm" and locale_map.get("neutral"):
            return locale_map["neutral"]
        if emotion == "unknown" and locale_map.get("neutral"):
            return locale_map["neutral"]
        return locale_map.get(emotion, ())


@dataclass
class SequenceGraph:
    version: int
    locales: tuple[str, ...]
    default_tts: TtsLimits
    nodes: dict[str, GraphNode]
    edges: tuple[GraphEdge, ...]

    def node(self, node_id: str) -> GraphNode | None:
        return self.nodes.get(node_id)

    def nodes_for(
        self,
        event_type: str,
        phase: str,
    ) -> list[GraphNode]:
        key = event_type.strip().upper()
        phase_key = phase.strip().upper()
        matched = [
            node
            for node in self.nodes.values()
            if key in node.event_types and phase_key in node.phases
        ]
        matched.sort(key=lambda item: item.speak_priority, reverse=True)
        return matched

    def outgoing(self, node_id: str) -> list[GraphEdge]:
        return [edge for edge in self.edges if edge.source == node_id]

    def incoming(self, node_id: str) -> list[GraphEdge]:
        return [edge for edge in self.edges if edge.target == node_id]

    def unfilled_cells(self) -> list[tuple[str, str, str]]:
        """Return (node_id, locale, emotion) cells with no authored text."""
        missing: list[tuple[str, str, str]] = []
        for node in self.nodes.values():
            for locale in self.locales:
                locale_map = node.variants.get(locale) or {}
                for emotion in node.hr_states:
                    bucket = emotion if emotion != "unknown" else "neutral"
                    texts = locale_map.get(bucket) or locale_map.get(emotion) or ()
                    if not texts:
                        missing.append((node.id, locale, bucket))
        return missing


def default_graph_path() -> Path:
    return _DEFAULT_GRAPH


def load_sequence_graph(path: Path | None = None) -> SequenceGraph:
    raw = json.loads((path or default_graph_path()).read_text(encoding="utf-8"))
    return parse_sequence_graph(raw)


def parse_sequence_graph(raw: dict[str, Any]) -> SequenceGraph:
    errors = validate_graph_document(raw)
    if errors:
        raise ValueError("invalid sequence graph: " + "; ".join(errors[:8]))
    default_tts = _tts_limits(raw.get("default_tts") or {})
    locales = tuple(str(item) for item in raw.get("locales") or SUPPORTED_LOCALES)
    nodes_raw = raw.get("nodes") or {}
    nodes: dict[str, GraphNode] = {}
    for node_id, payload in nodes_raw.items():
        nodes[str(node_id)] = _parse_node(str(node_id), payload, default_tts, locales)
    edges = tuple(
        GraphEdge(
            source=str(item["from"]),
            target=str(item["to"]),
            same_correlation=bool((item.get("when") or {}).get("same_correlation", True)),
            min_gap_s=float((item.get("when") or {}).get("min_gap_s", 0.0)),
            max_gap_s=float((item.get("when") or {}).get("max_gap_s", 60.0)),
        )
        for item in raw.get("edges") or []
    )
    return SequenceGraph(
        version=int(raw.get("version") or GRAPH_VERSION),
        locales=locales,
        default_tts=default_tts,
        nodes=nodes,
        edges=edges,
    )


def validate_graph_document(raw: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(raw, dict):
        return ["graph must be an object"]
    version = raw.get("version")
    if version != GRAPH_VERSION:
        errors.append(f"unsupported version: {version!r}")
    locales = raw.get("locales") or []
    if not isinstance(locales, list) or not locales:
        errors.append("locales must be a non-empty list")
    else:
        for locale in locales:
            if locale not in SUPPORTED_LOCALES:
                errors.append(f"unsupported locale: {locale!r}")
    known_events = set(catalog_entries()) | set(catalog_fallbacks())
    nodes = raw.get("nodes")
    if not isinstance(nodes, dict) or not nodes:
        errors.append("nodes must be a non-empty object")
        return errors
    for node_id, payload in nodes.items():
        errors.extend(_validate_node(str(node_id), payload, known_events))
    for index, edge in enumerate(raw.get("edges") or []):
        if not isinstance(edge, dict):
            errors.append(f"edges[{index}] must be an object")
            continue
        src = edge.get("from")
        dst = edge.get("to")
        if src not in nodes:
            errors.append(f"edges[{index}] unknown from: {src!r}")
        if dst not in nodes:
            errors.append(f"edges[{index}] unknown to: {dst!r}")
    return errors


def _validate_node(node_id: str, payload: Any, known_events: set[str]) -> list[str]:
    errors: list[str] = []
    prefix = f"nodes.{node_id}"
    if not isinstance(payload, dict):
        return [f"{prefix} must be an object"]
    event_types = payload.get("event_types") or []
    if not event_types:
        errors.append(f"{prefix}.event_types is required")
    for event_type in event_types:
        key = str(event_type).upper()
        if key not in known_events:
            errors.append(f"{prefix} unknown event type: {event_type!r}")
    phases = payload.get("phases") or []
    if not phases:
        errors.append(f"{prefix}.phases is required")
    for phase in phases:
        if str(phase).upper() not in {
            "ENTER",
            "ACTIVE",
            "UPDATE",
            "RESULT",
            "EXIT",
            "COMPACT",
            "SUSPEND",
            "RESUME",
        }:
            errors.append(f"{prefix} invalid phase: {phase!r}")
    for slot in payload.get("slots") or []:
        if not isinstance(slot, dict) or not slot.get("name"):
            errors.append(f"{prefix} slot missing name")
            continue
        slot_type = str(slot.get("type") or "")
        if slot_type not in ALLOWED_SLOT_TYPES:
            errors.append(f"{prefix} slot {slot.get('name')!r} bad type: {slot_type!r}")
    for hr_state in payload.get("hr_states") or []:
        if hr_state not in ALLOWED_HR_STATES:
            errors.append(f"{prefix} bad hr_state: {hr_state!r}")
    priority = payload.get("speak_priority")
    if not isinstance(priority, int) or priority < 0:
        errors.append(f"{prefix}.speak_priority must be a non-negative int")
    return errors


def _parse_node(
    node_id: str,
    payload: dict[str, Any],
    default_tts: TtsLimits,
    locales: tuple[str, ...],
) -> GraphNode:
    slots = tuple(
        SlotSpec(
            name=str(item["name"]),
            type=str(item.get("type") or "label"),
            example=str(item.get("example") if item.get("example") is not None else ""),
        )
        for item in payload.get("slots") or []
    )
    tts_raw = payload.get("tts") or {}
    tts = _tts_limits(tts_raw, default_tts) if tts_raw else default_tts
    variants = _parse_variants(payload.get("variants") or {}, locales)
    return GraphNode(
        id=node_id,
        family=str(payload.get("family") or ""),
        event_types=tuple(str(item).upper() for item in payload.get("event_types") or []),
        phases=tuple(str(item).upper() for item in payload.get("phases") or []),
        speak_priority=int(payload.get("speak_priority") or 0),
        cooldown_s=float(payload.get("cooldown_s") or 0.0),
        slots=slots,
        hr_states=tuple(str(item) for item in payload.get("hr_states") or ("unknown",)),
        notes=str(payload.get("notes") or ""),
        tts=tts,
        variants=variants,
    )


def _parse_variants(
    raw: dict[str, Any],
    locales: tuple[str, ...],
) -> dict[str, dict[str, tuple[str, ...]]]:
    parsed: dict[str, dict[str, tuple[str, ...]]] = {}
    for locale in locales:
        locale_raw = raw.get(locale) or {}
        buckets: dict[str, tuple[str, ...]] = {}
        if isinstance(locale_raw, dict):
            for key in VARIANT_KEYS:
                texts = locale_raw.get(key) or []
                buckets[key] = tuple(str(item) for item in texts if str(item).strip())
        parsed[locale] = buckets
    return parsed


def _tts_limits(raw: dict[str, Any], base: TtsLimits | None = None) -> TtsLimits:
    seed = base or TtsLimits()
    allowed = tuple(
        str(item) for item in raw.get("ssml_allowed", seed.ssml_allowed) if str(item) in ALLOWED_SSML
    )
    return TtsLimits(
        max_chars=int(raw.get("max_chars", seed.max_chars)),
        max_seconds=float(raw.get("max_seconds", seed.max_seconds)),
        ssml_allowed=allowed or seed.ssml_allowed,
        require_terminal_punct=bool(raw.get("require_terminal_punct", seed.require_terminal_punct)),
    )
