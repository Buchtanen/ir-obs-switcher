"""#284 NarrativeRuntime Qwen enable + warmup preflight."""

from __future__ import annotations

from pathlib import Path

from irswitch.events import __all__ as events_exports
from irswitch.events.narrative_realization_bridge import warmup_qwen_component
from irswitch.events.qwen_transport import FakeTransport, LlmComponent, chat_completions_url
from irswitch.race.runtime import (
    commentary_llm_chat_url,
    commentary_llm_model,
    commentary_llm_timeout_ms,
)

SOURCE = (
    Path(__file__).resolve().parents[1]
    / "src"
    / "irswitch"
    / "events"
    / "narrative_realization_bridge.py"
)
RACE_SOURCE = Path(__file__).resolve().parents[1] / "src" / "irswitch" / "race" / "runtime.py"


def test_warmup_helper_not_exported() -> None:
    assert "warmup_qwen_component" not in events_exports
    assert "warmup_qwen_component" in SOURCE.read_text(encoding="utf-8")


def test_warmup_qwen_component_marks_ready_on_fake_transport() -> None:
    component = LlmComponent()
    transport = FakeTransport()
    assert component.qwen_ready is False
    assert warmup_qwen_component(component, transport, generation=3) is True
    assert component.qwen_ready is True
    assert component.residency == "warmup_succeeded"
    assert component.applied_generation == 3


def test_warmup_qwen_component_fails_closed_on_transport_error() -> None:
    component = LlmComponent()
    transport = FakeTransport(fail=True)
    assert warmup_qwen_component(component, transport, generation=2) is False
    assert component.qwen_ready is False
    assert component.status == "failed"
    assert component.residency == "warmup_failed"


def test_chat_completions_url_joins_v1_base() -> None:
    assert chat_completions_url(None) == "http://127.0.0.1:11434/v1/chat/completions"
    assert (
        chat_completions_url("http://192.168.0.38:11434/v1")
        == "http://192.168.0.38:11434/v1/chat/completions"
    )
    assert (
        chat_completions_url("http://192.168.0.38:11434/v1/chat/completions")
        == "http://192.168.0.38:11434/v1/chat/completions"
    )


def test_commentary_llm_helpers_read_v2_snapshot() -> None:
    class _Snap:
        values = {
            "commentary.llm.base_url": "http://192.168.0.38:11434/v1",
            "commentary.llm.model": "qwen3:4b-instruct-2507-q4_K_M",
            "commentary.llm.timeout_s": 4.0,
        }

    class _Cand:
        valid = True
        snapshot = _Snap()

    class _Cfg:
        commentary_v2 = _Cand()

    assert commentary_llm_chat_url(_Cfg()) == "http://192.168.0.38:11434/v1/chat/completions"
    assert commentary_llm_model(_Cfg()) == "qwen3:4b-instruct-2507-q4_K_M"
    assert commentary_llm_timeout_ms(_Cfg()) == 4000


def test_warmup_posts_resolved_endpoint() -> None:
    transport = FakeTransport()
    component = LlmComponent()
    assert (
        warmup_qwen_component(
            component,
            transport,
            endpoint="http://192.168.0.38:11434/v1",
        )
        is True
    )
    assert transport.last_url == "http://192.168.0.38:11434/v1/chat/completions"


def test_race_enables_qwen_and_calls_warmup() -> None:
    race = RACE_SOURCE.read_text(encoding="utf-8")
    assert "commentary_llm_enabled" in race
    assert "commentary_llm_chat_url" in race
    assert "warmup_qwen_component" in race
    assert "StdlibTransport" in race
    assert "endpoint=qwen_endpoint" in race
    # Soft-fail path must remain so missing Ollama does not crash startup.
    assert "warmup_qwen_component(" in race
