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
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol

from irswitch.commentary.duck import ducker_from_settings
from irswitch.commentary.graph import GraphNode
from irswitch.commentary.graph_runtime import GraphCandidate
from irswitch.commentary.polish import PolishOutcome, polish_skeleton
from irswitch.commentary.speech_hero import mix_hero_name
from irswitch.commentary.speech_numbers import numbers_to_words
from irswitch.overlay.settings import CommentarySettings
from irswitch.race.ministory import CommitStatus, MiniStoryRegistry, MiniStoryToken

logger = logging.getLogger(__name__)

BACKENDS = ("auto", "sapi", "espeak", "null")
STREAM_START_EVENT = "STREAM_START"
SpeakRunner = Callable[[list[str], dict[str, str], float], subprocess.CompletedProcess[str]]
CancelProbe = Callable[[], bool]
PolishDebugHook = Callable[[dict[str, Any]], None]
SpokenTextHook = Callable[[str], None]
StoryDebugHook = Callable[[dict[str, Any]], None]
GraphLifecycleHook = Callable[[str, GraphCandidate, float], None]
_SAPI_PS1 = Path(__file__).with_name("sapi_speak.ps1")


class _TtsInterrupted(Exception):
    """Internal control flow for a cancelled backend process."""


_SAPI_VOICES_SCRIPT = """\
$voice = New-Object -ComObject SAPI.SpVoice
$voice.GetVoices() | ForEach-Object { $_.GetDescription() }
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
    priority: int = 0
    past_framing: bool = False
    hero_names: tuple[str, ...] = ()
    hero_name: str | None = None
    fact_pack: dict[str, Any] | None = None
    composition_path: tuple[str, ...] = ()
    graph_path: tuple[str, ...] = ()
    story_token: MiniStoryToken | None = None
    graph_candidate: GraphCandidate | None = None
    editorial_score: float | None = None


@dataclass(frozen=True)
class TtsResult:
    backend: str
    spoken: bool
    error: str | None = None


class TtsSink(Protocol):
    def enqueue(self, utterance: CommentaryUtterance) -> None:
        """Accept a validated line. Must not block the race loop."""

    def interrupt(self) -> None:
        """Best-effort cancel queued/in-flight speech (hard interrupt)."""

    def is_busy(self) -> bool:
        """True while a speak is in-flight or waiting (observed busy)."""

    def close(self) -> None:
        """Release owned worker resources after cancellation."""


@dataclass
class NullTtsSink:
    """Records utterances for tests and dry-runs. No audio.

    Instant by default (``is_busy`` false). Set ``force_busy`` to simulate a
    stuck sink for observed-busy / defer tests.
    """

    spoken: list[CommentaryUtterance] = field(default_factory=list)
    interrupted: int = 0
    force_busy: bool = False
    dropped: list[CommentaryUtterance] = field(default_factory=list)
    story_registry: MiniStoryRegistry | None = None
    on_graph_lifecycle: GraphLifecycleHook | None = None

    def enqueue(self, utterance: CommentaryUtterance) -> None:
        token = utterance.story_token
        if self.story_registry is not None and token is not None:
            decision = self.story_registry.commit(
                token, utterance.fact_pack, locale=utterance.locale
            )
            if decision.status == CommitStatus.INVALIDATED:
                self.dropped.append(utterance)
                return
            if decision.status == CommitStatus.RESOLVED:
                utterance = replace(
                    utterance,
                    text=decision.canonical,
                    fact_pack=decision.fact_pack,
                    past_framing=True,
                )
            self.story_registry.mark_speaking(token)
        if self.force_busy and self.spoken:
            # Depth ≤1: keep higher-or-equal priority, drop the other.
            prev = self.spoken[-1]
            if int(utterance.priority) < int(prev.priority):
                self.dropped.append(utterance)
                return
            self.dropped.append(prev)
            self.spoken[-1] = utterance
            return
        self.spoken.append(utterance)
        self._emit_graph_lifecycle("speaking", utterance)
        if self.story_registry is not None and token is not None and not self.force_busy:
            self.story_registry.complete(token)
        if not self.force_busy:
            self._emit_graph_lifecycle("completed", utterance)

    def interrupt(self) -> None:
        self.interrupted += 1
        self.spoken.clear()
        self.force_busy = False

    def is_busy(self) -> bool:
        return bool(self.force_busy)

    def close(self) -> None:
        self.interrupt()

    def _emit_graph_lifecycle(self, action: str, utterance: CommentaryUtterance) -> None:
        hook = self.on_graph_lifecycle
        candidate = utterance.graph_candidate
        if hook is None or candidate is None:
            return
        try:
            hook(action, candidate, time.monotonic())
        except Exception:
            logger.debug("commentary graph lifecycle hook failed", exc_info=True)


@dataclass
class ProcessTtsSink:
    """Speaks via a single serial worker thread (queue + one consumer).

    ``enqueue`` never waits for SAPI/espeak or duck fades. At most **one**
    waiter behind the in-flight speak (replace-by-priority); no sequential
    drain of a deep TTS backlog. Duck enter/exit stays on that one worker.
    """

    settings: CommentarySettings
    spoken: list[CommentaryUtterance] = field(default_factory=list)
    last_error: str | None = None
    last_result: TtsResult | None = None
    runner: SpeakRunner | None = None
    on_polish_debug: PolishDebugHook | None = None
    on_spoken_text: SpokenTextHook | None = None
    on_story_debug: StoryDebugHook | None = None
    on_graph_lifecycle: GraphLifecycleHook | None = None
    story_registry: MiniStoryRegistry | None = None
    _queue: queue.SimpleQueue[CommentaryUtterance | object] = field(
        default_factory=queue.SimpleQueue, repr=False
    )
    _worker_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _worker: threading.Thread | None = field(default=None, init=False, repr=False)
    _pending: int = field(default=0, init=False, repr=False)
    _speaking: bool = field(default=False, init=False, repr=False)
    _idle: threading.Condition = field(default_factory=threading.Condition, repr=False)
    _interrupt_generation: int = field(default=0, init=False, repr=False)
    _closed: bool = field(default=False, init=False, repr=False)
    _sentinel: object = field(default_factory=object, init=False, repr=False)

    def enqueue(self, utterance: CommentaryUtterance) -> None:
        """Accept a validated line. Must not block the race loop.

        Keeps at most one queued waiter. If a waiter already exists, replace it
        when incoming priority is higher-or-equal; otherwise drop incoming.
        """
        if self._closed:
            return
        self.spoken.append(utterance)
        if len(self.spoken) > 32:
            del self.spoken[:-16]

        accepted = True
        replaced: CommentaryUtterance | None = None
        with self._idle:
            waiters = self._pending - (1 if self._speaking else 0)
            if waiters >= 1:
                try:
                    old = self._queue.get_nowait()
                except queue.Empty:
                    old = None
                if isinstance(old, CommentaryUtterance):
                    self._pending = max(0, self._pending - 1)
                    if int(utterance.priority) < int(old.priority):
                        self._pending += 1
                        self._queue.put(old)
                        accepted = False
                    else:
                        replaced = old
            if accepted:
                self._pending += 1

        if not accepted:
            logger.debug(
                "tts enqueue dropped lower-prio node=%s prio=%s",
                utterance.node_id,
                utterance.priority,
            )
            return

        if replaced is not None:
            self._close_queued_story(replaced, "tts_queue_replaced")
        if utterance.story_token is not None:
            self._emit_story_debug(utterance.story_token, "building", "tts_queued")

        self._ensure_worker()
        self._queue.put(utterance)

    def interrupt(self) -> None:
        """Drop queued speaks; signal worker to skip remaining work best-effort."""
        dropped = 0
        dropped_utterances: list[CommentaryUtterance] = []
        with self._idle:
            self._interrupt_generation += 1
            while True:
                try:
                    queued = self._queue.get_nowait()
                    dropped += 1
                    if isinstance(queued, CommentaryUtterance):
                        dropped_utterances.append(queued)
                except queue.Empty:
                    break
            if dropped:
                self._pending = max(0, self._pending - dropped)
                if self._pending == 0 and not self._speaking:
                    self._idle.notify_all()
        for utterance in dropped_utterances:
            self._close_queued_story(utterance, "tts_queue_interrupted")

    def is_busy(self) -> bool:
        """True while speaking or a waiter is queued (#180 observed busy)."""
        with self._idle:
            return self._pending > 0 or self._speaking

    def close(self) -> None:
        """Bounded worker shutdown; current backend retains its own timeout."""
        if self._closed:
            return
        self._closed = True
        self.interrupt()
        worker = self._worker
        if worker is None:
            return
        self._queue.put(self._sentinel)
        worker.join(timeout=0.5)

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
            if utterance is self._sentinel:
                return
            if not isinstance(utterance, CommentaryUtterance):
                continue
            with self._idle:
                self._speaking = True
                generation = self._interrupt_generation
            try:
                self._speak(utterance, generation)
            except Exception:
                logger.exception("tts serial worker failed")
            finally:
                with self._idle:
                    self._speaking = False
                    self._pending = max(0, self._pending - 1)
                    if self._pending == 0:
                        self._idle.notify_all()

    def _speak(self, utterance: CommentaryUtterance, generation: int | None = None) -> None:
        if generation is None:
            generation = self._interrupt_generation

        def cancelled() -> bool:
            return generation != self._interrupt_generation

        if cancelled():
            return
        # Digits + compact units → words; mix hero name via he/him/his only.
        spoken_text = numbers_to_words(utterance.text, utterance.locale)
        spoken_text = mix_hero_name(
            spoken_text,
            utterance.hero_names,
            utterance.locale,
            name=utterance.hero_name,
        )
        past = bool(utterance.past_framing) and getattr(
            self.settings.scheduler, "llm_past_framing", True
        )
        outcome: PolishOutcome | None = None
        if self.settings.llm_polish:
            polish_kwargs: dict[str, Any] = {
                "past": past,
                "driver_names": utterance.hero_names,
            }
            if utterance.fact_pack is not None:
                polish_kwargs.update(
                    locale=utterance.locale,
                    fact_pack=utterance.fact_pack,
                    composition_path=utterance.composition_path,
                )
            outcome = polish_skeleton(spoken_text, utterance.node, self.settings, **polish_kwargs)
            self._emit_polish_debug(utterance, outcome)
            polished = (outcome.text or "").strip()
            if polished:
                spoken_text = numbers_to_words(polished, utterance.locale)
                spoken_text = mix_hero_name(
                    spoken_text,
                    utterance.hero_names,
                    utterance.locale,
                    name=utterance.hero_name,
                )
            if not spoken_text.strip():
                return
        token = utterance.story_token
        lifecycle_token = token
        registry = self.story_registry
        if registry is not None and token is not None:
            decision = registry.commit(token, utterance.fact_pack, locale=utterance.locale)
            if decision.status == CommitStatus.INVALIDATED or cancelled():
                self._emit_story_debug(token, "skipped", "ministory_invalidated")
                return
            lifecycle_token = registry.current_token(token) or token
            self._emit_story_debug(
                lifecycle_token, "committed", f"ministory_{decision.status.value}"
            )
            if decision.status == CommitStatus.RESOLVED:
                spoken_text = decision.canonical
                if (
                    self.settings.llm_polish
                    and outcome is not None
                    and outcome.outcome == "ok"
                    and outcome.attempts < 2
                    and decision.fact_pack is not None
                ):
                    remaining = 2 - outcome.attempts
                    resolved_settings = replace(self.settings, llm_max_attempts=remaining)
                    resolved_outcome = polish_skeleton(
                        decision.canonical,
                        utterance.node,
                        resolved_settings,
                        past=True,
                        driver_names=utterance.hero_names,
                        locale=utterance.locale,
                        fact_pack=decision.fact_pack,
                        composition_path=utterance.composition_path,
                    )
                    self._emit_polish_debug(utterance, resolved_outcome)
                    spoken_text = resolved_outcome.text or decision.canonical
                spoken_text = numbers_to_words(spoken_text, utterance.locale)
                spoken_text = mix_hero_name(
                    spoken_text,
                    utterance.hero_names,
                    utterance.locale,
                    name=utterance.hero_name,
                )
            if not registry.mark_speaking(token):
                self._emit_story_debug(token, "skipped", "ministory_invalidated")
                return
            lifecycle_token = registry.current_token(token) or lifecycle_token
            self._emit_story_debug(lifecycle_token, "speaking", "tts_started")
        self._emit_graph_lifecycle("speaking", utterance)
        try:
            with ducker_from_settings(self.settings):
                if cancelled():
                    return
                result = speak_text(
                    spoken_text,
                    locale=utterance.locale,
                    voice=self.settings.tts_voice,
                    rate=self.settings.tts_rate,
                    backend=self.settings.tts_backend,
                    device=self.settings.audio_device,
                    timeout_s=speak_timeout_s(
                        self.settings,
                        event_type=utterance.event_type,
                        node=utterance.node,
                    ),
                    runner=self.runner,
                    cancelled=cancelled,
                )
        finally:
            if registry is not None and token is not None:
                state_before = registry.state_of(token)
                registry.complete(token)
                state = registry.state_of(token)
                if state is None and state_before is None:
                    action = "invalidated"
                else:
                    action = state.value if state is not None else "completed"
                self._emit_story_debug(
                    registry.current_token(token) or lifecycle_token or token,
                    action,
                    "tts_finished",
                )
            self._emit_graph_lifecycle(
                "interrupted" if cancelled() else "completed",
                utterance,
            )
        self.last_result = result
        self.last_error = result.error
        if result.error:
            logger.warning("tts speak failed backend=%s error=%s", result.backend, result.error)
        elif result.spoken and self.on_spoken_text is not None:
            try:
                self.on_spoken_text(spoken_text)
            except Exception:
                logger.debug("commentary final-spoken hook failed", exc_info=True)

    def _emit_polish_debug(self, utterance: CommentaryUtterance, outcome: PolishOutcome) -> None:
        hook = self.on_polish_debug
        if hook is None:
            return
        try:
            hook(
                outcome.debug_record(
                    node_id=utterance.node_id,
                    event_type=utterance.event_type,
                )
            )
        except Exception:
            logger.debug("commentary polish debug hook failed", exc_info=True)

    def _emit_story_debug(self, token: MiniStoryToken, action: str, reason: str) -> None:
        hook = self.on_story_debug
        if hook is None:
            return
        try:
            hook(
                {
                    "action": action,
                    "reason": reason,
                    "eventType": token.event_type,
                    "storyId": token.story_id,
                    "storyRevision": token.revision,
                    "runEpoch": token.run_epoch,
                    "heroOrderRevision": token.hero_order_revision,
                    "correlationId": token.correlation_id,
                }
            )
        except Exception:
            logger.debug("commentary mini-story debug hook failed", exc_info=True)

    def _emit_graph_lifecycle(self, action: str, utterance: CommentaryUtterance) -> None:
        hook = self.on_graph_lifecycle
        candidate = utterance.graph_candidate
        if hook is None or candidate is None:
            return
        try:
            hook(action, candidate, time.monotonic())
        except Exception:
            logger.debug("commentary graph lifecycle hook failed", exc_info=True)

    def _close_queued_story(self, utterance: CommentaryUtterance, reason: str) -> None:
        token = utterance.story_token
        if token is None:
            return
        registry = self.story_registry
        if registry is not None:
            registry.invalidate(token)
        self._emit_story_debug(token, "invalidated", reason)


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


def build_tts_sink(
    settings: CommentarySettings | None = None,
    *,
    on_polish_debug: PolishDebugHook | None = None,
) -> TtsSink:
    cfg = settings or CommentarySettings()
    if detect_backend(cfg.tts_backend) == "null":
        return NullTtsSink()
    return ProcessTtsSink(
        settings=cfg,
        on_polish_debug=on_polish_debug if cfg.llm_polish else None,
    )


def speak_timeout_s(
    settings: CommentarySettings,
    *,
    event_type: str = "",
    node: GraphNode | None = None,
) -> float:
    """Subprocess TTS timeout. STREAM_START may exceed commentary.max_utterance_s."""
    cap = float(settings.max_utterance_s)
    types = {str(event_type).strip().upper()}
    if node is not None:
        types.update(str(item).upper() for item in node.event_types)
        if STREAM_START_EVENT in types:
            cap = max(cap, float(node.tts.max_seconds))
    elif STREAM_START_EVENT in types:
        cap = max(cap, 16.0)
    return max(cap + 10.0, 20.0)


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
    cancelled: CancelProbe | None = None,
) -> TtsResult:
    """Blocking speak for a worker thread. Fail-soft; never raises to callers."""
    spoken = (text or "").strip()
    if not spoken:
        return TtsResult(backend="null", spoken=False, error="empty text")
    resolved = detect_backend(backend)
    if resolved == "null":
        return TtsResult(backend="null", spoken=False, error="no TTS backend on this host")
    try:
        if cancelled is not None and cancelled():
            raise _TtsInterrupted
        if resolved == "sapi":
            _speak_sapi(
                spoken,
                voice=voice,
                rate=rate,
                device=device,
                timeout_s=timeout_s,
                runner=runner,
                cancelled=cancelled,
            )
        else:
            _speak_espeak(
                spoken,
                locale=locale,
                voice=voice,
                rate=rate,
                timeout_s=timeout_s,
                runner=runner,
                cancelled=cancelled,
            )
    except _TtsInterrupted:
        return TtsResult(backend=resolved, spoken=False, error="interrupted")
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
    cancelled: CancelProbe | None = None,
) -> subprocess.CompletedProcess[str]:
    if runner is not None:
        completed = runner(argv, env or {}, timeout_s)
        if cancelled is not None and cancelled():
            raise _TtsInterrupted
        return completed
    if cancelled is None:
        return subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_s,
            env=env,
        )
    process = subprocess.Popen(
        argv,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )
    deadline = time.monotonic() + timeout_s
    while process.poll() is None:
        if cancelled():
            process.terminate()
            try:
                process.communicate(timeout=0.5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate()
            raise _TtsInterrupted
        if time.monotonic() >= deadline:
            process.kill()
            stdout, stderr = process.communicate()
            raise subprocess.TimeoutExpired(argv, timeout_s, output=stdout, stderr=stderr)
        time.sleep(0.02)
    stdout, stderr = process.communicate()
    return subprocess.CompletedProcess(argv, process.returncode, stdout=stdout, stderr=stderr)


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
    cancelled: CancelProbe | None = None,
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
        cancelled=cancelled,
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
    cancelled: CancelProbe | None = None,
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
        cancelled=cancelled,
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
