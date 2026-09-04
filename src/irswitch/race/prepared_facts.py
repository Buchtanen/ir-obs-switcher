"""Producer-owned normalized facts for graph-driven prepared commentary.

Raw iRSDK mappings are unreliable and sparse.  This collector emits only
explicitly evidenced, JSON-safe values and retains short transition facts for
the current editorial stage so asynchronous generation cannot miss an edge.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, cast

from irswitch.iracing.extractors import as_bool, as_int
from irswitch.iracing.session_context import extract_session_context
from irswitch.iracing.sof import RosterRow, compute_sof_bundle
from irswitch.iracing.weather import extract_weather
from irswitch.overlay.models import BioState, RaceState

_ENGINE_STALLED = 0x8
_ON_TRACK = 3
_LENGTH = re.compile(r"^\s*(-?\d+(?:[.,]\d+)?)\s*(km|mi|m)?\s*$", re.IGNORECASE)


class PreparedFactCollector:
    """Collect static facts and hold stage-scoped transition evidence."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self._key: tuple[str, int, int] | None = None
        self._stage_epoch = -1
        self._held: dict[str, object] = {}
        self._previous_in_car = False
        self._ever_in_car = False
        self._previous_speed: float | None = None
        self._previous_stalled: bool | None = None
        self._quiet_since_ms: int | None = None
        self._moving_since_ms: int | None = None

    def observe(
        self,
        data: Mapping[str, object] | None,
        race: RaceState,
        bio: BioState,
        *,
        stage: str,
        stage_epoch: int,
        now_ms: int,
        in_car: bool,
    ) -> dict[str, object]:
        if not race.connected:
            self.reset()
            return {}
        key = (str(race.subsession_id or ""), int(race.session_num or 0), race.run_epoch)
        if key != self._key:
            self.reset()
            self._key = key
        if stage_epoch != self._stage_epoch:
            self._stage_epoch = stage_epoch
            self._held.clear()
            self._quiet_since_ms = None
            self._moving_since_ms = None

        facts = extract_prepared_session_facts(data, player_class_id=race.player_car_class)
        speed = _finite_number(race.speed_mps)
        stalled = _engine_stalled(data)
        rpm = _finite_number(_get(data, "RPM"))

        if self._previous_stalled is True and stalled is False and rpm is not None and rpm > 100:
            self._held["engine_state"] = "started"
        if (
            in_car
            and speed is not None
            and speed > 1.0
            and (self._previous_speed is None or self._previous_speed <= 1.0)
        ):
            self._held["rollout_state"] = "moving"
        if in_car and not self._previous_in_car and self._ever_in_car:
            self._held["returned_to_car"] = True

        flags = set(race.session_flag_names)
        if "startReady" in flags:
            self._held["start_ready"] = True
        if "startSet" in flags:
            self._held["start_set"] = True

        circulating = _circulating_cars(data)
        if circulating is not None:
            facts["circulating_cars"] = circulating
            quiet = race.overlay_mode == "PRACTICE" and circulating <= 3
            if quiet:
                if self._quiet_since_ms is None:
                    self._quiet_since_ms = now_ms
                if now_ms - self._quiet_since_ms >= 10_000:
                    facts["circulating_cars"] = circulating
                else:
                    facts.pop("circulating_cars", None)
            else:
                self._quiet_since_ms = None

        if race.opponent_ahead is not None or race.opponent_behind is not None:
            facts["traffic_band"] = "nearby"
        elif in_car:
            facts["traffic_band"] = "clear"

        if race.session_state == 3:
            facts["formation_state"] = "formation"
            if speed is not None and speed > 1.0:
                if self._moving_since_ms is None:
                    self._moving_since_ms = now_ms
                if now_ms - self._moving_since_ms >= 2_000 and _near_start_line(race, facts, speed):
                    facts["distance_to_start"] = "near"
            else:
                self._moving_since_ms = None
        else:
            self._moving_since_ms = None

        if bio.state in {"calm", "focused", "pushing", "high"}:
            facts["hr_band"] = bio.state
        if stage == "SESSION_CONCLUSION" and not in_car and self._ever_in_car:
            facts["lobby_break"] = True

        facts.update(self._held)
        self._previous_in_car = in_car
        self._ever_in_car = self._ever_in_car or in_car
        self._previous_speed = speed
        self._previous_stalled = stalled
        return facts


