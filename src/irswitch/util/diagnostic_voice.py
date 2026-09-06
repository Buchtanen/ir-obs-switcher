"""Operator diagnostic SAPI on the Windows default playback device.

Independent of commentary TTS, OBS duck, and ``commentary.enabled``.
Missing SAPI / non-Windows / speak errors are fail-soft.
"""

from __future__ import annotations

import logging
import platform
import queue
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

logger = logging.getLogger(__name__)

PHRASES: dict[str, str] = {
    "iracing_connected": "Simulator running.",
    "iracing_disconnected": "iRacing disconnected.",
    "stream_started": "We are live.",
    "stream_stopped": "Stream stopped.",
    "switcher_fatal": "Fatal error. Switcher not working.",
}

SpeakFn = Callable[..., object]


@dataclass(frozen=True)
class DiagnosticVoiceSettings:
    """``[diagnostics]`` operator ear lane. Missing section stays off."""

    voice: bool = False
    cooldown_s: float = 4.0


class DiagnosticVoice:
    """Owned SAPI worker. Never shares the commentary queue or duck."""

    def __init__(
        self,
        settings: DiagnosticVoiceSettings,
        *,
        speak: SpeakFn | None = None,
        clock: Callable[[], float] = time.monotonic,
        system: str | None = None,
    ) -> None:
        self._settings = settings
        self._speak = speak
        self._clock = clock
        self._windows = (system or platform.system()) == "Windows"
        self._last: dict[str, float] = {}
        self._queue: queue.SimpleQueue[str | object] = queue.SimpleQueue()
        self._worker: threading.Thread | None = None
        self._closed = False
        self._sentinel = object()

    def configure(self, settings: DiagnosticVoiceSettings) -> None:
        self._settings = settings

    def announce(self, phrase_id: str, *, now: float | None = None) -> None:
        if self._closed or not self._settings.voice or not self._windows:
            return
        text = PHRASES.get(phrase_id)
        if not text:
            return
        stamp = self._clock() if now is None else now
        last = self._last.get(phrase_id)
        cooldown = max(0.0, float(self._settings.cooldown_s))
        if last is not None and stamp - last < cooldown:
            return
        self._last[phrase_id] = stamp
        self._ensure_worker()
        self._queue.put(text)

    def announce_fatal_blocking(self) -> None:
        """Best-effort speak before process exit. Does not use the worker."""
        if not self._settings.voice or not self._windows:
            return
        try:
            self._speak_line(PHRASES["switcher_fatal"])
        except Exception:
            logger.debug("diagnostic fatal speak failed", exc_info=True)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        worker = self._worker
        if worker is None:
            return
        self._queue.put(self._sentinel)
        worker.join(timeout=0.5)

    def _ensure_worker(self) -> None:
        worker = self._worker
        if worker is not None and worker.is_alive():
            return
        worker = threading.Thread(
            target=self._worker_loop,
            name="irswitch-diagnostic-voice",
            daemon=True,
        )
        self._worker = worker
        worker.start()

    def _worker_loop(self) -> None:
        while True:
            item = self._queue.get()
            if item is self._sentinel:
                return
            if not isinstance(item, str):
                continue
            try:
                self._speak_line(item)
            except Exception:
                logger.debug("diagnostic voice speak failed", exc_info=True)

    def _speak_line(self, text: str) -> None:
        speak = self._speak
        if speak is None:
            from irswitch.commentary.tts import speak_text

            speak = speak_text
        speak(
            text,
            locale="en",
            voice="",
            backend="sapi",
            device="",
            timeout_s=3.0,
        )


_voice: DiagnosticVoice | None = None


def configure_diagnostic_voice(settings: DiagnosticVoiceSettings) -> DiagnosticVoice:
    global _voice
    if _voice is None or _voice._closed:
        _voice = DiagnosticVoice(settings)
    else:
        _voice.configure(settings)
    return _voice


def announce_diagnostic(phrase_id: str) -> None:
    voice = _voice
    if voice is not None:
        voice.announce(phrase_id)


def announce_fatal_blocking() -> None:
    voice = _voice
    if voice is not None:
        voice.announce_fatal_blocking()


def close_diagnostic_voice() -> None:
    global _voice
    voice = _voice
    if voice is not None:
        voice.close()
    _voice = None
