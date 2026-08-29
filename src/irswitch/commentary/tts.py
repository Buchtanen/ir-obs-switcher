"""TTS sinks. Windows SAPI (PowerShell) or espeak-ng; never block the race loop."""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from typing import Callable, Protocol

from irswitch.commentary.graph import GraphNode
from irswitch.overlay.settings import CommentarySettings

logger = logging.getLogger(__name__)

BACKENDS = ("auto", "sapi", "espeak", "null")
SpeakRunner = Callable[[list[str], dict[str, str], float], subprocess.CompletedProcess[str]]

_SAPI_SCRIPT = """\
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$rate = 0
[void][int]::TryParse($env:IRSWITCH_TTS_RATE, [ref]$rate)
if ($rate -lt -10) { $rate = -10 }
if ($rate -gt 10) { $rate = 10 }
$synth.Rate = $rate
if ($env:IRSWITCH_TTS_VOICE) { $synth.SelectVoice($env:IRSWITCH_TTS_VOICE) }
$text = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($env:IRSWITCH_TTS_B64))
$synth.Speak($text)
"""

_SAPI_VOICES_SCRIPT = """\
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.GetInstalledVoices() | ForEach-Object { $_.VoiceInfo.Name }
"""


@dataclass(frozen=True)
class CommentaryUtterance:
    node_id: str
    locale: str
    emotion: str
    text: str
    event_type: str
    event_id: str
    correlation_id: str
    estimated_seconds: float
    node: GraphNode


@dataclass(frozen=True)
class TtsResult:
    backend: str
    spoken: bool
    error: str | None = None


class TtsSink(Protocol):
    def enqueue(self, utterance: CommentaryUtterance) -> None:
        """Accept a validated line. Must not block the race loop."""


@dataclass
class NullTtsSink:
    """Records utterances for tests and dry-runs. No audio."""

    spoken: list[CommentaryUtterance] = field(default_factory=list)

    def enqueue(self, utterance: CommentaryUtterance) -> None:
        self.spoken.append(utterance)


@dataclass
class ProcessTtsSink:
    """Speaks via a subprocess in a worker thread / executor."""

    settings: CommentarySettings
    spoken: list[CommentaryUtterance] = field(default_factory=list)
    last_error: str | None = None
    last_result: TtsResult | None = None
    runner: SpeakRunner | None = None

    def enqueue(self, utterance: CommentaryUtterance) -> None:
        self.spoken.append(utterance)
        if len(self.spoken) > 32:
            del self.spoken[:-16]
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            threading.Thread(target=self._speak, args=(utterance,), daemon=True).start()
            return
        loop.run_in_executor(None, self._speak, utterance)

    def _speak(self, utterance: CommentaryUtterance) -> None:
        result = speak_text(
            utterance.text,
            locale=utterance.locale,
            voice=self.settings.tts_voice,
            rate=self.settings.tts_rate,
            backend=self.settings.tts_backend,
            timeout_s=max(self.settings.max_utterance_s + 3.0, 6.0),
            runner=self.runner,
        )
        self.last_result = result
        self.last_error = result.error
        if result.error:
            logger.warning("tts speak failed backend=%s error=%s", result.backend, result.error)


def detect_backend(preferred: str = "auto") -> str:
    choice = (preferred or "auto").strip().lower()
    if choice == "null":
        return "null"
    if choice == "sapi" and _sapi_available():
        return "sapi"
    if choice == "espeak" and _espeak_bin():
        return "espeak"
    if choice in {"sapi", "espeak"}:
        return "null"
    if _sapi_available():
        return "sapi"
    if _espeak_bin():
        return "espeak"
    return "null"


def build_tts_sink(settings: CommentarySettings | None = None) -> TtsSink:
    cfg = settings or CommentarySettings()
    if detect_backend(cfg.tts_backend) == "null":
        return NullTtsSink()
    return ProcessTtsSink(settings=cfg)


