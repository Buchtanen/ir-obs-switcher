"""Fail-soft SessionInfo track + DriverInfo roster for commentary intros.

Pure extraction helpers (no race logic, no SoF math, no weather). Callers pass
dict-like SDK / SessionInfo fixtures. Missing or malformed fields are normal
state — helpers return ``None`` / empty structures and never raise into the
main loop.

Cache identity is ``(SubSessionID, SessionNum)``; invalidate when that changes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from irswitch.iracing.drivers import speakable_driver_name
from irswitch.iracing.extractors import as_bool, as_int


@dataclass(frozen=True)
class RosterDriver:
    """One racing-eligible DriverInfo row after pace-car / spectator filters."""

    car_idx: int
    i_rating: int | None
    car_class_id: int | None
    car_is_pace_car: bool
    is_spectator: bool
    display_name: str | None = None


@dataclass(frozen=True)
class SessionContext:
    """Normalized circuit + roster snapshot for session intros / SoF inputs."""

    track: str | None
    roster: tuple[RosterDriver, ...]
    player_car_idx: int | None = None
    player_class_id: int | None = None


def track_display_name(weekend_info: object) -> str | None:
    """Build a speakable circuit name from WeekendInfo.

    Uses ``TrackDisplayName``; optionally appends ``TrackConfigName`` when it is
    non-empty and not already contained in the display name. Never returns
    ``TrackID`` alone as the spoken name.
    """
    try:
        weekend = _as_mapping(weekend_info)
        if weekend is None:
            return None
        display = _clean_str(weekend.get("TrackDisplayName"))
        if not display:
            return None
        config = _clean_str(weekend.get("TrackConfigName"))
        if config and config.lower() not in display.lower():
            return f"{display} - {config}"
        return display
    except Exception:
        return None


def parse_roster(driver_info: object) -> tuple[RosterDriver, ...]:
    """Parse ``DriverInfo.Drivers[]`` into racing-eligible roster rows.

    Excludes pace cars (``CarIsPaceCar != 0``), spectators (``IsSpectator``
    truthy), invalid ``CarIdx`` (< 0 or non-numeric), and empty / non-mapping
    rows.

    Missing ``IsSpectator`` is treated **conservatively as spectator** (row
    excluded). Prefer a false positive exclusion over inflating field size /
    SoF with an ambiguous entry. Missing ``CarIsPaceCar`` is treated as not a
    pace car (include). Invalid / missing ``IRating`` yields ``i_rating=None``
    but the driver remains in the roster when otherwise eligible.
    """
    try:
        drivers = _drivers_list(driver_info)
        if not drivers:
            return ()
        out: list[RosterDriver] = []
        for row in drivers:
            parsed = _parse_driver_row(row)
            if parsed is not None:
                out.append(parsed)
        return tuple(out)
    except Exception:
        return ()


def session_key(data: object) -> tuple[int, int] | None:
    """Return ``(SubSessionID, SessionNum)`` when both are available.

    ``SubSessionID`` may come from the top-level SDK var or
    ``WeekendInfo.SubSessionID``. Returns ``None`` when either part is missing
    or not convertible to int.
    """
    try:
        mapping = _as_mapping(data)
        if mapping is None:
            return None
        sub = as_int(mapping.get("SubSessionID"))
        if sub is None:
            weekend = _as_mapping(mapping.get("WeekendInfo"))
            if weekend is not None:
                sub = as_int(weekend.get("SubSessionID"))
        session_num = as_int(mapping.get("SessionNum"))
        if sub is None or session_num is None:
            return None
        return (sub, session_num)
    except Exception:
        return None


def extract_session_context(data: object) -> SessionContext | None:
    """Extract track display name + racing roster + player class hints.

    Fail-soft: returns ``None`` only when ``data`` is not a mapping (or an
    unexpected error escapes inner helpers). Sparse but valid mappings yield a
    ``SessionContext`` with ``track=None`` and/or an empty roster.
    """
    try:
        mapping = _as_mapping(data)
        if mapping is None:
            return None
        weekend = mapping.get("WeekendInfo")
        driver_info = mapping.get("DriverInfo")
        track = track_display_name(weekend)
        roster = parse_roster(driver_info)
        player_car_idx = _player_car_idx(mapping, driver_info)
        player_class_id = _player_class_id(mapping, driver_info, roster, player_car_idx)
        return SessionContext(
            track=track,
            roster=roster,
            player_car_idx=player_car_idx,
            player_class_id=player_class_id,
        )
    except Exception:
        return None


class SessionContextCache:
    """Cache ``SessionContext`` by ``(SubSessionID, SessionNum)``.

    Invalidates automatically when ``session_key(data)`` changes. A missing
    key clears the cache and re-extracts (no stale cross-session reuse).
    """

    def __init__(self) -> None:
        self._key: tuple[int, int] | None = None
        self._context: SessionContext | None = None

    @property
    def key(self) -> tuple[int, int] | None:
        return self._key

    @property
    def context(self) -> SessionContext | None:
        return self._context

    def clear(self) -> None:
        self._key = None
        self._context = None

    def get_or_extract(self, data: object) -> SessionContext | None:
        """Return cached context for the current session key, else extract."""
        try:
            key = session_key(data)
            if key is not None and key == self._key and self._context is not None:
                return self._context
            ctx = extract_session_context(data)
            self._key = key
            self._context = ctx
            return ctx
        except Exception:
            self.clear()
            return None


def _parse_driver_row(row: object) -> RosterDriver | None:
    if not isinstance(row, Mapping):
        return None
    if not row:
        return None
    car_idx = as_int(row.get("CarIdx"))
    if car_idx is None or car_idx < 0:
        return None

    # Pace car: missing key → not a pace car (include).
    if "CarIsPaceCar" in row and as_bool(row.get("CarIsPaceCar")):
        return None

    # Spectator: missing key → exclude (conservative).
    if "IsSpectator" not in row:
        return None
    if as_bool(row.get("IsSpectator")):
        return None

    return RosterDriver(
        car_idx=car_idx,
        i_rating=_parse_irating(row.get("IRating")),
        car_class_id=as_int(row.get("CarClassID")),
        car_is_pace_car=False,
        is_spectator=False,
        display_name=speakable_driver_name(row),
    )


def _parse_irating(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    rating = as_int(value)
    if rating is None or rating < 0:
        return None
    return rating


def _player_car_idx(data: Mapping[str, Any], driver_info: object) -> int | None:
    info = _as_mapping(driver_info)
    if info is not None:
        idx = as_int(info.get("DriverCarIdx"))
        if idx is not None and idx >= 0:
            return idx
    idx = as_int(data.get("PlayerCarIdx"))
    if idx is not None and idx >= 0:
        return idx
    return None


def _player_class_id(
    data: Mapping[str, Any],
    driver_info: object,
    roster: tuple[RosterDriver, ...],
    player_car_idx: int | None,
) -> int | None:
    if player_car_idx is not None:
        for driver in roster:
            if driver.car_idx == player_car_idx and driver.car_class_id is not None:
                return driver.car_class_id
        # Player may have been filtered out; look at raw Drivers[] row.
        for row in _drivers_list(driver_info):
            if not isinstance(row, Mapping):
                continue
            if as_int(row.get("CarIdx")) == player_car_idx:
                class_id = as_int(row.get("CarClassID"))
                if class_id is not None:
                    return class_id
                break
    direct = as_int(data.get("PlayerCarClass"))
    if direct is not None:
        return direct
    return None


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


def _as_mapping(value: object) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return value
    if hasattr(value, "__dict__"):
        raw = getattr(value, "__dict__", None)
        if isinstance(raw, Mapping):
            return raw
    return None


def _clean_str(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()
