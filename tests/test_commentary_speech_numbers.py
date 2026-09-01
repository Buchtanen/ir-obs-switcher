"""numbers_to_words for commentary LLM/TTS path."""

from __future__ import annotations

from irswitch.commentary.speech_numbers import numbers_to_words


def test_english_position_and_gap() -> None:
    text = numbers_to_words("He closes to 0.38 s from P5.", "en")
    assert "zero point three eight" in text
    assert "seconds" in text
    assert "P five" in text
    assert "0.38" not in text
    assert "P5" not in text
    assert " eight s " not in f" {text} "


def test_english_lap_time() -> None:
    text = numbers_to_words("Personal best 1:52.084 on lap 12.", "en")
    assert "one minute fifty-two point zero eight four" in text
    assert "twelve" in text
    assert "1:52" not in text


def test_czech_position_and_gap() -> None:
    text = numbers_to_words("Dotahuje na 0.38 s z P5.", "cs")
    assert "nula tečka tři osm" in text
    assert "sekund" in text
    assert "P pět" in text


def test_czech_lap_time() -> None:
    text = numbers_to_words("Nový čas 1:52.084.", "cs")
    assert "jedna minuta" in text
    assert "padesát dva" in text
    assert "tečka nula osm čtyři" in text


def test_sector_marker() -> None:
    assert "S one" in numbers_to_words("Gain at S1.", "en")
    assert "S dva" in numbers_to_words("Zisk na S2.", "cs")
    text = numbers_to_words("Gain at S1.", "en")
    assert "seconds" not in text


def test_signed_delta() -> None:
    assert "plus zero point three" in numbers_to_words("Delta +0.318.", "en")
    assert "minus zero point four" in numbers_to_words("Delta -0.418.", "en")


def test_noop_without_digits() -> None:
    assert numbers_to_words("Clean air ahead.", "en") == "Clean air ahead."


def test_english_wind_and_temp_units() -> None:
    wind = numbers_to_words("Wind at 5 m/s.", "en")
    assert "five" in wind
    assert "meters per second" in wind
    assert "m/s" not in wind

    temp = numbers_to_words("Air temperature is 23 C.", "en")
    assert "twenty-three" in temp
    assert "degrees Celsius" in temp
    assert "degrees Celsius" in temp
    assert " C." not in temp

    deg = numbers_to_words("Track at 31°C.", "en")
    assert "degrees Celsius" in deg
    assert "°" not in deg

    leftover = numbers_to_words("Wind at five m/s, pushing slightly.", "en")
    assert leftover == "Wind at five meters per second, pushing slightly."


def test_english_normalizes_degrees_of_celsius() -> None:
    text = numbers_to_words("Air at twenty-three degrees of Celsius.", "en")
    assert "degrees of Celsius" not in text.lower()
    assert "degrees Celsius" in text


def test_english_kmh_percent_bpm() -> None:
    speed = numbers_to_words("Wind 12 km/h.", "en")
    assert "twelve" in speed
    assert "kilometers per hour" in speed
    assert "km/h" not in speed

    pct = numbers_to_words("Wetness 10%.", "en")
    assert "ten" in pct
    assert "percent" in pct
    assert "%" not in pct

    hr = numbers_to_words("Heart rate 94 bpm.", "en")
    assert "ninety-four" in hr
    assert "beats per minute" in hr
    assert "bpm" not in hr.lower()


def test_czech_wind_and_temp_units() -> None:
    wind = numbers_to_words("Vítr 5 m/s.", "cs")
    assert "pět" in wind
    assert "metrů za sekundu" in wind
    assert "m/s" not in wind

    temp = numbers_to_words("Vzduch má 23 C.", "cs")
    assert "stupňů Celsia" in temp
    assert "  C" not in temp

    awkward = numbers_to_words("Vzduch má dvacet tři degrees of Celsius.", "cs")
    assert "degrees of Celsius" not in awkward.lower()
    assert "stupňů Celsia" in awkward


def test_prose_is_not_seconds() -> None:
    text = numbers_to_words("This is the clear picture.", "en")
    assert text == "This is the clear picture."
    assert "seconds" not in text
