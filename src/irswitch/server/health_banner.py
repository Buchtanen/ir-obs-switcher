"""GR dashboard health banner mapping (connection → actionable tips)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HealthBannerView:
    """View-model for the GR health banner when connections are degraded."""

    severity: str  # "degraded" | "unhealthy"
    title_key: str
    tip_keys: tuple[str, ...]


def resolve_health_banner(
    connected_iracing: bool,
    connected_obs: bool,
) -> HealthBannerView | None:
    """
    Map iRacing/OBS connection flags to a banner view.

    Returns None when both are connected (banner should be hidden).
    Mirrors /health severity: degraded = one down, unhealthy = both down.
    """
    if connected_iracing and connected_obs:
        return None

    tip_keys: list[str] = []
    if not connected_iracing:
        tip_keys.append("health_banner_tip_iracing")
    if not connected_obs:
        tip_keys.append("health_banner_tip_obs")

    if not connected_iracing and not connected_obs:
        return HealthBannerView(
            severity="unhealthy",
            title_key="health_banner_title_unhealthy",
            tip_keys=tuple(tip_keys),
        )

    return HealthBannerView(
        severity="degraded",
        title_key="health_banner_title_degraded",
        tip_keys=tuple(tip_keys),
    )
