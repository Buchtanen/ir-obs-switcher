"""Battle intensity ladder helpers (hunting track only)."""

from __future__ import annotations

from irswitch.overlay.settings import HuntingSettings

_INTENSITY_ORDER = ("hunting", "approach", "attack_range", "side_by_side")


def resolve_hunting_intensity(
    gap: float | None,
    closing: float | None,
    current: str,
    cfg: HuntingSettings,
) -> str:
    """Stepwise escalation/de-escalation with enter/exit hysteresis."""
    if current not in _INTENSITY_ORDER:
        current = "hunting"
    if gap is None or closing is None or closing < cfg.intensity_min_closing_rate:
        return "hunting"

    cur = current
    if cur == "side_by_side" and gap > cfg.side_by_side_exit_gap:
        cur = "attack_range"
    if cur == "attack_range" and gap > cfg.attack_exit_gap:
        cur = "approach"
    if cur == "approach" and gap > cfg.approach_exit_gap:
        cur = "hunting"

    if cur == "hunting" and gap <= cfg.approach_enter_gap:
        return "approach"
    if cur == "approach" and gap <= cfg.attack_enter_gap:
        return "attack_range"
    if cur == "attack_range" and gap <= cfg.side_by_side_enter_gap:
        return "side_by_side"
    return cur
