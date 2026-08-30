"""Weather extraction + spoken formatters (commentary H3)."""

from __future__ import annotations

from irswitch.iracing.weather import (
    WeatherSnapshot,
    compose_weather_brief,
    extract_weather,
    format_air_temp,
    format_precipitation,
    format_skies,
    format_track_temp,
    format_wind_speed,
    spoken_weather_bindings,
)


def test_skies_enum_localization_en_cs() -> None:
    assert format_skies(0, "en") == "clear"
    assert format_skies(1, "en") == "partly cloudy"
    assert format_skies(2, "en") == "mostly cloudy"
    assert format_skies(3, "en") == "overcast"
    assert format_skies(1, "cs") == "polojasno"
    assert format_skies(3, "cs") == "zataženo"
    assert format_skies("Partly Cloudy", "en") == "partly cloudy"
    assert format_skies("Clear", "cs") == "jasno"
    assert format_skies(None) is None
    assert format_skies("") is None
    assert format_skies(99) is None


def test_temp_and_wind_formatters() -> None:
    assert format_air_temp(23.4) == "23 C"
    assert format_air_temp("22.00 C") == "22 C"
    assert format_track_temp(31.2) == "31 C"
    assert format_air_temp(None) is None
    assert format_wind_speed(4.2) == "4 m/s"
    assert format_wind_speed(0) == "0 m/s"
    assert format_wind_speed(-1) is None
    assert format_wind_speed(None) is None


def test_precipitation_vocab_and_wet_without_rain() -> None:
    assert format_precipitation(0.0) == "dry"
    assert format_precipitation(0.08, locale="en") == "light rain"
    assert format_precipitation(0.3, locale="en") == "rain"
    assert format_precipitation(0.6, locale="cs") == "silný déšť"
    # Percent scale
    assert format_precipitation(10) == "light rain"
    # Wet track, no rain — never invent rain from skies
    assert (
        format_precipitation(
            0.0,
            track_wetness=5,
            weather_declared_wet=False,
            locale="en",
        )
        == "wet track"
    )
    assert (
        format_precipitation(
            None,
            track_wetness=None,
            weather_declared_wet=True,
            locale="cs",
        )
        == "mokrý povrch"
    )
    assert format_precipitation(None) is None
    # Skies alone must not produce precipitation
    snap = extract_weather({"Skies": 3})
    assert snap.precipitation is None
    assert spoken_weather_bindings(snap)["precipitation"] is None


def test_extract_live_prefers_telemetry() -> None:
    data = {
        "Skies": 1,
        "AirTemp": 23.0,
        "TrackTempCrew": 31.5,
        "WindVel": 4.0,
        "Precipitation": 0.0,
        "TrackWetness": 1,
        "WeatherDeclaredWet": 0,
        "WeekendInfo": {
            "TrackSkies": "Overcast",
            "TrackAirTemp": "10.00 C",
            "TrackSurfaceTemp": "12.00 C",
            "TrackWindVel": "1.00 m/s",
            "WeekendOptions": {
                "Skies": "Clear",
                "WeatherTemp": "5.00 C",
                "WindSpeed": "36.00 km/h",
            },
        },
    }
    snap = extract_weather(data, prefer="live")
    assert snap.source == "live"
    assert snap.skies == "partly cloudy"
    assert snap.air_temp_c == 23.0
    assert snap.track_temp_c == 31.5
    assert snap.wind_speed_mps == 4.0
    assert snap.precipitation == 0.0
    assert snap.field_sources["skies"] == "live"
    # Forecast must not leak into live preference
    assert snap.air_temp_c != 5.0
    assert abs(snap.wind_speed_mps - 10.0) > 0.1


def test_extract_live_falls_back_to_session_not_forecast() -> None:
    data = {
        "WeekendInfo": {
            "TrackSkies": "Mostly Cloudy",
            "TrackAirTemp": "18.50 C",
            "TrackSurfaceTemp": "22.00 C",
            "TrackWindVel": "2.50 m/s",
            "WeekendOptions": {
                "Skies": "Clear",
                "WeatherTemp": "99.00 C",
                "WindSpeed": "100.00 km/h",
            },
        }
    }
    snap = extract_weather(data, prefer="live")
    assert snap.source == "session"
    assert snap.skies == "mostly cloudy"
    assert snap.air_temp_c == 18.5
    assert snap.track_temp_c == 22.0
    assert snap.wind_speed_mps == 2.5
    assert snap.field_sources["air_temp"] == "session"
    # Forecast values must not be used as silent fallback
    assert snap.air_temp_c != 99.0


