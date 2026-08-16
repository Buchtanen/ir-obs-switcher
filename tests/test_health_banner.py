"""Tests for GR health banner mapping."""

from __future__ import annotations

from irswitch.i18n import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES, Translator
from irswitch.server.health_banner import resolve_health_banner


def test_hidden_when_both_connected() -> None:
    assert resolve_health_banner(True, True) is None


def test_degraded_iracing_only() -> None:
    view = resolve_health_banner(False, True)
    assert view is not None
    assert view.severity == "degraded"
    assert view.title_key == "health_banner_title_degraded"
    assert view.tip_keys == ("health_banner_tip_iracing",)


def test_degraded_obs_only() -> None:
    view = resolve_health_banner(True, False)
    assert view is not None
    assert view.severity == "degraded"
    assert view.title_key == "health_banner_title_degraded"
    assert view.tip_keys == ("health_banner_tip_obs",)


def test_unhealthy_both_offline() -> None:
    view = resolve_health_banner(False, False)
    assert view is not None
    assert view.severity == "unhealthy"
    assert view.title_key == "health_banner_title_unhealthy"
    assert view.tip_keys == ("health_banner_tip_iracing", "health_banner_tip_obs")


def test_banner_keys_exist_in_all_languages() -> None:
    keys = {
        "health_banner_title_degraded",
        "health_banner_title_unhealthy",
        "health_banner_tip_iracing",
        "health_banner_tip_obs",
    }
    for lang in SUPPORTED_LANGUAGES:
        translator = Translator(lang)
        for key in keys:
            text = translator.t(key)
            assert text != key, f"missing {key} in {lang}"
            assert text.strip(), f"empty {key} in {lang}"

    # Smoke: CS/EN are actionable (mention product / config)
    cs = Translator("CS")
    en = Translator("EN")
    assert "iRacing" in cs.t("health_banner_tip_iracing")
    assert "OBS" in cs.t("health_banner_tip_obs")
    assert "config" in en.t("health_banner_tip_obs").lower()
    assert Translator(DEFAULT_LANGUAGE).t("health_banner_title_unhealthy")