def extract_prepared_session_facts(
    data: Mapping[str, object] | None,
    *,
    player_class_id: int | None,
) -> dict[str, object]:
    """Extract nullable circuit, weather, roster and start facts without guessing."""
    if not isinstance(data, Mapping):
        return {}
    facts: dict[str, object] = {}
    weekend = _mapping(data.get("WeekendInfo"))
    options = _mapping(weekend.get("WeekendOptions"))
    _copy_text(facts, "layout", weekend.get("TrackConfigName"))
    _copy_text(facts, "city", weekend.get("TrackCity"))
    _copy_text(facts, "country", weekend.get("TrackCountry"))
    _copy_text(facts, "track_type", weekend.get("TrackType"))
    _copy_text(facts, "track_direction", weekend.get("TrackDirection"))
    length = _track_length_km(weekend.get("TrackLength"))
    if length is not None:
        facts["circuit_length"] = length
    turns = as_int(weekend.get("TrackNumTurns"))
    if turns is not None and turns > 0:
        facts["turn_count"] = turns

    standing = _optional_bool(options.get("StandingStart"))
    if standing is not None:
        facts["start_mode"] = "standing" if standing else "rolling"

    weather = extract_weather(data, prefer="live")
    if weather.skies:
        facts["sky"] = weather.skies
    if weather.air_temp_c is not None:
        facts["air_temperature"] = weather.air_temp_c
    if weather.track_temp_c is not None:
        facts["track_temperature"] = weather.track_temp_c
    if weather.wind_speed_mps is not None:
        facts["wind_speed"] = weather.wind_speed_mps
    if weather.precipitation is not None:
        facts["precipitation"] = weather.precipitation
    wetness = _surface_wetness(weather.track_wetness, weather.weather_declared_wet)
    if wetness is not None:
        facts["surface_wetness"] = wetness
    rubber = _rubber_state(data)
    if rubber:
        facts["rubber_state"] = rubber

    ctx = extract_session_context(data)
    if ctx is not None:
        if ctx.track:
            facts["track"] = ctx.track
        bundle = compute_sof_bundle(
            cast("Iterable[RosterRow]", ctx.roster), player_class_id
        )
        if bundle.field_size > 0:
            facts["field_size"] = bundle.field_size
        if bundle.overall is not None and bundle.overall > 0:
            facts["overall_sof"] = bundle.overall
        if bundle.class_sof is not None and bundle.class_sof > 0:
            facts["class_sof"] = bundle.class_sof
        class_rows = [row for row in ctx.roster if row.car_class_id == player_class_id]
        if class_rows:
            facts["class_field_size"] = len(class_rows)
        ai_count = _ai_count(data, {row.car_idx for row in ctx.roster})
        if ai_count > 0 and bundle.field_size > 0:
            facts["ai_count"] = ai_count
            facts["ai_ratio"] = ai_count / bundle.field_size
        rated = [
            row
            for row in class_rows
            if row.i_rating is not None and row.i_rating > 0 and row.display_name
        ]
        if rated:
            winner = min(rated, key=lambda row: (-int(row.i_rating or 0), row.car_idx))
            facts["highest_rated_driver"] = str(winner.display_name)
    return facts


def _near_start_line(race: RaceState, facts: Mapping[str, object], speed: float) -> bool:
    length_km = _finite_number(facts.get("circuit_length"))
    lap_pct = _finite_number(race.player_lap_dist_pct)
    if length_km is None or length_km <= 0 or lap_pct is None or not 0 <= lap_pct <= 1:
        return False
    remaining_m = (1.0 - lap_pct) * length_km * 1000.0
    return 0 <= remaining_m <= speed * 12.0


def _circulating_cars(data: Mapping[str, object] | None) -> int | None:
    if not isinstance(data, Mapping):
        return None
    ctx = extract_session_context(data)
    if ctx is None or not ctx.roster:
        return None
    eligible = {row.car_idx for row in ctx.roster}
    surfaces = _sequence(_get(data, "CarIdxTrackSurface"))
    pits = _sequence(_get(data, "CarIdxOnPitRoad"))
    if surfaces is None:
        return None
    count = 0
    for index, raw in enumerate(surfaces):
        if index not in eligible:
            continue
        surface = as_int(raw)
        on_pit = as_bool(pits[index]) if pits is not None and index < len(pits) else False
        if surface == _ON_TRACK and not on_pit:
            count += 1
    return count


def _engine_stalled(data: Mapping[str, object] | None) -> bool | None:
    raw = as_int(_get(data, "EngineWarnings"))
    return bool(raw & _ENGINE_STALLED) if raw is not None else None


def _rubber_state(data: Mapping[str, object]) -> str | None:
    session_info = _mapping(data.get("SessionInfo"))
    sessions = _sequence(session_info.get("Sessions"))
    number = as_int(data.get("SessionNum"))
    if sessions is None or number is None or number < 0 or number >= len(sessions):
        return None
    session = _mapping(sessions[number])
    value = session.get("SessionTrackRubberState")
    return _text(value)


def _ai_count(data: Mapping[str, object], eligible: set[int]) -> int:
    info = _mapping(data.get("DriverInfo"))
    rows = _sequence(info.get("Drivers"))
    if rows is None:
        return 0
    count = 0
    for raw in rows:
        row = _mapping(raw)
        idx = as_int(row.get("CarIdx"))
        if idx in eligible and as_bool(row.get("CarIsAI")):
            count += 1
    return count


def _surface_wetness(value: int | None, declared: bool | None) -> str | None:
    if value is not None:
        if value <= 0:
            return "wet" if declared is True else None
        if value <= 2:
            return "dry"
        if value == 3:
            return "damp"
        return "wet"
    return "wet" if declared is True else None


def _track_length_km(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    match = _LENGTH.match(str(value))
    if not match:
        return None
    number = float(match.group(1).replace(",", "."))
    unit = (match.group(2) or "km").lower()
    if unit == "mi":
        number *= 1.609344
    elif unit == "m":
        number /= 1000.0
    return round(number, 3) if math.isfinite(number) and 0 < number < 100 else None


def _copy_text(target: dict[str, object], key: str, value: object) -> None:
    text = _text(value)
    if text:
        target[key] = text


def _get(mapping: Mapping[str, object] | None, key: str) -> object:
    return mapping.get(key) if isinstance(mapping, Mapping) else None


def _mapping(value: object) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: object) -> Sequence[Any] | None:
    return value if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) else None


def _text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = " ".join(value.split())
    return text or None


def _finite_number(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def _optional_bool(value: object) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"0", "false", "no", "off"}:
            return False
        if normalized in {"1", "true", "yes", "on"}:
            return True
        return None
    return as_bool(value)