def speak_text(
    text: str,
    *,
    locale: str = "en",
    voice: str = "",
    rate: int = 0,
    backend: str = "auto",
    timeout_s: float = 12.0,
    runner: SpeakRunner | None = None,
) -> TtsResult:
    """Blocking speak for a worker thread. Fail-soft; never raises to callers."""
    spoken = (text or "").strip()
    if not spoken:
        return TtsResult(backend="null", spoken=False, error="empty text")
    resolved = detect_backend(backend)
    if resolved == "null":
        return TtsResult(backend="null", spoken=False, error="no TTS backend on this host")
    try:
        if resolved == "sapi":
            _speak_sapi(spoken, voice=voice, rate=rate, timeout_s=timeout_s, runner=runner)
        else:
            _speak_espeak(
                spoken,
                locale=locale,
                voice=voice,
                rate=rate,
                timeout_s=timeout_s,
                runner=runner,
            )
    except subprocess.TimeoutExpired:
        return TtsResult(backend=resolved, spoken=False, error="tts timeout")
    except Exception as exc:
        logger.warning("tts backend %s failed", resolved, exc_info=True)
        return TtsResult(backend=resolved, spoken=False, error=str(exc))
    return TtsResult(backend=resolved, spoken=True)


def list_voices(backend: str = "auto") -> list[str]:
    resolved = detect_backend(backend)
    try:
        if resolved == "sapi":
            return _list_sapi_voices()
        if resolved == "espeak":
            return _list_espeak_voices()
    except Exception:
        logger.debug("tts voice listing failed", exc_info=True)
    return []


def _sapi_available() -> bool:
    return sys.platform == "win32" and bool(shutil.which("powershell") or shutil.which("pwsh"))


def _espeak_bin() -> str | None:
    return shutil.which("espeak-ng") or shutil.which("espeak")


def _run(
    argv: list[str],
    *,
    env: dict[str, str] | None = None,
    timeout_s: float,
    runner: SpeakRunner | None,
) -> subprocess.CompletedProcess[str]:
    if runner is not None:
        return runner(argv, env or {}, timeout_s)
    return subprocess.run(
        argv,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_s,
        env=env,
    )


def _speak_sapi(
    text: str,
    *,
    voice: str,
    rate: int,
    timeout_s: float,
    runner: SpeakRunner | None,
) -> None:
    env = os.environ.copy()
    env["IRSWITCH_TTS_B64"] = base64.b64encode(text.encode("utf-8")).decode("ascii")
    env["IRSWITCH_TTS_RATE"] = str(int(rate))
    env["IRSWITCH_TTS_VOICE"] = voice or ""
    exe = shutil.which("powershell") or shutil.which("pwsh") or "powershell"
    completed = _run(
        [exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", _SAPI_SCRIPT],
        env=env,
        timeout_s=timeout_s,
        runner=runner,
    )
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "sapi failed").strip()
        raise RuntimeError(err[:300])


def _speak_espeak(
    text: str,
    *,
    locale: str,
    voice: str,
    rate: int,
    timeout_s: float,
    runner: SpeakRunner | None,
) -> None:
    binary = _espeak_bin()
    if not binary:
        raise RuntimeError("espeak-ng not installed")
    wpm = 80 + (max(-10, min(10, int(rate))) + 10) * 10
    lang = "cs" if locale.lower().startswith("cs") else "en"
    voice_arg = voice or lang
    completed = _run(
        [binary, "-v", voice_arg, "-s", str(wpm), "--", text],
        timeout_s=timeout_s,
        runner=runner,
    )
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "espeak failed").strip()
        raise RuntimeError(err[:300])


def _list_sapi_voices() -> list[str]:
    exe = shutil.which("powershell") or shutil.which("pwsh") or "powershell"
    completed = subprocess.run(
        [exe, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", _SAPI_VOICES_SCRIPT],
        check=False,
        capture_output=True,
        text=True,
        timeout=8.0,
    )
    if completed.returncode != 0:
        return []
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def _list_espeak_voices() -> list[str]:
    binary = _espeak_bin()
    if not binary:
        return []
    completed = subprocess.run(
        [binary, "--voices"],
        check=False,
        capture_output=True,
        text=True,
        timeout=8.0,
    )
    voices: list[str] = []
    for line in completed.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) >= 2:
            voices.append(parts[1])
        if len(voices) >= 40:
            break
    return voices
