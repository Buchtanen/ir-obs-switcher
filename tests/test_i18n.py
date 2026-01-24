"""Tests for internationalization (i18n) support."""
from __future__ import annotations

import pytest

from irswitch.i18n import (
    DEFAULT_LANGUAGE,
    SUPPORTED_LANGUAGES,
    Translator,
    get_translator,
    set_language,
    t,
)


class TestTranslator:
    """Test Translator class."""

    def test_init_with_valid_language(self) -> None:
        """Test Translator initialization with valid language."""
        translator = Translator("EN")
        assert translator.language == "EN"
        assert translator.translations is not None

    def test_init_with_invalid_language_fallback(self) -> None:
        """Test Translator initialization with invalid language falls back to default."""
        translator = Translator("INVALID")
        assert translator.language == DEFAULT_LANGUAGE
        assert translator.translations is not None

    def test_init_case_insensitive(self) -> None:
        """Test Translator initialization is case-insensitive."""
        translator1 = Translator("en")
        translator2 = Translator("EN")
        translator3 = Translator("En")
        
        assert translator1.language == "EN"
        assert translator2.language == "EN"
        assert translator3.language == "EN"

    def test_translate_existing_key(self) -> None:
        """Test translating an existing key."""
        translator = Translator("EN")
        result = translator.translate("connected")
        assert result == "Connected"

    def test_translate_missing_key_returns_key(self) -> None:
        """Test translating a missing key returns the key itself."""
        translator = Translator("EN")
        result = translator.translate("nonexistent_key")
        assert result == "nonexistent_key"

    def test_translate_with_parameters(self) -> None:
        """Test translating with format parameters."""
        translator = Translator("CS")
        result = translator.translate("youtube_quota_message", time="08:00")
        assert "08:00" in result
        assert "{time}" not in result

    def test_translate_with_invalid_parameters(self) -> None:
        """Test translating with invalid parameters returns translation without formatting."""
        translator = Translator("CS")
        result = translator.translate("connected", invalid_param="value")
        # Should return translation without formatting if format fails
        assert result == "Připojeno"

    def test_t_alias(self) -> None:
        """Test that t() is an alias for translate()."""
        translator = Translator("EN")
        result1 = translator.translate("connected")
        result2 = translator.t("connected")
        assert result1 == result2

    def test_all_supported_languages_have_translations(self) -> None:
        """Test that all supported languages have all required keys."""
        # Get keys from default language
        default_translator = Translator(DEFAULT_LANGUAGE)
        required_keys = set(default_translator.translations.keys())
        
        for lang in SUPPORTED_LANGUAGES:
            translator = Translator(lang)
            lang_keys = set(translator.translations.keys())
            # All languages should have the same keys
            assert lang_keys == required_keys, f"Language {lang} is missing keys: {required_keys - lang_keys}"

    def test_all_languages_have_common_keys(self) -> None:
        """Test that all languages have common essential keys."""
        essential_keys = [
            "connected",
            "disconnected",
            "iracing_connection",
            "obs_connection",
            "stream_title",
            "stream_description",
        ]
        
        for lang in SUPPORTED_LANGUAGES:
            translator = Translator(lang)
            for key in essential_keys:
                assert key in translator.translations, f"Language {lang} missing key: {key}"


