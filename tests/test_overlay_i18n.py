"""Overlay copy catalogs and token resolution."""

import pytest

from irswitch.overlay import i18n
from irswitch.overlay.i18n import (
    CS,
    EN,
    SUPPORTED_LANGUAGES,
    catalog_for,
    normalize_language,
    resolve_copy,
)

MVP_TOKENS = (
    "battle.hunting",
    "battle.hunted",
    "battle.closing_in",
    "battle.approach",
    "battle.attack_range",
    "battle.side_by_side",
    "lap.complete",
    "lap.personal_best",
    "position.gained",
    "position.lost",
    "position.overtake",
    "session.final_lap",
    "session.finish",
    "incident",
    "pit.entry",
    "pit.lane",
    "pit.stopped",
    "pit.released",
    "pit.exit",
    "pit.outcome",
    "bio.hr_high",
    "bio.hr_pressure",
    "ble.lost",
)


def test_en_catalog_covers_mvp_tokens() -> None:
    assert set(MVP_TOKENS) <= set(EN)
    assert all(EN[token] for token in MVP_TOKENS)


def test_cs_catalog_covers_en_keys_without_extras() -> None:
    assert set(CS) == set(EN)
    assert all(CS[token] for token in CS)


def test_supported_languages() -> None:
    assert SUPPORTED_LANGUAGES == ("en", "cs")


def test_resolve_copy_en_and_cs() -> None:
    assert resolve_copy("lap.personal_best", "en") == "PERSONAL BEST"
    assert resolve_copy("lap.personal_best", "cs") == "OSOBNÍ REKORD"
    assert resolve_copy("lap.personal_best") == EN["lap.personal_best"]


def test_resolve_copy_falls_back_to_english_for_unknown_language() -> None:
    assert resolve_copy("session.finish", "de") == EN["session.finish"]
    assert resolve_copy("session.finish", "") == EN["session.finish"]


def test_resolve_copy_unknown_token_is_empty() -> None:
    """Missing keys must not leak dotted tokens onto the HUD."""
    assert resolve_copy("nope.not_a_token", "cs") == ""
    assert resolve_copy("nope.not_a_token", "en") == ""


def test_resolve_copy_falls_back_to_english_for_partial_locale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A locale missing a key resolves through English, not to the raw token."""
    partial = {k: v for k, v in CS.items() if k != "incident"}
    monkeypatch.setattr(i18n, "CATALOGS", {"en": EN, "cs": partial})
    assert i18n.resolve_copy("incident", "cs") == EN["incident"]


def test_normalize_and_catalog_lookup() -> None:
    assert normalize_language("CS") == "cs"
    assert normalize_language("  En ") == "en"
    assert normalize_language(None) == "en"
    assert normalize_language("klingon") == "en"
    assert catalog_for("cs") is CS
    assert catalog_for("klingon") is EN
