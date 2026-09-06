"""Operator diagnostic voice: catalog, debounce, default device, fail-soft."""

from __future__ import annotations

from typing import Any

from irswitch.overlay.settings import CommentarySettings
from irswitch.util.diagnostic_voice import (
    PHRASES,
    DiagnosticVoice,
    DiagnosticVoiceSettings,
)


def test_catalog_has_required_operator_phrases() -> None:
    assert PHRASES["iracing_connected"] == "Simulator running."
    assert PHRASES["iracing_disconnected"] == "iRacing disconnected."
    assert PHRASES["stream_started"] == "We are live."
    assert PHRASES["stream_stopped"] == "Stream stopped."
    assert PHRASES["switcher_fatal"] == "Fatal error. Switcher not working."


def test_disabled_voice_does_not_speak() -> None:
    spoken: list[dict[str, Any]] = []

    def speak(text: str, **kwargs: Any) -> None:
        spoken.append({"text": text, **kwargs})

    voice = DiagnosticVoice(
        DiagnosticVoiceSettings(voice=False),
        speak=speak,
        system="Windows",
        clock=lambda: 10.0,
    )
    voice.announce("iracing_connected")
    assert spoken == []


def test_repeat_connect_is_cooled_down() -> None:
    spoken: list[str] = []
    now = 0.0

    def speak(text: str, **_kwargs: Any) -> None:
        spoken.append(text)

    voice = DiagnosticVoice(
        DiagnosticVoiceSettings(voice=True, cooldown_s=4.0),
        speak=speak,
        system="Windows",
        clock=lambda: now,
    )
    voice.announce("iracing_connected", now=0.0)
    voice.announce("iracing_connected", now=1.0)
    voice.close()
    assert spoken == ["Simulator running."]


def test_speak_uses_sapi_default_device_not_commentary_cable() -> None:
    seen: list[dict[str, Any]] = []
    commentary = CommentarySettings(enabled=False, audio_device="CABLE Input")

    def speak(text: str, **kwargs: Any) -> None:
        seen.append({"text": text, **kwargs})

    voice = DiagnosticVoice(
        DiagnosticVoiceSettings(voice=True),
        speak=speak,
        system="Windows",
        clock=lambda: 1.0,
    )
    voice.announce("switcher_fatal")
    voice.close()
    assert seen == [
        {
            "text": "Fatal error. Switcher not working.",
            "locale": "en",
            "voice": "",
            "backend": "sapi",
            "device": "",
            "timeout_s": 3.0,
        }
    ]
    assert commentary.audio_device not in {row["device"] for row in seen}
    assert commentary.enabled is False


def test_speak_exception_is_fail_soft() -> None:
    def speak(_text: str, **_kwargs: Any) -> None:
        raise RuntimeError("sapi missing")

    voice = DiagnosticVoice(
        DiagnosticVoiceSettings(voice=True),
        speak=speak,
        system="Windows",
        clock=lambda: 1.0,
    )
    voice.announce("stream_started")
    voice.close()


def test_non_windows_is_noop() -> None:
    spoken: list[str] = []
    voice = DiagnosticVoice(
        DiagnosticVoiceSettings(voice=True),
        speak=lambda text, **_k: spoken.append(text),
        system="Linux",
        clock=lambda: 1.0,
    )
    voice.announce("iracing_connected")
    voice.close()
    assert spoken == []
