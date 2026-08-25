"""Display rules: channel occupancy, asset fallback. No graphic assets here."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

CHANNEL_CAPACITY: dict[str, int] = {
    "battle": 2,
    "lap": 1,
    "alert": 1,
    "session": 1,
    "bio": 1,
    "system": 1,
}

ASSET_SLOTS: tuple[str, ...] = (
    "battle_background",
    "battle_frame",
    "battle_glow",
    "battle_target_icon",
    "lap_background",
    "lap_frame",
    "heart_icon",
    "ble_icon",
    "sysinfo_background",
    "sysinfo_dividers",
    "cpu_icon",
    "gpu_icon",
    "ram_icon",
)


@dataclass(frozen=True)
class ActiveSlot:
    channel: str
    name: str
    priority: int


def can_place(active: list[ActiveSlot], channel: str, priority: int) -> bool:
    """True if a new event fits the channel or outranks an occupant."""
    cap = CHANNEL_CAPACITY.get(channel, 1)
    occupied = [slot for slot in active if slot.channel == channel]
    if len(occupied) < cap:
        return True
    return any(priority > slot.priority for slot in occupied)


def place(active: list[ActiveSlot], incoming: ActiveSlot) -> list[ActiveSlot]:
    """Insert incoming; evict lowest-priority occupant when the channel is full."""
    cap = CHANNEL_CAPACITY.get(incoming.channel, 1)
    others = [slot for slot in active if slot.channel != incoming.channel]
    occupied = [slot for slot in active if slot.channel == incoming.channel]
    if incoming.name in {slot.name for slot in occupied}:
        occupied = [incoming if slot.name == incoming.name else slot for slot in occupied]
        return others + occupied
    if len(occupied) < cap:
        return others + occupied + [incoming]
    lowest = min(occupied, key=lambda slot: slot.priority)
    if incoming.priority > lowest.priority:
        occupied = [slot for slot in occupied if slot is not lowest] + [incoming]
        return others + occupied
    return active


class AssetManifest:
    """Maps theme + slot → relative asset path. Missing files fall back to CSS."""

    def __init__(self, theme: str, web_root: Path, slots: dict[str, str] | None = None) -> None:
        self.theme = theme
        self.web_root = web_root
        self.slots = slots or {}

    def resolve(self, slot: str) -> str | None:
        rel = self.slots.get(slot)
        if not rel:
            # Convention: themes/<theme>/assets/<slot>.svg
            rel = f"themes/{self.theme}/assets/{slot}.svg"
        path = self.web_root / rel
        if path.is_file():
            return rel.replace("\\", "/")
        png = path.with_suffix(".png")
        if png.is_file():
            return str(Path(rel).with_suffix(".png")).replace("\\", "/")
        return None

    def to_dict(self) -> dict[str, Any]:
        resolved = {slot: self.resolve(slot) for slot in ASSET_SLOTS}
        return {"theme": self.theme, "assets": resolved}
