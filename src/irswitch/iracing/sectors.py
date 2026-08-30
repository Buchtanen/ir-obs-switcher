"""Extract official sector start percentages from iRSDK SplitTimeInfo."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from irswitch.race.timing.points import TimingPoint, default_sectors, start_finish_point

# Values above this are 0–100 percent, not 0–1 fractions.
_PERCENT_HINT = 1.5


def sector_start_pcts(split_time_info: object) -> tuple[float, ...]:
    """Return SectorStartPct values sorted by SectorNum, as 0–1 fractions."""
    rows = _sectors_list(split_time_info)
    parsed: list[tuple[int, float]] = []
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        num = row.get("SectorNum")
        raw = row.get("SectorStartPct")
        if not isinstance(num, (int, float)):
            continue
        pct = _as_float(raw)
        if pct is None:
            continue
        parsed.append((int(num), pct))
    if not parsed:
        return ()
    parsed.sort(key=lambda item: item[0])
    raw_values = [p[1] for p in parsed]
    as_percent = any(value > _PERCENT_HINT for value in raw_values)
    out: list[float] = []
    for value in raw_values:
        frac = value / 100.0 if as_percent else value
        if frac < 0.0:
            continue
        out.append(round(frac, 6))
    return tuple(out)


def timing_points_from_pcts(pcts: Sequence[float]) -> tuple[TimingPoint, ...]:
    """MS00 plus S1..Sn intermediates for starts strictly inside (0, 1)."""
    points: list[TimingPoint] = [start_finish_point()]
    intermediates = [p for p in pcts if 0.0 < p < 1.0]
    for i, pct in enumerate(intermediates, start=1):
        sid = f"S{i}"
        points.append(TimingPoint(id=sid, lap_dist_pct=pct, label=sid))
    return tuple(points)


def resolve_sector_points_from_pcts(pcts: Sequence[float]) -> tuple[TimingPoint, ...]:
    """Official intermediates when present; else geometric S1/S2."""
    points = timing_points_from_pcts(pcts)
    if len(points) < 2:
        return default_sectors()
    return points


def resolve_sector_points(split_time_info: object) -> tuple[TimingPoint, ...]:
    return resolve_sector_points_from_pcts(sector_start_pcts(split_time_info))


def _sectors_list(split_time_info: object) -> Sequence[object]:
    if split_time_info is None:
        return ()
    if isinstance(split_time_info, Mapping):
        sectors = split_time_info.get("Sectors")
        if isinstance(sectors, Sequence) and not isinstance(sectors, (str, bytes)):
            return sectors
        return ()
    sectors = getattr(split_time_info, "Sectors", None)
    if isinstance(sectors, Sequence) and not isinstance(sectors, (str, bytes)):
        return sectors
    return ()


def _as_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return None
