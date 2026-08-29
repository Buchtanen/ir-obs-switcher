"""TTS backend resolution and subprocess speak path (no real audio)."""

from __future__ import annotations

import subprocess
from typing import Any

from irswitch.commentary.graph import GraphNode, SlotSpec, TtsLimits
from irswitch.commentary.tts import (
    CommentaryUtterance,
    ProcessTtsSink,
    detect_backend,
    speak_text,
)
from irswitch.overlay.settings import CommentarySettings


def _ok_run(
    argv: list[str], env: dict[str, str], timeout_s: float
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")


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
        assert "-Command" in argv
        return _ok_run(argv, env, timeout_s)

    result = speak_text("Hello.", voice="Microsoft David", rate=-2, backend="sapi", runner=runner)
    assert result.spoken is True
    assert seen_env["IRSWITCH_TTS_VOICE"] == "Microsoft David"
    assert seen_env["IRSWITCH_TTS_RATE"] == "-2"
    assert seen_env["IRSWITCH_TTS_B64"]


def test_process_sink_enqueues_without_blocking(monkeypatch: Any) -> None:
    monkeypatch.setattr(
        "irswitch.commentary.tts.speak_text",
        lambda *args, **kwargs: type("R", (), {"backend": "null", "spoken": True, "error": None})(),
    )
    sink = ProcessTtsSink(CommentarySettings(tts_backend="null"))
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
    sink.enqueue(
        CommentaryUtterance(
            node_id="overtake",
            locale="en",
            emotion="unknown",
            text="You take P5.",
            event_type="OVERTAKE",
            event_id="e1",
            correlation_id="c1",
            estimated_seconds=1.0,
            node=node,
        )
    )
    assert sink.spoken[-1].text == "You take P5."
