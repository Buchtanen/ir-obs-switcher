"""Extract speakable driver names from iRSDK DriverInfo (session YAML)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


def speakable_driver_name(driver: Mapping[str, Any]) -> str | None:
    """Pick a short broadcast name from one DriverInfo Drivers[] row.

    Prefers the last token of ``UserName`` (e.g. ``Rossi``), then ``AbbrevName``,
    then ``Initials``. Returns None when nothing usable is present.
    """
    user = _clean(driver.get("UserName"))
    if user:
        parts = user.replace(",", " ").split()
        if len(parts) >= 2:
            return parts[-1]
        return user
    abbrev = _clean(driver.get("AbbrevName"))
    if abbrev:
        # "J. Smith" / "Smith" → last token without trailing dots
        parts = abbrev.replace(",", " ").split()
        token = parts[-1].rstrip(".") if parts else abbrev
        return token or None
    initials = _clean(driver.get("Initials"))
    return initials or None


def driver_names_by_car_idx(driver_info: object) -> tuple[str | None, ...]:
    """Build a CarIdx-indexed tuple of speakable names from DriverInfo."""
    drivers = _drivers_list(driver_info)
    if not drivers:
        return ()
    max_idx = -1
    parsed: list[tuple[int, str]] = []
    for row in drivers:
        if not isinstance(row, Mapping):
            continue
        idx = row.get("CarIdx")
        if not isinstance(idx, (int, float)):
            continue
        car_idx = int(idx)
        if car_idx < 0:
            continue
        name = speakable_driver_name(row)
        if not name:
            continue
        parsed.append((car_idx, name))
        if car_idx > max_idx:
            max_idx = car_idx
    if max_idx < 0:
        return ()
    out: list[str | None] = [None] * (max_idx + 1)
    for car_idx, name in parsed:
        out[car_idx] = name
    return tuple(out)


def name_for_car_idx(names: Sequence[str | None], car_idx: int | None) -> str | None:
    if car_idx is None or car_idx < 0 or car_idx >= len(names):
        return None
    value = names[car_idx]
    return value if value else None


def _drivers_list(driver_info: object) -> Sequence[object]:
    if driver_info is None:
        return ()
    if isinstance(driver_info, Mapping):
        drivers = driver_info.get("Drivers")
        if isinstance(drivers, Sequence) and not isinstance(drivers, (str, bytes)):
            return drivers
        return ()
    drivers = getattr(driver_info, "Drivers", None)
    if isinstance(drivers, Sequence) and not isinstance(drivers, (str, bytes)):
        return drivers
    return ()


def _clean(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return text
