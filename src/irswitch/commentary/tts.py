"""TTS sinks. Windows SAPI (PowerShell) or espeak-ng; never block the race loop."""

from __future__ import annotations

import base64
import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from irswitch.commentary.duck import ducker_from_settings
from irswitch.commentary.graph import GraphNode
from irswitch.overlay.settings import CommentarySettings

logger = logging.getLogger(__name__)

BACKENDS = ("auto", "sapi", "espeak", "null")
SpeakRunner = Callable[[list[str], dict[str, str], float], subprocess.CompletedProcess[str]]
_SAPI_PS1 = Path(__file__).with_name("sapi_speak.ps1")

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
    """Speaks via a single serial worker thread (queue + one consumer).

    ``enqueue`` only appends history and puts on an unbounded queue — never
    waits for SAPI/espeak or duck fades. Concurrent enqueues cannot start two
    speaks at once; duck enter/exit stays on that one worker path and remains
    nested-safe via the shared ``VolumeDucker``.
    """

    settings: CommentarySettings
    spoken: list[CommentaryUtterance] = field(default_factory=list)
    last_error: str | None = None
    last_result: TtsResult | None = None
    runner: SpeakRunner | None = None
    _queue: queue.SimpleQueue[CommentaryUtterance] = field(
        default_factory=queue.SimpleQueue, repr=False
    )
    _worker_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _worker: threading.Thread | None = field(default=None, init=False, repr=False)
    _pending: int = field(default=0, init=False, repr=False)
    _speaking: bool = field(default=False, init=False, repr=False)
    _idle: threading.Condition = field(default_factory=threading.Condition, repr=False)

    def enqueue(self, utterance: CommentaryUtterance) -> None:
        """Accept a validated line. Must not block the race loop."""
        self.spoken.append(utterance)
        if len(self.spoken) > 32:
            del self.spoken[:-16]
        with self._idle:
            self._pending += 1
        self._ensure_worker()
        self._queue.put(utterance)

    def pending_count(self) -> int:
        """Queued + in-flight speaks (test / diagnostics)."""
        with self._idle:
            return self._pending

    def wait_idle(self, timeout_s: float = 5.0) -> bool:
        """Block until the serial worker has drained. For tests only."""
        deadline = time.monotonic() + max(0.0, float(timeout_s))
        with self._idle:
            while self._pending > 0 or self._speaking:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                self._idle.wait(remaining)
            return True

    def _ensure_worker(self) -> None:
        with self._worker_lock:
            worker = self._worker
            if worker is not None and worker.is_alive():
                return
            worker = threading.Thread(
                target=self._worker_loop,
                name="irswitch-commentary-tts",
                daemon=True,
            )
            self._worker = worker
            worker.start()

    def _worker_loop(self) -> None:
        while True:
            utterance = self._queue.get()
            with self._idle:
                self._speaking = True
            try:
                self._speak(utterance)
            except Exception:
                logger.exception("tts serial worker failed")
            finally:
                with self._idle:
                    self._speaking = False
                    self._pending = max(0, self._pending - 1)
                    if self._pending == 0:
                        self._idle.notify_all()

    def _speak(self, utterance: CommentaryUtterance) -> None:
        with ducker_from_settings(self.settings):
            result = speak_text(
                utterance.text,
                locale=utterance.locale,
                voice=self.settings.tts_voice,
                rate=self.settings.tts_rate,
                backend=self.settings.tts_backend,
                device=self.settings.audio_device,
                timeout_s=max(self.settings.max_utterance_s + 10.0, 20.0),
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
    device: str = "",
    timeout_s: float = 25.0,
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
            _speak_sapi(
                spoken,
                voice=voice,
                rate=rate,
                device=device,
                timeout_s=timeout_s,
                runner=runner,
            )
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


def select_sapi_output_name(descriptions: list[str], want: str) -> str | None:
    """Pick a playback device. Prefer stereo over 16ch when both match."""
    needle = (want or "").strip().lower()
    if not needle:
        return None
    matches = [name for name in descriptions if needle in name.lower()]
    stereo = [name for name in matches if "16ch" not in name.lower()]
    pool = stereo or matches
    return pool[0] if pool else None


def _speak_sapi(
    text: str,
    *,
    voice: str,
    rate: int,
    device: str,
    timeout_s: float,
    runner: SpeakRunner | None,
) -> None:
    env = os.environ.copy()
    env["IRSWITCH_TTS_B64"] = base64.b64encode(text.encode("utf-8")).decode("ascii")
    env["IRSWITCH_TTS_RATE"] = str(int(rate))
    env["IRSWITCH_TTS_VOICE"] = voice or ""
    env["IRSWITCH_TTS_DEVICE"] = device.strip()
    exe = shutil.which("powershell") or shutil.which("pwsh") or "powershell"
    script = str(_SAPI_PS1)
    completed = _run(
        [
            exe,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            script,
        ],
        env=env,
        timeout_s=timeout_s,
        runner=runner,
    )
    if completed.returncode != 0:
        err = (completed.stderr or completed.stdout or "sapi failed").strip()
        raise RuntimeError(err[:300])
    chosen = (completed.stdout or "").strip()
    if chosen:
        logger.info("tts sapi %s", chosen.splitlines()[-1][:200])


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
        [
            exe,
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            _SAPI_VOICES_SCRIPT,
        ],
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
