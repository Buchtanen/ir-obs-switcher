"""iRacing SDK units, sentinels, and HUD display formats.

Telemetry stays in SDK units (seconds, 0–1 lap fraction). Format only at display.
Keep ``src/irswitch/web/overlay/js/timing-format.js`` in sync with the formatters.

See ``.cursor/skills/iracing-sdk-display-format/SKILL.md``.
"""

from __future__ import annotations

import math
from typing import Final

from irswitch.iracing.extractors import as_int

PLACEHOLDER: Final = "—"

# irsdk.h markers (also iracing-telem / community ports)
IRSDK_UNLIMITED_LAPS: Final = 32767
IRSDK_UNLIMITED_TIME_S: Final = 604800.0  # 7 days; SessionTimeRemain "unlimited"

# Typical racing lap on this HUD; longer is treated as unset/garbage.
MAX_SANE_LAP_S: Final = 30 * 60


def _finite(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
    else:
        try:
            number = float(str(value))
        except ValueError:
            return None
    if not math.isfinite(number):
        return None
    return number


def as_completed_lap_time(value: object) -> float | None:
    """LapLastLapTime / LapBestLapTime. SDK uses -1 (and often 0) when unset."""
    number = _finite(value)
    if number is None or number <= 0 or number > MAX_SANE_LAP_S:
        return None
    return number


def as_current_lap_time(value: object) -> float | None:
    """LapCurrentLapTime. 0 is valid just after start/finish."""
    number = _finite(value)
    if number is None or number < 0 or number > MAX_SANE_LAP_S:
        return None
    return number


def as_elapsed_seconds(value: object) -> float | None:
    """SessionTime and other elapsed clocks. 0 is valid; negative is invalid."""
    number = _finite(value)
    if number is None or number < 0:
        return None
    return number


def as_session_time_remain(value: object) -> float | None:
    """SessionTimeRemain. 604800 s means unlimited, not a real countdown."""
    number = as_elapsed_seconds(value)
    if number is None or number >= IRSDK_UNLIMITED_TIME_S:
        return None
    return number


def as_session_laps_remain(value: object) -> float | None:
    """SessionLapsRemain / SessionLapsRemainEx. 32767 means unlimited."""
    number = _finite(value)
    if number is None or number < 0 or number >= IRSDK_UNLIMITED_LAPS:
        return None
    return number


def as_lap_dist_pct(value: object) -> float | None:
    """LapDistPct / CarIdxLapDistPct: fraction 0–1, not 0–100. -1 = not in world."""
    number = _finite(value)
    if number is None or number < 0 or number > 1.05:
        return None
    return number


def as_est_time(value: object) -> float | None:
    """CarIdxEstTime: estimated seconds around the track, not a gap to a rival."""
    number = _finite(value)
    if number is None or number < 0:
        return None
    return number


def as_non_negative_int(value: object) -> int | None:
    """Lap / LapCompleted / CarIdxLapCompleted. -1 = not in world."""
    number = as_int(value)
    if number is None or number < 0:
        return None
    return number


def as_grid_position(value: object) -> int | None:
    """PlayerCarPosition / CarIdxPosition. 0 means not in the results."""
    number = as_int(value)
    if number is None or number <= 0:
        return None
    return number


def format_lap_time(seconds: object) -> str:
    """SimHub ``format(secondstotimespan(s), 'm\\:ss\\.fff')`` / iRacing F3."""
    number = _finite(seconds)
    if number is None or number < 0:
        return PLACEHOLDER
    total_ms = int(round(number * 1000.0))
    if total_ms < 0:
        return PLACEHOLDER
    minutes, rest = divmod(total_ms, 60_000)
    secs, millis = divmod(rest, 1000)
    return f"{minutes}:{secs:02d}.{millis:03d}"


def format_delta(seconds: object, digits: int = 3) -> str:
    """Signed sector / lap delta, e.g. ``+0.318`` / ``-0.418``."""
    number = _finite(seconds)
    if number is None:
        return PLACEHOLDER
    return f"{number:+.{digits}f}"


def format_gap(seconds: object, digits: int = 2) -> str:
    """Battle interval. Absolute seconds plus unit, e.g. ``1.91 s``."""
    number = _finite(seconds)
    if number is None:
        return PLACEHOLDER
    return f"{abs(number):.{digits}f} s"


def format_session_clock(seconds: object) -> str:
    """Elapsed / remaining session clock (not a lap time)."""
    number = as_elapsed_seconds(seconds)
    if number is None:
        return PLACEHOLDER
    total = int(round(number))
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"
