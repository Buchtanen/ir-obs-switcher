"""Spoken timing formatters for commentary slot bindings.

Wire / envelope metrics stay in SDK seconds. Format only when building
spoken bindings for TTS. Sentinel / unformattable values become ``None`` so
``fill_slots`` leaves ``{slot}`` leftovers and ``choose_filled_line`` skips
that candidate (re-draw).

Reuses ``irswitch.iracing.sdk_units`` (same rules as the HUD).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Final

from irswitch.iracing.sdk_units import (
    PLACEHOLDER,
    as_completed_lap_time,
    as_elapsed_seconds,
    format_delta,
    format_gap,
    format_lap_time,
)

SpeakFormatter = Callable[[object], str | None]

# Slot names from sequence_graph SlotSpec that carry SDK seconds.
_TIMING_SLOTS: Final[frozenset[str]] = frozenset(
    {
        "lap_time",
        "segment_time",
        "target_time",
        "projected_time",
        "delta",
        "gap",
    }
)


def speak_lap_time(value: object) -> str | None:
    """Completed / projected lap or segment duration → ``m:ss.fff``.

    Uses completed-lap sentinels: ``-1`` and ``0`` are unset → ``None``.
    """
    seconds = as_completed_lap_time(value)
    if seconds is None:
        return None
    text = format_lap_time(seconds)
    if text == PLACEHOLDER:
        return None
    return text


def speak_delta(value: object) -> str | None:
    """Signed time delta → ``+0.318`` / ``-0.418``. Missing / non-finite → ``None``."""
    if value is None or value == "":
        return None
    if not _is_finite_number(value):
        return None
    text = format_delta(value)
    if text == PLACEHOLDER:
        return None
    return text


def speak_gap(value: object) -> str | None:
    """Battle gap → ``1.91 s``. Negative SDK sentinels and missing → ``None``."""
    seconds = as_elapsed_seconds(value)
    if seconds is None:
        return None
    text = format_gap(seconds)
    if text == PLACEHOLDER:
        return None
    return text


_FORMATTERS: Final[dict[str, SpeakFormatter]] = {
    "lap_time": speak_lap_time,
    "segment_time": speak_lap_time,
    "target_time": speak_lap_time,
    "projected_time": speak_lap_time,
    "delta": speak_delta,
    "gap": speak_gap,
}


def format_spoken_slot(name: str, value: object) -> object | None:
    """Format one binding if ``name`` is a known timing slot; else pass through.

    Returns ``None`` when the timing value is sentinel / unformattable so the
    line stays unbound.
    """
    formatter = _FORMATTERS.get(name)
    if formatter is None:
        return value
    if value is None or value == "":
        return None
    return formatter(value)


def format_spoken_bindings(bindings: dict[str, object]) -> dict[str, object]:
    """Apply spoken formatters to timing keys in a bindings dict (copy)."""
    out = dict(bindings)
    for name in _TIMING_SLOTS:
        if name not in out:
            continue
        out[name] = format_spoken_slot(name, out[name])
    return out


def is_timing_slot(name: str) -> bool:
    return name in _TIMING_SLOTS


def _is_finite_number(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    try:
        return math.isfinite(float(str(value)))
    except ValueError:
        return False