class TestGlobalFunctions:
    """Test global i18n functions."""

    def test_set_language(self) -> None:
        """Test setting global language."""
        set_language("EN")
        translator = get_translator()
        assert translator.language == "EN"

    def test_set_language_invalid_fallback(self) -> None:
        """Test setting invalid language falls back to default."""
        set_language("INVALID")
        translator = get_translator()
        assert translator.language == DEFAULT_LANGUAGE

    def test_set_language_case_insensitive(self) -> None:
        """Test set_language is case-insensitive."""
        set_language("en")
        translator = get_translator()
        assert translator.language == "EN"

    def test_get_translator_returns_singleton(self) -> None:
        """Test that get_translator returns the same instance."""
        set_language("EN")
        translator1 = get_translator()
        translator2 = get_translator()
        assert translator1 is translator2

    def test_get_translator_creates_default_if_none(self) -> None:
        """Test that get_translator creates default translator if none exists."""
        # Reset global translator
        set_language("INVALID")  # This will create a translator
        translator = get_translator()
        assert translator is not None
        assert translator.language == DEFAULT_LANGUAGE

    def test_t_function(self) -> None:
        """Test global t() function."""
        set_language("EN")
        result = t("connected")
        assert result == "Connected"

    def test_t_function_with_parameters(self) -> None:
        """Test global t() function with parameters."""
        set_language("CS")
        result = t("youtube_quota_message", time="08:00")
        assert "08:00" in result

    def test_t_function_uses_current_language(self) -> None:
        """Test that t() function uses currently set language."""
        set_language("EN")
        result_en = t("connected")
        assert result_en == "Connected"
        
        set_language("DE")
        result_de = t("connected")
        assert result_de == "Verbunden"
        assert result_en != result_de


class TestLanguageSupport:
    """Test support for all languages."""

    @pytest.mark.parametrize("lang_code", SUPPORTED_LANGUAGES)
    def test_language_supported(self, lang_code: str) -> None:
        """Test that each supported language works."""
        translator = Translator(lang_code)
        assert translator.language == lang_code
        
        # Test a common key exists
        result = translator.translate("connected")
        assert result is not None
        assert result != "connected"  # Should be translated, not the key

    def test_czech_default(self) -> None:
        """Test that Czech is the default language."""
        translator = Translator("INVALID")
        assert translator.language == DEFAULT_LANGUAGE
        assert DEFAULT_LANGUAGE == "CS"

    def test_all_languages_have_youtube_messages(self) -> None:
        """Test that all languages have YouTube API messages."""
        youtube_keys = [
            "youtube_api_quota_exceeded",
            "youtube_api_key_not_configured",
            "youtube_quota_message",
            "youtube_key_message",
        ]
        
        for lang in SUPPORTED_LANGUAGES:
            translator = Translator(lang)
            for key in youtube_keys:
                assert key in translator.translations, f"Language {lang} missing YouTube key: {key}"

    def test_all_languages_have_event_types(self) -> None:
        """Test that all languages have event type translations."""
        event_keys = [
            "application_started",
            "connection_lost",
            "connection_restored",
            "scene_switched",
            "stream_started",
            "stream_stopped",
        ]
        
        for lang in SUPPORTED_LANGUAGES:
            translator = Translator(lang)
            for key in event_keys:
                assert key in translator.translations, f"Language {lang} missing event key: {key}"


class TestParameterFormatting:
    """Test parameter formatting in translations."""

    def test_youtube_quota_message_formatting(self) -> None:
        """Test YouTube quota message formatting."""
        translator = Translator("CS")
        result = translator.translate("youtube_quota_message", time="08:00")
        assert "08:00" in result
        assert "{time}" not in result

    def test_youtube_quota_message_all_languages(self) -> None:
        """Test YouTube quota message formatting in all languages."""
        for lang in SUPPORTED_LANGUAGES:
            translator = Translator(lang)
            result = translator.translate("youtube_quota_message", time="08:00")
            assert "08:00" in result, f"Language {lang} did not format time parameter"
            assert "{time}" not in result, f"Language {lang} did not replace {{time}} placeholder"

    def test_formatting_with_multiple_parameters(self) -> None:
        """Test formatting with multiple parameters (if any exist)."""
        translator = Translator("EN")
        # Test with a key that might have multiple parameters
        # Most keys have single or no parameters, so we test with youtube_quota_message
        result = translator.translate("youtube_quota_message", time="08:00")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_formatting_with_missing_parameter(self) -> None:
        """Test formatting when a required parameter is missing."""
        translator = Translator("CS")
        # Should return translation without formatting if parameter is missing
        result = translator.translate("youtube_quota_message")
        # Should still return a string (might contain {time} placeholder or be formatted differently)
        assert isinstance(result, str)
