"""Fail-soft weather extraction + spoken formatters for commentary.

Pure helpers over dict-like SDK / SessionInfo fixtures. Missing or malformed
fields are normal state — never raise into the main loop.

Sources (do not silently swap forecast and live):

* **live** — telemetry: ``Skies``, ``AirTemp``, ``TrackTempCrew``/``TrackTemp``,
  ``WindVel``, ``Precipitation``, ``TrackWetness``, ``WeatherDeclaredWet``
* **session** — ``WeekendInfo.Track*`` current-condition fallbacks
* **forecast** — ``WeekendInfo.WeekendOptions.*`` pre-session plan only

``prefer`` selects a coherent layer. Live may fall back to session (same
"current" family) and tag ``mixed`` when both contribute. Forecast never
pulls live/session values, and live/session never pull forecast.

Spoken formatters are EN/CS labels for graph slots ``skies``, ``air_temp``,
``track_temp``, ``wind_speed``, ``precipitation``. Emitter wiring is H4.
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Final, Literal

from irswitch.iracing.extractors import as_bool, as_int

WeatherSource = Literal["live", "session", "forecast", "mixed"]
WeatherPrefer = Literal["live", "session", "forecast"]
LocaleCode = Literal["en", "cs"]

# Live Skies enum (irsdk)
_SKIES_BY_INT: Final[dict[int, str]] = {
    0: "clear",
    1: "partly cloudy",
    2: "mostly cloudy",
    3: "overcast",
}

_SKIES_ALIASES: Final[dict[str, str]] = {
    "clear": "clear",
    "sunny": "clear",
    "partly cloudy": "partly cloudy",
    "partlycloudy": "partly cloudy",
    "p cloudy": "partly cloudy",
    "pcloudy": "partly cloudy",
    "mostly cloudy": "mostly cloudy",
    "mostlycloudy": "mostly cloudy",
    "m cloudy": "mostly cloudy",
    "mcloudy": "mostly cloudy",
    "cloudy": "mostly cloudy",
    "overcast": "overcast",
}

_SKIES_SPOKEN: Final[dict[str, dict[str, str]]] = {
    "en": {
        "clear": "clear",
        "partly cloudy": "partly cloudy",
        "mostly cloudy": "mostly cloudy",
        "overcast": "overcast",
    },
    "cs": {
        "clear": "jasno",
        "partly cloudy": "polojasno",
        "mostly cloudy": "oblačno",
        "overcast": "zataženo",
    },
}

# Precipitation intensity keys → spoken labels
_PRECIP_SPOKEN: Final[dict[str, dict[str, str]]] = {
    "en": {
        "none": "dry",
        "light": "light rain",
        "moderate": "rain",
        "heavy": "heavy rain",
        "wet_track": "wet track",
    },
    "cs": {
        "none": "sucho",
        "light": "slabý déšť",
        "moderate": "déšť",
        "heavy": "silný déšť",
        "wet_track": "mokrý povrch",
    },
}

# irsdk_TrackWetness: 0 unknown … 7 extremely wet
_WETNESS_LIGHTLY_WET: Final = 4

_TEMP_RE: Final = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(?:°\s*)?([cCfF])?\s*$")
_WIND_RE: Final = re.compile(
    r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*(km/?h|kph|m/?s|mph)?\s*$",
    re.IGNORECASE,
)
_KMH_TO_MPS: Final = 1.0 / 3.6
_MPH_TO_MPS: Final = 0.44704


@dataclass(frozen=True, slots=True)
class WeatherSnapshot:
    """Normalized weather observation for commentary slot binding.

    Numeric fields are in SI-ish speech units (Celsius, m/s, precip 0..1).
    ``skies`` is a canonical English key (``clear`` / ``partly cloudy`` / …)
    or ``None``. ``source`` is honest about live vs session vs forecast mix.
    ``field_sources`` maps populated slot names to the layer that supplied them.
    """

    skies: str | None = None
    air_temp_c: float | None = None
    track_temp_c: float | None = None
    wind_speed_mps: float | None = None
    precipitation: float | None = None
    track_wetness: int | None = None
    weather_declared_wet: bool | None = None
    source: WeatherSource = "live"
    field_sources: Mapping[str, WeatherSource] = field(default_factory=dict)


def extract_weather(
    data: object,
    *,
    prefer: WeatherPrefer = "live",
) -> WeatherSnapshot:
    """Parse weather from a telemetry / SessionInfo-like mapping.

    Fail-soft: bad input → empty snapshot with ``source`` matching ``prefer``
    (never raises). Partial fields are allowed (``None``).
    """
    try:
        mapping = _as_mapping(data)
        if mapping is None:
            return WeatherSnapshot(source=prefer, field_sources={})

        weekend = _as_mapping(mapping.get("WeekendInfo")) or {}
        options = _as_mapping(weekend.get("WeekendOptions")) or {}

        if prefer == "forecast":
            return _extract_forecast(options)
        if prefer == "session":
            return _extract_session(weekend, mapping)
        return _extract_live_with_session_fallback(mapping, weekend)
    except Exception:
        return WeatherSnapshot(source=prefer, field_sources={})


def format_skies(value: object, locale: LocaleCode = "en") -> str | None:
    """Spoken sky label from enum int, canonical key, or SessionInfo string."""
    key = _normalize_skies(value)
    if key is None:
        return None
    table = _SKIES_SPOKEN.get(locale) or _SKIES_SPOKEN["en"]
    return table.get(key)


def format_air_temp(celsius: object, locale: LocaleCode = "en") -> str | None:
    """Spoken air temperature, e.g. ``23 C`` (locale does not change unit)."""
    del locale  # reserved for future spoken forms
    return _format_temp_c(celsius)


def format_track_temp(celsius: object, locale: LocaleCode = "en") -> str | None:
    """Spoken track temperature, e.g. ``31 C``."""
    del locale
    return _format_temp_c(celsius)


def format_wind_speed(mps: object, locale: LocaleCode = "en") -> str | None:
    """Spoken wind speed already in m/s, e.g. ``4 m/s``."""
    del locale
    speed = _as_finite_float(mps)
    if speed is None or speed < 0:
        return None
    return f"{int(round(speed))} m/s"


def format_precipitation(
    precip: object,
    *,
    track_wetness: object = None,
    weather_declared_wet: object = None,
    locale: LocaleCode = "en",
) -> str | None:
    """Spoken precip / surface wetness from live intensity + corroboration.

    Never invents rain from skies. Wet track without measurable rain →
    ``wet track`` / ``mokrý povrch``. Missing everything → ``None``.
    """
    intensity = _precip_fraction(precip)
    wetness = as_int(track_wetness)
    declared = _optional_bool(weather_declared_wet)

    table = _PRECIP_SPOKEN.get(locale) or _PRECIP_SPOKEN["en"]
    key = _precip_vocab_key(intensity, wetness=wetness, declared=declared)
    if key is None:
        return None
    return table.get(key)


def spoken_weather_bindings(
    snapshot: WeatherSnapshot,
    locale: LocaleCode = "en",
) -> dict[str, str | None]:
    """Map a snapshot to the five commentary weather slot labels."""
    return {
        "skies": format_skies(snapshot.skies, locale),
        "air_temp": format_air_temp(snapshot.air_temp_c, locale),
        "track_temp": format_track_temp(snapshot.track_temp_c, locale),
        "wind_speed": format_wind_speed(snapshot.wind_speed_mps, locale),
        "precipitation": format_precipitation(
            snapshot.precipitation,
            track_wetness=snapshot.track_wetness,
            weather_declared_wet=snapshot.weather_declared_wet,
            locale=locale,
        ),
    }


def compose_weather_brief(
    snapshot: WeatherSnapshot,
    locale: LocaleCode = "en",
) -> str | None:
    """Optional short composed phrase for tests / previews (≤ ~90 chars).

    Not wired to the director; H4 will emit slot-bound graph lines instead.
    """
    b = spoken_weather_bindings(snapshot, locale)
    parts: list[str] = []
    if b["skies"]:
        parts.append(b["skies"])
    if b["air_temp"]:
        parts.append(b["air_temp"])
    if b["wind_speed"]:
        parts.append(b["wind_speed"])
    if b["precipitation"] and b["precipitation"] not in {"dry", "sucho"}:
        parts.append(b["precipitation"])
    if not parts:
        return None
    if locale == "cs":
        text = "Počasí: " + ", ".join(parts) + "."
    else:
        text = "Weather: " + ", ".join(parts) + "."
    return text if len(text) <= 90 else text[:89].rstrip() + "."


# --- extraction layers -------------------------------------------------------


def _extract_forecast(options: Mapping[str, Any]) -> WeatherSnapshot:
    fields: dict[str, WeatherSource] = {}
    skies = _normalize_skies(options.get("Skies"))
    if skies is not None:
        fields["skies"] = "forecast"
    air = _parse_temp_c(options.get("WeatherTemp"))
    if air is not None:
        fields["air_temp"] = "forecast"
    wind = _parse_wind_mps(options.get("WindSpeed"), default_unit="km/h")
    if wind is not None:
        fields["wind_speed"] = "forecast"
    # No evidenced forecast track_temp / precipitation keys.
    return WeatherSnapshot(
        skies=skies,
        air_temp_c=air,
        track_temp_c=None,
        wind_speed_mps=wind,
        precipitation=None,
        track_wetness=None,
        weather_declared_wet=None,
        source="forecast",
        field_sources=fields,
    )


def _extract_session(
    weekend: Mapping[str, Any],
    mapping: Mapping[str, Any],
) -> WeatherSnapshot:
    del mapping  # session prefer stays on WeekendInfo Track* only
    fields: dict[str, WeatherSource] = {}
    skies = _normalize_skies(weekend.get("TrackSkies"))
    if skies is not None:
        fields["skies"] = "session"
    air = _parse_temp_c(weekend.get("TrackAirTemp"))
    if air is not None:
        fields["air_temp"] = "session"
    track = _parse_temp_c(weekend.get("TrackSurfaceTemp"))
    if track is not None:
        fields["track_temp"] = "session"
    wind = _parse_wind_mps(weekend.get("TrackWindVel"), default_unit="m/s")
    if wind is not None:
        fields["wind_speed"] = "session"
    # No evidenced SessionInfo precipitation / wetness keys for this layer.
    return WeatherSnapshot(
        skies=skies,
        air_temp_c=air,
        track_temp_c=track,
        wind_speed_mps=wind,
        precipitation=None,
        track_wetness=None,
        weather_declared_wet=None,
        source="session",
        field_sources=fields,
    )


def _extract_live_with_session_fallback(
    mapping: Mapping[str, Any],
    weekend: Mapping[str, Any],
) -> WeatherSnapshot:
    fields: dict[str, WeatherSource] = {}

    skies, skies_src = _pick_skies(mapping, weekend)
    if skies is not None and skies_src is not None:
        fields["skies"] = skies_src

    air, air_src = _pick_temp(
        live_keys=("AirTemp",),
        session_value=weekend.get("TrackAirTemp"),
        mapping=mapping,
    )
    if air is not None and air_src is not None:
        fields["air_temp"] = air_src

    track, track_src = _pick_temp(
        live_keys=("TrackTempCrew", "TrackTemp"),
        session_value=weekend.get("TrackSurfaceTemp"),
        mapping=mapping,
    )
    if track is not None and track_src is not None:
        fields["track_temp"] = track_src

    wind, wind_src = _pick_wind(mapping, weekend)
    if wind is not None and wind_src is not None:
        fields["wind_speed"] = wind_src

    precip = _precip_fraction(mapping.get("Precipitation"))
    if precip is not None:
        fields["precipitation"] = "live"

    wetness = as_int(mapping.get("TrackWetness"))
    declared = (
        _optional_bool(mapping.get("WeatherDeclaredWet"))
        if "WeatherDeclaredWet" in mapping
        else None
    )

    source = _aggregate_source(fields, default="live")
    return WeatherSnapshot(
        skies=skies,
        air_temp_c=air,
        track_temp_c=track,
        wind_speed_mps=wind,
        precipitation=precip,
        track_wetness=wetness,
        weather_declared_wet=declared,
        source=source,
        field_sources=fields,
    )


def _pick_skies(
    mapping: Mapping[str, Any],
    weekend: Mapping[str, Any],
) -> tuple[str | None, WeatherSource | None]:
    live = _normalize_skies(mapping.get("Skies"))
    if live is not None:
        return live, "live"
    session = _normalize_skies(weekend.get("TrackSkies"))
    if session is not None:
        return session, "session"
    return None, None


def _pick_temp(
    *,
    live_keys: tuple[str, ...],
    session_value: object,
    mapping: Mapping[str, Any],
) -> tuple[float | None, WeatherSource | None]:
    for key in live_keys:
        if key not in mapping:
            continue
        value = _parse_temp_c(mapping.get(key))
        if value is not None:
            return value, "live"
    session = _parse_temp_c(session_value)
    if session is not None:
        return session, "session"
    return None, None


def _pick_wind(
    mapping: Mapping[str, Any],
    weekend: Mapping[str, Any],
) -> tuple[float | None, WeatherSource | None]:
    if "WindVel" in mapping:
        live = _parse_wind_mps(mapping.get("WindVel"), default_unit="m/s")
        if live is not None:
            return live, "live"
    session = _parse_wind_mps(weekend.get("TrackWindVel"), default_unit="m/s")
    if session is not None:
        return session, "session"
    return None, None


def _aggregate_source(
    fields: Mapping[str, WeatherSource],
    *,
    default: WeatherSource,
) -> WeatherSource:
    if not fields:
        return default
    distinct = set(fields.values())
    if len(distinct) == 1:
        return next(iter(distinct))
    return "mixed"


# --- parsers / normalizers ---------------------------------------------------


def _normalize_skies(value: object) -> str | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)):
            return None
        key = _SKIES_BY_INT.get(int(value))
        return key
    text = str(value).strip().lower()
    text = re.sub(r"\s+", " ", text)
    if text in _SKIES_ALIASES:
        return _SKIES_ALIASES[text]
    compact = text.replace(" ", "").replace("-", "")
    if compact in _SKIES_ALIASES:
        return _SKIES_ALIASES[compact]
    # "Partly Cloudy / Dynamic" style — take left token group
    head = text.split("/")[0].strip()
    if head in _SKIES_ALIASES:
        return _SKIES_ALIASES[head]
    return None


def _parse_temp_c(value: object) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number):
            return None
        # Sanity: telemetry temps are Celsius in modern SDK.
        if number < -80 or number > 120:
            return None
        return number
    match = _TEMP_RE.match(str(value).strip())
    if not match:
        return None
    number = float(match.group(1))
    unit = (match.group(2) or "C").upper()
    if unit == "F":
        number = (number - 32.0) * 5.0 / 9.0
    if not math.isfinite(number) or number < -80 or number > 120:
        return None
    return number


def _parse_wind_mps(value: object, *, default_unit: str) -> float | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        if not math.isfinite(number) or number < 0:
            return None
        return _to_mps(number, default_unit)
    match = _WIND_RE.match(str(value).strip())
    if not match:
        return None
    number = float(match.group(1))
    if not math.isfinite(number) or number < 0:
        return None
    unit = (match.group(2) or default_unit).lower().replace("/", "")
    return _to_mps(number, unit)


def _to_mps(number: float, unit: str) -> float:
    normalized = unit.lower().replace("/", "").replace(" ", "")
    if normalized in {"kmh", "kph"} or "km" in normalized:
        return number * _KMH_TO_MPS
    if normalized == "mph":
        return number * _MPH_TO_MPS
    # m/s (live WindVel / TrackWindVel) and unknown → treat as m/s
    return number


def _precip_fraction(value: object) -> float | None:
    """Normalize Precipitation to 0..1. Accepts 0..1 or 0..100 (%) scales."""
    number = _as_finite_float(value)
    if number is None or number < 0:
        return None
    if number > 1.0:
        # Percent scale
        if number > 100.0:
            return None
        return number / 100.0
    return number


def _precip_vocab_key(
    intensity: float | None,
    *,
    wetness: int | None,
    declared: bool | None,
) -> str | None:
    raining = intensity is not None and intensity > 0.005
    if raining and intensity is not None:
        if intensity < 0.15:
            return "light"
        if intensity < 0.45:
            return "moderate"
        return "heavy"

    wet_surface = (wetness is not None and wetness >= _WETNESS_LIGHTLY_WET) or (declared is True)
    if wet_surface:
        return "wet_track"

    if intensity is not None and intensity <= 0.005:
        return "none"

    # Declared/wetness unknown and no precip sample → nothing to say
    if intensity is None and wetness is None and declared is None:
        return None
    if intensity is None and wetness is not None and wetness <= 1:
        return "none"
    if intensity is None and declared is False and (wetness is None or wetness <= 1):
        return "none"
    return None


def _format_temp_c(celsius: object) -> str | None:
    number = _parse_temp_c(celsius)
    if number is None:
        return None
    return f"{int(round(number))} C"


def _as_finite_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    try:
        number = float(str(value).strip())
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _optional_bool(value: object) -> bool | None:
    if value is None:
        return None
    return as_bool(value)


def _as_mapping(value: object) -> Mapping[str, Any] | None:
    if value is None:
        return None
    if isinstance(value, Mapping):
        return value
    raw = getattr(value, "__dict__", None)
    if isinstance(raw, Mapping):
        return raw
    return None
