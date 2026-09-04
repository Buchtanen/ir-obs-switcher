"""Immutable style catalog loaded once during graph initialization."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


@dataclass(frozen=True)
class StyleCard:
    id: str
    relations: tuple[str, ...]
    states: tuple[str, ...]
    capacity: int
    guidance: str
    example_en: str
    example_cs: str

    def compatible(self, relation: str, state: str, count: int) -> bool:
        return (
            ("*" in self.relations or relation in self.relations)
            and state in self.states
            and count <= self.capacity
        )

    def example(self, locale: str) -> str:
        return self.example_cs if locale.startswith("cs") else self.example_en


@lru_cache(maxsize=1)
def load_style_cards() -> tuple[StyleCard, ...]:
    path = Path(__file__).resolve().parent / "data" / "style_cards.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    cards = tuple(
        StyleCard(
            id=item["id"],
            relations=tuple(item["relations"]),
            states=tuple(item["states"]),
            capacity=int(item["capacity"]),
            guidance=item["guidance"],
            example_en=item["example_en"],
            example_cs=item["example_cs"],
        )
        for item in raw["cards"]
    )
    if len({card.id for card in cards}) != len(cards) or not any(
        card.id == "fact_first" for card in cards
    ):
        raise ValueError("style card IDs must be unique and include fact_first")
    return cards


@lru_cache(maxsize=1)
def load_node_moods() -> tuple[str, dict[str, str]]:
    """Load short per-node mood hints; never full example sentences."""
    path = Path(__file__).resolve().parent / "data" / "node_moods.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    default = _validated_mood(raw.get("default"), key="default")
    nodes = raw.get("nodes")
    if not isinstance(nodes, dict):
        raise ValueError("node mood catalog must contain an object named nodes")
    return default, {
        str(node_id): _validated_mood(mood, key=str(node_id))
        for node_id, mood in nodes.items()
    }


def mood_for_node(node_id: str) -> str:
    default, nodes = load_node_moods()
    return nodes.get(str(node_id), default)


def _validated_mood(value: object, *, key: str) -> str:
    mood = str(value or "").strip()
    words = [part.strip() for part in mood.split(",") if part.strip()]
    if not 2 <= len(words) <= 4 or any(len(part.split()) > 2 for part in words):
        raise ValueError(f"node mood {key!r} must contain 2-4 short comma-separated adjectives")
    return ", ".join(words)


def select_style_card(
    ids: tuple[str, ...], relation: str, state: str, count: int, *, index: int = 0
) -> StyleCard:
    cards = load_style_cards()
    compatible = [
        card for card in cards if card.id in ids and card.compatible(relation, state, count)
    ]
    if not compatible:
        compatible = [card for card in cards if card.id == "fact_first"]
    return compatible[index % len(compatible)]
