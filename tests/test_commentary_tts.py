"""TTS backend resolution and subprocess speak path (no real audio)."""

from __future__ import annotations

import subprocess
import threading
import time
from typing import Any

from irswitch.commentary.duck import reset_shared_ducker
from irswitch.commentary.graph import GraphNode, SlotSpec, TtsLimits
from irswitch.commentary.tts import (
    CommentaryUtterance,
    ProcessTtsSink,
    TtsResult,
    detect_backend,
    select_sapi_output_name,
    speak_text,
)
from irswitch.overlay.settings import CommentarySettings


def _ok_run(
    argv: list[str], env: dict[str, str], timeout_s: float
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")


def _sample_utterance(text: str = "You take P5.", event_id: str = "e1") -> CommentaryUtterance:
    node = GraphNode(
        id="overtake",
        family="position",
        event_types=("OVERTAKE",),
        phases=("RESULT",),
        speak_priority=1,
        cooldown_s=1.0,
        slots=(SlotSpec("position", "int", "5"),),
        hr_states=("unknown",),
        tts=TtsLimits(),
    )
    return CommentaryUtterance(
        node_id="overtake",
        locale="en",
        emotion="unknown",
        text=text,
        event_type="OVERTAKE",
        event_id=event_id,
        correlation_id="c1",
        estimated_seconds=1.0,
        node=node,
    )


def test_detect_backend_null_when_forced() -> None:
    assert detect_backend("null") == "null"


def test_speak_text_empty_is_not_spoken() -> None:
    result = speak_text("   ")
    assert result.spoken is False
    assert result.error == "empty text"


def test_speak_text_espeak_uses_runner(monkeypatch: Any) -> None:
    monkeypatch.setattr("irswitch.commentary.tts.detect_backend", lambda _pref="auto": "espeak")
    monkeypatch.setattr("irswitch.commentary.tts._espeak_bin", lambda: "/usr/bin/espeak-ng")
    seen: list[list[str]] = []

    def runner(
        argv: list[str], env: dict[str, str], timeout_s: float
    ) -> subprocess.CompletedProcess[str]:
        seen.append(argv)
        return _ok_run(argv, env, timeout_s)

    result = speak_text(
        "You take P5 from Rossi.", locale="en", rate=0, backend="espeak", runner=runner
    )
    assert result.spoken is True
    assert result.backend == "espeak"
    assert seen[0][0] == "/usr/bin/espeak-ng"
    assert "You take P5 from Rossi." in seen[0]


def test_speak_text_sapi_passes_base64_env(monkeypatch: Any) -> None:
    monkeypatch.setattr("irswitch.commentary.tts.detect_backend", lambda _pref="auto": "sapi")
    seen_env: dict[str, str] = {}

    def runner(
        argv: list[str], env: dict[str, str], timeout_s: float
    ) -> subprocess.CompletedProcess[str]:
        seen_env.update(env)
        assert "-File" in argv
        assert argv[-1].endswith("sapi_speak.ps1")
        return _ok_run(argv, env, timeout_s)

    result = speak_text("Hello.", voice="Microsoft David", rate=-2, backend="sapi", runner=runner)
    assert result.spoken is True
    assert seen_env["IRSWITCH_TTS_VOICE"] == "Microsoft David"
    assert seen_env["IRSWITCH_TTS_RATE"] == "-2"
    assert seen_env["IRSWITCH_TTS_B64"]


def test_speak_text_sapi_passes_audio_device_env(monkeypatch: Any) -> None:
    monkeypatch.setattr("irswitch.commentary.tts.detect_backend", lambda _pref="auto": "sapi")
    seen_env: dict[str, str] = {}

    def runner(
        argv: list[str], env: dict[str, str], timeout_s: float
    ) -> subprocess.CompletedProcess[str]:
        seen_env.update(env)
        return _ok_run(argv, env, timeout_s)

    result = speak_text("Hello.", backend="sapi", device="CABLE Input", runner=runner)
    assert result.spoken is True
    assert seen_env["IRSWITCH_TTS_DEVICE"] == "CABLE Input"


def test_sapi_script_plays_via_waveout_not_default_device() -> None:
    from irswitch.commentary.tts import _SAPI_PS1

    text = _SAPI_PS1.read_text(encoding="utf-8")
    assert "IrswitchWaveOut" in text
    assert "SpMemoryStream" in text
    assert "waveOutOpen" in text


def test_select_sapi_output_skips_16ch_when_stereo_exists() -> None:
    picked = select_sapi_output_name(
        [
            "CABLE Input (VB-Audio Virtual Cable)",
            "CABLE Input Cable 16ch (VB-Audio Virtual Cable)",
        ],
        "CABLE Input",
    )
    assert picked == "CABLE Input (VB-Audio Virtual Cable)"


def test_select_sapi_output_empty_want_is_none() -> None:
    assert select_sapi_output_name(["CABLE Input (VB-Audio Virtual Cable)"], "") is None


def test_process_sink_enqueues_without_blocking(monkeypatch: Any) -> None:
    gate = threading.Event()

    def blocked_speak(*_args: Any, **_kwargs: Any) -> TtsResult:
        gate.wait(timeout=2.0)
        return TtsResult(backend="null", spoken=True, error=None)

    monkeypatch.setattr("irswitch.commentary.tts.speak_text", blocked_speak)
    sink = ProcessTtsSink(CommentarySettings(tts_backend="null"))
    started = time.perf_counter()
    sink.enqueue(_sample_utterance())
    elapsed = time.perf_counter() - started
    assert sink.spoken[-1].text == "You take P5."
    assert elapsed < 0.05, f"enqueue blocked for {elapsed:.3f}s"
    assert sink.pending_count() >= 1
    gate.set()
    assert sink.wait_idle(timeout_s=2.0)


def test_process_sink_serialises_concurrent_speaks(monkeypatch: Any) -> None:
    """Concurrent enqueue must not run two speaks (or duck cycles) at once."""
    reset_shared_ducker()
    store = {"Desktop": 1.0}
    duck_depths: list[int] = []
    active = {"n": 0, "max": 0}
    speak_order: list[str] = []
    lock = threading.Lock()

    def get_mul(name: str) -> float | None:
        return store[name]

    def set_mul(name: str, mul: float) -> bool:
        store[name] = mul
        return True

    monkeypatch.setattr("irswitch.commentary.duck._obs_get_mul", get_mul)
    monkeypatch.setattr("irswitch.commentary.duck._obs_set_mul", set_mul)

    def slow_speak(text: str, **_kwargs: Any) -> TtsResult:
        with lock:
            active["n"] += 1
            active["max"] = max(active["max"], active["n"])
            speak_order.append(text)
            from irswitch.commentary.duck import ducker_from_settings

            # Depth observed on shared ducker while speak runs (enter already done).
            ducker = ducker_from_settings(
                CommentarySettings(duck_input="Desktop", duck_ratio=0.25, duck_fade_ms=0)
            )
            duck_depths.append(ducker._depth)
        time.sleep(0.04)
        with lock:
            active["n"] -= 1
        return TtsResult(backend="null", spoken=True, error=None)

    monkeypatch.setattr("irswitch.commentary.tts.speak_text", slow_speak)
    settings = CommentarySettings(
        tts_backend="null", duck_input="Desktop", duck_ratio=0.25, duck_fade_ms=0
    )
    sink = ProcessTtsSink(settings=settings)

    for i in range(5):
        sink.enqueue(_sample_utterance(text=f"line-{i}", event_id=f"e{i}"))

    assert sink.wait_idle(timeout_s=3.0)
    assert active["max"] == 1
    assert speak_order == [f"line-{i}" for i in range(5)]
    # Serial worker: each speak sees duck depth 1 (no overlapping nested enters).
    assert duck_depths == [1, 1, 1, 1, 1]
    assert store["Desktop"] == 1.0
    assert sink.pending_count() == 0
    reset_shared_ducker()


def test_process_sink_queue_invariant_single_worker(monkeypatch: Any) -> None:
    workers_seen: set[int] = set()
    barrier = threading.Barrier(2)

    def speak_on_worker(*_args: Any, **_kwargs: Any) -> TtsResult:
        workers_seen.add(threading.get_ident())
        if len(workers_seen) == 1:
            try:
                barrier.wait(timeout=1.0)
            except threading.BrokenBarrierError:
                pass
        return TtsResult(backend="null", spoken=True, error=None)

    monkeypatch.setattr("irswitch.commentary.tts.speak_text", speak_on_worker)
    sink = ProcessTtsSink(CommentarySettings(tts_backend="null"))
    sink.enqueue(_sample_utterance(text="a", event_id="a"))
    sink.enqueue(_sample_utterance(text="b", event_id="b"))
    # Hold first speak until second is queued; still one worker thread id.
    time.sleep(0.02)
    try:
        barrier.wait(timeout=1.0)
    except threading.BrokenBarrierError:
        pass
    assert sink.wait_idle(timeout_s=2.0)
    assert len(workers_seen) == 1
    assert sink._worker is not None
    assert sink._worker.ident in workers_seen
