"""Session-scoped, immutable driver facts for the N12 context boundary."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass, replace
from typing import Literal, TypeVar

from irswitch.iracing.drivers import speakable_driver_name
from irswitch.overlay.models import TelemetrySnapshot

StartPositionScope = Literal["class", "overall"]
_T = TypeVar("_T")


@dataclass(frozen=True)
class DriverProfileSnapshot:
    car_idx: int
    user_id: int | None
    display_name: str | None
    i_rating: int | None
    safety_rating: str | None
    car_name: str | None
    nationality: None
    start_position: int | None
    start_position_scope: StartPositionScope | None
    session_id: str
    identity_epoch: int
    roster_revision: str
    observed_monotonic_ms: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class DriverFactLedger:
    """Retain valid static facts without leaking them across identities/sessions."""

    def __init__(self) -> None:
        self._session_id = "session:unknown"
        self._profiles: dict[int, DriverProfileSnapshot] = {}
        self._roster_digest = ""
        self._grid_captured = False
        self._grid_fallback = False

    @property
    def grid_fallback(self) -> bool:
        return self._grid_fallback

    def reset(self, session_id: str = "session:unknown") -> None:
        self._session_id = session_id or "session:unknown"
        self._profiles.clear()
        self._roster_digest = ""
        self._grid_captured = False
        self._grid_fallback = False

    def refresh(
        self,
        telemetry_data: Mapping[str, object] | None,
        snapshot: TelemetrySnapshot,
        *,
        session_id: str,
        observed_monotonic_ms: int,
    ) -> None:
        if not snapshot.connected:
            self.reset(session_id)
            return
        if session_id != self._session_id:
            self.reset(session_id)
        rows = _driver_rows((telemetry_data or {}).get("DriverInfo"))
        digest = _digest(rows)
        if digest != self._roster_digest:
            self._refresh_roster(rows, digest, observed_monotonic_ms)
            self._roster_digest = digest
        else:
            self._touch(observed_monotonic_ms)
        self._capture_start_grid(snapshot)

    def snapshot(self) -> dict[str, object]:
        return {
            "profiles": {
                str(car_idx): profile.to_dict()
                for car_idx, profile in sorted(self._profiles.items())
            },
            "roster_revision": self._roster_digest,
            "start_grid_captured": self._grid_captured,
            "start_grid_green_fallback": self._grid_fallback,
        }

    def profiles_snapshot(self) -> dict[str, object]:
        return self.snapshot()["profiles"]  # type: ignore[return-value]

    def _refresh_roster(
        self,
        rows: Sequence[Mapping[str, object]],
        digest: str,
        observed_monotonic_ms: int,
    ) -> None:
        updated: dict[int, DriverProfileSnapshot] = {}
        for row in rows:
            car_idx = _non_negative_int(row.get("CarIdx"))
            if car_idx is None:
                continue
            user_id = _non_negative_int(row.get("UserID"))
            old = self._profiles.get(car_idx)
            same_identity = old is not None and old.user_id == user_id
            epoch = old.identity_epoch if same_identity else (old.identity_epoch + 1 if old else 1)
            updated[car_idx] = DriverProfileSnapshot(
                car_idx=car_idx,
                user_id=user_id,
                display_name=_clean(row.get("UserName")) or speakable_driver_name(row),
                i_rating=_prefer_valid(
                    _valid_i_rating(row.get("IRating")),
                    old.i_rating if same_identity else None,
                ),
                safety_rating=_prefer_valid(
                    _safety_rating(row.get("LicString")),
                    old.safety_rating if same_identity else None,
                ),
                car_name=_clean(row.get("CarScreenName"))
                or _clean(row.get("CarScreenNameShort"))
                or (old.car_name if same_identity else None),
                nationality=None,
                start_position=(old.start_position if same_identity else None),
                start_position_scope=(old.start_position_scope if same_identity else None),
                session_id=self._session_id,
                identity_epoch=epoch,
                roster_revision=digest,
                observed_monotonic_ms=observed_monotonic_ms,
            )
        self._profiles = updated

    def _touch(self, observed_monotonic_ms: int) -> None:
        self._profiles = {
            car_idx: replace(profile, observed_monotonic_ms=observed_monotonic_ms)
            for car_idx, profile in self._profiles.items()
        }

    def _capture_start_grid(self, snapshot: TelemetrySnapshot) -> None:
        if self._grid_captured or snapshot.session_type != "Race":
            return
        state = snapshot.session_state
        if state is None or state < 3:
            return
        green_fallback = state >= 4
        class_ids = {value for value in snapshot.car_idx_class if value is not None}
        multiclass = len(class_ids) > 1
        positions = snapshot.car_idx_class_position if multiclass else snapshot.car_idx_position
        valid = [
            _position_at(positions, car_idx)
            for car_idx in self._profiles
            if _position_at(positions, car_idx) is not None
        ]
        if not valid:
            return
        scope: StartPositionScope = "class" if multiclass else "overall"
        self._profiles = {
            car_idx: replace(
                profile,
                start_position=_position_at(positions, car_idx),
                start_position_scope=(
                    scope if _position_at(positions, car_idx) is not None else None
                ),
            )
            for car_idx, profile in self._profiles.items()
        }
        self._grid_captured = True
        self._grid_fallback = green_fallback


def _driver_rows(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, Mapping):
        return ()
    drivers = value.get("Drivers")
    if not isinstance(drivers, Sequence) or isinstance(drivers, (str, bytes)):
        return ()
    return tuple(row for row in drivers if isinstance(row, Mapping))


def _digest(rows: Sequence[Mapping[str, object]]) -> str:
    try:
        payload = json.dumps(rows, sort_keys=True, separators=(",", ":"), default=str)
    except (TypeError, ValueError):
        payload = repr(rows)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16] if rows else ""


def _non_negative_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0 or not number.is_integer():
        return None
    return int(number)


def _valid_i_rating(value: object) -> int | None:
    return _non_negative_int(value)


def _prefer_valid(current: _T | None, previous: _T | None) -> _T | None:
    return current if current is not None else previous


def _clean(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _safety_rating(value: object) -> str | None:
    text = _clean(value)
    if text is None:
        return None
    match = re.fullmatch(r"\s*([A-Za-z])\s*([0-9](?:\.[0-9]{1,2})?)\s*", text)
    if match is None:
        return None
    return f"{match.group(1).upper()} {float(match.group(2)):.2f}"


def _position_at(values: Sequence[int | None], car_idx: int) -> int | None:
    if car_idx < 0 or car_idx >= len(values):
        return None
    value = values[car_idx]
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None