def test_extract_forecast_never_mixes_live() -> None:
    data = {
        "Skies": 3,
        "AirTemp": 30.0,
        "WindVel": 1.0,
        "Precipitation": 0.5,
        "WeekendInfo": {
            "TrackSkies": "Overcast",
            "TrackAirTemp": "28.00 C",
            "WeekendOptions": {
                "Skies": "Partly Cloudy",
                "WeatherTemp": "20.00 C",
                "WindSpeed": "18.00 km/h",
            },
        },
    }
    snap = extract_weather(data, prefer="forecast")
    assert snap.source == "forecast"
    assert snap.skies == "partly cloudy"
    assert snap.air_temp_c == 20.0
    # WindSpeed km/h → m/s
    assert snap.wind_speed_mps is not None
    assert abs(snap.wind_speed_mps - 5.0) < 0.05
    assert snap.track_temp_c is None
    assert snap.precipitation is None
    assert all(src == "forecast" for src in snap.field_sources.values())


def test_forecast_vs_live_not_silently_swapped() -> None:
    data = {
        "Skies": 0,
        "AirTemp": 25.0,
        "WindVel": 3.0,
        "WeekendInfo": {
            "WeekendOptions": {
                "Skies": "Overcast",
                "WeatherTemp": "12.00 C",
                "WindSpeed": "7.20 km/h",
            }
        },
    }
    live = extract_weather(data, prefer="live")
    forecast = extract_weather(data, prefer="forecast")
    assert live.skies == "clear"
    assert forecast.skies == "overcast"
    assert live.air_temp_c == 25.0
    assert forecast.air_temp_c == 12.0
    assert live.source == "live"
    assert forecast.source == "forecast"
    assert live.skies != forecast.skies


def test_mixed_source_when_live_and_session_combine() -> None:
    data = {
        "AirTemp": 21.0,
        "WeekendInfo": {
            "TrackSkies": "Clear",
            "TrackSurfaceTemp": "27.00 C",
            "TrackWindVel": "3.00 m/s",
        },
    }
    snap = extract_weather(data, prefer="live")
    assert snap.source == "mixed"
    assert snap.field_sources["air_temp"] == "live"
    assert snap.field_sources["skies"] == "session"
    assert snap.field_sources["track_temp"] == "session"


def test_missing_values_fail_soft() -> None:
    assert extract_weather(None).skies is None
    assert extract_weather("bogus").air_temp_c is None
    empty = extract_weather({})
    assert empty.skies is None
    assert empty.air_temp_c is None
    assert empty.track_temp_c is None
    assert empty.wind_speed_mps is None
    assert empty.precipitation is None
    bindings = spoken_weather_bindings(empty)
    assert bindings == {
        "skies": None,
        "air_temp": None,
        "track_temp": None,
        "wind_speed": None,
        "precipitation": None,
    }


def test_track_temp_prefers_crew_then_track_then_surface() -> None:
    assert (
        extract_weather(
            {"TrackTempCrew": 33.0, "TrackTemp": 30.0},
            prefer="live",
        ).track_temp_c
        == 33.0
    )
    assert extract_weather({"TrackTemp": 30.0}, prefer="live").track_temp_c == 30.0
    assert (
        extract_weather(
            {"WeekendInfo": {"TrackSurfaceTemp": "29.00 C"}},
            prefer="live",
        ).track_temp_c
        == 29.0
    )


def test_spoken_bindings_en_cs_and_composed_under_90() -> None:
    snap = WeatherSnapshot(
        skies="partly cloudy",
        air_temp_c=23.0,
        track_temp_c=31.0,
        wind_speed_mps=4.0,
        precipitation=0.1,
        source="live",
        field_sources={"skies": "live"},
    )
    en = spoken_weather_bindings(snap, "en")
    cs = spoken_weather_bindings(snap, "cs")
    assert en["skies"] == "partly cloudy"
    assert en["air_temp"] == "23 C"
    assert en["wind_speed"] == "4 m/s"
    assert en["precipitation"] == "light rain"
    assert cs["skies"] == "polojasno"
    assert cs["precipitation"] == "slabý déšť"
    en_brief = compose_weather_brief(snap, "en")
    cs_brief = compose_weather_brief(snap, "cs")
    assert en_brief is not None and len(en_brief) <= 90
    assert cs_brief is not None and len(cs_brief) <= 90


def test_prefer_session_ignores_live_and_forecast() -> None:
    data = {
        "Skies": 0,
        "AirTemp": 40.0,
        "WeekendInfo": {
            "TrackSkies": "Overcast",
            "TrackAirTemp": "16.00 C",
            "TrackWindVel": "1.00 m/s",
            "WeekendOptions": {"WeatherTemp": "1.00 C", "Skies": "Clear"},
        },
    }
    snap = extract_weather(data, prefer="session")
    assert snap.source == "session"
    assert snap.skies == "overcast"
    assert snap.air_temp_c == 16.0
    assert snap.precipitation is None
