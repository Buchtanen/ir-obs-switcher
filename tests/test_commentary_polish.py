"""Tests for optional commentary LLM polish."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from irswitch.commentary.graph import load_sequence_graph
from irswitch.commentary.polish import build_polish_request, polish_skeleton
from irswitch.commentary.tts import ProcessTtsSink, build_tts_sink
from irswitch.overlay.models import RaceState
from irswitch.overlay.settings import (
    CommentarySettings,
    OverlaySettings,
    OverlayTapeSettings,
    OverlayV4Settings,
)
from irswitch.overlay.tape import OverlaySessionTape
from irswitch.util.logging import set_runtime_log_level


def _open_tape(tmp_path: Path) -> OverlaySessionTape:
    tape = OverlaySessionTape(get_version=lambda: "test")
    settings = OverlaySettings(
        v4=OverlayV4Settings(renderer=True),
        tape=OverlayTapeSettings(enabled=True, directory=str(tmp_path)),
    )
    tape.observe(
        RaceState(
            connected=True,
            overlay_mode="RACE",
            session_state=4,
            subsession_id="1",
            session_num=0,
        ),
        10.0,
        settings,
    )
    return tape


def test_polish_disabled_returns_skeleton() -> None:
    graph = load_sequence_graph()
    node = graph.nodes["hunting"]
    settings = CommentarySettings(llm_polish=False)
    outcome = polish_skeleton("Gap 0.42 to Smith.", node, settings)
    assert outcome.outcome == "fallback_disabled"
    assert outcome.text == "Gap 0.42 to Smith."


def test_polish_uses_mock_http_response() -> None:
    graph = load_sequence_graph()
    node = graph.nodes["hunting"]
    settings = CommentarySettings(llm_polish=True, llm_timeout_s=5.0)

    def opener(req, timeout):  # noqa: ARG001
        payload = {
            "choices": [
                {
                    "message": {
                        "content": "He is closing on Smith, gap 0.42 seconds.",
                    }
                }
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 8},
        }
        return json.dumps(payload).encode("utf-8")

    outcome = polish_skeleton("Gap 0.42 to Smith.", node, settings, opener=opener)
    assert outcome.outcome == "ok"
    assert "0.42" in outcome.text
    assert outcome.request["model"] == settings.llm_model


def test_polish_rejects_non_http_scheme() -> None:
    graph = load_sequence_graph()
    node = graph.nodes["hunting"]
    settings = CommentarySettings(
        llm_polish=True,
        llm_base_url="file:///tmp/evil",
    )
    outcome = polish_skeleton("Gap 0.42 to Smith.", node, settings)
    assert outcome.outcome == "fallback_error"
    assert outcome.text == "Gap 0.42 to Smith."


def test_polish_timeout_falls_back_to_skeleton() -> None:
    graph = load_sequence_graph()
    node = graph.nodes["hunting"]
    settings = CommentarySettings(llm_polish=True)

    def opener(_req, timeout):  # noqa: ARG001
        raise TimeoutError

    skeleton = "Gap 0.42 to Smith."
    outcome = polish_skeleton(skeleton, node, settings, opener=opener)
    assert outcome.outcome == "fallback_timeout"
    assert outcome.text == skeleton


def test_tape_commentary_and_llm_rows(tmp_path: Path) -> None:
    tape = _open_tape(tmp_path)
    tape.record_commentary(
        {
            "action": "spoken",
            "reason": "spoken",
            "eventType": "HUNTING",
            "nodeId": "hunting",
            "text": "Gap 0.42.",
        },
        11.0,
        None,
    )
    tape.record_llm_polish(
        {
            "nodeId": "hunting",
            "outcome": "ok",
            "skeleton": "Gap 0.42.",
            "spoken": "He closes on Smith.",
        },
        11.5,
        None,
    )
    path = tape.path
    assert path is not None
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    types = [row["type"] for row in rows]
    assert "commentary" in types
    assert "llm_polish" in types


def test_build_polish_request_shape() -> None:
    settings = CommentarySettings(llm_model="qwen2.5:3b")
    req = build_polish_request("Line one.", settings)
    assert req["model"] == "qwen2.5:3b"
    assert req["messages"][0]["role"] == "system"
    assert "Line one." in req["messages"][1]["content"]


def test_process_sink_polish_hook_called(monkeypatch: pytest.MonkeyPatch) -> None:
    graph = load_sequence_graph()
    node = graph.nodes["hunting"]
    captured: list[dict] = []

    def fake_polish(skeleton, _node, settings, *, opener=None, past=False):  # noqa: ARG001
        return type(
            "O",
            (),
            {
                "text": "Polished line.",
                "outcome": "ok",
                "latency_ms": 1.0,
                "skeleton": skeleton,
                "request": {},
                "response": None,
                "debug_record": lambda self, node_id="", event_type="": {
                    "outcome": "ok",
                    "spoken": "Polished line.",
                },
            },
        )()

    monkeypatch.setattr("irswitch.commentary.tts.polish_skeleton", fake_polish)
    monkeypatch.setattr(
        "irswitch.commentary.tts.speak_text",
        lambda *args, **kwargs: type("R", (), {"backend": "null", "spoken": True, "error": None})(),
    )

    settings = CommentarySettings(llm_polish=True, tts_backend="null")
    sink = ProcessTtsSink(settings=settings, on_polish_debug=captured.append)
    from irswitch.commentary.tts import CommentaryUtterance

    sink._speak(
        CommentaryUtterance(
            node_id="hunting",
            locale="en",
            emotion="focused",
            text="Skeleton.",
            event_type="HUNTING",
            event_id="e1",
            correlation_id="c1",
            estimated_seconds=2.0,
            node=node,
        )
    )
    assert captured
    assert captured[0]["outcome"] == "ok"


def test_build_tts_sink_omits_hook_when_polish_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("irswitch.commentary.tts.detect_backend", lambda preferred="auto": "sapi")
    sink = build_tts_sink(CommentarySettings(llm_polish=False, tts_backend="sapi"))
    assert isinstance(sink, ProcessTtsSink)
    assert sink.on_polish_debug is None


def test_runtime_debug_gate_for_tape(monkeypatch: pytest.MonkeyPatch) -> None:
    set_runtime_log_level("INFO")
    assert logging.getLogger().getEffectiveLevel() == logging.INFO
    set_runtime_log_level("DEBUG")
    assert logging.getLogger().getEffectiveLevel() == logging.DEBUG
    set_runtime_log_level("INFO")
