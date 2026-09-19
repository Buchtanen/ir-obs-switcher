"""Mix featured driver name into he/him/his commentary lines."""

from __future__ import annotations

import random

from irswitch.commentary.speech_hero import mix_hero_name, resolve_hero_names


def test_english_replaces_first_he_and_keeps_later_pronoun() -> None:
    rng = random.Random(0)
    text = mix_hero_name(
        "He closes the gap and he stays on it.",
        ("Richard",),
        "en",
        rng=rng,
    )
    assert text.startswith("Richard closes")
    assert " he stays " in text


def test_english_his_becomes_possessive() -> None:
    text = mix_hero_name("His heart rate is climbing.", ("Richard",), "en")
    assert text == "Richard's heart rate is climbing."


def test_english_hes_becomes_name_is() -> None:
    text = mix_hero_name("He's closing on Rossi.", ("Richard",), "en")
    assert text == "Richard is closing on Rossi."


def test_english_him() -> None:
    text = mix_hero_name("That's a lap for him.", ("Buchtanen",), "en")
    assert text == "That's a lap for Buchtanen."


def test_skips_when_name_already_present() -> None:
    src = "Richard closes the gap."
    assert mix_hero_name(src, ("Richard", "Buchtanen"), "en") == src


def test_picks_nickname_from_pool() -> None:
    rng = random.Random(1)
    text = mix_hero_name("He banks the lap.", ("Richard", "Buchtanen"), "en", rng=rng)
    assert text.startswith("Richard ") or text.startswith("Buchtanen ")
    assert "He " not in text


def test_english_does_not_prefix_vocative_when_no_pronoun() -> None:
    src = "That's a best lap without fuss."
    text = mix_hero_name(src, ("Richard",), "en")
    assert text == src
    assert not text.startswith("Richard.")
    assert not text.startswith("Richard,")


def test_english_skips_when_another_person_is_named() -> None:
    assert mix_hero_name("Ohanian is closing.", ("Richard",), "en") == "Ohanian is closing."
    assert mix_hero_name("West is coming back.", ("Richard",), "en") == "West is coming back."


def test_czech_on_replace_without_vocative_prefix() -> None:
    assert mix_hero_name("On uzavírá kolo.", ("Richard",), "cs") == "Richard uzavírá kolo."
    src = "Kolo je hotové."
    assert mix_hero_name(src, ("Richard",), "cs") == src


def test_resolve_config_beats_iracing() -> None:
    names = resolve_hero_names(
        driver_name="Richard",
        driver_nickname="Buchtanen",
        iracing_names=("Bušek",),
    )
    assert names == ("Richard", "Buchtanen")


def test_resolve_falls_back_to_iracing() -> None:
    names = resolve_hero_names(
        driver_name="",
        driver_nickname=None,
        iracing_names=("Richard", "Bušek"),
    )
    assert names == ("Richard", "Bušek")
