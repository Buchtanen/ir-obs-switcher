"""Strength-of-Field (SoF) helpers for commentary — pure, no iRSDK I/O.

**Interim product formula (not official iRacing SoF):** arithmetic mean of
valid racing-driver iRatings, as proposed in ``EVENT_ENGINE_V4_SOF_REMAIN_SPEC.md``.
Round **once** after aggregation (nearest int). Return ``None`` when there are
no valid samples. Overall and class SoF stay separate.

Racing drivers are roster rows that are not pace cars and not spectators, with
a finite non-negative iRating. Missing ``is_spectator`` / ``car_is_pace_car``
are treated as false (conservative include) so callers that omit keys still
contribute when ratings are valid — H1 fixtures should cover explicit flags.

This module intentionally does **not** import ``session_context``; a minimal
``RosterRow`` protocol mirrors the fields H1 ``RosterDriver`` will expose.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@runtime_checkable
class RosterRow(Protocol):
    """Minimal roster shape for SoF (mirrors future H1 ``RosterDriver``)."""

    i_rating: int | None
    car_class_id: int | None
    car_is_pace_car: bool
    is_spectator: bool


@dataclass(frozen=True, slots=True)
class SofBundle:
    """Overall + class SoF with field/sample evidence counts.

    ``overall`` / ``class_sof`` are rounded means, or ``None`` when the
    corresponding sample set is empty. ``field_size`` counts racing drivers
    (pace/spectator excluded), regardless of rating validity.
    ``overall_samples`` / ``class_samples`` count ratings that entered each mean.
    """

    overall: int | None
    class_sof: int | None
    field_size: int
    overall_samples: int
    class_samples: int


def compute_sof(ratings: Iterable[int]) -> int | None:
    """Arithmetic mean of *ratings*, rounded once to int; ``None`` if empty.

    Only non-negative ints are accepted as samples. Invalid entries are skipped.
    """
    samples = [r for r in ratings if _is_valid_rating(r)]
    return _mean_round(samples)


def compute_sof_bundle(
    roster: Iterable[RosterRow | Mapping[str, object]],
    player_class_id: int | None,
) -> SofBundle:
    """Compute overall + class SoF from a roster of drivers.

    Excludes pace cars and spectators from field size and means. When
    ``player_class_id`` is ``None``, ``class_sof`` is ``None`` and
    ``class_samples`` is 0 (even if class ids are present on rows).
    """
    overall_ratings: list[int] = []
    class_ratings: list[int] = []
    field_size = 0

    for row in roster:
        if not _is_racing_driver(row):
            continue
        field_size += 1
        rating = _row_rating(row)
        if rating is None:
            continue
        overall_ratings.append(rating)
        if player_class_id is not None and _row_class_id(row) == player_class_id:
            class_ratings.append(rating)

    return SofBundle(
        overall=_mean_round(overall_ratings),
        class_sof=_mean_round(class_ratings) if player_class_id is not None else None,
        field_size=field_size,
        overall_samples=len(overall_ratings),
        class_samples=len(class_ratings) if player_class_id is not None else 0,
    )


def format_sof_label(value: int | None, locale: str) -> str | None:
    """Locale-aware thousands separator for ``label`` slots (EN / CS).

    EN: ``2,450``; CS: ``2 450`` (narrow no-break space avoided — plain space).
    Returns ``None`` when *value* is ``None`` so bindings can omit the line.
    """
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        return None
    text = f"{value:,}"
    if locale.lower().startswith("cs"):
        return text.replace(",", " ")
    return text


def _mean_round(samples: list[int]) -> int | None:
    if not samples:
        return None
    return int(round(sum(samples) / len(samples)))


def _is_valid_rating(value: object) -> bool:
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return value >= 0


def _is_racing_driver(row: RosterRow | Mapping[str, object]) -> bool:
    if _row_flag(row, "car_is_pace_car"):
        return False
    if _row_flag(row, "is_spectator"):
        return False
    return True


def _row_flag(row: RosterRow | Mapping[str, object], name: str) -> bool:
    if isinstance(row, Mapping):
        if name not in row:
            return False
        raw = row.get(name)
    else:
        raw = getattr(row, name, False)
    if raw is None:
        return False
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, (int, float)):
        return raw != 0
    return str(raw).lower() in {"1", "true", "yes", "on"}


def _row_rating(row: RosterRow | Mapping[str, object]) -> int | None:
    if isinstance(row, Mapping):
        raw = row.get("i_rating")
    else:
        raw = getattr(row, "i_rating", None)
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw if raw >= 0 else None
    if isinstance(raw, float):
        if raw != raw or raw < 0:  # NaN or negative
            return None
        return int(raw)
    try:
        parsed = int(str(raw))
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def _row_class_id(row: RosterRow | Mapping[str, object]) -> int | None:
    if isinstance(row, Mapping):
        raw = row.get("car_class_id")
    else:
        raw = getattr(row, "car_class_id", None)
    if raw is None or isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw
    if isinstance(raw, float):
        if raw != raw:
            return None
        return int(raw)
    try:
        return int(str(raw))
    except ValueError:
        return None
