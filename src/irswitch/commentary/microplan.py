"""Versioned immutable editorial input; wire serialization is deliberately separate."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class CommentaryMicroplan:
    family: str
    relation: str
    story_state: str
    density: str
    actor_roles: tuple[tuple[str, str], ...]
    required_ids: tuple[str, ...]
    optional_ids: tuple[str, ...]
    style_card_id: str
    canonical: str
    source_correlation: str
    run_epoch: int
    source_revision: int
    version: str = "commentary-microplan/1"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
