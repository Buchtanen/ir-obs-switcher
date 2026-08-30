"""Timing point definitions (minisectors / sectors)."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_MINISECTOR_COUNT = 20


@dataclass(frozen=True)
class TimingPoint:
    id: str
    lap_dist_pct: float
    label: str = ""

    def __post_init__(self) -> None:
        if self.lap_dist_pct == 0.0:
            return
        if not 0.0 < self.lap_dist_pct < 1.0:
            raise ValueError(f"lap_dist_pct out of range: {self.lap_dist_pct}")


def default_minisectors(count: int = DEFAULT_MINISECTOR_COUNT) -> tuple[TimingPoint, ...]:
    """Uniform fallback minisectors per Spec §6.1 (20 × 5 %). Includes S/F at 0."""
    if count < 1:
        raise ValueError("count must be >= 1")
    step = 1.0 / count
    points: list[TimingPoint] = [
        TimingPoint(id="MS00", lap_dist_pct=0.0, label="START_FINISH"),
    ]
    for i in range(1, count):
        pct = round(i * step, 6)
        points.append(
            TimingPoint(
                id=f"MS{i:02d}",
                lap_dist_pct=pct,
                label=f"MINISECTOR {i:02d}",
            )
        )
    return tuple(points)


def start_finish_point() -> TimingPoint:
    return TimingPoint(id="MS00", lap_dist_pct=0.0, label="START_FINISH")


def default_sectors() -> tuple[TimingPoint, ...]:
    """S1 / S2 intermediates + start/finish. Used for Practice/Quali split callouts."""
    return (
        TimingPoint(id="MS00", lap_dist_pct=0.0, label="START_FINISH"),
        TimingPoint(id="S1", lap_dist_pct=1.0 / 3.0, label="S1"),
        TimingPoint(id="S2", lap_dist_pct=2.0 / 3.0, label="S2"),
    )
