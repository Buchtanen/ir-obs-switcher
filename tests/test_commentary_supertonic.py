"""SuperTonic CPU backend helpers (no real ONNX / audio)."""

from __future__ import annotations

from typing import Any

from irswitch.commentary.supertonic_backend import (
    pick_output_device,
    rate_to_speed,
    resolve_voice,
)
from irswitch.commentary.tts import detect_backend, speak_text
from irswitch.config import AppConfig
from irswitch.overlay.schema import overlay_values


def test_resolve_voice_falls_back_from_sapi_name() -> None:
    assert resolve_voice("M2") == "M2"
    assert resolve_voice("f5") == "F5"
    assert resolve_voice("Microsoft David Desktop - English (United States)") == "M1"
    assert resolve_voice("") == "M1"


def test_rate_to_speed_maps_sapi_range() -> None:
    assert rate_to_speed(0) == 1.05
    assert rate_to_speed(-10) == 0.7
    assert abs(rate_to_speed(10) - 1.4) < 1e-9


def test_pick_output_prefers_wasapi_stereo() -> None:
    devices = [
        {
            "name": "CABLE In 16ch (VB-Audio Virtual Cable)",
            "max_output_channels": 16,
            "hostapi_name": "MME",
        },
        {
            "name": "CABLE Input (VB-Audio Virtual Cable)",
            "max_output_channels": 16,
            "hostapi_name": "MME",
        },
        {
            "name": "CABLE Input (VB-Audio Virtual Cable)",
            "max_output_channels": 2,
            "hostapi_name": "Windows WDM-KS",
            "default_samplerate": 44100.0,
        },
        {
            "name": "CABLE Input (VB-Audio Virtual Cable)",
            "max_output_channels": 2,
            "hostapi_name": "Windows WASAPI",
            "default_samplerate": 48000.0,
        },
        {
            "name": "CABLE Input (VB-Audio Virtual Cable)",
            "max_output_channels": 2,
            "hostapi_name": "Windows WASAPI",
            "default_samplerate": 44100.0,
        },
    ]
    assert pick_output_device(devices, "CABLE Input") == 4
    assert pick_output_device(devices, "") is None


def test_pick_output_skips_wdmks() -> None:
    devices = [
        {
            "name": "CABLE Input (VB-Audio Virtual Cable)",
            "max_output_channels": 2,
            "hostapi_name": "Windows WDM-KS",
            "default_samplerate": 44100.0,
        },
        {
            "name": "CABLE Input (VB-Audio Virtual Cable)",
            "max_output_channels": 16,
            "hostapi_name": "MME",
            "default_samplerate": 44100.0,
        },
    ]
    assert pick_output_device(devices, "CABLE Input") == 1


def test_detect_backend_supertonic_missing(monkeypatch: Any) -> None:
    monkeypatch.setattr("irswitch.commentary.tts._supertonic_available", lambda: False)
    assert detect_backend("supertonic") == "null"
    assert detect_backend("auto") != "supertonic"


def test_detect_backend_supertonic_when_installed(monkeypatch: Any) -> None:
    monkeypatch.setattr("irswitch.commentary.tts._supertonic_available", lambda: True)
    assert detect_backend("supertonic") == "supertonic"
    assert detect_backend("auto") != "supertonic"


def test_speak_text_supertonic_uses_backend(monkeypatch: Any) -> None:
    seen: dict[str, Any] = {}

    def fake_speak(
        text: str,
        *,
        voice: str,
        rate: int,
        device: str,
        timeout_s: float,
        steps: int = 6,
        locale: str = "en",
        cancelled: Any = None,
        before_play: Any = None,
    ) -> None:
        seen["text"] = text
        seen["voice"] = voice
        seen["rate"] = rate
        seen["device"] = device
        seen["steps"] = steps
        seen["locale"] = locale
        seen["before_play"] = before_play
        if before_play is not None:
            before_play()

    monkeypatch.setattr("irswitch.commentary.tts._supertonic_available", lambda: True)
    monkeypatch.setattr("irswitch.commentary.supertonic_backend.speak", fake_speak)
    result = speak_text(
        "He is hunting Lukas Novak down.",
        backend="supertonic",
        voice="M1",
        rate=-1,
        device="CABLE Input",
        steps=5,
        locale="en",
    )
    assert result.spoken is True
    assert result.backend == "supertonic"
    assert seen["steps"] == 5
    assert seen["device"] == "CABLE Input"


def test_speak_text_supertonic_wait_before_play(monkeypatch: Any) -> None:
    order: list[str] = []

    def fake_speak(*_args: Any, before_play: Any = None, **_kwargs: Any) -> None:
        order.append("synth")
        if before_play is not None:
            before_play()
        order.append("play")

    monkeypatch.setattr("irswitch.commentary.tts._supertonic_available", lambda: True)
    monkeypatch.setattr("irswitch.commentary.supertonic_backend.speak", fake_speak)
    result = speak_text(
        "He takes P5 from Rossi.",
        backend="supertonic",
        wait_before_play=lambda: order.append("duck"),
    )
    assert result.spoken is True
    assert order == ["synth", "duck", "play"]


def test_speak_text_supertonic_interrupt(monkeypatch: Any) -> None:
    from irswitch.commentary.supertonic_backend import PlaybackInterrupted

    def fake_speak(*_args: Any, **_kwargs: Any) -> None:
        raise PlaybackInterrupted

    monkeypatch.setattr("irswitch.commentary.tts._supertonic_available", lambda: True)
    monkeypatch.setattr("irswitch.commentary.supertonic_backend.speak", fake_speak)
    result = speak_text("Contact there.", backend="supertonic")
    assert result.spoken is False
    assert result.error == "interrupted"


def test_commentary_ini_loads_supertonic(tmp_path: Any) -> None:
    path = tmp_path / "config.ini"
    path.write_text(
        """[app]
http_host = 127.0.0.1
http_port = 17321
log_level = INFO
[iracing]
poll_hz = 5
[obs]
ws_url = ws://127.0.0.1:4455
password = x
[switching]
autoswitch_default = true
debounce_ms = 900
cooldown_ms = 1000
override_seconds = 120
safe_scene = Idle
[scenes]
IDLE = Idle
GARAGE = Pits
RACE = Race
REPLAY = Replay
[commentary]
enabled = true
tts_backend = supertonic
tts_voice = M1
tts_steps = 5
tts_rate = -1
audio_device = CABLE Input
""",
        encoding="utf-8",
    )
    cfg = AppConfig.from_file(path)
    assert cfg.overlay.commentary.tts_backend == "supertonic"
    assert cfg.overlay.commentary.tts_voice == "M1"
    assert cfg.overlay.commentary.tts_steps == 5
    assert overlay_values(cfg.overlay)["commentary.tts_steps"] == 5
