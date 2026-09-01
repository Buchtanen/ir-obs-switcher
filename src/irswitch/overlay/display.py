"""Display rules: channel occupancy, asset fallback. No graphic assets here."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

CHANNEL_CAPACITY: dict[str, int] = {
    # Independent front/rear relations plus the derived two-front fact.
    "battle": 3,
    "lap": 1,
    "alert": 1,
    "session": 1,
    "bio": 1,
    "system": 1,
}

ASSET_SLOTS: tuple[str, ...] = (
    "battle_shadow",
    "battle_base_plate",
    "battle_material",
    "battle_tech_diagram",
    "battle_frame_base",
    "battle_frame_highlight",
    "battle_state_accent_mask",
    "battle_corner_left",
    "battle_corner_right",
    "battle_icon_well",
    "battle_radar_ticks",
    "battle_radar_ring_inner",
    "battle_radar_ring_outer",
    "battle_target_icon",
    "battle_pressure_icon",
    "battle_micro_details",
    "battle_scan_mask",
    "battle_glow_cyan",
    "battle_glow_amber",
    "battle_glow_red",
    "battle_scan_enter",
    "battle_signal_lock",
    "battle_theme_motion",
    "lap_background",
    "lap_frame",
    "lap_flag_icon",
    "lap_stopwatch_icon",
    "alert_banner",
    "position_banner",
    "chevron_up",
    "chevron_down",
    "session_background",
    "final_lap_flag",
    "finish_flag",
    "finish_accent_sweep",
    "bio_compact_plate",
    "bio_expanded_plate",
    "heart_icon",
    "ble_icon",
    "bio_pulse_trace",
    "bio_accent",
    "sysinfo_background",
    "sysinfo_module_segment",
    "sysinfo_dividers",
    "cpu_icon",
    "gpu_icon",
    "ram_icon",
    "temp_icon",
    "power_icon",
    "fps_icon",
    "accent_slash",
    "scan_line",
    "thin_divider",
    "wireframe_fragment",
)

_ASSET_EXTS = (".png", ".webm", ".svg")


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
        if rel:
            path = self.web_root / rel
            return rel.replace("\\", "/") if path.is_file() else None
        stem = f"themes/{self.theme}/assets/{slot}"
        for ext in _ASSET_EXTS:
            rel = f"{stem}{ext}"
            if (self.web_root / rel).is_file():
                return rel.replace("\\", "/")
        return None

    def to_dict(self) -> dict[str, Any]:
        resolved = {slot: self.resolve(slot) for slot in ASSET_SLOTS}
        return {"theme": self.theme, "assets": resolved}
